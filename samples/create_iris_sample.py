"""Generate sample Iris dataset and Tableau workbooks (.twb and .twbx).

Creates:
- samples/iris.csv
- samples/iris_dashboard.twb
- samples/iris_dashboard.twbx
"""

import csv
import os
from pathlib import Path
import zipfile

# 150-row Iris dataset
IRIS_DATA = [
    (5.1, 3.5, 1.4, 0.2, "setosa"),
    (4.9, 3.0, 1.4, 0.2, "setosa"),
    (4.7, 3.2, 1.3, 0.2, "setosa"),
    (4.6, 3.1, 1.5, 0.2, "setosa"),
    (5.0, 3.6, 1.4, 0.2, "setosa"),
    (5.4, 3.9, 1.7, 0.4, "setosa"),
    (4.6, 3.4, 1.4, 0.3, "setosa"),
    (5.0, 3.4, 1.5, 0.2, "setosa"),
    (4.4, 2.9, 1.4, 0.2, "setosa"),
    (4.9, 3.1, 1.5, 0.1, "setosa"),
    (5.4, 3.7, 1.5, 0.2, "setosa"),
    (4.8, 3.4, 1.6, 0.2, "setosa"),
    (4.8, 3.0, 1.4, 0.1, "setosa"),
    (4.3, 3.0, 1.1, 0.1, "setosa"),
    (5.8, 4.0, 1.2, 0.2, "setosa"),
    (5.7, 4.4, 1.5, 0.4, "setosa"),
    (5.4, 3.9, 1.3, 0.4, "setosa"),
    (5.1, 3.5, 1.4, 0.3, "setosa"),
    (5.7, 3.8, 1.7, 0.3, "setosa"),
    (5.1, 3.8, 1.5, 0.3, "setosa"),
    (5.4, 3.4, 1.7, 0.2, "setosa"),
    (5.1, 3.7, 1.5, 0.4, "setosa"),
    (4.6, 3.6, 1.0, 0.2, "setosa"),
    (5.1, 3.3, 1.7, 0.5, "setosa"),
    (4.8, 3.4, 1.9, 0.2, "setosa"),
    (5.0, 3.0, 1.6, 0.2, "setosa"),
    (5.0, 3.4, 1.6, 0.4, "setosa"),
    (5.2, 3.5, 1.5, 0.2, "setosa"),
    (5.2, 3.4, 1.4, 0.2, "setosa"),
    (4.7, 3.2, 1.6, 0.2, "setosa"),
    (4.8, 3.1, 1.6, 0.2, "setosa"),
    (5.4, 3.4, 1.5, 0.4, "setosa"),
    (5.2, 4.1, 1.5, 0.1, "setosa"),
    (5.5, 4.2, 1.4, 0.2, "setosa"),
    (4.9, 3.1, 1.5, 0.2, "setosa"),
    (5.0, 3.2, 1.2, 0.2, "setosa"),
    (5.5, 3.5, 1.3, 0.2, "setosa"),
    (4.9, 3.6, 1.4, 0.1, "setosa"),
    (4.4, 3.0, 1.3, 0.2, "setosa"),
    (5.1, 3.4, 1.5, 0.2, "setosa"),
    (5.0, 3.5, 1.3, 0.3, "setosa"),
    (4.5, 2.3, 1.3, 0.3, "setosa"),
    (4.4, 3.2, 1.3, 0.2, "setosa"),
    (5.0, 3.5, 1.6, 0.6, "setosa"),
    (5.1, 3.8, 1.9, 0.4, "setosa"),
    (4.8, 3.0, 1.4, 0.3, "setosa"),
    (5.1, 3.8, 1.6, 0.2, "setosa"),
    (4.6, 3.2, 1.4, 0.2, "setosa"),
    (5.3, 3.7, 1.5, 0.2, "setosa"),
    (5.0, 3.3, 1.4, 0.2, "setosa"),
    (7.0, 3.2, 4.7, 1.4, "versicolor"),
    (6.4, 3.2, 4.5, 1.5, "versicolor"),
    (6.9, 3.1, 4.9, 1.5, "versicolor"),
    (5.5, 2.3, 4.0, 1.3, "versicolor"),
    (6.5, 2.8, 4.6, 1.5, "versicolor"),
    (5.7, 2.8, 4.5, 1.3, "versicolor"),
    (6.3, 3.3, 4.7, 1.6, "versicolor"),
    (4.9, 2.4, 3.3, 1.0, "versicolor"),
    (6.6, 2.9, 4.6, 1.3, "versicolor"),
    (5.2, 2.7, 3.9, 1.4, "versicolor"),
    (5.0, 2.0, 3.5, 1.0, "versicolor"),
    (5.9, 3.0, 4.2, 1.5, "versicolor"),
    (6.0, 2.2, 4.0, 1.0, "versicolor"),
    (6.1, 2.9, 4.7, 1.4, "versicolor"),
    (5.6, 2.9, 3.6, 1.3, "versicolor"),
    (6.7, 3.1, 4.4, 1.4, "versicolor"),
    (5.6, 3.0, 4.5, 1.5, "versicolor"),
    (5.8, 2.7, 4.1, 1.0, "versicolor"),
    (6.2, 2.2, 4.5, 1.5, "versicolor"),
    (5.6, 2.5, 3.9, 1.1, "versicolor"),
    (5.9, 3.2, 4.8, 1.8, "versicolor"),
    (6.1, 2.8, 4.0, 1.3, "versicolor"),
    (6.3, 2.5, 4.9, 1.5, "versicolor"),
    (6.1, 2.8, 4.7, 1.2, "versicolor"),
    (6.4, 2.9, 4.3, 1.3, "versicolor"),
    (6.6, 3.0, 4.4, 1.4, "versicolor"),
    (6.8, 2.8, 4.8, 1.4, "versicolor"),
    (6.7, 3.0, 5.0, 1.7, "versicolor"),
    (6.0, 2.9, 4.5, 1.5, "versicolor"),
    (5.7, 2.6, 3.5, 1.0, "versicolor"),
    (5.5, 2.4, 3.8, 1.1, "versicolor"),
    (5.5, 2.4, 3.7, 1.0, "versicolor"),
    (5.8, 2.7, 3.9, 1.2, "versicolor"),
    (6.0, 2.7, 5.1, 1.6, "versicolor"),
    (5.4, 3.0, 4.5, 1.5, "versicolor"),
    (6.0, 3.4, 4.5, 1.6, "versicolor"),
    (6.7, 3.1, 4.7, 1.5, "versicolor"),
    (6.3, 2.3, 4.4, 1.3, "versicolor"),
    (5.6, 3.0, 4.1, 1.3, "versicolor"),
    (5.5, 2.5, 4.0, 1.3, "versicolor"),
    (5.5, 2.6, 4.4, 1.2, "versicolor"),
    (6.1, 3.0, 4.6, 1.4, "versicolor"),
    (5.8, 2.6, 4.0, 1.2, "versicolor"),
    (5.0, 2.3, 3.3, 1.0, "versicolor"),
    (5.6, 2.7, 4.2, 1.3, "versicolor"),
    (5.7, 3.0, 4.2, 1.2, "versicolor"),
    (5.7, 2.9, 4.2, 1.3, "versicolor"),
    (6.2, 2.9, 4.3, 1.3, "versicolor"),
    (5.1, 2.5, 3.0, 1.1, "versicolor"),
    (5.7, 2.8, 4.1, 1.3, "versicolor"),
    (6.3, 3.3, 6.0, 2.5, "virginica"),
    (5.8, 2.7, 5.1, 1.9, "virginica"),
    (7.1, 3.0, 5.9, 2.1, "virginica"),
    (6.3, 2.9, 5.6, 1.8, "virginica"),
    (6.5, 3.0, 5.8, 2.2, "virginica"),
    (7.6, 3.0, 6.6, 2.1, "virginica"),
    (4.9, 2.5, 4.5, 1.7, "virginica"),
    (7.3, 2.9, 6.3, 1.8, "virginica"),
    (6.7, 2.5, 5.8, 1.8, "virginica"),
    (7.2, 3.6, 6.1, 2.5, "virginica"),
    (6.5, 3.2, 5.1, 2.0, "virginica"),
    (6.4, 2.7, 5.3, 1.9, "virginica"),
    (6.8, 3.0, 5.5, 2.1, "virginica"),
    (5.7, 2.5, 5.0, 2.0, "virginica"),
    (5.8, 2.8, 5.1, 2.4, "virginica"),
    (6.4, 3.2, 5.3, 2.3, "virginica"),
    (6.5, 3.0, 5.5, 1.8, "virginica"),
    (7.7, 3.8, 6.7, 2.2, "virginica"),
    (7.7, 2.6, 6.9, 2.3, "virginica"),
    (6.0, 2.2, 5.0, 1.5, "virginica"),
    (6.9, 3.2, 5.7, 2.3, "virginica"),
    (5.6, 2.8, 4.9, 2.0, "virginica"),
    (7.7, 2.8, 6.7, 2.0, "virginica"),
    (6.3, 2.7, 4.9, 1.8, "virginica"),
    (6.7, 3.3, 5.7, 2.1, "virginica"),
    (7.2, 3.2, 6.0, 1.8, "virginica"),
    (6.2, 2.8, 4.8, 1.8, "virginica"),
    (6.1, 3.0, 4.9, 1.8, "virginica"),
    (6.4, 2.8, 5.6, 2.1, "virginica"),
    (7.2, 3.0, 5.8, 1.6, "virginica"),
    (7.4, 2.8, 6.1, 1.9, "virginica"),
    (7.9, 3.8, 6.4, 2.0, "virginica"),
    (6.4, 2.8, 5.6, 2.2, "virginica"),
    (6.3, 2.8, 5.1, 1.5, "virginica"),
    (6.1, 2.6, 5.6, 1.4, "virginica"),
    (7.7, 3.0, 6.1, 2.3, "virginica"),
    (6.3, 3.4, 5.6, 2.4, "virginica"),
    (6.4, 3.1, 5.5, 1.8, "virginica"),
    (6.0, 3.0, 4.8, 1.8, "virginica"),
    (6.9, 3.1, 5.4, 2.1, "virginica"),
    (6.7, 3.1, 5.6, 2.4, "virginica"),
    (6.9, 3.1, 5.1, 2.3, "virginica"),
    (5.8, 2.7, 5.1, 1.9, "virginica"),
    (6.8, 3.2, 5.9, 2.3, "virginica"),
    (6.7, 3.3, 5.7, 2.5, "virginica"),
    (6.7, 3.0, 5.2, 2.3, "virginica"),
    (6.3, 2.5, 5.0, 1.9, "virginica"),
    (6.5, 3.0, 5.2, 2.0, "virginica"),
    (6.2, 3.4, 5.4, 2.3, "virginica"),
    (5.9, 3.0, 5.1, 1.8, "virginica"),
]

