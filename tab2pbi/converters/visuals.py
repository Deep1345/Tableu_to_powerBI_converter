"""Map Tableau mark types and shelf fields to Power BI visual types.

Determines the Power BI visualType and field projections based on
the mark type and placement of fields on rows/cols/encodings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from tab2pbi.models import (
    AggregationType, FieldKind, MarkType, ShelfField, Worksheet,
)

logger = logging.getLogger(__name__)


@dataclass
class FieldProjection:
    """A field placed in a Power BI visual role."""
    table: str = ""
    column: str = ""
    role: str = ""           # Category, Y, X, Series, Values, Rows, Columns, Details
    aggregation: str = ""    # Sum, Average, Count, DistinctCount, Min, Max, None
    is_measure: bool = False
    query_ref: str = ""      # "Table.Column"
    native_query_ref: str = ""  # "Column"


@dataclass
class VisualMapping:
    """The result of mapping a Tableau worksheet to a Power BI visual."""
    visual_type: str = ""
    projections: dict[str, list[FieldProjection]] = field(default_factory=dict)
    title: str = ""
    status: str = "converted"
    warnings: list[str] = field(default_factory=list)


# Map Tableau aggregation types to Power BI aggregation function names
_PBI_AGG_MAP = {
    AggregationType.SUM: "Sum",
    AggregationType.AVG: "Average",
    AggregationType.COUNT: "Count",
    AggregationType.COUNTD: "DistinctCount",
    AggregationType.MIN: "Min",
    AggregationType.MAX: "Max",
    AggregationType.ATTR: "None",
    AggregationType.MEDIAN: "None",
    AggregationType.NONE: "None",
}


def map_visual(worksheet: Worksheet, table_name: str = "Table") -> VisualMapping:
    """Map a Tableau worksheet to a Power BI visual type and field projections.

    Args:
        worksheet: The parsed Tableau worksheet.
        table_name: Name of the Power BI table.

    Returns:
        VisualMapping with visual type and projections.
    """
    vm = VisualMapping(title=worksheet.title or worksheet.name)

    mark = worksheet.resolved_mark

    # Classify shelf contents
    row_dims = [f for f in worksheet.rows if not f.is_measure]
    row_measures = [f for f in worksheet.rows if f.is_measure]
    col_dims = [f for f in worksheet.cols if not f.is_measure]
    col_measures = [f for f in worksheet.cols if f.is_measure]

    color_dims = [f for f in worksheet.color if not f.is_measure]
    color_measures = [f for f in worksheet.color if f.is_measure]

    try:
        if mark == MarkType.PIE:
            vm = _map_pie(worksheet, table_name)
        elif mark in (MarkType.CIRCLE, MarkType.SHAPE):
            if row_measures and col_measures:
                vm = _map_scatter(worksheet, table_name)
            else:
                vm = _map_bar(worksheet, table_name)
        elif mark == MarkType.LINE:
            vm = _map_line(worksheet, table_name)
        elif mark == MarkType.AREA:
            vm = _map_area(worksheet, table_name)
        elif mark == MarkType.TEXT:
            vm = _map_text(worksheet, table_name)
        elif mark == MarkType.SQUARE:
            if color_measures:
                vm = _map_matrix(worksheet, table_name)
            else:
                vm = _map_bar(worksheet, table_name)
        elif mark in (MarkType.BAR, MarkType.AUTOMATIC):
            vm = _map_bar(worksheet, table_name)
        elif mark == MarkType.MAP:
            vm.visual_type = "map"
            vm.status = "unsupported"
            vm.warnings.append("Map visuals are not supported")
        else:
            vm = _map_bar(worksheet, table_name)
            vm.warnings.append(f"Unknown mark type '{mark.value}', defaulting to bar")

    except Exception as e:
        logger.error(f"Error mapping visual for '{worksheet.name}': {e}")
        vm.visual_type = "clusteredColumnChart"
        vm.status = "partial"
        vm.warnings.append(f"Error during visual mapping: {e}")

    vm.title = worksheet.title or worksheet.name
    return vm


def _map_bar(ws: Worksheet, table: str) -> VisualMapping:
    """Map bar/column marks to bar or column chart."""
    vm = VisualMapping()

    is_mn = lambda f: ":Measure Names" in (f.field_name or "") or "Measure Names" in (f.field_name or "") or ":Measure Names" in (f.raw_token or "") or "Measure Names" in (f.raw_token or "")
    row_dims = [f for f in ws.rows if not f.is_measure and not is_mn(f)]
    row_measures = [f for f in ws.rows if f.is_measure]
    col_dims = [f for f in ws.cols if not f.is_measure and not is_mn(f)]
    col_measures = [f for f in ws.cols if f.is_measure]
    color_dims = [f for f in ws.color if not f.is_measure and not is_mn(f)]

    # Determine bar vs column orientation
    if row_dims and col_measures:
        # Dimensions on rows, measures on cols -> horizontal bar
        if color_dims:
            vm.visual_type = "stackedBarChart"
        else:
            vm.visual_type = "clusteredBarChart"

        vm.projections["Category"] = [_make_proj(f, table) for f in row_dims]
        vm.projections["Y"] = [_make_proj(f, table, is_measure=True) for f in col_measures]
        if color_dims:
            vm.projections["Series"] = [_make_proj(f, table) for f in color_dims]

    elif col_dims and row_measures:
        # Dimensions on cols, measures on rows -> vertical column chart
        if color_dims:
            vm.visual_type = "stackedColumnChart"
        else:
            vm.visual_type = "clusteredColumnChart"

        vm.projections["Category"] = [_make_proj(f, table) for f in col_dims]
        vm.projections["Y"] = [_make_proj(f, table, is_measure=True) for f in row_measures]
        if color_dims:
            vm.projections["Series"] = [_make_proj(f, table) for f in color_dims]

    else:
        # Default: try to figure out what goes where
        vm.visual_type = "clusteredColumnChart"
        all_dims = col_dims + row_dims
        all_measures = col_measures + row_measures
        if all_dims:
            vm.projections["Category"] = [_make_proj(f, table) for f in all_dims]
        if all_measures:
            vm.projections["Y"] = [_make_proj(f, table, is_measure=True) for f in all_measures]

    return vm


def _map_line(ws: Worksheet, table: str) -> VisualMapping:
    """Map line marks to line chart."""
    vm = VisualMapping(visual_type="lineChart")

    col_dims = [f for f in ws.cols if not f.is_measure]
    row_measures = [f for f in ws.rows if f.is_measure]
    color_dims = [f for f in ws.color if not f.is_measure]

    # Category is usually on columns (often a date)
    all_dims = col_dims + [f for f in ws.rows if not f.is_measure]
    if all_dims:
        vm.projections["Category"] = [_make_proj(f, table) for f in all_dims[:1]]

    # Measures on rows (Y-axis)
    all_measures = row_measures + [f for f in ws.cols if f.is_measure]
    if all_measures:
        vm.projections["Y"] = [_make_proj(f, table, is_measure=True) for f in all_measures]

    # Color dimension as series
    if color_dims:
        vm.projections["Series"] = [_make_proj(f, table) for f in color_dims]

    return vm


def _map_area(ws: Worksheet, table: str) -> VisualMapping:
    """Map area marks to area chart."""
    vm = _map_line(ws, table)
    vm.visual_type = "areaChart"
    return vm


def _map_pie(ws: Worksheet, table: str) -> VisualMapping:
    """Map pie marks to pie chart."""
    vm = VisualMapping(visual_type="pieChart")

    # Category = color dimension (slices)
    color_dims = [f for f in ws.color if not f.is_measure]
    if color_dims:
        vm.projections["Category"] = [_make_proj(f, table) for f in color_dims]
    else:
        # Fallback: use any dimension
        all_dims = [f for f in ws.rows + ws.cols if not f.is_measure]
        if all_dims:
            vm.projections["Category"] = [_make_proj(f, table) for f in all_dims[:1]]

    # Y = size/wedge measure
    size_measures = [f for f in ws.size if f.is_measure]
    if size_measures:
        vm.projections["Y"] = [_make_proj(f, table, is_measure=True) for f in size_measures]
    else:
        all_measures = [f for f in ws.rows + ws.cols if f.is_measure]
        if all_measures:
            vm.projections["Y"] = [_make_proj(f, table, is_measure=True) for f in all_measures[:1]]

    return vm


def _map_scatter(ws: Worksheet, table: str) -> VisualMapping:
    """Map circle/shape marks to scatter chart."""
    vm = VisualMapping(visual_type="scatterChart")

    row_measures = [f for f in ws.rows if f.is_measure]
    col_measures = [f for f in ws.cols if f.is_measure]
    all_dims = [f for f in ws.rows + ws.cols if not f.is_measure]

    if col_measures:
        vm.projections["X"] = [_make_proj(f, table, is_measure=True) for f in col_measures[:1]]
    if row_measures:
        vm.projections["Y"] = [_make_proj(f, table, is_measure=True) for f in row_measures[:1]]
    if all_dims:
        vm.projections["Details"] = [_make_proj(f, table) for f in all_dims]

    return vm


def _map_text(ws: Worksheet, table: str) -> VisualMapping:
    """Map text marks to card, multiRowCard, table, or matrix."""
    vm = VisualMapping()

    all_dims = [f for f in ws.rows + ws.cols if not f.is_measure]
    all_measures = [f for f in ws.rows + ws.cols if f.is_measure]
    text_fields = ws.text or ws.label

    row_dims = [f for f in ws.rows if not f.is_measure]
    col_dims = [f for f in ws.cols if not f.is_measure]

    if not all_dims and all_measures:
        # Only measures -> card
        if len(all_measures) == 1:
            vm.visual_type = "card"
            vm.projections["Values"] = [
                _make_proj(f, table, is_measure=True) for f in all_measures
            ]
        else:
            vm.visual_type = "multiRowCard"
            vm.projections["Values"] = [
                _make_proj(f, table, is_measure=True) for f in all_measures
            ]
    elif row_dims and col_dims:
        # Dimensions on both rows and cols -> matrix/pivot table
        vm.visual_type = "pivotTable"
        vm.projections["Rows"] = [_make_proj(f, table) for f in row_dims]
        vm.projections["Columns"] = [_make_proj(f, table) for f in col_dims]
        if all_measures:
            vm.projections["Values"] = [
                _make_proj(f, table, is_measure=True) for f in all_measures
            ]
    else:
        # Dimensions with or without measures -> table
        vm.visual_type = "tableEx"
        values = []
        for f in all_dims:
            values.append(_make_proj(f, table))
        for f in all_measures:
            values.append(_make_proj(f, table, is_measure=True))
        vm.projections["Values"] = values

    return vm


def _map_matrix(ws: Worksheet, table: str) -> VisualMapping:
    """Map square marks with color measure to matrix."""
    vm = VisualMapping(visual_type="pivotTable")

    row_dims = [f for f in ws.rows if not f.is_measure]
    col_dims = [f for f in ws.cols if not f.is_measure]
    all_measures = [f for f in ws.rows + ws.cols if f.is_measure]
    color_measures = [f for f in ws.color if f.is_measure]

    if row_dims:
        vm.projections["Rows"] = [_make_proj(f, table) for f in row_dims]
    if col_dims:
        vm.projections["Columns"] = [_make_proj(f, table) for f in col_dims]

    values = all_measures + color_measures
    if values:
        vm.projections["Values"] = [
            _make_proj(f, table, is_measure=True) for f in values
        ]

    return vm


def _make_proj(
    shelf_field: ShelfField,
    table: str,
    is_measure: bool = False,
) -> FieldProjection:
    """Create a FieldProjection from a ShelfField."""
    # Determine aggregation
    agg = _PBI_AGG_MAP.get(shelf_field.aggregation, "None")
    if is_measure and agg == "None" and shelf_field.aggregation == AggregationType.NONE:
        agg = "Sum"  # Default aggregation for measures

    field_name = shelf_field.field_name
    if "].[" in field_name:
        field_name = field_name.split("].[")[-1].rstrip("]")
    field_name = field_name.strip("[]")
    if field_name.startswith(":"):
        field_name = field_name[1:]

    return FieldProjection(
        table=table,
        column=field_name,
        role="",  # Set by the caller via dict key
        aggregation=agg,
        is_measure=is_measure or shelf_field.is_measure,
        query_ref=f"{table}.{field_name}",
        native_query_ref=field_name,
    )

