"""Independent fixtures and boundary tests for the focused target engines."""
from __future__ import annotations

import math

import numpy as np
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


def test_industrial_field_mapper_suggests_aliases_and_never_auto_confirms_fuzzy_fields():
    from shoir_target_engines import map_industrial_fields

    result = map_industrial_fields(["Timestamp", "Qty", "Defects", "mystery_label"])
    mapped = result["mapping_table"].set_index("Source column")
    assert result["status"] == "FIELD_MAPPING_SUGGESTIONS_READY"
    assert mapped.loc["Timestamp", "Suggested canonical field"] == "timestamp"
    assert mapped.loc["Qty", "Suggested canonical field"] == "quantity"
    assert mapped.loc["Qty", "Mapping status"] == "EXACT_ALIAS — CONFIRM"
    assert mapped.loc["Defects", "Suggested canonical field"] == "defect_count"
    assert mapped.loc["mystery_label", "Mapping status"] == "UNMAPPED — MANUAL REVIEW"
    assert result["warning"].lower().find("confirm each mapping") >= 0
    with pytest.raises(ValueError, match="unknown canonical field"):
        map_industrial_fields(["Qty"], manual_mapping={"Qty": "not-a-field"})


def test_maintenance_backlog_prioritization_respects_skill_and_labor_limits():
    from shoir_target_engines import prioritize_maintenance_backlog

    result = prioritize_maintenance_backlog(
        [
            {"work_order_id": "WO-1", "task": "Critical bearing", "criticality_score": 5,
             "days_until_due": -2, "estimated_hours": 4, "required_skill": "Mechanical"},
            {"work_order_id": "WO-2", "task": "Calibration", "criticality_score": 4,
             "days_until_due": 0, "estimated_hours": 3, "required_skill": "Mechanical"},
            {"work_order_id": "WO-3", "task": "Paint repair", "criticality_score": 2,
             "days_until_due": 5, "estimated_hours": 2, "required_skill": "Electrical"},
        ],
        7,
        available_skills=["Mechanical"],
    )
    assert result["status"] == "BACKLOG_PRIORITIZED"
    assert result["selected_count"] == 2
    assert result["deferred_count"] == 1
    assert result["selected_labor_hours"] == pytest.approx(7)
    selected = set(result["selected_work_orders"]["Work order ID"])
    assert selected == {"WO-1", "WO-2"}
    deferred = result["deferred_work_orders"].set_index("Work order ID")
    assert deferred.loc["WO-3", "Deferral reason"] == "Required skill not in available-skill list"
    with pytest.raises(ValueError, match="whole number from 1 through 5"):
        prioritize_maintenance_backlog([{"work_order_id": "X", "task": "Bad", "criticality_score": 6, "days_until_due": 0, "estimated_hours": 1}], 2)


def test_sop_plan_applies_capacity_limits_and_carries_backlog_forward():
    from shoir_target_engines import reconcile_sop_plan

    result = reconcile_sop_plan(
        [
            {"period": "Jan", "demand": 30, "planned_production": 35, "production_capacity": 30, "scheduled_receipts": 0, "target_safety_stock": 15},
            {"period": "Feb", "demand": 60, "planned_production": 40, "production_capacity": 50, "scheduled_receipts": 10, "target_safety_stock": 20},
        ],
        starting_inventory=20,
    )
    assert result["status"] == "SOP_RECONCILED"
    assert result["total_demand"] == pytest.approx(90)
    assert result["total_production_above_capacity"] == pytest.approx(5)
    periods = result["period_plan"].set_index("Period")
    assert periods.loc["Jan", "Capacity-constrained production"] == pytest.approx(30)
    assert periods.loc["Jan", "Ending inventory"] == pytest.approx(20)
    assert periods.loc["Feb", "Ending inventory"] == pytest.approx(10)
    assert periods.loc["Feb", "Safety stock gap"] == pytest.approx(10)

    deficit = reconcile_sop_plan([
        {"period": "P1", "demand": 40, "planned_production": 10},
        {"period": "P2", "demand": 20, "planned_production": 10},
    ])
    assert deficit["period_plan"].iloc[0]["Ending backlog"] == pytest.approx(30)
    assert deficit["period_plan"].iloc[1]["Opening backlog"] == pytest.approx(30)
    assert deficit["ending_backlog"] == pytest.approx(40)


def test_supplier_scorecard_keeps_incomplete_supplier_unranked():
    from shoir_target_engines import score_supplier_performance

    result = score_supplier_performance(
        [
            {"supplier": "Acme", "scores": {"Delivery": 90, "Quality": 80}, "data_as_of": "2026-Q3", "evidence_reference": "audit-1"},
            {"supplier": "Beta", "scores": {"Delivery": 75}, "data_as_of": "2026-Q3"},
            {"supplier": "Gamma", "scores": {"Delivery": 70, "Quality": 100}, "data_as_of": "2026-Q3", "evidence_reference": "audit-3"},
        ],
        {"Delivery": 0.4, "Quality": 0.6},
    )
    assert result["status"] == "SUPPLIER_SCORECARD_CALCULATED"
    assert result["complete_score_count"] == 2
    assert result["incomplete_score_count"] == 1
    table = result["scorecard"].set_index("Supplier")
    assert table.loc["Acme", "Composite score (0–100)"] == pytest.approx(84)
    assert table.loc["Gamma", "Composite score (0–100)"] == pytest.approx(88)
    assert pd.isna(table.loc["Beta", "Composite score (0–100)"])
    assert pd.isna(table.loc["Beta", "Rank among complete scores"])
    with pytest.raises(ValueError, match="between 0 and 100"):
        score_supplier_performance([{"supplier": "Bad", "scores": {"Quality": 105}}], {"Quality": 1})


# Additional 100-tool tranche: independent, hand-checkable fixtures.
def test_simple_regression_matches_hand_checked_fixture_and_exposes_assumptions():
    from shoir_target_engines import fit_simple_linear_regression

    result = fit_simple_linear_regression([
        {"x": 1, "y": 2}, {"x": 2, "y": 4},
        {"x": 3, "y": 5}, {"x": 4, "y": 8},
    ])
    assert result["status"] == "CALCULATED"
    assert result["slope"] == pytest.approx(1.9)
    assert result["intercept"] == pytest.approx(0.0)
    assert result["r_squared"] == pytest.approx(1 - 0.7 / 18.75)
    assert len(result["residuals"]) == 4
    assert result["anova_table"].iloc[0]["Sum of squares"] == pytest.approx(18.05)
    assert "Association is not proof of causation" in result["warning"]


