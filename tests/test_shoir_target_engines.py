"""Independent fixtures and boundary tests for the focused target engines."""
from __future__ import annotations

import math

import pytest
import pandas as pd

from shoir_target_engines import (
    monitor_forecast_drift,
    plan_two_sample_t_sample_size,
    solve_cutting_stock,
)


def test_cutting_stock_known_case_and_material_reconciliation():
    # Two 6-unit pieces fit on each 12-unit stock; four parts require two stocks.
    result = solve_cutting_stock(
        12,
        [{"name": "A", "length": 6, "quantity": 4}],
        kerf=0,
    )
    assert result["status"] == "OPTIMAL"
    assert result["stock_count"] == 2
    assert result["physical_length_total"] == pytest.approx(24)
    assert result["total_stock_length"] == pytest.approx(24)
    assert result["waste_length"] == pytest.approx(0)
    assert int(result["cut_plan"]["Stocks"].sum()) == 2


def test_cutting_stock_kerf_is_applied_and_reported_explicitly():
    result = solve_cutting_stock(
        10,
        [{"name": "A", "length": 5, "quantity": 2}],
        kerf=0.2,
    )
    assert result["status"] == "OPTIMAL"
    assert result["stock_count"] == 2
    assert result["kerf_allowance_total"] == pytest.approx(0.4)
    assert result["waste_length"] == pytest.approx(9.6)


def test_cutting_stock_rejects_bad_inputs_and_reports_impossible_piece():
    with pytest.raises(ValueError, match="greater than zero"):
        solve_cutting_stock(0, [{"name": "A", "length": 1, "quantity": 1}])
    with pytest.raises(ValueError, match="whole number"):
        solve_cutting_stock(10, [{"name": "A", "length": 1, "quantity": 1.5}])
    result = solve_cutting_stock(5, [{"name": "oversize", "length": 6, "quantity": 1}])
    assert result["status"] == "INFEASIBLE"
    assert result["stock_count"] is None
    assert result["issues"][0]["part"] == "oversize"


def test_forecast_drift_monitor_has_hand_calculated_error_values():
    result = monitor_forecast_drift(
        predictions=[10, 20, 30],
        actuals=[12, 18, 33],
        max_mae=2,
    )
    assert result["status"] == "DRIFT_ALERT"
    assert result["mae"] == pytest.approx(7 / 3)
    assert result["rmse"] == pytest.approx(math.sqrt(17 / 3))
    assert result["bias_actual_minus_prediction"] == pytest.approx(1)
    assert result["mape_pct_excluding_zero_actuals"] == pytest.approx(
        (2/12 + 2/18 + 3/33) / 3 * 100
    )


def test_forecast_drift_monitor_window_and_invalid_inputs():
    result = monitor_forecast_drift([1, 100, 100], [1, 105, 101], max_mae=10, window=2)
    assert result["observations"] == 2
    assert result["status"] == "WITHIN_THRESHOLD"
    with pytest.raises(ValueError, match="same number"):
        monitor_forecast_drift([1, 2], [1], max_mae=1)
    with pytest.raises(ValueError, match="[Aa]t least two"):
        monitor_forecast_drift([1], [1], max_mae=1)
    with pytest.raises(ValueError, match="negative"):
        monitor_forecast_drift([1, 2], [1, 2], max_mae=-0.5)


def test_power_planner_matches_known_balanced_t_test_reference():
    result = plan_two_sample_t_sample_size(effect_size=0.5, alpha=0.05, target_power=0.80)
    assert result["status"] == "CALCULATED"
    assert result["required_n_per_group"] == 64
    assert result["total_sample_size"] == 128
    assert result["achieved_power"] >= 0.80
    assert result["power_at_n_minus_1"] < 0.80
    assert "no multiplicity/dropout" in result["assumptions"]


def test_power_planner_handles_search_limit_and_invalid_inputs():
    result = plan_two_sample_t_sample_size(0.01, target_power=0.99, max_n_per_group=3)
    assert result["status"] == "LIMIT_REACHED"
    assert result["required_n_per_group"] is None
    with pytest.raises(ValueError, match="greater than zero"):
        plan_two_sample_t_sample_size(0)
    with pytest.raises(ValueError, match="strictly between"):
        plan_two_sample_t_sample_size(0.5, alpha=1)



def test_time_study_uses_explicit_rating_and_allowance_convention():
    from shoir_target_engines import calculate_time_study

    result = calculate_time_study(
        [1, 2, 3], performance_rating_pct=110, allowance_pct=10, time_unit="minutes"
    )
    assert result["status"] == "CALCULATED"
    assert result["observation_count"] == 3
    assert result["mean_observed_time"] == pytest.approx(2.0)
    assert result["sample_standard_deviation"] == pytest.approx(1.0)
    assert result["normal_time"] == pytest.approx(2.2)
    # 10% allowance is defined as a share of standard time, not normal time.
    assert result["standard_time"] == pytest.approx(2.2 / 0.9)
    assert len(result["observations"]) == 3
    assert "percentage of standard time" in result["method"]
    assert "Fewer than 10 observations" in result["warning"]


def test_time_study_rejects_empty_nonpositive_and_invalid_assumptions():
    from shoir_target_engines import calculate_time_study

    with pytest.raises(ValueError, match="at least one"):
        calculate_time_study([])
    with pytest.raises(ValueError, match="greater than zero"):
        calculate_time_study([1, 0, 2])
    with pytest.raises(ValueError, match="greater than zero"):
        calculate_time_study([1, 2], performance_rating_pct=0)
    with pytest.raises(ValueError, match="less than 100"):
        calculate_time_study([1, 2], allowance_pct=100)
    with pytest.raises(ValueError, match="finite number"):
        calculate_time_study([1, float("nan")])


def test_takt_capacity_calculates_capacity_gap_and_exact_boundary():
    from shoir_target_engines import calculate_takt_capacity

    result = calculate_takt_capacity(480, 120, 3, time_unit="minutes")
    assert result["status"] == "CAPACITY_MEETS_DEMAND"
    assert result["takt_time_per_unit"] == pytest.approx(4.0)
    assert result["implied_capacity_units_per_period"] == pytest.approx(160.0)
    assert result["capacity_gap_units_per_period"] == pytest.approx(40.0)
    assert result["demand_load_pct_of_implied_capacity"] == pytest.approx(75.0)

    boundary = calculate_takt_capacity(480, 120, 4, time_unit="minutes")
    assert boundary["implied_capacity_units_per_period"] == pytest.approx(120.0)
    assert boundary["capacity_gap_units_per_period"] == pytest.approx(0.0)
    assert boundary["feasible_at_stated_cycle_time"] is True

    shortfall = calculate_takt_capacity(480, 120, 5, time_unit="minutes")
    assert shortfall["status"] == "CAPACITY_BELOW_DEMAND"
    assert shortfall["capacity_gap_units_per_period"] == pytest.approx(-24.0)


def test_takt_capacity_rejects_zero_mixed_or_noninteger_denominators():
    from shoir_target_engines import calculate_takt_capacity

    with pytest.raises(ValueError, match="[Aa]vailable production time"):
        calculate_takt_capacity(0, 120, 3)
    with pytest.raises(ValueError, match="whole number"):
        calculate_takt_capacity(480, 120.5, 3)
    with pytest.raises(ValueError, match="[Cc]ycle time"):
        calculate_takt_capacity(480, 120, 0)
    with pytest.raises(ValueError, match="[Tt]ime unit"):
        calculate_takt_capacity(480, 120, 3, time_unit="")


