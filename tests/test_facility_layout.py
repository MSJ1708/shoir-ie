import pandas as pd

from shoir_facility_layout import _flow_matrix, _slp_frame, _matrix


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
