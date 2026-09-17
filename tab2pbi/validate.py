"""Validate generated PBIP output files.

Checks:
- All JSON files parse correctly
- All projections reference existing tables/columns/measures
- TMDL files use tab indentation
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class ValidationResult:
    """Collects validation results."""

    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks_passed: int = 0
        self.checks_failed: int = 0

    def add_error(self, message: str):
        self.errors.append(message)
        self.checks_failed += 1

    def add_warning(self, message: str):
        self.warnings.append(message)

    def add_pass(self, message: str = ""):
        self.checks_passed += 1

    @property
    def is_valid(self) -> bool:
        return self.checks_failed == 0

    def summary(self) -> str:
        lines = [
            f"Validation: {'PASSED' if self.is_valid else 'FAILED'}",
            f"  Checks passed: {self.checks_passed}",
            f"  Checks failed: {self.checks_failed}",
            f"  Warnings: {len(self.warnings)}",
        ]
        for err in self.errors:
            lines.append(f"  ERROR: {err}")
        for warn in self.warnings:
            lines.append(f"  WARN: {warn}")
        return "\n".join(lines)


def validate_output(output_dir: str | Path) -> ValidationResult:
    """Validate a generated PBIP output directory.

    Args:
        output_dir: Path to the output directory.

    Returns:
        ValidationResult with errors and warnings.
    """
    output_dir = Path(output_dir)
    result = ValidationResult()

    if not output_dir.exists():
        result.add_error(f"Output directory does not exist: {output_dir}")
        return result

    # Check for .pbip file
    pbip_files = list(output_dir.glob("*.pbip"))
    if not pbip_files:
        result.add_error("No .pbip file found")
    else:
        result.add_pass(".pbip file exists")

    # Validate all JSON files
    _validate_json_files(output_dir, result)

    # Validate TMDL files
    _validate_tmdl_files(output_dir, result)

    # Validate projections reference valid entities
    _validate_projections(output_dir, result)

    # Check directory structure
    _validate_structure(output_dir, result)

    return result


def _validate_json_files(output_dir: Path, result: ValidationResult):
    """Validate all JSON files parse correctly and conform to PBIP schema requirements."""
    files_to_check = (
        list(output_dir.rglob("*.json"))
        + list(output_dir.rglob("*.pbir"))
        + list(output_dir.rglob("*.pbism"))
    )
    for fpath in files_to_check:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            result.add_pass(f"JSON valid: {fpath.name}")

            # Check for required $schema in PBIR and PBISM files
            if fpath.suffix in (".pbir", ".pbism") or fpath.name in (
                "version.json", "report.json", "pages.json", "page.json", "visual.json"
            ):
                if "$schema" not in data:
                    result.add_error(f"Missing required '$schema' in {fpath.name}")
                else:
                    result.add_pass(f"Schema present: {fpath.name}")

            # Check specific file requirements
            if fpath.name == "version.json":
                if data.get("version") != "1.0.0":
                    result.add_error(f"version.json version must be '1.0.0', got '{data.get('version')}'")
            elif fpath.name == "visual.json":
                if not data.get("name"):
                    result.add_error(f"visual.json missing required 'name' property")
        except json.JSONDecodeError as e:
            result.add_error(f"Invalid JSON in {fpath}: {e}")


def _validate_tmdl_files(output_dir: Path, result: ValidationResult):
    """Validate TMDL files use tab indentation."""
    for tmdl_file in output_dir.rglob("*.tmdl"):
        try:
            content = tmdl_file.read_text(encoding="utf-8")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                if line.startswith("  ") and not line.startswith("\t"):
                    # Check if this is indentation using spaces instead of tabs
                    stripped = line.lstrip()
                    if stripped:  # Non-empty line
                        indent = line[:len(line) - len(stripped)]
                        if " " in indent and "\t" not in indent:
                            result.add_warning(
                                f"Space indentation in {tmdl_file.name} line {i}"
                            )
                            break

            # Check object declaration headers
            if tmdl_file.name == "database.tmdl":
                if not content.strip().startswith("database"):
                    result.add_error(
                        f"database.tmdl must start with 'database <name>', got: '{lines[0]}'"
                    )
                if "compatibilityLevel:" not in content:
                    result.add_error("database.tmdl missing 'compatibilityLevel:'")
            elif tmdl_file.name == "model.tmdl":
                if not content.strip().startswith("model"):
                    result.add_error(
                        f"model.tmdl must start with 'model <name>', got: '{lines[0]}'"
                    )

            result.add_pass(f"TMDL valid: {tmdl_file.name}")

        except Exception as e:
            result.add_error(f"Error reading {tmdl_file}: {e}")


def _validate_projections(output_dir: Path, result: ValidationResult):
    """Validate that visual projections reference existing entities."""
    # Collect all table names and columns from TMDL files
    known_entities: dict[str, set[str]] = {}  # table -> set of columns

    for tmdl_file in output_dir.rglob("*.tmdl"):
        content = tmdl_file.read_text(encoding="utf-8")

        # Find table name
        table_match = re.search(r'^table\s+(.+)$', content, re.MULTILINE)
        if table_match:
            table_name = table_match.group(1).strip().strip("'")
            known_entities[table_name] = set()

            # Find columns
            for col_match in re.finditer(
                r'^\tcolumn\s+(.+?)(?:\s*=.*)?$', content, re.MULTILINE
            ):
                col_name = col_match.group(1).strip().strip("'")
                known_entities[table_name].add(col_name)

            # Find measures
            for measure_match in re.finditer(
                r'^\tmeasure\s+(.+?)\s*=', content, re.MULTILINE
            ):
                measure_name = measure_match.group(1).strip().strip("'")
                known_entities[table_name].add(measure_name)

    # Check visual.json files for references
    for visual_file in output_dir.rglob("visual.json"):
        try:
            with open(visual_file, "r", encoding="utf-8") as f:
                visual_data = json.load(f)

            query_state = (
                visual_data.get("visual", {})
                .get("query", {})
                .get("queryState", {})
            )

            for role, role_data in query_state.items():
                for proj in role_data.get("projections", []):
                    field = proj.get("field", {})

                    # Check Column references
                    for field_type in ("Column", "Measure", "Aggregation"):
                        field_spec = field.get(field_type, {})
                        if field_type == "Aggregation":
                            field_spec = field_spec.get("Expression", {}).get("Column", {})

                        if field_spec:
                            entity = (
                                field_spec.get("Expression", {})
                                .get("SourceRef", {})
                                .get("Entity", "")
                            )
                            prop = field_spec.get("Property", "")

                            if entity and entity not in known_entities:
                                result.add_warning(
                                    f"Visual {visual_file.parent.name} references "
                                    f"unknown table '{entity}'"
                                )
                            elif entity and prop and prop not in known_entities.get(entity, set()):
                                result.add_warning(
                                    f"Visual {visual_file.parent.name} references "
                                    f"unknown column '{entity}.{prop}'"
                                )

            result.add_pass(f"Projections valid: {visual_file.parent.name}")

        except Exception as e:
            result.add_error(f"Error validating {visual_file}: {e}")


def _validate_structure(output_dir: Path, result: ValidationResult):
    """Validate the expected PBIP directory structure."""
    # Check for SemanticModel
    sm_dirs = list(output_dir.glob("*.SemanticModel"))
    if not sm_dirs:
        result.add_error("No .SemanticModel directory found")
    else:
        sm_dir = sm_dirs[0]
        expected = [
            sm_dir / "definition.pbism",
            sm_dir / "definition" / "database.tmdl",
            sm_dir / "definition" / "model.tmdl",
        ]
        for path in expected:
            if path.exists():
                result.add_pass(f"Found: {path.name}")
            else:
                result.add_error(f"Missing: {path}")

    # Check for Report
    report_dirs = list(output_dir.glob("*.Report"))
    if not report_dirs:
        result.add_error("No .Report directory found")
    else:
        report_dir = report_dirs[0]
        expected = [
            report_dir / "definition.pbir",
            report_dir / "definition" / "report.json",
            report_dir / "definition" / "pages" / "pages.json",
        ]
        for path in expected:
            if path.exists():
                result.add_pass(f"Found: {path.name}")
            else:
                result.add_error(f"Missing: {path}")


def main():
    """CLI entry point for validation."""
    if len(sys.argv) < 2:
        print("Usage: python -m tab2pbi.validate <output_dir>")
        sys.exit(1)

    output_dir = sys.argv[1]
    logging.basicConfig(level=logging.INFO)

    result = validate_output(output_dir)
    print(result.summary())
    sys.exit(0 if result.is_valid else 1)


if __name__ == "__main__":
    main()
