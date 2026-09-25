import os
import sqlite3
import tempfile

import numpy as np
import pandas as pd

from shoir_enterprise_ops import (
    artifact_fingerprint,
    build_control_tower_health,
    build_realtime_monitoring,
    build_research_manuscript,
    build_twin_state_frame,
    infer_data_intelligence,
    normalize_connector_health,
    run_twin_what_if,
)


def test_twin_snapshot_and_deterministic_replay():
    snapshot = build_twin_state_frame(
        [{"id": "WS-01", "status": "running"}],
        [{"agv_id": "AGV-01", "battery": 80, "status": "moving"}],
        [{"queue_id": "Q1", "arrival_rate": 8, "service_rate": 10}],
        [{"sensor_id": "S1", "reading": 5, "threshold": 10, "status": "active"}],
        [{"buffer_id": "B1", "current_wip": 10, "max_capacity": 20, "state": "normal"}],
    )
    assert set(snapshot["Domain"]) == {"Production", "Transport", "Process Flow", "Telemetry", "WIP"}
    first = run_twin_what_if(
        pd.DataFrame([{"arrival_rate": 8, "service_rate": 10}]),
        pd.DataFrame([{"current_wip": 10, "max_capacity": 20}]),
        pd.DataFrame([{"status": "moving", "battery": 80}]),
        downtime_rate=0.2,
        ticks=12,
    )
    second = run_twin_what_if(
        pd.DataFrame([{"arrival_rate": 8, "service_rate": 10}]),
        pd.DataFrame([{"current_wip": 10, "max_capacity": 20}]),
        pd.DataFrame([{"status": "moving", "battery": 80}]),
        downtime_rate=0.2,
        ticks=12,
    )
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 12


def test_control_tower_contains_all_domains_without_fake_health():
    result = build_control_tower_health({"supply": pd.DataFrame({"name": ["Plant A"]})})
    assert set(result["Area"]) == {"Production", "Supply", "Inventory", "Quality", "Maintenance", "Transport", "Workforce", "Energy", "Carbon"}
    supply = result.loc[result["Area"] == "Supply"].iloc[0]
    assert pd.isna(supply["Health %"])
    assert supply["Status"] == "Review"


def test_connector_health_does_not_invent_unknown_health():
    result = normalize_connector_health(pd.DataFrame({
        "Name": ["ERP-1", "SAP-1"],
        "Protocol": ["REST", "SAP"],
        "Status": ["Unknown", "Connected"],
        "Latency ms": [10, 20],
        "Errors": [0, 1],
        "Freshness min": [2, 1],
    }))
    assert pd.isna(result.loc[result["Name"] == "ERP-1", "Health %"].iloc[0])
    assert result.loc[result["Name"] == "SAP-1", "Health %"].iloc[0] < 95


def test_data_intelligence_detects_units_ids_dates_outliers_and_drift():
    base = pd.DataFrame({
        "Asset_ID": [f"A{i}" for i in range(12)],
        "Date": pd.date_range("2026-01-01", periods=12),
        "Mass (kg)": [10, 10, 11, 10, 12, 10, 11, 10, 10, 11, 10, 10],
    })
    current = base.copy()
    current.loc[11, "Mass (kg)"] = 100
    current["Asset_ID"] = [f"B{i}" for i in range(12)]
    info = infer_data_intelligence(current, base)
    mass = info.loc[info["Column"] == "Mass (kg)"].iloc[0]
    asset = info.loc[info["Column"] == "Asset_ID"].iloc[0]
    date = info.loc[info["Column"] == "Date"].iloc[0]
    assert mass["Inferred Unit"].lower() == "kg"
    assert mass["Outliers"] >= 1
    assert abs(float(mass["Drift % vs prior"])) > 0
    assert bool(asset["ID-like"])
    assert bool(date["Date-like"])


def test_realtime_monitoring_flags_three_sigma_anomaly():
    df = pd.DataFrame({
        "Timestamp": pd.date_range("2026-01-01", periods=20, freq="h"),
        "Value": [10.0] * 19 + [50.0],
    })
    out = build_realtime_monitoring(df, threshold=20.0)
    assert "Anomaly" in out.columns
    assert "Threshold Breach" in out.columns
    assert int(out["Threshold Breach"].sum()) == 1
    assert int(out["Anomaly"].sum()) >= 1


def test_research_manuscript_is_evidence_bounded():
    md, tex = build_research_manuscript(
        {
            "title": "Industrial Decision Study",
            "objective": "Test a planning intervention",
            "research_question": "Does the intervention change the KPI?",
            "hypothesis": "The intervention changes the KPI.",
            "methodology": "Randomized scenario experiment",
            "primary_endpoint": "Cost",
            "replications": 10,
            "protocol_hash": "abc123",
        },
        pd.DataFrame([{"Citation": "Example Author (2026)", "DOI / URL": "https://doi.org/example"}]),
        [("Observed Results", pd.DataFrame({"Scenario": ["Baseline"], "Cost": [100.0]}))],
        "engineer",
    )
    assert "# Industrial Decision Study" in md
    assert "Observed Results" in md
    assert "Example Author" in md
    assert "\\section*{Methods}" in tex
    assert "abc123" in tex
    assert "[insert" not in md.lower()


def test_artifact_fingerprint_is_stable():
    frame = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    assert artifact_fingerprint(frame) == artifact_fingerprint(frame.copy())
    assert artifact_fingerprint(frame) != artifact_fingerprint(pd.DataFrame({"A": [1, 2], "B": [3, 5]}))


def test_model_registry_persists_reproducibility_columns():
    from industrial_platform import init_platform_db, save_model_snapshot

    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "test.db")
        init_platform_db(db)
        model_id = save_model_snapshot(
            "Test Model",
            "MILP",
            {"objective": "cost"},
            "datahash",
            "engineer",
            {"assumption": "test"},
            db_path=db,
            version="2.0.0",
            solver_version="CBC 2.x",
            result_hash="resulthash",
            dataset_id="DS-1",
            run_id="RUN-1",
        )
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT version,solver_version,result_hash,dataset_id,run_id FROM platform_models WHERE model_id=?",
                (model_id,),
            ).fetchone()
        assert row == ("2.0.0", "CBC 2.x", "resulthash", "DS-1", "RUN-1")
