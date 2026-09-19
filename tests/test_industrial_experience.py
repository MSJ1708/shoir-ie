import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from industrial_experience import FEATURES_60, compute_evidence_roi, ensure_experience_db, feature_stats, generic_result, verification_snapshot


def test_feature_catalog_has_exactly_60_capabilities():
    assert len(FEATURES_60) == 60
    stats = feature_stats()
    assert stats["total"] == 60
    assert stats["implemented"] == 58
    assert stats["integration_ready"] == 2


def test_experience_database_is_idempotent():
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "experience.db")
        ensure_experience_db(db)
        ensure_experience_db(db)
        with sqlite3.connect(db) as conn:
            names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "experience_projects" in names
        assert "experience_decisions" in names
        assert "experience_jobs" in names
        assert "experience_copilot_actions" in names


def test_generic_result_and_verification_are_numeric_safe():
    df = pd.DataFrame({"Area": ["A", "B"], "Baseline": [100.0, 90.0], "Scenario": [95.0, 88.0]})
    result = generic_result(df)
    verification = verification_snapshot(df)
    assert result["rows"] == 2
    assert result["numeric_fields"] == 2
    assert verification["score"] == 100.0


def test_evidence_roi_is_transparent_and_assumption_driven():
    result = compute_evidence_roi(2500, 120, 5)
    assert result["baseline_monthly_value"] == 300000
    assert result["illustrative_monthly_impact"] == 15000
    assert result["illustrative_annual_impact"] == 180000
