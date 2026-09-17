"""Generate conversion reports.

Produces both JSON and Markdown reports summarizing what was
converted, what was unsupported, and any warnings.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from tab2pbi.converters.visuals import VisualMapping
from tab2pbi.data_export import DataExportResult
from tab2pbi.models import WorkbookModel

logger = logging.getLogger(__name__)


class ConversionReport:
    """Collects and writes conversion report data."""

    def __init__(self, workbook_name: str):
        self.workbook_name = workbook_name
        self.timestamp = datetime.now().isoformat()
        self.datasources: list[dict] = []
        self.tables: list[dict] = []
        self.calculations: list[dict] = []
        self.worksheets: list[dict] = []
        self.dashboards: list[dict] = []
        self.warnings: list[str] = []
        self.unsupported: list[dict] = []

    def add_datasource(self, name: str, connection_type: str):
        """Record a datasource."""
        self.datasources.append({
            "name": name,
            "connection_type": connection_type,
        })

    def add_table(self, name: str, row_count: int, csv_path: str):
        """Record an exported table."""
        self.tables.append({
            "name": name,
            "row_count": row_count,
            "csv_path": csv_path,
        })

    def add_calculation(
        self, name: str, original: str, dax: str,
        calc_type: str, status: str,
    ):
        """Record a calculated field conversion."""
        self.calculations.append({
            "name": name,
            "original_formula": original,
            "dax_formula": dax,
            "type": calc_type,
            "status": status,
        })

    def add_worksheet(
        self, name: str, mark_type: str, visual_type: str,
        projections: dict, status: str, warnings: list[str] = None,
    ):
        """Record a worksheet conversion."""
        self.worksheets.append({
            "name": name,
            "tableau_mark": mark_type,
            "pbi_visual_type": visual_type,
            "projections": {
                k: [{"column": p.column, "aggregation": p.aggregation} for p in v]
                for k, v in projections.items()
            } if projections else {},
            "status": status,
            "warnings": warnings or [],
        })

    def add_dashboard(self, name: str, page_name: str, visual_count: int):
        """Record a dashboard conversion."""
        self.dashboards.append({
            "name": name,
            "page_name": page_name,
            "visual_count": visual_count,
        })

    def add_warning(self, message: str):
        """Add a general warning."""
        self.warnings.append(message)

    def add_unsupported(self, feature: str, reason: str):
        """Record an unsupported feature."""
        self.unsupported.append({
            "feature": feature,
            "reason": reason,
        })

    def to_dict(self) -> dict:
        """Convert to a dictionary."""
        return {
            "workbook_name": self.workbook_name,
            "timestamp": self.timestamp,
            "summary": {
                "datasources": len(self.datasources),
                "tables_exported": len(self.tables),
                "total_rows": sum(t["row_count"] for t in self.tables),
                "calculations_total": len(self.calculations),
                "calculations_converted": sum(
                    1 for c in self.calculations if c["status"] == "converted"
                ),
                "calculations_unsupported": sum(
                    1 for c in self.calculations if c["status"] == "unsupported"
                ),
                "worksheets": len(self.worksheets),
                "dashboards": len(self.dashboards),
                "warnings": len(self.warnings),
                "unsupported_features": len(self.unsupported),
            },
            "datasources": self.datasources,
            "tables": self.tables,
            "calculations": self.calculations,
            "worksheets": self.worksheets,
            "dashboards": self.dashboards,
            "warnings": self.warnings,
            "unsupported": self.unsupported,
        }

    def write_json(self, output_dir: Path) -> Path:
        """Write conversion_report.json."""
        path = output_dir / "conversion_report.json"
        path.write_text(
            json.dumps(self.to_dict(), indent=2), encoding="utf-8"
        )
        logger.info(f"Wrote {path}")
        return path

    def write_markdown(self, output_dir: Path) -> Path:
        """Write conversion_report.md."""
        data = self.to_dict()
        summary = data["summary"]

        lines = [
            f"# Conversion Report: {self.workbook_name}",
            f"",
            f"**Generated:** {self.timestamp}",
            f"",
            f"## Summary",
            f"",
            f"| Metric | Count |",
            f"|--------|-------|",
            f"| Datasources | {summary['datasources']} |",
            f"| Tables Exported | {summary['tables_exported']} |",
            f"| Total Rows | {summary['total_rows']:,} |",
            f"| Calculations (converted) | {summary['calculations_converted']} |",
            f"| Calculations (unsupported) | {summary['calculations_unsupported']} |",
            f"| Worksheets | {summary['worksheets']} |",
            f"| Dashboards | {summary['dashboards']} |",
            f"| Warnings | {summary['warnings']} |",
            f"",
        ]

        # Tables
        if self.tables:
            lines.extend([
                "## Exported Tables",
                "",
                "| Table | Rows | File |",
                "|-------|------|------|",
            ])
            for t in self.tables:
                lines.append(
                    f"| {t['name']} | {t['row_count']:,} | `{t['csv_path']}` |"
                )
            lines.append("")

        # Calculations
        if self.calculations:
            lines.extend([
                "## Calculated Fields",
                "",
                "| Name | Type | Status | Original | DAX |",
                "|------|------|--------|----------|-----|",
            ])
            for c in self.calculations:
                orig = c['original_formula'][:50] + "..." if len(c['original_formula']) > 50 else c['original_formula']
                dax = c['dax_formula'][:50] + "..." if len(c['dax_formula']) > 50 else c['dax_formula']
                status_icon = "✅" if c['status'] == 'converted' else "⚠️"
                lines.append(
                    f"| {c['name']} | {c['type']} | {status_icon} {c['status']} "
                    f"| `{orig}` | `{dax}` |"
                )
            lines.append("")

        # Worksheets
        if self.worksheets:
            lines.extend([
                "## Worksheets",
                "",
                "| Worksheet | Tableau Mark | Power BI Visual | Status |",
                "|-----------|-------------|-----------------|--------|",
            ])
            for w in self.worksheets:
                status_icon = "✅" if w['status'] == 'converted' else "⚠️"
                lines.append(
                    f"| {w['name']} | {w['tableau_mark']} | {w['pbi_visual_type']} "
                    f"| {status_icon} {w['status']} |"
                )
            lines.append("")

        # Dashboards
        if self.dashboards:
            lines.extend([
                "## Dashboards",
                "",
                "| Dashboard | Page | Visuals |",
                "|-----------|------|---------|",
            ])
            for d in self.dashboards:
                lines.append(
                    f"| {d['name']} | {d['page_name']} | {d['visual_count']} |"
                )
            lines.append("")

        # Warnings
        if self.warnings:
            lines.extend([
                "## ⚠️ Warnings",
                "",
            ])
            for w in self.warnings:
                lines.append(f"- {w}")
            lines.append("")

        # Unsupported
        if self.unsupported:
            lines.extend([
                "## ❌ Unsupported Features",
                "",
                "| Feature | Reason |",
                "|---------|--------|",
            ])
            for u in self.unsupported:
                lines.append(f"| {u['feature']} | {u['reason']} |")
            lines.append("")

        path = output_dir / "conversion_report.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Wrote {path}")
        return path
