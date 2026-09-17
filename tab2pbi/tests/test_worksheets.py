"""Tests for worksheet shelf parsing and visual type mapping."""

import pytest
from tab2pbi.models import AggregationType, FieldKind, MarkType, ShelfField, Worksheet
from tab2pbi.parser.worksheets import parse_shelf_tokens, _resolve_mark_type
from tab2pbi.converters.visuals import map_visual


def test_parse_shelf_tokens_aggregated():
    shelf_text = "[federated.123].[sum:Sales:qk] [federated.123].[none:Region:nk]"
    fields = parse_shelf_tokens(shelf_text)
    assert len(fields) == 2

    assert fields[0].field_name == "Sales"
    assert fields[0].aggregation == AggregationType.SUM
    assert fields[0].kind == FieldKind.QUANTITATIVE

    assert fields[1].field_name == "Region"
    assert fields[1].aggregation == AggregationType.NONE
    assert fields[1].kind == FieldKind.NOMINAL


def test_parse_shelf_tokens_simple():
    shelf_text = "[federated.123].[Category]"
    fields = parse_shelf_tokens(shelf_text)
    assert len(fields) == 1
    assert fields[0].field_name == "Category"
    assert fields[0].aggregation == AggregationType.NONE


def test_resolve_mark_type_automatic_line():
    ws = Worksheet(
        name="Trend",
        mark_type=MarkType.AUTOMATIC,
        cols=[ShelfField(field_name="Order Date", aggregation=AggregationType.YEAR, kind=FieldKind.ORDINAL)],
        rows=[ShelfField(field_name="Sales", aggregation=AggregationType.SUM, kind=FieldKind.QUANTITATIVE)],
    )
    resolved = _resolve_mark_type(ws)
    assert resolved == MarkType.LINE


def test_resolve_mark_type_automatic_bar():
    ws = Worksheet(
        name="Category Sales",
        mark_type=MarkType.AUTOMATIC,
        cols=[ShelfField(field_name="Category", aggregation=AggregationType.NONE, kind=FieldKind.NOMINAL)],
        rows=[ShelfField(field_name="Sales", aggregation=AggregationType.SUM, kind=FieldKind.QUANTITATIVE)],
    )
    resolved = _resolve_mark_type(ws)
    assert resolved == MarkType.BAR


def test_map_visual_bar():
    ws = Worksheet(
        name="Category Sales",
        resolved_mark=MarkType.BAR,
        cols=[ShelfField(field_name="Category", aggregation=AggregationType.NONE, kind=FieldKind.NOMINAL)],
        rows=[ShelfField(field_name="Sales", aggregation=AggregationType.SUM, kind=FieldKind.QUANTITATIVE)],
    )
    vm = map_visual(ws, "Orders")
    assert vm.visual_type in ("clusteredColumnChart", "clusteredBarChart")
    assert "Category" in vm.projections or "Y" in vm.projections


def test_map_visual_scatter():
    ws = Worksheet(
        name="Sales vs Profit",
        resolved_mark=MarkType.CIRCLE,
        cols=[ShelfField(field_name="Sales", aggregation=AggregationType.SUM, kind=FieldKind.QUANTITATIVE)],
        rows=[ShelfField(field_name="Profit", aggregation=AggregationType.SUM, kind=FieldKind.QUANTITATIVE)],
        detail=[ShelfField(field_name="Customer Name", aggregation=AggregationType.NONE, kind=FieldKind.NOMINAL)],
    )
    vm = map_visual(ws, "Orders")
    assert vm.visual_type == "scatterChart"
