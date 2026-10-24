"""Golden/boundary fixtures for maintenance, spare-parts and supplier methods."""
import pandas as pd
import pytest

from shoir_100_tool_asset_engines import plan_preventive_maintenance, plan_spare_part_criticality, score_supplier_performance


def test_maintenance_due_dates_overdue_and_rollup_metrics():
    result = plan_preventive_maintenance([
        {"task_id":"PM-1","asset_id":"A1","task":"Inspect seal","interval_days":30,"last_completed_date":"2026-09-01","estimated_duration_hours":2,"required_skill":"Mechanic","downtime_window":"Night"},
        {"task_id":"PM-2","asset_id":"A2","task":"Check pump","interval_days":30,"last_completed_date":"2026-10-10","estimated_duration_hours":1.5,"required_skill":"Technician","downtime_window":"Weekend"},
    ], "2026-10-24")
    assert result["metrics"]["task_count"] == 2
    assert result["metrics"]["overdue_tasks"] == 1
    assert result["metrics"]["due_within_30_days"] == 1
    assert result["metrics"]["total_estimated_hours"] == pytest.approx(3.5)
    assert result["maintenance_plan"].iloc[0]["next_due_date"] == "2026-10-01"


def test_maintenance_planner_rejects_future_completion_and_fractional_intervals():
    row={"task_id":"PM-1","asset_id":"A1","task":"Inspect","interval_days":30,"last_completed_date":"2026-10-25","estimated_duration_hours":1,"required_skill":"Tech","downtime_window":"Night"}
    with pytest.raises(ValueError, match="after the as-of"):
        plan_preventive_maintenance([row], "2026-10-24")
    with pytest.raises(ValueError, match="whole number"):
        plan_preventive_maintenance([{**row,"last_completed_date":"2026-10-20","interval_days":30.5}], "2026-10-24")


def test_spare_part_reorder_point_uses_lead_demand_and_safety_stock():
    result = plan_spare_part_criticality([
        {"part_id":"SP-01","asset_id":"Pump-1","annual_demand":1000,"daily_demand_stddev":2,"lead_time_days":5,"unit_cost":20,"current_stock":10,"on_order":5,"criticality_score":5}
    ], operating_days_per_year=250, service_factor_z=1.645)
    plan = result["spare_parts_plan"].iloc[0]
    assert plan["mean_lead_time_demand"] == pytest.approx(20)
    assert plan["safety_stock"] == pytest.approx(1.645 * 2 * (5 ** 0.5))
    assert plan["recommended_reorder_quantity"] == 13
    assert result["metrics"]["parts_below_reorder_point"] == 1


def test_spare_part_planner_rejects_criticality_outside_scale():
    row={"part_id":"SP-01","asset_id":"Pump-1","annual_demand":100,"daily_demand_stddev":1,"lead_time_days":2,"unit_cost":5,"current_stock":0,"on_order":0,"criticality_score":6}
    with pytest.raises(ValueError, match="from 1 to 5"):
        plan_spare_part_criticality([row])


def test_supplier_scorecard_discloses_missing_evidence_and_normalizes_weights():
    result=score_supplier_performance([
        {"supplier":"A","quality_score":90,"delivery_score":80,"cost_score":70,"responsiveness_score":100,"evidence_date":"2026-10-01"},
        {"supplier":"B","quality_score":70,"delivery_score":70,"cost_score":None,"responsiveness_score":60,"evidence_date":""},
    ], minimum_acceptable_score=70)
    a=result["scorecard"].set_index("supplier").loc["A"]
    b=result["scorecard"].set_index("supplier").loc["B"]
    assert a["weighted_score_on_available_evidence"] == pytest.approx(84)
    assert a["evidence_coverage_percent"] == pytest.approx(100)
    assert b["weighted_score_on_available_evidence"] == pytest.approx(68.75)
    assert b["evidence_coverage_percent"] == pytest.approx(80)
    assert b["score_status"] == "BELOW_CONFIGURED_THRESHOLD"


def test_supplier_scorecard_rejects_bad_score_weights_and_duplicates():
    row={"supplier":"A","quality_score":90,"delivery_score":80,"cost_score":70,"responsiveness_score":60,"evidence_date":"2026-10-01"}
    with pytest.raises(ValueError, match="must not exceed 100"):
        score_supplier_performance([{**row,"quality_score":101}])
    with pytest.raises(ValueError, match="Duplicate supplier"):
        score_supplier_performance([row,row])
