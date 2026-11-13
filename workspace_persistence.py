"""Persistent per-user Shoir-IE workspace state.

The Streamlit session is ephemeral. This module snapshots the user's
workspace state into SQLite so a later login restores the same dashboard
inputs, tables, selections, research state, and Copilot conversation.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import sqlite3
from shoir_sqlite import ClosingSQLiteConnection
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
    "remote_session_token",
    "renewal_session_token",
    "access_token",
    "refresh_token",
    "session_token",
    "api_secret",
    "password",
    "password_hash",
    "_shoir_persist_change_signature",
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
    "token_",
    "secret_",
    "password_",
    "reg_",
    "payment_",
    "uploaded_",
    "_workspace_",
    # Home/data-hub controls are transient Streamlit widgets, not durable values.
    "shoir_home_",
    "shoir_data_hub_",
    # Streamlit action widgets are event controls, not durable workspace values.
    # The unified shell uses a consistent shoir_shell_* namespace for UI
    # controls and transient surface state; none of it belongs in persistence.
    "shoir_shell_",
    # The active organization/workspace selector is request context, not
    # personal workspace data to restore for a later sign-in.
    "shoir_active_organization_",
    "team_org_",
    "team_workspace_",
    "team_member_",
    "team_invitation_",
    "team_owner_",
    "team_accept_",
    "team_invite_",
    "shoir_global_module_",
    "upgrade_clean_",
    "upgrade_reset_",
    "upgrade_uploader_",
    # Never hydrate Streamlit button state; the global command Open button is transient.
    "global_command_open_",
    "global_thread_rename_",
    "sx_save_",
    "sx_open_",
    "sx_job_",
    "sx_decision_",
    "sx_copilot_",
    "sx_export_",
    "sx_dl_",
    # Universal Module Parity widget plumbing is intentionally transient;
    # the canonical parity data/results keys below are persisted instead.
    "module_profile_widget_",
    "module_parity_upload_",
    "module_parity_workbook_",
    "module_parity_editor_",
    "module_parity_sheet_",
    "module_parity_validate_",
    "module_parity_clean_",
    "module_parity_reset_",
    "module_parity_apply_native_",
    "module_parity_result_source_",
    "module_parity_xlsx_",
    "module_parity_csv_",
    "module_parity_zip_",
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
    "shoir_create_study",
    "global_thread_rename_save",
    "shoir_presentation_return",
    # Unified application-shell actions are ephemeral Streamlit button state.
    # Persisting any of these keys would hydrate a button before its widget is
    # instantiated on the next run, which Streamlit rejects.
    "shoir_shell_new_study",
    "shoir_shell_present",
    "shoir_shell_trust",
    "shoir_shell_runs",
    "shoir_shell_copilot",
    "shoir_shell_os",
    "shoir_shell_excellence",
    "shoir_shell_edit_account",
    "shoir_shell_logout",
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
            # pandas JSON round-trips can infer an integer dtype for float columns
            # whose current values happen to be whole numbers. Preserve the schema.
            "dtypes": [str(dtype) for dtype in value.dtypes],
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
        frame = pd.read_json(StringIO(payload), orient="split")
        dtypes = value.get("dtypes")
        if isinstance(dtypes, list) and len(dtypes) == len(frame.columns):
            for column_index, dtype in enumerate(dtypes):
                try:
                    frame.isetitem(
                        column_index,
                        frame.iloc[:, column_index].astype(dtype),
                    )
                except (TypeError, ValueError, OverflowError):
                    # If a value cannot safely fit the original dtype, preserve
                    # the decoded values rather than failing workspace recovery.
                    continue
        return frame
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
    with sqlite3.connect(db_path, timeout=15, factory=ClosingSQLiteConnection) as conn:
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

def _persist_domain_manifest(username: str, session_state: MutableMapping[str, Any], db_path: str) -> None:
    """Persist a compact durable manifest of the user's engineering state."""
    try:
        from shoir_enterprise_layer import record_artifact, canonical_state_manifest
        workspace = str(
            session_state.get("shoir_workspace_name")
            or session_state.get("workspace")
            or session_state.get("active_workspace_name")
            or "default"
        )
        ids = {}
        for key in (
            "active_project_id", "project_id", "sx_project_id", "sx_research_study_id",
            "sx_research_id", "sx_research_protocol_hash", "decision_active_id",
            "copilot_orchestrator_run_id", "sx_copilot_run_id",
        ):
            value = session_state.get(key)
            if value:
                ids[key] = str(value)
        dataframe_keys = [
            str(k) for k, v in session_state.items()
            if isinstance(v, pd.DataFrame) and not str(k).startswith(("password","token","secret"))
        ]
        artifact_catalog = session_state.get("shoir_artifact_catalog", [])
        manifest = {
            "workspace": workspace,
            "owner": username,
            "identifiers": ids,
            "dataframe_keys": dataframe_keys[:200],
            "artifact_count": int(len(artifact_catalog)) if isinstance(artifact_catalog, list) else 0,
            "canonical": canonical_state_manifest(username, workspace),
            "persisted_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "backend": "managed" if (db_path == "enterprise_full_workspace.db" and durable_backend_configured()) else "local",
        }
        record_artifact(username, "workspace_manifest", f"{username}:{workspace}", manifest, workspace)
    except Exception:
        # Manifest persistence is supplementary; native workspace save must remain independent.
        pass


