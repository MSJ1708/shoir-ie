import io
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import pytest

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
    research_evidence_bundle,
    save_project,
    analyze_fallback_module,
    fallback_module_blueprint,
    _starter_data,
    FALLBACK_MODULE_BLUEPRINTS,
    create_decision,
    load_decision_spec,
    save_decision_spec,
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
        actual_research_id, _ = create_research_protocol("PRJ-RUN-HISTORY", protocol, "alice")
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
            "PRJ-RUN-HISTORY", actual_research_id, "alice", cfg, results
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
        actual_research_id, _ = create_research_protocol("PRJ-IMPORT", protocol, "alice")
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
            "PRJ-IMPORT", actual_research_id, "alice", Upload()
        )
        assert run_id.startswith("RRUN-")
        assert summary["experiment_code"] == "001I"
        assert summary["observations"] == 2
        frame = research_runs_frame("PRJ-IMPORT", owner="alice")
        assert len(frame) == 1
        assert frame.iloc[0]["Experiment"] == "001I"



def test_production_fallback_coerces_excel_numeric_strings_without_mutating_input():
    source = pd.DataFrame({
        "Line": ["A", "B"],
        "Planned_Units": ["100", "200"],
        "Good_Units": ["95", "180"],
        "Scrap_Units": ["5", "20"],
    })
    original = source.copy(deep=True)

    result = analyze_fallback_module("Lean Manufacturing & Shop Floor Operations", source)

    assert result["metrics"]["Weighted good-unit yield (%)"] == 91.67
    assert result["result"]["Good_Unit_Yield_pct"].round(2).tolist() == [95.0, 90.0]
    pd.testing.assert_frame_equal(source, original)



def test_all_named_fallback_modules_run_on_their_starter_data():
    failures = []
    for module in sorted(FALLBACK_MODULE_BLUEPRINTS):
        starter = _starter_data(module)
        try:
            analysis = analyze_fallback_module(module, starter)
            result = analysis.get("result")
            metrics = analysis.get("metrics")
            if not isinstance(result, pd.DataFrame) or result.empty:
                failures.append(f"{module}: analysis returned no result rows")
            if not isinstance(metrics, dict):
                failures.append(f"{module}: analysis returned no metrics dictionary")
            if not analysis.get("method") or not analysis.get("guardrail"):
                failures.append(f"{module}: missing method or interpretation guardrail")
        except Exception as exc:
            failures.append(f"{module}: {type(exc).__name__}: {exc}")
    assert not failures, "\\n".join(failures)



def test_research_protocol_id_cannot_be_overwritten_by_another_owner(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "research-owner-boundary.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(db, timeout=30))
        ensure_experience_db(db)
        original = {
            "title": "Alice's protected study",
            "objective": "Original owner protocol",
            "research_question": "Does ownership remain enforced?",
            "hypothesis": "A different owner cannot overwrite the record.",
            "null_hypothesis": "A different owner can overwrite the record.",
            "methodology": "Controlled simulation benchmark",
            "primary_domain": "Manufacturing",
            "transfer_domain": "Maintenance",
            "primary_endpoint": "Normalized decision regret",
            "sample_size": 20,
            "replications": 2,
        }
        research_id, _ = create_research_protocol("PRJ-OWNER-GUARD", original, "alice")

        attempted = dict(original)
        attempted["title"] = "Bob's overwrite attempt"
        attempted["objective"] = "Attempt to replace Alice's record."
        with pytest.raises(PermissionError):
            create_research_protocol("PRJ-OWNER-GUARD", attempted, "bob")

        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT research_id,owner,title,objective FROM experience_research_studies WHERE study_id=?",
                ("PRJ-OWNER-GUARD",),
            ).fetchone()
        assert row == (research_id, "alice", "Alice's protected study", "Original owner protocol")


