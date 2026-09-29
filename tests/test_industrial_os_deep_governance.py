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
    scenario_uncertainty_bundle,
    twin_state_estimate,
    twin_calibrate,
    twin_model_drift,
    copilot_orchestrate,
    safe_calculate,
    universal_module_contract_matrix,
    enqueue_distributed_job, claim_distributed_job, update_distributed_job, reap_stale_jobs,
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
        "callable_path": "tests.test_industrial_os_deep_governance:_replay_fixture",
        "kwargs": {"value": 3},
        "input_hash": __import__("shoir_platform_core").dataframe_digest(frame),
        "expected_result_hash": __import__("shoir_platform_core").digest({"value": 6}),
    }
    result = execute_replay(record, current_input=frame)
    assert result == {"value": 6}
    assert __import__("streamlit").session_state.get("shoir_last_replay_result", {}).get("status") == "PASS"
    with pytest.raises(RuntimeError):
        execute_replay(record, current_input=pd.DataFrame({"x": [9]}))
    with pytest.raises(PermissionError):
        execute_replay({"callable_path": "os:system", "kwargs": {"command": "echo blocked"}})


def _replay_fixture(value: int):
    return {"value": int(value) * 2}


def test_scenario_uncertainty_and_twin_operations():
    ub, meta = scenario_uncertainty_bundle(
        {
            "Baseline": {"Throughput": [95, 100, 105]},
            "Stress": {"Throughput": [80, 85, 90]},
        },
        constraints={"Throughput": {"min": 95}},
    )
    assert meta["status"] == "OK"
    row = ub[(ub["Scenario"] == "Stress") & (ub["KPI"] == "Throughput")].iloc[0]
    assert 0.99 <= float(row["Constraint Violation Probability"]) <= 1.0
    estimate = twin_state_estimate({"x": 10.0}, {"x": 20.0}, gain=0.5)
    assert estimate["state"]["x"] == 15.0
    observed = pd.DataFrame({"x": [2, 4, 6, 8, 10]})
    modelled = pd.DataFrame({"x": [1, 2, 3, 4, 5]})
    calibration = twin_calibrate(observed, modelled)
    assert calibration["signals"]["x"]["scale"] > 1.9
    history = pd.DataFrame({"x_observed": [1, 1, 1, 1, 1, 5, 5, 5], "x_model": [1, 1, 1, 1, 1, 1, 1, 1]})
    drift = twin_model_drift(history, window=3)
    assert bool(drift.iloc[0]["Drift"]) is True


def test_copilot_orchestration_is_bounded_and_evidence_first():
    frame = pd.DataFrame({"Throughput": [90, 100, 110], "Cost": [55, 50, 45]})
    result = copilot_orchestrate(
        "analyze capacity and cost",
        df=frame,
        actor_level="RECOMMEND",
        workspace="test-governance",
        approval=False,
    )
    assert result["status"] == "COMPLETE"
    assert result["decision"]["approval_required"] is True
    stages = [x["stage"] for x in result["stages"]]
    assert {"DATA", "VALIDATE", "MAP", "MODEL", "RUN", "VISUALIZE", "COMPARE", "EXPLAIN", "VERIFY", "DECIDE", "EXPORT"}.issubset(stages)

def test_accessibility_config_and_report_pack_manifest():
    cfg = accessibility_config("Arabic", high_contrast=True, reduced_motion=True)
    assert cfg["rtl"] is True
    assert cfg["high_contrast"] is True
    pack = report_pack_manifest("Engineering", module="Test", workspace="default")
    assert "uncertainty" in pack["sections"]
    assert pack["pack_type"] == "Engineering"


def test_no_direct_sqlite_connect_outside_repository_gateway():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob("*.py"):
        if "tests" in path.parts or ".venv" in path.parts or "__pycache__" in path.parts:
            continue
        if path.name in {"shoir_repository.py"}:
            continue
        source = path.read_text(encoding="utf-8")
        if "sqlite3.connect(" in source:
            offenders.append(str(path.relative_to(root)))
    assert not offenders, "Direct SQLite connections bypass repository gateway: " + ", ".join(offenders)


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


def test_160_capability_catalog_has_stable_contract_surface():
    from shoir_160 import FEATURES_160
    assert len(FEATURES_160) == 160
    for feature in FEATURES_160:
        assert feature.get("name")
        assert feature.get("area") is not None


def test_every_specialist_module_has_the_universal_contract():
    matrix = universal_module_contract_matrix()
    assert len(matrix) >= 30
    assert matrix["Contract"].eq("COMPLETE").all()
    assert matrix["Workflow"].eq("11/11").all()
    assert matrix["Visualization"].all()
    assert matrix["Lineage"].all()
    assert matrix["Uncertainty"].all()
    assert matrix["Replay"].all()
    assert matrix["Verification"].all()


def test_durable_local_job_queue_is_atomic_and_recoverable(tmp_path, monkeypatch):
    import shoir_platform_core as core
    monkeypatch.setattr(core, "DEFAULT_DB_PATH", str(tmp_path / "jobs.db"))
    job_id = enqueue_distributed_job(
        "Regression",
        {"callable_path": "tests.test_industrial_os_deep_governance:_replay_fixture", "kwargs": {"value": 4}},
        workspace="w", max_attempts=2,
    )
    claimed = claim_distributed_job("worker-1", workspace="w", lease_seconds=60)
    assert claimed and claimed["job_id"] == job_id
    assert claimed["attempts"] == 1
    update_distributed_job(job_id, status="COMPLETED", worker_id="worker-1", progress=1.0, result={"value": 8}, workspace="w")
    assert claim_distributed_job("worker-2", workspace="w") is None
    assert reap_stale_jobs(workspace="w") == 0
