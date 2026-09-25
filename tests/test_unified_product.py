import tempfile
from pathlib import Path

import pandas as pd

from shoir_unified_product import (
    assess_data_readiness,
    explain_scenario,
    recommendations_for,
    ensure_unified_db,
    _starter_for_module,
)


def test_unified_readiness_gate_is_deterministic():
    df = pd.DataFrame({"SKU": ["A", "B"], "Demand": [100, 120]})
    result = assess_data_readiness(df, ["SKU", "Demand"])
    assert result["score"] == 100.0
    assert result["passed"] == result["total"]


def test_unified_readiness_flags_missing_and_duplicates():
    df = pd.DataFrame({"SKU": ["A", "A"], "Demand": [100, 100]})
    result = assess_data_readiness(df, ["SKU", "Demand", "Date"])
    assert result["score"] < 100
    assert any("Missing: Date" in c["detail"] for c in result["checks"])
    assert any(c["name"] == "Duplicate rows" and not c["status"] for c in result["checks"])


def test_starter_studios_are_domain_specific():
    quality = _starter_for_module("Quality Engineering & Reliability")
    carbon = _starter_for_module("Industrial Sustainability & LCA")
    assert "Process" in quality.columns
    assert "Area" in carbon.columns
    assert "Baseline" in quality.columns and "Scenario" in quality.columns


def test_scenario_explanation_and_recommendations():
    baseline = {"Scenario": "Baseline", "Cost": 100, "Service": 95, "Carbon": 100, "Risk": 10}
    scenario = {"Scenario": "A", "Cost": 92, "Service": 97, "Carbon": 88, "Risk": 8}
    text = explain_scenario(scenario, baseline)
    assert "Cost: lower by 8.0" in text
    recs = recommendations_for("warehouse optimization", 80, 1, "Draft")
    assert recs and "Resolve" in recs[0]


def test_unified_database_is_idempotent():
    with tempfile.TemporaryDirectory() as td:
        # The shared DB helper is intentionally fixed to the application DB;
        # this test validates that its schema statements remain repeatable.
        ensure_unified_db()
        ensure_unified_db()
        assert Path("enterprise_full_workspace.db").exists()
