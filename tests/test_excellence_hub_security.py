import sqlite3

import pytest

from industrial_experience import (create_decision, create_job, decision_approval_history, ensure_experience_db, research_runs_frame, transition_decision, update_job)
from industrial_excellence_hub import _self_diagnostic_report


def test_legacy_job_rows_are_preserved_and_owner_migration_is_additive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "enterprise_full_workspace.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE experience_jobs("
            "job_id TEXT PRIMARY KEY,module TEXT,job_type TEXT,status TEXT,progress REAL,"
            "message TEXT,payload_json TEXT,started_at TEXT,finished_at TEXT)"
        )
        conn.execute(
            "INSERT INTO experience_jobs VALUES(?,?,?,?,?,?,?,?,?)",
            ("legacy-job", "Legacy module", "legacy", "Queued", 0.0, "Existing row", "{}", None, None),
        )
        conn.commit()

    ensure_experience_db()
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(experience_jobs)")}
        legacy = conn.execute(
            "SELECT job_id,status,owner FROM experience_jobs WHERE job_id='legacy-job'"
        ).fetchone()

    assert "owner" in columns
    assert legacy == ("legacy-job", "Queued", None)


def test_job_updates_can_be_restricted_to_the_owning_actor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_experience_db()
    job_id = create_job("Test module", "test", "alice", {"sample": True})

    with sqlite3.connect(tmp_path / "enterprise_full_workspace.db") as conn:
        owner = conn.execute(
            "SELECT owner FROM experience_jobs WHERE job_id=?", (job_id,)
        ).fetchone()[0]
    assert owner == "alice"

    with pytest.raises(PermissionError):
        update_job(job_id, "Cancelled", 100, "unauthorized attempt", actor="bob")

    update_job(job_id, "Running", 25, "owned update", actor="alice")
    with sqlite3.connect(tmp_path / "enterprise_full_workspace.db") as conn:
        status, message = conn.execute(
            "SELECT status,message FROM experience_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
    assert (status, message) == ("Running", "owned update")


def test_excellence_self_diagnostic_does_not_claim_unrun_integrations_pass(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_experience_db()
    report = _self_diagnostic_report()

    assert {"Check", "Status", "Evidence"} <= set(report.columns)
    connectivity = report.loc[report["Check"] == "Live connector connectivity", "Status"].iloc[0]
    e2e = report.loc[report["Check"] == "Authenticated imports, exports and tenant isolation", "Status"].iloc[0]
    assert connectivity == "NOT TESTED"
    assert e2e == "NOT TESTED"
    assert "PASS" not in {connectivity, e2e}



def test_research_run_compatibility_view_does_not_mix_users_jobs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_experience_db()
    alice_job = create_job(
        "Research module", "experiment", "alice",
        {"study_id": "study-alpha", "experiment_code": "alice-only"},
    )
    bob_job = create_job(
        "Research module", "experiment", "bob",
        {"study_id": "study-alpha", "experiment_code": "bob-only"},
    )

    alice_view = research_runs_frame("study-alpha", owner="alice")

    assert alice_job in set(alice_view["Run ID"])
    assert bob_job not in set(alice_view["Run ID"])



def test_hub_decision_transition_and_history_are_owner_scoped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_experience_db()
    alice_decision = create_decision(
        "Alice decision", "Quality", {"Cpk": 1.2}, {}, {}, "alice"
    )
    create_decision("Bob decision", "Maintenance", {}, {}, {}, "bob")

    transition_decision(
        alice_decision, "alice", "Review", "Ready for review", require_owner=True
    )
    with pytest.raises(PermissionError):
        transition_decision(
            alice_decision, "bob", "Approved", "unauthorized", require_owner=True
        )

    alice_history = decision_approval_history(alice_decision, owner="alice")
    bob_view = decision_approval_history(alice_decision, owner="bob")
    assert len(alice_history) == 1
    assert alice_history.iloc[0]["To"] == "Review"
    assert bob_view.empty

    import sqlite3
    with sqlite3.connect(tmp_path / "enterprise_full_workspace.db") as conn:
        state = conn.execute(
            "SELECT status FROM experience_decisions WHERE decision_id=?",
            (alice_decision,),
        ).fetchone()[0]
    assert state == "Review"
