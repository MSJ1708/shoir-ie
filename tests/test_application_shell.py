import json
import os
import sqlite3

import pandas as pd

from shoir_application_shell import (
    PASTED_SPEC_UPDATES,
    PROVENANCE_STATES,
    _flatten_variance,
    data_readiness,
    ensure_shell_schema,
    infer_provenance,
    module_group,
    build_module_index,
)


def test_readiness_identifies_missing_and_duplicates():
    df = pd.DataFrame({"Asset ID": ["A1", "A1", "A2", "A3"], "Qty": [10, 10, None, 20]})
    result = data_readiness(df)
    assert result["rows"] == 4
    assert result["columns"] == 2
    assert result["duplicate_pct"] > 0
    assert result["missing_pct"] > 0
    assert 0 <= result["score"] <= 100


def test_module_groups_cover_core_engineering_families():
    assert module_group("Excel Data Cleaning & Import") == "Data"
    assert module_group("Fleet Routing") == "Supply Chain"
    assert module_group("Quality Control, Six Sigma & Reliability") == "Quality"
    assert module_group("Digital Twin & Discrete-Event Simulation") == "Maintenance"
    assert module_group("Statistical Hypothesis Testing") == "Research"
    assert module_group("Engineering Decision Center") == "Platform & Governance"


def test_module_index_is_searchable_metadata():
    index = build_module_index(["MILP Solvers", "Excel Data Cleaning & Import", "Experiment Engine"])
    assert list(index["Module"]) == ["MILP Solvers", "Excel Data Cleaning & Import", "Experiment Engine"]
    assert set(index["Group"]) == {"Industrial Engineering", "Data", "Research"}


def test_provenance_states_are_explicit():
    assert set(PROVENANCE_STATES) == {"LIVE", "IMPORTED", "SIMULATED", "DEMO"}
    assert "provenance_state_contract" in PASTED_SPEC_UPDATES
    assert "presentation_mode" in PASTED_SPEC_UPDATES


def test_variance_calculation_is_numeric_and_traceable():
    expected = {"Throughput": 100, "Cost": 120}
    actual = {"Throughput": 112, "Cost": 126}
    result = _flatten_variance(expected, actual)
    assert result.loc[result["Metric"] == "Throughput", "Variance"].iloc[0] == 12
    assert result.loc[result["Metric"] == "Cost", "Variance %"].iloc[0] == 5


def test_shell_schema_can_be_created(tmp_path):
    db = tmp_path / "shell.db"
    ensure_shell_schema(str(db))
    with sqlite3.connect(db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "shoir_shell_decision_outcomes" in tables