def _dataframe_content_signature(frame: pd.DataFrame) -> str:
    """Hash DataFrame values and schema so in-place cell edits cannot be skipped.

    pandas' vectorized hashing is materially faster than serializing a frame to
    JSON. Object columns containing unhashable cells (lists/dicts) use a JSON
    fallback. The caller still includes object identity to retain the existing
    copy-vs-same-object behavior of the persistence change detector.
    """
    metadata = {
        "shape": tuple(frame.shape),
        "columns": [str(column) for column in frame.columns],
        "dtypes": [str(dtype) for dtype in frame.dtypes],
        "index_names": [str(name) if name is not None else None for name in frame.index.names],
        "index_type": type(frame.index).__name__,
    }
    try:
        value_bytes = pd.util.hash_pandas_object(frame, index=True, categorize=True).to_numpy().tobytes()
    except Exception:
        value_bytes = frame.to_json(
            orient="split",
            date_format="iso",
            double_precision=15,
            default_handler=str,
        ).encode("utf-8", errors="replace")
    digest = hashlib.sha256()
    digest.update(json.dumps(metadata, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    digest.update(b"\0")
    digest.update(value_bytes)
    return digest.hexdigest()


def _nested_value_signature(value: Any) -> str:
    """Hash mutable state collections without truncating long repr() output.

    DataFrames nested inside a dict/list are represented by their schema/value
    digest, not serialized again as full JSON. This keeps registry, Copilot and
    multi-step workspace records safe while avoiding false no-op saves after a
    mutation beyond the first 1,000 characters.
    """
    def normalize(item: Any, depth: int = 0) -> Any:
        if depth > 30:
            return {"__type__": "depth-limit", "class": type(item).__name__}
        if isinstance(item, pd.DataFrame):
            return {"__type__": "dataframe", "digest": _dataframe_content_signature(item)}
        if isinstance(item, pd.Series):
            return {"__type__": "series", "digest": _series_content_signature(item)}
        if isinstance(item, dict):
            return {
                "__type__": "dict",
                "items": [
                    [str(k), normalize(v, depth + 1)]
                    for k, v in sorted(item.items(), key=lambda pair: str(pair[0]))
                ],
            }
        if isinstance(item, (list, tuple)):
            return {
                "__type__": type(item).__name__,
                "items": [normalize(v, depth + 1) for v in item],
            }
        if isinstance(item, set):
            normalized = [normalize(v, depth + 1) for v in item]
            normalized.sort(key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False, default=str))
            return {"__type__": "set", "items": normalized}
        if item is None or isinstance(item, (str, int, float, bool)):
            return item
        if isinstance(item, (pd.Timestamp, _dt.datetime, _dt.date)):
            return {"__type__": type(item).__name__, "value": item.isoformat()}
        return {"__type__": type(item).__name__, "value": str(item)}

    canonical = json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8", errors="replace")).hexdigest()


def _series_content_signature(series: pd.Series) -> str:
    try:
        raw = pd.util.hash_pandas_object(series, index=True, categorize=True).to_numpy().tobytes()
    except Exception:
        raw = series.to_json(date_format="iso", default_handler=str).encode("utf-8", errors="replace")
    metadata = {
        "name": str(series.name),
        "dtype": str(series.dtype),
        "length": len(series),
    }
    digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode("utf-8"))
    digest.update(b"\0")
    digest.update(raw)
    return digest.hexdigest()


