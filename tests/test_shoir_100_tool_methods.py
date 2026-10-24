"""Golden, boundary, and entitlement tests for T013/T017/T018/T019/T034/T070/T082/T084."""
from __future__ import annotations

import math

import pandas as pd
import pytest
from scipy.stats import binom

from shoir_100_tool_methods import (
    a3_improvement, abc_xyz_analysis, acceptance_sampling_oc, audit_5s,
    capa_completeness, fmea_prioritization, hazard_risk_register, map_industrial_fields,
    preventive_maintenance_plan, preview_reversible_cleaning, spare_parts_criticality,
    value_stream_summary,
    bin_pack_1d, bottleneck_analysis, cost_variance, forecast_drift_report,
    generate_synthetic_industrial_data, inventory_policy, join_dataframes,
    line_balance, mm1_queue, mtbf_mttr_analysis, oee_analysis, portfolio_score, process_time_series,
    profile_dataframe, quality_cost_analysis, require_tool_access,
    root_cause_analysis, two_sample_mean_power, weibull_reliability,
)


def test_profile_counts_missing_duplicates_and_iqr_outlier_without_mutating_input():
    source = pd.DataFrame({"cycle": [1, 2, 3, 4, 100], "area": ["A", "A", None, "B", "B"]})
    before = source.copy(deep=True)
    result = profile_dataframe(source)
    assert result["row_count"] == 5
    assert result["missing_cell_count"] == 1
    assert result["duplicate_row_count"] == 0
    prof = result["columns"].set_index("column")
    assert prof.loc["cycle", "iqr_outlier_count"] == 1
    pd.testing.assert_frame_equal(source, before)


def test_join_reconciles_rows_and_blocks_unapproved_many_to_many_and_null_keys():
    left = pd.DataFrame({"machine": ["M1", "M2", "M3"], "units": [1, 2, 3]})
    right = pd.DataFrame({"machine": ["M1", "M2"], "line": ["A", "B"]})
    result = join_dataframes(left, right, ["machine"], cardinality="many_to_one")
    assert result["output_rows"] == 3
    assert result["join_status_counts"]["left_only"] == 1
    assert list(result["data"]["line"].fillna("")) == ["A", "B", ""]
    duplicated_right = pd.DataFrame({"machine": ["M1", "M1"], "line": ["A", "B"]})
    with pytest.raises(ValueError, match="violates"):
        join_dataframes(left, duplicated_right, ["machine"], cardinality="many_to_one")
    with pytest.raises(ValueError, match="(?i)many-to-many"):
        join_dataframes(left, duplicated_right, ["machine"], cardinality="many_to_many")
    with pytest.raises(ValueError, match="Null join keys"):
        join_dataframes(pd.DataFrame({"k": [None]}), pd.DataFrame({"k": [1]}), ["k"])


def test_time_series_normalizes_timezone_sorts_and_flags_gap():
    source = pd.DataFrame({
        "ts": ["2026-01-01T02:00:00+03:00", "bad", "2026-01-01T00:00:00+03:00",
               "2026-01-01T12:00:00+03:00"],
        "value": [2, 999, 0, 5],
    })
    result = process_time_series(source, "ts", ["value"], target_timezone="UTC")
    assert result["invalid_timestamp_rows"] == 1
    assert result["rows_in"] == 4 and result["rows_out"] == 3
    assert result["data"]["timestamp"].is_monotonic_increasing
    assert result["gap_count_vs_median_interval"] >= 1


def test_synthetic_data_is_reproducible_and_explicitly_synthetic():
    a = generate_synthetic_industrial_data(20, 77, "2026-01-01")
    b = generate_synthetic_industrial_data(20, 77, "2026-01-01")
    pd.testing.assert_frame_equal(a["data"], b["data"])
    assert set(a["data"]["data_status"]) == {"SYNTHETIC"}
    with pytest.raises(ValueError, match="between 1 and 10,000"):
        generate_synthetic_industrial_data(0)


