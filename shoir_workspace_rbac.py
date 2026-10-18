"""Workspace membership authorization and persistence for the industrial platform.

Membership lists are treated as security-sensitive records, not as ordinary
editable UI state. All reads require active membership; membership changes
require a workspace Owner or Admin and preserve the existing Owner identity.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

DEFAULT_DB_PATH = "enterprise_full_workspace.db"
WORKSPACE_ROLES = ("Owner", "Admin", "Manager", "Planner", "Engineer", "Viewer")
_OWNER_ROLES = {"owner"}
_EDITOR_ROLES = {"owner", "admin"}
_COLUMNS = ["Username", "Role", "Updated At"]


def _authenticated_actor(username: str) -> tuple[str, str]:
    """Resolve the actor from Streamlit's active identity, never from form input."""
    import streamlit as st

    state = st.session_state
    session_username = str(state.get("current_user") or "").strip()
    account_role = str(state.get("user_role") or "").strip()
    if not bool(state.get("authenticated")):
        raise PermissionError("Sign in before accessing workspace membership.")
    if not session_username:
        raise PermissionError("The active session has no signed-in username.")
    if not str(username or "").strip() or session_username.casefold() != str(username).strip().casefold():
        raise PermissionError("The requested identity does not match the signed-in account.")
    if not account_role:
        raise PermissionError("The active account role is missing; workspace access is denied.")
    return session_username, account_role


def ensure_workspace_members_schema(db_path: str = DEFAULT_DB_PATH) -> None:
    """Create the compatible local membership table if it is not present."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=15) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS workspace_members(
                workspace TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(workspace, username)
            )"""
        )
        conn.commit()


def _workspace_name(workspace: str) -> str:
    value = str(workspace or "").strip()
    if not value:
        raise ValueError("Workspace name is required.")
    if len(value) > 160:
        raise ValueError("Workspace name must be 160 characters or fewer.")
    if any(ord(ch) < 32 for ch in value):
        raise ValueError("Workspace name contains unsupported control characters.")
    return value


def _frame(rows: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Username": str(row.get("username", "")),
                "Role": str(row.get("role", "")),
                "Updated At": str(row.get("updated_at", "")),
            }
            for row in rows
        ],
        columns=_COLUMNS,
    )


def _read_members(conn: sqlite3.Connection, workspace: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """SELECT workspace, username, role, updated_at
           FROM workspace_members
           WHERE lower(workspace)=lower(?)
           ORDER BY username COLLATE NOCASE""",
        (workspace,),
    ).fetchall()
    normalized = [
        {"workspace": str(row[0]), "username": str(row[1]), "role": str(row[2]), "updated_at": str(row[3])}
        for row in rows
    ]
    workspace_names = {row["workspace"] for row in normalized}
    if len(workspace_names) > 1:
        raise PermissionError(
            "Workspace names differing only by case collide in legacy membership data; access is blocked pending administrative cleanup."
        )
    folded = [row["username"].strip().casefold() for row in normalized]
    if len(folded) != len(set(folded)):
        raise PermissionError(
            "This workspace contains case-insensitive duplicate usernames; membership access is blocked pending administrative cleanup."
        )
    allowed_roles = {role.casefold() for role in WORKSPACE_ROLES}
    if any(row["role"].strip().casefold() not in allowed_roles for row in normalized):
        raise PermissionError(
            "This workspace contains an unsupported saved role; membership access is blocked pending administrative cleanup."
        )
    return normalized


def list_workspace_members(
    workspace: str,
    username: str,
    db_path: str = DEFAULT_DB_PATH,
    *,
    allow_draft: bool = True,
) -> pd.DataFrame:
    """List members only to current workspace members.

    For a not-yet-created workspace, return an in-memory draft showing the
    signed-in creator as Owner. This does not write any records to the database.
    """
    actor, _account_role = _authenticated_actor(username)
    requested_workspace = _workspace_name(workspace)
    ensure_workspace_members_schema(db_path)
    with sqlite3.connect(db_path, timeout=15) as conn:
        rows = _read_members(conn, requested_workspace)
    if not rows:
        if not allow_draft:
            raise LookupError("Workspace does not exist yet; create it from Team Workspaces & RBAC first.")
        return pd.DataFrame(
            [{"Username": actor, "Role": "Owner", "Updated At": ""}],
            columns=_COLUMNS,
        )
    if not any(row["username"].casefold() == actor.casefold() for row in rows):
        raise PermissionError("You are not a member of this workspace.")
    return _frame(rows)


