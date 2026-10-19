import json
import sqlite3

import pandas as pd
import pytest

from shoir_shadowshift import (
    CAUSES, EVENT_TYPES, add_event, calculate_loss_metrics, clean_event_frame,
    create_study, ensure_shadowshift_schema, list_experiments, list_studies, load_events,
    rank_next_experiments, record_experiment_result, save_analysis_snapshot, save_experiment,
    load_snapshots, replace_events,
)


def _events():
    return pd.DataFrame([
        {"Event type": "Waiting / blocked", "Station": "A", "Interruption min": 10, "Recovery min": 5,
         "People affected": 2, "Suspected cause": "Material / tool availability",
         "Evidence strength (1-5)": 3, "Evidence source": "Direct observation", "Notes": "Observed"},
        {"Event type": "Equipment stop / reset", "Station": "B", "Interruption min": 20, "Recovery min": 5,
         "People affected": 1, "Suspected cause": "Equipment / reset",
         "Evidence strength (1-5)": 4, "Evidence source": "Machine / system log", "Notes": "Observed"},
    ])


def test_metrics_separate_interruption_recovery_and_modelled_stress():
    result = calculate_loss_metrics(_events(), 60, 480, 250, 50, 1.5)
    assert result["interruption_minutes_observed"] == 30
    assert result["recovery_minutes_observed"] == 10
    assert result["observed_elapsed_burden_minutes"] == 40
    assert result["people_weighted_labor_minutes_observed"] == 55
    assert result["projected_elapsed_burden_minutes_per_shift"] == 320
    assert result["modeled_downstream_extra_minutes_per_shift"] == 160
    assert result["projected_labor_hours_per_shift"] == 55 / 60 * 8
    assert result["annual_gross_labor_exposure_sar"] == (55 / 60 * 8) * 250 * 50
    assert result["is_extrapolation"] is True


def test_empty_events_give_zero_exposure():
    result = calculate_loss_metrics(pd.DataFrame(), 60, 480, 250, 50, 2)
    assert result["event_count"] == 0
    assert result["observed_elapsed_burden_minutes"] == 0
    assert result["annual_gross_labor_exposure_sar"] == 0
    assert result["modeled_downstream_extra_minutes_per_shift"] == 0
    assert result["is_extrapolation"] is False


def test_event_normalization_bounds_invalid_values():
    d = clean_event_frame(pd.DataFrame([{
        "Event type": "bogus", "Station": "X", "Interruption min": -5, "Recovery min": "bad",
        "People affected": 0, "Suspected cause": "unmapped", "Evidence strength (1-5)": 99,
        "Evidence source": "web", "Notes": "test",
    }]))
    row = d.iloc[0]
    assert row["Event type"] == "Other / unclassified"
    assert row["Interruption min"] == 0
    assert row["Recovery min"] == 0
    assert row["People affected"] == 1
    assert row["Suspected cause"] == "Unknown / not yet tested"
    assert row["Evidence strength (1-5)"] == 5
    assert row["Evidence source"] == "Operator report"


def test_next_experiment_has_baseline_recommendation_without_events():
    ranked = rank_next_experiments(pd.DataFrame())
    assert ranked.iloc[0]["Cause"] == "Unknown / not yet tested"
    assert ranked.iloc[0]["Priority score (relative)"] == 100
    assert "next 5 events" in ranked.iloc[0]["Recommended test"]


def test_observed_causes_produce_ranked_test_candidates():
    ranked = rank_next_experiments(_events())
    assert ranked.iloc[0]["Priority score (relative)"] == 100
    assert ranked["Cause"].isin(CAUSES).all()
    assert ranked["Rank"].tolist() == list(range(1, len(ranked) + 1))
    assert ranked["Effort min"].gt(0).all()