def _workspace_change_signature(session_state: MutableMapping[str, Any]) -> str:
    """Stable content signature that detects in-place mutation of mutable state."""
    parts: list[str] = []
    for key, value in session_state.items():
        key = str(key)
        if _excluded(key) or key.startswith("_shoir_persist_"):
            continue
        if isinstance(value, pd.DataFrame):
            parts.append(f"DF|{key}|{id(value)}|{_dataframe_content_signature(value)}")
        elif isinstance(value, pd.Series):
            parts.append(f"SER|{key}|{id(value)}|{_series_content_signature(value)}")
        elif isinstance(value, (dict, list, tuple, set)):
            parts.append(f"C|{key}|{type(value).__name__}|{_nested_value_signature(value)}")
        else:
            try:
                parts.append(f"V|{key}|{type(value).__name__}|{repr(value)[:1000]}")
            except Exception:
                parts.append(f"V|{key}|{type(value).__name__}")
    return hashlib.sha1("\n".join(sorted(parts)).encode("utf-8", errors="replace")).hexdigest()

def clear_loaded_workspace_state(
    session_state: MutableMapping[str, Any],
) -> None:
    """Remove only persisted workspace values currently hydrated into this session."""
    prior_keys = session_state.get("_workspace_loaded_keys", [])
    keys_to_clear = {
        key for key in prior_keys
        if isinstance(key, str) and not _excluded(key)
    } if isinstance(prior_keys, list) else set()
    if isinstance(session_state.get("shoir_active_organization_workspace"), dict):
        # Include values created since the last confirmed autosave. A disconnect
        # or revoked-membership path must not leave new team-only keys behind.
        keys_to_clear.update(_snapshot(session_state).keys())
    for key in keys_to_clear:
        if not _excluded(key):
            session_state.pop(key, None)
    session_state["_workspace_loaded_keys"] = []
    session_state.pop("_shoir_persist_change_signature", None)
    session_state.pop("_workspace_org_revision", None)
    session_state.pop("_workspace_org_updated_at", None)
    session_state.pop("_workspace_save_conflict", None)
    session_state["_workspace_loaded_owner"] = None
    session_state["_workspace_loaded_scope"] = None
    session_state["_workspace_loaded_for_user"] = None


