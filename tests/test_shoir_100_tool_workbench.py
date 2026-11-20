"""App-level regression checks for the preserved Workbench and a real target action."""
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_workbench_renders_tool_directory_and_runs_cutting_stock_action():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=45)
    at.session_state["current_user"] = "workbench-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=45)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    # The directory must not auto-run the first tool just because the page opened.
    inspector = at.selectbox(key="shoir_100_tool_inspector")
    assert inspector.value == "— Select a tool to inspect —"
    assert at.session_state.get("shoir_tool_result_T001") is None

    # The target directory is within the existing Workbench, not a new top-level page.
    inspector.select("T066 · Cutting Stock and Bin Packing")
    at.run(timeout=45)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    at.button(key="tool066_run").click()
    at.run(timeout=45)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    result = at.session_state.get("shoir_tool_result_T066")
    assert result is not None
    assert result["status"] == "OPTIMAL"
    assert result["stock_count"] == 2

    # A mapped specialist should open by the existing module selector, not
    # by bypassing the legacy renderer or module entitlement check.
    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T067 · Multi-Objective Optimization")
    at.run(timeout=45)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    at.button(key="shoir_open_mapped_T067").click()
    at.run(timeout=45)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    assert at.session_state["workbench_module_selector"] == "Optimization · Multi-Objective Optimization"


def test_workbench_selects_and_runs_time_study_and_takt_capacity():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=45)
    at.session_state["current_user"] = "workbench-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T021 · Time Study and Standard Time")
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool021_run").click()
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    time_result = at.session_state.get("shoir_tool_result_T021")
    assert time_result is not None
    assert time_result["mean_observed_time"] == pytest.approx(2.0)
    assert time_result["standard_time"] == pytest.approx(2.0 / 0.9)

    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T023 · Takt Time and Capacity Calculator")
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool023_run").click()
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    takt_result = at.session_state.get("shoir_tool_result_T023")
    assert takt_result is not None
    assert takt_result["takt_time_per_unit"] == pytest.approx(4.0)
    assert takt_result["implied_capacity_units_per_period"] == pytest.approx(160.0)




def test_workbench_denies_focused_tool_execution_to_unauthenticated_guest():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=45)
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T021 · Time Study and Standard Time")
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.button(key="tool021_run").click()
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert at.session_state.get("shoir_tool_result_T021") is None
    assert any("Sign in with an active Shoir-IE account" in str(item.value) for item in at.error)


def test_workbench_selects_and_runs_work_sampling_and_pareto_tools():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=45)
    at.session_state["current_user"] = "sampling-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T022 · Work Sampling Analyzer")
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool022_run").click()
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    work_sampling = at.session_state.get("shoir_tool_result_T022")
    assert work_sampling is not None
    assert work_sampling["total_observations"] == 100
    assert work_sampling["minimum_observations_for_target_margin"] == 385
    assert work_sampling["data_provenance"] == "SYNTHETIC_EXAMPLE"

    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T028 · Root-Cause Analysis Toolkit")
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.text_area(key="tool028_fishbone_causes").set_value(
        '{"Manpower":["Training gap"],"Machine":["Loose sensor mount"],"Method":[],"Material":[],"Measurement":[],"Environment":[]}'
    )
    # Streamlit form values should be submitted together without an intervening
    # rerun, otherwise the unsent textarea value is discarded.
    at.button(key="tool028_run").click()
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    root_cause = at.session_state.get("shoir_tool_result_T028")
    assert root_cause is not None
    assert root_cause["status"] == "PARETO_ONLY"
    assert root_cause["total_count"] == 22
    assert root_cause["categories_to_reach_80_percent"] == 2
    assert root_cause["data_provenance"] == "SYNTHETIC_EXAMPLE"
    assert root_cause["fishbone_cause_count"] == 2
    assert root_cause["fishbone_status"] == "HYPOTHESES_RECORDED"
    saved_inputs = at.session_state.get("shoir_tool_inputs_T028")
    assert saved_inputs is not None
    saved_fishbone = json.loads(saved_inputs["fishbone_causes_json"])
    assert saved_fishbone["Manpower"] == ["Training gap"]
    assert saved_fishbone["Machine"] == ["Loose sensor mount"]


def test_workbench_runs_5s_and_revisioned_kaizen_a3():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=45)
    at.session_state["current_user"] = "a3-workbench-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T029 · 5S and Workplace Audit")
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool029_run").click()
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    audit_result = at.session_state.get("shoir_tool_result_T029")
    assert audit_result is not None
    assert audit_result["overall_5s_score_pct_equal_pillar_weight"] == pytest.approx(75.0)
    assert audit_result["status"] == "AUDIT_RECORDED"
    assert audit_result["data_provenance"] == "SYNTHETIC_EXAMPLE"

    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T030 · Kaizen and A3 Improvement Manager")
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.text_input(key="tool030_title").set_value("Reduce cycle time")
    at.text_area(key="tool030_problem").set_value("Cycle time is above the target")
    at.text_input(key="tool030_metric").set_value("Cycle time")
    at.text_input(key="tool030_unit").set_value("minutes per unit")
    at.text_input(key="tool030_baseline").set_value("100")
    at.text_input(key="tool030_target").set_value("80")
    at.text_input(key="tool030_actual").set_value("90")
    at.text_area(key="tool030_root_cause").set_value("Setup standard is inconsistently followed")
    at.text_area(key="tool030_countermeasure").set_value("Standardize and audit setup steps")
    at.text_input(key="tool030_owner").set_value("Process engineer")
    at.text_input(key="tool030_due_date").set_value("2026-11-15")
    at.text_input(key="tool030_baseline_evidence").set_value("baseline-run-101")
    at.selectbox(key="tool030_status").select("In Progress")
    # These are form fields; do not force a script rerun before submitting,
    # because Streamlit forms commit input state together on submit.
    at.button(key="tool030_run").click()
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    a3 = at.session_state.get("shoir_tool_result_T030")
    assert a3 is not None, "visible Streamlit errors: " + " | ".join(str(error.value) for error in at.error)
    assert a3["target_progress_pct"] == pytest.approx(50.0)
    assert a3["revision_number"] == 1
    record_id = a3["record_id"]
    assert len(at.session_state["shoir_kaizen_a3_records"]) == 1

    at.text_input(key="tool030_record_id").set_value(record_id)
    at.text_input(key="tool030_actual").set_value("88")
    at.button(key="tool030_run").click()
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    revised = at.session_state["shoir_tool_result_T030"]
    assert revised["record_id"] == record_id
    assert revised["revision_number"] == 2
    assert len(revised["revision_history"]) == 1
    assert revised["actual_after_value"] == pytest.approx(88.0)


