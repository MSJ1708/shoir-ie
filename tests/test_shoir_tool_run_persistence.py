"""Workspace persistence tests for Engineering Tool Library results."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from shoir_tool_run_persistence import persist_tool_run_record
from workspace_persistence import load_user_workspace, save_user_workspace


def test_tool_result_survives_workspace_save_and_reload_in_isolated_local_store(tmp_path):
    db_path = str(tmp_path / "tool-workspace.sqlite")
    state = {
        "shoir_T021_result": {
            "signature": "fixture-signature",
            "source": "USER_ENTERED_UNVERIFIED",
            "executed_at": "2026-10-24T10:00:00+00:00",
            "result": {
                "status": "CALCULATED",
                "metrics": {"mean_observed_time": 10.0, "standard_time": 12.65},
                "observations": pd.DataFrame({"Observation": [10.0, 12.0, 8.0]}),
            },
        }
    }

    result = persist_tool_run_record(
        "disposable-engineering-user",
        state,
        "shoir_T021_result",
        save_workspace=lambda username, session: save_user_workspace(
            username, session, db_path=db_path
        ),
        managed_backend_configured=lambda: False,
    )

    assert result["saved"] is True
    assert result["status"] == "LOCAL_SQLITE_SAVED_MAY_BE_EPHEMERAL"
    assert state["shoir_T021_result"]["persistence_status"] == result["status"]

    restored = {}
    assert load_user_workspace("disposable-engineering-user", restored, db_path=db_path)
    saved_record = restored["shoir_T021_result"]
    assert saved_record["signature"] == "fixture-signature"
    assert saved_record["result"]["metrics"]["standard_time"] == 12.65
    pd.testing.assert_frame_equal(
        saved_record["result"]["observations"],
        pd.DataFrame({"Observation": [10.0, 12.0, 8.0]}),
    )

    # The same local store is username-keyed; another account cannot hydrate
    # this user's result by requesting a different username.
    other_user = {}
    assert not load_user_workspace("unrelated-user", other_user, db_path=db_path)
    assert "shoir_T021_result" not in other_user


def test_failed_workspace_write_keeps_result_in_session_and_never_claims_saved():
    state = {"shoir_T026_result": {
        "signature": "oee-fixture",
        "result": {"status": "CALCULATED", "metrics": {"oee_pct": 81.67}},
    }}
    result = persist_tool_run_record(
        "disposable-engineering-user",
        state,
        "shoir_T026_result",
        save_workspace=lambda username, session: False,
        managed_backend_configured=lambda: True,
    )

    assert result["saved"] is False
    assert result["status"] == "SESSION_ONLY_SAVE_FAILED"
    assert state["shoir_T026_result"]["result"]["metrics"]["oee_pct"] == 81.67
    assert state["shoir_T026_result"]["persistence_status"] == "SESSION_ONLY_SAVE_FAILED"


def test_guest_or_missing_user_cannot_persist_result():
    state = {"shoir_T021_result": {"result": {"status": "CALCULATED"}}}
    result = persist_tool_run_record(
        "Guest Visitor",
        state,
        "shoir_T021_result",
        save_workspace=lambda username, session: (_ for _ in ()).throw(AssertionError("must not save")),
        managed_backend_configured=lambda: True,
    )
    assert result["saved"] is False
    assert result["status"] == "SESSION_ONLY_SAVE_FAILED"