def test_simple_regression_rejects_invalid_or_unidentifiable_inputs():
    from shoir_target_engines import fit_simple_linear_regression

    with pytest.raises(ValueError, match="at least three"):
        fit_simple_linear_regression([{"x": 1, "y": 2}, {"x": 2, "y": 3}])
    with pytest.raises(ValueError, match="distinct values"):
        fit_simple_linear_regression([{"x": 1, "y": 2}, {"x": 1, "y": 3}, {"x": 1, "y": 4}])
    with pytest.raises(ValueError, match="Alpha"):
        fit_simple_linear_regression([{"x": 1, "y": 2}, {"x": 2, "y": 3}, {"x": 3, "y": 5}], alpha=1)


def test_one_way_anova_matches_hand_calculated_f_statistic():
    from shoir_target_engines import run_one_way_anova

    result = run_one_way_anova({
        "Line A": [1, 2, 3],
        "Line B": [4, 5, 6],
        "Line C": [7, 8, 9],
    })
    assert result["f_statistic"] == pytest.approx(27.0)
    assert result["df_between"] == 2
    assert result["df_within"] == 6
    assert result["eta_squared"] == pytest.approx(54 / 60)
    assert result["p_value"] < 0.01
    assert result["decision"] == "REJECT_EQUAL_MEANS_NULL"


def test_one_way_anova_rejects_incomplete_and_zero_within_variance_cases():
    from shoir_target_engines import run_one_way_anova

    with pytest.raises(ValueError, match="at least two"):
        run_one_way_anova({"A": [1, 2]})
    with pytest.raises(ValueError, match="at least 2 observations"):
        run_one_way_anova({"A": [1, 2], "B": [3]})
    with pytest.raises(ValueError, match="variance is zero"):
        run_one_way_anova({"A": [1, 1], "B": [2, 2]})


def test_welch_t_test_matches_group_means_and_interval_direction():
    from shoir_target_engines import run_welch_t_test

    result = run_welch_t_test([2, 3, 4, 5], [8, 9, 10, 11])
    assert result["mean_a"] == pytest.approx(3.5)
    assert result["mean_b"] == pytest.approx(9.5)
    assert result["mean_difference_a_minus_b"] == pytest.approx(-6.0)
    assert result["t_statistic"] < 0
    assert result["p_value"] < 0.01
    lower, upper = result["mean_difference_confidence_interval"]
    assert lower < upper < 0
    assert "does not assume equal population variances" in result["assumptions"]


def test_welch_t_test_rejects_zero_variance_and_invalid_alpha():
    from shoir_target_engines import run_welch_t_test

    with pytest.raises(ValueError, match="zero estimated uncertainty"):
        run_welch_t_test([1, 1, 1], [2, 2, 2])
    with pytest.raises(ValueError, match="strictly between"):
        run_welch_t_test([1, 2], [3, 4], alpha=0)


def test_demand_forecast_baselines_use_chronological_holdout_without_leakage():
    from shoir_target_engines import forecast_demand_baselines

    result = forecast_demand_baselines(
        [10, 12, 13, 15, 17, 20, 23, 25, 26, 28],
        holdout_periods=3, horizon=2, moving_average_window=3,
    )
    assert result["selected_model"] == "Naive last value"
    assert result["training_count"] == 7
    assert result["holdout_count"] == 3
    backtest = result["backtest"]
    assert backtest["Observed demand"].tolist() == [25, 26, 28]
    assert backtest["Naive last value"].tolist() == [23, 23, 23]
    assert result["metrics"].iloc[0]["Holdout MAE"] == pytest.approx(10 / 3)
    assert result["forecast"]["Forecast"].tolist() == [28, 28]
    assert "prediction intervals" in result["warning"]


def test_demand_forecasting_rejects_short_or_nonfinite_history():
    from shoir_target_engines import forecast_demand_baselines

    with pytest.raises(ValueError, match="at least 5"):
        forecast_demand_baselines([1, 2, 3, 4])
    with pytest.raises(ValueError, match="finite number"):
        forecast_demand_baselines([1, 2, float("nan"), 4, 5])
    with pytest.raises(ValueError, match="Holdout periods"):
        forecast_demand_baselines([1, 2, 3, 4, 5], holdout_periods=3)


def test_monte_carlo_fixed_components_reconcile_and_seed_is_reproducible():
    from shoir_target_engines import simulate_monte_carlo_net_value

    fixed = simulate_monte_carlo_net_value([
        {"name": "Benefit", "role": "benefit", "distribution": "constant", "value": 100},
        {"name": "Cost", "role": "cost", "distribution": "constant", "value": 30},
    ], iterations=1000, seed=7, output_unit="SAR")
    assert fixed["mean"] == pytest.approx(70)
    assert fixed["standard_deviation"] == pytest.approx(0)
    assert fixed["probability_negative_pct"] == pytest.approx(0)
    assert fixed["percentiles"]["50"] == pytest.approx(70)
    assert fixed["sample_outcomes"]["Net outcome (SAR)"].nunique() == 1

    components = [
        {"name": "Benefit", "role": "benefit", "distribution": "normal", "mean": 100, "sd": 10},
        {"name": "Cost", "role": "cost", "distribution": "uniform", "low": 20, "high": 30},
    ]
    a = simulate_monte_carlo_net_value(components, iterations=1000, seed=123, output_unit="units")
    b = simulate_monte_carlo_net_value(components, iterations=1000, seed=123, output_unit="units")
    pd.testing.assert_frame_equal(a["sample_outcomes"], b["sample_outcomes"])
    assert a["seed"] == 123
    assert a["iterations"] == 1000
    assert "independently" in a["assumptions"]


def test_monte_carlo_rejects_invalid_distribution_and_resource_bounds():
    from shoir_target_engines import simulate_monte_carlo_net_value

    with pytest.raises(ValueError, match="high must be greater than low"):
        simulate_monte_carlo_net_value([
            {"name": "Bad", "role": "benefit", "distribution": "uniform", "low": 5, "high": 5}
        ])
    with pytest.raises(ValueError, match="role must be benefit or cost"):
        simulate_monte_carlo_net_value([
            {"name": "Bad", "role": "income", "distribution": "constant", "value": 5}
        ])
    with pytest.raises(ValueError, match="Iterations"):
        simulate_monte_carlo_net_value([
            {"name": "Known", "role": "benefit", "distribution": "constant", "value": 5}
        ], iterations=10)


