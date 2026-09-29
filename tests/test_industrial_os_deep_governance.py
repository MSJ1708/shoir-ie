"""Deep regression tests for the Industrial OS governance kernel."""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from shoir_platform_core import (
    ACTION_LEVELS,
    MANIFEST_FIELDS,
    WORKFLOW_STEPS,
    accessibility_config,
    derive_formula_unit,
    execute_replay,
    factorial_design,
    fit_response_surface,
    fractional_factorial_design,
    forecast_decomposition,
    forecast_drift,
    manifest_quality,
    module_manifest,
    report_pack_manifest,
    response_surface_design,
    scenario_analysis,
    safe_calculate,
)


def test_universal_workflow_and_manifest_are_machine_checkable():
    manifest = module_manifest("Regression Module")
    assert tuple(manifest["workflow"]) == WORKFLOW_STEPS
    assert set(MANIFEST_FIELDS).issubset(manifest)
    quality = manifest_quality(manifest)
    assert quality["complete"] is True
    assert quality["completeness_pct"] == 100.0
    assert set(ACTION_LEVELS) == {"READ", "ANALYZE", "SIMULATE", "RECOMMEND", "PREPARE", "EXECUTE", "ADMIN"}


def test_fractional_factorial_does_not_duplicate_default_generators():
    factors = {name: [-1, 1] for name in ("A", "B", "C", "D", "E")}
    design, meta = fractional_factorial_design(factors, fraction=4, randomized=False, reps=1, seed=2026)
    assert meta["runs"] == 4
    assert len(design) == 4
    # C and D must not be identical columns under the default generator.
    assert not design["C"].equals(design["D"])


def test_response_surface_design_and_fit():
    design, meta = response_surface_design(
        {"Speed": (10, 20), "Feed": (1, 2), "Depth": (5, 9)},
        design="central_composite",
        center_points=3,
        seed=2026,
    )
    assert meta["runs"] == len(design)
    frame = design.copy()
    frame["Response"] = 2.0 * frame["Speed"] + 3.0 * frame["Feed"] - 0.5 * frame["Depth"]
    model, fitted = fit_response_surface(frame, "Response", ["Speed", "Feed", "Depth"])
    assert model["n"] == len(fitted)
    assert model["r2"] > 0.99
    assert "Residual" in fitted.columns


def test_scenario_constraints_best_worst_and_drivers():
    comparison, summary = scenario_analysis(
        {
            "Baseline": {"Throughput": 100, "Cost": 50},
            "A": {"Throughput": 110, "Cost": 45},
            "B": {"Throughput": 90, "Cost": 70},
        },
        baseline="Baseline",
        constraints={"Throughput": {"min": 95}, "Cost": {"max": 60}},
    )
    assert len(comparison) == 6
    assert summary["violations"] >= 2
    assert summary["best"]["Throughput"] == "A"
    assert summary["worst"]["Throughput"] == "B"
    assert summary["drivers"]["Cost"]


def test_quantity_dimensions_are_enforced():
    derived = derive_formula_unit("flow * time", {"flow": "units/min", "time": "min"})
    assert derived["dimensions"] == {"count": 1}
    with pytest.raises(ValueError):
        derive_formula_unit("length + mass", {"length": "m", "mass": "kg"})


def test_safe_calculation_rejects_code_execution():
    assert safe_calculate("a * 2 + 1", {"a": 3}) == 7.0
    with pytest.raises(ValueError):
        safe_calculate("__import__('os').system('echo bad')", {"a": 3})


def test_forecast_drift_and_decomposition():
    actual = list(np.linspace(100, 110, 24)) + [150, 155, 160, 165]
    predicted = actual[:]
    drift = forecast_drift(actual, predicted, baseline_window=12, threshold=0.25)
    assert drift["status"] == "DRIFT"
    decomposition = forecast_decomposition(actual, seasonal_period=7)
    assert not decomposition.empty
    assert set(["Observed", "Trend", "Seasonal", "Residual"]).issubset(decomposition.columns)


def test_replay_checks_input_and_result_fingerprint():
    frame = pd.DataFrame({"x": [1, 2, 3]})
    record = {
        "callable_path": "tests.test_shoir_industrial_os:_replay_fixture",
        "kwargs": {"value": 3},
        "input_hash": __import__("shoir_platform_core").dataframe_digest(frame),
        "expected_result_hash": __import__("shoir_platform_core").digest({"value": 6}),
    }
    result = execute_replay(record, current_input=frame)
    assert result == {"value": 6}
    assert __import__("streamlit").session_state.get("shoir_last_replay_result", {}).get("status") == "PASS"
    with pytest.raises(RuntimeError):
        execute_replay(record, current_input=pd.DataFrame({"x": [9]}))


def _replay_fixture(value: int):
    return {"value": int(value) * 2}


def test_accessibility_config_and_report_pack_manifest():
    cfg = accessibility_config("Arabic", high_contrast=True, reduced_motion=True)
    assert cfg["rtl"] is True
    assert cfg["high_contrast"] is True
    pack = report_pack_manifest("Engineering", module="Test", workspace="default")
    assert "uncertainty" in pack["sections"]
    assert pack["pack_type"] == "Engineering"


def test_app_entrypoint_is_thin():
    root = Path(__file__).resolve().parents[1]
    app_path = root / "app.py"
    text = app_path.read_text(encoding="utf-8")
    assert len(text) < 5000
    assert "import shoir_app_runtime" in text


def test_no_silent_broad_exception_swallowing():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and isinstance(node.type, ast.Name) and node.type.id == "Exception":
                body = [x for x in node.body if not isinstance(x, ast.Pass)]
                if not body:
                    offenders.append(f"{path.relative_to(root)}:{node.lineno}")
    assert not offenders, "Silent 'except Exception: pass' remains: " + ", ".join(offenders[:30])