def test_acceptance_sampling_oc_matches_binomial_reference_and_risk_direction():
    result = acceptance_sampling_oc(10, 1, 5, 20)
    assert result["probability_accept_at_aql"] == pytest.approx(binom.cdf(1, 10, 0.05))
    assert result["probability_accept_at_ltpd"] == pytest.approx(binom.cdf(1, 10, 0.20))
    assert result["producer_risk_at_aql"] == pytest.approx(1 - result["probability_accept_at_aql"])
    assert result["consumer_risk_at_ltpd"] == pytest.approx(result["probability_accept_at_ltpd"])
    assert result["probability_accept_at_aql"] > result["probability_accept_at_ltpd"]
    with pytest.raises(ValueError, match="AQL < LTPD"):
        acceptance_sampling_oc(10, 1, 20, 5)


def test_mm1_queue_matches_known_values_and_rejects_unstable_system():
    result = mm1_queue(4, 5, "hour")
    assert result["utilization"] == pytest.approx(0.8)
    assert result["Lq_expected_queue_length"] == pytest.approx(3.2)
    assert result["L_expected_system_length"] == pytest.approx(4.0)
    assert result["Wq_expected_wait"] == pytest.approx(0.8)
    assert result["W_expected_system_time"] == pytest.approx(1.0)
    unstable = mm1_queue(5, 5)
    assert unstable["status"] == "UNSTABLE"
    with pytest.raises(ValueError, match="greater than zero"):
        mm1_queue(0, 5)


def test_cost_variance_reconciles_components_and_marks_cost_direction():
    result = cost_variance([
        {"component": "Material", "actual": 120, "standard": 100, "plan": 110},
        {"component": "Labor", "actual": 80, "standard": 90, "plan": 85},
    ], "SAR")
    assert result["totals"]["actual_cost"] == 200
    assert result["totals"]["actual_minus_standard"] == 10
    assert result["totals"]["actual_minus_plan"] == 5
    assert list(result["components"]["standard_variance"]) == ["UNFAVORABLE", "FAVORABLE"]
    with pytest.raises(ValueError, match="currency code"):
        cost_variance([{"component": "A", "actual": 1, "standard": 1, "plan": 1}], "SAR1")


def test_portfolio_score_normalizes_weights_and_reports_limited_sensitivity():
    result = portfolio_score([
        {"name": "A", "scores": {"value": 5, "risk": 3}},
        {"name": "B", "scores": {"value": 3, "risk": 5}},
    ], {"value": 2, "risk": 1})
    weights = result["weights"]
    assert weights["normalized_weight_pct"].sum() == pytest.approx(100.0)
    assert result["scores"].iloc[0]["project"] == "A"
    assert result["scores"].iloc[0]["weighted_score_pct"] == pytest.approx(86.6666667)
    assert set(result["sensitivity"].columns) >= {"base_rank", "best_rank", "worst_rank"}
    with pytest.raises(ValueError, match="missing criterion"):
        portfolio_score([{"name": "A", "scores": {"value": 4}}], {"value": 1, "risk": 1})


@pytest.mark.parametrize("tool_id,tier,allowed", [
    ("T013", "Starter Tier", True),
    ("T017", "Starter", False),
    ("T017", "Mid-Tier Pro", True),
    ("T034", "Research Pack", True),
    ("T034", "Professional", True),
    ("T098", "Research Pack", False),
    ("T098", "Enterprise Plus Tier", True),
])
def test_tool_access_matches_six_package_contract(tool_id, tier, allowed):
    if allowed:
        assert require_tool_access(tier, tool_id, "disposable-test-user")["tool_id"] == tool_id
    else:
        with pytest.raises(PermissionError):
            require_tool_access(tier, tool_id, "disposable-test-user")


@pytest.mark.parametrize("tier,tool_id,actor", [
    ("Enterprise Plus", "T013", "guest"),
    ("Made Up Tier", "T013", "disposable-test-user"),
    ("Enterprise Plus", "T999", "disposable-test-user"),
])
def test_tool_access_fails_closed_for_guest_unknown_tier_or_id(tier, tool_id, actor):
    with pytest.raises(PermissionError):
        require_tool_access(tier, tool_id, actor)