def test_workbench_runs_oee_capability_inventory_carbon_and_economics():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=60)
    at.session_state["current_user"] = "workbench-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=60)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T026 · OEE and Loss Analysis", "tool026_run", "T026", "oee_pct", 79.1666666667),
        ("T032 · Process Capability Analyzer", "tool032_run", "T032", "cp", 2 / 3),
        ("T055 · Inventory Policy Optimizer", "tool055_run", "T055", "economic_order_quantity_units", 353.553390593),
        ("T078 · Carbon Emissions Calculator", "tool078_run", "T078", "emissions_kg_co2e", 100.0),
        ("T081 · Engineering Economics Calculator", "tool081_run", "T081", "npv", 100 / 2.42),
    ]
    for label, button_key, tool_id, metric_key, expected in cases:
        at.selectbox(key="shoir_100_tool_inspector").select(label)
        at.run(timeout=60)
        assert not at.exception, f"{tool_id} selection raised: " + "\n".join(str(error.value) for error in at.exception)
        at.button(key=button_key).click()
        at.run(timeout=60)
        assert not at.exception, f"{tool_id} run raised: " + "\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get(f"shoir_tool_result_{tool_id}")
        assert result is not None, f"{tool_id} did not produce a structured result."
        assert result[metric_key] == pytest.approx(expected, rel=1e-5)


def test_workbench_runs_unit_spc_quality_cost_mtbf_and_abc_xyz():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=60)
    at.session_state["current_user"] = "workbench-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=60)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T016 · Unit and Currency Converter", "tool016_run", "T016", "converted_value", 10.0),
        ("T031 · Statistical Process Control", "tool031_run", "T031", "mean", 10.5),
        ("T040 · Quality Cost and Defect Analyzer", "tool040_run", "T040", "cost_of_poor_quality", 760.0),
        ("T042 · MTBF and MTTR Analyzer", "tool042_run", "T042", "mtbf_hours", 200.0),
        ("T056 · ABC/XYZ Inventory Analyzer", "tool056_run", "T056", "sku_count", 3),
    ]
    for label, button_key, tool_id, metric_key, expected in cases:
        at.selectbox(key="shoir_100_tool_inspector").select(label)
        at.run(timeout=60)
        assert not at.exception, f"{tool_id} selection raised: " + "\n".join(str(error.value) for error in at.exception)
        at.button(key=button_key).click()
        at.run(timeout=60)
        assert not at.exception, f"{tool_id} run raised: " + "\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get(f"shoir_tool_result_{tool_id}")
        assert result is not None, f"{tool_id} did not produce a structured result."
        assert result[metric_key] == pytest.approx(expected, rel=1e-5)
        if tool_id == "T056":
            assert result["classification"]["ABC"].tolist() == ["A", "B", "C"]


def test_workbench_runs_seven_additional_gated_specialist_methods():
    """Exercise each new UI form and execution route through Streamlit AppTest."""
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "focused-method-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T024 · Production Line Balancer", "tool024_run", "T024", "status", "FEASIBLE_HEURISTIC"),
        ("T025 · Bottleneck and Constraint Analyzer", "tool025_run", "T025", "bottleneck_capacity_per_period", 80.0),
        ("T027 · Value Stream Mapping Studio", "tool027_run", "T027", "status", "CALCULATED_ESTIMATE"),
        ("T038 · FMEA Manager", "tool038_run", "T038", "status", "CALCULATED_REQUIRES_ENGINEERING_REVIEW"),
        ("T070 · Queuing and Service-System Analyzer", "tool070_run", "T070", "utilization_pct", 100 * 4 / 6),
        ("T082 · Industrial Costing and Variance Analyzer", "tool082_run", "T082", "total_variance", 260.0),
        ("T083 · Evidence-Based ROI Tracker", "tool083_run", "T083", "roi_pct", 200.0),
    ]
    for label, button_key, tool_id, result_key, expected in cases:
        at.selectbox(key="shoir_100_tool_inspector").select(label)
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} selection raised: " + "\n".join(str(error.value) for error in at.exception)
        at.button(key=button_key).click()
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} run raised: " + "\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get(f"shoir_tool_result_{tool_id}")
        assert result is not None, f"{tool_id} did not produce a result; visible errors: " + " | ".join(str(item.value) for item in at.error)
        assert result[result_key] == pytest.approx(expected) if isinstance(expected, (float, int)) else result[result_key] == expected
        assert result.get("_workspace_persistence") in {"SAVED_LOCAL_FALLBACK", "SAVED_MANAGED_WORKSPACE", "SESSION_ONLY", "SAVE_FAILED", "SAVE_PENDING", "SAVE_STATUS_NOT_CONFIRMED"}
        assert result.get("status") or result.get("verification_status")


def test_workbench_runs_maintenance_hazard_mrp_and_portfolio_methods():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "operations-method-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T043 · Preventive Maintenance Planner", "tool043_run", "T043", "overdue_task_count", 1),
        ("T047 · Job Safety and Hazard Register", "tool047_run", "T047", "high_screen_score_count", 1),
        ("T054 · Material Requirements Planner", "tool054_run", "T054", "total_planned_order_receipts", 40.0),
        ("T084 · Engineering Project Portfolio Scorer", "tool084_run", "T084", "project_count", 2),
    ]
    for label, button_key, tool_id, result_key, expected in cases:
        at.selectbox(key="shoir_100_tool_inspector").select(label)
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} selection raised: " + "\n".join(str(error.value) for error in at.exception)
        at.button(key=button_key).click()
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} run raised: " + "\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get(f"shoir_tool_result_{tool_id}")
        assert result is not None, f"{tool_id} returned no result; visible errors: " + " | ".join(str(item.value) for item in at.error)
        assert result[result_key] == pytest.approx(expected)
        assert result.get("_workspace_persistence") in {
            "SAVED_LOCAL_FALLBACK", "SAVED_MANAGED_WORKSPACE", "SESSION_ONLY",
            "SAVE_FAILED", "SAVE_PENDING", "SAVE_STATUS_NOT_CONFIRMED",
        }


def test_workbench_runs_data_join_time_series_synthetic_sampling_process_mining_and_flow_balance():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "data-method-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T017 · Data Join and Merge Studio", "tool017_run", "T017", "output_rows", 3),
        ("T018 · Time-Series Data Processor", "tool018_run", "T018", "output_rows", 3),
        ("T019 · Synthetic Industrial Data Generator", "tool019_run", "T019", "row_count", 100),
        ("T034 · Acceptance Sampling Planner", "tool034_run", "T034", "status", "PLAN_FOUND"),
        ("T076 · Process Mining Analyzer", "tool076_run", "T076", "event_count", 4),
        ("T079 · Water and Waste Efficiency Analyzer", "tool079_run", "T079", "all_process_balances_close", True),
    ]
    for label, button_key, tool_id, result_key, expected in cases:
        at.selectbox(key="shoir_100_tool_inspector").select(label)
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} selection raised: " + "\n".join(str(error.value) for error in at.exception)
        at.button(key=button_key).click()
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} run raised: " + "\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get(f"shoir_tool_result_{tool_id}")
        assert result is not None, f"{tool_id} returned no result; visible errors: " + " | ".join(str(item.value) for item in at.error)
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            assert result[result_key] == pytest.approx(expected)
        else:
            assert result[result_key] == expected
        assert result.get("_workspace_persistence") in {
            "SAVED_LOCAL_FALLBACK", "SAVED_MANAGED_WORKSPACE", "SESSION_ONLY",
            "SAVE_FAILED", "SAVE_PENDING", "SAVE_STATUS_NOT_CONFIRMED",
        }


