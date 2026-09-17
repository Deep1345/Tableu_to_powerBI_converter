"""Tests for TMDL, PBIR, and PBIP writer modules."""

import json
from pathlib import Path
import pytest
from tab2pbi.converters.types import (
    tmdl_quote_name,
    to_tmdl_type,
    to_pq_type,
    get_summarize_by,
)
from tab2pbi.models import (
    ColumnInfo,
    DataType,
    Datasource,
    FieldRole,
    WorkbookModel,
)
from tab2pbi.writers.pbip import write_pbip
from tab2pbi.writers.semantic_model import write_semantic_model
from tab2pbi.validate import validate_output


def test_tmdl_quote_name():
    assert tmdl_quote_name("Simple") == "Simple"
    assert tmdl_quote_name("Sales Amount") == "'Sales Amount'"
    assert tmdl_quote_name("1st Quarter") == "'1st Quarter'"
    assert tmdl_quote_name("User's Measure") == "'User''s Measure'"
    assert tmdl_quote_name("Profit%") == "'Profit%'"


def test_type_mappings():
    assert to_tmdl_type(DataType.REAL) == "double"
    assert to_tmdl_type(DataType.INTEGER) == "int64"
    assert to_tmdl_type(DataType.DATE) == "dateTime"

    assert to_pq_type(DataType.REAL) == "type number"
    assert to_pq_type(DataType.INTEGER) == "Int64.Type"


def test_summarize_by():
    assert get_summarize_by(FieldRole.MEASURE, DataType.REAL) == "sum"
    assert get_summarize_by(FieldRole.DIMENSION, DataType.STRING) == "none"
    assert get_summarize_by(FieldRole.DIMENSION, DataType.INTEGER) == "none"


def test_write_pbip(tmp_path: Path):
    pbip_file = write_pbip(tmp_path, "TestModel")
    assert pbip_file.exists()
    assert pbip_file.name == "TestModel.pbip"

    data = json.loads(pbip_file.read_text(encoding="utf-8"))
    assert data["version"] == "1.0"
    assert "artifacts" in data

    gitignore = tmp_path / ".gitignore"
    assert gitignore.exists()


def test_write_semantic_model(tmp_path: Path):
    ds = Datasource(
        name="iris",
        caption="IrisData",
        columns={
            "sepal_length": ColumnInfo(
                internal_name="sepal_length",
                caption="Sepal Length",
                datatype=DataType.REAL,
                role=FieldRole.MEASURE,
            ),
            "species": ColumnInfo(
                internal_name="species",
                caption="Species",
                datatype=DataType.STRING,
                role=FieldRole.DIMENSION,
            ),
        },
    )
    model = WorkbookModel(name="IrisProject", datasources=[ds])

    # Dummy csv file
    csv_file = tmp_path / "iris.csv"
    csv_file.write_text("sepal_length,species\n5.1,setosa\n", encoding="utf-8")

    sm_dir, calcs = write_semantic_model(
        model=model,
        output_dir=tmp_path,
        data_paths={"IrisData": csv_file},
        table_name="IrisData",
    )

    assert sm_dir.exists()
    assert (sm_dir / "definition.pbism").exists()
    assert (sm_dir / "definition" / "database.tmdl").exists()
    assert (sm_dir / "definition" / "model.tmdl").exists()
    assert (sm_dir / "definition" / "tables" / "IrisData.tmdl").exists()

    # Verify TMDL indentation uses tabs, not spaces
    table_tmdl = (sm_dir / "definition" / "tables" / "IrisData.tmdl").read_text(encoding="utf-8")
    for line in table_tmdl.splitlines():
        if line.startswith(" "):
            # TMDL strictly requires tab indentation
            pytest.fail(f"TMDL file contains leading space instead of tab: {line}")
