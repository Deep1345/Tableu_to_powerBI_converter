# tab2pbi: Tableau to Power BI Project Converter

A production-grade CLI tool built for the **Micron Placement Hackathon (Round 2)** that automatically converts Tableau workbooks (`.twb` / `.twbx`) into native Power BI Project files (`.pbip`).

The generated `.pbip` output uses modern text-based formats (**TMDL** for semantic modeling and **PBIR** for reports) that open directly in Power BI Desktop with full version control compatibility.

---

## 🚀 Key Highlights

- **Zero-Binary Generation**: Generates clean, human-readable, text-based TMDL and PBIR files instead of opaque binary `.pbix` blobs.
- **Full Extraction**: Unpacks `.twbx` archives and extracts embedded data sources (`.hyper`, `.csv`, `.xlsx`).
- **DAX AST Engine**: Custom tokenizer and recursive-descent parser translating Tableau calculations (arithmetic, aggregates, logical `IF`/`CASE`, date/string functions, and `{FIXED}` LOD expressions) into valid DAX.
- **Layout Precision**: Normalizes Tableau 0–100,000 zone coordinates into pixel-perfect Power BI canvas positions (1280×720 default).
- **Built-in Validation**: Verifies TMDL tab indentation, JSON schemas, and projection entity references before completion.
- **Audit Reports**: Emits structured `conversion_report.json` and human-readable `conversion_report.md` detailing every converted measure, table, and visual.

---

## 🛠️ System Architecture

```text
Tableau Workbook (.twb / .twbx)
               │
               ▼
   [1. Extractor (extractor.py)] ── Unzip .twbx, locate .twb & data files
               │
               ▼
   [2. XML Parser (parser/*)] ──── Parse datasources, calcs, worksheets, zones
               │
               ▼
       Intermediate Model ──────── In-memory AST & dataclass representation
               │
               ├────────────────────────┬────────────────────────┐
               ▼                        ▼                        ▼
      [3. Data Export]        [4. DAX Converter]       [5. Visual & Layout]
   (hyper/csv/xlsx -> CSV)    (Tableau Calc -> DAX)    (Zones -> Canvas Pos)
               │                        │                        │
               └────────────────────────┴────────────────────────┘
                                        │
                                        ▼
                            [6. PBIP Writers (writers/*)]
                                        │
             ┌──────────────────────────┴──────────────────────────┐
             ▼                                                     ▼
     Semantic Model (.SemanticModel)                       Report (.Report)
   - definition.pbism                                    - definition.pbir
   - definition/database.tmdl                            - definition/report.json
   - definition/model.tmdl                               - definition/pages/*.json
   - definition/tables/*.tmdl                            - definition/pages/*/visuals/*.json
             │                                                     │
             └──────────────────────────┬──────────────────────────┘
                                        ▼
                        [7. Validator & Report Writer]
                        - Root .pbip project file
                        - conversion_report.md & .json
```

---

## 📦 Installation & Setup

### 1. Requirements
- Python 3.9+ (tested on Python 3.9 – 3.11)
- Virtual environment recommended

### 2. Setup
```bash
# Clone or navigate to the repository
cd /Users/deep/Desktop/fileConverter

# Activate virtual environment
source .venv/bin/activate

# Install dependencies (already installed in .venv)
pip install -r requirements.txt
```

---

## 🧪 Testing

### Run the Full Automated Test Suite (31 unit & integration tests)
```bash
.venv/bin/pytest tab2pbi/tests/ -v
```