def test_workbench_runs_weibull_spares_safety_slotting_assignment_and_energy_methods():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "reliability-method-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T041 · Weibull Reliability Analyzer", "tool041_run", "T041", "status", "WEIBULL_FIT_RIGHT_CENSORED_MLE"),
        ("T045 · Spare Parts and Criticality Planner", "tool045_run", "T045", "parts_below_reorder_point", 1),
        ("T050 · Safety Incident Trend Analyzer", "tool050_run", "T050", "total_incidents", 5),
        ("T059 · Warehouse Slotting and Picking Optimizer", "tool059_run", "T059", "assigned_count", 2),
        ("T063 · Assignment and Scheduling Optimizer", "tool063_run", "T063", "total_assignment_cost", 175.0),
        ("T077 · Energy Performance Optimizer", "tool077_run", "T077", "best_intensity_scenario", "Improved"),
    ]
    for label, button_key, tool_id, result_key, expected in cases:
        at.selectbox(key="shoir_100_tool_inspector").select(label)
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} selection raised: " + "\n".join(str(error.value) for error in at.exception)
        if tool_id == "T041":
            at.text_area(key="tool041_events").set_value(
                "[true,true,false,true,false,true,true,false,true,true]"
            )
        # Submit the form once after any input edits; do not rerun before click.
        at.button(key=button_key).click()
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} run raised: " + "\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get(f"shoir_tool_result_{tool_id}")
        assert result is not None, f"{tool_id} returned no result; visible errors: " + " | ".join(str(item.value) for item in at.error)
        if tool_id == "T041":
            assert result["censored_count"] == 3
            assert result["failure_count"] == 7
            assert result["goodness_of_fit"]["formal_p_value"] is None
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            assert result[result_key] == pytest.approx(expected)
        else:
            assert result[result_key] == expected
        assert result.get("_workspace_persistence") in {
            "SAVED_LOCAL_FALLBACK", "SAVED_MANAGED_WORKSPACE", "SESSION_ONLY",
            "SAVE_FAILED", "SAVE_PENDING", "SAVE_STATUS_NOT_CONFIRMED",
        }


def test_workbench_runs_field_mapper_backlog_sop_and_supplier_methods():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "operations-planning-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T015 · Industrial Field Mapper", "tool015_run", "T015", "mapped_or_suggested_count", 4),
        ("T049 · Maintenance Backlog Optimizer", "tool049_run", "T049", "selected_count", 2),
        ("T052 · Sales and Operations Planning", "tool052_run", "T052", "ending_inventory", 10.0),
        ("T058 · Supplier Performance and Risk Scorecard", "tool058_run", "T058", "complete_score_count", 2),
    ]
    for label, button_key, tool_id, result_key, expected in cases:
        at.selectbox(key="shoir_100_tool_inspector").select(label)
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} selection raised: " + "\n".join(str(error.value) for error in at.exception)
        at.button(key=button_key).click()
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} run raised: " + "\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get(f"shoir_tool_result_{tool_id}")
        assert result is not None, f"{tool_id} returned no result; visible errors: " + " | ".join(str(item.value) for item in at.error)
        assert result[result_key] == pytest.approx(expected)
        assert result.get("_workspace_persistence") in {
            "SAVED_LOCAL_FALLBACK", "SAVED_MANAGED_WORKSPACE", "SESSION_ONLY",
            "SAVE_FAILED", "SAVE_PENDING", "SAVE_STATUS_NOT_CONFIRMED",
        }


def test_workbench_runs_regression_and_chronological_demand_forecast():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "statistical-tool-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Professional"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T036 · Regression and ANOVA Studio")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool036_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    regression = at.session_state.get("shoir_tool_result_T036")
    assert regression is not None
    assert regression["slope"] == pytest.approx(1.9)
    assert regression["data_provenance"] == "SYNTHETIC_EXAMPLE"

    at.selectbox(key="shoir_100_tool_inspector").select("T051 · Demand Forecasting Studio")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool051_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    forecast = at.session_state.get("shoir_tool_result_T051")
    assert forecast is not None
    assert forecast["selected_model"] == "Naive last value"
    assert forecast["forecast"]["Forecast"].tolist() == [28.0, 28.0, 28.0]


def test_workbench_enforces_research_pack_gate_and_runs_welch_and_monte_carlo():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "research-simulation-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Research Pack ($30 add-on)"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T037 · Hypothesis Testing Assistant")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool037_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    hypothesis = at.session_state.get("shoir_tool_result_T037")
    assert hypothesis is not None
    assert hypothesis["mean_difference_a_minus_b"] == pytest.approx(-6)
    assert hypothesis["p_value"] < 0.01

    at.session_state["user_tier"] = "Enterprise Plus Tier ($399)"
    at.selectbox(key="shoir_100_tool_inspector").select("T072 · Monte Carlo Risk Simulator")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool072_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    simulation = at.session_state.get("shoir_tool_result_T072")
    assert simulation is not None
    assert simulation["status"] == "SIMULATION_COMPLETED"
    assert simulation["iterations"] == 10000
    assert simulation["seed"] == 42
    assert "not verified ROI" in simulation["warning"]


def test_workbench_runs_t084_portfolio_weight_sensitivity():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "portfolio-sensitivity-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select(
        "T084 · Engineering Project Portfolio Scorer"
    )
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool084_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    result = at.session_state.get("shoir_tool_result_T084")
    assert result is not None
    assert result["base_winner"] == "Project A"
    assert result["sensitivity_scenario_count"] == 4
    assert result["winner_stability_pct"] == pytest.approx(100.0)
    saved_inputs = at.session_state.get("shoir_tool_inputs_T084")
    assert saved_inputs is not None
    assert saved_inputs["sensitivity_pct"] == pytest.approx(20.0)


