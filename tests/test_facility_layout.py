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


def test_slp_export_handles_flows_without_reason_column():
    flows = _flows().drop(columns=["reason"])
    slp = _slp_frame(_departments(), flows)
    row = slp[(slp["From"] == "D1") & (slp["To"] == "D2")].iloc[0]
    assert row["Reason"] == ""
