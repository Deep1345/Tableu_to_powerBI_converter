"""Type mapping between Tableau and Power BI.

Maps Tableau data types to TMDL dataType and Power Query M type names.
"""

from __future__ import annotations

from tab2pbi.models import DataType, FieldRole


# Tableau datatype -> TMDL dataType
TMDL_TYPE_MAP: dict[DataType, str] = {
    DataType.STRING: "string",
    DataType.INTEGER: "int64",
    DataType.REAL: "double",
    DataType.DATE: "dateTime",
    DataType.DATETIME: "dateTime",
    DataType.BOOLEAN: "boolean",
    DataType.UNKNOWN: "string",
}

# Tableau datatype -> Power Query M type
PQ_TYPE_MAP: dict[DataType, str] = {
    DataType.STRING: "type text",
    DataType.INTEGER: "Int64.Type",
    DataType.REAL: "type number",
    DataType.DATE: "type date",
    DataType.DATETIME: "type datetime",
    DataType.BOOLEAN: "type logical",
    DataType.UNKNOWN: "type text",
}

# Format strings for common types in TMDL
FORMAT_STRING_MAP: dict[DataType, str] = {
    DataType.INTEGER: "0",
    DataType.REAL: "#,0.00",
    DataType.DATE: "yyyy-mm-dd",
    DataType.DATETIME: "yyyy-mm-dd hh:nn:ss",
}


def to_tmdl_type(datatype: DataType) -> str:
    """Convert Tableau datatype to TMDL dataType string."""
    return TMDL_TYPE_MAP.get(datatype, "string")


def to_pq_type(datatype: DataType) -> str:
    """Convert Tableau datatype to Power Query M type string."""
    return PQ_TYPE_MAP.get(datatype, "type text")


def get_summarize_by(role: FieldRole, datatype: DataType) -> str:
    """Determine the summarizeBy value for a column.

    Measures with numeric types get 'sum', everything else gets 'none'.
    """
    if role == FieldRole.MEASURE and datatype in (DataType.INTEGER, DataType.REAL):
        return "sum"
    return "none"


def get_format_string(datatype: DataType) -> str:
    """Get a default format string for a data type."""
    return FORMAT_STRING_MAP.get(datatype, "")


def tmdl_quote_name(name: str) -> str:
    """Quote a name for TMDL if it contains special characters.

    TMDL uses single quotes for names with spaces, special chars, or
    that start with digits.
    """
    if not name:
        return "''"

    needs_quoting = (
        ' ' in name or
        "'" in name or
        name[0].isdigit() or
        any(c in name for c in '[]{}().,;:!@#$%^&*+-=<>?/\\|~`"')
    )

    if needs_quoting:
        # Escape single quotes by doubling them
        escaped = name.replace("'", "''")
        return f"'{escaped}'"

    return name


def m_escape_path(path: str) -> str:
    """Escape a file path for use in Power Query M expressions.

    Backslashes need to be escaped in M strings.
    """
    return path.replace("\\", "\\\\")
