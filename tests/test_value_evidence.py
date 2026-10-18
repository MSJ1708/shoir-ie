"""Regression tests for trustworthy value evidence and financial persistence."""
import sqlite3

import pytest

from shoir_value_evidence import (
    calculate_financial_bridge,
    calculate_time_value,
    ensure_value_evidence_db,
    record_time_snapshot,
    save_financial_bridge_record,
)


def test_time_value_uses_explicit_before_after_inputs():
    result = calculate_time_value(180, 30, studies_per_year=10, hourly_rate=250)
    assert result["baseline_hours"] == pytest.approx(3)
    assert result["shoir_hours"] == pytest.approx(0.5)
    assert result["hours_saved"] == pytest.approx(2.5)
    assert result["annual_capacity_hours"] == pytest.approx(25)
    assert result["annual_time_value"] == pytest.approx(6250)


@pytest.mark.parametrize(
    "args",
    [
        (-1, 10, 1, 10),
        (10, float("nan"), 1, 10),
        (10, 1, float("inf"), 10),
        (10, 1, 1, -1),
        ("unknown", 1, 1, 10),
    ],
)
def test_time_value_rejects_invalid_inputs_instead_of_silently_zeroing(args):
    with pytest.raises(ValueError):
        calculate_time_value(*args)


def test_financial_bridge_matches_documented_formula_and_labels_estimate():
    result = calculate_financial_bridge(1000, 800, 100, 12)
    assert result["calculated_period_net_benefit"] == pytest.approx(100)
    assert result["verified_period_benefit"] == pytest.approx(100)  # legacy key, no longer called verified in UI
    assert result["annualized_operational_benefit"] == pytest.approx(2400)
    assert result["annual_net_benefit"] == pytest.approx(2300)
    assert result["roi_percent"] == pytest.approx(2300)
    assert result["payback_months"] == pytest.approx(0.5)
    assert "not a verified" in result["classification"]


@pytest.mark.parametrize("args", [(-1, 0, 0, 1), (1, float("inf"), 0, 1), (1, 0, -1, 1), (1, 0, 0, float("nan"))])
def test_financial_bridge_rejects_negative_or_nonfinite_inputs(args):
    with pytest.raises(ValueError):
        calculate_financial_bridge(*args)


def test_financial_record_inserts_all_fields_and_stores_review_provenance(tmp_path):
    db = str(tmp_path / "value.db")
    record = save_financial_bridge_record(
        "alice", "Capacity Study", 1000, 800, 100, 12,
        source="MES extract RUN-17",
        evidence_state="Customer measured",
        currency="SAR",
        db_path=db,
    )
    assert record["calculation"]["calculated_period_net_benefit"] == pytest.approx(100)
    assert len(record["bridge_sha256"]) == 64
    assert record["source_authentication"] == "Not independently authenticated by Shoir-IE"

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            """SELECT verified_economic_benefit,evidence_state,reviewer_reference,bridge_sha256,source
               FROM shoir_value_financial_bridges WHERE bridge_id=?""",
            (record["bridge_id"],),
        ).fetchone()
    assert row[0] == pytest.approx(100)
    assert row[1] == "Customer measured"
    assert row[2] == ""
    assert row[3] == record["bridge_sha256"]
    assert row[4] == "MES extract RUN-17"


def test_independent_review_is_only_user_attested_and_requires_reviewer_reference(tmp_path):
    db = str(tmp_path / "review.db")
    state = "Independent review record (user-attested; not authenticated)"
    with pytest.raises(ValueError, match="reviewer reference is required"):
        save_financial_bridge_record(
            "alice", "Study", 100, 80, 5,
            source="Customer record", evidence_state=state, db_path=db,
        )
    record = save_financial_bridge_record(
        "alice", "Study", 100, 80, 5,
        source="Customer record",
        evidence_state=state,
        reviewer_reference="Review package REV-03",
        db_path=db,
    )
    assert record["reviewer_reference"] == "Review package REV-03"
    assert "not authenticated" in record["evidence_state"]


def test_existing_legacy_financial_table_is_migrated_without_breaking_snapshots(tmp_path):
    db = str(tmp_path / "legacy.db")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE shoir_value_financial_bridges (
                bridge_id TEXT PRIMARY KEY, owner TEXT NOT NULL, module TEXT NOT NULL,
                baseline_cost REAL NOT NULL, post_cost REAL NOT NULL, implementation_cost REAL NOT NULL,
                verified_economic_benefit REAL NOT NULL, frequency_per_year REAL NOT NULL,
                annualized_operational_benefit REAL NOT NULL, annual_net_benefit REAL NOT NULL,
                roi_percent REAL NOT NULL, payback_months REAL, currency TEXT NOT NULL,
                source TEXT NOT NULL, created_at TEXT NOT NULL
            )"""
        )
        conn.commit()

    ensure_value_evidence_db(db)
    record = save_financial_bridge_record(
        "alice", "Migrated study", 200, 100, 25, 4,
        source="legacy migration test", db_path=db,
    )
    values = {
        "baseline_hours": 3.0,
        "shoir_hours": 1.0,
        "hours_saved": 2.0,
        "annual_capacity_hours": 4.0,
        "annual_time_value": 1000.0,
        "currency": "SAR",
    }
    snapshot_id = record_time_snapshot("alice", "Migrated study", "Test task", values, "measured time-study reference")
    assert record["bridge_sha256"]
    assert snapshot_id.startswith("VE-")
    with sqlite3.connect(db) as conn:
        snapshot_count = conn.execute("SELECT COUNT(*) FROM shoir_value_snapshots").fetchone()[0]
        columns = {row[1] for row in conn.execute("PRAGMA table_info(shoir_value_financial_bridges)")}
    assert snapshot_count == 1
    assert {"evidence_state", "reviewer_reference", "bridge_sha256"} <= columns


def test_application_latency_receipt_does_not_create_false_time_saved_claims():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "shoir_value_evidence.py").read_text(encoding="utf-8")
    start = source.index("def render_value_receipt(")
    end = source.index("\ndef render_value_pulse", start)
    receipt = source[start:end]
    assert "Observed application execution duration" in receipt
    assert "not the total time an engineer spends completing the task" in receipt
    assert "record_time_snapshot(" not in receipt
    assert '"time_saved_hours": None' in receipt
