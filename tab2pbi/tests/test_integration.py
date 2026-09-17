"""Integration tests for tab2pbi converting end-to-end sample workbooks."""

from pathlib import Path
import json
import pytest
from tab2pbi.validate import validate_output
from tab2pbi.extractor import extract
from tab2pbi.parser.datasources import parse_datasources
from tab2pbi.parser.worksheets import parse_worksheets
from tab2pbi.parser.dashboards import parse_dashboards
from tab2pbi.models import WorkbookModel
from tab2pbi.data_export import export_data
from tab2pbi.writers.semantic_model import write_semantic_model
from tab2pbi.writers.report import write_report
from tab2pbi.writers.pbip import write_pbip
from tab2pbi.report_writer import ConversionReport


SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "samples"


def test_convert_iris_twb_end_to_end(tmp_path: Path):
    twb_path = SAMPLES_DIR / "iris_dashboard.twb"
    assert twb_path.exists()

    project_name = "Iris_TWB_Test"
    project_dir = tmp_path / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    # 1. Extract
    wb = extract(twb_path)
    assert wb.twb_path.exists()

    # 2. Parse
    datasources = parse_datasources(wb.root)
    assert len(datasources) == 1
    ds = datasources[0]
    assert len(ds.columns) >= 5
    assert len(ds.calculated_fields) == 4

    worksheets = parse_worksheets(wb.root)
    assert len(worksheets) == 4

    dashboards = parse_dashboards(wb.root)
    assert len(dashboards) == 1

    model = WorkbookModel(
        name=project_name,
        datasources=datasources,
        worksheets=worksheets,
        dashboards=dashboards,
    )

    # 3. Export data
    export_result = export_data(ds, wb.data_files, project_dir)
    assert len(export_result.exported_tables) >= 1
    table_name = next(iter(export_result.exported_tables.keys()))
    assert export_result.row_counts[table_name] == 150

    # 4. Semantic model
    sm_dir, calcs = write_semantic_model(model, project_dir, export_result.exported_tables, table_name)
    assert sm_dir.exists()
    assert len(calcs) == 4
    # All 4 calcs should be successfully converted
    for c in calcs:
        assert c.status == "converted"

    # 5. Report
    rep_dir = write_report(model, project_dir, table_name)
    assert rep_dir.exists()

    # 6. PBIP
    pbip_file = write_pbip(project_dir, project_name)
    assert pbip_file.exists()

    # 7. Conversion report
    report = ConversionReport(project_name)
    report_json_path = report.write_json(project_dir)
    assert report_json_path.exists()

    # 8. Validation
    val_res = validate_output(project_dir)
    assert val_res.is_valid, f"Validation errors: {val_res.errors}"


def test_convert_iris_twbx_end_to_end(tmp_path: Path):
    twbx_path = SAMPLES_DIR / "iris_dashboard.twbx"
    assert twbx_path.exists()

    project_name = "Iris_TWBX_Test"
    project_dir = tmp_path / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    # Extract .twbx (tests zip extraction)
    wb = extract(twbx_path)
    try:
        assert wb.twb_path.exists()
        assert len(wb.data_files) >= 1

        datasources = parse_datasources(wb.root)
        worksheets = parse_worksheets(wb.root)
        dashboards = parse_dashboards(wb.root)

        model = WorkbookModel(
            name=project_name,
            datasources=datasources,
            worksheets=worksheets,
            dashboards=dashboards,
        )

        export_result = export_data(datasources[0], wb.data_files, project_dir)
        table_name = next(iter(export_result.exported_tables.keys()))

        sm_dir, calcs = write_semantic_model(model, project_dir, export_result.exported_tables, table_name)
        rep_dir = write_report(model, project_dir, table_name)
        pbip_file = write_pbip(project_dir, project_name)

        val_res = validate_output(project_dir)
        assert val_res.is_valid, f"Validation errors: {val_res.errors}"
    finally:
        wb.cleanup()
