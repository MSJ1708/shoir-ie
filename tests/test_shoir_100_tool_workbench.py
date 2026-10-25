"""App-level regression checks for the preserved Workbench and a real target action."""
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

    # The target directory is within the existing Workbench, not a new top-level page.
    inspector = at.selectbox(key="shoir_100_tool_inspector")
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
    at.button(key="tool028_run").click()
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    root_cause = at.session_state.get("shoir_tool_result_T028")
    assert root_cause is not None
    assert root_cause["status"] == "PARETO_ONLY"
    assert root_cause["total_count"] == 22
    assert root_cause["categories_to_reach_80_percent"] == 2
    assert root_cause["data_provenance"] == "SYNTHETIC_EXAMPLE"


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
        ("T054 · Material Requirements Planner", "tool054_run", "T054", "total_planned_order_receipts", 30.0),
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
        ("T041 · Weibull Reliability Analyzer", "tool041_run", "T041", "status", "WEIBULL_FIT_UNCENSORED_DATA"),
        ("T045 · Spare Parts and Criticality Planner", "tool045_run", "T045", "parts_below_reorder_point", 1),
        ("T050 · Safety Incident Trend Analyzer", "tool050_run", "T050", "total_incidents", 5),
        ("T059 · Warehouse Slotting and Picking Optimizer", "tool059_run", "T059", "assigned_count", 2),
        ("T063 · Assignment and Scheduling Optimizer", "tool063_run", "T063", "total_assignment_cost", 9.0),
        ("T077 · Energy Performance Optimizer", "tool077_run", "T077", "best_intensity_scenario", "Improved"),
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
        next(button for button in at.get("form_submit_button") if getattr(button, "key", None) == button_key).click()
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
    next(button for button in at.get("form_submit_button") if getattr(button, "key", None) == "tool087_run").click()
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
    at.button(key="tool039_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T039")
    assert result is not None
    assert result["status"] == "CAPA_REGISTER_REVIEWED"
    assert result["record_count"] == 1
    assert result["data_provenance"] == "SYNTHETIC_EXAMPLE"
    assert result["records"].iloc[0]["Workflow state"] == "IN_PROGRESS"


def test_workbench_runs_rnle_ergonomics_screen():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=90)
    at.session_state["current_user"] = "rnle-workbench-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Professional"
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.selectbox(key="shoir_100_tool_inspector").select("T046 · Ergonomics Assessment Toolkit")
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    # Scope confirmation is explicit: the method must not run on an unchecked default.
    at.checkbox(key="tool046_confirm_scope").check()
    at.button(key="tool046_run").click()
    at.run(timeout=90)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    result = at.session_state.get("shoir_tool_result_T046")
    assert result is not None, "T046 did not produce a result: " + " | ".join(str(item.value) for item in at.error)
    assert result["status"] == "CALCULATED_SCREENING"
    assert result["recommended_weight_limit_kg"] > 0
    assert result["lifting_index"] > 0
    assert result["data_provenance"] == "USER_ENTERED_UNVERIFIED"
    assert result["_workspace_persistence"] in {
        "SAVED_LOCAL_FALLBACK", "SAVED_MANAGED_WORKSPACE", "SESSION_ONLY",
        "SAVE_FAILED", "SAVE_PENDING", "SAVE_STATUS_NOT_CONFIRMED",
    }
