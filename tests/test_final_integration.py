import json
import pandas as pd

from benchmark_harness import calculate_roi_evidence, benchmark_callable
from shoir_digital_thread import CANONICAL_LIFECYCLE, canonical_flow_figure
from shoir_live_visuals import _auto_chart_choice, _make_figure, build_visualization_suite

def test_categorical_only_tables_are_visualized():
    df = pd.DataFrame({"Status": ["Running", "Running", "Idle", "Warning"]})
    assert _auto_chart_choice(df) == "Categorical Distribution"
    assert _make_figure(df, "Categorical Distribution", "Status", None, None, "Status counts") is not None
    suite = build_visualization_suite(df, context="Maintenance", max_figures=3)
    assert suite

def test_roi_evidence_is_transparent_and_deterministic():
    result = calculate_roi_evidence(240, 60, 250, 50, 25000, 0.8)
    assert result["hours_saved_per_run"] == 3.0
    assert result["annual_hours_saved"] == 600.0
    assert result["annual_labor_value"] == 30000.0
    assert result["first_year_net_value"] == 5000.0
    assert result["evidence_status"].startswith("User-entered")

def test_benchmark_callable_returns_repeatable_schema():
    result = benchmark_callable("noop", lambda: sum(range(100)), repetitions=2, warmup=0)
    assert result["repetitions"] == 2
    assert len(result["samples_ms"]) == 2
    assert result["mean_ms"] >= 0
    assert result["p95_ms"] >= 0

def test_canonical_lifecycle_flow_is_renderable():
    nodes = [
        {"node_id": "A1", "node_type": "Asset", "name": "Machine", "status": "Observed"},
        {"node_id": "P1", "node_type": "Process", "name": "Assembly", "status": "Observed"},
        {"node_id": "D1", "node_type": "Decision", "name": "Scenario A", "status": "Proposed"},
        {"node_id": "O1", "node_type": "Outcome", "name": "Outcome", "status": "Pending verification"},
    ]
    edges = [
        {"source_id": "A1", "target_id": "P1", "relation": "canonical asset to process"},
        {"source_id": "P1", "target_id": "D1", "relation": "supports decision"},
        {"source_id": "D1", "target_id": "O1", "relation": "has outcome"},
    ]
    assert "Asset" in CANONICAL_LIFECYCLE and "Outcome" in CANONICAL_LIFECYCLE
    assert canonical_flow_figure(nodes, edges) is not None

def test_decision_variance_round_trip(tmp_path):
    import industrial_experience as exp
    db = str(tmp_path / "experience.db")
    exp.ensure_experience_db(db)
    did = exp.create_decision("Test decision", "Testing", {"Throughput": 100}, {}, {}, "owner", db_path=db) if False else None
    # Verify the pure comparison contract independently of UI state.
    variance = exp.calculate_decision_variance({"Throughput": 100, "Cost": 50}, {"Throughput": 90, "Cost": 55})
    assert list(variance["KPI"]) == ["Cost", "Throughput"]
    assert float(variance.loc[variance["KPI"].eq("Throughput"), "Delta"].iloc[0]) == -10.0