def test_workbench_runs_t075_forecast_drift_monitor_and_persists_assumptions():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "forecast-drift-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select(
        "T075 · Forecast and Model Drift Monitor"
    )
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.text_input(key="tool075_model_id").set_value("MODEL-TEST-01")
    at.text_input(key="tool075_model_version").set_value("v1.4")
    at.text_input(key="tool075_dataset_id").set_value("DS-ABCDEF123456")
    at.text_input(key="tool075_dataset_version").set_value("2026-11-01")
    at.text_input(key="tool075_source_label").set_value("Synthetic staging test")
    at.text_input(key="tool075_period_start").set_value("2026-10-01")
    at.text_input(key="tool075_period_end").set_value("2026-10-31")
    at.button(key="tool075_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    result = at.session_state.get("shoir_tool_result_T075")
    assert result is not None
    assert result["status"] == "DRIFT_ALERT"
    assert result["mae"] == pytest.approx(7 / 3)
    assert result["observations"] == 3
    assert result["lineage_status"] == "USER_SUPPLIED_MODEL_AND_DATASET_VERSIONS"
    assert result["model_version"] == "v1.4"
    assert result["dataset_version"] == "2026-11-01"
    assert result["evaluation_period_start"] == "2026-10-01"
    assert result["lineage_verification"] == "USER_SUPPLIED_UNVERIFIED"
    saved_inputs = at.session_state.get("shoir_tool_inputs_T075")
    assert saved_inputs is not None
    assert saved_inputs["maximum_mae"] == pytest.approx(2.0)
    assert saved_inputs["trailing_window"] == 0
    assert saved_inputs["model_id"] == "MODEL-TEST-01"
    assert saved_inputs["model_version"] == "v1.4"
    assert saved_inputs["dataset_id"] == "DS-ABCDEF123456"
    assert saved_inputs["dataset_version"] == "2026-11-01"
    assert saved_inputs["evaluation_period_start"] == "2026-10-01"
    assert result.get("_workspace_persistence") in {
        "SAVED_LOCAL_FALLBACK", "SAVED_MANAGED_WORKSPACE", "SESSION_ONLY",
        "SAVE_FAILED", "SAVE_PENDING", "SAVE_STATUS_NOT_CONFIRMED",
    }


def test_workbench_runs_t085_research_pack_sample_size_and_denies_lower_tier():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    research = AppTest.from_file(page, default_timeout=90)
    research.session_state["current_user"] = "research-power-checker"
    research.session_state["authenticated"] = True
    research.session_state["user_tier"] = "Research Pack"
    from shoir_tool_registry import tier_allows_tool
    assert tier_allows_tool("Research Pack", "T085")
    research.run(timeout=90)
    assert not research.exception, "\\n".join(
        str(error.value) for error in research.exception
    )

    research.selectbox(key="shoir_100_tool_inspector").select(
        "T085 · Statistical Power and Sample-Size Planner"
    )
    research.run(timeout=90)
    assert not research.exception, "\\n".join(
        str(error.value) for error in research.exception
    )
    assert research.selectbox(key="shoir_100_tool_inspector").value == (
        "T085 · Statistical Power and Sample-Size Planner"
    )
    assert research.button(key="tool085_run") is not None, (
        "Research Pack entitlement should render the T085 form; visible errors: "
        + " | ".join(str(item.value) for item in research.error)
    )
    research.button(key="tool085_run").click()
    research.run(timeout=90)
    assert not research.exception, "\\n".join(
        str(error.value) for error in research.exception
    )
    result = research.session_state.get("shoir_tool_result_T085")
    assert result is not None
    assert result["status"] == "CALCULATED"
    assert result["effect_size_cohens_d"] == pytest.approx(0.5)
    assert result["alpha"] == pytest.approx(0.05)
    assert result["target_power"] == pytest.approx(0.80)
    assert result["required_n_per_group"] >= 2
    assert result["achieved_power"] >= result["target_power"]
    assert result.get("_workspace_persistence") in {
        "SAVED_LOCAL_FALLBACK", "SAVED_MANAGED_WORKSPACE", "SESSION_ONLY",
        "SAVE_FAILED", "SAVE_PENDING", "SAVE_STATUS_NOT_CONFIRMED",
    }
    saved_inputs = research.session_state.get("shoir_tool_inputs_T085")
    assert saved_inputs is not None
    assert saved_inputs["effect_size_cohens_d"] == pytest.approx(0.5)
    assert saved_inputs["alpha"] == pytest.approx(0.05)
    assert saved_inputs["target_power"] == pytest.approx(0.80)
    assert saved_inputs["max_n_per_group"] == 10000

    professional = AppTest.from_file(page, default_timeout=90)
    professional.session_state["current_user"] = "professional-power-checker"
    professional.session_state["authenticated"] = True
    professional.session_state["user_tier"] = "Professional Tier"
    professional.run(timeout=90)
    assert not professional.exception, "\\n".join(
        str(error.value) for error in professional.exception
    )
    professional.selectbox(key="shoir_100_tool_inspector").select(
        "T085 · Statistical Power and Sample-Size Planner"
    )
    professional.run(timeout=90)
    assert not professional.exception, "\\n".join(
        str(error.value) for error in professional.exception
    )
    professional_button_keys = {item.key for item in professional.button}
    assert "tool085_run" not in professional_button_keys, (
        "A Professional-only account must not receive the Research Pack run control."
    )
    assert professional.session_state.get("shoir_tool_result_T085") is None
    assert any(
        "Research Pack" in str(item.value) or "tier" in str(item.value).casefold()
        for item in professional.warning
    )


def test_workbench_runs_crossed_msa_and_factorial_doe():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "msa-doe-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Professional Tier"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T033 · Measurement Systems Analysis")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool033_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    msa = at.session_state.get("shoir_tool_result_T033")
    assert msa is not None
    assert msa["status"] == "CROSSED_GAGE_RR_SCREENED"
    assert msa["part_count"] == 2
    assert msa["operator_count"] == 2
    assert msa["number_of_distinct_categories"] == 12

    at.selectbox(key="shoir_100_tool_inspector").select("T035 · Design of Experiments")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool035_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    doe = at.session_state.get("shoir_tool_result_T035")
    assert doe is not None
    effects = doe["effects"].set_index("Term")
    assert effects.loc["A", "Estimated effect (high − low)"] == pytest.approx(4)
    assert effects.loc["B", "Estimated effect (high − low)"] == pytest.approx(6)


def test_workbench_runs_discrete_event_simulation():
    """Verify T071 is wired to the shared Workbench and keeps assumptions explicit."""
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "des-simulation-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Research Pack"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T071 · Discrete-Event Simulation")
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    at.button(key="tool071_run").click()
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T071")
    assert result is not None
    assert result["status"] == "DISCRETE_EVENT_SIMULATION_COMPLETED"
    assert result["job_count"] == 50
    assert result["warmup_jobs_excluded_from_performance_metrics"] == 5
    assert result["replications"] == 10
    assert result["station_count"] == 2
    assert len(result["replication_results"]) == 10
    assert len(result["station_summary"]) == 2
    assert result["data_provenance"] == "SYNTHETIC_EXAMPLE"


def test_workbench_runs_solver_diagnostics():
    """Verify T062 uses the current Workbench, solver engine and execution-time tier gate."""
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "solver-diagnostics-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Professional"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T062 · Constraint and Solver Diagnostics")
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    at.button(key="tool062_run").click()
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T062")
    assert result is not None
    assert result["status"] == "OPTIMAL_FEASIBLE"
    assert result["solver_status"] == "Optimal"
    assert result["objective_value"] == pytest.approx(8.0)
    assert result["independent_feasibility_check"] is True
    assert result["constraint_diagnostics"]["Status"].eq("SATISFIED").all()
    assert result["data_provenance"] == "SYNTHETIC_EXAMPLE"


def test_workbench_builds_downloadable_reproducibility_pack():
    """Exercise source-result selection, Research Pack gate, ZIP creation and download wiring."""
    import io
    import zipfile
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "reproducibility-pack-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Research Pack"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T021 · Time Study and Standard Time")
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    at.button(key="tool021_run").click()
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    assert at.session_state.get("shoir_tool_result_T021") is not None

    at.selectbox(key="shoir_100_tool_inspector").select("T087 · Reproducibility Pack Generator")
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    source = at.selectbox(key="tool087_source_id")
    assert "T021 · Time Study and Standard Time" in source.options
    # Select the underlying stable target ID. The widget's format_func renders
    # the human-readable label; feeding that label back into the widget causes
    # AppTest to apply the formatter twice and creates an invalid value.
    source.set_value("T021")
    at.checkbox(key="tool087_include_inputs").set_value(True)
    at.checkbox(key="tool087_include_tables").set_value(True)
    assert at.checkbox(key="tool087_include_inputs").value is True
    assert at.checkbox(key="tool087_include_tables").value is True
    # Form controls are committed together on submit; do not run a separate
    # app cycle between editing the form and submitting it.
    at.button(key="tool087_run").click()
    at.run(timeout=90)
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T087")
    payload = at.session_state.get("shoir_tool_bundle_bytes_T087")
    assert result is not None
    assert result["status"] == "REPRODUCIBILITY_PACK_CREATED"
    assert isinstance(payload, bytes) and payload.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
        assert "manifest.json" in archive.namelist()
        assert "SHA256SUMS.txt" in archive.namelist()
        assert "input_snapshot_redacted.json" in archive.namelist()
    assert result["bundle_sha256"]
    assert any(button.key == "tool087_download" for button in at.get("download_button"))


def test_workbench_runs_facility_location_flow():
    """Exercise T069's form, execution-time tier gate and structured result output."""
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "facility-location-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T069 · Network Flow and Location Optimization")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool069_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T069")
    assert result is not None
    assert result["status"] == "OPTIMAL_FEASIBLE"
    assert result["objective_value"] == pytest.approx(21.0)
    assert result["independent_feasibility_check"] is True
    assert result["data_provenance"] == "SYNTHETIC_EXAMPLE"


