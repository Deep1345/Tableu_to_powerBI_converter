"""Parse Tableau worksheet XML.

Extracts mark types, row/col shelves, encodings, and filters
from /workbook/worksheets/worksheet elements.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from lxml import etree

from tab2pbi.models import (
    AggregationType, FieldKind, FilterInfo, FilterType,
    MarkType, ShelfField, Worksheet,
)

logger = logging.getLogger(__name__)

# Regex to parse shelf tokens like:
# [federated.abc].[sum:Sales:qk]
# [datasource].[agg:field:kind]
SHELF_TOKEN_RE = re.compile(
    r'\[([^\]]+)\]\.\[(\w+):([^:]+?):(nk|ok|qk)\]'
)

# Simpler pattern for un-aggregated fields: [datasource].[field]
SIMPLE_FIELD_RE = re.compile(
    r'\[([^\]]+)\]\.\[([^\]]+)\]'
)

# Map aggregation abbreviations
_AGG_MAP = {
    "sum": AggregationType.SUM,
    "avg": AggregationType.AVG,
    "cnt": AggregationType.COUNT,
    "ctd": AggregationType.COUNTD,
    "min": AggregationType.MIN,
    "max": AggregationType.MAX,
    "attr": AggregationType.ATTR,
    "med": AggregationType.MEDIAN,
    "none": AggregationType.NONE,
    "yr": AggregationType.YEAR,
    "qr": AggregationType.QUARTER,
    "mn": AggregationType.MONTH,
    "dy": AggregationType.DAY,
    "hr": AggregationType.HOUR,
    "mi": AggregationType.MINUTE,
    "sc": AggregationType.SECOND,
    "wk": AggregationType.WEEK,
    "tyr": AggregationType.TRUNCYEAR,
    "tqr": AggregationType.TRUNCQUARTER,
    "tmn": AggregationType.TRUNCMONTH,
    "tdy": AggregationType.TRUNCDAY,
    "user": AggregationType.USER,
}

_KIND_MAP = {
    "nk": FieldKind.NOMINAL,
    "ok": FieldKind.ORDINAL,
    "qk": FieldKind.QUANTITATIVE,
}


def parse_worksheets(root: etree._Element) -> list[Worksheet]:
    """Parse all worksheets from the workbook XML.

    Args:
        root: Root element of the Tableau workbook XML.

    Returns:
        List of Worksheet objects.
    """
    worksheets = []

    for ws_elem in root.findall(".//worksheets/worksheet"):
        name = ws_elem.get("name", "")
        if not name:
            continue

        logger.info(f"Parsing worksheet: {name}")

        try:
            ws = Worksheet(name=name, title=name)

            # Get the primary datasource used
            ds_deps = ws_elem.findall(".//table/view/datasource-dependencies")
            if ds_deps:
                ws.datasource_name = ds_deps[0].get("datasource", "")

            # Parse mark type
            ws.mark_type = _parse_mark_type(ws_elem)

            # Parse rows and columns shelves
            ws.rows = _parse_shelf(ws_elem, "rows")
            ws.cols = _parse_shelf(ws_elem, "cols")

            # Parse encodings
            ws.color = _parse_encoding(ws_elem, "color")
            ws.size = _parse_encoding(ws_elem, "size")
            ws.label = _parse_encoding(ws_elem, "label")
            ws.text = _parse_encoding(ws_elem, "text")
            ws.tooltip = _parse_encoding(ws_elem, "tooltip")
            ws.detail = _parse_encoding(ws_elem, "detail")

            # Parse filters
            ws.filters = _parse_filters(ws_elem)

            # Handle Tableau's Measure Values and Measure Names pseudo-fields
            _handle_measure_values_names(ws, ws_elem)

            # Resolve automatic mark type
            ws.resolved_mark = _resolve_mark_type(ws)

            worksheets.append(ws)

        except Exception as e:
            logger.error(f"Error parsing worksheet '{name}': {e}")
            worksheets.append(Worksheet(name=name, title=name))

    return worksheets


def _handle_measure_values_names(ws: Worksheet, ws_elem: etree._Element):
    """Handle Tableau's Measure Values and Measure Names pseudo-fields."""
    has_multiple_values_rows = any(f.field_name in ("Multiple Values", "Measure Values") for f in ws.rows)
    has_multiple_values_cols = any(f.field_name in ("Multiple Values", "Measure Values") for f in ws.cols)

    if has_multiple_values_rows or has_multiple_values_cols:
        # Extract the member measures from groupfilter or column-instance
        measure_fields = []
        for gf in ws_elem.findall(".//filter//groupfilter[@member]"):
            member_val = gf.get("member", "").strip("\"'")
            parsed = parse_shelf_tokens(member_val)
            if parsed:
                measure_fields.extend(parsed)

        # Fallback to quantitative column-instances if no filter members found
        if not measure_fields:
            for ci in ws_elem.findall(".//datasource-dependencies/column-instance"):
                ci_type = ci.get("type", "")
                if ci_type == "quantitative":
                    derivation = ci.get("derivation", "none").lower()
                    col_name = ci.get("column", "").strip("[]")
                    sf = ShelfField(
                        datasource=ws.datasource_name,
                        aggregation=_AGG_MAP.get(derivation, AggregationType.SUM),
                        field_name=col_name,
                        kind=FieldKind.QUANTITATIVE,
                        raw_token=ci.get("name", ""),
                    )
                    measure_fields.append(sf)

        if measure_fields:
            if has_multiple_values_rows:
                new_rows = []
                for f in ws.rows:
                    if f.field_name in ("Multiple Values", "Measure Values"):
                        new_rows.extend(measure_fields)
                    else:
                        new_rows.append(f)
                ws.rows = new_rows

            if has_multiple_values_cols:
                new_cols = []
                for f in ws.cols:
                    if f.field_name in ("Multiple Values", "Measure Values"):
                        new_cols.extend(measure_fields)
                    else:
                        new_cols.append(f)
                ws.cols = new_cols

    # Remove [:Measure Names] and [Measure Names] pseudo-dimension from shelves, encodings & filters
    def _is_measure_name_field(f: ShelfField) -> bool:
        name = f.field_name or ""
        token = f.raw_token or ""
        return (
            ":Measure Names" in name
            or "Measure Names" in name
            or ":Measure Names" in token
            or "Measure Names" in token
        )

    def _is_measure_name_filter(f: FilterInfo) -> bool:
        col = f.column_name or ""
        return ":Measure Names" in col or "Measure Names" in col

    ws.rows = [f for f in ws.rows if not _is_measure_name_field(f)]
    ws.cols = [f for f in ws.cols if not _is_measure_name_field(f)]
    ws.color = [f for f in ws.color if not _is_measure_name_field(f)]
    ws.size = [f for f in ws.size if not _is_measure_name_field(f)]
    ws.label = [f for f in ws.label if not _is_measure_name_field(f)]
    ws.text = [f for f in ws.text if not _is_measure_name_field(f)]
    ws.tooltip = [f for f in ws.tooltip if not _is_measure_name_field(f)]
    ws.detail = [f for f in ws.detail if not _is_measure_name_field(f)]
    ws.filters = [f for f in ws.filters if not _is_measure_name_filter(f)]


