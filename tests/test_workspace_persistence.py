from pathlib import Path

import pandas as pd

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