def test_line_balance_respects_precedence_and_reports_heuristic_limits():
    result = line_balance([
        {"task": "A", "duration": 4, "predecessors": ""},
        {"task": "B", "duration": 3, "predecessors": "A"},
        {"task": "C", "duration": 2, "predecessors": "A"},
        {"task": "D", "duration": 4, "predecessors": "B, C"},
    ], cycle_time=6)
    assert result["status"] == "HEURISTIC_BALANCED"
    assert result["station_count"] == 3
    assert result["efficiency_pct"] == pytest.approx(13 / 18 * 100)
    station = result["tasks"].set_index("task")["station"].to_dict()
    assert station["A"] <= station["B"] <= station["D"]
    assert station["A"] <= station["C"] <= station["D"]
    with pytest.raises(ValueError, match="cycle"):
        line_balance([
            {"task": "A", "duration": 1, "predecessors": "B"},
            {"task": "B", "duration": 1, "predecessors": "A"},
        ], 2)


def test_root_cause_pareto_and_five_whys_are_hypotheses_not_causal_proof():
    result = root_cause_analysis(
        [{"category": "Stops", "count": 8}, {"category": "Material", "count": 2}, {"category": "Stops", "count": 2}],
        ["Why 1", "Why 2", "Why 3", "Why 4", "Why 5"], "Owner A", "Run observation", "2026-11-01",
    )
    assert result["total_count"] == 12
    assert result["pareto"].iloc[0]["category"] == "Stops"
    assert result["pareto"].iloc[-1]["cumulative_share_pct"] == pytest.approx(100)
    assert result["action"]["status"] == "ACTION_RECORDED"
    with pytest.raises(ValueError, match="exactly five"):
        root_cause_analysis([{"category": "Stops", "count": 1}], ["one why"])


def test_5s_audit_computes_score_and_rejects_duplicate_area_category():
    result = audit_5s([
        {"area": "Cell A", "category": category, "score": score, "evidence": "photo-1", "owner": "Lead", "action": "", "due_date": ""}
        for category, score in zip(["Sort", "Set in order", "Shine", "Standardize", "Sustain"], [1, 2, 3, 4, 5])
    ])
    assert result["overall_score_pct"] == pytest.approx(60)
    assert len(result["category_summary"]) == 5
    with pytest.raises(ValueError, match="Duplicate 5S"):
        audit_5s([
            {"area": "Cell A", "category": "Sort", "score": 1},
            {"area": "Cell A", "category": "Sort", "score": 3},
        ])


def test_a3_records_actual_measurement_and_evidence_without_auto_verifying_it():
    result = a3_improvement(
        "Reduce setup", "Setup varies", "Setup time", "min", 45, 30, "lower",
        "Standardize tool staging", "Owner A", "2026-11-01", 32, "run-123", 100,
    )
    assert result["absolute_improvement"] == 13
    assert result["target_met"] is False
    assert result["evidence_reference_recorded"] is True
    assert result["verification_status"] == "PENDING_REVIEW"
    assert result["outcome_verified"] is False


def test_quality_cost_analysis_reconciles_scrap_rework_and_inspection():
    result = quality_cost_analysis([
        {"defect_type": "Cracked", "scrap_qty": 2, "scrap_unit_cost": 20, "rework_hours": 2, "rework_cost_per_hour": 10, "inspection_cost": 5},
        {"defect_type": "Mislabel", "scrap_qty": 0, "scrap_unit_cost": 20, "rework_hours": 1, "rework_cost_per_hour": 10, "inspection_cost": 3},
    ], "SAR")
    assert result["totals"]["scrap_cost"] == 40
    assert result["totals"]["rework_cost"] == 30
    assert result["totals"]["inspection_cost"] == 8
    assert result["totals"]["cost_of_poor_quality"] == 78


def test_inventory_policy_matches_golden_eoq_and_reorder_point():
    result = inventory_policy(10000, 25, 4, 100, 20, 4, 1.645)
    assert result["eoq_units"] == pytest.approx(math.sqrt(125000))
    assert result["safety_stock_units"] == pytest.approx(65.8)
    assert result["expected_lead_time_demand_units"] == pytest.approx(400)
    assert result["reorder_point_units"] == pytest.approx(465.8)
    with pytest.raises(ValueError, match="must be positive"):
        inventory_policy(0, 25, 4, 100, 20, 4, 1.645)


