"""Intermediate data model for Tableau workbook representation.

These dataclasses serve as the bridge between Tableau XML parsing
and Power BI PBIP generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class DataType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    REAL = "real"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    UNKNOWN = "unknown"


class FieldRole(str, Enum):
    DIMENSION = "dimension"
    MEASURE = "measure"


class FieldKind(str, Enum):
    NOMINAL = "nominal"       # nk
    ORDINAL = "ordinal"       # ok
    QUANTITATIVE = "quantitative"  # qk


class MarkType(str, Enum):
    AUTOMATIC = "Automatic"
    BAR = "Bar"
    LINE = "Line"
    AREA = "Area"
    PIE = "Pie"
    TEXT = "Text"
    CIRCLE = "Circle"
    SQUARE = "Square"
    SHAPE = "Shape"
    MAP = "Map"
    GANTT_BAR = "GanttBar"
    POLYGON = "Polygon"


class AggregationType(str, Enum):
    NONE = "none"
    SUM = "sum"
    AVG = "avg"
    COUNT = "cnt"
    COUNTD = "ctd"
    MIN = "min"
    MAX = "max"
    ATTR = "attr"
    MEDIAN = "med"
    YEAR = "yr"
    QUARTER = "qr"
    MONTH = "mn"
    DAY = "dy"
    HOUR = "hr"
    MINUTE = "mi"
    SECOND = "sc"
    WEEK = "wk"
    TRUNCYEAR = "tyr"
    TRUNCQUARTER = "tqr"
    TRUNCMONTH = "tmn"
    TRUNCDAY = "tdy"
    USER = "user"


class FilterType(str, Enum):
    CATEGORICAL = "categorical"
    QUANTITATIVE = "quantitative"


@dataclass
class ColumnInfo:
    """Represents a column/field in a Tableau datasource."""
    internal_name: str          # e.g. "[Sales]"
    caption: str                # Display name, e.g. "Sales Amount"
    remote_name: str = ""       # Name in the actual data source
    table_name: str = ""        # Parent table name
    datatype: DataType = DataType.STRING
    role: FieldRole = FieldRole.DIMENSION
    kind: FieldKind = FieldKind.NOMINAL
    aggregation: str = ""       # Default aggregation
    is_calculated: bool = False
    formula: str = ""           # Tableau calc formula
    is_generated: bool = False  # System-generated columns like Number of Records


@dataclass
class JoinClause:
    """Represents a join clause between tables."""
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    operator: str = "="


@dataclass
class JoinInfo:
    """Represents a join between tables."""
    join_type: str = "inner"  # inner, left, right, full
    clauses: list[JoinClause] = field(default_factory=list)


@dataclass
class TableRelation:
    """Represents a table or a join relation in a datasource."""
    name: str
    table_name: str = ""       # Actual table/file reference
    connection: str = ""       # Connection reference
    is_join: bool = False
    join_info: Optional[JoinInfo] = None
    children: list[TableRelation] = field(default_factory=list)


@dataclass
class ConnectionInfo:
    """Represents a data connection."""
    class_name: str = ""       # hyper, textscan, excel-direct, federated
    filename: str = ""
    server: str = ""
    dbname: str = ""
    named_connection: str = ""


@dataclass
class Datasource:
    """Represents a Tableau datasource."""
    name: str
    caption: str = ""
    connection: ConnectionInfo = field(default_factory=ConnectionInfo)
    tables: list[TableRelation] = field(default_factory=list)
    columns: dict[str, ColumnInfo] = field(default_factory=dict)
    calculated_fields: dict[str, ColumnInfo] = field(default_factory=dict)


@dataclass
class ShelfField:
    """A field placed on a shelf (rows/cols/encoding)."""
    datasource: str = ""
    aggregation: AggregationType = AggregationType.NONE
    field_name: str = ""
    kind: FieldKind = FieldKind.NOMINAL
    raw_token: str = ""

    @property
    def is_measure(self) -> bool:
        return self.kind == FieldKind.QUANTITATIVE

    @property
    def is_date_part(self) -> bool:
        return self.aggregation in (
            AggregationType.YEAR, AggregationType.QUARTER,
            AggregationType.MONTH, AggregationType.DAY,
            AggregationType.HOUR, AggregationType.MINUTE,
            AggregationType.WEEK,
        )

    @property
    def is_date_trunc(self) -> bool:
        return self.aggregation in (
            AggregationType.TRUNCYEAR, AggregationType.TRUNCQUARTER,
            AggregationType.TRUNCMONTH, AggregationType.TRUNCDAY,
        )


@dataclass
class FilterInfo:
    """Represents a filter on a worksheet."""
    column_name: str
    datasource: str = ""
    filter_type: FilterType = FilterType.CATEGORICAL
    members: list[str] = field(default_factory=list)
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    include_null: bool = True


@dataclass
class Worksheet:
    """Represents a Tableau worksheet."""
    name: str
    title: str = ""
    datasource_name: str = ""
    mark_type: MarkType = MarkType.AUTOMATIC
    rows: list[ShelfField] = field(default_factory=list)
    cols: list[ShelfField] = field(default_factory=list)
    color: list[ShelfField] = field(default_factory=list)
    size: list[ShelfField] = field(default_factory=list)
    label: list[ShelfField] = field(default_factory=list)
    text: list[ShelfField] = field(default_factory=list)
    tooltip: list[ShelfField] = field(default_factory=list)
    detail: list[ShelfField] = field(default_factory=list)
    filters: list[FilterInfo] = field(default_factory=list)
    resolved_mark: MarkType = MarkType.BAR


@dataclass
class DashboardZone:
    """A zone (visual container) in a dashboard."""
    zone_id: str = ""
    worksheet_name: str = ""   # Empty for non-worksheet zones
    zone_type: str = ""        # worksheet, text, title, blank
    x: int = 0                 # 0-100000 scale
    y: int = 0
    w: int = 0
    h: int = 0
    text_content: str = ""     # For text zones


@dataclass
class Dashboard:
    """Represents a Tableau dashboard."""
    name: str
    title: str = ""
    width: int = 1000
    height: int = 800
    zones: list[DashboardZone] = field(default_factory=list)


@dataclass
class WorkbookModel:
    """Complete intermediate representation of a Tableau workbook."""
    name: str
    datasources: list[Datasource] = field(default_factory=list)
    worksheets: list[Worksheet] = field(default_factory=list)
    dashboards: list[Dashboard] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        """Serialize the model to JSON for debugging."""
        def _serialize(obj):
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, '__dict__'):
                return {k: _serialize(v) for k, v in obj.__dict__.items()
                        if not k.startswith('_')}
            if isinstance(obj, list):
                return [_serialize(i) for i in obj]
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            return obj
        return json.dumps(_serialize(self), indent=indent)

    def get_datasource(self, name: str) -> Optional[Datasource]:
        """Find a datasource by name or caption."""
        for ds in self.datasources:
            if ds.name == name or ds.caption == name:
                return ds
        return None

    def get_primary_datasource(self) -> Optional[Datasource]:
        """Get the first non-Parameters datasource."""
        for ds in self.datasources:
            if ds.name.lower() != 'parameters':
                return ds
        return None