def test_load_research_protocol_and_evidence_bundle_enforce_owner(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "research-read-owner.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(db, timeout=30))
        ensure_experience_db(db)
        create_research_protocol(
            "PRJ-ALICE-PRIVATE",
            {"title": "Private Alice study", "objective": "Alice's objective"},
            "alice",
        )
        create_research_protocol(
            "PRJ-BOB-PRIVATE",
            {"title": "Private Bob study", "objective": "Bob's objective"},
            "bob",
        )

        assert ie.load_research_protocol("PRJ-ALICE-PRIVATE", owner="alice") is not None
        assert ie.load_research_protocol("PRJ-BOB-PRIVATE", owner="alice") is None
        with pytest.raises(PermissionError):
            research_evidence_bundle("PRJ-BOB-PRIVATE", owner="alice")

        bundle = research_evidence_bundle("PRJ-ALICE-PRIVATE", owner="alice")
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            exported = json.loads(archive.read("research_protocol.json").decode("utf-8"))
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert exported["title"] == "Private Alice study"
        assert manifest["owner"] == "alice"
        assert manifest["study_id"] == "PRJ-ALICE-PRIVATE"



def test_research_run_registration_rejects_another_owner_and_mismatched_protocol(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "research-run-owner-boundary.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(db, timeout=30))
        ensure_experience_db(db)
        alice_research_id, _ = create_research_protocol(
            "PRJ-ALICE-RUNS",
            {"title": "Alice protected study", "objective": "Only Alice may add runs"},
            "alice",
        )
        results = pd.DataFrame({
            "scenario": [1, 2],
            "decision_regret": [0.1, 0.2],
            "readiness_score": [0.8, 0.7],
            "split": ["development", "holdout"],
        })
        with pytest.raises(PermissionError):
            register_research_run(
                "PRJ-ALICE-RUNS", alice_research_id, "bob", {}, results
            )
        with pytest.raises(ValueError, match="does not match"):
            register_research_run(
                "PRJ-ALICE-RUNS", "RSH-UNRELATED", "alice", {}, results
            )

        frame = research_runs_frame("PRJ-ALICE-RUNS", owner="alice")
        assert frame.empty
        with sqlite3.connect(db) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM experience_research_runs WHERE study_id=?",
                ("PRJ-ALICE-RUNS",),
            ).fetchone()[0]
        assert count == 0


def test_project_autosave_rejects_other_owner_without_mutating_snapshot_or_payload(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "project-autosave-owner.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(db, timeout=30))
        ensure_experience_db(db)
        project_id = save_project(
            "Alice project", "Experiment Lab", "alice", {"value": "original"}
        )

        snapshot = ie.autosave_project(project_id, {"value": "alice update"}, owner="alice")
        assert snapshot == 2
        with pytest.raises(PermissionError):
            ie.autosave_project(project_id, {"value": "bob overwrite"}, owner="bob")

        with sqlite3.connect(db) as conn:
            owner, payload = conn.execute(
                "SELECT owner,payload_json FROM experience_projects WHERE project_id=?",
                (project_id,),
            ).fetchone()
            snapshots = conn.execute(
                "SELECT snapshot_no,payload_json FROM experience_project_snapshots WHERE project_id=? ORDER BY snapshot_no",
                (project_id,),
            ).fetchall()

        assert owner == "alice"
        assert __import__("json").loads(payload) == {"value": "alice update"}
        assert len(snapshots) == 2
        assert __import__("json").loads(snapshots[-1][1]) == {"value": "alice update"}


def test_autosave_materializes_missing_legacy_project_only_for_research_owner(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "restored-research-project.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(db, timeout=30))
        ensure_experience_db(db)
        study_id = "PRJ-RESTORED-REMOTE"
        protocol = {"title": "Alice restored protocol", "module": "Experiment Lab"}
        create_research_protocol(study_id, protocol, "alice")

        snapshot = ie.autosave_project(
            study_id,
            {"research_protocol": protocol, "protocol_type": "local_research_protocol"},
            owner="alice",
        )
        assert snapshot == 1
        with pytest.raises(PermissionError):
            ie.autosave_project(
                study_id,
                {"research_protocol": {"title": "Bob overwrite"}},
                owner="bob",
            )

        with sqlite3.connect(db) as conn:
            owner, title = conn.execute(
                "SELECT owner,name FROM experience_projects WHERE project_id=?",
                (study_id,),
            ).fetchone()
            count = conn.execute(
                "SELECT COUNT(*) FROM experience_project_snapshots WHERE project_id=?",
                (study_id,),
            ).fetchone()[0]
        assert (owner, title, count) == ("alice", "Alice restored protocol", 1)


def test_decision_spec_save_rejects_non_owner_and_preserves_original_spec(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "decision-spec-owner.db")
        monkeypatch.setattr(ie, "_db", lambda path=db: sqlite3.connect(db, timeout=30))
        ensure_experience_db(db)
        decision_id = create_decision(
            "Alice decision", "Quality", {"Cpk": 1.25}, {"baseline": "measured"},
            {"uncertainty": "medium"}, "alice"
        )
        save_decision_spec(
            decision_id, "alice", {"Cpk": 1.0}, [{"name": "current"}], {},
            ["Cpk"], {"interval": "95%"}, [{"source": "quality log"}], [],
        )

        with pytest.raises(PermissionError):
            save_decision_spec(
                decision_id, "bob", {"Cpk": -999}, [{"name": "overwrite"}], {},
                ["Cpk"], {}, [], [],
            )

        saved = load_decision_spec(decision_id, owner="alice")
        assert saved is not None
        assert saved["baseline"] == {"Cpk": 1.0}
        assert saved["owner"] == "alice"
        assert load_decision_spec(decision_id, owner="bob") is None