def test_abc_xyz_segments_selected_period_value_and_variability():
    data = pd.DataFrame([
        {"SKU": "B", "unit_cost": 100, "P1": 2, "P2": 4, "P3": 1},
        {"SKU": "A", "unit_cost": 10, "P1": 10, "P2": 11, "P3": 9},
        {"SKU": "C", "unit_cost": 1, "P1": 50, "P2": 50, "P3": 50},
    ])
    result = abc_xyz_analysis(data, "SKU", "unit_cost", ["P1", "P2", "P3"])
    ranked = result["items"].set_index("sku")
    assert ranked.loc["B", "ABC_class"] == "A"
    assert ranked.loc["C", "XYZ_class"] == "X"
    assert set(ranked["ABC_XYZ_class"]) <= {"AX", "AY", "AZ", "BX", "BY", "BZ", "CX", "CY", "CZ"}
    with pytest.raises(ValueError, match="greater than zero"):
        abc_xyz_analysis(pd.DataFrame([{"SKU": "A", "unit_cost": 0, "P1": 0}]), "SKU", "unit_cost", ["P1"])



def test_bottleneck_analysis_ranks_lowest_effective_capacity_and_discloses_limits():
    result = bottleneck_analysis([
        {"operation": "Cut", "cycle_time_seconds": 10, "available_hours": 8, "downtime_hours": 1, "observed_units": 2000},
        {"operation": "Pack", "cycle_time_seconds": 20, "available_hours": 8, "downtime_hours": 0, "observed_units": 1200},
    ])
    assert result["bottleneck_candidate"] == "Pack"
    assert result["estimated_system_capacity_units_per_window"] == pytest.approx(1440)
    assert result["operations"].iloc[0]["bottleneck_candidate"] is True or bool(result["operations"].iloc[0]["bottleneck_candidate"])
    with pytest.raises(ValueError, match="downtime below available"):
        bottleneck_analysis([{"operation": "A", "cycle_time_seconds": 10, "available_hours": 8, "downtime_hours": 8, "observed_units": 0}])


def test_oee_matches_hand_calculated_availability_performance_quality():
    result = oee_analysis(480, 30, 60, 400, 380)
    assert result["availability_pct"] == pytest.approx(93.75)
    assert result["performance_pct"] == pytest.approx(88.8888889)
    assert result["quality_pct"] == pytest.approx(95)
    assert result["oee_pct"] == pytest.approx(79.1666667)
    with pytest.raises(ValueError, match="good count"):
        oee_analysis(480, 30, 60, 400, 401)


def test_weibull_fit_produces_ordered_percentiles_and_discloses_uncensored_scope():
    result = weibull_reliability([10, 20, 30, 40, 60, 90])
    assert result["shape_beta"] > 0
    assert result["scale_eta"] > 0
    assert result["B10"] < result["B50"] < result["B90"]
    with pytest.raises(ValueError, match="at least three"):
        weibull_reliability([10, 20])
    with pytest.raises(ValueError, match="positive"):
        weibull_reliability([10, 20, 0])


def test_bin_pack_1d_is_feasible_and_reconciles_piece_kerf_and_waste():
    result = bin_pack_1d([6, 4, 4, 4], stock_length=10, kerf=0)
    assert result["stock_count"] == 2
    assert result["total_piece_length"] == 18
    assert result["total_waste_length"] == 2
    assert result["overall_utilization_pct"] == pytest.approx(90)
    kerfed = bin_pack_1d([5, 4, 4], stock_length=10, kerf=1)
    assert kerfed["stock_count"] == 2
    assert (kerfed["stocks"]["waste_length"] >= 0).all()


def test_forecast_drift_metrics_match_reference_and_zero_actual_mape_handling():
    result = forecast_drift_report([100, 110, 90], [102, 100, 95], 0.5, 5)
    assert result["bias_prediction_minus_actual"] == pytest.approx(-1)
    assert result["mae"] == pytest.approx(17/3)
    assert result["rmse"] == pytest.approx(math.sqrt(43))
    assert result["status"] == "DRIFT_FLAGGED"
    zeros = forecast_drift_report([0, 10], [5, 10], 100, 100)
    assert zeros["mape_pct_nonzero_actuals"] == pytest.approx(0)
    assert zeros["zero_actual_count_excluded_from_mape"] == 1


