import inspect

import pandas as pd

import shoir_investor_demo as demo


def _clear_demo_state():
    prefix = f"{demo.DEMO_KEY}_"
    for key in list(demo.st.session_state.keys()):
        if str(key).startswith(prefix):
            demo.st.session_state.pop(key, None)


def setup_function():
    _clear_demo_state()


def teardown_function():
    _clear_demo_state()


def test_flagship_rescue_case_keeps_investor_demo_values_stable():
    demo._set("inputs", demo._default_inputs())
    demo._set("active_preset", "Flagship 72-hour crisis")

    rescue = demo._rescue_case()

    assert rescue["baseline"]["Financial exposure SAR"] == 1_520_000.0
    assert rescue["intervention"]["Financial exposure SAR"] == 210_000.0
    assert rescue["avoided_exposure"] == 1_310_000.0
    assert rescue["baseline"]["Production shortfall %"] == 9.4
    assert rescue["intervention"]["Production shortfall %"] == 0.8
    assert rescue["baseline"]["Unplanned downtime h"] == 14.2
    assert rescue["intervention"]["Unplanned downtime h"] == 3.1
    assert len(rescue["action_plan"]) == 9


def test_risk_analysis_has_seven_cross_domain_signals():
    risk = demo._risk_analysis(demo._default_inputs())

    assert len(risk) == 7
    assert risk["Asset"].is_unique
    assert set(risk["Domain"]) == {
        "Maintenance",
        "Production",
        "Inventory",
        "Quality",
        "Supply",
        "Workforce",
        "Energy",
    }
    assert float(risk.loc[risk["Asset"].eq("C-204"), "Risk %"].iloc[0]) == 90.0


def test_digital_thread_contains_twelve_connected_entities():
    demo._set("inputs", demo._default_inputs())
    thread = demo._twin_frame()

    assert len(thread) == 12
    assert thread["ID"].is_unique
    assert {"C-204", "LINE-02", "SUP-18", "MW-BACKLOG", "ENERGY-01", "OUT-72H"} <= set(thread["ID"])


def test_simulation_is_reproducible_and_has_expected_horizon():
    inputs = demo._default_inputs()
    first = demo._simulation(inputs, seed=20261004)
    second = demo._simulation(inputs, seed=20261004)

    pd.testing.assert_frame_equal(first["summary"], second["summary"])
    assert first["reps"] == 1500
    assert first["horizon"] == 72
    assert set(first["samples"]) == {"Baseline", "Intervention"}


def test_optimization_exposes_all_rescue_alternatives():
    demo._set("inputs", demo._default_inputs())
    demo._set("simulation", demo._simulation(demo._default_inputs(), seed=20261004))

    result = demo._optimization(demo._default_inputs())

    assert set(result["alternatives"]["Alternative"]) == {
        "Do Nothing",
        "Preventive Rescue",
        "Reroute + Rescue",
        "Capacity Expansion",
    }
    assert not result["scored"].empty


def test_verification_is_explicit_and_structured():
    decision = {
        "expected_throughput": 9500.0,
        "expected_otif": 97.0,
        "expected_downtime": 3.0,
        "risk_after": 22.0,
    }

    verification = demo._verify(decision)

    assert list(verification.columns) == [
        "KPI",
        "Expected",
        "Verified",
        "Target",
        "Rule",
        "Status",
    ]
    assert len(verification) == 4
    assert set(verification["Status"]) <= {"PASS", "REVIEW"}


def test_scenario_change_clears_stale_decision_lifecycle():
    demo._init_ui_state()
    demo._ui_set("decision_status", "VERIFIED")
    demo._ui_set("whatif_result", {"stale": True})

    demo._reset_flow_only()

    assert demo._ui_state("decision_status") == "RECOMMENDED"
    assert demo._ui_state("whatif_result") is None


def test_command_center_2_contract_contains_all_fifteen_upgrade_surfaces():
    source = inspect.getsource(demo)
    required_markers = [
        "_render_top_cockpit",
        "_render_health_map_and_inspector",
        "_render_why_recommendation",
        "_render_what_if_mode",
        "_render_scenario_library",
        "_render_evidence_chain",
        "_render_decision_governance",
        "_render_closed_loop",
        "_render_executive_summary",
        "Command Palette",
        "Industrial Command Center 2.0",
        "Persistent Inspector",
        "Recommended rescue",
        "Do nothing vs Shoir-IE",
        "Decision pipeline",
    ]
    missing = [marker for marker in required_markers if marker not in source]
    assert not missing, f"Missing Command Center 2.0 surfaces: {missing}"
