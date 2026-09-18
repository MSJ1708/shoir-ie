import json
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from industrial_operating_system import (
    compare_frames,
    decision_verify,
    drift_report,
    process_mining_discovery,
    safe_formula,
)


def test_safe_formula_rejects_code_execution():
    assert safe_formula("a * 2 + b", {"a": 3, "b": 4}) == 10
    with pytest.raises(ValueError):
        safe_formula("__import__('os').system('echo bad')", {"a": 1})


def test_compare_frames_produces_delta_columns():
    a = pd.DataFrame({"ID": ["A", "B"], "Cost": [100, 200]})
    b = pd.DataFrame({"ID": ["A", "B"], "Cost": [110, 180]})
    out = compare_frames(a, b, "ID")
    assert "Cost — Δ" in out.columns
    assert "Cost — Δ%" in out.columns
    assert out.loc[out["ID"] == "A", "Cost — Δ"].iloc[0] == 10


def test_process_mining_discovery_and_conformance():
    events = pd.DataFrame({
        "Case ID": ["1", "1", "1", "2", "2", "2"],
        "Activity": ["Create", "Pick", "Ship", "Create", "Pick", "Ship"],
        "Timestamp": pd.to_datetime([
            "2026-09-01 08:00", "2026-09-01 09:00", "2026-09-01 10:00",
            "2026-09-02 08:00", "2026-09-02 09:00", "2026-09-02 11:00",
        ]),
    })
    result = process_mining_discovery(events, expected_sequence=["Create", "Pick", "Ship"])
    assert result["cases"] == 2
    assert result["variant_count"] == 1
    assert result["conformance"] == 100


def test_drift_report_flags_shifted_numeric_distribution():
    rng = np.random.default_rng(7)
    ref = pd.DataFrame({"x": rng.normal(0, 1, 200)})
    cur = pd.DataFrame({"x": rng.normal(4, 1, 200)})
    result = drift_report(ref, cur)
    assert list(result["Feature"]) == ["x"]
    assert bool(result["Flagged"].iloc[0]) is True


def test_decision_verify_calculates_error():
    pred = pd.DataFrame({"Metric": ["Cost"], "Value": [100]})
    actual = pd.DataFrame({"Metric": ["Cost"], "Value": [110]})
    out = decision_verify("TEST-1", pred, actual, verified_by="pytest")
    assert out["Absolute Error"].iloc[0] == 10
    assert out["Percent Error"].iloc[0] == 10