def test_time_study_result_and_input_snapshot_roundtrip_per_user(tmp_path):
    from shoir_target_engines import calculate_time_study
    from workspace_persistence import load_user_workspace, save_user_workspace

    db_path = str(tmp_path / "focused-tool-workspace.db")
    inputs = {
        "observation_times_text": "1, 2, 3",
        "performance_rating_pct": 110.0,
        "allowance_pct_of_standard_time": 10.0,
        "time_unit": "minutes",
    }
    result = calculate_time_study([1, 2, 3], 110, 10, time_unit="minutes")
    result["_workspace_persistence"] = "SAVED_LOCAL_FALLBACK"
    workspace = {
        "shoir_tool_result_T021": result,
        "shoir_tool_inputs_T021": inputs,
        "shoir_tool_save_status_T021": "SAVED_LOCAL_FALLBACK",
    }

    assert save_user_workspace("Alice", workspace, db_path)
    alice = {}
    bob = {}
    assert load_user_workspace("Alice", alice, db_path)
    assert not load_user_workspace("Bob", bob, db_path)

    restored = alice["shoir_tool_result_T021"]
    assert restored["standard_time"] == pytest.approx(2.2 / 0.9)
    assert restored["_workspace_persistence"] == "SAVED_LOCAL_FALLBACK"
    assert isinstance(restored["observations"], pd.DataFrame)
    pd.testing.assert_frame_equal(restored["observations"], result["observations"])
    assert alice["shoir_tool_inputs_T021"] == inputs
    assert "shoir_tool_result_T021" not in bob


def test_work_sampling_wilson_intervals_match_hand_checked_counts():
    from shoir_target_engines import analyze_work_sampling

    result = analyze_work_sampling(
        {"Productive": 60, "Idle": 40}, confidence_level=0.95, target_margin_pct=5.0
    )
    assert result["status"] == "MORE_OBSERVATIONS_RECOMMENDED"
    assert result["total_observations"] == 100
    assert result["minimum_observations_for_target_margin"] == 385
    assert result["target_sample_size_met"] is False
    frame = result["activity_summary"].set_index("Activity")
    assert frame.loc["Productive", "Observed proportion (%)"] == pytest.approx(60.0)
    assert frame.loc["Productive", "95.0% Wilson lower (%)"] == pytest.approx(50.22, abs=0.03)
    assert frame.loc["Productive", "95.0% Wilson upper (%)"] == pytest.approx(69.08, abs=0.03)
    assert frame.loc["Idle", "Observed proportion (%)"] == pytest.approx(40.0)

    adequate = analyze_work_sampling(
        {"Productive": 200, "Idle": 200}, confidence_level=0.95, target_margin_pct=5.0
    )
    assert adequate["status"] == "SAMPLE_TARGET_MET"
    assert adequate["target_sample_size_met"] is True
    assert adequate["total_observations"] == 400


def test_work_sampling_rejects_invalid_counts_and_assumptions():
    from shoir_target_engines import analyze_work_sampling

    with pytest.raises(ValueError, match="at least two"):
        analyze_work_sampling({})
    with pytest.raises(ValueError, match="greater than zero"):
        analyze_work_sampling({"Productive": 0, "Idle": 0})
    with pytest.raises(ValueError, match="whole number"):
        analyze_work_sampling({"Productive": 2.5, "Idle": 1})
    with pytest.raises(ValueError, match="whole number"):
        analyze_work_sampling({"Productive": True, "Idle": 1})
    with pytest.raises(ValueError, match="normalization"):
        analyze_work_sampling({"Idle": 2, " idle ": 3})
    with pytest.raises(ValueError, match="Confidence level"):
        analyze_work_sampling({"Productive": 1, "Idle": 1}, confidence_level=1.0)
    with pytest.raises(ValueError, match="margin of error"):
        analyze_work_sampling({"Productive": 1, "Idle": 1}, target_margin_pct=0)


def test_pareto_root_cause_matches_hand_checked_cumulative_counts_and_records_five_whys():
    from shoir_target_engines import analyze_pareto_root_cause

    result = analyze_pareto_root_cause(
        {"Method": 10, "Machine": 60, "Material": 30},
        problem_statement="Repeated stoppages",
        why_chain=[
            "Why 1: line stops unexpectedly",
            "Why 2: sensor faults are recorded",
            "Why 3: sensor mount vibrates loose",
            "Why 4: fastener inspection is not specified",
            "Why 5: maintenance standard omits the mount",
        ],
        countermeasure="Add a mount inspection to the preventive checklist",
        owner="Maintenance lead",
        due_date="2026-11-01",
    )
    frame = result["pareto_summary"]
    assert result["status"] == "ROOT_CAUSE_REVIEW_RECORDED"
    assert result["total_count"] == 100
    assert result["categories_to_reach_80_percent"] == 2
    assert frame["Category"].tolist() == ["Machine", "Material", "Method"]
    assert frame["Share (%)"].tolist() == pytest.approx([60.0, 30.0, 10.0])
    assert frame["Cumulative (%)"].tolist() == pytest.approx([60.0, 90.0, 100.0])
    assert len(result["why_chain"]) == 5
    assert result["follow_up_complete"] is True
    assert "do not prove causation" in result["warning"]


def test_pareto_root_cause_rejects_invalid_counts_incomplete_whys_and_bad_dates():
    from shoir_target_engines import analyze_pareto_root_cause

    with pytest.raises(ValueError, match="non-empty"):
        analyze_pareto_root_cause({})
    with pytest.raises(ValueError, match="greater than zero"):
        analyze_pareto_root_cause({"Machine": 0, "Material": 0})
    with pytest.raises(ValueError, match="non-negative whole number"):
        analyze_pareto_root_cause({"Machine": -1, "Material": 2})
    with pytest.raises(ValueError, match="whole number"):
        analyze_pareto_root_cause({"Machine": 1.5, "Material": 2})
    with pytest.raises(ValueError, match="normalization"):
        analyze_pareto_root_cause({"Machine": 1, " machine ": 2})
    with pytest.raises(ValueError, match="exactly five"):
        analyze_pareto_root_cause({"Machine": 1}, why_chain=["Why one", "Why two"])
    with pytest.raises(ValueError, match="problem statement"):
        analyze_pareto_root_cause({"Machine": 1}, why_chain=["a", "b", "c", "d", "e"])
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        analyze_pareto_root_cause({"Machine": 1}, due_date="tomorrow")


def test_5s_audit_reports_equal_pillar_scores_and_action_assignment_gaps():
    from shoir_target_engines import assess_5s_audit

    items = [
        {"category": "Sort", "criterion": "Remove unnecessary items", "score": 1, "evidence": "photo-1", "owner": "", "due_date": ""},
        {"category": "Set in Order", "criterion": "Label storage locations", "score": 2, "evidence": "audit-2", "owner": "Shift lead", "due_date": "2026-11-01"},
        {"category": "Shine", "criterion": "Clean stations", "score": 3},
        {"category": "Standardize", "criterion": "Display standard work", "score": 4},
        {"category": "Sustain", "criterion": "Run weekly reviews", "score": 4},
    ]
    result = assess_5s_audit(items)
    assert result["status"] == "FOLLOW_UP_DETAILS_MISSING"
    assert result["overall_5s_score_pct_equal_pillar_weight"] == pytest.approx(70.0)
    assert result["item_weighted_score_pct"] == pytest.approx(70.0)
    assert result["priority_action_count"] == 2
    assert result["priority_action_assignment_gaps"] == 1
    assert result["pillar_summary"]["5S pillar"].tolist() == [
        "Sort", "Set in Order", "Shine", "Standardize", "Sustain"
    ]

    items[0]["owner"] = "Area owner"
    items[0]["due_date"] = "2026-11-05"
    assigned = assess_5s_audit(items)
    assert assigned["status"] == "FOLLOW_UP_REQUIRED"
    assert assigned["priority_action_assignment_gaps"] == 0
    assert "not a certified audit" in assigned["warning"]