def test_crossed_gage_rr_matches_balanced_fixture_and_reports_tolerance():
    from shoir_target_engines import analyze_crossed_gage_rr

    records = []
    values = {
        ("P1", "A"): [9.8, 9.9],
        ("P1", "B"): [10.0, 10.1],
        ("P2", "A"): [11.8, 11.9],
        ("P2", "B"): [12.0, 12.1],
    }
    for (part, operator), measurements in values.items():
        for trial, measurement in enumerate(measurements, start=1):
            records.append({"part": part, "operator": operator, "trial": trial, "measurement": measurement})
    result = analyze_crossed_gage_rr(records, tolerance=6.0)
    assert result["status"] == "CROSSED_GAGE_RR_SCREENED"
    assert result["part_count"] == 2
    assert result["operator_count"] == 2
    assert result["repeat_count"] == 2
    assert result["repeatability_sd"] == pytest.approx(math.sqrt(0.005))
    assert result["reproducibility_sd"] == pytest.approx(math.sqrt(0.02))
    assert result["gage_rr_percent_variance"] == pytest.approx(0.025 / 2.025 * 100)
    assert result["percent_tolerance"] == pytest.approx(math.sqrt(0.025) * 100)
    assert result["number_of_distinct_categories"] == 12
    assert "not automatically a compliant/certified MSA" in result["warning"]


def test_crossed_gage_rr_rejects_unbalanced_or_duplicate_observations():
    from shoir_target_engines import analyze_crossed_gage_rr

    records = [
        {"part": "P1", "operator": "A", "trial": 1, "measurement": 1.0},
        {"part": "P1", "operator": "A", "trial": 2, "measurement": 1.1},
        {"part": "P1", "operator": "B", "trial": 1, "measurement": 1.2},
        {"part": "P1", "operator": "B", "trial": 2, "measurement": 1.3},
        {"part": "P2", "operator": "A", "trial": 1, "measurement": 2.0},
        {"part": "P2", "operator": "A", "trial": 2, "measurement": 2.1},
        {"part": "P2", "operator": "B", "trial": 1, "measurement": 2.2},
    ]
    with pytest.raises(ValueError, match="balanced"):
        analyze_crossed_gage_rr(records)
    with pytest.raises(ValueError, match="Duplicate"):
        analyze_crossed_gage_rr(records + [records[0]])


def test_full_factorial_doe_matches_hand_calculated_effects_and_inference():
    from shoir_target_engines import analyze_full_factorial_2level

    observations = [
        {"A": -1, "B": -1, "response": 6.4},
        {"A": -1, "B": -1, "response": 6.6},
        {"A": -1, "B": 1, "response": 9.4},
        {"A": -1, "B": 1, "response": 9.6},
        {"A": 1, "B": -1, "response": 7.4},
        {"A": 1, "B": -1, "response": 7.6},
        {"A": 1, "B": 1, "response": 16.4},
        {"A": 1, "B": 1, "response": 16.6},
    ]
    result = analyze_full_factorial_2level(observations, response_field="response", factor_fields=["A", "B"])
    assert result["status"] == "FACTORIAL_ANALYZED"
    assert result["run_count"] == 8
    assert result["residual_degrees_of_freedom"] == 4
    effects = result["effects"].set_index("Term")
    assert effects.loc["A", "Estimated effect (high − low)"] == pytest.approx(4.0)
    assert effects.loc["B", "Estimated effect (high − low)"] == pytest.approx(6.0)
    assert effects.loc["A × B", "Estimated effect (high − low)"] == pytest.approx(3.0)
    assert effects["p-value"].notna().all()
    assert "run order randomization" in result["assumptions"]


def test_full_factorial_doe_rejects_missing_combinations_and_non_coded_levels():
    from shoir_target_engines import analyze_full_factorial_2level

    with pytest.raises(ValueError, match="factor combination is missing"):
        analyze_full_factorial_2level([
            {"A": -1, "B": -1, "response": 1},
            {"A": -1, "B": 1, "response": 2},
            {"A": 1, "B": -1, "response": 3},
        ], response_field="response", factor_fields=["A", "B"])
    with pytest.raises(ValueError, match="coded levels"):
        analyze_full_factorial_2level([
            {"A": -1, "B": -1, "response": 1},
            {"A": -1, "B": 1, "response": 2},
            {"A": 1, "B": -1, "response": 3},
            {"A": 2, "B": 1, "response": 4},
        ], response_field="response", factor_fields=["A", "B"])


def test_anomaly_screening_flags_robust_outlier_and_handles_stable_baseline():
    from shoir_target_engines import detect_equipment_anomalies

    records = [
        {"timestamp": f"2026-10-{day:02d}T00:00:00Z", "value": value}
        for day, value in enumerate([99, 100, 101, 100, 99, 100, 101, 100, 99, 100, 100, 140], start=1)
    ]
    result = detect_equipment_anomalies(records, threshold=3.5)
    assert result["status"] == "ANOMALIES_SCREENED"
    assert result["anomaly_count"] == 1
    assert result["anomaly_rate_pct"] == pytest.approx(100 / 12)
    assert result["anomaly_table"].iloc[0]["Value"] == pytest.approx(140)
    assert result["anomaly_table"].iloc[0]["Anomaly"]
    assert "not a live equipment monitor" in result["warning"]

    flat_records = [{"timestamp": f"2026-10-{day:02d}T00:00:00Z", "value": 10 if day < 8 else 25} for day in range(1, 9)]
    fallback = detect_equipment_anomalies(flat_records)
    assert fallback["anomaly_count"] == 1
    assert "stable-baseline deviation fallback" in fallback["method"].lower()