def parse_shelf_tokens(shelf_text: str) -> list[ShelfField]:
    """Parse the text content of a rows or cols element into ShelfFields.

    Tableau shelf text looks like:
    [federated.abc].[sum:Sales:qk] [federated.abc].[none:Region:nk]

    Args:
        shelf_text: Raw text from <rows> or <cols> element.

    Returns:
        List of ShelfField objects.
    """
    fields = []

    # Try aggregated pattern first
    for match in SHELF_TOKEN_RE.finditer(shelf_text):
        datasource = match.group(1)
        agg_str = match.group(2)
        field_name = match.group(3)
        kind_str = match.group(4)

        sf = ShelfField(
            datasource=datasource,
            aggregation=_AGG_MAP.get(agg_str, AggregationType.NONE),
            field_name=field_name,
            kind=_KIND_MAP.get(kind_str, FieldKind.NOMINAL),
            raw_token=match.group(0),
        )
        fields.append(sf)

    # If no aggregated matches, try simple pattern
    if not fields:
        for match in SIMPLE_FIELD_RE.finditer(shelf_text):
            datasource = match.group(1)
            field_name = match.group(2)

            sf = ShelfField(
                datasource=datasource,
                aggregation=AggregationType.NONE,
                field_name=field_name,
                kind=FieldKind.NOMINAL,
                raw_token=match.group(0),
            )
            fields.append(sf)

    return fields


def _parse_shelf(ws_elem: etree._Element, shelf_name: str) -> list[ShelfField]:
    """Parse a shelf (rows/cols) from a worksheet element."""
    shelf_elem = ws_elem.find(f".//table/{shelf_name}")
    if shelf_elem is None:
        shelf_elem = ws_elem.find(f".//{shelf_name}")

    if shelf_elem is None or not shelf_elem.text:
        return []

    return parse_shelf_tokens(shelf_elem.text)


