"""Tests for layout conversion and coordinate scaling."""

import pytest
from tab2pbi.models import Dashboard, DashboardZone
from tab2pbi.converters.layout import (
    compute_page_size,
    zone_to_position,
    layout_dashboard,
    compute_full_page_position,
    DEFAULT_PAGE_WIDTH,
    DEFAULT_PAGE_HEIGHT,
    INNER_PADDING,
)


def test_compute_page_size_default():
    db = Dashboard(name="Overview", width=0, height=0)
    w, h = compute_page_size(db)
    assert w == DEFAULT_PAGE_WIDTH
    assert h == DEFAULT_PAGE_HEIGHT


def test_compute_page_size_custom():
    db = Dashboard(name="Overview", width=1600, height=900)
    w, h = compute_page_size(db)
    assert w == DEFAULT_PAGE_WIDTH
    assert h == 720  # 16:9 preserved


def test_zone_to_position_padding():
    # Zone spanning the full 0-100000 range has inner padding applied
    zone = DashboardZone(zone_id="1", worksheet_name="Sheet1", x=0, y=0, w=100000, h=100000)
    pos = zone_to_position(zone, page_width=1280, page_height=720)
    assert pos.x == INNER_PADDING
    assert pos.y == INNER_PADDING
    assert pos.width == 1280 - 2 * INNER_PADDING
    assert pos.height == 720 - 2 * INNER_PADDING


def test_compute_full_page_position():
    pos = compute_full_page_position(1280, 720)
    assert pos.x == 20
    assert pos.y == 20
    assert pos.width == 1240
    assert pos.height == 680


def test_layout_dashboard():
    db = Dashboard(
        name="MainDashboard",
        width=1600,
        height=900,
        zones=[
            DashboardZone(zone_id="1", worksheet_name="Chart1", x=0, y=0, w=50000, h=50000),
            DashboardZone(zone_id="2", worksheet_name="Chart2", x=50000, y=0, w=50000, h=50000),
            DashboardZone(zone_id="3", worksheet_name="", x=0, y=50000, w=100000, h=50000),  # non-sheet container
        ],
    )
    pw, ph, items = layout_dashboard(db)
    assert pw == DEFAULT_PAGE_WIDTH
    assert ph == DEFAULT_PAGE_HEIGHT
    # Should only contain the 2 leaf visual zones
    assert len(items) == 2
    sheet_names = [zone.worksheet_name for zone, pos in items]
    assert "Chart1" in sheet_names
    assert "Chart2" in sheet_names
