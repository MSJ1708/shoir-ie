"""Shared observability for Shoir-IE.

Errors are classified and retained in session state for UI diagnostics while
remaining non-fatal, preserving the platform's recovery-first behavior.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import json
import logging

LOGGER = logging.getLogger("shoir-ie")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_exception(scope: str, exc: BaseException, *, recoverable: bool = True, **context: Any) -> dict[str, Any]:
    payload = {
        "scope": str(scope),
        "type": type(exc).__name__,
        "message": str(exc),
        "recoverable": bool(recoverable),
        "at": now_iso(),
        **context,
    }
    LOGGER.exception("Shoir-IE exception [%s]: %s", scope, exc)
    return payload


def safe_error_json(scope: str, exc: BaseException, **context: Any) -> str:
    return json.dumps(log_exception(scope, exc, **context), default=str, ensure_ascii=False)


__all__ = ["log_exception", "safe_error_json"]
