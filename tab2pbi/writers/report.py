"""Write Power BI Report (PBIR) files.

Generates the .Report/ folder structure with:
- definition.pbir
- definition/version.json
- definition/report.json
- definition/pages/pages.json
- definition/pages/<pageId>/page.json
- definition/pages/<pageId>/visuals/<visualId>/visual.json
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from tab2pbi.converters.layout import (
    DEFAULT_PAGE_HEIGHT, DEFAULT_PAGE_WIDTH,
    compute_full_page_position, layout_dashboard,
)
from tab2pbi.converters.visuals import FieldProjection, VisualMapping, map_visual
from tab2pbi.models import Dashboard, WorkbookModel, Worksheet

logger = logging.getLogger(__name__)


def write_report(
    model: WorkbookModel,
    output_dir: Path,
    table_name: str = "Table",
) -> Path:
    """Write the complete .Report folder.

    Args:
        model: The workbook intermediate model.
        output_dir: Base output directory.
        table_name: Name of the primary table.

    Returns:
        Path to the report directory.
    """
    name = model.name
    report_dir = output_dir / f"{name}.Report"
    def_dir = report_dir / "definition"
    pages_dir = def_dir / "pages"

    # Create directory structure
    report_dir.mkdir(parents=True, exist_ok=True)
    def_dir.mkdir(exist_ok=True)
    pages_dir.mkdir(exist_ok=True)

    # Write definition.pbir
    _write_pbir(report_dir, name)

    # Write version.json
    _write_version_json(def_dir)

    # Write report.json
    _write_report_json(def_dir)

    # Collect pages
    pages = []

    # Track which worksheets are placed on dashboards
    placed_worksheets = set()
    for db in model.dashboards:
        for zone in db.zones:
            if zone.worksheet_name:
                placed_worksheets.add(zone.worksheet_name)

    # Build column caption map for resolving shelf field names to TMDL column names
    column_map = {}
    for ds in model.datasources:
        for col in ds.columns.values():
            caption = col.caption or col.internal_name.strip("[]")
            clean_internal = col.internal_name.strip("[]")
            if caption:
                column_map[clean_internal] = caption
                column_map[caption] = caption

    # Create pages from dashboards
    for db in model.dashboards:
        page_id = _generate_id(f"page_{db.name}")
        page_info = _create_dashboard_page(
            db, model.worksheets, table_name, pages_dir, page_id, column_map
        )
        if page_info:
            pages.append(page_info)

    # Create pages for worksheets not on any dashboard
    for ws in model.worksheets:
        if ws.name not in placed_worksheets:
            page_id = _generate_id(f"page_{ws.name}")
            page_info = _create_worksheet_page(
                ws, table_name, pages_dir, page_id, column_map
            )
            if page_info:
                pages.append(page_info)

    # If no pages were created, create a default page
    if not pages:
        page_id = _generate_id("page_default")
        pages.append({
            "name": page_id,
            "displayName": name,
        })
        page_dir = pages_dir / page_id
        page_dir.mkdir(exist_ok=True)
        _write_page_json(page_dir, page_id, name)

    # Write pages.json
    _write_pages_json(pages_dir, pages)

    logger.info(f"Report written to {report_dir}")
    return report_dir


def _write_pbir(report_dir: Path, name: str):
    """Write definition.pbir file."""
    content = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {
            "byPath": {
                "path": f"../{name}.SemanticModel"
            }
        }
    }
    (report_dir / "definition.pbir").write_text(
        json.dumps(content, indent=2), encoding="utf-8"
    )


def _write_version_json(def_dir: Path):
    """Write version.json."""
    content = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "1.0.0"
    }
    (def_dir / "version.json").write_text(
        json.dumps(content, indent=2), encoding="utf-8"
    )


def _write_report_json(def_dir: Path):
    """Write report.json with theme configuration."""
    content = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.0.0/schema.json",
        "themeCollection": {
            "baseTheme": {
                "name": "CY24SU10",
                "reportVersionAtImport": "5.54",
                "type": "SharedResources"
            }
        }
    }
    (def_dir / "report.json").write_text(
        json.dumps(content, indent=2), encoding="utf-8"
    )


def _write_pages_json(pages_dir: Path, pages: list[dict]):
    """Write pages.json with page order."""
    content = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p["name"] for p in pages],
        "activePageName": pages[0]["name"] if pages else ""
    }
    (pages_dir / "pages.json").write_text(
        json.dumps(content, indent=2), encoding="utf-8"
    )


def _write_page_json(
    page_dir: Path,
    page_id: str,
    display_name: str,
    width: int = DEFAULT_PAGE_WIDTH,
    height: int = DEFAULT_PAGE_HEIGHT,
):
    """Write page.json for a single page."""
    content = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.0.0/schema.json",
        "name": page_id,
        "displayName": display_name,
        "displayOption": "FitToPage",
        "width": width,
        "height": height
    }
    (page_dir / "page.json").write_text(
        json.dumps(content, indent=2), encoding="utf-8"
    )


def _create_dashboard_page(
    dashboard: Dashboard,
    worksheets: list[Worksheet],
    table_name: str,
    pages_dir: Path,
    page_id: str,
    column_map: Optional[dict[str, str]] = None,
) -> Optional[dict]:
    """Create a page from a dashboard with positioned visuals."""
    page_dir = pages_dir / page_id
    page_dir.mkdir(exist_ok=True)
    visuals_dir = page_dir / "visuals"
    visuals_dir.mkdir(exist_ok=True)

    # Layout the dashboard
    page_w, page_h, zone_positions = layout_dashboard(dashboard)

    # Write page.json
    _write_page_json(
        page_dir, page_id,
        dashboard.title or dashboard.name,
        page_w, page_h,
    )

    # Create visuals for each positioned worksheet
    ws_map = {ws.name: ws for ws in worksheets}

    for zone, pos in zone_positions:
        ws = ws_map.get(zone.worksheet_name)
        if not ws:
            logger.warning(
                f"Worksheet '{zone.worksheet_name}' referenced in dashboard "
                f"but not found"
            )
            continue

        visual_id = _generate_id(f"visual_{ws.name}")
        visual_mapping = map_visual(ws, table_name)

        _write_visual_json(
            visuals_dir, visual_id, visual_mapping, pos, table_name, ws, column_map
        )

    return {
        "name": page_id,
        "displayName": dashboard.title or dashboard.name,
    }


def _create_worksheet_page(
    worksheet: Worksheet,
    table_name: str,
    pages_dir: Path,
    page_id: str,
    column_map: Optional[dict[str, str]] = None,
) -> Optional[dict]:
    """Create a page from a standalone worksheet."""
    page_dir = pages_dir / page_id
    page_dir.mkdir(exist_ok=True)
    visuals_dir = page_dir / "visuals"
    visuals_dir.mkdir(exist_ok=True)

    # Write page.json
    _write_page_json(
        page_dir, page_id,
        worksheet.title or worksheet.name,
    )

    # Create a full-page visual
    visual_id = _generate_id(f"visual_{worksheet.name}")
    visual_mapping = map_visual(worksheet, table_name)
    pos = compute_full_page_position()

    _write_visual_json(
        visuals_dir, visual_id, visual_mapping, pos, table_name, worksheet, column_map
    )

    return {
        "name": page_id,
        "displayName": worksheet.title or worksheet.name,
    }


def _write_visual_json(
    visuals_dir: Path,
    visual_id: str,
    mapping: VisualMapping,
    position,  # VisualPosition
    table_name: str,
    worksheet: Worksheet,
    column_map: Optional[dict[str, str]] = None,
):
    """Write a visual.json file for a single visual."""
    visual_dir = visuals_dir / visual_id
    visual_dir.mkdir(exist_ok=True)

    # Build query state projections
    query_state = {}
    for role_name, projections in mapping.projections.items():
        valid_projs = [
            p for p in projections
            if p.column and ":Measure Names" not in p.column and "Measure Names" not in p.column
        ]
        if valid_projs:
            query_state[role_name] = {
                "projections": [
                    _build_projection(p, table_name, column_map)
                    for p in valid_projs
                ]
            }

    # Build visual JSON
    visual_json = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json",
        "name": visual_id,
        "position": {
            "x": position.x,
            "y": position.y,
            "z": position.z,
            "width": position.width,
            "height": position.height,
            "tabOrder": position.tab_order,
        },
        "visual": {
            "visualType": mapping.visual_type,
            "query": {
                "queryState": query_state,
            },
            "visualContainerObjects": {
                "title": [{
                    "properties": {
                        "text": {
                            "expr": {
                                "Literal": {
                                    "Value": f"'{mapping.title}'"
                                }
                            }
                        },
                        "show": {
                            "expr": {
                                "Literal": {
                                    "Value": "true"
                                }
                            }
                        }
                    }
                }]
            }
        }
    }

    # Add filter config if worksheet has filters
    if worksheet.filters:
        filter_config = _build_filter_config(worksheet, table_name)
        if filter_config:
            visual_json["filterConfig"] = filter_config

    (visual_dir / "visual.json").write_text(
        json.dumps(visual_json, indent=2), encoding="utf-8"
    )


def _build_projection(
    proj: FieldProjection,
    table_name: str,
    column_map: Optional[dict[str, str]] = None,
) -> dict:
    """Build a Power BI projection JSON for a field."""
    table = proj.table or table_name
    prop_name = proj.column
    if column_map and prop_name in column_map:
        prop_name = column_map[prop_name]

    # Determine if this is a column or measure reference
    if proj.is_measure and proj.aggregation not in ("None", ""):
        field_spec = {
            "Aggregation": {
                "Expression": {
                    "Column": {
                        "Expression": {
                            "SourceRef": {
                                "Entity": table,
                            }
                        },
                        "Property": prop_name,
                    }
                },
                "Function": _agg_function_id(proj.aggregation),
            }
        }
    elif proj.is_measure:
        # Measure reference (no aggregation)
        field_spec = {
            "Measure": {
                "Expression": {
                    "SourceRef": {
                        "Entity": table,
                    }
                },
                "Property": prop_name,
            }
        }
    else:
        # Column reference
        field_spec = {
            "Column": {
                "Expression": {
                    "SourceRef": {
                        "Entity": table,
                    }
                },
                "Property": prop_name,
            }
        }

    return {
        "field": field_spec,
        "queryRef": f"{table}.{prop_name}",
        "nativeQueryRef": prop_name,
    }


def _agg_function_id(agg_name: str) -> int:
    """Map aggregation name to Power BI function ID."""
    mapping = {
        "Sum": 0,
        "Average": 1,
        "Count": 2,
        "Min": 3,
        "Max": 4,
        "DistinctCount": 5,
        "None": 6,
    }
    return mapping.get(agg_name, 0)


def _build_filter_config(
    worksheet: Worksheet,
    table_name: str,
) -> Optional[dict]:
    """Build filter configuration for a visual."""
    filters = []

    for fi in worksheet.filters:
        if not fi.members:
            continue

        # Ignore Measure Names pseudo-field filters
        if ":Measure Names" in fi.column_name or "Measure Names" in fi.column_name:
            continue

        # Extract field name from column reference
        field_name = fi.column_name
        if "].[" in field_name:
            # Extract the field part from [ds].[field]
            parts = field_name.split("].[")
            if len(parts) >= 2:
                field_name = parts[-1].rstrip("]")
        field_name = field_name.strip("[]")

        # Remove aggregation prefix if present
        if ":" in field_name:
            parts = field_name.split(":")
            if len(parts) >= 2:
                field_name = parts[1] if len(parts) == 3 else parts[0]
        field_name = field_name.strip("[]")

        if not field_name:
            continue

        filter_entry = {
            "type": "In",
            "expression": {
                "Column": {
                    "Expression": {
                        "SourceRef": {
                            "Entity": table_name,
                        }
                    },
                    "Property": field_name,
                }
            },
            "values": [
                [{"Literal": {"Value": f"'{m}'"}}]
                for m in fi.members
            ]
        }
        filters.append(filter_entry)

    if filters:
        return {"filters": filters}
    return None


def _generate_id(seed: str) -> str:
    """Generate a 20-character hex ID deterministically from a seed."""
    return hashlib.md5(seed.encode()).hexdigest()[:20]