### Test Coverage Summary
- **DAX Translation Tests (`test_dax.py`)**: Tests basic arithmetic, aggregations (`SUM`, `AVG`, `COUNTD`, `MIN`, `MAX`), null handling (`ZN`, `IFNULL`, `ISNULL`), conditional statements (`IF/THEN/ELSE`, `CASE/WHEN`), string functions, date functions, and `{FIXED}` LOD expressions.
- **Worksheet & Shelf Tests (`test_worksheets.py`)**: Tests shelf token regex (`[datasource].[sum:Field:qk]`), mark type deduction (`Automatic` -> Line / Bar), and visual mapping.
- **Layout Math Tests (`test_layout.py`)**: Tests 0–100,000 coordinate scaling to 1280×720 canvas, inner padding, and dashboard zone positioning.
- **Writer Tests (`test_writers.py`)**: Tests TMDL strict tab indentation, Power Query M expressions, and `.pbip` schema generation.
- **End-to-End Integration Tests (`test_integration.py`)**: Converts the synthetic Iris dataset workbook from both `.twb` and `.twbx`, running full validation.

---

## 🎮 How to Run the Converter

### 1. Convert the Included Iris Demo Workbook
```bash
.venv/bin/python -m tab2pbi samples/iris_dashboard.twbx --out ./output --validate --verbose
```

Output:
```text
🔄 Converting: samples/iris_dashboard.twbx
📁 Output: output/iris_dashboard
📦 Step 1: Extracting workbook...
🔍 Step 2: Parsing Tableau XML...
   Found 1 datasource(s)
   Found 4 worksheet(s)
   Found 1 dashboard(s)
💾 Step 3: Exporting data...
   Exported: iris (150 rows)
📊 Step 4-5: Writing Semantic Model (TMDL)...
   ✅ Calc: Petal Area -> Iris[Petal Length] * Iris[Petal Width]
   ✅ Calc: Species Group -> IF(Iris[Species] = "setosa", "Setosa Group", "Other Group")
   ✅ Calc: Avg Sepal by Species -> CALCULATE(AVERAGE(Iris[Sepal Length]), ALLEXCEPT(Iris, Iris[Species]))
   ✅ Calc: Total Sepal Length -> SUM(Iris[Sepal Length])
📈 Step 6-7: Writing Report (PBIR)...
   Sepal Scatter: Circle -> scatterChart
   Petal Length by Species: Bar -> clusteredColumnChart
   Species Breakdown: Pie -> pieChart
   Petal Area Summary: Text -> card
📝 Step 8: Writing .pbip project file...
📋 Step 9: Writing conversion report...
============================================================
✅ Conversion complete!
```

### 2. Convert Your Own Tableau Files Later
```bash
.venv/bin/python -m tab2pbi /path/to/workbook.twbx --out ./my_output --validate
```

---

## 🖥️ Opening in Power BI Desktop

1. Copy the output folder to a Windows machine with **Power BI Desktop** (March 2024 or newer).
2. Ensure **PBIP and PBIR preview features** are enabled in Power BI Desktop:
   - Go to `File` > `Options and settings` > `Options` > `Preview features`
   - Check **"Power BI Project (.pbip) save option"**
   - Check **"Store reports using enhanced metadata format (PBIR)"**
3. Double-click the root `<WorkbookName>.pbip` file.
4. Click **"Refresh"** on the Home tab to load the exported CSV data into the local VertiPaq engine.
5. The dashboard pages and visuals will render automatically according to the layout!

---

## 📋 Scope & Graceful Degradation

| Feature Area | Supported in Scope | Unsupported Handling |
| :--- | :--- | :--- |
| **Data Sources** | Hyper extracts, CSV, Excel (`.xlsx`) | Logged in conversion report |
| **Visual Types** | Bar, Column, Line, Area, Pie, Donut, Text Table, Card, Scatter | Degrades to Table/Card with warning |
| **Calculations** | Arithmetic, Aggregates, `IF/ELSE`, `CASE`, Strings, Dates, `{FIXED}` LOD | Emits `= BLANK()` + logs in report |
| **Dashboards** | Absolute & tiled zone layout to 1280×720 canvas | Overflow clamped inside bounds |
| **Filters** | Categorical dimension filters | Wildcard/complex regex skipped |
