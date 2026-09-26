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

def test_decision_outcome_persistence_and_variance(tmp_path, monkeypatch):
    import sqlite3
    import industrial_experience as exp
    db = str(tmp_path / "experience.db")
    monkeypatch.setattr(exp, "_db", lambda path="enterprise_full_workspace.db": sqlite3.connect(db, timeout=30))
    exp.ensure_experience_db(db)
    did = exp.create_decision("Test decision", "Testing", {"Throughput": 100}, {}, {}, "owner")
    oid = exp.record_decision_outcome(
        did, "owner", "Verified", {"Throughput": 100, "Cost": 50}, {"Throughput": 90, "Cost": 55},
        lesson="Actual throughput was lower than predicted.", workspace="plant-a", persist_artifact=False
    )
    assert oid.startswith("OUT-")
    stored = exp.decision_outcomes_frame(decision_id=did, owner="owner", db_path=db)
    assert len(stored) == 1
    variance = exp.calculate_decision_variance({"Throughput": 100, "Cost": 50}, {"Throughput": 90, "Cost": 55})
    assert list(variance["KPI"]) == ["Cost", "Throughput"]
    assert float(variance.loc[variance["KPI"].eq("Throughput"), "Delta"].iloc[0]) == -10.0
    assert float(variance.loc[variance["KPI"].eq("Cost"), "Delta %"].iloc[0]) == 10.0

def test_connector_sql_adapter_and_endpoint_redaction(tmp_path, monkeypatch):
    import shoir_enterprise_layer as ent
    db = tmp_path / "source.db"
    import sqlite3
    with sqlite3.connect(db) as conn:
        conn.execute("select 1")
    monkeypatch.setattr(ent, "DEFAULT_DB", str(tmp_path / "enterprise.db"))
    monkeypatch.setattr(ent, "_remote", lambda: False)
    result = ent.test_connector_profile("alice", "Local SQL", "SQL", "SQL", "sqlite:///" + str(db))
    assert result["status"] == "Healthy"
    assert result["run_id"].startswith("CRUN-")
    secret_id = ent.record_connector_health("alice", "REST", "REST", "REST", "https://example.test/api?token=topsecret&x=1", "Healthy")
    health = ent.connector_health_frame("alice")
    saved = str(health.loc[health["connector_id"].eq(secret_id), "endpoint"].iloc[0])
    assert "topsecret" not in saved
    assert "***" in saved



def test_canonical_store_roundtrip_and_workspace_isolation(tmp_path, monkeypatch):
    import shoir_enterprise_layer as ent
    monkeypatch.setattr(ent, "DEFAULT_DB", str(tmp_path / "enterprise.db"))
    monkeypatch.setattr(ent, "_remote", lambda: False)

    a = ent.upsert_canonical_entity(
        "alice", "Asset", "CNC-01", "test",
        {"temperature": 64.0}, "Observed", "plant-a",
    )
    b = ent.upsert_canonical_entity(
        "bob", "Asset", "CNC-01", "test",
        {"temperature": 77.0}, "Observed", "plant-a",
    )
    rel = ent.upsert_canonical_relationship("alice", a, a, "self-check", metadata={"ok": True}, workspace="plant-a")
    ent.record_canonical_event("alice", "asset_observed", {"value": 64.0}, entity_id=a, relationship_id=rel, workspace="plant-a")

    entities = ent.canonical_entities_frame("alice", "plant-a")
    assert len(entities) == 1
    assert entities.iloc[0]["entity_id"] == a
    assert len(ent.canonical_entities_frame("bob", "plant-a")) == 1
    assert ent.canonical_entities_frame("alice", "other").empty
    assert ent.canonical_state_manifest("alice", "plant-a")["event_count"] == 1


