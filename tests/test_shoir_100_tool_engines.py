"""Independent fixtures for the new deterministic bin-packing and process-mining engines."""
import io
import math
import pandas as pd
import pytest

from shoir_100_tool_engines import analyze_process_event_log, first_fit_decreasing_bin_pack


def test_first_fit_decreasing_known_fixture_and_capacity_accounting():
    source = pd.DataFrame({"item":["A","B","C","D","E","F"],
                           "size":[6,5,5,4,4,2], "quantity":[1,1,1,1,1,1]})
    result = first_fit_decreasing_bin_pack(source, 10)
    assert result["status"] == "HEURISTIC_FEASIBLE"
    assert result["optimality_proven"] is False
    assert result["metrics"]["item_instances"] == 6
    assert result["metrics"]["bins_used"] == 3
    assert result["metrics"]["item_size_total"] == 26
    assert result["metrics"]["capacity_total"] == 30
    assert result["metrics"]["unused_capacity_total"] == 4
    assert math.isclose(result["metrics"]["utilization_percent"], 260/3)
    assert result["bins"]["Unused capacity"].sum() == 4
    assert (result["bins"]["Used capacity"] <= 10 + 1e-9).all()
    assert all("not proof" in warning or "not implemented" in warning for warning in result["warnings"])


@pytest.mark.parametrize("capacity,items", [
    (0, pd.DataFrame({"item":["A"],"size":[1]})),
    (10, pd.DataFrame({"item":["A"],"size":[0]})),
    (10, pd.DataFrame({"item":["A"],"size":[11]})),
    (10, pd.DataFrame({"item":["A"],"size":[1],"quantity":[1.5]})),
    (10, pd.DataFrame({"item":["A"],"size":["bad"]})),
])
def test_bin_packing_rejects_invalid_inputs(capacity, items):
    with pytest.raises(ValueError):
        first_fit_decreasing_bin_pack(items, capacity)


def test_bin_packing_expands_quantity_without_mutating_source():
    source = pd.DataFrame({"item":["widget"],"size":[2.5],"quantity":[3]})
    before = source.copy(deep=True)
    result = first_fit_decreasing_bin_pack(source, 5)
    assert result["metrics"]["item_instances"] == 3
    assert result["metrics"]["bins_used"] == 2
    pd.testing.assert_frame_equal(source, before)


def _events():
    return pd.DataFrame([
        {"case_id":"C1","activity":"Start","timestamp":"2026-10-01T00:00:00Z"},
        {"case_id":"C1","activity":"Inspect","timestamp":"2026-10-01T00:03:00Z"},
        {"case_id":"C1","activity":"Pack","timestamp":"2026-10-01T00:05:00Z"},
        {"case_id":"C2","activity":"Start","timestamp":"2026-10-01T01:00:00+01:00"},
        {"case_id":"C2","activity":"Inspect","timestamp":"2026-10-01T01:04:00+01:00"},
        {"case_id":"C2","activity":"Pack","timestamp":"2026-10-01T01:10:00+01:00"},
    ])


def test_process_mining_timezone_duration_and_transition_fixture():
    source = _events()
    before = source.copy(deep=True)
    result = analyze_process_event_log(source, reference_sequence=["Start","Inspect","Pack"])
    assert result["status"] == "ANALYZED"
    assert result["metrics"] == {
        "case_count": 2, "event_count": 6, "transition_count": 4, "activity_count": 3,
        "mean_case_duration_minutes": 7.5, "median_case_duration_minutes": 7.5,
    }
    dfg = result["directly_follows"]
    assert set(zip(dfg["From activity"],dfg["To activity"])) == {("Start","Inspect"),("Inspect","Pack")}
    counts = {(r["From activity"],r["To activity"]):r["transition_count"] for _,r in dfg.iterrows()}
    assert counts == {("Start","Inspect"):2,("Inspect","Pack"):2}
    assert result["cases"]["Exact reference-trace match"].tolist() == [True,True]
    pd.testing.assert_frame_equal(source, before)


def test_process_mining_rejects_missing_invalid_and_empty_fields():
    with pytest.raises(ValueError, match="Missing required event-log columns"):
        analyze_process_event_log(pd.DataFrame({"order":[1]}))
    with pytest.raises(ValueError, match="invalid timestamps"):
        analyze_process_event_log(pd.DataFrame([{"case_id":"C1","activity":"Start","timestamp":"bad-time"}]))
    with pytest.raises(ValueError, match="must not be empty"):
        analyze_process_event_log(pd.DataFrame([{"case_id":"","activity":"Start","timestamp":"2026-10-01T00:00:00Z"}]))
    with pytest.raises(ValueError, match="event records"):
        analyze_process_event_log(pd.DataFrame(columns=["case_id","activity","timestamp"]))

def test_download_ready_csv_outputs_round_trip_with_expected_content():
    packed = first_fit_decreasing_bin_pack(
        pd.DataFrame({"item":["A","B"],"size":[6,4],"quantity":[1,1]}), 10
    )
    assignments_csv = packed["assignments"].to_csv(index=False)
    bins_csv = packed["bins"].to_csv(index=False)
    assignments = pd.read_csv(io.StringIO(assignments_csv))
    bins = pd.read_csv(io.StringIO(bins_csv))
    assert len(assignments) == 2
    assert set(assignments["Item"]) == {"A","B"}
    assert float(bins["Used capacity"].sum()) == 10.0
    assert float(bins["Unused capacity"].sum()) == 0.0

    mined = analyze_process_event_log(_events())
    case_csv = pd.read_csv(io.StringIO(mined["cases"].to_csv(index=False)))
    transition_csv = pd.read_csv(io.StringIO(mined["directly_follows"].to_csv(index=False)))
    assert case_csv["Case"].tolist() == ["C1","C2"]
    assert int(transition_csv["transition_count"].sum()) == 4
