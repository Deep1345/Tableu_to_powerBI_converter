"""Extract Tableau workbook contents.

Handles both .twbx (zip archive) and .twb (plain XML) formats.
Extracts the XML tree and any embedded data files (.hyper, .csv, .xlsx).
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from lxml import etree

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Raised when extraction of a Tableau workbook fails."""
    pass


class ExtractedWorkbook:
    """Holds the results of extracting a Tableau workbook."""

    def __init__(
        self,
        twb_path: Path,
        xml_tree: etree._ElementTree,
        data_files: dict[str, Path],
        temp_dir: Optional[Path] = None,
        workbook_dir: Path = Path("."),
    ):
        self.twb_path = twb_path
        self.xml_tree = xml_tree
        self.root = xml_tree.getroot()
        self.data_files = data_files  # {filename: absolute_path}
        self.temp_dir = temp_dir
        self.workbook_dir = workbook_dir

    def cleanup(self):
        """Remove temporary extraction directory."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)


def extract_twbx(twbx_path: Path) -> ExtractedWorkbook:
    """Extract a .twbx file (zip archive containing .twb + data files).

    Args:
        twbx_path: Path to the .twbx file.

    Returns:
        ExtractedWorkbook with parsed XML and extracted data files.

    Raises:
        ExtractionError: If the file cannot be extracted or no .twb found.
    """
    twbx_path = Path(twbx_path).resolve()
    if not twbx_path.exists():
        raise ExtractionError(f"File not found: {twbx_path}")

    if not zipfile.is_zipfile(twbx_path):
        raise ExtractionError(f"Not a valid zip/twbx file: {twbx_path}")

    temp_dir = Path(tempfile.mkdtemp(prefix="tab2pbi_"))
    logger.info(f"Extracting .twbx to {temp_dir}")

    try:
        with zipfile.ZipFile(twbx_path, 'r') as zf:
            zf.extractall(temp_dir)

        # Find the .twb file
        twb_files = list(temp_dir.rglob("*.twb"))
        if not twb_files:
            raise ExtractionError(f"No .twb file found inside {twbx_path}")

        twb_path = twb_files[0]
        logger.info(f"Found workbook: {twb_path.name}")

        # Parse the XML
        xml_tree = _parse_twb_xml(twb_path)

        # Collect data files
        data_files = {}
        for ext in ("*.hyper", "*.csv", "*.xlsx", "*.xls"):
            for f in temp_dir.rglob(ext):
                data_files[f.name] = f
                logger.info(f"Found data file: {f.name}")

        return ExtractedWorkbook(
            twb_path=twb_path,
            xml_tree=xml_tree,
            data_files=data_files,
            temp_dir=temp_dir,
            workbook_dir=twbx_path.parent,
        )

    except ExtractionError:
        raise
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise ExtractionError(f"Failed to extract {twbx_path}: {e}") from e


def extract_twb(twb_path: Path) -> ExtractedWorkbook:
    """Parse a plain .twb XML file and resolve data file references.

    Args:
        twb_path: Path to the .twb file.

    Returns:
        ExtractedWorkbook with parsed XML and resolved data file paths.

    Raises:
        ExtractionError: If the file cannot be parsed.
    """
    twb_path = Path(twb_path).resolve()
    if not twb_path.exists():
        raise ExtractionError(f"File not found: {twb_path}")

    logger.info(f"Parsing .twb file: {twb_path}")
    xml_tree = _parse_twb_xml(twb_path)
    workbook_dir = twb_path.parent

    # Resolve data file references from connections
    data_files = _resolve_data_files(xml_tree, workbook_dir)

    return ExtractedWorkbook(
        twb_path=twb_path,
        xml_tree=xml_tree,
        data_files=data_files,
        temp_dir=None,
        workbook_dir=workbook_dir,
    )


def extract(input_path: str | Path) -> ExtractedWorkbook:
    """Auto-detect and extract a Tableau workbook.

    Args:
        input_path: Path to .twb or .twbx file.

    Returns:
        ExtractedWorkbook ready for parsing.
    """
    path = Path(input_path).resolve()
    suffix = path.suffix.lower()

    if suffix == ".twbx":
        return extract_twbx(path)
    elif suffix == ".twb":
        return extract_twb(path)
    else:
        raise ExtractionError(
            f"Unsupported file type: {suffix}. Expected .twb or .twbx"
        )


def _parse_twb_xml(twb_path: Path) -> etree._ElementTree:
    """Parse a .twb file as XML.

    Args:
        twb_path: Path to the .twb XML file.

    Returns:
        Parsed lxml ElementTree.
    """
    try:
        parser = etree.XMLParser(
            remove_blank_text=False,
            recover=True,  # Be lenient with malformed XML
        )
        tree = etree.parse(str(twb_path), parser)
        root = tree.getroot()

        if root.tag != "workbook":
            raise ExtractionError(
                f"Root element is '{root.tag}', expected 'workbook'"
            )

        version = root.get("version", "unknown")
        logger.info(f"Tableau workbook version: {version}")
        return tree

    except etree.XMLSyntaxError as e:
        raise ExtractionError(f"XML parse error in {twb_path}: {e}") from e


def _resolve_data_files(
    xml_tree: etree._ElementTree, workbook_dir: Path
) -> dict[str, Path]:
    """Find data files referenced by connections in the workbook XML.

    Args:
        xml_tree: Parsed workbook XML.
        workbook_dir: Directory containing the .twb file.

    Returns:
        Dictionary mapping filename to absolute path.
    """
    data_files = {}
    root = xml_tree.getroot()

    # Look for connection elements with file references
    for conn in root.iter("connection"):
        filename = conn.get("filename", "")
        directory = conn.get("directory", "")
        dbname = conn.get("dbname", "")

        for ref in (filename, dbname):
            if ref:
                ref_path = Path(ref)
                if not ref_path.is_absolute():
                    ref_path = workbook_dir / ref_path

                if ref_path.exists():
                    data_files[ref_path.name] = ref_path
                    logger.info(f"Resolved data file: {ref_path}")
                else:
                    logger.warning(f"Data file not found: {ref_path}")

        if directory:
            dir_path = Path(directory)
            if not dir_path.is_absolute():
                dir_path = workbook_dir / dir_path
            if dir_path.exists():
                for ext in ("*.hyper", "*.csv", "*.xlsx", "*.xls"):
                    for f in dir_path.glob(ext):
                        data_files[f.name] = f
                        logger.info(f"Found data file in directory: {f}")

    # Also look for named-connection elements
    for named_conn in root.iter("named-connection"):
        for conn in named_conn.iter("connection"):
            filename = conn.get("filename", "")
            if filename:
                ref_path = Path(filename)
                if not ref_path.is_absolute():
                    ref_path = workbook_dir / ref_path
                if ref_path.exists():
                    data_files[ref_path.name] = ref_path

    return data_files