def test_anomaly_screening_rejects_bad_timestamps_and_duplicate_rows():
    from shoir_target_engines import detect_equipment_anomalies

    with pytest.raises(ValueError, match="at least eight"):
        detect_equipment_anomalies([{"timestamp": "2026-01-01T00:00:00Z", "value": 1}] * 4)
    duplicate_records = [{"timestamp": f"2026-10-{day:02d}T00:00:00Z", "value": day} for day in range(1, 9)]
    duplicate_records[-1]["timestamp"] = duplicate_records[0]["timestamp"]
    with pytest.raises(ValueError, match="Duplicate timestamp"):
        detect_equipment_anomalies(duplicate_records)


def test_mm1_discrete_event_simulation_is_seed_reproducible_and_explicit_about_scope():
    from shoir_target_engines import simulate_mm1_discrete_event

    first = simulate_mm1_discrete_event(0.6, 0.8, jobs=1000, replications=4, warmup_fraction=0.1, seed=17, time_unit="minutes")
    second = simulate_mm1_discrete_event(0.6, 0.8, jobs=1000, replications=4, warmup_fraction=0.1, seed=17, time_unit="minutes")
    assert first["status"] == "DISCRETE_EVENT_SIMULATED"
    assert first["stable_queue"] is True
    assert first["warmup_jobs_excluded"] == 100
    assert len(first["replication_summary"]) == 4
    pd.testing.assert_frame_equal(first["replication_summary"], second["replication_summary"])
    assert 0 <= first["replication_summary"]["Server utilization (%)"].min()
    assert first["replication_summary"]["Server utilization (%)"].max() <= 100
    assert first["sample_customer_events"]["Queue wait (minutes)"].ge(0).all()
    assert "single-server fcfs m/m/1" in first["warning"].lower()


def test_mm1_discrete_event_simulation_rejects_invalid_rates_and_warns_on_instability():
    from shoir_target_engines import simulate_mm1_discrete_event

    with pytest.raises(ValueError, match="rates must be greater than zero"):
        simulate_mm1_discrete_event(0, 1, jobs=100)
    overloaded = simulate_mm1_discrete_event(1.1, 1.0, jobs=100, replications=2, seed=2)
    assert overloaded["stable_queue"] is False
    assert "not stable" in overloaded["warning"]


def test_supply_chain_network_transport_optimizes_cost_and_detects_route_disruption():
    from shoir_target_engines import optimize_supply_chain_network

    suppliers = [{"supplier": "S1", "supply_capacity": 60}, {"supplier": "S2", "supply_capacity": 50}]
    sites = [{"site": "A", "demand": 50}, {"site": "B", "demand": 40}]
    routes = [
        {"supplier": "S1", "site": "A", "unit_cost": 2, "capacity": 60, "available": True},
        {"supplier": "S1", "site": "B", "unit_cost": 4, "capacity": 30, "available": True},
        {"supplier": "S2", "site": "A", "unit_cost": 3, "capacity": 30, "available": True},
        {"supplier": "S2", "site": "B", "unit_cost": 1, "capacity": 50, "available": True},
    ]
    result = optimize_supply_chain_network(suppliers, sites, routes, unmet_demand_penalty_per_unit=1000)
    assert result["status"] == "OPTIMAL"
    assert result["total_unmet_demand"] == pytest.approx(0)
    assert result["transport_cost"] == pytest.approx(140)
    assert result["total_units_shipped"] == pytest.approx(90)
    assert result["site_service"]["Service level (%)"].min() == pytest.approx(100)

    disrupted = [dict(route) for route in routes]
    disrupted[-1]["available"] = False
    scenario = optimize_supply_chain_network(suppliers, sites, disrupted, unmet_demand_penalty_per_unit=1000)
    assert scenario["total_unmet_demand"] == pytest.approx(10)
    assert scenario["site_service"].set_index("Site").loc["B", "Unmet demand"] == pytest.approx(10)


def test_supply_chain_network_rejects_bad_route_links_and_negative_costs():
    from shoir_target_engines import optimize_supply_chain_network

    suppliers = [{"supplier": "S1", "supply_capacity": 10}]
    sites = [{"site": "A", "demand": 5}]
    with pytest.raises(ValueError, match="unknown supplier or site"):
        optimize_supply_chain_network(suppliers, sites, [{"supplier": "S2", "site": "A", "unit_cost": 1, "capacity": 5, "available": True}], unmet_demand_penalty_per_unit=10)
    with pytest.raises(ValueError, match="cannot be negative"):
        optimize_supply_chain_network(suppliers, sites, [{"supplier": "S1", "site": "A", "unit_cost": -1, "capacity": 5, "available": True}], unmet_demand_penalty_per_unit=10)


def test_discrete_event_simulation_matches_deterministic_single_station_golden_case():
    from shoir_target_engines import simulate_discrete_event_process

    result = simulate_discrete_event_process(
        [{"station": "Assembly", "servers": 1, "mean_service_time": 2, "service_distribution": "deterministic"}],
        job_count=3,
        mean_interarrival_time=1,
        arrival_distribution="deterministic",
        warmup_jobs=0,
        replications=1,
        random_seed=7,
        time_unit="minutes",
    )
    assert result["status"] == "DISCRETE_EVENT_SIMULATION_COMPLETED"
    assert result["station_count"] == 1
    assert result["job_count"] == 3
    summary = result["metric_summary"].set_index("Metric")
    assert summary.loc["Average flow time (minutes)", "Mean across replications"] == pytest.approx(3.0)
    assert summary.loc["Average total queue wait (minutes)", "Mean across replications"] == pytest.approx(1.0)
    assert summary.loc["Throughput (jobs/minutes)", "Mean across replications"] == pytest.approx(0.5)
    station = result["station_summary"].iloc[0]
    assert station["Average queue wait (minutes)"] == pytest.approx(1.0)
    assert station["Mean utilization across replications (%)"] == pytest.approx(100.0)
    assert result["replication_results"].iloc[0]["Retained jobs"] == 3
    assert "alternate routing" in " ".join(result["limitations"])


