from io import BytesIO

import pandas as pd

from shoir_facility_layout import _flow_matrix, _slp_frame, _matrix, _slp_heatmap_values


def _departments():
    return pd.DataFrame([
        {"id": "D1", "name": "Receiving", "x": 10, "y": 80, "area_sqm": 400},
        {"id": "D2", "name": "Assembly", "x": 50, "y": 50, "area_sqm": 500},
        {"id": "D3", "name": "New Department", "x": 80, "y": 20, "area_sqm": 300},
    ])


def _flows():
    return pd.DataFrame([
        {
            "flow_id": "F001",
            "from_id": "D1",
            "to_id": "D2",
            "loads_day": 120,
            "distance_m": 40,
            "relationship": "A",
            "reason": "Material flow",
            "transport": "Forklift",
            "updated_at": "2026-10-02T00:00:00+00:00",
        }
    ])


def test_new_department_is_visible_in_from_to_matrix():
    matrix = _flow_matrix(_departments(), _flows())
    assert list(matrix.index) == ["D1", "D2", "D3"]
    assert list(matrix.columns) == ["D1", "D2", "D3"]
    assert float(matrix.loc["D1", "D2"]) == 120.0
    assert float(matrix.loc["D3", "D1"]) == 0.0


def test_new_department_is_visible_in_slp_before_connection():
    slp = _slp_frame(_departments(), _flows())
    row = slp[(slp["From"] == "D3") & (slp["To"] == "D1")].iloc[0]
    assert row["Status"] == "Unconnected"
    assert row["REL"] == "—"
    assert row["Reason"] == "No connection defined"


def test_slp_matrix_contains_all_departments():
    slp = _slp_frame(_departments(), _flows())
    matrix = _matrix(_departments(), slp)
    assert list(matrix.index) == ["D1", "D2", "D3"]
    assert matrix.loc["D1", "D2"] == "A"
    assert matrix.loc["D3", "D1"] == ""


def test_route_scenario_can_remove_a_connection_and_find_an_alternate_path():
    flows = pd.DataFrame([
        {"flow_id":"F001","from_id":"D1","to_id":"D2","loads_day":100,"distance_m":10,"relationship":"A"},
        {"flow_id":"F002","from_id":"D2","to_id":"D3","loads_day":100,"distance_m":20,"relationship":"A"},
        {"flow_id":"F003","from_id":"D1","to_id":"D3","loads_day":100,"distance_m":50,"relationship":"O"},
    ])
    base, base_dist, _ = __import__("shoir_facility_layout")._shortest_path(flows, "D1", "D3")
    alt, alt_dist, _ = __import__("shoir_facility_layout")._shortest_path(flows, "D1", "D3", None, "F002")
    assert base == ["D1", "D2", "D3"]
    assert base_dist == 30.0
    assert alt == ["D1", "D3"]
    assert alt_dist == 50.0

def test_route_scenario_respects_from_to_direction():
    from shoir_facility_layout import _shortest_path
    flows = pd.DataFrame([
        {"flow_id":"F001","from_id":"D1","to_id":"D2","loads_day":10,"distance_m":5,"relationship":"A"},
    ])
    path, distance, _ = _shortest_path(flows, "D2", "D1")
    assert path == []
    assert distance == float("inf")



def test_slp_heatmap_conversion_is_pandas_compatible_and_preserves_unconnected_cells():
    matrix = pd.DataFrame(
        {
            "D1": ["", "A", "X"],
            "D2": ["E", "—", "U"],
            "D3": ["I", "O", ""],
        },
        index=["D1", "D2", "D3"],
    )

    heatmap = _slp_heatmap_values(matrix)

    assert list(heatmap.columns) == list(matrix.columns)
    assert list(heatmap.index) == list(matrix.index)
    assert heatmap.loc["D2", "D1"] == 4
    assert heatmap.loc["D3", "D1"] == -1
    assert heatmap.loc["D1", "D2"] == 3
    assert heatmap.loc["D3", "D2"] == 0
    assert heatmap.loc["D1", "D3"] == 2
    assert heatmap.loc["D2", "D3"] == 1
    assert pd.isna(heatmap.loc["D1", "D1"])
    assert pd.isna(heatmap.loc["D2", "D2"])
    assert pd.isna(heatmap.loc["D3", "D3"])
    assert all(pd.api.types.is_numeric_dtype(dtype) for dtype in heatmap.dtypes)


def _facility_import_frames(*, departments=None, flows=None):
    return {
        "Departments": pd.DataFrame(departments if departments is not None else [
            {"ID": "D1", "Name": "Receiving", "X": 10, "Y": 20, "Area": 100},
            {"ID": "D2", "Name": "Assembly", "X": 50, "Y": 60, "Area": 200},
        ]),
        "From_To_Flows": pd.DataFrame(flows if flows is not None else [
            {"Flow_ID": "F001", "From_ID": "D1", "To_ID": "D2",
             "Loads_Day": 25, "Distance_M": 12.5, "Relationship": "A"},
        ]),
    }