def test_workbench_student_practice_mode_checks_answers_and_shows_solution():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "student-practice-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Starter"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T089 · Student Learning and Practice Mode")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.number_input(key="tool089_answer").set_value(2.0)
    at.button(key="tool089_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T089")
    assert result is not None
    assert result["is_correct"] is True
    assert result["expected_answer"] == pytest.approx(2.0)
    assert result["data_provenance"] == "SYNTHETIC_EXERCISE"


def test_workbench_guided_study_wizard_returns_gated_step_plan():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "guided-study-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Starter"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T002 · Guided Study Wizard")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.text_input(key="tool002_available_fields").set_value(
        "source_file, validated_dataset, process_table, demand, time_unit"
    )
    at.button(key="tool002_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T002")
    assert result is not None
    assert result["status"] == "GUIDED_PLAN_CREATED"
    rows = result["steps"].set_index("Tool ID")
    assert rows.loc["T011", "Step status"] in ("READY", "COMPLETED_IN_SESSION")
    assert rows.loc["T025", "Step status"] == "TIER_RESTRICTED"


def test_workbench_runs_equipment_anomaly_monitor_and_labels_example_data():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "anomaly-monitor-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T048 · Equipment Anomaly Monitor")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool048_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T048")
    assert result is not None
    assert result["status"] == "ANOMALIES_DETECTED"
    assert result["anomaly_count"] == 1
    assert result["data_provenance"] == "SYNTHETIC_EXAMPLE"


def test_workbench_capa_8d_register_reports_completeness_and_overdue_state():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "capa-register-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Mid-Tier Pro"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T039 · CAPA and 8D Manager")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    # Freeze the review date so the overdue-state assertion is independent of
    # the CI runner's actual wall-clock date.
    at.text_input(key="tool039_as_of_date").set_value("2026-11-03")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool039_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T039")
    assert result is not None
    assert result["status"] == "CAPA_REGISTER_REVIEWED"
    assert result["record_count"] == 1
    assert result["data_provenance"] == "SYNTHETIC_EXAMPLE"
    assert result["records"].iloc[0]["Workflow state"] == "OVERDUE"


def _open_tool_for_app_test(at, tool_label: str) -> None:
    at.selectbox(key="shoir_100_tool_inspector").select(tool_label)
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)


