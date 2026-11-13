from pathlib import Path

import pandas as pd
import pytest

import workspace_persistence as workspace_module

from workspace_persistence import (
    _excluded,
    _workspace_change_signature,
    export_user_workspace_backup,
    load_user_workspace,
    restore_user_workspace_backup,
    save_user_workspace,
    verify_user_workspace_backup,
)


def test_organization_selection_is_not_saved_in_personal_workspace_state():
    assert _excluded("shoir_active_organization_id")
    assert _excluded("shoir_active_organization_workspace_id")
    for widget_key in (
        "team_org_create_name",
        "team_workspace_create_name",
        "team_workspace_open_id",
        "team_member_role_target",
        "team_invitation_target_username",
        "team_owner_transfer_target",
        "team_accept_token",
        "team_invite_email",
    ):
        assert _excluded(widget_key)


def test_workspace_round_trip_and_secret_exclusion(tmp_path: Path):
    db = str(tmp_path / "workspace.db")
    source = {
        "authenticated": True,
        "current_user": "Alice",
        "user_tier": "Professional Tier",
        "selected_nav": "Dashboard",
        "enterprise_module_selector": "Inventory · EOQ",
        "demand": 1250,
        "copilot_messages": [{"role": "user", "content": "run my scenario"}],
        "df": pd.DataFrame({"SKU": ["A", "B"], "Demand": [10, 20]}),
        "signin_password_input": "must-not-persist",
    }

    assert save_user_workspace("Alice", source, db)

    restored = {
        "authenticated": True,
        "current_user": "Alice",
        "demand": 999,
    }
    assert load_user_workspace("Alice", restored, db)

    assert restored["current_user"] == "Alice"
    assert restored["demand"] == 1250
    assert restored["selected_nav"] == "Dashboard"
    assert restored["enterprise_module_selector"] == "Inventory · EOQ"
    assert restored["copilot_messages"][0]["content"] == "run my scenario"
    pd.testing.assert_frame_equal(restored["df"], source["df"])
    assert "signin_password_input" not in restored


def test_workspace_isolated_per_user(tmp_path: Path):
    db = str(tmp_path / "workspace.db")
    assert save_user_workspace("Alice", {"selection": "A"}, db)
    assert save_user_workspace("Bob", {"selection": "B"}, db)

    alice = {}
    bob = {}
    assert load_user_workspace("Alice", alice, db)
    assert load_user_workspace("Bob", bob, db)
    assert alice["selection"] == "A"
    assert bob["selection"] == "B"


def test_workspace_does_not_restore_streamlit_action_widget_keys(tmp_path: Path):
    db = str(tmp_path / "workspace.db")
    source = {
        "sidebar_edit_acc": True,
        "btn_confirm_pay": True,
        "shoir_shell_new_study": True,
        "shoir_shell_present": True,
        "shoir_shell_trust": True,
        "shoir_shell_runs": True,
        "shoir_shell_copilot": True,
        "shoir_shell_os": True,
        "shoir_shell_excellence": True,
        "shoir_shell_edit_account": True,
        "shoir_shell_logout": True,
        "shoir_create_study": True,
        "shoir_presentation_return": True,
        "shoir_global_module_0": True,
        "shoir_home_open_workbook": True,
        "shoir_home_open_excel": True,
        "shoir_home_open_core": True,
        "shoir_data_hub_upload": "transient",
        "shoir_data_hub_sheet": "Sheet1",
        "enterprise_module_selector": "Inventory · EOQ",
        "research_title": "My Study",
        "research_question": "A durable question that should be restored.",
    }
    assert save_user_workspace("Alice", source, db)

    restored = {}
    assert load_user_workspace("Alice", restored, db)

    assert "sidebar_edit_acc" not in restored
    assert "btn_confirm_pay" not in restored
    for key in (
        "shoir_shell_new_study",
        "shoir_shell_present",
        "shoir_shell_trust",
        "shoir_shell_runs",
        "shoir_shell_copilot",
        "shoir_shell_os",
        "shoir_shell_excellence",
        "shoir_shell_edit_account",
        "shoir_shell_logout",
        "shoir_create_study",
        "shoir_presentation_return",
    ):
        assert key not in restored
    assert "global_command_open_inventory" not in restored
    assert "shoir_global_module_0" not in restored
    for key in ("shoir_home_open_workbook", "shoir_home_open_excel", "shoir_home_open_core", "shoir_data_hub_upload", "shoir_data_hub_sheet"):
        assert key not in restored
    assert restored["enterprise_module_selector"] == "Inventory · EOQ"
    assert restored["research_title"] == "My Study"