def _use_temporary_facility_database(tmp_path, monkeypatch):
    import shoir_facility_layout as facility

    monkeypatch.setattr(facility, "DB_PATH", str(tmp_path / "facility-import.db"))
    return facility


def test_facility_import_round_trip_validates_headers_and_preserves_flow_direction(
    tmp_path, monkeypatch
):
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    frames = _facility_import_frames(flows=[
        {"Flow_ID": "F001", "From_ID": "D1", "To_ID": "D2",
         "Loads_Day": 25, "Distance_M": 12.5, "Relationship": "A"},
        {"Flow_ID": "F002", "From_ID": "D2", "To_ID": "D1",
         "Loads_Day": 7, "Distance_M": 15, "Relationship": "O"},
    ])

    assert facility._import_data(frames, "tester", "workspace-a") == (2, 2)
    flows = facility._load_flows("tester", "workspace-a")
    by_direction = {
        (row.from_id, row.to_id): row.loads_day
        for row in flows.itertuples(index=False)
    }
    assert by_direction == {("D1", "D2"): 25.0, ("D2", "D1"): 7.0}


def test_facility_import_rejects_negative_flow_without_partial_writes(
    tmp_path, monkeypatch
):
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    frames = _facility_import_frames(flows=[
        {"Flow_ID": "F001", "From_ID": "D1", "To_ID": "D2",
         "Loads_Day": -1, "Distance_M": 12.5, "Relationship": "A"},
    ])

    import pytest
    with pytest.raises(ValueError, match="loads_day must be at least 0"):
        facility._import_data(frames, "tester", "workspace-a")

    assert facility._load_departments("tester", "workspace-a").empty
    assert facility._load_flows("tester", "workspace-a").empty


def test_facility_import_rejects_dangling_endpoint_without_partial_writes(
    tmp_path, monkeypatch
):
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    frames = _facility_import_frames(flows=[
        {"Flow_ID": "F001", "From_ID": "D1", "To_ID": "MISSING",
         "Loads_Day": 25, "Distance_M": 12.5, "Relationship": "A"},
    ])

    import pytest
    with pytest.raises(ValueError, match="unknown To department"):
        facility._import_data(frames, "tester", "workspace-a")

    assert facility._load_departments("tester", "workspace-a").empty
    assert facility._load_flows("tester", "workspace-a").empty


def test_facility_import_rejects_duplicate_department_ids_and_invalid_slp_codes(
    tmp_path, monkeypatch
):
    import pytest
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    duplicate_departments = _facility_import_frames(departments=[
        {"ID": "D1", "Name": "Receiving", "X": 10, "Y": 20, "Area": 100},
        {"ID": "D1", "Name": "Assembly", "X": 50, "Y": 60, "Area": 200},
    ])
    with pytest.raises(ValueError, match="Duplicate department ID"):
        facility._import_data(duplicate_departments, "tester", "workspace-a")

    invalid_relationship = _facility_import_frames(flows=[
        {"Flow_ID": "F001", "From_ID": "D1", "To_ID": "D2",
         "Loads_Day": 25, "Distance_M": 12.5, "Relationship": "Q"},
    ])
    with pytest.raises(ValueError, match="unsupported SLP relationship"):
        facility._import_data(invalid_relationship, "tester", "workspace-a")

    assert facility._load_departments("tester", "workspace-a").empty
    assert facility._load_flows("tester", "workspace-a").empty


def test_facility_import_rejects_duplicate_directed_edges_but_allows_reverse_flow(
    tmp_path, monkeypatch
):
    import pytest
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    frames = _facility_import_frames(flows=[
        {"Flow_ID": "F001", "From_ID": "D1", "To_ID": "D2",
         "Loads_Day": 25, "Distance_M": 12.5, "Relationship": "A"},
        {"Flow_ID": "F002", "From_ID": "D1", "To_ID": "D2",
         "Loads_Day": 7, "Distance_M": 15, "Relationship": "O"},
    ])

    with pytest.raises(ValueError, match="Duplicate directed flow"):
        facility._import_data(frames, "tester", "workspace-a")

    assert facility._load_departments("tester", "workspace-a").empty
    assert facility._load_flows("tester", "workspace-a").empty


def test_facility_import_is_idempotent_for_the_same_existing_flow_id(
    tmp_path, monkeypatch
):
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    frames = _facility_import_frames()
    assert facility._import_data(frames, "tester", "workspace-a") == (2, 1)
    assert facility._import_data(frames, "tester", "workspace-a") == (2, 1)
    assert len(facility._load_departments("tester", "workspace-a")) == 2
    assert len(facility._load_flows("tester", "workspace-a")) == 1


