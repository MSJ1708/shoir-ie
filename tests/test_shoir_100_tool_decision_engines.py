"""Deterministic fixtures for typed operational-decision tools."""
import pandas as pd
import pytest

from shoir_100_tool_decision_engines import (
    build_hazard_register, reconcile_sop_scenario, solve_assignment_cost_matrix,
    compare_capacity_scenarios, score_project_portfolio, build_hypothesis_evidence_register,
    evaluate_kpi_thresholds,
)


def test_hazard_register_sorts_residual_risk_and_flags_initial_high_score():
    result=build_hazard_register([
        {"hazard_id":"H1","hazard":"Hot surface","potential_harm":"Burn","likelihood_1_to_5":4,"severity_1_to_5":4,
         "residual_likelihood_1_to_5":2,"residual_severity_1_to_5":4,"current_controls":"Guard","additional_controls":"Inspect guard","owner":"Safety","due_date":"2026-11-01","status":"Open"},
        {"hazard_id":"H2","hazard":"Pinch point","potential_harm":"Injury","likelihood_1_to_5":2,"severity_1_to_5":5,
         "residual_likelihood_1_to_5":3,"residual_severity_1_to_5":4,"current_controls":"Interlock","additional_controls":"Test interlock","owner":"Maintenance","due_date":"","status":"In Progress"},
    ])
    assert result["metrics"]["hazard_count"] == 2
    assert result["metrics"]["high_initial_score_count"] == 2
    assert result["metrics"]["high_residual_score_count"] == 2
    assert result["hazard_register"].iloc[0]["hazard_id"] == "H2"


def test_hazard_register_rejects_invalid_rating_and_duplicate_id():
    row={"hazard_id":"H1","hazard":"Hazard","potential_harm":"Harm","likelihood_1_to_5":2,"severity_1_to_5":3,
         "residual_likelihood_1_to_5":1,"residual_severity_1_to_5":2,"current_controls":"","additional_controls":"","owner":"","due_date":"","status":"Open"}
    with pytest.raises(ValueError,match="whole number from 1 to 5"):
        build_hazard_register([{**row,"severity_1_to_5":7}])
    with pytest.raises(ValueError,match="Duplicate hazard ID"):
        build_hazard_register([row,row])


def test_sop_rollforward_carries_inventory_and_backlog_and_reports_overcapacity():
    result=reconcile_sop_scenario([
        {"period":"P1","demand_units":100,"planned_production_units":90,"capacity_units":100},
        {"period":"P2","demand_units":80,"planned_production_units":100,"capacity_units":90},
    ],starting_inventory_units=0)
    rec=result["reconciliation"]
    assert rec.loc[0,"ending_backlog_units"] == 10
    assert rec.loc[1,"ending_backlog_units"] == 0
    assert rec.loc[1,"ending_inventory_units"] == 10
    assert result["metrics"]["capacity_exceeded_periods"] == 1


def test_sop_rejects_duplicate_periods_and_negative_inputs():
    with pytest.raises(ValueError,match="non-empty and unique"):
        reconcile_sop_scenario([{"period":"P1","demand_units":0,"planned_production_units":0,"capacity_units":0},
                                {"period":"P1","demand_units":0,"planned_production_units":0,"capacity_units":0}])
    with pytest.raises(ValueError,match="at least 0"):
        reconcile_sop_scenario([{"period":"P1","demand_units":-1,"planned_production_units":0,"capacity_units":0}])


def test_assignment_hungarian_solution_matches_hand_checkable_fixture():
    result=solve_assignment_cost_matrix(pd.DataFrame({
        "job":["A","B","C"],"M1":[4,2,3],"M2":[3,5,2],"M3":[6,4,1]
    }))
    assert result["status"]=="OPTIMAL_FOR_ASSIGNMENT_MODEL"
    assert result["metrics"]["total_assignment_cost"] == pytest.approx(6)
    assert set(result["assignments"]["job"])=={"A","B","C"}
    assert result["metrics"]["assignment_complete"] is True


def test_assignment_rejects_nonsquare_missing_and_negative_costs():
    with pytest.raises(ValueError,match="square matrix"):
        solve_assignment_cost_matrix(pd.DataFrame({"job":["A","B"],"M1":[1,2],"M2":[3,4],"M3":[5,6]}))
    with pytest.raises(ValueError,match="non-negative"):
        solve_assignment_cost_matrix(pd.DataFrame({"job":["A","B"],"M1":[1,2],"M2":[3,-1]}))
    with pytest.raises(ValueError,match="finite and complete"):
        solve_assignment_cost_matrix(pd.DataFrame({"job":["A","B"],"M1":[1,float("nan")],"M2":[3,4]}))