def test_discrete_event_simulation_is_reproducible_and_excludes_warmup_jobs():
    from shoir_target_engines import simulate_discrete_event_process

    steps = [
        {"station": "Cut", "servers": 1, "mean_service_time": 1.7, "service_distribution": "exponential"},
        {"station": "Pack", "servers": 2, "mean_service_time": 2.4, "service_distribution": "exponential"},
    ]
    kwargs = dict(
        job_count=30,
        mean_interarrival_time=1.5,
        arrival_distribution="exponential",
        warmup_jobs=4,
        replications=5,
        random_seed=2026,
        time_unit="hours",
    )
    first = simulate_discrete_event_process(steps, **kwargs)
    second = simulate_discrete_event_process(steps, **kwargs)
    pd.testing.assert_frame_equal(first["replication_results"], second["replication_results"])
    pd.testing.assert_frame_equal(first["station_summary"], second["station_summary"])
    assert first["replications"] == 5
    assert (first["replication_results"]["Retained jobs"] == 26).all()
    assert len(first["station_summary"]) == 2
    assert first["station_summary"]["Mean utilization across replications (%)"].between(0, 100).all()
    assert (first["metric_summary"]["P05 across replications"] <= first["metric_summary"]["P95 across replications"]).all()


def test_discrete_event_simulation_rejects_invalid_job_counts_stations_and_distributions():
    from shoir_target_engines import simulate_discrete_event_process

    one_station = [{"station": "Cut", "servers": 1, "mean_service_time": 2}]
    with pytest.raises(ValueError, match="Job count"):
        simulate_discrete_event_process(one_station, job_count=1, mean_interarrival_time=1)
    with pytest.raises(ValueError, match="Warm-up jobs"):
        simulate_discrete_event_process(one_station, job_count=3, mean_interarrival_time=1, warmup_jobs=3)
    with pytest.raises(ValueError, match="greater than zero"):
        simulate_discrete_event_process(one_station, job_count=3, mean_interarrival_time=0)
    with pytest.raises(ValueError, match="Arrival distribution"):
        simulate_discrete_event_process(one_station, job_count=3, mean_interarrival_time=1, arrival_distribution="normal")
    with pytest.raises(ValueError, match="unique; duplicate"):
        simulate_discrete_event_process(
            [{"station": "Cut", "servers": 1, "mean_service_time": 1},
             {"station": "cut", "servers": 1, "mean_service_time": 2}],
            job_count=3, mean_interarrival_time=1,
        )
    with pytest.raises(ValueError, match="Server count"):
        simulate_discrete_event_process([{"station": "Cut", "servers": 0, "mean_service_time": 1}], job_count=3, mean_interarrival_time=1)
    with pytest.raises(ValueError, match="greater than zero"):
        simulate_discrete_event_process([{"station": "Cut", "servers": 1, "mean_service_time": -1}], job_count=3, mean_interarrival_time=1)


def test_solver_diagnostics_returns_optimal_solution_and_independently_checks_constraints():
    from shoir_target_engines import run_solver_diagnostics

    result = run_solver_diagnostics(
        {
            "x": {"low": 0, "up": 10, "category": "Continuous"},
            "y": {"low": 0, "up": 10, "category": "Continuous"},
        },
        {"x": 3, "y": 2},
        [
            {"name": "minimum_output", "coefficients": {"x": 1, "y": 1}, "sense": ">=", "rhs": 4},
            {"name": "balance", "coefficients": {"x": 1, "y": 3}, "sense": ">=", "rhs": 6},
        ],
        direction="minimize",
    )
    assert result["status"] == "OPTIMAL_FEASIBLE"
    assert result["solver_status"] == "Optimal"
    assert result["independent_feasibility_check"] is True
    assert result["objective_value"] == pytest.approx(8.0)
    values = result["variable_values"].set_index("Variable")
    assert values.loc["x", "Value"] == pytest.approx(0.0)
    assert values.loc["y", "Value"] == pytest.approx(4.0)
    assert (values["Bound status"] == "SATISFIED").all()
    constraints = result["constraint_diagnostics"].set_index("Constraint")
    assert constraints.loc["minimum_output", "LHS value"] >= 4
    assert constraints.loc["balance", "LHS value"] >= 6
    assert (constraints["Status"] == "SATISFIED").all()
    assert not result["violations"]


def test_solver_diagnostics_distinguishes_infeasible_unbounded_and_milp_models():
    from shoir_target_engines import run_solver_diagnostics

    infeasible = run_solver_diagnostics(
        {"x": {"low": 0, "up": 1, "category": "Continuous"}},
        {"x": 1},
        [{"name": "impossible", "coefficients": {"x": 1}, "sense": ">=", "rhs": 2}],
    )
    assert infeasible["solver_status"] == "Infeasible"
    assert infeasible["status"] == "INFEASIBLE"
    assert infeasible["objective_value"] is None

    unbounded = run_solver_diagnostics(
        {"x": {"low": 0, "up": None, "category": "Continuous"}},
        {"x": 1},
        [],
        direction="maximize",
    )
    assert unbounded["solver_status"] == "Unbounded"
    assert unbounded["status"] == "UNBOUNDED"
    assert unbounded["objective_value"] is None

    integer = run_solver_diagnostics(
        {"x": {"low": 0, "up": 10, "category": "Integer"}},
        {"x": 1},
        [{"name": "minimum", "coefficients": {"x": 1}, "sense": ">=", "rhs": 2.2}],
        direction="minimize",
    )
    assert integer["status"] == "OPTIMAL_FEASIBLE"
    assert integer["variable_values"].iloc[0]["Value"] == pytest.approx(3.0)
    assert integer["variable_values"].iloc[0]["Category"] == "integer"
    assert integer["independent_feasibility_check"] is True


def test_solver_diagnostics_rejects_invalid_model_schema_and_uses_clear_solver_error_states():
    from shoir_target_engines import run_solver_diagnostics

    with pytest.raises(ValueError, match="unknown variable"):
        run_solver_diagnostics(
            {"x": {"low": 0, "up": 1}},
            {"z": 1},
            [],
        )
    with pytest.raises(ValueError, match="Lower bound exceeds upper"):
        run_solver_diagnostics(
            {"x": {"low": 5, "up": 1}},
            {"x": 1},
            [],
        )
    with pytest.raises(ValueError, match="sense must be"):
        run_solver_diagnostics(
            {"x": {"low": 0, "up": 1}},
            {"x": 1},
            [{"coefficients": {"x": 1}, "sense": "~=", "rhs": 1}],
        )
    with pytest.raises(ValueError, match="time limit"):
        run_solver_diagnostics({"x": {"low": 0}}, {"x": 1}, [], time_limit_seconds=0)