def test_5s_audit_rejects_missing_pillar_duplicate_criteria_bad_scores_and_dates():
    from shoir_target_engines import assess_5s_audit

    five = [
        {"category": category, "criterion": f"Criterion {index}", "score": 3}
        for index, category in enumerate(["Sort", "Set in Order", "Shine", "Standardize", "Sustain"])
    ]
    with pytest.raises(ValueError, match="each 5S pillar"):
        assess_5s_audit(five[:-1])
    duplicate = [dict(row) for row in five]
    duplicate[-1]["criterion"] = duplicate[0]["criterion"]
    with pytest.raises(ValueError, match="must be unique"):
        assess_5s_audit(duplicate)
    fractional = [dict(row) for row in five]
    fractional[0]["score"] = 2.5
    with pytest.raises(ValueError, match="whole number from 0 to 4"):
        assess_5s_audit(fractional)
    invalid_date = [dict(row) for row in five]
    invalid_date[0].update(score=1, owner="Owner", due_date="next week")
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        assess_5s_audit(invalid_date)


def test_kaizen_a3_computes_signed_progress_without_claiming_unverified_savings():
    from shoir_target_engines import build_kaizen_a3_record

    result = build_kaizen_a3_record(
        title="Reduce cycle time",
        problem_statement="Cycle time exceeds target",
        metric_name="Cycle time",
        unit="minutes per unit",
        baseline_value=100,
        target_value=80,
        actual_after_value=90,
        root_cause_hypothesis="Setup standard is not followed",
        countermeasure="Standardize and audit setup steps",
        owner="Process engineer",
        due_date="2026-11-15",
        baseline_evidence="baseline-run-101",
        implementation_status="In Progress",
    )
    assert result["status"] == "In Progress"
    assert result["outcome_status"] == "OBSERVED_NOT_VERIFIED"
    assert result["target_progress_pct"] == pytest.approx(50.0)
    assert result["remaining_difference_to_target"] == pytest.approx(-10.0)
    assert result["baseline_evidence"] == "baseline-run-101"
    assert "not marked verified" in result["warning"]


def test_kaizen_a3_requires_comparable_targets_and_evidence_for_verified_status():
    from shoir_target_engines import build_kaizen_a3_record

    required = dict(
        title="Improve yield",
        problem_statement="Yield below target",
        metric_name="Yield",
        unit="percent",
        baseline_value=80,
        target_value=90,
        root_cause_hypothesis="Cause pending review",
        baseline_evidence="baseline-quality-20",
        countermeasure="Test revised process settings",
        owner="Quality engineer",
        due_date="2026-11-15",
    )
    with pytest.raises(ValueError, match="differ from baseline"):
        build_kaizen_a3_record(**{**required, "target_value": 80})
    with pytest.raises(ValueError, match="post-change evidence reference"):
        build_kaizen_a3_record(**required, actual_after_value=88, implementation_status="Verified")
    verified = build_kaizen_a3_record(
        **required, actual_after_value=88, implementation_status="Verified",
        post_change_evidence="quality-review-23", review_date="2026-11-20",
    )
    assert verified["outcome_status"] == "HUMAN_REVIEW_RECORDED"
    assert verified["warnings"] == []
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        build_kaizen_a3_record(**{**required, "due_date": "Friday"})


def test_oee_matches_hand_calculated_metrics_and_reconciles_loss_time():
    from shoir_target_engines import calculate_oee

    result = calculate_oee(480, 60, 2, 200, 190, time_unit="minutes")
    assert result["status"] == "CALCULATED"
    assert result["availability_pct"] == pytest.approx(87.5)
    assert result["performance_pct"] == pytest.approx(400 / 420 * 100)
    assert result["quality_pct"] == pytest.approx(95.0)
    assert result["oee_pct"] == pytest.approx(79.1666666667)
    assert result["losses"]["Time equivalent (minutes)"].sum() == pytest.approx(100.0)


def test_oee_rejects_invalid_counts_and_flags_over_100_percent_performance():
    from shoir_target_engines import calculate_oee

    with pytest.raises(ValueError, match="less than planned"):
        calculate_oee(60, 60, 1, 10, 10)
    with pytest.raises(ValueError, match="cannot exceed"):
        calculate_oee(60, 5, 1, 10, 11)
    result = calculate_oee(10, 0, 2, 10, 10)
    assert result["status"] == "REVIEW_PERFORMANCE_OR_OEE_ABOVE_100_PERCENT"
    assert result["performance_pct"] == pytest.approx(200.0)
    assert result["oee_pct"] == pytest.approx(200.0)


def test_process_capability_matches_hand_calculated_subgroup_and_overall_sigma():
    from shoir_target_engines import analyze_process_capability

    result = analyze_process_capability([9, 10, 11, 9, 10, 11], 8, 12, subgroup_size=3, unit="mm")
    assert result["status"] == "CALCULATED"
    assert result["mean"] == pytest.approx(10.0)
    assert result["within_sigma"] == pytest.approx(1.0)
    assert result["overall_sigma"] == pytest.approx(math.sqrt(0.8))
    assert result["cp"] == pytest.approx(2 / 3)
    assert result["cpk"] == pytest.approx(2 / 3)
    assert result["pp"] == pytest.approx(4 / (6 * math.sqrt(0.8)))
    assert result["ppk"] == pytest.approx(4 / (6 * math.sqrt(0.8)))


def test_process_capability_rejects_invalid_specs_subgroups_and_zero_variance():
    from shoir_target_engines import analyze_process_capability

    with pytest.raises(ValueError, match="less than upper"):
        analyze_process_capability([1, 2, 3, 4], 5, 5, subgroup_size=2)
    with pytest.raises(ValueError, match="divisible"):
        analyze_process_capability([1, 2, 3, 4, 5], 0, 10, subgroup_size=2)
    with pytest.raises(ValueError, match="variation is zero"):
        analyze_process_capability([1, 1, 1, 1], 0, 10, subgroup_size=2)


def test_inventory_policy_matches_hand_calculated_eoq_safety_stock_and_reorder_point():
    from shoir_target_engines import plan_inventory_policy

    result = plan_inventory_policy(
        10, 2, 4, 50, 2, operating_days_per_year=250, service_factor_z=1.645
    )
    assert result["status"] == "CALCULATED"
    assert result["annual_demand_units"] == pytest.approx(2500)
    assert result["economic_order_quantity_units"] == pytest.approx(math.sqrt(125000))
    assert result["safety_stock_units"] == pytest.approx(6.58)
    assert result["reorder_point_units"] == pytest.approx(46.58)


def test_inventory_policy_rejects_invalid_cost_demand_and_calendar():
    from shoir_target_engines import plan_inventory_policy

    with pytest.raises(ValueError, match="Mean daily demand"):
        plan_inventory_policy(0, 1, 4, 50, 2)
    with pytest.raises(ValueError, match="must both be greater"):
        plan_inventory_policy(10, 1, 4, 0, 2)
    with pytest.raises(ValueError, match="Operating days"):
        plan_inventory_policy(10, 1, 4, 50, 2, operating_days_per_year=0)


def test_carbon_emissions_multiplier_requires_versioned_factor_provenance():
    from shoir_target_engines import calculate_carbon_emissions

    result = calculate_carbon_emissions(
        250, 0.4, activity_unit="kWh", factor_unit="kg CO2e/kWh",
        factor_source="Test reference factor", factor_date="2026-01-01",
        boundary="Scope 2 location-based",
    )
    assert result["status"] == "CALCULATED_FROM_USER_SUPPLIED_FACTOR"
    assert result["emissions_kg_co2e"] == pytest.approx(100.0)
    assert result["emissions_tonnes_co2e"] == pytest.approx(0.1)
    assert "not an audited" in result["warning"]