def test_study_and_experiment_persistence_is_owner_scoped(tmp_path):
    db = str(tmp_path / "shadowshift.sqlite")
    ensure_shadowshift_schema(db)
    study_id = create_study("alice", db_path=db)
    assert len(list_studies("alice", db_path=db)) == 1
    assert list_studies("bob", db_path=db).empty
    add_event(study_id, "alice", {
        "Event type": EVENT_TYPES[0], "Station": "A", "Interruption min": 2, "Recovery min": 1,
        "People affected": 1, "Suspected cause": CAUSES[0], "Evidence strength (1-5)": 3,
        "Evidence source": "Direct observation", "Notes": "test",
    }, db_path=db)
    assert len(load_events(study_id, "alice", db_path=db)) == 1
    assert load_events(study_id, "bob", db_path=db).empty
    eid = save_experiment(study_id, "alice", {
        "hypothesis": "Testable hypothesis", "comparison_condition": "Current method",
        "test_condition": "Checklist", "primary_metric": "Recovery", "unit": "min",
        "target_n": 5, "planned_minutes": 20, "expected_direction": "Decrease",
    }, db_path=db)
    result = {"control_value": 4, "test_value": 2, "unit": "min", "observations_completed": 5,
              "conclusion": "Supports hypothesis", "notes": "Small pilot"}
    assert record_experiment_result(eid, study_id, "alice", result, db_path=db)
    assert not record_experiment_result(eid, study_id, "bob", result, db_path=db)
    data = list_experiments(study_id, "alice", db_path=db)
    assert len(data) == 1
    assert data.iloc[0]["Status"] == "Measured"
    assert json.loads(data.iloc[0]["Result"])["test_value"] == 2



def test_event_replacement_is_atomic_when_import_contains_duplicate_ids(tmp_path):
    db = str(tmp_path / "shadowshift.sqlite")
    ensure_shadowshift_schema(db)
    study_id = create_study("alice", db_path=db)
    original = _events().iloc[[0]].copy()
    original["Event ID"] = "stable-event"
    assert replace_events(study_id, "alice", original, db_path=db) == 1
    before = load_events(study_id, "alice", db_path=db)

    invalid_replacement = pd.concat([original, original], ignore_index=True)
    with pytest.raises(sqlite3.IntegrityError):
        replace_events(study_id, "alice", invalid_replacement, db_path=db)

    after = load_events(study_id, "alice", db_path=db)
    pd.testing.assert_frame_equal(before, after)


def test_snapshots_are_owner_scoped_and_hash_normalized_event_evidence(tmp_path):
    db = str(tmp_path / "shadowshift.sqlite")
    ensure_shadowshift_schema(db)
    study_id = create_study("alice", db_path=db)
    events = _events()
    snapshot_id, evidence_hash = save_analysis_snapshot(
        study_id, "alice", {"observation_window_min": 60},
        {"observed_burden_min": 40}, events, db_path=db,
    )
    assert len(evidence_hash) == 64
    assert snapshot_id in set(load_snapshots(study_id, "alice", db_path=db)["Snapshot ID"])
    assert load_snapshots(study_id, "bob", db_path=db).empty


def test_cross_owner_event_mutations_are_rejected(tmp_path):
    db = str(tmp_path / "shadowshift.sqlite")
    ensure_shadowshift_schema(db)
    study_id = create_study("alice", db_path=db)
    with pytest.raises(ValueError, match="current owner"):
        add_event(study_id, "bob", _events().iloc[0].to_dict(), db_path=db)
    with __import__("pytest").raises(ValueError, match="current owner"):
        replace_events(study_id, "bob", _events(), db_path=db)



def test_non_finite_measurements_are_normalized_before_projection():
    frame = clean_event_frame(pd.DataFrame([{
        "Event type": EVENT_TYPES[0],
        "Station": "A",
        "Interruption min": float("inf"),
        "Recovery min": float("-inf"),
        "People affected": float("inf"),
        "Evidence strength (1-5)": float("inf"),
    }]))
    row = frame.iloc[0]
    assert row["Interruption min"] == 0
    assert row["Recovery min"] == 0
    assert row["People affected"] == 1
    assert row["Evidence strength (1-5)"] == 3
    metrics = calculate_loss_metrics(frame, 60, 480, 250, 50, 2)
    assert metrics["observed_elapsed_burden_minutes"] == 0
    assert metrics["annual_gross_labor_exposure_sar"] == 0
