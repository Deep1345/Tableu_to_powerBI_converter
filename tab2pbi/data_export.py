"""Export data from Tableau data sources to clean CSV files.

Supports .hyper (via tableauhyperapi), .csv, and .xlsx files.
"""

from __future__ import annotations

import csv
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd

from tab2pbi.models import ColumnInfo, Datasource

logger = logging.getLogger(__name__)


class DataExportResult:
    """Results of a data export operation."""

    def __init__(self):
        self.exported_tables: dict[str, Path] = {}  # table_name -> csv_path
        self.row_counts: dict[str, int] = {}
        self.column_mappings: dict[str, dict[str, str]] = {}  # table -> {orig: clean}
        self.errors: list[str] = []


def export_data(
    datasource: Datasource,
    data_files: dict[str, Path],
    output_dir: Path,
) -> DataExportResult:
    """Export data from a datasource's data files to CSV.

    Args:
        datasource: The datasource model.
        data_files: Mapping of filename to path.
        output_dir: Directory to write CSV files to.

    Returns:
        DataExportResult with paths and metadata.
    """
    result = DataExportResult()
    data_dir = output_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    conn = datasource.connection

    # Determine which data file to use
    target_file = None

    # Try to match by connection filename
    if conn.filename:
        fname = Path(conn.filename).name
        if fname in data_files:
            target_file = data_files[fname]
    if conn.dbname:
        fname = Path(conn.dbname).name
        if fname in data_files:
            target_file = data_files[fname]

    # If no match, try by connection class
    if not target_file:
        for name, path in data_files.items():
            ext = path.suffix.lower()
            if conn.class_name == "hyper" and ext == ".hyper":
                target_file = path
                break
            elif conn.class_name == "textscan" and ext == ".csv":
                target_file = path
                break
            elif conn.class_name in ("excel-direct", "excel") and ext in (".xlsx", ".xls"):
                target_file = path
                break

    # Last resort: use any available data file
    if not target_file and data_files:
        target_file = next(iter(data_files.values()))

    if not target_file:
        result.errors.append("No data file found for datasource")
        return result

    ext = target_file.suffix.lower()
    logger.info(f"Exporting data from {target_file.name} ({ext})")

    try:
        if ext == ".hyper":
            _export_hyper(target_file, data_dir, datasource, result)
        elif ext == ".csv":
            _export_csv(target_file, data_dir, datasource, result)
        elif ext in (".xlsx", ".xls"):
            _export_excel(target_file, data_dir, datasource, result)
        else:
            result.errors.append(f"Unsupported data file type: {ext}")
    except Exception as e:
        logger.error(f"Error exporting data: {e}")
        result.errors.append(str(e))

    return result


def _export_hyper(
    hyper_path: Path,
    output_dir: Path,
    datasource: Datasource,
    result: DataExportResult,
):
    """Export data from a .hyper file."""
    try:
        from tableauhyperapi import (
            HyperProcess, Telemetry, Connection, TableName, SchemaName
        )
    except ImportError:
        logger.warning(
            "tableauhyperapi not installed. "
            "Hyper file export skipped."
        )
        result.errors.append(
            "tableauhyperapi not installed - cannot export .hyper files"
        )
        return

    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(
            endpoint=hyper.endpoint,
            database=str(hyper_path),
        ) as connection:
            # List all schemas and tables
            schemas = connection.catalog.get_schema_names()

            for schema in schemas:
                tables = connection.catalog.get_table_names(schema)

                for table_name in tables:
                    full_name = str(table_name)
                    clean_name = _clean_table_name(
                        table_name.name.unescaped
                    )

                    logger.info(f"Reading table: {full_name}")

                    # Read table into DataFrame
                    rows = connection.execute_list_query(
                        f"SELECT * FROM {table_name}"
                    )
                    columns = connection.catalog.get_table_definition(
                        table_name
                    ).columns
                    col_names = [col.name.unescaped for col in columns]

                    df = pd.DataFrame(rows, columns=col_names)

                    # Clean column names
                    col_mapping = _clean_column_names(df, datasource)
                    result.column_mappings[clean_name] = col_mapping

                    # Write CSV
                    csv_path = output_dir / f"{clean_name}.csv"
                    df.to_csv(csv_path, index=False, encoding="utf-8")

                    result.exported_tables[clean_name] = csv_path
                    result.row_counts[clean_name] = len(df)

                    logger.info(
                        f"Exported {len(df)} rows to {csv_path.name}"
                    )


def _export_csv(
    csv_path: Path,
    output_dir: Path,
    datasource: Datasource,
    result: DataExportResult,
):
    """Export (copy and clean) a CSV file."""
    # Read and re-write for consistent encoding
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding="latin1")

    table_name = _clean_table_name(csv_path.stem)

    # Clean column names
    col_mapping = _clean_column_names(df, datasource)
    result.column_mappings[table_name] = col_mapping

    out_path = output_dir / f"{table_name}.csv"
    df.to_csv(out_path, index=False, encoding="utf-8")

    result.exported_tables[table_name] = out_path
    result.row_counts[table_name] = len(df)

    logger.info(f"Exported {len(df)} rows to {out_path.name}")


def _export_excel(
    excel_path: Path,
    output_dir: Path,
    datasource: Datasource,
    result: DataExportResult,
):
    """Export Excel sheets to CSV files."""
    try:
        xls = pd.ExcelFile(excel_path, engine="openpyxl")
    except Exception:
        xls = pd.ExcelFile(excel_path)

    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        table_name = _clean_table_name(sheet_name)

        # Clean column names
        col_mapping = _clean_column_names(df, datasource)
        result.column_mappings[table_name] = col_mapping

        out_path = output_dir / f"{table_name}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8")

        result.exported_tables[table_name] = out_path
        result.row_counts[table_name] = len(df)

        logger.info(f"Exported sheet '{sheet_name}': {len(df)} rows")


def _clean_column_names(
    df: pd.DataFrame,
    datasource: Datasource,
) -> dict[str, str]:
    """Clean DataFrame column names, matching to Tableau captions.

    Returns a mapping of original -> cleaned column names.
    Also renames the DataFrame columns in place.
    """
    mapping = {}
    new_columns = []

    for col in df.columns:
        original = str(col)

        # Try to match with Tableau column captions
        matched_caption = None
        for tab_col in datasource.columns.values():
            if (tab_col.remote_name == original or
                tab_col.caption == original or
                tab_col.internal_name.strip("[]") == original):
                matched_caption = tab_col.caption
                break

        if matched_caption:
            clean = _sanitize_column_name(matched_caption)
        else:
            clean = _sanitize_column_name(original)

        mapping[original] = clean
        new_columns.append(clean)

    # Handle duplicate column names
    seen = {}
    for i, name in enumerate(new_columns):
        if name in seen:
            seen[name] += 1
            new_columns[i] = f"{name}_{seen[name]}"
        else:
            seen[name] = 0

    df.columns = new_columns
    return mapping


def _sanitize_column_name(name: str) -> str:
    """Sanitize a column name for Power BI compatibility."""
    # Replace problematic characters but keep spaces and common chars
    clean = name.strip()
    # Remove leading/trailing brackets
    clean = clean.strip("[]")
    return clean if clean else "Column"


def _clean_table_name(name: str) -> str:
    """Clean a table name for file system and Power BI."""
    clean = name.strip()
    # Remove characters that are invalid in filenames
    for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        clean = clean.replace(char, '_')
    return clean if clean else "Table"