def test_carbon_emissions_rejects_invalid_amount_factor_date_and_missing_boundary():
    from shoir_target_engines import calculate_carbon_emissions

    args = dict(activity_unit="kWh", factor_unit="kg/kWh", factor_source="source",
                factor_date="2026-01-01", boundary="Scope 2")
    with pytest.raises(ValueError, match="non-negative"):
        calculate_carbon_emissions(-1, 0.4, **args)
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        calculate_carbon_emissions(1, 0.4, **{**args, "factor_date": "tomorrow"})
    with pytest.raises(ValueError, match="boundary are required"):
        calculate_carbon_emissions(1, 0.4, **{**args, "boundary": ""})


def test_engineering_economics_matches_npv_irr_and_simple_payback():
    from shoir_target_engines import analyze_engineering_economics

    result = analyze_engineering_economics([-1000, 600, 600], 10, currency="SAR")
    assert result["status"] == "CALCULATED"
    assert result["npv"] == pytest.approx(100 / 2.42)
    assert result["irr_pct"] == pytest.approx(13.0662386, abs=0.001)
    assert result["irr_status"] == "CALCULATED"
    assert result["simple_payback_periods"] == pytest.approx(5 / 3)
    assert len(result["cash_flow_schedule"]) == 3


def test_engineering_economics_omits_irr_for_nonconventional_cashflows_and_validates_rate():
    from shoir_target_engines import analyze_engineering_economics

    result = analyze_engineering_economics([-100, 230, -132], 10, currency="SAR")
    assert result["irr_pct"] is None
    assert result["irr_status"] == "NOT_CALCULATED_NONCONVENTIONAL_CASH_FLOWS"
    with pytest.raises(ValueError, match="greater than -100"):
        analyze_engineering_economics([-100, 150], -100, currency="SAR")
    with pytest.raises(ValueError, match="numeric values"):
        analyze_engineering_economics([-100, True], 10, currency="SAR")


def test_unit_converter_checks_dimensions_and_converts_temperature():
    from shoir_target_engines import convert_units_or_currency

    assert convert_units_or_currency(100, "cm", "m")["converted_value"] == pytest.approx(1.0)
    assert convert_units_or_currency(0, "°C", "°F")["converted_value"] == pytest.approx(32.0)
    assert convert_units_or_currency(1, "kWh", "MJ")["converted_value"] == pytest.approx(3.6)
    with pytest.raises(ValueError, match="Incompatible dimensions"):
        convert_units_or_currency(1, "kg", "m")


def test_currency_converter_requires_dated_sourced_rate():
    from shoir_target_engines import convert_units_or_currency

    with pytest.raises(ValueError, match="positive exchange rate"):
        convert_units_or_currency(100, "SAR", "USD")
    result = convert_units_or_currency(
        100, "SAR", "USD", exchange_rate=0.2667,
        exchange_rate_date="2026-01-01", exchange_rate_source="Fixture rate",
    )
    assert result["converted_value"] == pytest.approx(26.67)
    assert result["exchange_rate_date"] == "2026-01-01"
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        convert_units_or_currency(1, "SAR", "USD", exchange_rate=0.25,
                                  exchange_rate_date="not-a-date", exchange_rate_source="fixture")


def test_spc_individuals_chart_matches_hand_calculated_limits():
    from shoir_target_engines import analyze_spc_individuals

    result = analyze_spc_individuals([10, 11, 9, 10, 12, 11], unit="mm")
    assert result["status"] == "NO_POINT_OUTSIDE_CALCULATED_LIMITS"
    assert result["mean"] == pytest.approx(10.5)
    assert result["moving_range_average"] == pytest.approx(1.4)
    assert result["estimated_within_sigma"] == pytest.approx(1.4 / 1.128)
    assert result["individuals_ucl"] == pytest.approx(10.5 + 3 * 1.4 / 1.128)
    assert result["moving_range_ucl"] == pytest.approx(3.267 * 1.4)


def test_spc_rejects_insufficient_or_constant_measurements():
    from shoir_target_engines import analyze_spc_individuals

    with pytest.raises(ValueError, match="at least three"):
        analyze_spc_individuals([1, 2])
    with pytest.raises(ValueError, match="Moving-range average is zero"):
        analyze_spc_individuals([5, 5, 5])


def test_quality_cost_reconciles_scrap_rework_and_inspection():
    from shoir_target_engines import analyze_quality_cost_defects

    result = analyze_quality_cost_defects(
        100, 10, 2, 5, 20, 6, 120, currency="SAR", period="Fixture month"
    )
    assert result["defective_rate_pct"] == pytest.approx(10.0)
    assert result["scrap_cost"] == pytest.approx(40.0)
    assert result["rework_cost"] == pytest.approx(30.0)
    assert result["cost_of_poor_quality"] == pytest.approx(190.0)
    assert result["copq_per_produced_unit"] == pytest.approx(1.9)


def test_quality_cost_rejects_overlapping_dispositions():
    from shoir_target_engines import analyze_quality_cost_defects

    with pytest.raises(ValueError, match="cannot exceed the defective"):
        analyze_quality_cost_defects(100, 10, 7, 5, 20, 6, 120)


def test_mtbf_mttr_matches_hand_calculated_reliability_measures():
    from shoir_target_engines import analyze_mtbf_mttr

    result = analyze_mtbf_mttr(600, [2, 1, 3])
    assert result["failure_count"] == 3
    assert result["mtbf_hours"] == pytest.approx(200)
    assert result["mttr_hours"] == pytest.approx(2)
    assert result["steady_state_availability_estimate_pct"] == pytest.approx(200 / 202 * 100)


def test_mtbf_mttr_rejects_invalid_events():
    from shoir_target_engines import analyze_mtbf_mttr

    with pytest.raises(ValueError, match="greater than zero"):
        analyze_mtbf_mttr(0, [1])
    with pytest.raises(ValueError, match="cannot be negative"):
        analyze_mtbf_mttr(10, [1, -0.1])
    with pytest.raises(ValueError, match="at least one"):
        analyze_mtbf_mttr(10, [])


def test_abc_xyz_uses_value_thresholds_and_demand_cv():
    from shoir_target_engines import analyze_abc_xyz_inventory

    result = analyze_abc_xyz_inventory([
        {"sku": "A", "annual_demand": 100, "unit_cost": 8, "period_demand": [8, 10, 12]},
        {"sku": "B", "annual_demand": 50, "unit_cost": 3, "period_demand": [1, 10, 3]},
        {"sku": "C", "annual_demand": 25, "unit_cost": 2, "period_demand": [1, 20, 0]},
    ], currency="SAR")
    df = result["classification"]
    assert result["annual_usage_value_total"] == pytest.approx(1000)
    assert df["SKU"].tolist() == ["A", "B", "C"]
    assert df["ABC"].tolist() == ["A", "B", "C"]
    assert df["XYZ"].tolist() == ["X", "Y", "Z"]
    assert df["ABC/XYZ class"].tolist() == ["A-X", "B-Y", "C-Z"]