def test_two_sample_mean_power_matches_normal_approximation_and_rejects_bad_design():
    result = two_sample_mean_power(effect_size=2, population_std=2, alpha=.05, desired_power=.80)
    assert result["sample_size_per_group"] == 16
    assert result["total_sample_size"] == 32
    assert result["normal_approximation_achieved_power"] >= .80
    with pytest.raises(ValueError, match="alpha"):
        two_sample_mean_power(2, 2, alpha=1, desired_power=.8)



def test_mtbf_mttr_aggregates_completed_intervals_and_uses_explicit_time_units():
    result = mtbf_mttr_analysis([
        {"uptime_hours": 10, "repair_hours": 8},
        {"uptime_hours": 20, "repair_hours": 10},
        {"uptime_hours": 15, "repair_hours": 7},
    ])
    assert result["mtbf_hours"] == pytest.approx(15)
    assert result["mttr_hours"] == pytest.approx(25/3)
    assert result["interval_availability_pct"] == pytest.approx(45/70*100)
    with pytest.raises(ValueError, match="cannot have both zero"):
        mtbf_mttr_analysis([{"uptime_hours": 0, "repair_hours": 0}])


@pytest.mark.parametrize("tier,tool_id,allowed", [
    ("Starter Tier ($29)", "T013", True),
    ("Mid-Tier Pro ($79)", "T017", True),
    ("Professional Tier ($129)", "T034", True),
    ("Enterprise Tier ($199)", "T048", True),
    ("Enterprise Plus Tier ($399)", "T098", True),
    ("Research Pack ($30 add-on)", "T085", True),
    ("Research Pack ($30 add-on)", "T098", False),
])
def test_price_bearing_app_tier_labels_are_mapped_without_cross_package_access(tier, tool_id, allowed):
    if allowed:
        assert require_tool_access(tier, tool_id, "disposable-test-user")["tool_id"] == tool_id
    else:
        with pytest.raises(PermissionError):
            require_tool_access(tier, tool_id, "disposable-test-user")



def test_reversible_cleaner_returns_candidate_and_change_log_without_mutating_source():
    source = pd.DataFrame({"part": [" A ", "B", "B"], "qty": [1, None, None]})
    before = source.copy(deep=True)
    result = preview_reversible_cleaning(source, trim_strings=True, duplicate_policy="drop_exact", missing_policy="fill_value", fill_value=0)
    pd.testing.assert_frame_equal(source, before)
    assert result["apply_confirmed"] is False
    assert result["candidate"]["part"].tolist() == ["A", "B"]
    assert result["missing_cells_after"] == 0
    assert result["exact_duplicate_rows_removed"] == 1
    with pytest.raises(ValueError, match="remove every row"):
        preview_reversible_cleaning(pd.DataFrame({"a": [None, None]}), missing_policy="drop_rows")


def test_industrial_field_mapper_preserves_source_and_blocks_duplicate_targets():
    source = pd.DataFrame({"Equipment Tag": ["M1", "M2"], "Cycles": [1, 2]})
    result = map_industrial_fields(source, {"asset_id": "Equipment Tag", "cycle_count": "Cycles"})
    assert list(result["mapped"].columns) == ["asset_id", "cycle_count"]
    pd.testing.assert_frame_equal(result["source"], source)
    with pytest.raises(ValueError, match="duplicate column names"):
        map_industrial_fields(pd.DataFrame({"A": [1], "asset_id": [2]}), {"asset_id": "A"})


def test_value_stream_summary_reconciles_takt_process_queue_and_va_ratio():
    result = value_stream_summary([
        {"stage": "Cut", "cycle_time_seconds": 60, "changeover_minutes": 5, "wip_units": 10, "value_added": True},
        {"stage": "Pack", "cycle_time_seconds": 30, "changeover_minutes": 2, "wip_units": 20, "value_added": False},
    ], demand_units=60, available_minutes_per_period=480, period_label="shift")
    assert result["takt_time_minutes_per_unit"] == pytest.approx(8)
    assert result["total_process_cycle_minutes"] == pytest.approx(1.5)
    assert result["total_value_added_minutes"] == pytest.approx(1)
    assert result["estimated_queue_wait_minutes"] == pytest.approx(240)
    with pytest.raises(ValueError, match="positive"):
        value_stream_summary([{"stage": "Cut", "cycle_time_seconds": 60}], 0, 480)


