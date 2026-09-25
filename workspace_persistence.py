"""Persistent per-user Shoir-IE workspace state.

The Streamlit session is ephemeral. This module snapshots the user's
workspace state into SQLite so a later login restores the same dashboard
inputs, tables, selections, research state, and Copilot conversation.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from io import StringIO
from typing import Any, MutableMapping

import numpy as np
import pandas as pd

from durable_account_store import durable_backend_configured, save_remote_workspace, load_remote_workspace

_STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workspace_states (
    username TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

# Never persist authentication, passwords, payment uploads, or one-request
# UI plumbing. Workspace/module state is persisted normally.
_EXACT_EXCLUDE = {
    "authenticated",
    "current_user",
    "user_role",
    "user_tier",
    "user_email",
    "signin_username_input",
    "signin_password_input",
    "reg_name",
    "reg_email",
    "reg_pass",
    "reg_ticket",
    "reg_chk",
    "reg_confirm_delivery",
    "payment_screenshot_upload",
    "show_qr",
    "signup_otp_sent",
    "trial_otp_sent",
}

_PREFIX_EXCLUDE = (
    "signin_",
    "reg_",
    "payment_",
    "uploaded_",
    "_workspace_",
    # Streamlit action widgets are event controls, not durable workspace values.
    "upgrade_clean_",
    "upgrade_reset_",
    "upgrade_uploader_",
    "sx_save_",
    "sx_open_",
    "sx_job_",
    "sx_decision_",
    "sx_copilot_",
    "sx_export_",
    "sx_dl_",
)

_ACTION_KEYS = {
    "btn_sign_action",
    "btn_confirm_pay",
    "btn_send_request",
    "sidebar_edit_acc",
    "run_milp_solver_btn_tab1",
    "generate_pdf_summary_btn",
    "run_meio_opt_btn",
    "btn_run_slotting_opt",
    "btn_render_gantt",
    "update_status_btn",
    "btn_add_truck",
    "btn_remove_truck",
    "btn_add_landmark",
    "btn_remove_landmark",
    "run_monte_carlo_btn",
    "payment_screenshot_upload",
}

def _excluded(key: str) -> bool:
    lowered = str(key).lower()
    return (
        key in _EXACT_EXCLUDE
        or key in _ACTION_KEYS
        or any(key.startswith(p) for p in _PREFIX_EXCLUDE)
        or lowered.startswith(("download_", "upload_"))
        or lowered.endswith(("_button", "_btn", "_submit"))
    )

def _pack(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return None if np.isnan(value) else value
    if isinstance(value, np.generic):
        return _pack(value.item())
    if isinstance(value, pd.DataFrame):
        return {
            "__type__": "dataframe",
            "value": value.to_json(orient="split", date_format="iso"),
        }
    if isinstance(value, pd.Series):
        return {
            "__type__": "series",
            "value": value.to_json(date_format="iso"),
        }
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, dict):
        return {
            "__type__": "dict",
            "value": {str(k): _pack(v) for k, v in value.items()},
        }
    if isinstance(value, list):
        return {"__type__": "list", "value": [_pack(v) for v in value]}
    if isinstance(value, tuple):
        return {"__type__": "tuple", "value": [_pack(v) for v in value]}
    if isinstance(value, set):
        return {"__type__": "set", "value": [_pack(v) for v in value]}
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError, OverflowError):
        return None

def _unpack(value: Any) -> Any:
    if not isinstance(value, dict) or "__type__" not in value:
        return value
    kind = value["__type__"]
    payload = value.get("value")
    if kind == "dataframe":
        return pd.read_json(StringIO(payload), orient="split")
    if kind == "series":
        return pd.read_json(StringIO(payload), typ="series")
    if kind == "datetime":
        try:
            return _dt.datetime.fromisoformat(payload)
        except ValueError:
            return payload
    if kind == "dict":
        return {k: _unpack(v) for k, v in payload.items()}
    if kind == "list":
        return [_unpack(v) for v in payload]
    if kind == "tuple":
        return tuple(_unpack(v) for v in payload)
    if kind == "set":
        return set(_unpack(v) for v in payload)
    return payload

def ensure_workspace_state_db(db_path: str = "enterprise_full_workspace.db") -> None:
    with sqlite3.connect(db_path, timeout=15) as conn:
        conn.execute(_STATE_TABLE_SQL)
        conn.commit()

def _snapshot(session_state: MutableMapping[str, Any]) -> dict[str, Any]:
    result = {}
    for key, value in session_state.items():
        key = str(key)
        if _excluded(key):
            continue
        packed = _pack(value)
        try:
            json.dumps(packed)
            result[key] = packed
        except (TypeError, ValueError, OverflowError):
            continue
    return result

def save_user_workspace(
    username: str,
    session_state: MutableMapping[str, Any],
    db_path: str = "enterprise_full_workspace.db",
) -> bool:
    if not username or username == "Guest Visitor":
        return False
    try:
        payload = json.dumps(_snapshot(session_state), ensure_ascii=False, separators=(",", ":"))
        # A custom db_path is used by local/regression tests and intentionally
        # bypasses the remote backend. The deployed application uses the default
        # enterprise_full_workspace.db path and therefore uses Supabase.
        if durable_backend_configured() and db_path == "enterprise_full_workspace.db":
            return save_remote_workspace(username, payload)

        # Local development fallback only. A deployed Streamlit instance should
        # configure a managed database because local files are ephemeral.
        ensure_workspace_state_db(db_path)
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        with sqlite3.connect(db_path, timeout=15) as conn:
            conn.execute(
                """
                INSERT INTO workspace_states (username, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    state_json = excluded.state_json,
                    updated_at = excluded.updated_at
                """,
                (username.strip().lower(), payload, now),
            )
            conn.commit()
        return True
    except Exception:
        # Workspace persistence should never crash the engineering application.
        return False

def load_user_workspace(
    username: str,
    session_state: MutableMapping[str, Any],
    db_path: str = "enterprise_full_workspace.db",
) -> bool:
    if not username or username == "Guest Visitor":
        return False
    try:
        remote_payload = (
            load_remote_workspace(username)
            if durable_backend_configured() and db_path == "enterprise_full_workspace.db"
            else None
        )
        if remote_payload:
            payload = json.loads(remote_payload)
        else:
            ensure_workspace_state_db(db_path)
            with sqlite3.connect(db_path, timeout=15) as conn:
                row = conn.execute(
                    "SELECT state_json FROM workspace_states WHERE username = ?",
                    (username.strip().lower(),),
                ).fetchone()
            if not row or not row[0]:
                return False
            payload = json.loads(row[0])
        for key, value in payload.items():
            if _excluded(str(key)):
                continue
            # Load persisted workspace values before module widgets are rendered.
            # This intentionally replaces initial defaults on first login.
            session_state[key] = _unpack(value)
        return True
    except Exception:
        return False
