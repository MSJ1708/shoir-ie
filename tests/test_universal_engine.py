import pandas as pd
import plotly.graph_objects as go
import pytest

from shoir_universal_engine import (
    ENGINE_ACTION_LEVELS,
    action_gate,
    build_script,
    choose_agent,
    data_readiness,
    dependency_figure,
    dependency_graph,
    pivot_table,
    runtime_choice,
)


def test_universal_pivot_is_repeatable():
    df = pd.DataFrame({
        "Plant": ["A", "A", "B"],
        "Month": ["Jan", "Feb", "Jan"],
        "Throughput": [10.0, 14.0, 8.0],
    })
    first = pivot_table(df, ["Plant"], ["Throughput"], ["Month"], "sum")
    second = pivot_table(df, ["Plant"], ["Throughput"], ["Month"], "sum")
    pd.testing.assert_frame_equal(first, second)
    assert {"Plant", "Throughput · Jan", "Throughput · Feb"}.issubset(set(first.columns))


def test_dependency_graph_is_deterministic_and_renderable():
    nodes, edges = dependency_graph(
        "Production",
        formulas={"Sheet1": {"E2": "=B2*C2", "E3": "=E2+1"}},
        query_steps=[{"type": "rename", "source": "A", "target": "Asset"}],
        semantic_map={"Sheet1": {"Asset": "Asset"}},
        source_tables=["production_data"],
    )
    assert not nodes.empty
    assert not edges.empty
    fig = dependency_figure(nodes, edges, "Test graph")
    assert isinstance(fig, go.Figure)


def test_data_readiness_and_runtime_contract():
    df = pd.DataFrame({"A": [1, 2, 3], "B": [4.0, None, 6.0]})
    ready = data_readiness(df)
    assert ready["rows"] == 3
    assert ready["columns"] == 2
    assert ready["missing_cells"] == 1
    runtime = runtime_choice(df)
    assert runtime["engine"] in {"pandas", "duckdb"}
    assert runtime["cells"] == 6


def test_agent_routing_and_action_gates():
    route = choose_agent("forecast demand and capacity for tomorrow")
    assert route["agent"] == "Forecast Agent"
    assert set(ENGINE_ACTION_LEVELS) >= {"Read", "Analyze", "Simulate", "Recommend", "Prepare", "Execute", "Admin"}

    assert action_gate("Read", "Starter Tier")["allowed"]
    assert not action_gate("Execute", "Enterprise Tier", approved=False)["allowed"]
    assert action_gate("Execute", "Enterprise Tier", approved=True)["allowed"]


def test_replay_script_is_human_readable_and_stable():
    script = build_script([
        {"kind": "pivot_saved", "payload": {"module": "Quality", "aggregation": "mean"}},
        {"kind": "analysis_snapshot", "payload": {"rows": 10}},
    ])
    assert script.startswith("# Shoir-IE Universal Engine replay script")
    assert "pivot_saved" in script
    assert "analysis_snapshot" in script


def test_universal_engine_integration_is_present_in_app_and_dependencies():
    from pathlib import Path

    app = Path("app.py").read_text(encoding="utf-8")
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    assert "from shoir_universal_engine import" in app
    assert "render_universal_engine_surface" in app
    assert "postflight_contract" in app
    assert "duckdb" in requirements.lower()


def test_visualization_fallback_handles_unfamiliar_table():
    from shoir_universal_engine import guaranteed_figure

    df = pd.DataFrame({"Only Text": ["a", "b", "c"]})
    fig = guaranteed_figure(df, "Fallback")
    assert isinstance(fig, go.Figure)


def test_formula_contract_examples():
    from shoir_industrial_workbook import SafeFormulaEngine

    wb = {"Sheet1": pd.DataFrame({"A": [1.0], "B": [2.0], "C": [3.0], "D": [4.0], "E": [5.0]})}
    engine = SafeFormulaEngine(wb)
    assert engine.evaluate("=OEE(90,80,95)", "Sheet1") == pytest.approx(0.684)
    assert engine.evaluate("=TAKT_TIME(480,120)", "Sheet1") == pytest.approx(4.0)
    assert engine.evaluate("=NPV(0.1,A1:E1)", "Sheet1") == pytest.approx(
        1.0 + 2.0 / 1.1 + 3.0 / 1.21 + 4.0 / 1.331 + 5.0 / 1.4641
    )
