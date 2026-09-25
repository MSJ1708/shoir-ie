from pathlib import Path

import pandas as pd

from workspace_persistence import load_user_workspace, save_user_workspace


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
        "enterprise_module_selector": "Inventory · EOQ",
        "research_title": "My Study",
        "research_question": "A durable question that should be restored.",
    }
    assert save_user_workspace("Alice", source, db)

    restored = {}
    assert load_user_workspace("Alice", restored, db)

    assert "sidebar_edit_acc" not in restored
    assert "btn_confirm_pay" not in restored
    assert restored["enterprise_module_selector"] == "Inventory · EOQ"
    assert restored["research_title"] == "My Study"
