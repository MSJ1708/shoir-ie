from pathlib import Path

import pandas as pd

from workspace_persistence import load_user_workspace, save_user_workspace, _workspace_change_signature


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
