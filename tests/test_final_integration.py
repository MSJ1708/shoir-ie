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

def test_decision_variance_contract():
    import industrial_experience as exp
    variance = exp.calculate_decision_variance({"Throughput": 100, "Cost": 50}, {"Throughput": 90, "Cost": 55})
    assert list(variance["KPI"]) == ["Cost", "Throughput"]
    assert float(variance.loc[variance["KPI"].eq("Throughput"), "Delta"].iloc[0]) == -10.0
    assert float(variance.loc[variance["KPI"].eq("Cost"), "Delta %"].iloc[0]) == 10.0

def test_connector_sql_adapter_and_endpoint_redaction(tmp_path):
    import shoir_enterprise_layer as ent
    db = tmp_path / "source.db"
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute("select 1")
    ent.DEFAULT_DB = str(tmp_path / "enterprise.db")
    ent._remote = lambda: False
    result = ent.test_connector_profile("alice", "Local SQL", "SQL", "SQL", "sqlite:///" + str(db))
    assert result["status"] == "Healthy"
    assert result["run_id"].startswith("CRUN-")
    secret_id = ent.record_connector_health("alice", "REST", "REST", "REST", "https://example.test/api?token=topsecret&x=1", "Healthy")
    health = ent.connector_health_frame("alice")
    saved = str(health.loc[health["connector_id"].eq(secret_id), "endpoint"].iloc[0])
    assert "topsecret" not in saved
    assert "***" in saved