def test_reproducibility_pack_contains_hash_verified_payloads_and_redacts_secrets_and_contact_columns():
    import hashlib
    import io
    import json
    import zipfile
    from shoir_target_engines import build_reproducibility_pack

    result = {
        "status": "ANALYSIS_COMPLETED",
        "seed": 42,
        "api_token": "DO_NOT_EXPORT_TOKEN_abc",
        "metadata": "Bearer DO_NOT_EXPORT_BEARER_xyz",
        "metrics": pd.DataFrame({
            "Station": ["Cutting", "Packing"],
            "email": ["private@example.test", "another@example.test"],
            "Throughput": [12.0, 10.0],
        }),
    }
    inputs = {
        "job_count": 100,
        "random_seed": 42,
        "password": "DO_NOT_EXPORT_PASSWORD_123",
        "notes": "No credentials should survive redaction",
    }
    pack = build_reproducibility_pack(
        "T071",
        "Discrete-Event Simulation",
        result,
        inputs=inputs,
        metadata={"study_reference": "Fixture-07", "api_key": "DO_NOT_EXPORT_METADATA_KEY_456"},
        include_input_snapshot=True,
        include_result_tables=True,
    )
    payload = pack["bundle_bytes"]
    assert payload.startswith(b"PK")
    assert hashlib.sha256(payload).hexdigest() == pack["bundle_sha256"]
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "result_summary.json", "input_snapshot_redacted.json", "run_metadata.json", "SHA256SUMS.txt", "README.txt"} <= names
        manifest = json.loads(archive.read("manifest.json"))
        summary_text = archive.read("result_summary.json").decode("utf-8")
        input_text = archive.read("input_snapshot_redacted.json").decode("utf-8")
        metadata_text = archive.read("run_metadata.json").decode("utf-8")
        table_paths = [name for name in names if name.startswith("tables/") and name.endswith(".csv")]
        assert len(table_paths) == 1
        table_text = archive.read(table_paths[0]).decode("utf-8")
        assert "DO_NOT_EXPORT_TOKEN_abc" not in summary_text
        assert "DO_NOT_EXPORT_BEARER_xyz" not in summary_text
        assert "DO_NOT_EXPORT_PASSWORD_123" not in input_text
        assert "DO_NOT_EXPORT_METADATA_KEY_456" not in metadata_text
        assert "private@example.test" not in table_text
        assert "[REDACTED]" in table_text
        assert manifest["configuration_snapshot_included"] is True
        assert manifest["detailed_result_tables_included"] is True
        manifest_items = {item["path"]: item for item in manifest["payload_files"]}
        assert "README.txt" in manifest_items
        for name, item in manifest_items.items():
            actual = archive.read(name)
            assert len(actual) == item["byte_count"]
            assert hashlib.sha256(actual).hexdigest() == item["sha256"]
        checksum_lines = archive.read("SHA256SUMS.txt").decode("utf-8").splitlines()
        for line in checksum_lines:
            digest, path = line.split("  ", 1)
            assert hashlib.sha256(archive.read(path)).hexdigest() == digest
    inventory = pack["artifact_inventory"].set_index("Path")
    assert inventory.loc["README.txt", "Bytes"] > 0
    assert pack["status"] == "REPRODUCIBILITY_PACK_CREATED"


def test_reproducibility_pack_defaults_to_metadata_and_table_fingerprints_only():
    import io
    import json
    import zipfile
    from shoir_target_engines import build_reproducibility_pack

    pack = build_reproducibility_pack(
        "T021",
        "Time Study",
        {"status": "CALCULATED", "standard_time": 14.5, "observations": pd.DataFrame({"time": [10, 12, 15]})},
        inputs={"observation_text": "10,12,15"},
    )
    with zipfile.ZipFile(io.BytesIO(pack["bundle_bytes"]), "r") as archive:
        names = set(archive.namelist())
        assert "input_snapshot_redacted.json" not in names
        assert not any(name.startswith("tables/") for name in names)
        summary = json.loads(archive.read("result_summary.json"))
        assert summary["standard_time"] == pytest.approx(14.5)
        assert summary["observations"]["artifact_type"] == "omitted_table_metadata"
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["configuration_snapshot_included"] is False
        assert manifest["detailed_result_tables_included"] is False
        assert manifest["configuration_sha256"] == pack["input_fingerprint_sha256"]


def test_reproducibility_pack_validates_canonical_ids_and_size_limits():
    from shoir_target_engines import build_reproducibility_pack

    with pytest.raises(ValueError, match="T001–T100"):
        build_reproducibility_pack("T999", "Invalid", {"status": "OK"})
    with pytest.raises(ValueError, match="completed result object"):
        build_reproducibility_pack("T087", "Reproducibility Pack", "not-an-object")
    with pytest.raises(ValueError, match="Maximum payload bytes"):
        build_reproducibility_pack("T087", "Reproducibility Pack", {"status": "OK"}, max_payload_bytes=1)


def test_facility_location_flow_matches_hand_checked_fixed_and_variable_costs():
    from shoir_target_engines import optimize_facility_location_flow

    result = optimize_facility_location_flow(
        [
            {"id": "F1", "fixed_opening_cost": 10, "capacity": 10},
            {"id": "F2", "fixed_opening_cost": 1, "capacity": 10},
        ],
        [{"id": "C1", "demand": 5}, {"id": "C2", "demand": 5}],
        [
            {"facility": "F1", "customer": "C1", "unit_cost": 1, "capacity": 10},
            {"facility": "F1", "customer": "C2", "unit_cost": 10, "capacity": 10},
            {"facility": "F2", "customer": "C1", "unit_cost": 5, "capacity": 10},
            {"facility": "F2", "customer": "C2", "unit_cost": 1, "capacity": 10},
        ],
    )
    assert result["status"] == "OPTIMAL_FEASIBLE"
    assert result["solver_status"] == "Optimal"
    assert result["objective_value"] == pytest.approx(21.0)
    assert result["fixed_opening_cost"] == pytest.approx(11.0)
    assert result["variable_shipment_cost"] == pytest.approx(10.0)
    assert result["independent_feasibility_check"] is True
    assert result["customer_balance"]["Status"].eq("SATISFIED").all()
    assert result["facility_table"]["Utilization (%)"].between(0, 100).all()