def test_workspace_change_signature_is_stable_for_unchanged_large_frame():
    df = pd.DataFrame({"value": range(100_000)})
    state = {"current_user": "Alice", "large": df}
    first = _workspace_change_signature(state)
    second = _workspace_change_signature(state)
    assert first == second
    state["large"] = df.copy()
    third = _workspace_change_signature(state)
    assert third != first


def test_workspace_backup_round_trip_excludes_secrets_and_is_owner_scoped():
    source = {
        "authenticated": True,
        "current_user": "Alice",
        "remote_session_token": "do-not-export",
        "renewal_session_token": "do-not-export-either",
        "access_token": "secret",
        "selected_nav": "Dashboard",
        "demand": 42,
        "df": pd.DataFrame({"SKU": ["A", "B"], "Demand": [10, 20]}),
    }
    exported = export_user_workspace_backup("Alice", source)
    assert exported["payload_key_count"] >= 3
    verified = verify_user_workspace_backup(exported["backup_bytes"], "Alice")
    assert verified["owner_username_lc"] == "alice"
    assert verified["sha256"] == exported["sha256"]

    target = {"authenticated": True, "current_user": "Alice", "remote_session_token": "fresh-session"}
    restored = restore_user_workspace_backup(exported["backup_bytes"], "Alice", target)
    assert restored["status"] == "WORKSPACE_BACKUP_RESTORED_IN_SESSION"
    assert target["authenticated"] is True
    assert target["current_user"] == "Alice"
    assert target["remote_session_token"] == "fresh-session"
    assert target["selected_nav"] == "Dashboard"
    assert target["demand"] == 42
    pd.testing.assert_frame_equal(target["df"], source["df"])
    assert "remote_session_token" not in verified["payload"]
    assert "renewal_session_token" not in verified["payload"]
    assert "access_token" not in verified["payload"]

    with pytest.raises(PermissionError, match="different account"):
        verify_user_workspace_backup(exported["backup_bytes"], "Bob")


def test_workspace_backup_detects_tampering_and_unsupported_payloads():
    import json

    exported = export_user_workspace_backup("Alice", {"selected_nav": "Dashboard"})
    envelope = json.loads(exported["backup_bytes"].decode("utf-8"))
    envelope["payload"]["selected_nav"] = "Admin"
    tampered = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    with pytest.raises(ValueError, match="checksum is invalid"):
        verify_user_workspace_backup(tampered, "Alice")

    with pytest.raises(ValueError, match="not valid UTF-8 JSON"):
        verify_user_workspace_backup(b"not-json", "Alice")
    with pytest.raises(PermissionError, match="Sign in"):
        export_user_workspace_backup("Guest Visitor", {})