def test_fmea_computes_rpn_and_keeps_rating_rationale_inputs():
    result = fmea_prioritization([
        {"failure_mode": "Jam", "severity": 8, "occurrence": 4, "detection": 6, "recommended_action": "Inspect guide"},
        {"failure_mode": "Label", "severity": 3, "occurrence": 6, "detection": 3},
    ])
    assert result["failure_modes"].iloc[0]["failure_mode"] == "Jam"
    assert result["failure_modes"].iloc[0]["RPN"] == 192
    with pytest.raises(ValueError, match="1 through 10"):
        fmea_prioritization([{"failure_mode": "X", "severity": 0, "occurrence": 1, "detection": 1}])


def test_capa_completeness_separates_complete_records_from_incomplete_actions():
    result = capa_completeness([
        {"issue": "Repeat defect", "containment": "Hold lot", "root_cause": "Seal worn",
         "corrective_action": "Replace seal", "owner": "Lead", "due_date": "2026-11-05",
         "effectiveness_evidence": "quality-run-17"},
        {"issue": "Late delivery"},
    ])
    assert result["ready_for_review_count"] == 1
    assert result["incomplete_count"] == 1
    assert result["records"].iloc[0]["readiness"] == "READY_FOR_REVIEW"


def test_pm_planner_calculates_next_due_dates_and_overdue_status():
    result = preventive_maintenance_plan([
        {"asset_id": "M1", "task": "Lubricate", "interval_days": 30, "last_done_date": "2026-09-01", "duration_hours": 1.5, "required_skill": "Mechanical"},
        {"asset_id": "M2", "task": "Inspect", "interval_days": 7, "last_done_date": "2026-10-23", "duration_hours": 0.5, "required_skill": "Electrical"},
    ], "2026-10-24")
    table = result["tasks"].set_index("task")
    assert table.loc["Lubricate", "next_due_date"] == "2026-10-01"
    assert table.loc["Lubricate", "status"] == "OVERDUE"
    assert table.loc["Inspect", "status"] == "DUE"
    with pytest.raises(ValueError, match="last_done_date"):
        preventive_maintenance_plan([{"asset_id": "M1", "task": "x", "interval_days": 30, "last_done_date": "bad", "duration_hours": 1}], "2026-10-24")


def test_spare_parts_criticality_computes_reorder_point_and_criticality_priority():
    result = spare_parts_criticality([
        {"part_id": "P1", "annual_demand": 365, "unit_cost": 10, "lead_time_days": 4, "daily_demand_std": 2, "stock_on_hand": 2, "criticality_1_to_5": 5},
        {"part_id": "P2", "annual_demand": 365, "unit_cost": 1, "lead_time_days": 1, "daily_demand_std": 0, "stock_on_hand": 50, "criticality_1_to_5": 2},
    ], service_z=1)
    parts = result["parts"].set_index("part_id")
    assert parts.loc["P1", "reorder_point"] == pytest.approx(8)
    assert bool(parts.loc["P1", "reorder_needed"]) is True
    assert parts.index[0] == "P1"
    with pytest.raises(ValueError, match="integer criticality"):
        spare_parts_criticality([{"part_id": "P1", "annual_demand": 1, "unit_cost": 1, "lead_time_days": 1, "daily_demand_std": 1, "stock_on_hand": 0, "criticality_1_to_5": 5.5}])


def test_hazard_register_distinguishes_inherent_and_residual_risk():
    result = hazard_risk_register([
        {"hazard": "Pinch point", "location": "Press 1", "severity": 5, "likelihood": 4,
         "existing_controls": "Guard", "residual_severity": 5, "residual_likelihood": 2,
         "owner": "Safety lead", "action": "Verify interlock"},
    ])
    row = result["hazards"].iloc[0]
    assert row["inherent_score"] == 20
    assert row["residual_score"] == 10
    assert "not a certified workplace risk assessment" in " ".join(result["warnings"])