def test_abc_xyz_rejects_duplicates_and_inconsistent_history():
    from shoir_target_engines import analyze_abc_xyz_inventory

    duplicate = [
        {"sku": "A", "annual_demand": 1, "unit_cost": 1, "period_demand": [1, 2]},
        {"sku": "a", "annual_demand": 1, "unit_cost": 1, "period_demand": [2, 3]},
    ]
    with pytest.raises(ValueError, match="Duplicate SKU"):
        analyze_abc_xyz_inventory(duplicate)
    mismatch = [
        {"sku": "A", "annual_demand": 1, "unit_cost": 1, "period_demand": [1, 2]},
        {"sku": "B", "annual_demand": 1, "unit_cost": 2, "period_demand": [1, 2, 3]},
    ]
    with pytest.raises(ValueError, match="same number"):
        analyze_abc_xyz_inventory(mismatch)


# Additional golden cases for methods integrated into the 100-tool Workbench.

def test_production_line_balancer_respects_precedence_and_cycle_time():
    from shoir_target_engines import balance_production_line

    result = balance_production_line(
        [
            {"task_id": "A", "duration": 2, "predecessors": []},
            {"task_id": "B", "duration": 3, "predecessors": []},
            {"task_id": "C", "duration": 2, "predecessors": ["A"]},
            {"task_id": "D", "duration": 1, "predecessors": ["B", "C"]},
        ],
        5,
        time_unit="minutes",
    )
    assert result["status"] == "FEASIBLE_HEURISTIC"
    assert result["station_count"] == 2
    assert result["theoretical_minimum_stations"] == 2
    assert result["efficiency_pct"] == pytest.approx(80)
    assignments = result["task_assignment"].set_index("Task")["Station"].to_dict()
    assert assignments["A"] <= assignments["C"]
    assert assignments["B"] <= assignments["D"]
    assert assignments["C"] <= assignments["D"]
    assert result["precedence_validated"] is True
    assert result["station_summary"]["Work content (minutes)"].max() <= 5


def test_production_line_balancer_rejects_cycles_unknown_predecessors_and_oversized_tasks():
    from shoir_target_engines import balance_production_line

    with pytest.raises(ValueError, match="cycle"):
        balance_production_line(
            [
                {"task_id": "A", "duration": 1, "predecessors": ["B"]},
                {"task_id": "B", "duration": 1, "predecessors": ["A"]},
            ],
            5,
        )
    with pytest.raises(ValueError, match="unknown predecessor"):
        balance_production_line([{"task_id": "A", "duration": 1, "predecessors": ["X"]}], 5)
    result = balance_production_line([{"task_id": "A", "duration": 6}], 5)
    assert result["status"] == "INFEASIBLE"
    assert result["station_count"] is None


def test_bottleneck_capacity_screen_identifies_shortfall_and_reconciles_processes():
    from shoir_target_engines import analyze_bottleneck_capacity

    result = analyze_bottleneck_capacity(
        [
            {"process": "Cut", "capacity": 110},
            {"process": "Weld", "capacity": 80},
            {"process": "Pack", "capacity": 95},
        ],
        90,
        period_label="units/shift",
    )
    assert result["status"] == "CAPACITY_SHORTFALL"
    assert result["bottleneck_process"] == "Weld"
    assert result["bottleneck_capacity_per_period"] == pytest.approx(80)
    assert result["capacity_shortfall_per_period"] == pytest.approx(10)
    assert result["minimum_recovery_capacity_required"] == pytest.approx(10)
    assert result["process_capacity_table"]["Bottleneck"].sum() == 1
    with pytest.raises(ValueError, match="greater than zero"):
        analyze_bottleneck_capacity([{"process": "Cut", "capacity": 10}], 0)


def test_vsm_first_pass_lead_time_uses_explicit_wip_flow_and_batch_assumptions():
    from shoir_target_engines import build_value_stream_map

    result = build_value_stream_map(
        [
            {"step": "Machine", "cycle_time": 1, "changeover_time": 20, "batch_size": 10,
             "uptime_pct": 100, "wip_units": 25, "value_added": True},
            {"step": "Inspect", "cycle_time": 2, "changeover_time": 0, "batch_size": 1,
             "uptime_pct": 50, "wip_units": 0, "value_added": False},
        ],
        demand_units_per_period=100,
        available_time_per_period=400,
        time_unit="minutes",
    )
    assert result["status"] == "CALCULATED_ESTIMATE"
    assert result["required_flow_rate_units_per_time"] == pytest.approx(0.25)
    assert result["total_queue_lead_time"] == pytest.approx(100)
    assert result["availability_adjusted_process_time"] == pytest.approx(7)
    assert result["estimated_total_lead_time"] == pytest.approx(107)
    assert result["value_added_time"] == pytest.approx(1)
    assert result["value_added_share_pct"] == pytest.approx(1 / 107 * 100)
    with pytest.raises(ValueError, match="Uptime percentage"):
        build_value_stream_map([{"step": "A", "cycle_time": 1, "uptime_pct": 0}], 10, 100)


def test_fmea_rpn_ranking_keeps_severity_override_visible():
    from shoir_target_engines import analyze_fmea

    result = analyze_fmea([
        {"failure_mode": "Rare catastrophic", "severity": 9, "occurrence": 1, "detection": 2},
        {"failure_mode": "Frequent nuisance", "severity": 5, "occurrence": 5, "detection": 5},
    ])
    assert result["status"] == "CALCULATED_REQUIRES_ENGINEERING_REVIEW"
    assert result["highest_rpn"] == 125
    assert result["high_severity_count"] == 1
    first = result["failure_modes"].iloc[0]
    assert first["Failure mode"] == "Rare catastrophic"
    assert first["RPN (S×O×D)"] == 18
    assert bool(first["Severity ≥ 9 review"])
    with pytest.raises(ValueError, match="whole number from 1 through 10"):
        analyze_fmea([{"failure_mode": "Bad score", "severity": 11, "occurrence": 1, "detection": 1}])


def test_mm1_queue_model_matches_analytical_values_and_rejects_instability():
    from shoir_target_engines import analyze_mm1_queue

    result = analyze_mm1_queue(4, 6, time_unit="hours")
    assert result["status"] == "STABLE_M_M_1"
    assert result["utilization_pct"] == pytest.approx(100 * 4 / 6)
    assert result["mean_customers_in_system"] == pytest.approx(2)
    assert result["mean_customers_waiting"] == pytest.approx(4 / 3)
    assert result["mean_time_in_system"] == pytest.approx(0.5)
    assert result["mean_waiting_time_in_queue"] == pytest.approx(1 / 3)
    with pytest.raises(ValueError, match="unstable"):
        analyze_mm1_queue(6, 6)
    with pytest.raises(ValueError, match="greater than zero"):
        analyze_mm1_queue(2, 0)


def test_cost_variance_reconciles_price_and_usage_components_against_actual_cost():
    from shoir_target_engines import analyze_industrial_cost_variance

    result = analyze_industrial_cost_variance(
        standard_quantity_per_unit=2,
        actual_output_units=100,
        actual_input_quantity=210,
        standard_unit_cost=5,
        actual_unit_cost=6,
        currency="SAR",
        period="2026-09",
    )
    assert result["standard_quantity_allowed"] == pytest.approx(200)
    assert result["standard_cost_for_actual_output"] == pytest.approx(1000)
    assert result["actual_input_cost"] == pytest.approx(1260)
    assert result["price_variance"] == pytest.approx(210)
    assert result["usage_variance"] == pytest.approx(50)
    assert result["total_variance"] == pytest.approx(260)
    assert result["price_variance"] + result["usage_variance"] == pytest.approx(result["total_variance"])
    assert result["variance_reconciles"] is True
    with pytest.raises(ValueError, match="cannot be negative"):
        analyze_industrial_cost_variance(2, 100, 210, 5, -1)