def test_personal_to_team_to_other_team_switch_clears_prior_workspace_values(monkeypatch, tmp_path: Path):
    db = str(tmp_path / "personal-workspace.db")
    personal = {"selection": "personal", "personal_only": "keep only in personal scope"}
    assert save_user_workspace("Alice", personal, db)

    remote_payloads = iter([
        '{"selection":"team-one","team_one_only":"confidential team one"}',
        '{"selection":"team-two","team_two_only":"confidential team two"}',
    ])
    monkeypatch.setattr(workspace_module, "durable_backend_configured", lambda: True)
    monkeypatch.setattr(
        workspace_module,
        "load_remote_workspace",
        lambda username: next(remote_payloads),
    )

    session = {"authenticated": True, "current_user": "Alice"}
    assert load_user_workspace("Alice", session, db)
    assert session["selection"] == "personal"
    session["shoir_active_organization_workspace"] = {
        "organization_id": "org-one",
        "organization_workspace_id": "workspace-one",
    }
    assert load_user_workspace("Alice", session)
    assert session["selection"] == "team-one"
    assert "personal_only" not in session
    assert "team_one_only" in session

    session["shoir_active_organization_workspace"] = {
        "organization_id": "org-two",
        "organization_workspace_id": "workspace-two",
    }
    assert load_user_workspace("Alice", session)
    assert session["selection"] == "team-two"
    assert "team_one_only" not in session
    assert "personal_only" not in session
    assert "team_two_only" in session
    assert session["_workspace_loaded_scope"] == ("org-two", "workspace-two")


def test_shared_workspace_never_falls_back_to_personal_sqlite_when_managed_backend_is_missing(tmp_path: Path, monkeypatch):
    db = str(tmp_path / "personal-workspace.db")
    assert save_user_workspace("Alice", {"selection": "personal"}, db)
    monkeypatch.setattr(workspace_module, "durable_backend_configured", lambda: False)

    session = {
        "authenticated": True,
        "current_user": "Alice",
        "shoir_active_organization_workspace": {
            "organization_id": "org-one",
            "organization_workspace_id": "workspace-one",
        },
    }
    assert load_user_workspace("Alice", session) is False
    assert "selection" not in session
    assert "shared organization workspaces require" in session["_workspace_load_error"].casefold()

    # The saver must check the shared-workspace backend requirement before
    # the unchanged-signature fast path, and may not write to personal SQLite.
    session["_shoir_persist_change_signature"] = workspace_module._workspace_change_signature(session)
    assert save_user_workspace("Alice", session) is False
    assert "shared organization workspaces require" in session["_workspace_save_error"].casefold()


def test_clear_loaded_workspace_state_removes_only_hydrated_data():
    session = {
        "dataset": {"name": "shared"},
        "selected_nav": "Workbench",
        "unsaved_shared_new_key": {"new": "uncommitted team-only value"},
        "remote_session_token": "live-session",
        "authenticated": True,
        "current_user": "Alice",
        "shoir_active_organization_workspace": {
            "organization_id": "org-one",
            "organization_workspace_id": "workspace-one",
        },
        "_workspace_loaded_keys": ["dataset", "selected_nav"],
        "_workspace_org_revision": 4,
        "_shoir_persist_change_signature": "previous",
    }

    workspace_module.clear_loaded_workspace_state(session)

    assert "dataset" not in session
    assert "selected_nav" not in session
    assert "unsaved_shared_new_key" not in session
    assert session["remote_session_token"] == "live-session"
    assert session["authenticated"] is True
    assert session["current_user"] == "Alice"
    assert session["shoir_active_organization_workspace"]["organization_id"] == "org-one"
    assert session["_workspace_loaded_keys"] == []
    assert "_workspace_org_revision" not in session
    assert "_shoir_persist_change_signature" not in session
    assert session["_workspace_loaded_for_user"] is None



def test_shared_workspace_save_does_not_write_personal_domain_manifest(monkeypatch):
    session = {
        "selection": "shared-workspace-value",
        "shoir_active_organization_workspace": {
            "organization_id": "org-one",
            "organization_workspace_id": "workspace-one",
        },
        "_workspace_org_revision": 2,
    }
    manifests = []
    monkeypatch.setattr(workspace_module, "durable_backend_configured", lambda: True)
    monkeypatch.setattr(workspace_module, "save_remote_workspace", lambda username, payload: True)
    monkeypatch.setattr(
        workspace_module,
        "_persist_domain_manifest",
        lambda *args: manifests.append(args),
    )

    assert save_user_workspace("Alice", session) is True
    assert manifests == []
    assert session["_workspace_loaded_keys"] == ["selection"]


