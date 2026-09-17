"""Parse Tableau calculated fields.

Extracts calculated field definitions from datasource column elements
and resolves internal name references to display captions.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from lxml import etree

from tab2pbi.models import ColumnInfo, DataType, FieldRole

logger = logging.getLogger(__name__)


def parse_calculations(
    ds_elem: etree._Element,
    columns: dict[str, ColumnInfo],
) -> dict[str, ColumnInfo]:
    """Parse calculated fields from a datasource element.

    Args:
        ds_elem: Datasource XML element.
        columns: Already-parsed columns dict for name resolution.

    Returns:
        Dictionary of calculated field internal names to ColumnInfo.
    """
    calc_fields: dict[str, ColumnInfo] = {}

    for col_elem in ds_elem.findall("column"):
        calc_elem = col_elem.find("calculation")
        if calc_elem is None:
            continue

        name = col_elem.get("name", "")
        caption = col_elem.get("caption", "")
        formula = calc_elem.get("formula", "")
        datatype = col_elem.get("datatype", "")
        role = col_elem.get("role", "")

        if not formula:
            continue

        logger.debug(f"Found calculated field: {caption or name} = {formula}")

        col = ColumnInfo(
            internal_name=name,
            caption=caption or name.strip("[]"),
            datatype=_parse_type(datatype),
            role=FieldRole.MEASURE if role == "measure" else FieldRole.DIMENSION,
            is_calculated=True,
            formula=formula,
        )

        calc_fields[name] = col

    # Also check columns dict for any calc fields found during metadata parsing
    for name, col in columns.items():
        if col.is_calculated and name not in calc_fields:
            calc_fields[name] = col

    return calc_fields


def resolve_formula_references(
    formula: str,
    columns: dict[str, ColumnInfo],
    calc_fields: dict[str, ColumnInfo],
) -> str:
    """Resolve internal references in a Tableau formula to display names.

    Tableau internally uses names like [Calculation_1234567890] which
    should be resolved to the field's display caption.

    Args:
        formula: The Tableau formula string.
        columns: Regular columns dictionary.
        calc_fields: Calculated fields dictionary.

    Returns:
        Formula with internal references replaced by captions.
    """
    # Find all [Name] references
    def replace_ref(match):
        ref = match.group(0)  # e.g. [Calculation_1234567890]
        # Try to find in calc fields first, then columns
        if ref in calc_fields:
            caption = calc_fields[ref].caption
            return f"[{caption}]"
        if ref in columns:
            caption = columns[ref].caption
            return f"[{caption}]"
        # Leave as-is if not found
        return ref

    # Match [anything] but not [Table].[Field] patterns
    resolved = re.sub(r'\[([^\]\.]+)\]', replace_ref, formula)
    return resolved


def classify_calculation(
    formula: str,
) -> str:
    """Classify a Tableau formula as 'measure' or 'column'.

    A formula is a measure if it contains aggregation functions
    or LOD expressions. Otherwise it's a row-level calculated column.

    Args:
        formula: The Tableau formula string.

    Returns:
        'measure' or 'column'.
    """
    formula_upper = formula.upper()

    # Check for aggregation functions
    agg_functions = [
        "SUM(", "AVG(", "COUNT(", "COUNTD(",
        "MIN(", "MAX(", "ATTR(", "MEDIAN(",
        "STDEV(", "STDEVP(", "VAR(", "VARP(",
    ]
    for func in agg_functions:
        if func in formula_upper:
            return "measure"

    # Check for LOD expressions
    if re.search(r'\{(?:FIXED|INCLUDE|EXCLUDE)\s', formula_upper):
        return "measure"

    return "column"


def _parse_type(type_str: str) -> DataType:
    """Convert Tableau type string to DataType enum."""
    type_map = {
        "string": DataType.STRING,
        "integer": DataType.INTEGER,
        "real": DataType.REAL,
        "date": DataType.DATE,
        "datetime": DataType.DATETIME,
        "boolean": DataType.BOOLEAN,
    }
    return type_map.get(type_str, DataType.STRING)
