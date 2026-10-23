"""App-level regression checks for the preserved Workbench and a real target action."""
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_workbench_renders_tool_directory_and_runs_cutting_stock_action():
    from streamlit.testing.v1 import AppTest

    page = ROOT / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=45)
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