def test_facility_location_flow_reports_infeasible_and_validates_route_contracts():
    from shoir_target_engines import optimize_facility_location_flow

    facilities = [{"id": "F1", "fixed_opening_cost": 0, "capacity": 10}]
    customers = [{"id": "C1", "demand": 5}]
    infeasible = optimize_facility_location_flow(
        facilities, customers,
        [{"facility": "F1", "customer": "C1", "unit_cost": 1, "capacity": 2}],
    )
    assert infeasible["status"] == "INFEASIBLE"
    assert infeasible["objective_value"] is None

    with pytest.raises(ValueError, match="unique"):
        optimize_facility_location_flow(
            facilities, customers,
            [{"facility": "F1", "customer": "C1", "unit_cost": 1},
             {"facility": "F1", "customer": "C1", "unit_cost": 2}],
        )
    with pytest.raises(ValueError, match="unknown facility or customer"):
        optimize_facility_location_flow(
            facilities, customers,
            [{"facility": "F2", "customer": "C1", "unit_cost": 1}],
        )
    with pytest.raises(ValueError, match="non-negative"):
        optimize_facility_location_flow(
            facilities, customers,
            [{"facility": "F1", "customer": "C1", "unit_cost": -1}],
        )


def test_student_practice_examples_match_hand_calculated_answers_and_explain_methods():
    from shoir_target_engines import evaluate_student_practice_answer, get_student_practice_problem

    topics = {
        "takt_time": (2.0, 0.01),
        "oee_percent": (68.4, 0.1),
        "eoq_units": (math.sqrt(500000.0), 1.0),
        "process_capability_cp": (1.0, 0.01),
        "npv_sar": (-1000.0 + 600.0/1.10 + 600.0/(1.10**2), 0.5),
    }
    for topic, (answer, tolerance) in topics.items():
        prompt = get_student_practice_problem(topic)
        assert prompt["question"]
        assert prompt["formula"]
        assert "expected_answer" not in prompt
        result = evaluate_student_practice_answer(topic, answer)
        assert result["is_correct"] is True
        assert result["status"] == "PRACTICE_ANSWER_CHECKED"
        assert result["worked_solution"]
        assert result["data_provenance"] == "SYNTHETIC_EXERCISE"


def test_student_practice_marks_wrong_answers_and_rejects_invalid_inputs():
    from shoir_target_engines import evaluate_student_practice_answer, get_student_practice_problem

    wrong = evaluate_student_practice_answer("takt_time", 5.0)
    assert wrong["is_correct"] is False
    assert wrong["expected_answer"] == pytest.approx(2.0)
    assert "try again" in wrong["message"].lower()
    with pytest.raises(ValueError, match="supported practice topic"):
        get_student_practice_problem("unspecified_method")
    with pytest.raises(ValueError, match="finite number"):
        evaluate_student_practice_answer("takt_time", float("nan"))


def test_guided_study_plan_exposes_missing_inputs_and_registry_readiness_without_fabricating_results():
    from shoir_target_engines import build_guided_study_plan

    plan = build_guided_study_plan(
        "capacity_bottleneck",
        available_data_fields=["source_file", "validated_dataset", "process_table", "demand", "time_unit"],
        tier="Starter",
    )
    assert plan["status"] == "GUIDED_PLAN_CREATED"
    assert plan["step_count"] == 6
    rows = plan["steps"].set_index("Tool ID")
    assert rows.loc["T011", "Step status"] == "READY"
    assert rows.loc["T025", "Step status"] == "TIER_RESTRICTED"
    assert rows.loc["T073", "Step status"] == "TIER_RESTRICTED"
    assert "not an engineering result" in plan["warning"]
    assert plan["next_recommended_step"]["tool_id"] == "T011"


def test_guided_study_plan_handles_user_completed_steps_and_bad_contracts():
    from shoir_target_engines import build_guided_study_plan

    plan = build_guided_study_plan(
        "facility_layout",
        available_data_fields=["departments", "from_to_flows", "distances"],
        completed_tool_ids=["T065"],
        tier="Enterprise",
    )
    rows = plan["steps"].set_index("Tool ID")
    assert rows.loc["T065", "Step status"] == "COMPLETED_IN_SESSION"
    assert rows.loc["T069", "Step status"] == "FOUNDATION_ONLY"
    assert "facility_table" in rows.loc["T069", "Missing input fields"]
    with pytest.raises(ValueError, match="guided-study goals"):
        build_guided_study_plan("unknown_goal")
    with pytest.raises(ValueError, match="canonical IDs"):
        build_guided_study_plan("facility_layout", completed_tool_ids=["bad"])


def test_equipment_anomaly_monitor_detects_spike_and_reports_freshness_deterministically():
    from shoir_target_engines import monitor_equipment_anomalies

    observations = [
        {"timestamp": f"2026-10-25T0{i}:00:00Z", "value": value}
        for i, value in enumerate([10, 10, 10, 10, 10, 10, 10, 100])
    ]
    result = monitor_equipment_anomalies(
        observations,
        modified_z_threshold=3.5,
        max_age_hours=24,
        evaluation_time_utc="2026-10-25T08:00:00Z",
    )
    assert result["status"] == "ANOMALIES_DETECTED"
    assert result["anomaly_count"] == 1
    assert result["anomalies"].iloc[0]["value"] == pytest.approx(100)
    assert result["freshness_status"] == "FRESH"
    assert result["detection_method"] == "ZERO_MAD_ABSOLUTE_DEVIATION_FALLBACK"


def test_equipment_anomaly_monitor_distinguishes_stale_data_and_rejects_bad_inputs():
    from shoir_target_engines import monitor_equipment_anomalies

    observations = [
        {"timestamp": f"2026-10-20T0{i}:00:00Z", "value": value}
        for i, value in enumerate([10, 10, 10, 10, 10, 10])
    ]
    stale = monitor_equipment_anomalies(
        observations, evaluation_time_utc="2026-10-25T08:00:00Z", max_age_hours=24
    )
    assert stale["freshness_status"] == "STALE"
    assert stale["status"] == "NO_ANOMALIES_DETECTED"
    with pytest.raises(ValueError, match="between 5 and 50,000"):
        monitor_equipment_anomalies([])
    with pytest.raises(ValueError, match="invalid timestamp"):
        monitor_equipment_anomalies([{"timestamp": "bad", "value": 1}] * 5)
    with pytest.raises(ValueError, match="threshold"):
        monitor_equipment_anomalies(observations, modified_z_threshold=0.5)


