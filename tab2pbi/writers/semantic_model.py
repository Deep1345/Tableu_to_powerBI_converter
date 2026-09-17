"""Write TMDL Semantic Model files for Power BI.

Generates the .SemanticModel/ folder structure with:
- definition.pbism
- definition/database.tmdl
- definition/model.tmdl
- definition/tables/<Table>.tmdl (one per table)
- definition/relationships.tmdl (if joins exist)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tab2pbi.converters.dax import convert_formula
from tab2pbi.converters.types import (
    get_format_string, get_summarize_by, m_escape_path,
    tmdl_quote_name, to_pq_type, to_tmdl_type,
)
from tab2pbi.models import (
    ColumnInfo, DataType, Datasource, FieldRole, WorkbookModel,
)
from tab2pbi.parser.calculations import classify_calculation

logger = logging.getLogger(__name__)


@dataclass
class ConvertedCalc:
    """Result of converting a calculated field."""
    name: str
    original_formula: str
    dax_formula: str
    calc_type: str       # 'measure' or 'column'
    status: str          # 'converted' or 'unsupported'


def write_semantic_model(
    model: WorkbookModel,
    output_dir: Path,
    data_paths: dict[str, Path],
    table_name: str = "",
) -> tuple[Path, list[ConvertedCalc]]:
    """Write the complete .SemanticModel folder.

    Args:
        model: The workbook intermediate model.
        output_dir: Base output directory.
        data_paths: Mapping of table name to CSV file path.
        table_name: Override table name (if empty, uses datasource caption).

    Returns:
        Tuple of (semantic_model_dir, list_of_converted_calcs).
    """
    name = model.name
    sm_dir = output_dir / f"{name}.SemanticModel"
    def_dir = sm_dir / "definition"
    tables_dir = def_dir / "tables"

    # Create directory structure
    sm_dir.mkdir(parents=True, exist_ok=True)
    def_dir.mkdir(exist_ok=True)
    tables_dir.mkdir(exist_ok=True)

    # Get the primary datasource
    ds = model.get_primary_datasource()

    # Determine table name
    if not table_name and ds:
        table_name = ds.caption or ds.name.split(".")[-1]
    if not table_name:
        table_name = "Table"

    # Clean table name
    table_name = table_name.replace("[", "").replace("]", "").strip()
    if not table_name:
        table_name = "Table"

    # Write definition.pbism
    _write_pbism(sm_dir)

    # Write database.tmdl
    _write_database_tmdl(def_dir, name)

    # Collect all tables and their columns
    tables_info = _collect_tables(ds, table_name, data_paths)

    # Check for date column
    date_column = _find_date_column(ds)

    # Write model.tmdl (references all tables)
    all_table_names = [t["name"] for t in tables_info]
    if date_column:
        all_table_names.append("DateTable")  # Auto-generated date table only when date column exists
    _write_model_tmdl(def_dir, all_table_names)

    # Convert calculated fields
    converted_calcs = []
    if ds:
        converted_calcs = _convert_all_calcs(ds, table_name)

    # Write table TMDL files
    for table_info in tables_info:
        _write_table_tmdl(
            tables_dir, table_info, converted_calcs
        )

    # Write DateTable only if date column exists
    if date_column:
        _write_date_table_tmdl(tables_dir, table_name, date_column)

    # Write relationships
    _write_relationships_tmdl(def_dir, ds, table_name, date_column)

    logger.info(f"Semantic model written to {sm_dir}")
    return sm_dir, converted_calcs


def _write_pbism(sm_dir: Path):
    """Write definition.pbism file."""
    content = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.0",
        "settings": {}
    }
    (sm_dir / "definition.pbism").write_text(
        json.dumps(content, indent=2), encoding="utf-8"
    )


def _write_database_tmdl(def_dir: Path, name: str = "Database"):
    """Write definition/database.tmdl file."""
    quoted = tmdl_quote_name(name) if name else "Database"
    content = (
        f"database {quoted}\n"
        "\tcompatibilityLevel: 1567\n"
    )
    (def_dir / "database.tmdl").write_text(content, encoding="utf-8")


def _write_model_tmdl(def_dir: Path, table_names: list[str]):
    """Write definition/model.tmdl file."""
    lines = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "",
    ]

    for table in table_names:
        quoted = tmdl_quote_name(table)
        lines.append(f"\tref table {quoted}")

    content = "\n".join(lines) + "\n"
    (def_dir / "model.tmdl").write_text(content, encoding="utf-8")


def _collect_tables(
    ds: Optional[Datasource],
    default_table_name: str,
    data_paths: dict[str, Path],
) -> list[dict]:
    """Collect table information for TMDL generation."""
    tables = []

    if not ds:
        # Create a default table from available data
        for csv_name, csv_path in data_paths.items():
            table_name = csv_name.replace(".csv", "").replace("_", " ").title()
            if not table_name:
                table_name = default_table_name

            tables.append({
                "name": table_name if table_name != default_table_name else default_table_name,
                "csv_path": str(csv_path.resolve()),
                "columns": [],
            })
        return tables

    # Use datasource columns
    columns = []
    for col in ds.columns.values():
        if col.is_generated:
            continue
        if col.is_calculated:
            continue
        columns.append(col)

    # Match to CSV data paths
    csv_path = ""
    if data_paths:
        # Use the first available CSV
        first_path = next(iter(data_paths.values()))
        csv_path = str(first_path.resolve())

    tables.append({
        "name": default_table_name,
        "csv_path": csv_path,
        "columns": columns,
    })

    return tables


def _convert_all_calcs(
    ds: Datasource,
    table_name: str,
) -> list[ConvertedCalc]:
    """Convert all calculated fields from a datasource."""
    converted = []

    for name, col in ds.calculated_fields.items():
        if not col.formula:
            continue

        dax, calc_type, status = convert_formula(
            col.formula,
            table_name=table_name,
            columns=ds.columns,
        )

        converted.append(ConvertedCalc(
            name=col.caption or col.internal_name.strip("[]"),
            original_formula=col.formula,
            dax_formula=dax,
            calc_type=calc_type,
            status=status,
        ))

        logger.debug(
            f"Calc '{col.caption}': {col.formula} -> {dax} ({calc_type}, {status})"
        )

    return converted


def _write_table_tmdl(
    tables_dir: Path,
    table_info: dict,
    converted_calcs: list[ConvertedCalc],
):
    """Write a single table's TMDL file."""
    table_name = table_info["name"]
    csv_path = table_info["csv_path"]
    columns = table_info.get("columns", [])
    quoted_name = tmdl_quote_name(table_name)

    lines = [f"table {quoted_name}"]
    lines.append(f"\tlineageTag: {_generate_guid()}")
    lines.append("")

    # If we have columns from metadata, use them
    if columns:
        for col in columns:
            col_name = col.caption or col.internal_name.strip("[]")
            tmdl_type = to_tmdl_type(col.datatype)
            summarize = get_summarize_by(col.role, col.datatype)

            lines.append(f"\tcolumn {tmdl_quote_name(col_name)}")
            lines.append(f"\t\tdataType: {tmdl_type}")
            lines.append(f"\t\tlineageTag: {_generate_guid()}")
            lines.append(f"\t\tsummarizeBy: {summarize}")
            lines.append(f"\t\tsourceColumn: {col_name}")
            lines.append("")
    else:
        # No metadata - try to infer from CSV
        if csv_path and os.path.exists(csv_path):
            try:
                import pandas as pd
                df = pd.read_csv(csv_path, nrows=5)
                for col_name in df.columns:
                    dtype = df[col_name].dtype
                    if dtype in ('int64', 'int32'):
                        tmdl_type = "int64"
                        summarize = "sum"
                    elif dtype in ('float64', 'float32'):
                        tmdl_type = "double"
                        summarize = "sum"
                    elif 'datetime' in str(dtype):
                        tmdl_type = "dateTime"
                        summarize = "none"
                    else:
                        tmdl_type = "string"
                        summarize = "none"

                    lines.append(f"\tcolumn {tmdl_quote_name(str(col_name))}")
                    lines.append(f"\t\tdataType: {tmdl_type}")
                    lines.append(f"\t\tlineageTag: {_generate_guid()}")
                    lines.append(f"\t\tsummarizeBy: {summarize}")
                    lines.append(f"\t\tsourceColumn: {col_name}")
                    lines.append("")
            except Exception as e:
                logger.warning(f"Could not read CSV for column inference: {e}")

    # Write measures (calculated fields of type 'measure')
    for calc in converted_calcs:
        if calc.calc_type == "measure":
            measure_name = tmdl_quote_name(calc.name)
            lines.append(f"\tmeasure {measure_name} = {calc.dax_formula}")
            lines.append(f"\t\tlineageTag: {_generate_guid()}")
            if calc.status == "unsupported":
                escaped_formula = calc.original_formula.replace("\n", " ").replace("\t", " ")
                lines.append(f"\t\t/// Original Tableau formula: {escaped_formula}")
            lines.append("")

    # Write calculated columns
    for calc in converted_calcs:
        if calc.calc_type == "column":
            col_name = tmdl_quote_name(calc.name)
            lines.append(f"\tcolumn {col_name} = {calc.dax_formula}")
            lines.append(f"\t\tlineageTag: {_generate_guid()}")
            lines.append(f"\t\tdataType: string")
            lines.append(f"\t\tsummarizeBy: none")
            if calc.status == "unsupported":
                escaped_formula = calc.original_formula.replace("\n", " ").replace("\t", " ")
                lines.append(f"\t\t/// Original Tableau formula: {escaped_formula}")
            lines.append("")

    # Write partition (data source connection)
    if csv_path:
        lines.append(f"\tpartition {quoted_name} = m")
        lines.append(f"\t\tmode: import")
        lines.append(f"\t\tsource =")
        lines.append(f"\t\t\tlet")

        b64_content = ""
        if os.path.exists(csv_path):
            import base64
            with open(csv_path, "rb") as f:
                b64_content = base64.b64encode(f.read()).decode("ascii")

        if b64_content:
            lines.append(f'\t\t\t\tSourceBinary = Binary.FromText("{b64_content}", BinaryEncoding.Base64),')
            lines.append(f'\t\t\t\tSource = Csv.Document(SourceBinary, [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),')
            lines.append(f"\t\t\t\tPromoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),")
        else:
            lines.append(f'\t\t\t\tPromoted = #table({{"Column1"}}, {{}}),')

        # Build type transforms
        if columns:
            type_pairs = []
            for col in columns:
                col_name = col.caption or col.internal_name.strip("[]")
                pq_type = to_pq_type(col.datatype)
                type_pairs.append(f'{{"{col_name}", {pq_type}}}')
            type_list = ", ".join(type_pairs)
            lines.append(f"\t\t\t\tTyped = Table.TransformColumnTypes(Promoted, {{{type_list}}})")
        else:
            lines.append(f"\t\t\t\tTyped = Promoted")

        lines.append(f"\t\t\tin")
        lines.append(f"\t\t\t\tTyped")

    lines.append("")

    # Write file
    filename = table_name.replace(" ", "_").replace("'", "") + ".tmdl"
    (tables_dir / filename).write_text("\n".join(lines), encoding="utf-8")

    logger.info(f"Wrote table TMDL: {filename}")