def test_workbench_runs_rcm_network_calibration_disruption_and_kpi_tools():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "foundation-tools-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    # T044: RCM decision candidates, including specialist escalation.
    _open_tool_for_app_test(at, "T044 · Reliability-Centered Maintenance Assistant")
    at.button(key="tool044_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    rcm = at.session_state["shoir_tool_result_T044"]
    assert rcm["status"] == "RCM_SCREEN_COMPLETED_REQUIRES_SPECIALIST_APPROVAL"
    assert rcm["task_candidate_count"] == 2
    assert rcm["specialist_review_count"] == 3
    assert "SPECIALIST_SAFETY_REVIEW" in rcm["decision_tree"]["Recommended task candidate"].tolist()

    # T060: deterministic transport optimization with explicit shortage reporting.
    _open_tool_for_app_test(at, "T060 · Supply Chain Network Planner")
    at.button(key="tool060_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    network = at.session_state["shoir_tool_result_T060"]
    assert network["status"] == "OPTIMAL"
    assert network["data_provenance"] == "USER_ENTERED_UNVERIFIED"
    assert network["total_unmet_demand"] == pytest.approx(0)
    assert network["total_units_shipped"] == pytest.approx(150)

    # T074: the sample is deliberately linear so the calibration fit is known.
    _open_tool_for_app_test(at, "T074 · Digital Twin Calibration Studio")
    at.text_input(key="tool074_simulated").set_value("1, 2, 3, 4, 5, 6")
    at.text_input(key="tool074_measured").set_value("2.5, 4.5, 6.5, 8.5, 10.5, 12.5")
    at.slider(key="tool074_fraction").set_value(0.67)
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool074_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    calibration = at.session_state["shoir_tool_result_T074"]
    assert calibration["status"] == "CALIBRATION_FIT_WITH_CHRONOLOGICAL_HOLDOUT"
    assert calibration["calibration_slope"] == pytest.approx(2.0)
    assert calibration["holdout_metrics"]["rmse"] == pytest.approx(0.0, abs=1e-8)

    # T080: reproducible synthetic shock study; never label this as live.
    _open_tool_for_app_test(at, "T080 · Industrial Disruption Simulator")
    at.number_input(key="tool080_iterations").set_value(10)
    at.number_input(key="tool080_seed").set_value(17)
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool080_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    disruption = at.session_state["shoir_tool_result_T080"]
    assert disruption["status"] == "SYNTHETIC_DISRUPTION_STRESS_TEST"
    assert disruption["iterations"] == 10
    assert disruption["data_provenance"] == "USER_ENTERED_UNVERIFIED"

    # T094: KPI breach must be visible and source freshness must be evaluated.
    _open_tool_for_app_test(at, "T094 · KPI Dashboard and Alert Center")
    at.text_area(key="tool094_records").set_value(
        '[{"kpi":"OEE","value":80,"unit":"%","observed_at":"2026-11-06T17:50:00Z","source":"synthetic-ci"}]'
    )
    at.text_area(key="tool094_rules").set_value(
        '[{"rule_id":"oee-floor","kpi":"OEE","operator":"<","threshold":85,"severity":"WARNING"}]'
    )
    at.text_input(key="tool094_as_of").set_value("2026-11-06T18:00:00Z")
    # These controls are inside a Streamlit form. Submit the form before
    # triggering a separate rerun; an intermediate AppTest rerun resets
    # unsubmitted form values to their defaults.
    at.button(key="tool094_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    # The focused-tool handler deliberately catches calculation errors and
    # displays them in the UI. Check that channel before reading the result;
    # otherwise a genuine T094 failure is obscured by a secondary KeyError.
    displayed_errors = [str(element.value) for element in at.error]
    assert not displayed_errors, (
        "T094 execution displayed an application error despite no uncaught "
        "Streamlit exception:\\n" + "\\n".join(displayed_errors)
    )
    assert "shoir_tool_result_T094" in at.session_state, (
        "T094 completed without raising but did not persist its result."
    )
    alerts = at.session_state["shoir_tool_result_T094"]
    assert alerts["open_alert_count"] == 1
    assert alerts["new_alert_count"] == 1
    assert alerts["alerts"].iloc[0]["Event"] == "NEW"


def test_workbench_plugin_contract_and_personal_backup_tools_are_not_fake_routes():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "plugin-governance-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    _open_tool_for_app_test(at, "T097 · API, SDK, and Plugin Toolkit")
    at.selectbox(key="tool097_plugin").select("REST connector adapter")
    at.text_area(key="tool097_payload").set_value("{}")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool097_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    plugin = at.session_state["shoir_tool_result_T097"]
    assert plugin["status"] == "PLUGIN_CONTRACT_VALIDATED"
    assert plugin["payload_valid"] is True
    assert plugin["execution_status"] == "METADATA_ONLY"
    assert "No external endpoint was called" in plugin["warning"]

    _open_tool_for_app_test(at, "T099 · Data Governance and Recovery Center")
    at.radio(key="tool099_action").set_value("Export personal workspace backup")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool099_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    governance = at.session_state["shoir_tool_result_T099"]
    backup = at.session_state["shoir_tool_bundle_bytes_T099"]
    assert governance["status"] == "PERSONAL_WORKSPACE_BACKUP_CREATED"
    assert backup.startswith(b"{")
    assert governance["backup_manifest"]["owner_username_lc"] == "plugin-governance-checker"

def test_workbench_recovery_tool_applies_a_verified_revision_snapshot():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "recovery-tool-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Starter"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    _open_tool_for_app_test(at, "T006 · Undo, Redo, and Recovery")
    at.button(key="tool006_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    result = at.session_state["shoir_tool_result_T006"]
    assert result["status"] == "RECOVERY_ACTION_APPLIED"
    assert result["action"] == "snapshot"
    assert result["current_state"]["dataset"] == "SYNTHETIC-example"
    assert result["can_undo"] is False
    assert len(result["history"]) == 1



def test_workbench_exposes_and_runs_t096_and_t098_configuration_checks():
    """T096/T098 must have real focused UI routes without fake live integrations."""
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "workbench-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.session_state["user_role"] = "Enterprise Admin"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T096 · Integration Management Center")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert at.selectbox(key="tool096_action").value == "Inspect configured connector settings"
    at.button(key="tool096_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    integration = at.session_state.get("shoir_tool_result_T096")
    assert integration is not None
    assert integration["status"] == "CONFIGURATION_INSPECTED"
    assert integration["connected_count"] == 0
    assert all(
        item["status"] in {
            "NOT_CONNECTED_CONFIGURATION_INCOMPLETE",
            "READY_FOR_AUTHORIZED_STAGING_TEST",
        }
        for item in integration["profile_records"]
    )
    assert all(item["last_test_at"] is None for item in integration["profile_records"])

    inspector = at.selectbox(key="shoir_100_tool_inspector")
    inspector.select("T098 · Enterprise Identity and Audit Center")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.button(key="tool098_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    identity = at.session_state.get("shoir_tool_result_T098")
    assert identity is not None
    assert identity["tool_id"] == "T098"
    assert identity["provider"].startswith("OIDC-compatible identity provider")
    assert identity["sso_active"] is False
    assert identity["mfa_active"] is False
    assert identity["provider_authentication_tested"] is False
    assert identity["provider_mfa_evidence_verified"] is False
    assert all(row["value_exposed"] is False for row in identity["environment_variables"].to_dict("records"))


def test_workbench_runs_kpi_alerts_and_persists_deduplicated_state():
    """Exercise T094's real Workbench form, result key, and open-alert deduplication."""
    from streamlit.testing.v1 import AppTest
    from workspace_persistence import _snapshot, _unpack

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "workbench-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T094 · KPI Dashboard and Alert Center")
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    at.text_area(key="tool094_records").set_value(
        '[{"kpi":"Scrap Rate","value":4,"unit":"%","observed_at":"2026-11-12T09:00:00Z","source":"Synthetic acceptance fixture"}]'
    )
    at.text_area(key="tool094_rules").set_value(
        '[{"rule_id":"scrap-high","kpi":"Scrap Rate","operator":"gt","threshold":3,"severity":"HIGH"}]'
    )
    at.text_input(key="tool094_as_of").set_value("2026-11-12T10:00:00Z")
    at.button(key="tool094_run").click()
    at.run(timeout=90)
    assert not at.exception, "T094 first run raised: " + "\n".join(str(error.value) for error in at.exception)

    first = at.session_state.get("shoir_tool_result_T094")
    assert first is not None, "T094 did not populate shoir_tool_result_T094."
    assert first["kpi_count"] == 1
    assert first["breached_kpi_count"] == 1
    assert first["new_alert_count"] == 1
    assert first["alert_records"][0]["rule_id"] == "scrap-high"
    assert first["alert_records"][0]["severity"] == "CRITICAL"
    assert first["alert_records"][0]["source"] == "Synthetic acceptance fixture"
    assert at.session_state["shoir_kpi_open_alert_records"][0]["state"] == "OPEN"

    # The app persists the whole eligible workspace snapshot. Prove both the
    # T094 result and its deduplication state survive the same serializer used
    # by the fresh-session workspace loader, including DataFrame result values.
    saved_workspace = _snapshot(at.session_state)
    assert "shoir_tool_result_T094" in saved_workspace
    assert "shoir_kpi_open_alert_records" in saved_workspace
    restored_workspace = {
        key: _unpack(value) for key, value in saved_workspace.items()
    }
    assert restored_workspace["shoir_kpi_open_alert_records"] == (
        at.session_state["shoir_kpi_open_alert_records"]
    )
    restored_result = restored_workspace["shoir_tool_result_T094"]
    assert restored_result["open_alert_count"] == 1
    assert restored_result["alert_records"][0]["alert_id"] == (
        first["alert_records"][0]["alert_id"]
    )

    at.button(key="tool094_run").click()
    at.run(timeout=90)
    assert not at.exception, "T094 repeat run raised: " + "\n".join(str(error.value) for error in at.exception)

    repeated = at.session_state.get("shoir_tool_result_T094")
    assert repeated is not None
    assert repeated["new_alert_count"] == 0
    assert repeated["alert_records"][0]["new_alert"] is False

    # A fresh reading back within the limit resolves the prior alert explicitly.
    at.text_area(key="tool094_records").set_value(
        '[{"kpi":"Scrap Rate","value":2,"unit":"%","observed_at":"2026-11-12T10:05:00Z","source":"Synthetic acceptance fixture"}]'
    )
    at.text_input(key="tool094_as_of").set_value("2026-11-12T10:10:00Z")
    at.button(key="tool094_run").click()
    at.run(timeout=90)
    assert not at.exception, "T094 recovery run raised: " + "\\n".join(str(error.value) for error in at.exception)
    recovered = at.session_state.get("shoir_tool_result_T094")
    assert recovered is not None
    assert recovered["resolved_alert_count"] == 1
    assert recovered["open_alert_count"] == 0
    assert recovered["alert_records"] == []
    assert recovered["alerts"].iloc[0]["Event"] == "RESOLVED"
    assert at.session_state.get("shoir_kpi_open_alert_records", []) == []


def test_workbench_t094_future_dated_measurement_does_not_open_alert():
    """A future observation must remain visible but cannot create an active alert."""
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "workbench-future-kpi-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T094 · KPI Dashboard and Alert Center")
    at.run(timeout=90)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    at.text_area(key="tool094_records").set_value(
        '[{"kpi":"Future Scrap Rate","value":9,"unit":"%","observed_at":"2026-11-15T12:30:00Z","source":"Synthetic future-timestamp fixture"}]'
    )
    at.text_area(key="tool094_rules").set_value(
        '[{"rule_id":"future-scrap-high","kpi":"Future Scrap Rate","operator":"gt","threshold":3,"severity":"CRITICAL"}]'
    )
    at.text_input(key="tool094_as_of").set_value("2026-11-15T12:00:00Z")
    at.button(key="tool094_run").click()
    at.run(timeout=90)
    assert not at.exception, "T094 future timestamp run raised: " + "\n".join(str(error.value) for error in at.exception)

    result = at.session_state.get("shoir_tool_result_T094")
    assert result is not None
    assert result["future_kpi_count"] == 1
    assert result["breached_kpi_count"] == 0
    assert result["open_alert_count"] == 0
    assert result["new_alert_count"] == 0
    assert result["alert_records"] == []
    assert at.session_state.get("shoir_kpi_open_alert_records", []) == []
    assert result["kpis"].iloc[0]["status"] == "FUTURE_TIMESTAMP"



def test_workbench_runs_canonical_lp_milp_pareto_and_robust_tools():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "optimization-tool-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T061 · Linear and Mixed-Integer Optimization", "tool061_run", "shoir_tool_result_T061"),
        ("T067 · Multi-Objective Optimization", "tool067_run", "shoir_tool_result_T067"),
        ("T068 · Sensitivity and Robust Optimization", "tool068_run", "shoir_tool_result_T068"),
        ("T073 · What-If Scenario Manager", "tool073_run", "shoir_tool_result_T073"),
    ]
    for label, button_key, result_key in cases:
        at.selectbox(key="shoir_100_tool_inspector").select(label)
        at.run(timeout=90)
        assert not at.exception, f"{label} form failed: " + "\\n".join(str(error.value) for error in at.exception)
        at.button(key=button_key).click()
        at.run(timeout=90)
        assert not at.exception, f"{label} execution failed: " + "\\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get(result_key)
        assert result is not None, (
            f"{label} did not return a result. "
            f"Streamlit errors: {[str(item.value) for item in at.error]}"
        )
        assert result["tool_id"] == label.split(" · ", 1)[0]
    assert at.session_state["shoir_tool_result_T067"]["status"] == "PARETO_TRADEOFFS_ANALYZED"
    assert at.session_state["shoir_tool_result_T068"]["status"] == "ROBUST_OPTIMAL"
    assert at.session_state["shoir_tool_result_T073"]["status"] == "SCENARIO_SET_SAVED"


def test_workbench_runs_owner_scoped_project_research_and_decision_registers():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "canonical-record-tool-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T004 · Engineering Project Manager", "tool004_run", "T004", "PROJECT_CREATED"),
        ("T005 · Autosave and Version History", "tool005_run", "T005", "PROJECT_SNAPSHOT_CREATED"),
        ("T086 · Hypothesis and Evidence Register", "tool086_run", "T086", "HYPOTHESIS_PROTOCOL_RECORDED"),
        ("T092 · Decision Register and Approval Workflow", "tool092_run", "T092", "DECISION_DRAFT_CREATED"),
    ]
    for label, button_key, tool_id, expected_status in cases:
        required_tier = "Research Pack" if tool_id == "T086" else "Enterprise Plus Tier"
        if at.session_state.get("user_tier") != required_tier:
            at.session_state["user_tier"] = required_tier
            at.run(timeout=90)
            assert not at.exception, f"{tool_id} tier refresh failed: " + "\\n".join(str(error.value) for error in at.exception)
        at.selectbox(key="shoir_100_tool_inspector").select(label)
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} form failed: " + "\\n".join(str(error.value) for error in at.exception)
        at.button(key=button_key).click()
        at.run(timeout=90)
        assert not at.exception, f"{tool_id} execution failed: " + "\\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get("shoir_tool_result_" + tool_id)
        assert result is not None
        assert result["status"] == expected_status