def test_capa_8d_register_flags_incomplete_and_overdue_records():
    from shoir_target_engines import assess_capa_8d_records

    records = [{
        "capa_id": "CAPA-001", "title": "Repeated seal failure", "status": "IN_PROGRESS",
        "team": "Maintenance and quality", "problem_statement": "Seal failures recur",
        "containment_action": "Inspect affected assets", "root_cause": "Not confirmed",
        "corrective_action": "Replace supplier lot", "implementation_evidence": "WO-100",
        "preventive_action": "Add incoming inspection", "closure_review": "Open review",
        "owner": "Quality lead", "evidence_reference": "INV-55",
        "opened_date": "2026-10-01", "due_date": "2026-10-10",
    }]
    result = assess_capa_8d_records(records, as_of_date="2026-10-25")
    assert result["status"] == "CAPA_REGISTER_REVIEWED"
    assert result["record_count"] == 1
    assert result["overdue_count"] == 1
    row = result["records"].iloc[0]
    assert row["Workflow state"] == "OVERDUE"
    assert row["Missing item count"] == 0


def test_capa_8d_register_requires_evidence_for_closed_records_and_validates_dates():
    from shoir_target_engines import assess_capa_8d_records

    closed = {
        "capa_id": "CAPA-CLOSED", "title": "Completed record", "status": "CLOSED",
        "team": "Team A", "problem_statement": "Problem", "containment_action": "Contained",
        "root_cause": "Cause", "corrective_action": "Corrected",
        "implementation_evidence": "WO-1", "preventive_action": "Prevent recurrence",
        "closure_review": "Reviewed", "owner": "Owner", "evidence_reference": "EV-1",
        "opened_date": "2026-10-01", "due_date": "2026-10-20",
    }
    result = assess_capa_8d_records([closed], as_of_date="2026-10-25")
    assert result["complete_closure_count"] == 0
    assert result["records"].iloc[0]["Workflow state"] == "CLOSURE_EVIDENCE_INCOMPLETE"
    assert "Effectiveness evidence" in result["records"].iloc[0]["Missing items"]
    complete = dict(closed, effectiveness_evidence="Checked on 2026-10-22", reviewer="Reviewer A", approval_reference="APP-1")
    good = assess_capa_8d_records([complete], as_of_date="2026-10-25")
    assert good["complete_closure_count"] == 1
    assert good["overdue_count"] == 0

    with pytest.raises(ValueError, match="unique"):
        assess_capa_8d_records([closed, closed])
    with pytest.raises(ValueError, match="cannot precede"):
        assess_capa_8d_records([dict(closed, opened_date="2026-10-25", due_date="2026-10-24")])
    with pytest.raises(ValueError, match="between 1 and 5,000"):
        assess_capa_8d_records([])

def test_rcm_decision_register_requires_human_review_and_flags_high_consequence_choices():
    from shoir_target_engines import build_rcm_decision_register

    result = build_rcm_decision_register([
        {
            "asset": "Press-01",
            "function": "Form parts within approved dimensions",
            "failure_mode": "Ram-position drift",
            "failure_effect": "Out-of-spec parts and production interruption",
            "consequence_category": "operational",
            "consequence_rationale": "Synthetic screening example; quality impact requires site confirmation.",
            "proposed_task": "Inspect the position trend against approved limits",
            "task_strategy": "condition_directed",
            "condition_indicator": "Trend exceeds the approved guard band",
            "evidence_reference": "SYNTHETIC example only; replace with approved inspection/work-order evidence",
            "owner": "Maintenance planner",
        },
        {
            "asset": "Boiler-01",
            "function": "Contain and transfer process heat",
            "failure_mode": "Pressure boundary degradation",
            "failure_effect": "Potential hazardous release",
            "consequence_category": "safety_environmental",
            "consequence_rationale": "Illustrative high-consequence case; qualified site review is mandatory.",
            "proposed_task": "No planned maintenance task",
            "task_strategy": "run_to_failure",
            "evidence_reference": "SYNTHETIC example only; replace with approved engineering evidence",
        },
    ])

    assert result["status"] == "STRUCTURED_FOR_HUMAN_REVIEW"
    assert result["failure_mode_count"] == 2
    assert result["unique_asset_count"] == 2
    assert result["open_review_count"] == 2
    assert result["high_consequence_run_to_failure_count"] == 1
    assert result["human_review_required"] is True
    register = result["review_register"]
    assert register.iloc[0]["Human review status"] == "PENDING"
    assert register.iloc[0]["Decision flags"] == "No rule-based flags; human review still required"
    assert "HIGH_CONSEQUENCE_RUN_TO_FAILURE_REQUIRES_FORMAL_REVIEW" in register.iloc[1]["Decision flags"]
    assert "not a complete or certified rcm analysis" in result["warning"].lower()


def test_rcm_decision_register_rejects_duplicate_modes_missing_evidence_and_invalid_task_inputs():
    from shoir_target_engines import build_rcm_decision_register

    base = {
        "asset": "CNC-01",
        "function": "Cut material",
        "failure_mode": "Spindle stops",
        "failure_effect": "Production is interrupted",
        "consequence_category": "operational",
        "consequence_rationale": "Synthetic example only.",
        "proposed_task": "Review vibration trend",
        "task_strategy": "condition_directed",
        "condition_indicator": "Vibration exceeds approved threshold",
        "evidence_reference": "SYNTHETIC; replace with actual records",
    }
    with pytest.raises(ValueError, match="non-empty JSON list"):
        build_rcm_decision_register([])
    with pytest.raises(ValueError, match="evidence_reference"):
        build_rcm_decision_register([{**base, "evidence_reference": ""}])
    with pytest.raises(ValueError, match="Duplicate asset/function/failure-mode"):
        build_rcm_decision_register([base, base])
    with pytest.raises(ValueError, match="condition_indicator"):
        build_rcm_decision_register([{**base, "condition_indicator": ""}])
    with pytest.raises(ValueError, match="positive whole number"):
        build_rcm_decision_register([{
            **base,
            "task_strategy": "scheduled_restoration",
            "task_interval_days": 0,
        }])
    with pytest.raises(ValueError, match="task_interval_days is required"):
        build_rcm_decision_register([{
            **base,
            "task_strategy": "failure_finding",
            "consequence_category": "hidden_function",
        }])