def save_user_workspace(
    username: str,
    session_state: MutableMapping[str, Any],
    db_path: str = "enterprise_full_workspace.db",
) -> bool:
    if not username or username == "Guest Visitor":
        return False
    try:
        raw_context = session_state.get("shoir_active_organization_workspace")
        if raw_context is not None and not isinstance(raw_context, dict):
            raise ValueError("Active organization workspace context is invalid.")
        if raw_context is not None and (
            not str(raw_context.get("organization_id") or "").strip()
            or not str(raw_context.get("organization_workspace_id") or "").strip()
        ):
            raise ValueError("Both organization and workspace IDs are required for shared persistence.")
        # A shared organization workspace must never fall back to a per-user
        # SQLite/PostgreSQL record, even when the change signature is unchanged.
        remote_mode = durable_backend_configured() and db_path == "enterprise_full_workspace.db"
        if raw_context is not None and not remote_mode:
            raise RuntimeError("Shared organization workspaces require the authenticated managed workspace service.")
        if raw_context is not None and session_state.get("_workspace_save_conflict"):
            session_state["_workspace_save_error"] = (
                "A newer shared-workspace revision exists. Reload the workspace before saving."
            )
            return False
        # Most Streamlit interactions rerun the script without changing the
        # durable workspace. Avoid serializing large Excel-backed DataFrames on
        # those no-op reruns (chart filters, tab switches, UI interactions).
        change_signature = _workspace_change_signature(session_state)
        prior_signature = session_state.get("_shoir_persist_change_signature")
        if prior_signature == change_signature:
            return True
        payload = json.dumps(_snapshot(session_state), ensure_ascii=False, separators=(",", ":"))
        # A custom db_path is used by local/regression tests and intentionally
        # bypasses the remote backend. It is never a valid target for shared state.
        if remote_mode:
            # In durable mode, never silently persist to shared/ephemeral SQLite.
            # A failed cloud write must stay a failed cloud write.
            ok = bool(save_remote_workspace(username, payload))
            if ok:
                session_state["_shoir_persist_change_signature"] = change_signature
                session_state["_workspace_loaded_keys"] = list(_snapshot(session_state).keys())
                if raw_context is None:
                    _persist_domain_manifest(username, session_state, db_path)
                session_state.pop("_workspace_save_error", None)
                session_state.pop("_workspace_save_conflict", None)
            return ok

        # Local development fallback only. A deployed Streamlit instance should
        # configure a managed database because local files are ephemeral.
        ensure_workspace_state_db(db_path)
        now = _dt.datetime.now(_dt.timezone.utc).isoformat()
        with sqlite3.connect(db_path, timeout=15, factory=ClosingSQLiteConnection) as conn:
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
        session_state["_shoir_persist_change_signature"] = change_signature
        session_state["_workspace_loaded_keys"] = list(_snapshot(session_state).keys())
        if raw_context is None:
            _persist_domain_manifest(username, session_state, db_path)
        session_state.pop("_workspace_save_error", None)
        session_state.pop("_workspace_save_conflict", None)
        return True
    except Exception as exc:
        # Do not fall back to SQLite or the personal workspace when a shared
        # organization save fails. Keep the in-session edits and surface a
        # non-secret diagnostic in the application shell.
        conflict = (
            "changed since it was loaded" in str(exc).casefold()
            or "shared_workspace_revision_conflict" in str(exc).casefold()
        )
        if conflict and isinstance(session_state.get("shoir_active_organization_workspace"), dict):
            session_state["_workspace_save_conflict"] = True
        if conflict:
            session_state["_workspace_save_error"] = (
                "A newer shared-workspace revision exists. Reload the workspace before saving."
            )
        elif isinstance(exc, ValueError) and str(exc) == "Both organization and workspace IDs are required for shared persistence.":
            session_state["_workspace_save_error"] = (
                "Both organization and workspace IDs are required for shared persistence."
            )
        elif isinstance(exc, ValueError) and str(exc) == "Active organization workspace context is invalid.":
            session_state["_workspace_save_error"] = (
                "Active organization workspace context is invalid."
            )
        elif "shared organization workspaces require" in str(exc).casefold():
            session_state["_workspace_save_error"] = (
                "Shared organization workspaces require the authenticated managed workspace service to be configured."
            )
        else:
            session_state["_workspace_save_error"] = (
                "Workspace persistence failed. Your current in-session changes have not been confirmed as saved."
            )
        return False


_BACKUP_FORMAT = "shoir-ie-user-workspace-backup"
_BACKUP_VERSION = 1
_MAX_BACKUP_BYTES = 32 * 1024 * 1024