def test_workbench_routes_facility_layout_to_existing_persistent_studio():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "facility-layout-canonical-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Starter"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.selectbox(key="shoir_100_tool_inspector").select("T065 · Facility Layout and SLP Studio")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert any("Facility Layout & Warehousing Studio" in str(element.value) for element in at.markdown)
    assert any("Department register" in str(element.value) for element in at.markdown)


def test_workbench_routes_team_collaboration_to_staging_gated_rbac_ui():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "team-workspace-canonical-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.selectbox(key="shoir_100_tool_inspector").select("T091 · Team Collaboration and Review")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert any("enabled only in the authorized staging environment" in str(element.value) for element in at.info)


def test_workbench_t095_builds_sanitized_xlsx_from_entitled_source_result():
    from io import BytesIO
    import pandas as pd
    from openpyxl import load_workbook
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "report-export-canonical-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Professional"
    at.session_state["shoir_tool_result_T083"] = {
        "tool_id": "T083",
        "status": "SYNTHETIC_TEST_RESULT",
        "data_provenance": "SYNTHETIC",
        "metrics": pd.DataFrame({
            "Metric": ["Scrap rate", "First-pass yield"],
            "Value": [2.5, 97.5],
            "api_token": ["must-not-export-1", "must-not-export-2"],
        }),
        "warning": "Synthetic result only.",
    }
    at.session_state["shoir_tool_inputs_T083"] = {"synthetic": True, "run_id": "SYN-RUN-095"}
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T095 · Verified Reporting and Export Studio")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.selectbox(key="tool095_source_id").select("T083")
    at.run(timeout=90)
    at.button(key="tool095_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    result = at.session_state.get("shoir_tool_result_T095")
    assert result is not None, "T095 did not return a result: " + " | ".join(str(item.value) for item in at.error)
    assert result["status"] == "REPORT_ARTIFACT_BUILT"
    assert result["format"] == "XLSX"
    assert result["source_tool_id"] == "T083"
    assert result["redacted_column_count"] == 1
    payload = at.session_state.get("shoir_tool_bundle_bytes_T095")
    assert isinstance(payload, bytes) and payload[:2] == b"PK"
    workbook = load_workbook(BytesIO(payload), data_only=True)
    try:
        rows = list(workbook["metrics"].values)
        values = str(rows)
        assert "Scrap rate" in values
        assert "First-pass yield" in values
        assert "must-not-export" not in values
        assert "api_token" not in values
    finally:
        workbook.close()

def test_workbench_routes_and_executes_the_nine_previously_mapped_only_tools():
    """Exercise the new canonical IDs through the real Workbench renderer."""
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=120)
    at.session_state["current_user"] = "canonical-nine-route-test-user"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Starter"
    at.run(timeout=120)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)

    cases = [
        ("T001", "Personalized Engineering Home", "Starter"),
        ("T003", "Universal Search and Command Center", "Starter"),
        ("T008", "Formula and Assumption Inspector", "Starter"),
        ("T053", "Finite-Capacity Production Scheduler", "Professional"),
        ("T057", "Workforce and Shift Planner", "Professional"),
        ("T064", "Vehicle Routing Optimizer", "Mid-Tier Pro"),
        ("T088", "Research and Literature Evidence Matrix", "Research Pack"),
        ("T090", "Research Report and Methods Builder", "Research Pack"),
        ("T093", "Cross-Module Workflow Builder", "Enterprise"),
    ]
    for tool_id, name, tier in cases:
        if at.session_state.get("user_tier") != tier:
            at.session_state["user_tier"] = tier
            at.run(timeout=120)
            assert not at.exception, f"{tool_id} tier refresh failed: " + "\n".join(str(error.value) for error in at.exception)

        at.selectbox(key="shoir_100_tool_inspector").select(f"{tool_id} · {name}")
        at.run(timeout=120)
        assert not at.exception, f"{tool_id} route render failed: " + "\n".join(str(error.value) for error in at.exception)

        if tool_id == "T003":
            # T003 itself is Starter-accessible. "home" gives it a result that
            # is also available to Starter instead of relying on a Professional
            # inventory capability.
            at.text_input(key="canonical_t003_query").set_value("home")
        elif tool_id == "T090":
            # Streamlit form values are submitted together. Do not rerun the
            # page between editing and submitting, or unsubmitted widget
            # values may be discarded by AppTest.
            at.text_input(key="canonical_t090_title").set_value("Synthetic engineering report")
            at.text_area(key="canonical_t090_objective").set_value("Document the supplied study objective.")
            at.text_area(key="canonical_t090_method").set_value("Use the supplied calculation method.")
            at.text_area(key="canonical_t090_limits").set_value(
                "Supplied results and sources have not been independently verified."
            )

        run_button = at.button(key="canonical_run_" + tool_id)
        assert run_button is not None, f"{tool_id} submit control was not rendered."
        run_button.click()
        at.run(timeout=120)
        assert not at.exception, f"{tool_id} execution failed: " + "\n".join(str(error.value) for error in at.exception)
        result = at.session_state.get("shoir_tool_result_" + tool_id)
        visible_errors = " | ".join(str(item.value) for item in at.error)
        assert result is not None, f"{tool_id} did not write its canonical result key. Visible UI errors: {visible_errors}"
        if tool_id == "T003":
            assert result["result_count"] >= 1
            assert "T001" in set(result["results"]["id"])
        assert result["tool_id"] == tool_id
        assert result["status"] == "COMPLETED_WITH_DECLARED_LIMITATIONS"
        assert result.get("_workspace_persistence") in {
            "SESSION_ONLY", "SAVED_MANAGED_WORKSPACE", "SAVED_LOCAL_FALLBACK",
            "SAVE_FAILED", "SAVE_STATUS_NOT_CONFIRMED", "SAVE_PENDING",
        }


