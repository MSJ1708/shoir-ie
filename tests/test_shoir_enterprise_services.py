import hashlib

import numpy as np
import pandas as pd

from shoir_enterprise_services import (
    calculate_tco,
    data_intelligence_profile,
    detect_data_drift,
    detect_twin_anomalies,
    replay_twin_what_if,
    safe_file_metadata,
)


def test_data_intelligence_detects_ids_units_and_outliers():
    df = pd.DataFrame({
        "Asset ID": ["A", "B", "C", "D", "E", "F", "G", "H", "I"],
        "Temperature (C)": [10, 11, 10, 12, 9, 10, 11, 10, 80],
        "Event Date": pd.date_range("2026-01-01", periods=9),
    })
    profile = data_intelligence_profile(df)
    assert "Asset ID" in profile["id_like_columns"]
    assert any(x["Column"] == "Temperature (C)" for x in profile["unit_hints"])
    assert profile["outlier_counts"]["Temperature (C)"] >= 1
    assert profile["quality_score"] < 100


def test_drift_reports_numeric_shift():
    reference = pd.DataFrame({"Demand": [100, 101, 99, 100, 102], "Code": ["A", "A", "B", "A", "B"]})
    current = pd.DataFrame({"Demand": [150, 151, 149, 150, 152], "Code": ["A", "B", "B", "B", "B"]})
    drift = detect_data_drift(current, reference)
    assert drift["available"] is True
    assert drift["max_shift"] > 0.2
    assert drift["flagged_fields"] >= 1


def test_twin_what_if_and_anomaly_detection():
    twin = pd.DataFrame({
        "Asset": ["CNC-01"] * 5,
        "Metric": ["Temperature"] * 5,
        "Value": [50.0, 51.0, 49.0, 50.5, 90.0],
    })
    result = replay_twin_what_if(twin, "Temperature", 10)
    assert np.isclose(result.loc[0, "Baseline Value"], 50.0)
    assert np.isclose(result.loc[0, "Scenario Value"], 55.0)
    anomalies = detect_twin_anomalies(twin, 2.0)
    assert "Alert" in anomalies.columns
    assert (anomalies["Alert"] == "Investigate").any()


def test_secure_file_metadata_is_path_safe_and_hashed():
    payload = b"test evidence"
    meta = safe_file_metadata("../../study/results.csv", payload, [".csv"])
    assert meta["filename"] == "results.csv"
    assert meta["sha256"] == hashlib.sha256(payload).hexdigest()


def test_tco_schedule_is_transparent_and_discounted():
    drivers = pd.DataFrame({
        "Driver": ["CAPEX", "Maintenance"],
        "Annual Cost": [0.0, 1000.0],
        "Year 1 Cost": [10000.0, 0.0],
    })
    schedule, summary = calculate_tco(drivers, years=3, discount_rate=0.10)
    assert len(schedule) == 3
    assert summary["TCO (Nominal)"] == 13000.0
    assert summary["TCO (Discounted)"] < summary["TCO (Nominal)"]


def test_model_registry_provenance_schema_is_additive(tmp_path):
    from industrial_platform import init_platform_db, save_model_snapshot

    db = tmp_path / "registry.db"
    init_platform_db(str(db))
    model_id = save_model_snapshot(
        "Test Model",
        "MILP",
        {"objective": "cost"},
        "DATAHASH",
        "tester",
        {"assumption": "test"},
        db_path=str(db),
        solver_version="CBC-test",
        result_hash="RESHASH",
    )
    import sqlite3
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT solver_version,result_hash FROM platform_models WHERE model_id=?",
            (model_id,),
        ).fetchone()
    assert row == ("CBC-test", "RESHASH")
