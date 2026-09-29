from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from shoir_platform_core import (
    ACTION_LEVELS,
    WORKFLOW_STEPS,
    capability_ledger,
    canonical_map_columns,
    convert_quantity,
    data_readiness,
    fractional_factorial_design,
    module_manifest as core_module_manifest,
    response_surface_design,
    safe_calculate,
    scenario_analysis,
    uncertainty_engine,
    verification_suite,
)


def test_core_exposes_full_mandatory_workflow():
    assert WORKFLOW_STEPS == (
        "DATA", "VALIDATE", "MAP", "MODEL", "RUN", "VISUALIZE",
        "COMPARE", "EXPLAIN", "DECIDE", "EXPORT", "VERIFY",
    )
    assert ACTION_LEVELS == (
        "READ", "ANALYZE", "SIMULATE", "RECOMMEND", "PREPARE", "EXECUTE", "ADMIN",
    )


def test_core_manifest_contains_every_contract_field():
    manifest = core_module_manifest("Capacity Optimizer")
    for key in (
        "identity", "purpose", "inputs", "required_fields", "optional_fields",
        "units", "validation_rules", "transformations", "model", "solver",
        "outputs", "kpis", "recommended_visualizations", "uncertainty",
        "assumptions", "scenario_support", "export_formats", "persistence",
        "permissions", "maturity", "verification_tests", "workflow", "enforcement",
    ):
        assert key in manifest
    assert manifest["workflow"] == list(WORKFLOW_STEPS)
    assert all(manifest["enforcement"].values())


def test_capability_ledger_covers_160_feature_inventory():
    ledger = capability_ledger()
    assert len(ledger) >= 160
    required = {
        "Capability ID", "Capability", "Area", "Status", "Coverage",
        "Test coverage", "Last verification", "Dependencies",
        "Deployment requirements", "Manifest",
    }
    assert required.issubset(ledger.columns)
    assert set(ledger["Status"]).issubset({
        "Verified", "Implemented", "Foundation", "Integration-ready",
    })


def test_canonical_mapping_and_data_readiness():
    df = pd.DataFrame({
        "Customer ID": ["C1", "C2"],
        "Demand Qty": [10, 12],
        "Production Output": [9, 11],
    })
    mapping = canonical_map_columns(df)
    assert mapping["customer_id"] == "Customer ID"
    assert mapping["demand_qty"] == "Demand Qty"
    assert mapping["throughput"] == "Production Output"
    assert data_readiness(df)["score"] == 100.0


def test_fractional_factorial_has_requested_fraction_and_replicates():
    factors = {"A": [-1, 1], "B": [-1, 1], "C": [-1, 1], "D": [-1, 1]}
    design, meta = fractional_factorial_design(factors, fraction=4, reps=2, seed=2026)
    assert meta["type"] == "fractional_factorial"
    assert meta["fraction"] == 4
    assert meta["replications"] == 2
    assert len(design) == 8
    assert "Run Order" in design.columns


def test_response_surface_design_is_reproducible():
    factors = {"Speed": [10, 20], "Feed": [1, 2], "Depth": [5, 9]}
    d1, m1 = response_surface_design(factors, design="central_composite", center_points=3, seed=2026)
    d2, m2 = response_surface_design(factors, design="central_composite", center_points=3, seed=2026)
    pd.testing.assert_frame_equal(d1, d2)
    assert m1["runs"] == len(d1) == m2["runs"]


def test_scenario_analysis_flags_constraint_violations_and_drivers():
    scenarios = {
        "Baseline": {"Cost": 100, "Service": 95},
        "A": {"Cost": 90, "Service": 93},
        "B": {"Cost": 80, "Service": 88},
    }
    comparison, summary = scenario_analysis(
        scenarios,
        baseline="Baseline",
        constraints={"Cost": {"max": 100}, "Service": {"min": 95}},
    )
    assert not comparison.empty
    assert (comparison["Constraint Violation"].astype(str).str.len() > 0).any()
    assert "Service" in summary["drivers"]


def test_uncertainty_engine_reports_intervals_and_constraint_probability():
    result = uncertainty_engine([1, 2, 3, 4, 5], threshold=3)
    assert result["n"] == 5
    assert result["p05"] <= result["p50"] <= result["p95"]
    assert 0 <= result["constraint_violation_probability"] <= 1


def test_quantity_engine_rejects_cross_dimension_math():
    assert convert_quantity(1, "m", "cm") == 100.0
    with pytest.raises(ValueError):
        convert_quantity(1, "m", "kg")


def test_safe_formula_engine_rejects_code_execution():
    assert safe_calculate("A * 2 + B", {"A": 3, "B": 4}) == 10
    with pytest.raises((ValueError, SyntaxError)):
        safe_calculate("__import__('os').system('echo unsafe')", {"A": 1})


def test_verification_suite_is_evidence_driven():
    inputs = pd.DataFrame({"x": [1, 2, 3]})
    results = pd.DataFrame({"output": [3, 4, 5]})
    report = verification_suite("Test Module", inputs=inputs, results=results)
    assert report["status"] == "PASS"
    assert all("passed" in check for check in report["checks"])


def test_app_entrypoint_is_thin_and_runtime_holds_application():
    entry = Path("app.py").read_text(encoding="utf-8")
    runtime = Path("shoir_app_runtime.py").read_text(encoding="utf-8")
    assert len(entry) < 1000
    assert "import shoir_app_runtime" in entry
    assert "render_platform_os_surface" in runtime