def test_workbench_t046_automatically_calculates_niosh_table_multipliers():
    """T046 defaults to Table 5/7 lookup and records user-entered provenance."""
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "rnle-screening-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Professional"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T046 · Ergonomics Assessment Toolkit")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.selectbox(key="tool046_duration").select("Short (≤ 1 hour)")
    at.checkbox(key="tool046_scope_confirmed").set_value(True)
    at.button(key="tool046_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    result = at.session_state.get("shoir_tool_result_T046")
    assert result is not None
    assert result["status"] == "CALCULATED_SCREENING"
    assert result["frequency_multiplier"] == pytest.approx(0.94)
    assert result["endpoint_results"]["origin"]["coupling_multiplier"] == pytest.approx(1.0)
    assert result["data_provenance"] == "USER_ENTERED_UNVERIFIED"
    assert "not been independently verified" in result["provenance_warning"]
    assert any("medical determination" in warning.casefold() for warning in result["warnings"])


def test_workbench_t046_fails_closed_without_explicit_rnle_scope_confirmation():
    """T046 cannot calculate until the operator confirms the supported task scope."""
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "rnle-scope-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Professional"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T046 · Ergonomics Assessment Toolkit")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    at.selectbox(key="tool046_duration").select("Short (≤ 1 hour)")
    at.button(key="tool046_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert at.session_state.get("shoir_tool_result_T046") is None
    assert any("Confirm the supported single-task" in str(item.value) for item in at.error)

