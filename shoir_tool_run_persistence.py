"""Persistence status helpers for Engineering Tool Library results.

Results are saved through Shoir-IE's existing owner-scoped workspace store.
The helper reports managed persistence separately from the local SQLite
fallback, which may be ephemeral in hosted environments.
"""
from __future__ import annotations

from typing import Any, MutableMapping


_MANAGED_OK = "MANAGED_WORKSPACE_SAVED"
_LOCAL_ONLY = "LOCAL_SQLITE_SAVED_MAY_BE_EPHEMERAL"
_SAVE_FAILED = "SESSION_ONLY_SAVE_FAILED"
_MODE_UNKNOWN = "SESSION_ONLY_PERSISTENCE_MODE_UNVERIFIED"


def persist_tool_run_record(
    username: str,
    session_state: MutableMapping[str, Any],
    result_key: str,
    *,
    save_workspace=None,
    managed_backend_configured=None,
) -> dict[str, Any]:
    """Save a tool-run record with the existing workspace persistence service.

    Unknown persistence mode or failed writes never produce a success status.
    The in-session result is retained on failure so the user can still export
    it, but it is explicitly marked as not saved to the workspace.
    """
    record = session_state.get(result_key)
    if not isinstance(record, dict):
        return {
            "saved": False,
            "status": _SAVE_FAILED,
            "message": "No result record was available to persist.",
        }
    if not str(username or "").strip() or str(username).strip().casefold() == "guest visitor":
        record["persistence_status"] = _SAVE_FAILED
        session_state[result_key] = record
        return {
            "saved": False,
            "status": _SAVE_FAILED,
            "message": "An authenticated workspace owner is required to save this result.",
        }

    try:
        if save_workspace is None:
            from workspace_persistence import save_user_workspace as save_workspace
        if managed_backend_configured is None:
            from durable_account_store import durable_backend_configured as managed_backend_configured
        managed = bool(managed_backend_configured())
    except Exception as exc:
        record["persistence_status"] = _MODE_UNKNOWN
        session_state[result_key] = record
        return {
            "saved": False,
            "status": _MODE_UNKNOWN,
            "message": f"Workspace persistence mode could not be verified ({type(exc).__name__}).",
        }

    # This status is included in the saved payload. It is shown to the user only
    # after the save function confirms success; on failure it is overwritten below.
    proposed_status = _MANAGED_OK if managed else _LOCAL_ONLY
    record["persistence_status"] = proposed_status
    session_state[result_key] = record
    try:
        saved = bool(save_workspace(str(username).strip(), session_state))
    except Exception:
        saved = False

    if not saved:
        record["persistence_status"] = _SAVE_FAILED
        session_state[result_key] = record
        return {
            "saved": False,
            "status": _SAVE_FAILED,
            "message": "The result remains available in this session, but workspace saving failed.",
        }

    if managed:
        message = "Saved to the configured managed workspace."
    else:
        message = "Saved to local SQLite for development; this may be ephemeral in hosted deployments."
    return {"saved": True, "status": proposed_status, "message": message}