def test_roi_evidence_calculation_never_self_certifies_claimed_savings():
    from shoir_target_engines import calculate_roi_evidence

    result = calculate_roi_evidence(
        1000, 700, 100, currency="SAR",
        measurement_window="2026-Q3",
        baseline_evidence="baseline.csv#row-1",
        outcome_evidence="outcome.csv#row-1",
        verifier="Engineering reviewer",
    )
    assert result["gross_cost_reduction"] == pytest.approx(300)
    assert result["net_benefit_after_implementation"] == pytest.approx(200)
    assert result["roi_pct"] == pytest.approx(200)
    assert result["break_even_or_better"] is True
    assert result["verification_status"] == "REQUIRES_HUMAN_VERIFICATION"
    assert result["missing_verification_items"] == []
    without_evidence = calculate_roi_evidence(100, 120, 0)
    assert without_evidence["roi_pct"] is None
    assert without_evidence["verification_status"] == "REQUIRES_HUMAN_VERIFICATION"
    assert without_evidence["missing_verification_items"]


def test_preventive_maintenance_planner_orders_overdue_tasks_and_validates_dates():
    from shoir_target_engines import plan_preventive_maintenance

    result = plan_preventive_maintenance(
        [
            {"asset": "CNC-01", "task": "Lubrication", "last_completed_date": "2026-10-01",
             "interval_days": 20, "estimated_duration_hours": 1.5, "required_skill": "Mechanical"},
            {"asset": "CNC-01", "task": "Inspection", "last_completed_date": "2026-10-20",
             "interval_days": 7, "estimated_duration_hours": 1, "required_skill": "Technician"},
        ],
        "2026-10-24",
    )
    assert result["status"] == "PLAN_CALCULATED"
    assert result["overdue_task_count"] == 1
    assert result["due_within_7_days_count"] == 1
    assert result["total_estimated_labor_hours"] == pytest.approx(2.5)
    assert result["maintenance_plan"].iloc[0]["Maintenance task"] == "Lubrication"
    assert result["maintenance_plan"].iloc[0]["Days until due"] == -3
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        plan_preventive_maintenance([{"asset": "A", "task": "PM", "last_completed_date": "bad", "interval_days": 10}], "2026-10-24")


def test_hazard_screen_scores_and_separates_residual_risk_and_missing_controls():
    from shoir_target_engines import assess_job_hazards

    result = assess_job_hazards([
        {"hazard": "Moving conveyor", "activity": "Clearing jam", "severity": 5, "likelihood": 4,
         "controls": "Isolate and lock out", "residual_severity": 5, "residual_likelihood": 1,
         "owner": "Shift supervisor"},
        {"hazard": "Manual handling", "severity": 3, "likelihood": 2},
    ])
    assert result["status"] == "HAZARD_SCREEN_REQUIRES_QUALIFIED_REVIEW"
    assert result["high_screen_score_count"] == 1
    assert result["missing_controls_count"] == 1
    assert result["unassigned_actions_count"] == 1
    first = result["hazard_register"].iloc[0]
    assert first["Hazard"] == "Moving conveyor"
    assert first["Initial risk score"] == 20
    assert first["Residual risk score"] == 5
    assert result["hazard_register"].iloc[1]["Residual risk score"] is None or pd.isna(result["hazard_register"].iloc[1]["Residual risk score"])
    with pytest.raises(ValueError, match="whole number from 1 through 5"):
        assess_job_hazards([{"hazard": "Bad rating", "severity": 6, "likelihood": 1}])


def test_one_level_mrp_calculates_net_requirements_lot_multiple_and_release_period():
    from shoir_target_engines import plan_material_requirements

    result = plan_material_requirements(
        [
            {"component": "Screw", "qty_per_parent": 4, "lead_time_periods": 2, "lot_size_multiple": 10},
            {"component": "Bolt", "qty_per_parent": 2, "lead_time_periods": 1},
        ],
        10,
        inventory={
            "Screw": {"on_hand": 20, "scheduled_receipts": 0, "safety_stock": 5},
            "Bolt": {"on_hand": 30, "scheduled_receipts": 0, "safety_stock": 0},
        },
        due_period=0,
    )
    assert result["status"] == "ONE_LEVEL_MRP_CALCULATED"
    assert result["total_gross_component_requirement"] == pytest.approx(60)
    assert result["total_planned_order_receipts"] == pytest.approx(30)
    screw = result["components"].set_index("Component").loc["Screw"]
    assert screw["Gross requirement"] == 40
    assert screw["Net requirement"] == 25
    assert screw["Planned order receipt"] == 30
    assert screw["Planned order release period"] == -2
    assert bool(screw["Release before current period"])
    with pytest.raises(ValueError, match="Duplicate BOM component"):
        plan_material_requirements([{"component": "A", "qty_per_parent": 1}, {"component": "A", "qty_per_parent": 2}], 10)


def test_project_portfolio_score_normalizes_direction_and_weights_reproducibly():
    from shoir_target_engines import score_project_portfolio

    result = score_project_portfolio(
        [
            {"name": "Cost", "weight": 2, "direction": "minimize"},
            {"name": "Quality", "weight": 1, "direction": "maximize"},
        ],
        [
            {"name": "Project A", "scores": {"Cost": 100, "Quality": 70}},
            {"name": "Project B", "scores": {"Cost": 200, "Quality": 90}},
        ],
    )
    assert result["status"] == "SCORED — WEIGHTS ARE USER-DEFINED"
    ranked = result["ranking"]
    assert ranked.iloc[0]["Project"] == "Project A"
    assert ranked.iloc[0]["Weighted score (0–100)"] == pytest.approx(200 / 3)
    assert ranked.iloc[1]["Weighted score (0–100)"] == pytest.approx(100 / 3)
    assert ranked.iloc[0]["Cost score (0–100)"] == pytest.approx(100)
    assert ranked.iloc[0]["Quality score (0–100)"] == pytest.approx(0)
    assert "Sensitivity" in result["warning"]
    with pytest.raises(ValueError, match="greater than zero"):
        score_project_portfolio([{"name": "C", "weight": 0}], [
            {"name": "A", "scores": {"C": 1}}, {"name": "B", "scores": {"C": 2}},
        ])


def test_preventive_maintenance_planner_hazard_register_mrp_and_portfolio_fixtures():
    from shoir_target_engines import (
        plan_preventive_maintenance, assess_job_hazards,
        plan_material_requirements, score_project_portfolio,
    )

    pm = plan_preventive_maintenance([
        {"asset": "CNC-01", "task": "Lubrication", "last_completed_date": "2026-10-01",
         "interval_days": 20, "estimated_duration_hours": 1.5},
        {"asset": "CNC-01", "task": "Inspection", "last_completed_date": "2026-10-20",
         "interval_days": 7, "estimated_duration_hours": 1},
    ], "2026-10-24")
    assert pm["overdue_task_count"] == 1
    assert pm["due_within_7_days_count"] == 1
    assert pm["maintenance_plan"].iloc[0]["Days until due"] == -3

    hazards = assess_job_hazards([
        {"hazard": "Moving conveyor", "severity": 5, "likelihood": 4,
         "controls": "Lockout/tagout", "residual_severity": 5, "residual_likelihood": 1,
         "owner": "Safety lead"},
        {"hazard": "Manual handling", "severity": 3, "likelihood": 2},
    ])
    assert hazards["high_screen_score_count"] == 1
    assert hazards["missing_controls_count"] == 1
    assert hazards["hazard_register"].iloc[0]["Initial risk score"] == 20

    mrp = plan_material_requirements(
        [
            {"component": "Screw", "qty_per_parent": 4, "lead_time_periods": 2, "lot_size_multiple": 10},
            {"component": "Bolt", "qty_per_parent": 2, "lead_time_periods": 1},
        ],
        10,
        inventory={
            "Screw": {"on_hand": 20, "scheduled_receipts": 0, "safety_stock": 5},
            "Bolt": {"on_hand": 30},
        },
    )
    screw = mrp["components"].set_index("Component").loc["Screw"]
    assert screw["Net requirement"] == 25
    assert screw["Planned order receipt"] == 30
    assert screw["Planned order release period"] == -2

    portfolio = score_project_portfolio(
        [{"name": "Cost", "weight": 2, "direction": "minimize"},
         {"name": "Quality", "weight": 1, "direction": "maximize"}],
        [{"name": "A", "scores": {"Cost": 100, "Quality": 70}},
         {"name": "B", "scores": {"Cost": 200, "Quality": 90}}],
    )
    assert portfolio["ranking"].iloc[0]["Project"] == "A"
    assert portfolio["ranking"].iloc[0]["Weighted score (0–100)"] == pytest.approx(200 / 3)


