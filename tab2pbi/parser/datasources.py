"""Parse Tableau datasource XML into intermediate model.

Extracts connections, tables, columns, and metadata from
/workbook/datasources/datasource elements.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from lxml import etree

from tab2pbi.models import (
    ColumnInfo, ConnectionInfo, DataType, Datasource,
    FieldKind, FieldRole, JoinClause, JoinInfo, TableRelation,
)

logger = logging.getLogger(__name__)

# Map Tableau local-type / datatype strings to our enum
_TYPE_MAP = {
    "string": DataType.STRING,
    "integer": DataType.INTEGER,
    "real": DataType.REAL,
    "date": DataType.DATE,
    "datetime": DataType.DATETIME,
    "boolean": DataType.BOOLEAN,
    "date&time": DataType.DATETIME,
}


def parse_datasources(root: etree._Element) -> list[Datasource]:
    """Parse all datasources from the workbook XML.

    Args:
        root: Root element of the Tableau workbook XML.

    Returns:
        List of Datasource objects (Parameters datasource is excluded).
    """
    datasources = []

    # Only parse top-level datasources under /workbook/datasources/datasource
    # (avoiding <worksheet><table><view><datasources><datasource> references)
    ds_elems = root.findall("datasources/datasource")
    if not ds_elems:
        ds_elems = [
            ds for ds in root.findall(".//datasources/datasource")
            if ds.getparent() is not None and (
                ds.getparent().tag == "datasources" and
                ds.getparent().getparent() is not None and
                "workbook" in ds.getparent().getparent().tag
            )
        ]
    if not ds_elems:
        ds_elems = root.findall(".//datasources/datasource")

    for ds_elem in ds_elems:
        name = ds_elem.get("name", "")
        caption = ds_elem.get("caption", name)

        # Skip the Parameters datasource
        if name.lower() == "parameters" or caption.lower() == "parameters":
            logger.debug("Skipping Parameters datasource")
            continue

        logger.info(f"Parsing datasource: {caption} ({name})")

        try:
            ds = Datasource(name=name, caption=caption)

            # Parse connection info
            ds.connection = _parse_connection(ds_elem)

            # Parse table relations
            ds.tables = _parse_relations(ds_elem)

            # Parse columns from metadata-records and column elements
            ds.columns = _parse_columns(ds_elem)

            # Separate calculated fields
            ds.calculated_fields = {
                k: v for k, v in ds.columns.items() if v.is_calculated
            }

            datasources.append(ds)

        except Exception as e:
            logger.error(f"Error parsing datasource '{caption}': {e}")
            # Create a minimal datasource entry
            datasources.append(Datasource(name=name, caption=caption))

    return datasources


def _parse_connection(ds_elem: etree._Element) -> ConnectionInfo:
    """Extract connection information from a datasource element."""
    conn = ConnectionInfo()

    # Check for named-connections first
    named_conn = ds_elem.find(".//named-connections/named-connection")
    if named_conn is not None:
        conn.named_connection = named_conn.get("name", "")
        conn_elem = named_conn.find("connection")
        if conn_elem is not None:
            conn.class_name = conn_elem.get("class", "")
            conn.filename = conn_elem.get("filename", "")
            conn.server = conn_elem.get("server", "")
            conn.dbname = conn_elem.get("dbname", "")
            return conn

    # Direct connection element
    conn_elem = ds_elem.find("connection")
    if conn_elem is not None:
        conn.class_name = conn_elem.get("class", "")
        conn.filename = conn_elem.get("filename", "")
        conn.server = conn_elem.get("server", "")
        conn.dbname = conn_elem.get("dbname", "")

        # For federated connections, look deeper
        if conn.class_name == "federated":
            for inner_conn in conn_elem.iter("connection"):
                inner_class = inner_conn.get("class", "")
                if inner_class and inner_class != "federated":
                    conn.class_name = inner_class
                    conn.filename = inner_conn.get("filename", conn.filename)
                    conn.dbname = inner_conn.get("dbname", conn.dbname)
                    break

    return conn


def _parse_relations(ds_elem: etree._Element) -> list[TableRelation]:
    """Parse table relations from a datasource element."""
    tables = []

    # Find relation elements (can be nested for joins)
    for conn_elem in ds_elem.findall(".//connection"):
        for rel in conn_elem.findall("relation"):
            table = _parse_relation_element(rel)
            if table:
                tables.append(table)

    return tables


def _parse_relation_element(rel_elem: etree._Element) -> Optional[TableRelation]:
    """Recursively parse a relation element."""
    rel_type = rel_elem.get("type", "")
    name = rel_elem.get("name", "")
    table_name = rel_elem.get("table", "")
    connection = rel_elem.get("connection", "")

    if rel_type == "table":
        return TableRelation(
            name=name,
            table_name=table_name,
            connection=connection,
        )
    elif rel_type == "text":
        # CSV/text file relations
        return TableRelation(
            name=name,
            table_name=name,
            connection=connection,
        )
    elif rel_type in ("join", "left", "right", "inner", "full"):
        # Join relation
        join_rel = TableRelation(
            name=name or "join",
            is_join=True,
        )

        # Parse join type
        join_type = rel_type if rel_type != "join" else "inner"
        join_info = JoinInfo(join_type=join_type)

        # Parse join clauses
        for clause in rel_elem.findall(".//clause"):
            expr = clause.find("expression")
            if expr is not None:
                op = expr.get("op", "=")
                operands = expr.findall("expression")
                if len(operands) >= 2:
                    left_op = operands[0].get("op", "")
                    right_op = operands[1].get("op", "")
                    # Extract [Table].[Column] references
                    left_parts = _parse_column_ref(left_op)
                    right_parts = _parse_column_ref(right_op)
                    if left_parts and right_parts:
                        join_info.clauses.append(JoinClause(
                            left_table=left_parts[0],
                            left_column=left_parts[1],
                            right_table=right_parts[0],
                            right_column=right_parts[1],
                            operator=op,
                        ))

        join_rel.join_info = join_info

        # Parse child relations
        for child_rel in rel_elem.findall("relation"):
            child = _parse_relation_element(child_rel)
            if child:
                join_rel.children.append(child)

        return join_rel

    return None


def _parse_column_ref(op_string: str) -> Optional[tuple[str, str]]:
    """Parse a column reference like '[Table].[Column]'."""
    match = re.match(r'\[([^\]]+)\]\.\[([^\]]+)\]', op_string)
    if match:
        return match.group(1), match.group(2)
    return None


def _parse_columns(ds_elem: etree._Element) -> dict[str, ColumnInfo]:
    """Parse columns from metadata-records and column elements."""
    columns: dict[str, ColumnInfo] = {}

    # First pass: metadata-records (detailed type info)
    for md in ds_elem.findall(".//metadata-records/metadata-record"):
        class_attr = md.get("class", "")
        if class_attr != "column":
            continue

        remote_name = ""
        local_name = ""
        local_type = ""
        parent_name = ""
        agg = ""

        for child in md:
            if child.tag == "remote-name":
                remote_name = child.text or ""
            elif child.tag == "local-name":
                local_name = child.text or ""
            elif child.tag == "local-type":
                local_type = child.text or ""
            elif child.tag == "parent-name":
                parent_name = child.text or ""
            elif child.tag == "aggregation":
                agg = child.text or ""

        if local_name:
            # Clean up internal name format
            internal_name = local_name.strip("[]")
            col = ColumnInfo(
                internal_name=local_name,
                caption=remote_name or internal_name,
                remote_name=remote_name,
                table_name=parent_name.strip("[]"),
                datatype=_TYPE_MAP.get(local_type, DataType.STRING),
                aggregation=agg,
            )
            columns[local_name] = col

    # Second pass: column elements (role, kind, caption, calc info)
    for col_elem in ds_elem.findall("column"):
        name = col_elem.get("name", "")
        if not name:
            continue

        caption = col_elem.get("caption", "")
        datatype = col_elem.get("datatype", "")
        role = col_elem.get("role", "")
        col_type = col_elem.get("type", "")
        hidden = col_elem.get("hidden", "false") == "true"

        # Get or create the column entry
        if name in columns:
            col = columns[name]
        else:
            col = ColumnInfo(
                internal_name=name,
                caption=caption or name.strip("[]"),
            )

        # Update with column element attributes
        if caption:
            col.caption = caption
        if datatype:
            col.datatype = _TYPE_MAP.get(datatype, col.datatype)
        if role:
            col.role = (FieldRole.MEASURE if role == "measure"
                       else FieldRole.DIMENSION)
        if col_type:
            col.kind = _kind_from_type(col_type)

        # Check for calculated field
        calc_elem = col_elem.find("calculation")
        if calc_elem is not None:
            col.is_calculated = True
            col.formula = calc_elem.get("formula", "")
            col_class = calc_elem.get("class", "")
            if col_class == "tableau":
                pass  # Normal calculated field

        # Check if system-generated
        if name.startswith("[Number of Records]") or name.startswith("[:Measure Names]"):
            col.is_generated = True

        columns[name] = col

    # Clean up captions: if caption is empty, use the stripped internal name
    for col in columns.values():
        if not col.caption or col.caption == col.internal_name:
            col.caption = col.internal_name.strip("[]").replace(":", " ").strip()

    return columns


def _kind_from_type(type_str: str) -> FieldKind:
    """Convert Tableau type attribute to FieldKind."""
    if type_str == "quantitative":
        return FieldKind.QUANTITATIVE
    elif type_str == "ordinal":
        return FieldKind.ORDINAL
    return FieldKind.NOMINAL
