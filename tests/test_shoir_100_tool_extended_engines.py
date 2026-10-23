"""Golden and boundary fixtures for the added Shoir-IE specialist methods."""
from __future__ import annotations

import math
import pytest
import pandas as pd

from shoir_100_tool_extended_engines import (
    analyze_work_sampling, analyze_pareto_root_cause, assess_5s_audit,
    build_kaizen_a3_record, monitor_forecast_drift, convert_units_or_currency,
    analyze_spc_individuals, analyze_quality_cost_defects, analyze_mtbf_mttr,
    analyze_abc_xyz_inventory, plan_two_sample_t_sample_size, solve_cutting_stock,
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

def test_work_sampling_wilson_intervals_match_hand_checked_counts():
    from shoir_100_tool_extended_engines import analyze_work_sampling

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
    from shoir_100_tool_extended_engines import analyze_work_sampling

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
    from shoir_100_tool_extended_engines import analyze_pareto_root_cause

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
    from shoir_100_tool_extended_engines import analyze_pareto_root_cause

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
    from shoir_100_tool_extended_engines import assess_5s_audit

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
    from shoir_100_tool_extended_engines import assess_5s_audit

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
    from shoir_100_tool_extended_engines import build_kaizen_a3_record

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
    from shoir_100_tool_extended_engines import build_kaizen_a3_record

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

def test_unit_converter_checks_dimensions_and_converts_temperature():
    from shoir_100_tool_extended_engines import convert_units_or_currency

    assert convert_units_or_currency(100, "cm", "m")["converted_value"] == pytest.approx(1.0)
    assert convert_units_or_currency(0, "°C", "°F")["converted_value"] == pytest.approx(32.0)
    assert convert_units_or_currency(1, "kWh", "MJ")["converted_value"] == pytest.approx(3.6)
    with pytest.raises(ValueError, match="Incompatible dimensions"):
        convert_units_or_currency(1, "kg", "m")

def test_currency_converter_requires_dated_sourced_rate():
    from shoir_100_tool_extended_engines import convert_units_or_currency

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
    from shoir_100_tool_extended_engines import analyze_spc_individuals

    result = analyze_spc_individuals([10, 11, 9, 10, 12, 11], unit="mm")
    assert result["status"] == "NO_POINT_OUTSIDE_CALCULATED_LIMITS"
    assert result["mean"] == pytest.approx(10.5)
    assert result["moving_range_average"] == pytest.approx(1.4)
    assert result["estimated_within_sigma"] == pytest.approx(1.4 / 1.128)
    assert result["individuals_ucl"] == pytest.approx(10.5 + 3 * 1.4 / 1.128)
    assert result["moving_range_ucl"] == pytest.approx(3.267 * 1.4)

def test_spc_rejects_insufficient_or_constant_measurements():
    from shoir_100_tool_extended_engines import analyze_spc_individuals

    with pytest.raises(ValueError, match="at least three"):
        analyze_spc_individuals([1, 2])
    with pytest.raises(ValueError, match="Moving-range average is zero"):
        analyze_spc_individuals([5, 5, 5])

def test_quality_cost_reconciles_scrap_rework_and_inspection():
    from shoir_100_tool_extended_engines import analyze_quality_cost_defects

    result = analyze_quality_cost_defects(
        100, 10, 2, 5, 20, 6, 120, currency="SAR", period="Fixture month"
    )
    assert result["defective_rate_pct"] == pytest.approx(10.0)
    assert result["scrap_cost"] == pytest.approx(40.0)
    assert result["rework_cost"] == pytest.approx(30.0)
    assert result["cost_of_poor_quality"] == pytest.approx(190.0)
    assert result["copq_per_produced_unit"] == pytest.approx(1.9)

def test_quality_cost_rejects_overlapping_dispositions():
    from shoir_100_tool_extended_engines import analyze_quality_cost_defects

    with pytest.raises(ValueError, match="cannot exceed the defective"):
        analyze_quality_cost_defects(100, 10, 7, 5, 20, 6, 120)

def test_mtbf_mttr_matches_hand_calculated_reliability_measures():
    from shoir_100_tool_extended_engines import analyze_mtbf_mttr

    result = analyze_mtbf_mttr(600, [2, 1, 3])
    assert result["failure_count"] == 3
    assert result["mtbf_hours"] == pytest.approx(200)
    assert result["mttr_hours"] == pytest.approx(2)
    assert result["steady_state_availability_estimate_pct"] == pytest.approx(200 / 202 * 100)

def test_mtbf_mttr_rejects_invalid_events():
    from shoir_100_tool_extended_engines import analyze_mtbf_mttr

    with pytest.raises(ValueError, match="greater than zero"):
        analyze_mtbf_mttr(0, [1])
    with pytest.raises(ValueError, match="cannot be negative"):
        analyze_mtbf_mttr(10, [1, -0.1])
    with pytest.raises(ValueError, match="at least one"):
        analyze_mtbf_mttr(10, [])

def test_abc_xyz_uses_value_thresholds_and_demand_cv():
    from shoir_100_tool_extended_engines import analyze_abc_xyz_inventory

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
    from shoir_100_tool_extended_engines import analyze_abc_xyz_inventory

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
