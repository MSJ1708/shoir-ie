import hashlib

import pandas as pd

from shoir_enterprise_services import (
    data_intelligence_profile,
    detect_data_drift,
    replay_twin_what_if,
    safe_file_metadata,
)


def test_data_intelligence_detects_ids_units_outliers():
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


def test_drift_reports_numeric_mean_shift():
    reference = pd.DataFrame({"Demand": [100, 101, 99, 100, 102], "Code": ["A", "A", "B", "A", "B"]})
    current = pd.DataFrame({"Demand": [150, 151, 149, 150, 152], "Code": ["A", "B", "B", "B", "B"]})
    drift = detect_data_drift(current, reference)
    assert drift["available"] is True
    assert drift["max_shift"] > 0.2
    assert drift["flagged_fields"] >= 1


def test_twin_what_if_is_explicit_baseline_vs_scenario():
    twin = pd.DataFrame({
        "Asset": ["CNC-01", "CNC-01"],
        "Metric": ["Temperature", "Vibration"],
        "Value": [50.0, 2.0],
    })
    result = replay_twin_what_if(twin, "Temperature", 10)
    temp = result[result["Metric"] == "Temperature"].iloc[0]
    vibration = result[result["Metric"] == "Vibration"].iloc[0]
    assert temp["Baseline Value"] == 50.0
    assert temp["Scenario Value"] == 55.0
    assert vibration["Scenario Value"] == 2.0


def test_secure_file_metadata_is_path_safe_and_hashed():
    payload = b"test evidence"
    meta = safe_file_metadata("../../study/results.csv", payload, [".csv"])
    assert meta["filename"] == "results.csv"
    assert meta["sha256"] == hashlib.sha256(payload).hexdigest()