def test_facility_import_rejects_missing_layout_geometry_instead_of_inventing_defaults(
    tmp_path, monkeypatch
):
    import pytest
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    frames = _facility_import_frames(
        departments=[
            {"ID": "D1", "Name": "Receiving", "Y": 20, "Area": 100},
            {"ID": "D2", "Name": "Assembly", "Y": 60, "Area": 200},
        ],
        flows=[],
    )

    with pytest.raises(ValueError, match="missing required column.*x"):
        facility._import_data(frames, "tester", "workspace-a")

    assert facility._load_departments("tester", "workspace-a").empty
    assert facility._load_flows("tester", "workspace-a").empty


def test_facility_import_rejects_missing_flow_measurement_columns_atomically(
    tmp_path, monkeypatch
):
    import pytest
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    frames = _facility_import_frames(flows=[
        {"Flow_ID": "F001", "From_ID": "D1", "To_ID": "D2", "Relationship": "A"},
    ])

    with pytest.raises(ValueError, match="missing required column.*distance_m|missing required column.*loads_day"):
        facility._import_data(frames, "tester", "workspace-a")

    assert facility._load_departments("tester", "workspace-a").empty
    assert facility._load_flows("tester", "workspace-a").empty


def test_facility_import_rejects_missing_flow_measurement_cells_atomically(
    tmp_path, monkeypatch
):
    import pytest
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    frames = _facility_import_frames(flows=[
        {"Flow_ID": "F001", "From_ID": "D1", "To_ID": "D2",
         "Loads_Day": None, "Distance_M": 12.5, "Relationship": "A"},
    ])

    with pytest.raises(ValueError, match="loads_day is required"):
        facility._import_data(frames, "tester", "workspace-a")

    assert facility._load_departments("tester", "workspace-a").empty
    assert facility._load_flows("tester", "workspace-a").empty


def test_blank_slp_relationship_remains_missing_not_a_fabricated_score(
    tmp_path, monkeypatch
):
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)
    frames = _facility_import_frames(flows=[
        {"Flow_ID": "F001", "From_ID": "D1", "To_ID": "D2",
         "Loads_Day": 25, "Distance_M": 12.5, "Relationship": ""},
    ])
    assert facility._import_data(frames, "tester", "workspace-a") == (2, 1)

    departments = facility._load_departments("tester", "workspace-a")
    flows = facility._load_flows("tester", "workspace-a")
    assert str(flows.iloc[0]["relationship"]) == ""

    slp = facility._slp_frame(departments, flows)
    row = slp[(slp["From"] == "D1") & (slp["To"] == "D2")].iloc[0]
    assert row["REL"] == ""
    assert pd.isna(row["Score"])

    matrix = facility._matrix(departments, slp)
    assert matrix.loc["D1", "D2"] == ""
    assert pd.isna(facility._slp_heatmap_values(matrix).loc["D1", "D2"])



def test_facility_workbook_export_reopens_and_preserves_model_tables():
    from shoir_facility_layout import _export_workbook

    depts = _departments()
    flows = _flows()
    slp = _slp_frame(depts, flows)

    payload = _export_workbook(depts, flows, slp)
    assert isinstance(payload, bytes) and payload.startswith(b"PK")
    assert len(payload) > 1000

    with pd.ExcelFile(BytesIO(payload), engine="openpyxl") as workbook:
        assert workbook.sheet_names == [
            "Departments",
            "From_To_Flows",
            "SLP_Relationships",
            "SLP_Matrix",
        ]
        exported_depts = pd.read_excel(workbook, sheet_name="Departments")
        exported_flows = pd.read_excel(workbook, sheet_name="From_To_Flows")
        exported_slp = pd.read_excel(workbook, sheet_name="SLP_Relationships")
        exported_matrix = pd.read_excel(workbook, sheet_name="SLP_Matrix")

    assert exported_depts["id"].astype(str).tolist() == ["D1", "D2", "D3"]
    assert exported_flows.loc[0, "from_id"] == "D1"
    assert exported_flows.loc[0, "to_id"] == "D2"
    assert float(exported_flows.loc[0, "loads_day"]) == 120.0
    assert len(exported_slp) == len(slp)
    assert exported_matrix.iloc[:, 0].astype(str).tolist() == ["D1", "D2", "D3"]
    assert list(exported_matrix.columns[1:]) == ["D1", "D2", "D3"]