def _parse_mark_type(ws_elem: etree._Element) -> MarkType:
    """Extract the mark type from a worksheet element."""
    # Look for mark class in panes
    for mark_elem in ws_elem.findall(".//pane/mark"):
        mark_class = mark_elem.get("class", "")
        if mark_class:
            try:
                return MarkType(mark_class)
            except ValueError:
                logger.warning(f"Unknown mark type: {mark_class}")

    # Also check at the panes level
    for mark_elem in ws_elem.findall(".//panes/pane/mark"):
        mark_class = mark_elem.get("class", "")
        if mark_class:
            try:
                return MarkType(mark_class)
            except ValueError:
                pass

    # Check the style element
    for mark_elem in ws_elem.findall(".//mark"):
        mark_class = mark_elem.get("class", "")
        if mark_class:
            try:
                return MarkType(mark_class)
            except ValueError:
                pass

    return MarkType.AUTOMATIC


def _parse_encoding(ws_elem: etree._Element, encoding_name: str) -> list[ShelfField]:
    """Parse an encoding (color, size, label, etc.) from a worksheet."""
    fields = []

    for enc_elem in ws_elem.findall(f".//pane/encodings/{encoding_name}"):
        column = enc_elem.get("column", "")
        if column:
            # Parse the column reference
            match = SHELF_TOKEN_RE.match(column)
            if match:
                sf = ShelfField(
                    datasource=match.group(1),
                    aggregation=_AGG_MAP.get(match.group(2), AggregationType.NONE),
                    field_name=match.group(3),
                    kind=_KIND_MAP.get(match.group(4), FieldKind.NOMINAL),
                    raw_token=column,
                )
                fields.append(sf)
            else:
                # Simple field reference
                simple_match = SIMPLE_FIELD_RE.match(column)
                if simple_match:
                    sf = ShelfField(
                        datasource=simple_match.group(1),
                        field_name=simple_match.group(2),
                        raw_token=column,
                    )
                    fields.append(sf)
                else:
                    # Bare field name
                    sf = ShelfField(
                        field_name=column.strip("[]"),
                        raw_token=column,
                    )
                    fields.append(sf)

    return fields


def _parse_filters(ws_elem: etree._Element) -> list[FilterInfo]:
    """Parse worksheet filters."""
    filters = []

    for filter_elem in ws_elem.findall(".//filter"):
        column = filter_elem.get("column", "")
        filter_class = filter_elem.get("class", "categorical")

        if not column:
            continue

        fi = FilterInfo(
            column_name=column,
            filter_type=(FilterType.QUANTITATIVE if filter_class == "quantitative"
                        else FilterType.CATEGORICAL),
        )

        # Parse datasource from column reference
        ds_match = re.match(r'\[([^\]]+)\]\.', column)
        if ds_match:
            fi.datasource = ds_match.group(1)

        # Parse filter members (categorical filters)
        for gf in filter_elem.findall(".//groupfilter"):
            member = gf.get("member", "")
            if member:
                fi.members.append(member.strip('"'))

            # Also check for function-based group filters
            func = gf.get("function", "")
            if func == "member":
                member_val = gf.get("member", "")
                if member_val and member_val not in fi.members:
                    fi.members.append(member_val.strip('"'))

            # Parse sub-members
            for sub_gf in gf.findall("groupfilter"):
                sub_member = sub_gf.get("member", "")
                if sub_member and sub_member not in fi.members:
                    fi.members.append(sub_member.strip('"'))

        # Parse quantitative filter range
        if fi.filter_type == FilterType.QUANTITATIVE:
            for range_elem in filter_elem.findall(".//range"):
                min_val = range_elem.get("min")
                max_val = range_elem.get("max")
                if min_val:
                    try:
                        fi.min_value = float(min_val)
                    except ValueError:
                        pass
                if max_val:
                    try:
                        fi.max_value = float(max_val)
                    except ValueError:
                        pass

        filters.append(fi)

    return filters


def _resolve_mark_type(ws: Worksheet) -> MarkType:
    """Resolve Automatic mark type based on shelf contents.

    Rules:
    - If date on columns with a measure on rows -> Line
    - If only measures (no dimensions) -> Text/Card
    - Otherwise -> Bar
    """
    if ws.mark_type != MarkType.AUTOMATIC:
        return ws.mark_type

    has_date_on_cols = any(f.is_date_part or f.is_date_trunc for f in ws.cols)
    has_measure_on_rows = any(f.is_measure for f in ws.rows)
    has_measure_on_cols = any(f.is_measure for f in ws.cols)
    has_dimension_on_rows = any(not f.is_measure for f in ws.rows)
    has_dimension_on_cols = any(not f.is_measure for f in ws.cols)

    if has_date_on_cols and has_measure_on_rows:
        return MarkType.LINE
    elif has_date_on_cols and has_measure_on_cols:
        return MarkType.LINE
    elif not has_dimension_on_rows and not has_dimension_on_cols:
        return MarkType.TEXT
    else:
        return MarkType.BAR
