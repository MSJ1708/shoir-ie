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
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
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
    at.run(timeout=45)
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
