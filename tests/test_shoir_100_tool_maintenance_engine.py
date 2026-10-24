"""Golden and boundary fixtures for the maintenance backlog MILP (T049)."""
import pandas as pd
import pytest

from shoir_100_tool_maintenance_engine import optimize_maintenance_backlog


def test_maintenance_backlog_milp_respects_skills_windows_and_slot_capacity():
    jobs=pd.DataFrame([
        {"work_order_id":"WO-A","asset_id":"A1","description":"Critical repair","estimated_hours":3.0,"criticality_1_to_5":5,"required_skill":"Mechanical","required_window":"Day","due_date":"2026-10-25"},
        {"work_order_id":"WO-B","asset_id":"A2","description":"Inspection","estimated_hours":2.0,"criticality_1_to_5":4,"required_skill":"Mechanical","required_window":"Day","due_date":"2026-11-05"},
        {"work_order_id":"WO-C","asset_id":"A3","description":"Lubrication","estimated_hours":2.0,"criticality_1_to_5":3,"required_skill":"Mechanical","required_window":"Day","due_date":"2026-10-29"},
        {"work_order_id":"WO-D","asset_id":"A4","description":"Electrical repair","estimated_hours":2.0,"criticality_1_to_5":5,"required_skill":"Electrical","required_window":"Night","due_date":"2026-10-25"},
    ])
    slots=pd.DataFrame([
        {"slot_id":"DAY-MECH-4H","skill":"Mechanical","downtime_window":"Day","available_hours":4.0},
        {"slot_id":"NIGHT-ELEC-3H","skill":"Electrical","downtime_window":"Night","available_hours":3.0},
    ])
    result=optimize_maintenance_backlog(jobs,slots,as_of_date="2026-10-24")
    assert result["status"]=="OPTIMAL"
    assert result["metrics"]["scheduled_count"]==3
    plan=result["work_plan"].set_index("work_order_id")
    assert plan.loc["WO-D","schedule_status"]=="SCHEDULED"
    assert plan.loc["WO-D","assigned_slot_id"]=="NIGHT-ELEC-3H"
    assert plan.loc["WO-B","schedule_status"]=="SCHEDULED"
    assert plan.loc["WO-C","schedule_status"]=="SCHEDULED"
    utilization=result["slot_utilization"].set_index("slot_id")
    assert utilization.loc["DAY-MECH-4H","scheduled_hours"]==pytest.approx(4)
    assert utilization.loc["NIGHT-ELEC-3H","scheduled_hours"]==pytest.approx(2)


def test_maintenance_backlog_marks_unmatched_and_capacity_tradeoff():
    jobs=pd.DataFrame([
        {"work_order_id":"WO-A","asset_id":"A1","description":"Repair","estimated_hours":3.0,"criticality_1_to_5":5,"required_skill":"Mechanical","required_window":"Day","due_date":""},
        {"work_order_id":"WO-B","asset_id":"A2","description":"Repair","estimated_hours":2.0,"criticality_1_to_5":4,"required_skill":"Mechanical","required_window":"Day","due_date":""},
        {"work_order_id":"WO-X","asset_id":"AX","description":"Repair","estimated_hours":1.0,"criticality_1_to_5":5,"required_skill":"Electrical","required_window":"Night","due_date":""},
    ])
    slots=pd.DataFrame([{"slot_id":"DAY-4H","skill":"Mechanical","downtime_window":"Day","available_hours":4.0}])
    result=optimize_maintenance_backlog(jobs,slots,as_of_date="2026-10-24")
    plan=result["work_plan"].set_index("work_order_id")
    assert plan.loc["WO-X","schedule_status"]=="NOT_SCHEDULED_NO_ELIGIBLE_SKILL_WINDOW"
    assert plan.loc["WO-A","schedule_status"]=="SCHEDULED"
    assert plan.loc["WO-B","schedule_status"]=="NOT_SCHEDULED_CAPACITY_TRADEOFF"
    assert (plan["schedule_status"]=="SCHEDULED").sum()==1


def test_maintenance_backlog_rejects_duplicate_orders_invalid_time_and_bad_criticality():
    job={"work_order_id":"WO-A","asset_id":"A1","description":"Repair","estimated_hours":2.0,"criticality_1_to_5":4,"required_skill":"Any","required_window":"Any","due_date":""}
    slots=[{"slot_id":"S1","skill":"Any","downtime_window":"Any","available_hours":4.0}]
    with pytest.raises(ValueError,match="must be non-empty and unique"):
        optimize_maintenance_backlog([job,job],slots,as_of_date="2026-10-24")
    with pytest.raises(ValueError,match="must be finite and positive"):
        optimize_maintenance_backlog([{**job,"estimated_hours":0}],slots,as_of_date="2026-10-24")
    with pytest.raises(ValueError,match="whole number from 1 to 5"):
        optimize_maintenance_backlog([{**job,"criticality_1_to_5":7}],slots,as_of_date="2026-10-24")