def test_data_join_reports_cardinality_unmatched_rows_and_duplicate_policy():
    from shoir_target_engines import merge_data_tables

    result = merge_data_tables(
        [{"id": 1, "part": "A"}, {"id": 2, "part": "B"}, {"id": 3, "part": "C"}],
        [{"component_id": 1, "cost": 10}, {"component_id": 3, "cost": 30}, {"component_id": 4, "cost": 40}],
        "id", "component_id", join_type="outer",
    )
    assert result["status"] == "JOIN_COMPLETED"
    assert result["output_rows"] == 4
    assert result["matched_output_rows"] == 2
    assert result["left_only_output_rows"] == 1
    assert result["right_only_output_rows"] == 1
    assert result["joined_table"]["part"].isna().sum() == 1
    with pytest.raises(ValueError, match="Duplicate join keys"):
        merge_data_tables(
            [{"id": 1}, {"id": 1}],
            [{"id": 1, "v": 2}],
            "id", "id", duplicate_policy="reject",
        )
    with pytest.raises(ValueError, match="exceeding"):
        merge_data_tables([{"id": i} for i in range(3)], [{"id": i} for i in range(3)], "id", "id", max_output_rows=2)


def test_time_series_processor_normalizes_timezone_and_reports_gap_and_resample():
    from shoir_target_engines import process_time_series

    result = process_time_series(
        [
            {"timestamp": "2026-01-01 00:00:00", "count": 1, "energy": 2.0},
            {"timestamp": "2026-01-01 02:00:00", "count": 3, "energy": 6.0},
        ],
        "timestamp",
        timezone_name="Asia/Riyadh",
        expected_interval="1h",
        resample_frequency="1h",
        aggregation="mean",
    )
    assert result["status"] == "TIME_SERIES_PROCESSED"
    assert result["input_rows"] == 2
    assert result["output_rows"] == 3
    assert result["gap_count"] == 1
    assert result["expected_missing_observations"] == 1
    assert str(result["processed_series"]["timestamp"].dt.tz) == "UTC"
    assert pd.isna(result["processed_series"].iloc[1]["count"])
    with pytest.raises(ValueError, match="missing values"):
        process_time_series([{"timestamp": None, "count": 1}], "timestamp")


def test_synthetic_industrial_data_is_reproducible_and_explicitly_labelled():
    from shoir_target_engines import generate_synthetic_industrial_data

    a = generate_synthetic_industrial_data(25, seed=7)
    b = generate_synthetic_industrial_data(25, seed=7)
    assert a["status"] == "SYNTHETIC_DATA_GENERATED"
    assert a["data_provenance"] == "SYNTHETIC"
    assert a["row_count"] == 25
    assert a["synthetic_dataset"]["total_output_units"].tolist() == b["synthetic_dataset"]["total_output_units"].tolist()
    assert set(a["synthetic_dataset"]["data_provenance"]) == {"SYNTHETIC"}
    with pytest.raises(ValueError, match="between 0 and 100"):
        generate_synthetic_industrial_data(5, defect_rate_pct=101)


def test_acceptance_sampling_plan_meets_stated_binomial_producer_consumer_risks():
    from scipy.stats import binom
    from shoir_target_engines import plan_acceptance_sampling

    result = plan_acceptance_sampling(0.01, 0.10, producer_risk=0.05, consumer_risk=0.10, max_sample_size=500)
    assert result["status"] == "PLAN_FOUND"
    n = result["sample_size"]
    c = result["acceptance_number"]
    assert n > 0 and c >= 0
    assert binom.cdf(c, n, 0.01) >= 0.95
    assert binom.cdf(c, n, 0.10) <= 0.10
    assert result["probability_of_acceptance_at_aql"] == pytest.approx(binom.cdf(c, n, 0.01))
    assert plan_acceptance_sampling(0.01, 0.10, max_sample_size=1)["status"] == "NO_PLAN_WITHIN_SEARCH_LIMIT"


def test_process_mining_reconstructs_variants_transitions_and_case_duration():
    from shoir_target_engines import analyze_process_mining

    result = analyze_process_mining([
        {"case_id": "1", "activity": "A", "timestamp": "2026-01-01T00:00:00Z"},
        {"case_id": "1", "activity": "B", "timestamp": "2026-01-01T02:00:00Z"},
        {"case_id": "2", "activity": "A", "timestamp": "2026-01-01T00:00:00Z"},
        {"case_id": "2", "activity": "C", "timestamp": "2026-01-01T01:00:00Z"},
        {"case_id": "2", "activity": "B", "timestamp": "2026-01-01T03:00:00Z"},
    ])
    assert result["status"] == "EVENT_LOG_ANALYZED"
    assert result["case_count"] == 2
    assert result["event_count"] == 5
    assert result["variant_count"] == 2
    assert result["median_case_duration_seconds"] == pytest.approx(9000)
    transitions = result["directly_follows"].set_index("Transition")["Occurrences"].to_dict()
    assert transitions == {"A → B": 1, "A → C": 1, "C → B": 1}
    with pytest.raises(ValueError, match="missing required columns"):
        analyze_process_mining([{"case_id": "1", "activity": "A"}])


def test_water_waste_flow_balance_reconciles_and_refuses_mixed_units():
    from shoir_target_engines import analyze_water_waste_efficiency

    result = analyze_water_waste_efficiency([
        {"process": "Wash", "input_quantity": 100, "product_output_quantity": 85,
         "waste_quantity": 15, "unit": "L", "period": "2026-09"},
        {"process": "Rinse", "input_quantity": 50, "product_output_quantity": 45,
         "waste_quantity": 5, "unit": "L", "period": "2026-09"},
    ])
    assert result["status"] == "FLOW_BALANCE_CALCULATED"
    assert result["total_input_quantity"] == pytest.approx(150)
    assert result["total_product_output_quantity"] == pytest.approx(130)
    assert result["total_waste_quantity"] == pytest.approx(20)
    assert result["total_unreconciled_balance"] == pytest.approx(0)
    assert result["all_process_balances_close"] is True
    assert result["overall_output_yield_pct"] == pytest.approx(130 / 150 * 100)
    with pytest.raises(ValueError, match="same unit"):
        analyze_water_waste_efficiency([
            {"process": "Wash", "input_quantity": 100, "product_output_quantity": 80, "waste_quantity": 20, "unit": "L"},
            {"process": "Cut", "input_quantity": 100, "product_output_quantity": 90, "waste_quantity": 10, "unit": "kg"},
        ])


def test_water_waste_processor_does_not_combine_unlike_measurement_periods():
    from shoir_target_engines import analyze_water_waste_efficiency

    result = analyze_water_waste_efficiency([
        {"process": "Wash", "input_quantity": 100, "product_output_quantity": 80,
         "waste_quantity": 20, "unit": "L", "period": "2026-08"},
        {"process": "Rinse", "input_quantity": 50, "product_output_quantity": 40,
         "waste_quantity": 10, "unit": "L", "period": "2026-09"},
    ])
    assert result["status"] == "FLOW_BALANCE_CALCULATED_PER_PROCESS_ONLY"
    assert result["total_input_quantity"] is None
    assert result["overall_output_yield_pct"] is None
    assert result["process_balance_table"]["Balance closes"].all()


