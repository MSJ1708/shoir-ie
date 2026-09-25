import numpy as np
import pandas as pd

import shoir_enterprise_layer as ent
from shoir_live_visuals import build_visualization_suite, figure_fingerprint


def _local_enterprise_db(monkeypatch, tmp_path):
    monkeypatch.setattr(ent, "DEFAULT_DB", str(tmp_path / "enterprise.db"))
    monkeypatch.setattr(ent, "_remote", lambda: False)


def test_digital_twin_round_trip_and_workspace_isolation(monkeypatch, tmp_path):
    _local_enterprise_db(monkeypatch, tmp_path)
    state = pd.DataFrame({
        "Asset": ["M-01", "M-02"],
        "Temperature": [62.0, 71.0],
        "Vibration": [1.8, 2.4],
        "Status": ["Running", "Warning"],
    })
    snapshot_id = ent.save_twin_snapshot("alice", state, source="test", workspace="plant-a")
    assert snapshot_id.startswith("TWS-")

    loaded = ent.load_twin_state("alice", workspace="plant-a")
    assert set(loaded["Asset"]) == {"M-01", "M-02"}
    assert ent.load_twin_state("bob", workspace="plant-a").empty

    ent.record_artifact("alice", "decision", "Test Decision", {"value": 1}, workspace="plant-a")
    ent.record_artifact("bob", "decision", "Other Decision", {"value": 2}, workspace="plant-a")
    assert len(ent.list_artifacts("alice", workspace="plant-a")) == 2
    assert len(ent.list_artifacts("bob", workspace="plant-a")) == 1


def test_control_tower_health_and_telemetry_anomaly():
    health = ent.build_control_tower_health({
        "Production": {"records": 10, "status": "Ready"},
        "Quality": {"records": 10, "status": "Warning", "alerts": 1},
    })
    assert "Health Score" in health.columns
    assert health.loc[health["Area"].eq("Quality"), "Health Score"].iloc[0] == 35

    values = [10.0] * 20 + [1000.0]
    telemetry = pd.DataFrame({
        "Timestamp": pd.date_range("2026-01-01", periods=len(values), freq="h"),
        "Asset": ["M-01"] * len(values),
        "Value": values,
    })
    analyzed = ent.analyze_telemetry(telemetry, timestamp_col="Timestamp", value_col="Value", group_col="Asset", window=10, z_threshold=3.0)
    assert "Anomaly" in analyzed.columns
    assert bool(analyzed["Anomaly"].iloc[-1])


def test_job_queue_can_be_cancelled_before_execution(monkeypatch, tmp_path):
    _local_enterprise_db(monkeypatch, tmp_path)
    job_id = ent.create_job_record("alice", "Experiment Lab", "test", {"n": 1})
    assert ent.request_job_action("alice", job_id, "cancel")
    jobs = ent.list_jobs("alice")
    row = jobs.loc[jobs["job_id"].eq(job_id)].iloc[0]
    assert row["status"] == "Cancelled"


def test_data_intelligence_and_visualization_suite():
    df = pd.DataFrame({
        "Area": ["Production", "Quality", "Maintenance"],
        "Health Score": [95, 62, 84],
        "Value": [100, 80, 90],
        "Timestamp": pd.date_range("2026-01-01", periods=3, freq="D"),
    })
    report = ent.profile_data_intelligence(df)
    assert 0 <= report["data_quality_score"] <= 100
    chart_df = ent.data_intelligence_frame(report)
    assert {"Metric", "Value"} == set(chart_df.columns)

    suite = build_visualization_suite(df, context="Control Tower", max_figures=4)
    assert suite
    assert any("Health map" in title for title, _ in suite)
    assert all(figure_fingerprint(fig) for _, fig in suite)
    assert len({figure_fingerprint(fig) for _, fig in suite}) == len(suite)


def test_connector_profiles_reject_malformed_endpoints():
    good = ent.validate_connector_profile("MQTT", "MQTT", "mqtts://broker.example")
    assert good["valid"]
    bad = ent.validate_connector_profile("OPC-UA", "OPC-UA", "https://wrong.example")
    assert not bad["valid"]
    assert bad["errors"]


def test_monitoring_rule_evaluation_is_explicit():
    df = pd.DataFrame({"Value": [2.0, 5.0, 8.0]})
    result = ent.evaluate_monitoring_rule(df, "Value", ">=", 5)
    assert result["Alert"].tolist() == [False, True, True]
    assert result["Rule Status"].tolist() == ["Normal", "Attention", "Attention"]