def _write_date_table_tmdl(
    tables_dir: Path,
    main_table: str,
    date_column: Optional[str],
):
    """Write the auto-generated DateTable."""
    quoted_main = tmdl_quote_name(main_table)
    date_col = date_column or "Date"

    lines = [
        "table DateTable",
        f"\tlineageTag: {_generate_guid()}",
        "\tdataCategory: Time",
        "",
        "\tcolumn Date",
        "\t\tdataType: dateTime",
        f"\t\tlineageTag: {_generate_guid()}",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: Date",
        "\t\tisKey: true",
        "",
        "\tcolumn Year = YEAR([Date])",
        f"\t\tlineageTag: {_generate_guid()}",
        "\t\tdataType: int64",
        "\t\tsummarizeBy: none",
        "",
        "\tcolumn Quarter = \"Q\" & FORMAT([Date], \"Q\")",
        f"\t\tlineageTag: {_generate_guid()}",
        "\t\tdataType: string",
        "\t\tsummarizeBy: none",
        "\t\tsortByColumn: QuarterNo",
        "",
        "\tcolumn QuarterNo = QUARTER([Date])",
        f"\t\tlineageTag: {_generate_guid()}",
        "\t\tdataType: int64",
        "\t\tsummarizeBy: none",
        "",
        "\tcolumn Month = FORMAT([Date], \"MMMM\")",
        f"\t\tlineageTag: {_generate_guid()}",
        "\t\tdataType: string",
        "\t\tsummarizeBy: none",
        "\t\tsortByColumn: MonthNo",
        "",
        "\tcolumn MonthNo = MONTH([Date])",
        f"\t\tlineageTag: {_generate_guid()}",
        "\t\tdataType: int64",
        "\t\tsummarizeBy: none",
        "",
        f"\tpartition DateTable = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\tlet",
        f"\t\t\t\tMinDate = List.Min({quoted_main}[{date_col}]),",
        f"\t\t\t\tMaxDate = List.Max({quoted_main}[{date_col}]),",
        "\t\t\t\tDates = List.Dates(MinDate, Duration.Days(MaxDate - MinDate) + 1, #duration(1, 0, 0, 0)),",
        "\t\t\t\tTable = Table.FromList(Dates, Splitter.SplitByNothing(), {\"Date\"}, null, ExtraValues.Error),",
        "\t\t\t\tTyped = Table.TransformColumnTypes(Table, {{\"Date\", type date}})",
        "\t\t\tin",
        "\t\t\t\tTyped",
        "",
    ]

    (tables_dir / "DateTable.tmdl").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def _write_relationships_tmdl(
    def_dir: Path,
    ds: Optional[Datasource],
    main_table: str,
    date_column: Optional[str],
):
    """Write relationships.tmdl if needed."""
    lines = []

    # Always add DateTable relationship
    if date_column:
        lines.extend([
            f"relationship {_generate_guid()}",
            f"\tfromColumn: {tmdl_quote_name(main_table)}.[{date_column}]",
            f"\ttoColumn: DateTable.[Date]",
            "",
        ])

    # Add join-based relationships from datasource
    if ds:
        for table in ds.tables:
            if table.is_join and table.join_info:
                for clause in table.join_info.clauses:
                    rel_id = _generate_guid()
                    lines.extend([
                        f"relationship {rel_id}",
                        f"\tfromColumn: {tmdl_quote_name(clause.left_table)}.[{clause.left_column}]",
                        f"\ttoColumn: {tmdl_quote_name(clause.right_table)}.[{clause.right_column}]",
                        "",
                    ])

    if lines:
        (def_dir / "relationships.tmdl").write_text(
            "\n".join(lines), encoding="utf-8"
        )


def _find_date_column(ds: Optional[Datasource]) -> Optional[str]:
    """Find the primary date column in a datasource."""
    if not ds:
        return None

    for col in ds.columns.values():
        if col.datatype in (DataType.DATE, DataType.DATETIME):
            if not col.is_calculated and not col.is_generated:
                return col.caption or col.internal_name.strip("[]")

    # Try to guess from column names
    date_keywords = ["date", "order_date", "ship_date", "created", "timestamp"]
    for col in ds.columns.values():
        for kw in date_keywords:
            if kw in col.caption.lower() or kw in col.internal_name.lower():
                return col.caption or col.internal_name.strip("[]")

    return None


_guid_counter = 0

def _generate_guid() -> str:
    """Generate a deterministic GUID-like string for lineage tags."""
    global _guid_counter
    _guid_counter += 1
    hex_part = format(_guid_counter, '032x')
    return f"{hex_part[:8]}-{hex_part[8:12]}-{hex_part[12:16]}-{hex_part[16:20]}-{hex_part[20:32]}"