def test_scenario_capacity_compares_baseline_and_changes():
    result=compare_capacity_scenarios([
        {"scenario_id":"Baseline","available_minutes_per_period":420,"cycle_time_minutes_per_unit":4,"yield_percent":95},
        {"scenario_id":"Shorter cycle","available_minutes_per_period":420,"cycle_time_minutes_per_unit":3.5,"yield_percent":95},
    ],demand_units=100,baseline_scenario_id="Baseline")
    table=result["scenario_comparison"].set_index("scenario_id")
    assert table.loc["Baseline","estimated_good_units_capacity"] == pytest.approx(99.75)
    assert table.loc["Shorter cycle","capacity_delta_vs_baseline_units"] > 0
    assert result["metrics"]["scenarios_meeting_entered_demand"] == 1


def test_project_portfolio_score_uses_visible_weights_and_rejects_bad_scores():
    result=score_project_portfolio([
        {"project_id":"P1","project_name":"Line change","estimated_cost":1000,"impact_score":90,"strategic_fit_score":80,"feasibility_score":70,"confidence_score":60},
        {"project_id":"P2","project_name":"Tooling","estimated_cost":500,"impact_score":80,"strategic_fit_score":90,"feasibility_score":90,"confidence_score":80},
    ])
    scores=result["portfolio"].set_index("project_id")["weighted_score"]
    assert scores["P1"]==pytest.approx(81)
    assert scores["P2"]==pytest.approx(85)
    assert result["metrics"]["top_ranked_project_id"]=="P2"
    with pytest.raises(ValueError,match="must not exceed 100"):
        score_project_portfolio([{"project_id":"P1","project_name":"Line change","estimated_cost":1,"impact_score":101,"strategic_fit_score":80,"feasibility_score":70,"confidence_score":60}])


def test_evidence_register_exposes_missing_source_and_never_claims_independent_verification():
    result=build_hypothesis_evidence_register([
        {"evidence_id":"E1","claim_or_hypothesis":"Line cycle decreased","source_reference":"RUN-123","method_or_run":"T036","review_state":"UNREVIEWED","reviewer":"","review_date":"","limitations":"Synthetic fixture"}
    ])
    assert result["metrics"]["evidence_record_count"] == 1
    assert result["metrics"]["independently_verified_count"] == 0
    assert result["evidence_register"].iloc[0]["independently_verified"] == False
    with pytest.raises(ValueError,match="reviewer and review_date"):
        build_hypothesis_evidence_register([
            {"evidence_id":"E2","claim_or_hypothesis":"Claim","source_reference":"SRC","method_or_run":"M1","review_state":"SUPPORTS","reviewer":"","review_date":"","limitations":""}
        ])


def test_kpi_alerts_apply_direction_and_freshness_explicitly():
    result=evaluate_kpi_thresholds([
        {"metric_name":"Scrap","observed_value":8,"threshold":5,"direction":"ABOVE","unit":"%","last_updated_date":"2026-10-20","owner":"Quality"},
        {"metric_name":"OEE","observed_value":70,"threshold":75,"direction":"BELOW","unit":"%","last_updated_date":"2026-10-01","owner":"Production"},
    ],as_of_date="2026-10-24",stale_after_days=7)
    table=result["kpi_status"].set_index("metric_name")
    assert table.loc["Scrap","status"] == "ALERT"
    assert table.loc["OEE","status"] == "ALERT_STALE"
    assert result["metrics"]["alert_count"] == 2
    assert result["metrics"]["stale_metric_count"] == 1


def test_kpi_alerts_reject_future_data_and_unknown_direction():
    row={"metric_name":"OEE","observed_value":70,"threshold":75,"direction":"BELOW","unit":"%","last_updated_date":"2026-10-24","owner":"Plant"}
    with pytest.raises(ValueError,match="cannot be after"):
        evaluate_kpi_thresholds([row],as_of_date="2026-10-23")
    with pytest.raises(ValueError,match="direction must be ABOVE or BELOW"):
        evaluate_kpi_thresholds([{**row,"direction":"EQUAL"}],as_of_date="2026-10-24")
