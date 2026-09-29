"""Structured observability helpers for Shoir-IE.

The UI can surface a concise diagnostic while the logger keeps the full
exception context in deployment logs. No secrets or full user payloads are
serialized by default.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("shoir.ie")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


def log_exception(scope: str, exc: BaseException, *, level: int = logging.ERROR, extra: dict[str, Any] | None = None) -> None:
    """Record an exception with scope and safe metadata without re-raising it."""
    metadata = {"scope": str(scope), **(dict(extra or {}))}
    logger.log(level, "Shoir-IE exception: %s | %s", str(exc), metadata, exc_info=True)


def log_event(event: str, *, scope: str = "platform", extra: dict[str, Any] | None = None) -> None:
    """Record a non-sensitive operational event."""
    logger.info("Shoir-IE event: %s | scope=%s | extra=%s", str(event), str(scope), dict(extra or {}))
