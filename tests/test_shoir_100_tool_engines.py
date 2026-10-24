"""Independent fixtures for the new deterministic bin-packing and process-mining engines."""
import io
import math
import pandas as pd
import pytest

from shoir_100_tool_engines import (
    analyze_process_event_log, calculate_carbon_emissions,
    calculate_engineering_economics, calculate_inventory_policy,
    calculate_oee, calculate_process_capability, calculate_standard_time,
    calculate_takt_capacity, first_fit_decreasing_bin_pack,
)


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
    with pytest.raises(ValueError, match="share a timestamp"):
        analyze_process_event_log(pd.DataFrame([
            {"case_id":"C1","activity":"Start","timestamp":"2026-10-01T00:00:00Z"},
            {"case_id":"C1","activity":"Inspect","timestamp":"2026-10-01T00:00:00Z"},
        ]))

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


def test_standard_time_golden_fixture_and_allowance_conventions():
    result = calculate_standard_time([0.50, 0.60, 0.55], 110, 15, allowance_basis="normal_time")
    assert result["metrics"]["observation_count"] == 3
    assert result["metrics"]["observed_mean"] == pytest.approx(0.55)
    assert result["metrics"]["normal_time"] == pytest.approx(0.605)
    assert result["metrics"]["standard_time"] == pytest.approx(0.69575)
    other_basis = calculate_standard_time([0.50, 0.60, 0.55], 110, 15, allowance_basis="standard_time")
    assert other_basis["metrics"]["standard_time"] == pytest.approx(0.605 / 0.85)
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_standard_time([0.5, -0.1], 100, 10)
    with pytest.raises(ValueError, match="less than 100"):
        calculate_standard_time([0.5], 100, 100)


def test_takt_time_and_capacity_golden_fixture():
    result = calculate_takt_capacity(480, 400, 1.2)
    m = result["metrics"]
    assert m["takt_time_minutes_per_unit"] == pytest.approx(1.2)
    assert m["theoretical_capacity_units"] == pytest.approx(400)
    assert m["maximum_whole_units_at_cycle_time"] == 400
    assert m["demand_feasible_at_cycle_time"] is True
    assert m["capacity_gap_units"] == pytest.approx(0)
    with pytest.raises(ValueError, match="Demand must be greater than zero"):
        calculate_takt_capacity(480, 0, 1.2)
    # Period compatibility is a caller-supplied contract because this API accepts
    # one numeric time basis and no separate period/unit metadata. Zero cycle time
    # is still invalid and must be rejected with the precise validation message.
    with pytest.raises(ValueError, match="Cycle time must be greater than zero"):
        calculate_takt_capacity(480, 400, 0)


def test_oee_golden_fixture_and_loss_decomposition():
    result = calculate_oee(480, 30, 30, 800, 760)
    m = result["metrics"]
    assert m["availability_percent"] == pytest.approx(93.75)
    assert m["performance_percent"] == pytest.approx(88.8888888889)
    assert m["quality_percent"] == pytest.approx(95)
    assert m["oee_percent"] == pytest.approx(79.1666666667)
    losses = m["availability_loss_percent"] + m["performance_loss_percent_of_planned_time"] + m["quality_loss_percent_of_planned_time"]
    assert losses == pytest.approx(100 - m["oee_percent"])
    with pytest.raises(ValueError, match="less than planned"):
        calculate_oee(480, 480, 30, 800, 760)
    with pytest.raises(ValueError, match="between zero and total"):
        calculate_oee(480, 30, 30, 800, 801)


def test_process_capability_golden_fixture_with_two_subgroups():
    result = calculate_process_capability([9, 10, 11, 9, 10, 11], 6, 14, subgroup_size=3)
    m = result["metrics"]
    assert m["sample_size"] == 6
    assert m["subgroup_count"] == 2
    assert m["within_subgroup_sigma"] == pytest.approx(1.0)
    assert m["overall_sample_sigma"] == pytest.approx((0.8) ** 0.5)
    assert m["Cp"] == pytest.approx(8 / 6)
    assert m["Cpk"] == pytest.approx(8 / 6)
    assert m["Pp"] == pytest.approx(8 / (6 * (0.8 ** 0.5)))
    assert m["Ppk"] == pytest.approx(m["Pp"])
    with pytest.raises(ValueError, match="less than upper"):
        calculate_process_capability([9, 10, 11, 9, 10, 11], 14, 6, subgroup_size=3)
    with pytest.raises(ValueError, match="two complete subgroups"):
        calculate_process_capability([9, 10, 11], 6, 14, subgroup_size=3)
    with pytest.raises(ValueError, match="variation is zero"):
        calculate_process_capability([10, 10, 10, 10, 10, 10], 6, 14, subgroup_size=3)


