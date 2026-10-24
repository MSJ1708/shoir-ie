"""Authenticated AppTest smoke checks for the additive 100-tool library.

These tests verify that the routed capability form renders and runs in the actual
Streamlit page with disposable in-memory session state. They do not substitute for
the separate hosted-browser, durable-persistence or production integration gates.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "Engineering_Tool_Library.py"


def _authed_library(tier="Research Pack"):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(PAGE, default_timeout=60)
    at.session_state["authenticated"] = True
    at.session_state["current_user"] = "disposable-tool-library-checker"
    # Research Pack inherits ordinary capabilities through Enterprise, but not
    # Enterprise Plus. This allows testing of all the targets in this tranche.
    at.session_state["user_tier"] = tier
    at.run(timeout=60)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    return at


def _open(at, tool_id, name):
    at.selectbox(key="tool_library_detail").select(f"{tool_id} · {name}")
    at.run(timeout=60)
    assert not at.exception, (
        f"{tool_id} form failed to render:\n"
        + "\n".join(str(error.value) for error in at.exception)
    )


def _run(at, tool_id):
    button = at.button(key=f"{tool_id}_run_button")
    button.click()
    at.run(timeout=60)
    assert not at.exception, (
        f"{tool_id} action failed:\n"
        + "\n".join(str(error.value) for error in at.exception)
    )
    result = at.session_state.get(f"shoir_{tool_id}_result")
    assert result is not None, (
        f"{tool_id} returned no result; visible errors: "
        + " | ".join(str(error.value) for error in at.error)
    )
    return result["result"]


def test_tool_library_public_preview_is_read_only_without_authentication():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(PAGE, default_timeout=60)
    at.run(timeout=60)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert any("Engineering Tool Library" in item.value for item in at.title)
    assert any("PUBLIC READ-ONLY PREVIEW" in item.value for item in at.info)

    # Public visitors can inspect a capability contract, but cannot execute it.
    at.selectbox(key="tool_library_detail").select("T016 · Unit and Currency Converter")
    at.run(timeout=60)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert any("cannot execute calculations" in item.value.lower() for item in at.info)
    assert not any(getattr(button, "key", None) == "T016_run_button" for button in at.button)


def test_public_explore_modules_links_to_the_grouped_library():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("with auth_tab3:")
    section = source[start:start + 30000]
    assert "st.page_link(" in section
    assert '"pages/Engineering_Tool_Library.py"' in section
    assert "Browse the 100-tool Engineering Library" in section
def test_extended_specialist_forms_render_and_run_with_golden_defaults():
    at = _authed_library()

    _open(at, "T016", "Unit and Currency Converter")
    unit_result = _run(at, "T016")
    assert unit_result["converted_value"] == pytest.approx(1.0)

    _open(at, "T022", "Work Sampling Analyzer")
    sample_result = _run(at, "T022")
    assert sample_result["total_observations"] == 100
    assert sample_result["minimum_observations_for_target_margin"] == 385

    _open(at, "T028", "Root-Cause Analysis Toolkit")
    pareto_result = _run(at, "T028")
    assert pareto_result["total_count"] == 100
    assert pareto_result["categories_to_reach_80_percent"] == 2

    _open(at, "T029", "5S and Workplace Audit")
    audit_result = _run(at, "T029")
    assert audit_result["overall_5s_score_pct_equal_pillar_weight"] == pytest.approx(70.0)

    _open(at, "T030", "Kaizen and A3 Improvement Manager")
    a3_result = _run(at, "T030")
    assert a3_result["target_progress_pct"] == pytest.approx(50.0)
    assert a3_result["outcome_status"] != "VERIFIED_SAVINGS"

    _open(at, "T031", "Statistical Process Control")
    spc_result = _run(at, "T031")
    assert spc_result["mean"] == pytest.approx(10.5)

    _open(at, "T040", "Quality Cost and Defect Analyzer")
    copq_result = _run(at, "T040")
    assert copq_result["cost_of_poor_quality"] == pytest.approx(190.0)

    _open(at, "T042", "MTBF and MTTR Analyzer")
    reliability_result = _run(at, "T042")
    assert reliability_result["mtbf_hours"] == pytest.approx(200.0)
    assert reliability_result["mttr_hours"] == pytest.approx(2.0)

    _open(at, "T056", "ABC/XYZ Inventory Analyzer")
    inventory_result = _run(at, "T056")
    assert inventory_result["annual_usage_value_total"] == pytest.approx(1000.0)

    _open(at, "T075", "Forecast and Model Drift Monitor")
    drift_result = _run(at, "T075")
    assert drift_result["status"] == "DRIFT_ALERT"
    assert drift_result["mae"] == pytest.approx(7 / 3)

    _open(at, "T085", "Statistical Power and Sample-Size Planner")
    power_result = _run(at, "T085")
    assert power_result["required_n_per_group"] == 64
    assert power_result["total_sample_size"] == 128


def test_cutting_stock_solver_is_exposed_in_the_existing_facilities_tool():
    at = _authed_library()
    _open(at, "T066", "Cutting Stock and Bin Packing")
    # This is a separate solver action under the existing target, not a new top-level
    # module. A solver exception must remain visible and must not erase prior state.
    button = at.button(key="T066_CUT_run_button")
    button.click()
    at.run(timeout=60)
    assert not at.exception, "\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_T066_CUT_result")
    assert result is not None, "Cutting-stock action did not return a structured result."
    assert result["result"]["status"] == "OPTIMAL"
    assert result["result"]["stock_count"] == 2

def test_lower_tier_cannot_render_or_execute_research_only_tool():
    from streamlit.testing.v1 import AppTest

    at = _authed_library(tier="Starter")
    _open(at, "T085", "Statistical Power and Sample-Size Planner")
    assert any(
        "does not grant this target capability" in str(item.value).lower()
        for item in at.warning
    )
    assert "shoir_T085_result" not in at.session_state
    with pytest.raises(KeyError):
        at.button(key="T085_run_button")

