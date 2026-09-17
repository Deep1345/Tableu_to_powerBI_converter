"""CLI entry point for tab2pbi.

Usage:
    python -m tab2pbi input.twbx --out ./output
    python -m tab2pbi input.twb --out ./output --name MyProject
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from tab2pbi.converters.visuals import map_visual
from tab2pbi.data_export import export_data
from tab2pbi.extractor import extract, ExtractionError
from tab2pbi.models import WorkbookModel
from tab2pbi.parser.calculations import parse_calculations, resolve_formula_references
from tab2pbi.parser.dashboards import parse_dashboards
from tab2pbi.parser.datasources import parse_datasources
from tab2pbi.parser.worksheets import parse_worksheets
from tab2pbi.report_writer import ConversionReport
from tab2pbi.validate import validate_output
from tab2pbi.writers.pbip import write_pbip
from tab2pbi.writers.report import write_report
from tab2pbi.writers.semantic_model import write_semantic_model

logger = logging.getLogger("tab2pbi")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="tab2pbi",
        description="Convert Tableau workbooks (.twb/.twbx) to Power BI Project files (.pbip)",
    )
    parser.add_argument(
        "input",
        help="Path to .twb or .twbx file",
    )
    parser.add_argument(
        "--out", "-o",
        default="./output",
        help="Output directory (default: ./output)",
    )
    parser.add_argument(
        "--name", "-n",
        default="",
        help="Override project name (default: derived from input filename)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and dump intermediate.json",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run validation after conversion",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.debug else (
        logging.INFO if args.verbose else logging.WARNING
    )
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    input_path = Path(args.input)
    output_dir = Path(args.out)

    # Determine project name
    name = args.name or input_path.stem
    # Clean name for file system
    name = name.replace(" ", "_").replace(".", "_")

    project_dir = output_dir / name
    project_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔄 Converting: {input_path}")
    print(f"📁 Output: {project_dir}")
    print()

    report = ConversionReport(name)

    try:
        # ── Step 1: Extract ──
        print("📦 Step 1: Extracting workbook...")
        workbook = extract(input_path)
        logger.info(f"Extracted workbook from {input_path}")

        # ── Step 2: Parse ──
        print("🔍 Step 2: Parsing Tableau XML...")
        root = workbook.root

        # Parse datasources
        datasources = parse_datasources(root)
        print(f"   Found {len(datasources)} datasource(s)")

        for ds in datasources:
            report.add_datasource(ds.caption or ds.name, ds.connection.class_name)

            # Resolve calculated field references
            for calc_name, calc in ds.calculated_fields.items():
                if calc.formula:
                    calc.formula = resolve_formula_references(
                        calc.formula, ds.columns, ds.calculated_fields
                    )

        # Parse worksheets
        worksheets = parse_worksheets(root)
        print(f"   Found {len(worksheets)} worksheet(s)")

        # Parse dashboards
        dashboards = parse_dashboards(root)
        print(f"   Found {len(dashboards)} dashboard(s)")

        # Build intermediate model
        model = WorkbookModel(
            name=name,
            datasources=datasources,
            worksheets=worksheets,
            dashboards=dashboards,
        )

        # Dump intermediate model for debugging
        if args.debug:
            intermediate_path = project_dir / "intermediate.json"
            intermediate_path.write_text(model.to_json(), encoding="utf-8")
            print(f"   Dumped intermediate model to {intermediate_path}")

        # ── Step 3: Export data ──
        print("💾 Step 3: Exporting data...")
        primary_ds = model.get_primary_datasource()
        data_paths = {}

        if primary_ds and workbook.data_files:
            export_result = export_data(
                primary_ds, workbook.data_files, project_dir
            )
            data_paths = export_result.exported_tables

            for table, path in export_result.exported_tables.items():
                row_count = export_result.row_counts.get(table, 0)
                report.add_table(table, row_count, str(path))
                print(f"   Exported: {table} ({row_count:,} rows)")

            for err in export_result.errors:
                report.add_warning(f"Data export: {err}")
                logger.warning(f"Data export error: {err}")

        elif workbook.data_files:
            # No datasource metadata, but we have data files
            from tab2pbi.models import Datasource
            dummy_ds = Datasource(name="data", caption="Data")
            export_result = export_data(
                dummy_ds, workbook.data_files, project_dir
            )
            data_paths = export_result.exported_tables

            for table, path in export_result.exported_tables.items():
                row_count = export_result.row_counts.get(table, 0)
                report.add_table(table, row_count, str(path))
                print(f"   Exported: {table} ({row_count:,} rows)")

        else:
            print("   ⚠️  No data files found")
            report.add_warning("No data files found in workbook")

        # Determine table name for Power BI
        table_name = ""
        if primary_ds:
            table_name = primary_ds.caption or primary_ds.name.split(".")[-1]
        if not table_name and data_paths:
            table_name = next(iter(data_paths.keys()))
        if not table_name:
            table_name = "Table"
        table_name = table_name.replace("[", "").replace("]", "").strip()

        # ── Step 4-5: Write Semantic Model ──
        print("📊 Step 4-5: Writing Semantic Model (TMDL)...")
        sm_dir, converted_calcs = write_semantic_model(
            model, project_dir, data_paths, table_name
        )
        print(f"   Semantic model: {sm_dir.name}")

        for calc in converted_calcs:
            report.add_calculation(
                calc.name, calc.original_formula,
                calc.dax_formula, calc.calc_type, calc.status,
            )
            if calc.status == "converted":
                print(f"   ✅ Calc: {calc.name} -> {calc.dax_formula[:60]}")
            else:
                print(f"   ⚠️  Calc: {calc.name} (unsupported)")

        # ── Step 6-7: Write Report ──
        print("📈 Step 6-7: Writing Report (PBIR)...")

        # Map visuals and record in report
        for ws in model.worksheets:
            vm = map_visual(ws, table_name)
            report.add_worksheet(
                ws.name, ws.resolved_mark.value,
                vm.visual_type, vm.projections,
                vm.status, vm.warnings,
            )
            print(f"   {ws.name}: {ws.resolved_mark.value} -> {vm.visual_type}")

        report_dir = write_report(model, project_dir, table_name)
        print(f"   Report: {report_dir.name}")

        for db in model.dashboards:
            ws_count = len([z for z in db.zones if z.worksheet_name])
            report.add_dashboard(db.name, db.name, ws_count)

        # ── Step 8: Write .pbip ──
        print("📝 Step 8: Writing .pbip project file...")
        pbip_path = write_pbip(project_dir, name)
        print(f"   Project file: {pbip_path.name}")

        # ── Step 9: Conversion report ──
        print("📋 Step 9: Writing conversion report...")
        report.write_json(project_dir)
        report.write_markdown(project_dir)

        # Cleanup temp files
        workbook.cleanup()

        print()
        print("=" * 60)
        print(f"✅ Conversion complete!")
        print(f"📁 Output: {project_dir}")
        print(f"📄 Open {pbip_path.name} in Power BI Desktop")
        print(f"📋 See conversion_report.md for details")
        print("=" * 60)

        # ── Optional: Validate ──
        if args.validate:
            print()
            print("🔍 Running validation...")
            val_result = validate_output(project_dir)
            print(val_result.summary())

    except ExtractionError as e:
        print(f"\n❌ Extraction error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception("Conversion failed")
        print(f"\n❌ Conversion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