def test_facility_department_persistence_is_isolated_by_owner_and_workspace(
    tmp_path, monkeypatch
):
    facility = _use_temporary_facility_database(tmp_path, monkeypatch)

    facility._save_departments("alpha", "workspace-a", [
        {"id": "D1", "name": "Alpha Receiving", "x": 10, "y": 10, "area_sqm": 100},
    ])
    facility._save_departments("alpha", "workspace-b", [
        {"id": "D1", "name": "Alpha Workspace B", "x": 20, "y": 20, "area_sqm": 200},
    ])
    facility._save_departments("beta", "workspace-a", [
        {"id": "D1", "name": "Beta Receiving", "x": 30, "y": 30, "area_sqm": 300},
    ])

    a = facility._load_departments("alpha", "workspace-a")
    b = facility._load_departments("alpha", "workspace-b")
    other_user = facility._load_departments("beta", "workspace-a")

    assert a["name"].tolist() == ["Alpha Receiving"]
    assert b["name"].tolist() == ["Alpha Workspace B"]
    assert other_user["name"].tolist() == ["Beta Receiving"]
    assert set(a["name"]).isdisjoint(set(b["name"]))
    assert set(a["name"]).isdisjoint(set(other_user["name"]))



def test_flow_distance_cost_summary_matches_hand_checked_load_distance_and_rate():
    from shoir_facility_layout import _flow_distance_cost_summary

    flows = pd.DataFrame({
        "loads_day": [10, 5, 0],
        "distance_m": [2, 4, 100],
    })
    summary = _flow_distance_cost_summary(flows, cost_per_load_meter=0.25)

    # 10×2 + 5×4 + 0×100 = 40 load·meters/day; 40×0.25 = SAR 10/day.
    assert summary["total_load_distance_per_day"] == 40.0
    assert summary["estimated_handling_cost_per_day"] == 10.0
    assert summary["cost_per_load_meter"] == 0.25

    no_rate = _flow_distance_cost_summary(flows)
    assert no_rate["total_load_distance_per_day"] == 40.0
    assert no_rate["estimated_handling_cost_per_day"] is None
    assert no_rate["cost_per_load_meter"] is None


def test_flow_distance_cost_summary_handles_empty_flows_and_rejects_invalid_measurements():
    import pytest
    from shoir_facility_layout import _flow_distance_cost_summary

    empty = pd.DataFrame(columns=["loads_day", "distance_m"])
    assert _flow_distance_cost_summary(empty)["total_load_distance_per_day"] == 0.0
    assert _flow_distance_cost_summary(empty)["estimated_handling_cost_per_day"] is None
    assert _flow_distance_cost_summary(empty, cost_per_load_meter=0.0)["estimated_handling_cost_per_day"] == 0.0

    with pytest.raises(ValueError, match="loads_day must be greater than or equal to 0"):
        _flow_distance_cost_summary(pd.DataFrame({"loads_day": [-1], "distance_m": [5]}))
    with pytest.raises(ValueError, match="distance_m must contain finite numeric values"):
        _flow_distance_cost_summary(pd.DataFrame({"loads_day": [1], "distance_m": ["unknown"]}))
    with pytest.raises(ValueError, match="cost_per_load_meter must be a finite non-negative number"):
        _flow_distance_cost_summary(pd.DataFrame({"loads_day": [1], "distance_m": [1]}), -0.5)



def test_facility_import_rejects_oversized_upload_before_workbook_parser(monkeypatch):
    import pytest
    import shoir_upgrade
    from shoir_facility_layout import _file_to_frames

    class UploadedFile:
        name = "oversized.xlsx"

        @staticmethod
        def getvalue():
            return b"12345"

    monkeypatch.setattr(shoir_upgrade, "MAX_UPLOAD_BYTES", 4)
    with pytest.raises(ValueError, match="Spreadsheet imports are limited to 0 MB"):
        _file_to_frames(UploadedFile())



def test_facility_layout_ui_renders_in_isolated_disposable_workspace(tmp_path, monkeypatch):
    from pathlib import Path

    import shoir_facility_layout as facility
    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(facility, "DB_PATH", str(tmp_path / "facility-ui-smoke.db"))
    smoke_page = tmp_path / "facility_layout_smoke.py"
    smoke_page.write_text(
        "from shoir_facility_layout import render_facility_layout\\n"
        "render_facility_layout('Starter Tier', 'disposable-facility-ui-smoke')\\n",
        encoding="utf-8",
    )

    at = AppTest.from_file(smoke_page, default_timeout=45)
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(exc.value) for exc in at.exception)

    rendered_markdown = "\\n".join(item.value for item in at.markdown)
    assert "Facility Layout & Warehousing Studio" in rendered_markdown
    assert "From-To load matrix" in rendered_markdown
    assert "Systematic Layout Planning" in rendered_markdown
    assert "Export current facility model" in rendered_markdown
