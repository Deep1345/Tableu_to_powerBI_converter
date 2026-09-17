"""Convert Tableau dashboard zone coordinates to Power BI visual positions.

Tableau dashboards use a 0-100000 coordinate system.
Power BI pages use pixel coordinates (default 1280x720).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tab2pbi.models import Dashboard, DashboardZone

logger = logging.getLogger(__name__)

# Power BI default page dimensions
DEFAULT_PAGE_WIDTH = 1280
DEFAULT_PAGE_HEIGHT = 720

# Padding inside visuals (pixels)
INNER_PADDING = 4

# Tableau coordinate space
TABLEAU_COORD_MAX = 100000


@dataclass
class VisualPosition:
    """Position of a visual on a Power BI page."""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    z: int = 0
    tab_order: int = 0


def compute_page_size(dashboard: Dashboard) -> tuple[int, int]:
    """Compute the Power BI page size based on dashboard dimensions.

    Scales the dashboard's size proportionally while trying to
    maintain a 16:9 aspect ratio (or close to it).

    Args:
        dashboard: The Tableau dashboard.

    Returns:
        Tuple of (page_width, page_height) in pixels.
    """
    db_w = dashboard.width
    db_h = dashboard.height

    if db_w <= 0 or db_h <= 0:
        return DEFAULT_PAGE_WIDTH, DEFAULT_PAGE_HEIGHT

    aspect = db_w / db_h

    # Try to keep within reasonable Power BI page sizes
    if aspect >= 1.0:
        # Landscape
        page_w = DEFAULT_PAGE_WIDTH
        page_h = int(page_w / aspect)
        # Clamp height
        if page_h < 400:
            page_h = 400
        elif page_h > 1080:
            page_h = 1080
            page_w = int(page_h * aspect)
    else:
        # Portrait
        page_h = DEFAULT_PAGE_HEIGHT
        page_w = int(page_h * aspect)
        if page_w < 400:
            page_w = 400

    return page_w, page_h


def zone_to_position(
    zone: DashboardZone,
    page_width: int = DEFAULT_PAGE_WIDTH,
    page_height: int = DEFAULT_PAGE_HEIGHT,
    z_index: int = 0,
    tab_order: int = 0,
) -> VisualPosition:
    """Convert a Tableau dashboard zone to a Power BI visual position.

    Args:
        zone: The dashboard zone with coordinates in 0-100000 scale.
        page_width: Power BI page width in pixels.
        page_height: Power BI page height in pixels.
        z_index: Z-order for layering.
        tab_order: Tab order for accessibility.

    Returns:
        VisualPosition with pixel coordinates.
    """
    # Convert from 0-100000 scale to pixels
    x_px = int(zone.x / TABLEAU_COORD_MAX * page_width)
    y_px = int(zone.y / TABLEAU_COORD_MAX * page_height)
    w_px = int(zone.w / TABLEAU_COORD_MAX * page_width)
    h_px = int(zone.h / TABLEAU_COORD_MAX * page_height)

    # Add inner padding
    x_px = max(0, x_px + INNER_PADDING)
    y_px = max(0, y_px + INNER_PADDING)
    w_px = max(10, w_px - 2 * INNER_PADDING)
    h_px = max(10, h_px - 2 * INNER_PADDING)

    # Clamp inside page bounds
    if x_px + w_px > page_width:
        w_px = page_width - x_px
    if y_px + h_px > page_height:
        h_px = page_height - y_px

    return VisualPosition(
        x=x_px,
        y=y_px,
        width=w_px,
        height=h_px,
        z=z_index,
        tab_order=tab_order,
    )


def compute_full_page_position(
    page_width: int = DEFAULT_PAGE_WIDTH,
    page_height: int = DEFAULT_PAGE_HEIGHT,
) -> VisualPosition:
    """Create a position that fills the entire page.

    Used for worksheets that aren't placed on any dashboard.

    Args:
        page_width: Page width in pixels.
        page_height: Page height in pixels.

    Returns:
        VisualPosition covering the full page with margin.
    """
    margin = 20
    return VisualPosition(
        x=margin,
        y=margin,
        width=page_width - 2 * margin,
        height=page_height - 2 * margin,
        z=0,
        tab_order=0,
    )


def layout_dashboard(
    dashboard: Dashboard,
) -> tuple[int, int, list[tuple[DashboardZone, VisualPosition]]]:
    """Compute layout for all zones in a dashboard.

    Args:
        dashboard: The Tableau dashboard.

    Returns:
        Tuple of (page_width, page_height, [(zone, position), ...]).
    """
    page_w, page_h = compute_page_size(dashboard)

    worksheet_zones = [z for z in dashboard.zones if z.worksheet_name]

    results = []
    for i, zone in enumerate(worksheet_zones):
        pos = zone_to_position(
            zone,
            page_width=page_w,
            page_height=page_h,
            z_index=i,
            tab_order=i,
        )
        results.append((zone, pos))

    logger.info(
        f"Dashboard '{dashboard.name}': {page_w}x{page_h}, "
        f"{len(results)} worksheet visuals"
    )

    return page_w, page_h, results
