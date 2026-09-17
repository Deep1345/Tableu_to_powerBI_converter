"""Parse Tableau dashboard XML.

Extracts dashboard size and zone positions from
/workbook/dashboards/dashboard elements.
"""

from __future__ import annotations

import logging
from typing import Optional

from lxml import etree

from tab2pbi.models import Dashboard, DashboardZone

logger = logging.getLogger(__name__)


def parse_dashboards(root: etree._Element) -> list[Dashboard]:
    """Parse all dashboards from the workbook XML.

    Args:
        root: Root element of the Tableau workbook XML.

    Returns:
        List of Dashboard objects.
    """
    dashboards = []

    for db_elem in root.findall(".//dashboards/dashboard"):
        name = db_elem.get("name", "")
        if not name:
            continue

        logger.info(f"Parsing dashboard: {name}")

        try:
            db = Dashboard(name=name, title=name)

            # Parse size
            size_elem = db_elem.find("size")
            if size_elem is not None:
                w = size_elem.get("maxwidth", size_elem.get("width", "1000"))
                h = size_elem.get("maxheight", size_elem.get("height", "800"))
                try:
                    db.width = int(w)
                    db.height = int(h)
                except ValueError:
                    db.width = 1000
                    db.height = 800

            # Parse zones recursively
            zones_elem = db_elem.find("zones")
            if zones_elem is not None:
                db.zones = _parse_zones_recursive(zones_elem)
            else:
                # Try looking for zone elements directly
                for zone_elem in db_elem.findall(".//zone"):
                    zone = _parse_single_zone(zone_elem)
                    if zone:
                        db.zones.append(zone)

            logger.info(
                f"Dashboard '{name}': {db.width}x{db.height}, "
                f"{len(db.zones)} zones"
            )

            dashboards.append(db)

        except Exception as e:
            logger.error(f"Error parsing dashboard '{name}': {e}")
            dashboards.append(Dashboard(name=name))

    return dashboards


def _parse_zones_recursive(parent_elem: etree._Element) -> list[DashboardZone]:
    """Recursively parse zones from a parent element.

    Only keeps leaf zones that reference a worksheet or contain text.
    """
    zones = []

    for zone_elem in parent_elem.findall("zone"):
        # Check if this is a leaf zone (has a worksheet reference)
        zone_name = zone_elem.get("name", "")
        zone_type = zone_elem.get("type-v2", zone_elem.get("type", ""))

        # Check for nested zones
        child_zones = zone_elem.findall("zone")

        if child_zones:
            # This is a container zone - recurse into children
            zones.extend(_parse_zones_recursive(zone_elem))
        else:
            # This is a leaf zone
            zone = _parse_single_zone(zone_elem)
            if zone:
                zones.append(zone)

    return zones


def _parse_single_zone(zone_elem: etree._Element) -> Optional[DashboardZone]:
    """Parse a single zone element into a DashboardZone.

    Args:
        zone_elem: A <zone> XML element.

    Returns:
        DashboardZone if the zone is relevant, None otherwise.
    """
    zone_name = zone_elem.get("name", "")
    zone_type_v2 = zone_elem.get("type-v2", "")
    zone_type = zone_elem.get("type", "")
    zone_id = zone_elem.get("id", "")

    # Determine zone type
    if zone_type_v2 == "text" or zone_type == "text":
        zone_category = "text"
    elif zone_type_v2 == "title" or zone_type == "title":
        zone_category = "title"
    elif zone_type_v2 == "blank" or zone_type == "blank":
        zone_category = "blank"
    elif zone_name:
        zone_category = "worksheet"
    else:
        return None

    # Get position (0-100000 scale)
    x = _safe_int(zone_elem.get("x", "0"))
    y = _safe_int(zone_elem.get("y", "0"))
    w = _safe_int(zone_elem.get("w", "0"))
    h = _safe_int(zone_elem.get("h", "0"))

    # For zones with position attributes using 'maxwidth'/'maxheight'
    if w == 0:
        w = _safe_int(zone_elem.get("maxwidth", "0"))
    if h == 0:
        h = _safe_int(zone_elem.get("maxheight", "0"))

    zone = DashboardZone(
        zone_id=zone_id or zone_name,
        worksheet_name=zone_name if zone_category == "worksheet" else "",
        zone_type=zone_category,
        x=x,
        y=y,
        w=w,
        h=h,
    )

    # Extract text content for text zones
    if zone_category == "text":
        text_elem = zone_elem.find(".//formatted-text/run")
        if text_elem is not None and text_elem.text:
            zone.text_content = text_elem.text

    return zone


def _safe_int(value: str) -> int:
    """Safely convert a string to int, returning 0 on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0