def test_weibull_fit_reports_shape_scale_percentiles_and_censoring_limit():
    from shoir_target_engines import analyze_weibull_reliability

    probabilities = np.linspace(0.05, 0.95, 40)
    observations = [1000 * (-np.log(1 - p)) ** 0.5 for p in probabilities]
    result = analyze_weibull_reliability(observations)
    assert result["status"] == "WEIBULL_FIT_UNCENSORED_DATA"
    assert result["sample_size"] == 40
    assert result["shape_beta"] > 0
    assert result["scale_eta"] > 0
    assert 1.3 < result["shape_beta"] < 2.7
    assert 700 < result["scale_eta"] < 1300
    assert result["B10_life"] == pytest.approx(result["scale_eta"] * (-np.log(0.90)) ** (1 / result["shape_beta"]))
    assert "censored" in result["warning"].lower()
    with pytest.raises(ValueError, match="at least five"):
        analyze_weibull_reliability([1, 2, 3, 4])


def test_spare_parts_criticality_reorder_screen_reconciles_stock_and_lead_time():
    from shoir_target_engines import analyze_spare_parts_criticality

    result = analyze_spare_parts_criticality([
        {"part": "Bearing", "average_daily_demand": 2, "lead_time_days": 5,
         "safety_stock": 10, "on_hand": 5, "scheduled_receipts": 0, "unit_cost": 20, "criticality_score": 5},
        {"part": "Gasket", "average_daily_demand": 0.5, "lead_time_days": 2,
         "safety_stock": 1, "on_hand": 10, "scheduled_receipts": 0, "unit_cost": 3, "criticality_score": 2},
    ])
    assert result["parts_below_reorder_point"] == 1
    bearing = result["priority_table"].set_index("Part").loc["Bearing"]
    assert bearing["Reorder point"] == pytest.approx(20)
    assert bearing["Stock position"] == pytest.approx(5)
    assert bearing["Suggested replenishment quantity"] == pytest.approx(15)
    assert bearing["Replenishment value"] == pytest.approx(300)
    assert result["estimated_replenishment_value"] == pytest.approx(300)
    with pytest.raises(ValueError, match="Criticality score"):
        analyze_spare_parts_criticality([{"part": "Bad", "lead_time_days": 1, "criticality_score": 9}])


def test_safety_incident_trends_calculate_rates_with_period_specific_denominators():
    from shoir_target_engines import analyze_safety_incident_trends

    result = analyze_safety_incident_trends([
        {"period": "2026-Q1", "incidents_by_category": {"Slip": 2, "Cut": 1}, "work_hours": 20000, "lost_workdays": 4},
        {"period": "2026-Q2", "incidents_by_category": {"Slip": 1, "Fatigue": 1}, "work_hours": 40000, "lost_workdays": 2},
    ])
    assert result["total_incidents"] == 5
    assert result["total_lost_workdays"] == pytest.approx(6)
    trend = result["period_trend"].set_index("Period")
    assert trend.loc["2026-Q1", "Incident rate per base hours"] == pytest.approx(30)
    assert trend.loc["2026-Q2", "Incident rate per base hours"] == pytest.approx(10)
    assert result["category_breakdown"]["Incidents"].sum() == 5
    with pytest.raises(ValueError, match="greater than zero"):
        analyze_safety_incident_trends([{"period": "Q", "incidents_by_category": {"Slip": 1}, "work_hours": 0}])


def test_warehouse_slotting_respects_compatibility_and_capacity():
    from shoir_target_engines import optimize_warehouse_slotting

    result = optimize_warehouse_slotting(
        [
            {"sku": "SKU-A", "picks_per_day": 10, "storage_units": 4, "compatibility_group": "food", "current_distance_m": 10},
            {"sku": "SKU-B", "picks_per_day": 4, "storage_units": 9, "compatibility_group": "chemical", "current_distance_m": 20},
        ],
        [
            {"slot_id": "near-food", "distance_m": 2, "capacity_units": 5, "compatibility_group": "food"},
            {"slot_id": "near-chemical", "distance_m": 3, "capacity_units": 10, "compatibility_group": "chemical"},
            {"slot_id": "far-general", "distance_m": 8, "capacity_units": 10, "compatibility_group": "*"},
        ],
    )
    assert result["status"] == "SLOTTING_HEURISTIC_COMPLETE"
    assert result["assigned_count"] == 2
    assigned = result["assignments"].set_index("SKU")
    assert assigned.loc["SKU-A", "Slot"] == "near-food"
    assert assigned.loc["SKU-B", "Slot"] == "near-chemical"
    assert (assigned["Required storage units"] <= assigned["Slot capacity units"]).all()
    assert result["estimated_round_trip_distance_change_m_per_day"] == pytest.approx(-296)
    with pytest.raises(ValueError, match="positive"):
        optimize_warehouse_slotting([{"sku": "A", "picks_per_day": 1, "storage_units": 0}], [{"slot_id": "S", "distance_m": 1, "capacity_units": 2}])


def test_linear_task_resource_assignment_finds_minimum_cost_and_reports_shortage():
    from shoir_target_engines import optimize_task_resource_assignment

    result = optimize_task_resource_assignment(
        ["Task A", "Task B", "Task C"],
        ["Worker 1", "Worker 2", "Worker 3"],
        [[9, 2, 7], [6, 4, 3], [5, 8, 1]],
    )
    assert result["status"] == "OPTIMAL_ONE_TO_ONE_ASSIGNMENT"
    assert result["total_assignment_cost"] == pytest.approx(9)
    assert result["assigned_count"] == 3
    shortage = optimize_task_resource_assignment(["A", "B"], ["R1"], [[1], [2]])
    assert shortage["status"] == "PARTIAL_ASSIGNMENT_NEEDS_MORE_RESOURCES"
    assert len(shortage["unassigned_tasks"]) == 1
    with pytest.raises(ValueError, match="dimensions"):
        optimize_task_resource_assignment(["A", "B"], ["R1"], [[1, 2]])


def test_energy_scenario_comparison_ranks_intensity_without_claiming_live_control():
    from shoir_target_engines import compare_energy_performance_scenarios

    result = compare_energy_performance_scenarios(
        {"name": "Baseline", "energy_kwh": 1000, "output_units": 100, "cost_per_kwh": 0.2, "emission_factor_kg_per_kwh": 0.5},
        [
            {"name": "Improved", "energy_kwh": 800, "output_units": 100, "cost_per_kwh": 0.2, "emission_factor_kg_per_kwh": 0.5},
            {"name": "Lower volume", "energy_kwh": 700, "output_units": 70, "cost_per_kwh": 0.2, "emission_factor_kg_per_kwh": 0.5},
        ],
    )
    assert result["status"] == "ENERGY_SCENARIOS_COMPARED"
    assert result["baseline_energy_intensity_kwh_per_unit"] == pytest.approx(10)
    assert result["best_intensity_scenario"] == "Improved"
    improved = result["scenario_comparison"].set_index("Scenario").loc["Improved"]
    assert improved["Energy intensity change vs baseline (%)"] == pytest.approx(-20)
    assert improved["Energy cost change vs baseline (%)"] == pytest.approx(-20)
    assert improved["Emissions change vs baseline (%)"] == pytest.approx(-20)
    assert "does not control plant equipment" in result["warning"]
