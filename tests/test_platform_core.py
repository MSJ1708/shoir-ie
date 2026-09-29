from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from shoir_platform_core import (
    ACTION_LEVELS,
    WORKFLOW_STEPS,
    capability_ledger,
    canonical_map_columns,
    command_center_snapshot,
    convert_quantity,
    derive_formula_unit,
    digital_twin_cycle,
    data_readiness,
    fractional_factorial_design,
    module_manifest as core_module_manifest,
    response_surface_design,
    research_study_record,
    lock_research_protocol,
    roi_evidence_snapshot,
    safe_calculate,
    scenario_analysis,
    uncertainty_engine,
    unified_optimization,
    generate_standard_scenarios,
    canonical_kpi_id,
    get_kpi_definition,
    knowledge_graph_frame,
    capability_verification_matrix,
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


def test_compound_units_and_formula_dimensions():
    result = derive_formula_unit("Mass / Time", {"Mass": "kg", "Time": "h"})
    assert result["dimensions"] == {"mass": 1, "time": -1}
    assert abs(result["scale_to_base"] - (1.0 / 3600.0)) < 1e-12


def test_digital_twin_cycle_creates_deviation_evidence():
    twin = digital_twin_cycle(
        "ASSET-01", {"Throughput": 120}, expected={"Throughput": 100},
        thresholds={"Throughput": 5},
    )
    assert twin["status"] == "DEGRADED"
    assert len(twin["anomalies"]) == 1


def test_research_protocol_lock_and_roi_evidence():
    study = research_study_record("Test Study", objective="Validate process", hypothesis="H1")
    locked = lock_research_protocol(study)
    assert locked["protocol_locked"] is True
    assert locked["protocol_hash"]
    roi = roi_evidence_snapshot(
        baseline={"Throughput": 100},
        target={"Throughput": 110},
        predicted={"Throughput": 108},
        actual={"Throughput": 112},
        financial_impact=5000,
        hours_saved=8,
        risk_reduction=0.1,
    )
    assert roi["verified_actuals"] is True
    assert roi["kpis"][0]["Actual Delta"] == 12


def test_command_center_snapshot_surfaces_attention_state():
    snap = command_center_snapshot(pd.DataFrame({"Throughput": [100, 80]}))
    assert "what_to_do_next" in snap
    assert "attention" in snap


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



def test_unified_optimization_exposes_solver_transparency():
    result = unified_optimization(
        "LP",
        [1, 2],
        A_ub=[[1, 1]],
        b_ub=[10],
        bounds=[(0, None), (0, None)],
    )
    assert result["success"] is True
    assert result["solver"] == "scipy-highs"
    assert "constraint_slacks" in result
    assert "runtime_ms" in result


def test_standard_scenarios_and_kpi_identity():
    scenarios = generate_standard_scenarios({"Throughput": 100, "Cost": 50}, uncertainty_pct=10, stress_pct=20)
    assert set(scenarios) == {"Baseline", "Best Case", "Worst Case", "Stress Up", "Stress Down"}
    assert canonical_kpi_id("Decision Regret") == "KPI-DECISION-REGRET"
    assert get_kpi_definition("Throughput")["kpi_id"] == "KPI-THROUGHPUT"


def test_unified_milp_uses_real_integer_solver():
    result = unified_optimization(
        "MILP",
        [1, 2],
        A_ub=[[1, 1]],
        b_ub=[3],
        bounds=[(0, 3), (0, 3)],
    )
    assert result["solver"] == "scipy-highs-milp"
    assert result["success"] is True
    assert all(float(x).is_integer() for x in result["variables"])


def test_copilot_blocks_high_impact_action_without_approval():
    from shoir_platform_core import execute_copilot_action
    blocked = execute_copilot_action("execute_operational_action", actor_level="EXECUTE")
    assert blocked["status"] == "BLOCKED"


def test_capability_verification_matrix_is_conservative():
    matrix = capability_verification_matrix()
    assert len(matrix) >= 160
    assert "Platform contract" in matrix.columns
    assert "Production deployment" in matrix.columns
    assert "Implemented" in set(matrix["Status"])


def test_knowledge_graph_frame_has_stable_schema():
    nodes, edges = knowledge_graph_frame(workspace="default")
    assert isinstance(nodes, pd.DataFrame)
    assert isinstance(edges, pd.DataFrame)
    if not nodes.empty:
        assert {"id", "label", "type"}.issubset(nodes.columns)
    if not edges.empty:
        assert {"source", "target", "relation"}.issubset(edges.columns)