def test_canonical_control_tower_uses_real_entities(tmp_path, monkeypatch):
    import shoir_enterprise_layer as ent
    monkeypatch.setattr(ent, "DEFAULT_DB", str(tmp_path / "tower.db"))
    monkeypatch.setattr(ent, "_remote", lambda: False)
    ent.upsert_canonical_entity("alice", "Process", "Assembly", "test", {"rows": 20}, workspace="plant-a")
    ent.upsert_canonical_entity("alice", "Quality", "FPY", "test", {"value": 97.0}, workspace="plant-a")
    ent.upsert_canonical_entity("alice", "Energy", "Electricity", "test", {"kwh": 1200}, workspace="plant-a")
    tower = ent.build_control_tower_health_from_canonical("alice", "plant-a")
    assert set(["Production", "Quality", "Energy"]).issubset(set(tower["Area"]))
    assert float(tower.loc[tower["Area"].eq("Quality"), "Health %"].iloc[0]) == 100.0
    assert float(tower.loc[tower["Area"].eq("Production"), "Records"].iloc[0]) >= 1


def test_connector_schedule_executes_due_health_check(tmp_path, monkeypatch):
    import sqlite3
    import shoir_enterprise_layer as ent
    db = tmp_path / "source.db"
    with sqlite3.connect(db) as conn:
        conn.execute("create table t(x integer)")
        conn.execute("insert into t values(1)")
        conn.commit()
    monkeypatch.setattr(ent, "DEFAULT_DB", str(tmp_path / "enterprise.db"))
    monkeypatch.setattr(ent, "_remote", lambda: False)
    tested = ent.test_connector_profile("alice", "Local SQL", "SQL", "SQL", f"sqlite:///{db}")
    schedule_id = ent.schedule_connector_sync("alice", tested["connector_id"], 60, "plant-a", enabled=True)
    with sqlite3.connect(str(ent.DEFAULT_DB)) as conn:
        conn.execute("update shoir_ent_connector_schedules set next_run_at=? where schedule_id=?",
                     ("2000-01-01T00:00:00+00:00", schedule_id))
        conn.commit()
    results = ent.run_due_connector_syncs("alice", "plant-a", max_attempts=2, require_approval=False)
    assert len(results) == 1
    assert results.iloc[0]["Attempts"] >= 1
    assert results.iloc[0]["Status"] == "Healthy"


def test_security_gate_requires_explicit_approval(monkeypatch):
    import streamlit as st
    import shoir_enterprise_layer as ent
    st.session_state.clear()
    st.session_state["current_user"] = "alice"
    st.session_state["current_role"] = "Owner"
    st.session_state["current_action_approved"] = False
    try:
        ent.enforce_action_gate("alice", "write", "plant-a", require_approval=True)
        raise AssertionError("Expected the write gate to block without approval.")
    except PermissionError:
        pass
    st.session_state["current_action_approved"] = True
    ent.enforce_action_gate("alice", "write", "plant-a", require_approval=True)


def test_decision_to_value_is_canonical_and_traceable(tmp_path, monkeypatch):
    import sqlite3
    import industrial_experience as exp
    import shoir_enterprise_layer as ent
    experience_db = str(tmp_path / "experience.db")
    enterprise_db = str(tmp_path / "enterprise.db")
    monkeypatch.setattr(exp, "_db", lambda path="enterprise_full_workspace.db": sqlite3.connect(experience_db, timeout=30))
    monkeypatch.setattr(ent, "DEFAULT_DB", enterprise_db)
    monkeypatch.setattr(ent, "_remote", lambda: False)
    exp.ensure_experience_db(experience_db)
    did = exp.create_decision("Decision", "Test", {"Throughput": 100}, {}, {}, "alice")
    oid = exp.record_decision_outcome(
        did, "alice", "Verified",
        {"Throughput": 100}, {"Throughput": 92},
        lesson="Actual throughput was below prediction.",
        workspace="plant-a", persist_artifact=False,
    )
    frame = exp.decision_to_value_frame(owner="alice", decision_id=did, db_path=experience_db)
    assert len(frame) == 1
    assert float(frame.iloc[0]["Delta"]) == -8.0
    entities = ent.canonical_entities_frame("alice", "plant-a")
    assert oid in " ".join(entities["name"].astype(str).tolist())


def test_visualization_audit_has_no_populated_gaps():
    from shoir_live_visuals import audit_all_module_visualizations
    audit = audit_all_module_visualizations(max_figures=3)
    assert not audit.empty
    assert not audit["Status"].eq("Gap").any()


def test_no_fabricated_digital_twin_fallback():
    import inspect
    import shoir_enterprise_layer as ent
    source = inspect.getsource(ent.render_enterprise_integration_surface)
    assert 'CNC-01","Packing-01' not in source