def _normalize_members(members: pd.DataFrame | Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    if isinstance(members, pd.DataFrame):
        raw_rows = members.to_dict("records")
    elif isinstance(members, Sequence) and not isinstance(members, (str, bytes, bytearray)):
        raw_rows = list(members)
    else:
        raise ValueError("Workspace members must be supplied as a table of usernames and roles.")
    if len(raw_rows) > 200:
        raise ValueError("A workspace may contain at most 200 member rows in this editor.")
    allowed = {role.casefold(): role for role in WORKSPACE_ROLES}
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for i, row in enumerate(raw_rows, 1):
        if not isinstance(row, Mapping):
            raise ValueError(f"Member row {i} is not a record.")
        member = str(row.get("Username", row.get("username", "")) or "").strip()
        role_raw = str(row.get("Role", row.get("role", "")) or "").strip()
        if not member:
            raise ValueError(f"Member row {i} requires a username.")
        if len(member) > 160 or any(ord(ch) < 32 for ch in member):
            raise ValueError(f"Member row {i} has an invalid username.")
        role = allowed.get(role_raw.casefold())
        if role is None:
            raise ValueError(
                f"Member row {i} has unsupported role {role_raw!r}. "
                f"Choose one of: {', '.join(WORKSPACE_ROLES)}."
            )
        key = member.casefold()
        if key in seen:
            raise ValueError(f"Duplicate member username {member!r}.")
        seen.add(key)
        normalized.append({"username": member, "role": role})
    if not normalized:
        raise ValueError("At least one workspace member is required.")
    return normalized


def save_workspace_members(
    workspace: str,
    username: str,
    members: pd.DataFrame | Sequence[Mapping[str, Any]],
    db_path: str = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    """Atomically save membership after server-side identity and role checks."""
    actor, _account_role = _authenticated_actor(username)
    requested_workspace = _workspace_name(workspace)
    proposed = _normalize_members(members)
    proposed_by_user = {row["username"].casefold(): row for row in proposed}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ensure_workspace_members_schema(db_path)

    with sqlite3.connect(db_path, timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = _read_members(conn, requested_workspace)
        if not existing:
            # Workspace creation is self-service; the creator becomes its Owner
            # regardless of the role text supplied by the browser.
            if actor.casefold() in proposed_by_user:
                proposed_by_user[actor.casefold()]["role"] = "Owner"
            else:
                proposed.append({"username": actor, "role": "Owner"})
                proposed_by_user[actor.casefold()] = proposed[-1]
            canonical_workspace = requested_workspace
        else:
            canonical_workspace = existing[0]["workspace"]
            active_membership = next(
                (row for row in existing if row["username"].casefold() == actor.casefold()),
                None,
            )
            if active_membership is None:
                raise PermissionError("You are not a member of this workspace.")
            actor_role = active_membership["role"].casefold()
            if actor_role not in _EDITOR_ROLES:
                raise PermissionError("Only a workspace Owner or Admin may change membership.")
            existing_owners = {
                row["username"].casefold()
                for row in existing
                if row["role"].casefold() in _OWNER_ROLES
            }
            if not existing_owners:
                raise PermissionError("Workspace has no valid Owner; membership edits are blocked.")
            for owner_name in existing_owners:
                proposed_owner = proposed_by_user.get(owner_name)
                if proposed_owner is None or proposed_owner["role"].casefold() != "owner":
                    raise PermissionError("Existing workspace Owner records cannot be removed or demoted here.")
            if actor_role == "admin":
                old_roles = {row["username"].casefold(): row["role"].casefold() for row in existing}
                if any(
                    row["role"].casefold() == "owner"
                    and old_roles.get(row["username"].casefold()) != "owner"
                    for row in proposed
                ):
                    raise PermissionError("Workspace Admins cannot assign the Owner role.")
                if any(
                    row["role"].casefold() == "owner"
                    and row["username"].casefold() not in existing_owners
                    for row in proposed
                ):
                    raise PermissionError("Workspace Admins cannot promote members to Owner.")
        # Owners can grant another Owner; Admins can manage non-owner assignments
        # but cannot create a new Owner. Preserve a non-removable Owner in all cases.
        if not any(row["role"].casefold() == "owner" for row in proposed):
            raise PermissionError("A workspace must retain at least one Owner.")

        conn.execute("DELETE FROM workspace_members WHERE workspace=?", (canonical_workspace,))
        conn.executemany(
            "INSERT INTO workspace_members(workspace,username,role,updated_at) VALUES(?,?,?,?)",
            [
                (canonical_workspace, row["username"], row["role"], now)
                for row in proposed
            ],
        )
        conn.commit()
        saved = _read_members(conn, canonical_workspace)
    return _frame(saved)