def test_shared_workspace_revision_conflict_pauses_retries_until_explicit_reload(monkeypatch):
    session = {
        "selection": "unsaved edit",
        "shoir_active_organization_workspace": {
            "organization_id": "org-one",
            "organization_workspace_id": "workspace-one",
        },
        "_workspace_org_revision": 3,
    }
    monkeypatch.setattr(workspace_module, "durable_backend_configured", lambda: True)
    calls = []

    def reject_stale_revision(username, payload):
        calls.append(payload)
        raise RuntimeError("SHARED_WORKSPACE_REVISION_CONFLICT")

    monkeypatch.setattr(workspace_module, "save_remote_workspace", reject_stale_revision)

    assert save_user_workspace("Alice", session) is False
    assert "newer shared-workspace revision" in session["_workspace_save_error"].casefold()
    assert session["_workspace_save_conflict"] is True
    assert "_shoir_persist_change_signature" not in session

    # Streamlit reruns autosave repeatedly. A known conflict is not retried
    # until the user explicitly reloads the server revision.
    assert save_user_workspace("Alice", session) is False
    assert len(calls) == 1

    workspace_module.clear_loaded_workspace_state(session)
    assert "_workspace_save_conflict" not in session



def test_malformed_organization_context_is_rejected_before_noop_save_shortcut(monkeypatch):
    session = {
        "selection": "unchanged",
        "shoir_active_organization_workspace": {"organization_id": "org-one"},
    }
    monkeypatch.setattr(workspace_module, "durable_backend_configured", lambda: True)
    calls = []
    monkeypatch.setattr(
        workspace_module,
        "save_remote_workspace",
        lambda *args: calls.append(args) or True,
    )
    session["_shoir_persist_change_signature"] = workspace_module._workspace_change_signature(session)

    assert save_user_workspace("Alice", session) is False
    assert "both organization and workspace ids" in session["_workspace_save_error"].casefold()
    assert calls == []



def test_clear_loaded_workspace_state_does_not_clear_untracked_personal_state():
    session = {
        "current_personal_value": "preserve",
        "remote_session_token": "live-session",
        "_workspace_loaded_keys": [],
        "_workspace_loaded_owner": "alice",
        "_workspace_loaded_scope": None,
    }

    workspace_module.clear_loaded_workspace_state(session)

    assert session["current_personal_value"] == "preserve"
    assert session["remote_session_token"] == "live-session"


def test_digital_thread_rename_history_persists_but_rename_widget_state_does_not(tmp_path: Path):
    db = str(tmp_path / "workspace.db")
    source = {
        "authenticated": True,
        "current_user": "Alice",
        "global_thread_rename_target": "AST-1001",
        "global_thread_rename_name_AST-1001": "Main Press",
        "global_thread_rename_save": True,
        "shoir_digital_thread_rename_history": [{
            "event_id": "DTR-TEST-1",
            "node_id": "AST-1001",
            "previous_name": "Press 1001",
            "new_name": "Main Press",
        }],
    }

    assert _excluded("global_thread_rename_target")
    assert _excluded("global_thread_rename_name_AST-1001")
    assert _excluded("global_thread_rename_save")
    assert save_user_workspace("Alice", source, db)

    restored = {}
    assert load_user_workspace("Alice", restored, db)
    assert "global_thread_rename_target" not in restored
    assert "global_thread_rename_name_AST-1001" not in restored
    assert "global_thread_rename_save" not in restored
    assert restored["shoir_digital_thread_rename_history"][0]["event_id"] == "DTR-TEST-1"