TWB_TEMPLATE = """<?xml version='1.0' encoding='utf-8' ?>
<workbook source-build='2023.2.0' source-platform='mac' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <datasources>
    <datasource caption='Iris' inline='true' name='federated.iris' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='iris' name='textscan.iris'>
            <connection class='textscan' directory='.' filename='iris.csv' />
          </named-connection>
        </named-connections>
        <relation connection='textscan.iris' name='iris.csv' table='[iris#csv]' type='table'>
          <columns character-set='UTF-8'>
            <column datatype='real' name='SepalLength' />
            <column datatype='real' name='SepalWidth' />
            <column datatype='real' name='PetalLength' />
            <column datatype='real' name='PetalWidth' />
            <column datatype='string' name='Species' />
          </columns>
        </relation>
      </connection>
      <column caption='Sepal Length' datatype='real' name='[SepalLength]' role='measure' type='quantitative' />
      <column caption='Sepal Width' datatype='real' name='[SepalWidth]' role='measure' type='quantitative' />
      <column caption='Petal Length' datatype='real' name='[PetalLength]' role='measure' type='quantitative' />
      <column caption='Petal Width' datatype='real' name='[PetalWidth]' role='measure' type='quantitative' />
      <column caption='Species' datatype='string' name='[Species]' role='dimension' type='nominal' />
      <!-- Calculated fields -->
      <column caption='Petal Area' datatype='real' name='[Calculation_PetalArea]' role='measure' type='quantitative'>
        <calculation class='tableau' formula='[PetalLength] * [PetalWidth]' />
      </column>
      <column caption='Species Group' datatype='string' name='[Calculation_SpeciesGroup]' role='dimension' type='nominal'>
        <calculation class='tableau' formula='IF [Species] = &quot;setosa&quot; THEN &quot;Setosa Group&quot; ELSE &quot;Other Group&quot; END' />
      </column>
      <column caption='Avg Sepal by Species' datatype='real' name='[Calculation_AvgSepalLOD]' role='measure' type='quantitative'>
        <calculation class='tableau' formula='{FIXED [Species] : AVG([SepalLength])}' />
      </column>
      <column caption='Total Sepal Length' datatype='real' name='[Calculation_TotalSepal]' role='measure' type='quantitative'>
        <calculation class='tableau' formula='SUM([SepalLength])' />
      </column>
    </datasource>
  </datasources>
  <worksheets>
    <!-- Worksheet 1: Scatter Plot -->
    <worksheet name='Sepal Scatter'>
      <table>
        <view>
          <datasources>
            <datasource caption='Iris' name='federated.iris' />
          </datasources>
          <datasource-dependencies datasource='federated.iris'>
            <column datatype='real' name='[SepalLength]' />
            <column datatype='real' name='[SepalWidth]' />
            <column datatype='string' name='[Species]' />
          </datasource-dependencies>
        </view>
        <panes>
          <pane>
            <mark class='Circle' />
            <encodings>
              <color column='[federated.iris].[none:Species:nk]' />
            </encodings>
          </pane>
        </panes>
        <rows>[federated.iris].[none:SepalWidth:qk]</rows>
        <cols>[federated.iris].[none:SepalLength:qk]</cols>
      </table>
    </worksheet>
    <!-- Worksheet 2: Bar Chart -->
    <worksheet name='Petal Length by Species'>
      <table>
        <view>
          <datasources>
            <datasource caption='Iris' name='federated.iris' />
          </datasources>
        </view>
        <panes>
          <pane>
            <mark class='Bar' />
          </pane>
        </panes>
        <rows>[federated.iris].[avg:PetalLength:qk]</rows>
        <cols>[federated.iris].[none:Species:nk]</cols>
      </table>
    </worksheet>
    <!-- Worksheet 3: Pie Chart -->
    <worksheet name='Species Breakdown'>
      <table>
        <view>
          <datasources>
            <datasource caption='Iris' name='federated.iris' />
          </datasources>
        </view>
        <panes>
          <pane>
            <mark class='Pie' />
            <encodings>
              <color column='[federated.iris].[none:Species:nk]' />
            </encodings>
          </pane>
        </panes>
        <rows />
        <cols />
      </table>
    </worksheet>
    <!-- Worksheet 4: Petal Area Card -->
    <worksheet name='Petal Area Summary'>
      <table>
        <view>
          <datasources>
            <datasource caption='Iris' name='federated.iris' />
          </datasources>
        </view>
        <panes>
          <pane>
            <mark class='Text' />
          </pane>
        </panes>
        <rows>[federated.iris].[avg:Petal Area:qk]</rows>
        <cols />
      </table>
    </worksheet>
  </worksheets>
  <dashboards>
    <dashboard name='Iris Overview'>
      <size maxheight='900' maxwidth='1600' minheight='900' minwidth='1600' />
      <zones>
        <zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>
          <!-- Top Left: Scatter -->
          <zone h='50000' id='2' name='Sepal Scatter' w='50000' x='0' y='0' />
          <!-- Top Right: Bar Chart -->
          <zone h='50000' id='3' name='Petal Length by Species' w='50000' x='50000' y='0' />
          <!-- Bottom Left: Pie Chart -->
          <zone h='50000' id='4' name='Species Breakdown' w='50000' x='0' y='50000' />
          <!-- Bottom Right: Petal Area Summary -->
          <zone h='50000' id='5' name='Petal Area Summary' w='50000' x='50000' y='50000' />
        </zone>
      </zones>
    </dashboard>
  </dashboards>
</workbook>
"""


def generate_samples(target_dir: Path):
    """Generate sample files in target_dir."""
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write iris.csv
    csv_path = target_dir / "iris.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["SepalLength", "SepalWidth", "PetalLength", "PetalWidth", "Species"])
        writer.writerows(IRIS_DATA)
    print(f"✅ Generated: {csv_path} ({len(IRIS_DATA)} rows)")

    # 2. Write iris_dashboard.twb
    twb_path = target_dir / "iris_dashboard.twb"
    twb_path.write_text(TWB_TEMPLATE, encoding="utf-8")
    print(f"✅ Generated: {twb_path}")

    # 3. Create iris_dashboard.twbx (zip containing twb and Data/iris.csv)
    twbx_path = target_dir / "iris_dashboard.twbx"
    with zipfile.ZipFile(twbx_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("iris_dashboard.twb", TWB_TEMPLATE)
        zf.write(csv_path, "Data/Extracts/iris.csv")
    print(f"✅ Generated: {twbx_path}")


if __name__ == "__main__":
    out_dir = Path(__file__).parent
    generate_samples(out_dir)