def test_inventory_policy_golden_fixture_and_boundaries():
    result = calculate_inventory_policy(10000, 50, 2, 5, working_days_per_year=250,
                                        daily_demand_std=3, service_factor_z=1.645)
    m = result["metrics"]
    assert m["EOQ_units"] == pytest.approx((500000) ** 0.5)
    assert m["average_daily_demand_units"] == pytest.approx(40)
    assert m["safety_stock_units"] == pytest.approx(1.645 * 3 * (5 ** 0.5))
    assert m["reorder_point_units"] == pytest.approx(40 * 5 + m["safety_stock_units"])
    assert m["annual_ordering_cost"] == pytest.approx(m["annual_cycle_stock_holding_cost"])
    with pytest.raises(ValueError, match="greater than zero"):
        calculate_inventory_policy(10000, 50, 0, 5)


def test_carbon_emissions_requires_sourced_versioned_factor():
    result = calculate_carbon_emissions(
        1000, 0.42, activity_unit="kWh", factor_source="Example source provided by user",
        factor_version="2026 demo version", factor_date="2026-01-15",
        scope_boundary="Declared illustrative calculation only",
    )
    assert result["metrics"]["emissions_kg_co2e"] == pytest.approx(420)
    assert result["metrics"]["emissions_tonnes_co2e"] == pytest.approx(0.42)
    assert result["provenance"]["factor date"] == "2026-01-15"
    with pytest.raises(ValueError, match="Factor date must use ISO"):
        calculate_carbon_emissions(
            1000, 0.42, activity_unit="kWh", factor_source="source", factor_version="v1",
            factor_date="not-a-date", scope_boundary="test",
        )
    with pytest.raises(ValueError, match="factor source"):
        calculate_carbon_emissions(
            1000, 0.42, activity_unit="kWh", factor_source="", factor_version="v1",
            factor_date="2026-01-15", scope_boundary="test",
        )


def test_engineering_economics_npv_irr_and_payback_golden_fixture():
    result = calculate_engineering_economics([-1000, 500, 600], 10,
                                               currency_code="SAR", period_unit="year")
    m = result["metrics"]
    assert m["NPV"] == pytest.approx(-49.5867768595)
    assert m["IRR_status"] == "BRACKETED"
    assert m["IRR_percent"] == pytest.approx(6.394, abs=0.01)
    assert m["simple_payback_periods"] == pytest.approx(1 + 500 / 600)
    assert result["units"]["currency_code"] == "SAR"
    with pytest.raises(ValueError, match="greater than -100"):
        calculate_engineering_economics([-100, 50], -100, currency_code="SAR")
    with pytest.raises(ValueError, match="three-letter currency"):
        calculate_engineering_economics([-100, 50], 10, currency_code="Saudi Riyal")


def test_all_new_calculation_results_export_to_parseable_csv():
    calculators = [
        calculate_standard_time([1, 1.1, 0.9], 100, 10),
        calculate_takt_capacity(480, 400, 1.1),
        calculate_oee(480, 30, 30, 800, 760),
        calculate_process_capability([9, 10, 11, 9, 10, 11], 6, 14, subgroup_size=3),
        calculate_inventory_policy(10000, 50, 2, 5, daily_demand_std=3),
        calculate_carbon_emissions(100, 0.4, activity_unit="kWh", factor_source="fixture",
                                   factor_version="v1", factor_date="2026-01-01", scope_boundary="test"),
        calculate_engineering_economics([-1000, 500, 600], 10, currency_code="SAR"),
    ]
    for result in calculators:
        assert result["status"] == "CALCULATED"
        rows = [{"Metric": k, "Value": v} for k, v in result["metrics"].items()]
        restored = pd.read_csv(io.StringIO(pd.DataFrame(rows).to_csv(index=False)))
        assert restored["Metric"].tolist() == list(result["metrics"].keys())
        assert len(restored) == len(result["metrics"])
