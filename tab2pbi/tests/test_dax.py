"""Tests for the Tableau-to-DAX conversion engine."""

import pytest
from tab2pbi.converters.dax import (
    convert_formula,
    Tokenizer,
    Parser,
    TokenType,
)


def test_tokenizer_simple():
    tokens = Tokenizer("SUM([Sales]) + 10").tokenize()
    types = [t.type for t in tokens if t.type != TokenType.EOF]
    assert types == [
        TokenType.IDENT,      # SUM
        TokenType.LPAREN,     # (
        TokenType.FIELD_REF,  # [Sales]
        TokenType.RPAREN,     # )
        TokenType.PLUS,       # +
        TokenType.NUMBER,     # 10
    ]


def test_basic_arithmetic():
    dax, calc_type, status = convert_formula("[Sales] * 1.1 + [Tax]", "Orders")
    assert status == "converted"
    assert "Orders[Sales] * 1.1 + Orders[Tax]" in dax


def test_basic_aggregations():
    cases = [
        ("SUM([Sales])", "SUM(Orders[Sales])"),
        ("AVG([Profit])", "AVERAGE(Orders[Profit])"),
        ("COUNT([Order ID])", "COUNT(Orders[Order ID])"),
        ("COUNTD([Customer ID])", "DISTINCTCOUNT(Orders[Customer ID])"),
        ("MIN([Order Date])", "MIN(Orders[Order Date])"),
        ("MAX([Order Date])", "MAX(Orders[Order Date])"),
        ("MEDIAN([Quantity])", "MEDIAN(Orders[Quantity])"),
    ]
    for tableau, expected in cases:
        dax, calc_type, status = convert_formula(tableau, "Orders")
        assert status == "converted"
        assert dax == expected, f"Failed for {tableau}: got {dax}"


def test_null_handling():
    dax_zn, _, status_zn = convert_formula("ZN([Profit])", "Orders")
    assert status_zn == "converted"
    assert "COALESCE" in dax_zn and "0" in dax_zn

    dax_ifnull, _, status_ifnull = convert_formula("IFNULL([Region], 'Unknown')", "Orders")
    assert status_ifnull == "converted"
    assert 'COALESCE(Orders[Region], "Unknown")' == dax_ifnull

    dax_isnull, _, status_isnull = convert_formula("ISNULL([Postal Code])", "Orders")
    assert status_isnull == "converted"
    assert "ISBLANK(Orders[Postal Code])" == dax_isnull


def test_if_then_else():
    tableau = "IF [Sales] > 1000 THEN 'High' ELSE 'Low' END"
    dax, _, status = convert_formula(tableau, "Orders")
    assert status == "converted"
    assert 'IF(Orders[Sales] > 1000, "High", "Low")' == dax


def test_if_elseif_else():
    tableau = "IF [Profit] > 500 THEN 'A' ELSEIF [Profit] > 100 THEN 'B' ELSE 'C' END"
    dax, _, status = convert_formula(tableau, "Orders")
    assert status == "converted"
    assert 'IF(Orders[Profit] > 500, "A", IF(Orders[Profit] > 100, "B", "C"))' == dax


def test_case_when():
    tableau = "CASE [Segment] WHEN 'Consumer' THEN 1 WHEN 'Corporate' THEN 2 ELSE 3 END"
    dax, _, status = convert_formula(tableau, "Orders")
    assert status == "converted"
    assert 'SWITCH(Orders[Segment], "Consumer", 1, "Corporate", 2, 3)' == dax


def test_lod_fixed_single_dimension():
    tableau = "{FIXED [Region] : SUM([Sales])}"
    dax, _, status = convert_formula(tableau, "Orders")
    assert status == "converted"
    assert "CALCULATE(SUM(Orders[Sales]), ALLEXCEPT(Orders, Orders[Region]))" == dax


def test_lod_fixed_multiple_dimensions():
    tableau = "{FIXED [Region], [Category] : AVG([Profit])}"
    dax, _, status = convert_formula(tableau, "Orders")
    assert status == "converted"
    assert "CALCULATE(AVERAGE(Orders[Profit]), ALLEXCEPT(Orders, Orders[Region], Orders[Category]))" == dax


def test_lod_fixed_table_scoped():
    tableau = "{FIXED : SUM([Sales])}"
    dax, _, status = convert_formula(tableau, "Orders")
    assert status == "converted"
    assert "CALCULATE(SUM(Orders[Sales]), ALL(Orders))" == dax


def test_string_functions():
    dax_upper, _, _ = convert_formula("UPPER([Category])", "Orders")
    assert dax_upper == "UPPER(Orders[Category])"

    dax_lower, _, _ = convert_formula("LOWER([Category])", "Orders")
    assert dax_lower == "LOWER(Orders[Category])"

    dax_len, _, _ = convert_formula("LEN([Category])", "Orders")
    assert dax_len == "LEN(Orders[Category])"


def test_date_functions():
    dax_datediff, _, status_datediff = convert_formula("DATEDIFF('day', [Order Date], [Ship Date])", "Orders")
    assert status_datediff == "converted"
    assert "DATEDIFF(Orders[Order Date], Orders[Ship Date], DAY)" == dax_datediff

    dax_dateadd, _, status_dateadd = convert_formula("DATEADD('month', 1, [Order Date])", "Orders")
    assert status_dateadd == "converted"
    assert "EDATE(Orders[Order Date], 1)" == dax_dateadd


def test_unsupported_syntax_graceful_fallback():
    # Malformed syntax or unparseable expressions fallback to BLANK()
    tableau = "{UNKNOWN_DIRECTIVE [X] : SUM([Y])}"
    dax, calc_type, status = convert_formula(tableau, "Orders")
    assert status == "unsupported"
    assert dax == "BLANK()"
