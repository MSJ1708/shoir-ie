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
