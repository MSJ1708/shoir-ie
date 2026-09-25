import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

import industrial_experience as ie
from industrial_experience import (
    FEATURES_60,
    compute_evidence_roi,
    ensure_experience_db,
    feature_stats,
    generic_result,
    verification_snapshot,
    create_research_protocol,
    load_research_protocol,
    list_research_studies,
    recover_legacy_research_studies,
    restore_decision_readiness_study,
    register_research_run,
    import_research_run_csv,
    research_runs_frame,
    save_project,
)


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


def test_research_protocol_update_keeps_stable_research_id(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "research.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(db, timeout=30))
        ensure_experience_db(db)
        protocol = {
            "title": "Boundary Study",
            "objective": "Test evidence degradation.",
            "research_question": "Does evidence degradation change decision reliability?",
            "hypothesis": "Joint degradation produces a measurable boundary.",
            "null_hypothesis": "Joint degradation does not produce a measurable boundary.",
            "methodology": "Controlled simulation benchmark",
            "primary_domain": "Manufacturing",
            "transfer_domain": "Maintenance",
            "primary_endpoint": "Normalized decision regret",
            "secondary_metrics": ["cost"],
            "independent_variables": ["evidence completeness"],
            "controls": ["scenario seed"],
            "baseline_definition": "Clean evidence baseline.",
            "treatment_definition": "Degraded evidence treatment.",
            "sample_size": 20,
            "replications": 2,
            "random_seed": 2026,
            "alpha": 0.05,
            "confidence_level": 0.95,
            "planned_tests": ["paired comparison"],
            "inclusion_criteria": "Valid scenarios.",
            "exclusion_criteria": "Invalid scenarios.",
            "data_source": "Synthetic",
            "protocol_notes": "Test",
            "protocol_locked": False,
        }
        create_research_protocol("PRJ-TEST", protocol, "alice")
        first = load_research_protocol("PRJ-TEST")
        protocol["objective"] = "Updated objective."
        create_research_protocol("PRJ-TEST", protocol, "alice")
        second = load_research_protocol("PRJ-TEST")
        assert first["research_id"] == second["research_id"]
        assert second["objective"] == "Updated objective."
        assert second["created_at"] == first["created_at"]


def test_legacy_research_project_can_be_recovered(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "research.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(db, timeout=30))
        ensure_experience_db(db)
        protocol = {
            "title": "Recovered Study",
            "objective": "Recover old protocol.",
            "research_question": "Can a saved protocol be restored?",
            "hypothesis": "A persisted project payload can reconstruct the protocol.",
            "null_hypothesis": "The project payload cannot reconstruct the protocol.",
            "methodology": "Controlled simulation benchmark",
            "primary_domain": "Manufacturing",
            "transfer_domain": "Maintenance",
            "primary_endpoint": "Normalized decision regret",
            "secondary_metrics": ["cost"],
            "independent_variables": ["evidence completeness"],
            "controls": ["scenario seed"],
            "baseline_definition": "Baseline.",
            "treatment_definition": "Treatment.",
            "sample_size": 20,
            "replications": 2,
            "random_seed": 2026,
            "alpha": 0.05,
            "confidence_level": 0.95,
            "planned_tests": ["paired comparison"],
            "inclusion_criteria": "Valid.",
            "exclusion_criteria": "Invalid.",
            "data_source": "Synthetic",
            "protocol_notes": "Recovery test.",
            "protocol_locked": False,
        }
        project_id = save_project(
            "Recovered Study",
            "Experiment Lab",
            "alice",
            {"research_protocol": protocol, "protocol_type": "local_research_protocol"},
        )
        assert list_research_studies("alice").empty
        recovered = recover_legacy_research_studies("alice")
        assert len(recovered) == 1
        restored = load_research_protocol(project_id)
        assert restored is not None
        assert restored["title"] == "Recovered Study"
        assert len(list_research_studies("alice")) == 1


def test_legacy_app_saved_project_can_be_recovered(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "research.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(path, timeout=30))
        ensure_experience_db(db)
        protocol = {
            "title": "Recovered App-Level Study",
            "objective": "Recover a protocol from the legacy saved-project table.",
            "research_question": "Can the older saved_projects record be recovered?",
            "hypothesis": "Legacy app storage can reconstruct the research protocol.",
            "null_hypothesis": "Legacy app storage cannot reconstruct the research protocol.",
            "methodology": "Controlled simulation benchmark",
            "primary_domain": "Manufacturing",
            "transfer_domain": "Maintenance",
            "primary_endpoint": "Normalized decision regret",
            "secondary_metrics": ["cost"],
            "independent_variables": ["evidence uncertainty"],
            "controls": ["scenario seed"],
            "baseline_definition": "Baseline.",
            "treatment_definition": "Treatment.",
            "sample_size": 20,
            "replications": 2,
            "random_seed": 2026,
            "alpha": 0.05,
            "confidence_level": 0.95,
            "planned_tests": ["paired comparison"],
            "inclusion_criteria": "Valid.",
            "exclusion_criteria": "Invalid.",
            "data_source": "Synthetic",
            "protocol_notes": "Legacy app recovery test.",
            "protocol_locked": False,
        }
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE saved_projects (name TEXT PRIMARY KEY, data TEXT, updated_at TEXT)")
            payload = {"research_protocol": protocol, "owner": "alice"}
            conn.execute(
                "INSERT INTO saved_projects(name,data,updated_at) VALUES(?,?,?)",
                ("Recovered App-Level Study", __import__("json").dumps(payload), "2026-09-24T00:00:00Z"),
            )
            conn.commit()

        recovered = recover_legacy_research_studies("alice")
        assert len(recovered) == 1
        assert recovered.iloc[0]["Title"] == "Recovered App-Level Study"
        assert len(list_research_studies("alice")) == 1


def test_decision_readiness_restore_is_idempotent(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "research.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(path, timeout=30))
        ensure_experience_db(db)
        first_id, first_rid = restore_decision_readiness_study("alice")
        second_id, second_rid = restore_decision_readiness_study("alice")
        assert first_id == second_id
        assert first_rid == second_rid
        restored = load_research_protocol(first_id, owner="alice")
        assert restored is not None
        assert restored["title"] == "Industrial AI Decision-Readiness Boundary — Experiment 001"


def test_research_run_history_persists_completed_run(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "research.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(path, timeout=30))
        ensure_experience_db(db)
        protocol = {
            "title": "Run History Study",
            "research_id": "RSH-TEST123",
            "primary_endpoint": "Normalized decision regret",
            "sample_size": 20,
            "replications": 2,
        }
        create_research_protocol("PRJ-RUN-HISTORY", protocol, "alice")
        results = pd.DataFrame({
            "scenario": [1,2,3,4],
            "decision_regret": [0.10,0.20,0.15,0.25],
            "readiness_score": [0.8,0.7,0.75,0.65],
            "split": ["development","development","holdout","holdout"],
        })
        cfg = {
            "evidence_completeness": 75,
            "evidence_freshness_hours": 6,
            "evidence_conflict_pct": 10,
            "evidence_uncertainty_pct": 20,
            "shock_severity": 0.0,
        }
        run_id = register_research_run(
            "PRJ-RUN-HISTORY", "RSH-TEST123", "alice", cfg, results
        )
        frame = research_runs_frame("PRJ-RUN-HISTORY", owner="alice")
        assert len(frame) == 1
        assert frame.iloc[0]["Experiment"] == "001I"
        assert frame.iloc[0]["Observations"] == 4
        assert abs(float(frame.iloc[0]["Mean regret"]) - 0.2) < 1e-12
        loaded = ie.load_research_run(run_id, owner="alice")
        assert loaded is not None
        assert len(loaded["results"]) == 4


def test_previous_lab_csv_can_be_imported_into_research_registry(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "research.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(path, timeout=30))
        ensure_experience_db(db)
        protocol = {
            "title": "Boundary Study",
            "primary_endpoint": "Normalized decision regret",
            "sample_size": 200,
            "replications": 20,
            "methodology": "Controlled simulation benchmark",
            "primary_domain": "Manufacturing",
            "transfer_domain": "Maintenance",
        }
        create_research_protocol("PRJ-IMPORT", protocol, "alice")
        csv = (
            "scenario,decision_regret,readiness_score,evidence_completeness,evidence_freshness_hours,"
            "evidence_conflict_pct,evidence_uncertainty_pct,shock_severity,split\n"
            "1,0.12,0.77409,75,6,10,20,0.0,development\n"
            "2,0.10,0.77409,75,6,10,20,0.0,holdout\n"
        )
        class Upload:
            def getvalue(self):
                return csv.encode("utf-8")
        run_id, summary = import_research_run_csv(
            "PRJ-IMPORT", "RSH-TEST", "alice", Upload()
        )
        assert run_id.startswith("RRUN-")
        assert summary["experiment_code"] == "001I"
        assert summary["observations"] == 2
        frame = research_runs_frame("PRJ-IMPORT", owner="alice")
        assert len(frame) == 1
        assert frame.iloc[0]["Experiment"] == "001I"