def export_user_workspace_backup(
    username: str,
    session_state: MutableMapping[str, Any],
) -> dict[str, Any]:
    """Create a portable, integrity-checked backup of the current user's workspace.

    Authentication/session secrets and transient controls are excluded by the
    same allow-by-exclusion policy used for normal workspace persistence.
    The SHA-256 digest detects accidental corruption; it is not a signature
    and does not prove who created or modified a backup.
    """
    owner = str(username or "").strip().lower()
    if not owner or owner == "guest visitor":
        raise PermissionError("Sign in with a named account before exporting a workspace backup.")
    payload = _snapshot(session_state)
    envelope = {
        "format": _BACKUP_FORMAT,
        "version": _BACKUP_VERSION,
        "owner_username_lc": owner,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "payload": payload,
    }
    canonical = json.dumps(
        envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    envelope["sha256"] = digest
    data = json.dumps(
        envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(data) > _MAX_BACKUP_BYTES:
        raise ValueError(
            f"Workspace backup exceeds the {_MAX_BACKUP_BYTES // (1024 * 1024)} MiB safety limit."
        )
    return {
        "backup_bytes": data,
        "sha256": digest,
        "owner_username_lc": owner,
        "created_at": envelope["created_at"],
        "payload_key_count": len(payload),
        "backup_size_bytes": len(data),
        "warning": (
            "This portable file may contain private engineering workspace data. Store it securely. "
            "Its checksum detects accidental corruption but is not a cryptographic signature or encrypted backup."
        ),
    }


def verify_user_workspace_backup(
    backup_bytes: bytes | bytearray,
    username: str,
) -> dict[str, Any]:
    """Verify format, digest, size and current-account target before restoring."""
    owner = str(username or "").strip().lower()
    if not owner or owner == "guest visitor":
        raise PermissionError("Sign in with a named account before restoring a workspace backup.")
    if not isinstance(backup_bytes, (bytes, bytearray)):
        raise TypeError("Workspace backup must be uploaded as bytes.")
    if not backup_bytes or len(backup_bytes) > _MAX_BACKUP_BYTES:
        raise ValueError("Workspace backup is empty or exceeds the 32 MiB safety limit.")
    try:
        envelope = json.loads(bytes(backup_bytes).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Workspace backup is not valid UTF-8 JSON.") from exc
    if not isinstance(envelope, dict):
        raise ValueError("Workspace backup root must be a JSON object.")
    if envelope.get("format") != _BACKUP_FORMAT or envelope.get("version") != _BACKUP_VERSION:
        raise ValueError("Workspace backup format or version is not supported.")
    if str(envelope.get("owner_username_lc", "")).strip().lower() != owner:
        raise PermissionError("This backup belongs to a different account; restore was blocked.")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Workspace backup payload must be a JSON object.")
    supplied_digest = str(envelope.get("sha256", "")).strip().lower()
    canonical_envelope = {
        key: envelope[key]
        for key in ("format", "version", "owner_username_lc", "created_at", "payload")
        if key in envelope
    }
    canonical = json.dumps(
        canonical_envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    expected_digest = hashlib.sha256(canonical).hexdigest()
    if len(supplied_digest) != 64 or not hmac.compare_digest(supplied_digest, expected_digest):
        raise ValueError("Workspace backup checksum is invalid; no state was restored.")
    forbidden = [str(key) for key in payload if _excluded(str(key))]
    if forbidden:
        raise ValueError("Workspace backup contains excluded authentication or transient state.")
    for key, value in payload.items():
        if not isinstance(key, str):
            raise ValueError("Workspace backup contains a non-string state key.")
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    return {
        "owner_username_lc": owner,
        "created_at": str(envelope.get("created_at", "")),
        "sha256": expected_digest,
        "payload": payload,
        "payload_key_count": len(payload),
    }


def restore_user_workspace_backup(
    backup_bytes: bytes | bytearray,
    username: str,
    session_state: MutableMapping[str, Any],
) -> dict[str, Any]:
    """Restore only an already-verified same-account backup into current session state.

    Persistence is a separate explicit step so callers can first save a copy of
    the current session and roll back if the managed write fails.
    """
    verified = verify_user_workspace_backup(backup_bytes, username)
    restored = 0
    for key, value in verified["payload"].items():
        if _excluded(str(key)):
            continue
        session_state[str(key)] = _unpack(value)
        restored += 1
    return {
        "status": "WORKSPACE_BACKUP_RESTORED_IN_SESSION",
        "owner_username_lc": verified["owner_username_lc"],
        "source_created_at": verified["created_at"],
        "source_sha256": verified["sha256"],
        "restored_key_count": restored,
        "warning": (
            "The backup was restored in this session. The caller must save the restored state "
            "to the configured managed persistence backend before treating it as durable."
        ),
    }


def load_user_workspace(
    username: str,
    session_state: MutableMapping[str, Any],
    db_path: str = "enterprise_full_workspace.db",
) -> bool:
    if not username or username == "Guest Visitor":
        return False
    try:
        owner = str(username).strip().lower()
        context = session_state.get("shoir_active_organization_workspace")
        if isinstance(context, dict):
            scope = (
                str(context.get("organization_id") or ""),
                str(context.get("organization_workspace_id") or ""),
            )
        else:
            scope = None

        # A session can switch from personal state to a team workspace, between
        # two team workspaces, or between accounts. Remove only values loaded
        # from the previous durable workspace; credentials and active UI state
        # are excluded from the snapshot and are never cleared here.
        prior_owner = session_state.get("_workspace_loaded_owner")
        prior_scope = session_state.get("_workspace_loaded_scope")
        if prior_owner != owner or prior_scope != scope:
            prior_keys = session_state.get("_workspace_loaded_keys", [])
            if isinstance(prior_keys, list):
                for key in prior_keys:
                    if isinstance(key, str) and not _excluded(key):
                        session_state.pop(key, None)
            session_state.pop("_shoir_persist_change_signature", None)
            session_state["_workspace_loaded_keys"] = []
            session_state["_workspace_loaded_owner"] = owner
            session_state["_workspace_loaded_scope"] = scope
            session_state.pop("_workspace_org_revision", None)
            session_state.pop("_workspace_org_updated_at", None)

        remote_mode = durable_backend_configured() and db_path == "enterprise_full_workspace.db"
        if scope is not None and not remote_mode:
            raise RuntimeError("Shared organization workspaces require the authenticated managed workspace service.")
        if remote_mode:
            # A configured managed backend is authoritative. Do not fall back
            # to SQLite when the remote record is missing or temporarily empty;
            # doing so can resurrect stale cross-user/local state after a restart.
            remote_payload = load_remote_workspace(username)
            if not remote_payload:
                session_state["_workspace_loaded_keys"] = []
                return False
            payload = json.loads(remote_payload)
        else:
            ensure_workspace_state_db(db_path)
            with sqlite3.connect(db_path, timeout=15, factory=ClosingSQLiteConnection) as conn:
                row = conn.execute(
                    "SELECT state_json FROM workspace_states WHERE username = ?",
                    (owner,),
                ).fetchone()
            if not row or not row[0]:
                session_state["_workspace_loaded_keys"] = []
                return False
            payload = json.loads(row[0])

        if not isinstance(payload, dict):
            raise ValueError("Persisted workspace state must be a JSON object.")
        loaded_keys: list[str] = []
        for key, value in payload.items():
            if _excluded(str(key)):
                continue
            # Load persisted workspace values before module widgets are rendered.
            # This intentionally replaces defaults for the selected workspace.
            session_state[key] = _unpack(value)
            loaded_keys.append(str(key))
        session_state["_workspace_loaded_keys"] = loaded_keys
        session_state["_workspace_loaded_owner"] = owner
        session_state["_workspace_loaded_scope"] = scope
        session_state.pop("_workspace_load_error", None)
        return True
    except Exception as exc:
        # Access denial and corrupted payloads fail closed; never load the
        # previous user's or previous organization's values as a fallback.
        error_message = str(exc).casefold()
        if "shared organization workspaces require" in error_message:
            session_state["_workspace_load_error"] = (
                "Shared organization workspaces require the authenticated managed workspace service to be configured."
            )
        else:
            session_state["_workspace_load_error"] = (
                "Shared workspace access could not be verified. Select another workspace or return to your personal workspace."
                if "workspace" in error_message or "organization" in error_message
                else "The saved workspace could not be loaded safely."
            )
        return False
