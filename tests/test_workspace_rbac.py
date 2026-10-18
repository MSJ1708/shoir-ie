import sqlite3
import pandas as pd
import pytest
import streamlit as st

from shoir_workspace_rbac import (
    list_workspace_members,
    save_workspace_members,
)


def _session(monkeypatch, username: str, role: str = "User", *, authenticated: bool = True):
    state = {
        "current_user": username,
        "user_role": role,
        "authenticated": authenticated,
    }
    monkeypatch.setattr(st, "session_state", state)
    return state


def _members(*rows):
    return pd.DataFrame(rows, columns=["Username", "Role", "Updated At"])


def test_workspace_membership_is_server_authorized_and_private(tmp_path, monkeypatch):
    state = _session(monkeypatch, "alice", role="User")
    db = str(tmp_path / "members.db")

    # Listing a not-yet-created workspace is a draft only; first save always
    # grants the signed-in creator ownership regardless of browser-supplied role.
    draft = list_workspace_members("Plant-A", "alice", db)
    assert draft.to_dict("records")[0]["Username"] == "alice"
    save_workspace_members(
        "Plant-A",
        "alice",
        _members(
            {"Username": "alice", "Role": "Owner", "Updated At": ""},
            {"Username": "bob", "Role": "Viewer", "Updated At": ""},
        ),
        db,
    )

    state["current_user"] = "mallory"
    with pytest.raises(PermissionError, match="not a member"):
        list_workspace_members("Plant-A", "mallory", db)
    with pytest.raises(PermissionError, match="not a member"):
        save_workspace_members(
            "Plant-A",
            "mallory",
            _members({"Username": "mallory", "Role": "Owner", "Updated At": ""}),
            db,
        )

    # A legitimate member can read membership, but Viewer cannot change it.
    state["current_user"] = "bob"
    visible = list_workspace_members("plant-a", "bob", db)
    assert set(visible["Username"]) == {"alice", "bob"}
    with pytest.raises(PermissionError, match="Owner or Admin"):
        save_workspace_members(
            "Plant-A",
            "bob",
            _members(
                {"Username": "alice", "Role": "Owner", "Updated At": ""},
                {"Username": "bob", "Role": "Planner", "Updated At": ""},
            ),
            db,
        )

    # Failed attempts do not partially update membership.
    state["current_user"] = "alice"
    after = list_workspace_members("Plant-A", "alice", db)
    assert dict(zip(after["Username"], after["Role"])) == {"alice": "Owner", "bob": "Viewer"}


def test_workspace_owner_can_edit_members_but_admin_cannot_promote_owner(tmp_path, monkeypatch):
    state = _session(monkeypatch, "alice")
    db = str(tmp_path / "owner-admin.db")
    save_workspace_members(
        "Plant-B",
        "alice",
        _members(
            {"Username": "alice", "Role": "Owner", "Updated At": ""},
            {"Username": "bob", "Role": "Admin", "Updated At": ""},
        ),
        db,
    )

    state["current_user"] = "bob"
    with pytest.raises(PermissionError, match="cannot assign the Owner"):
        save_workspace_members(
            "Plant-B",
            "bob",
            _members(
                {"Username": "alice", "Role": "Owner", "Updated At": ""},
                {"Username": "bob", "Role": "Admin", "Updated At": ""},
                {"Username": "carol", "Role": "Owner", "Updated At": ""},
            ),
            db,
        )

    # Owner may intentionally promote a colleague after reviewing membership.
    state["current_user"] = "alice"
    saved = save_workspace_members(
        "Plant-B",
        "alice",
        _members(
            {"Username": "alice", "Role": "Owner", "Updated At": ""},
            {"Username": "bob", "Role": "Admin", "Updated At": ""},
            {"Username": "carol", "Role": "Owner", "Updated At": ""},
        ),
        db,
    )
    assert set(saved.loc[saved["Role"].eq("Owner"), "Username"]) == {"alice", "carol"}


def test_workspace_member_save_rejects_invalid_or_duplicate_rows_atomically(tmp_path, monkeypatch):
    _session(monkeypatch, "alice")
    db = str(tmp_path / "validation.db")
    save_workspace_members(
        "Plant-C",
        "alice",
        _members({"Username": "alice", "Role": "Owner", "Updated At": ""}),
        db,
    )
    with pytest.raises(ValueError, match="Duplicate member username"):
        save_workspace_members(
            "Plant-C",
            "alice",
            _members(
                {"Username": "alice", "Role": "Owner", "Updated At": ""},
                {"Username": "ALICE", "Role": "Viewer", "Updated At": ""},
            ),
            db,
        )
    with pytest.raises(ValueError, match="unsupported role"):
        save_workspace_members(
            "Plant-C",
            "alice",
            _members(
                {"Username": "alice", "Role": "Owner", "Updated At": ""},
                {"Username": "bob", "Role": "SuperAdmin", "Updated At": ""},
            ),
            db,
        )
    assert list_workspace_members("Plant-C", "alice", db)["Username"].tolist() == ["alice"]


def test_workspace_membership_requires_authenticated_matching_identity_and_role(tmp_path, monkeypatch):
    db = str(tmp_path / "authentication.db")
    _session(monkeypatch, "alice", authenticated=False)
    with pytest.raises(PermissionError, match="Sign in"):
        list_workspace_members("Plant-D", "alice", db)

    state = _session(monkeypatch, "alice", role="")
    with pytest.raises(PermissionError, match="account role is missing"):
        list_workspace_members("Plant-D", "alice", db)

    state = _session(monkeypatch, "alice", role="User")
    with pytest.raises(PermissionError, match="does not match"):
        list_workspace_members("Plant-D", "bob", db)

def test_corrupt_legacy_membership_fails_closed(tmp_path, monkeypatch):
    _session(monkeypatch, "alice")
    db = str(tmp_path / "corrupt-members.db")
    # The historical table's primary key is case-sensitive, so old unsafe UI
    # writes could have created duplicate logical identities such as Alice/alice.
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE workspace_members(
                workspace TEXT NOT NULL, username TEXT NOT NULL, role TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY(workspace, username)
            )"""
        )
        conn.executemany(
            "INSERT INTO workspace_members(workspace,username,role,updated_at) VALUES(?,?,?,?)",
            [
                ("Plant-E", "alice", "Owner", "now"),
                ("Plant-E", "Alice", "Viewer", "now"),
            ],
        )
        conn.commit()
    with pytest.raises(PermissionError, match="duplicate usernames"):
        list_workspace_members("Plant-E", "alice", db)

def test_case_colliding_legacy_workspace_names_fail_closed(tmp_path, monkeypatch):
    _session(monkeypatch, "alice")
    db = str(tmp_path / "workspace-name-collision.db")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """CREATE TABLE workspace_members(
                workspace TEXT NOT NULL, username TEXT NOT NULL, role TEXT NOT NULL,
                updated_at TEXT NOT NULL, PRIMARY KEY(workspace, username)
            )"""
        )
        conn.executemany(
            "INSERT INTO workspace_members(workspace,username,role,updated_at) VALUES(?,?,?,?)",
            [
                ("Plant-F", "alice", "Owner", "now"),
                ("plant-f", "bob", "Viewer", "now"),
            ],
        )
        conn.commit()
    with pytest.raises(PermissionError, match="differing only by case"):
        list_workspace_members("Plant-F", "alice", db)

