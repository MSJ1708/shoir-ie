"""Redaction-first support diagnostics for T007 and T100.

These functions produce an actionable, user-reviewed diagnostic summary. They never
collect arbitrary environment variables or stack traces and do not submit an incident.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

_ERROR_GUIDANCE = {
    "Startup / loading": [
        "Reload once and note the exact page/module and time.",
        "Confirm required optional integrations are not treated as startup prerequisites.",
        "If loading still fails, share the redacted diagnostic reference with support.",
    ],
    "Import / workbook": [
        "Keep the original workbook unchanged and retry with a copy.",
        "Check file extension, file size, sheet names, headers, types, formulas and duplicate keys.",
        "Do not approve a cleaning or merge until row counts and source columns reconcile.",
    ],
    "Calculation / validation": [
        "Confirm required inputs, units, periods, denominator definitions and nonzero divisors.",
        "Read the method assumptions and warnings; do not substitute sample inputs for measured data.",
        "Record the target tool ID and a minimal synthetic reproduction without customer data.",
    ],
    "Solver / optimization": [
        "Inspect solver status; distinguish optimal, feasible, infeasible, unbounded, time limit and solver error.",
        "Check variable bounds, constraint directions, units, capacity and demand balance.",
        "Do not label a timeout or solver error as a proven infeasible model.",
    ],
    "Export / download": [
        "Retry with a smaller dataset and a distinct filename.",
        "Reopen the produced file with a parser or the intended office application.",
        "Compare key values, units, assumptions and source metadata against the on-screen result.",
    ],
    "Save / persistence": [
        "Confirm the visible persistence status; session-only is not durable storage.",
        "Do not assume data survived a refresh/relogin until a save/load check confirms it.",
        "Preserve the last successful result before retrying a failed save.",
    ],
    "Access / subscription": [
        "Confirm the signed-in account, active plan, expiry and workspace membership.",
        "A hidden card is not a security boundary; report direct-route denial behavior without sharing credentials.",
        "Do not use a privileged production administrator to reproduce an ordinary user issue.",
    ],
    "Connector / configuration": [
        "Treat the adapter as NOT CONNECTED until endpoint, credentials, permissions and a real test are confirmed.",
        "Check non-secret configuration names, endpoint reachability, authentication scope and schema/version.",
        "Never paste connection strings, access tokens, service-role keys or customer payloads into a support message.",
    ],
    "Other": [
        "Record the action attempted, visible status and a narrow sequence to reproduce the behavior.",
        "Remove personal/customer details and secrets before sharing any error text.",
        "Keep synthetic/demo values distinct from measured observations.",
    ],
}

_SECRET_KV = re.compile(
    r"(?i)\b(password|passwd|token|api[_-]?key|secret|authorization|service[_-]?role|"
    r"database[_-]?url|connection[_-]?string|access[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}={0,2}")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_URL = re.compile(r"(?i)\b(?:https?|postgres(?:ql)?|mysql)://[^\s<>\"']+")
_TOKEN_PREFIX = re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|sbp_[A-Za-z0-9]{12,})\b")
_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+")
_UNIX_HOME = re.compile(r"(?<!\w)/home/[^/\s]+")
_SAUDI_PHONE = re.compile(r"(?<!\w)(?:\+?966[-\s]?5\d(?:[-\s]?\d){7}|05\d(?:[-\s]?\d){7})(?!\w)")


def redact_diagnostic_text(value: str, *, max_length: int = 2000) -> dict[str, Any]:
    """Redact common secrets/PII and bound user-provided diagnostic text."""
    raw = str(value or "")
    if len(raw) > max_length:
        raw = raw[:max_length]
        truncated = True
    else:
        truncated = False
    raw = "".join(ch for ch in raw if ch in "\n\r\t" or ord(ch) >= 32)
    count = 0

    def sub(pattern: re.Pattern[str], replacement: str, text: str) -> str:
        nonlocal count
        text, n = pattern.subn(replacement, text)
        count += n
        return text

    raw = sub(_BEARER, "Bearer [REDACTED]", raw)
    raw = sub(_SECRET_KV, r"\1\2[REDACTED]", raw)
    raw = sub(_TOKEN_PREFIX, "[TOKEN REDACTED]", raw)
    raw = sub(_EMAIL, "[EMAIL REDACTED]", raw)
    raw = sub(_SAUDI_PHONE, "[PHONE REDACTED]", raw)
    raw = sub(_URL, "[URL REDACTED]", raw)
    raw = sub(_WINDOWS_PATH, "[PATH REDACTED]", raw)
    raw = sub(_UNIX_HOME, "[PATH REDACTED]", raw)
    return {"text": raw.strip(), "redactions_applied": count, "truncated": truncated}


def diagnose_error(
    *, category: str, operation: str = "", description: str = "", tool_id: str = "",
) -> dict[str, Any]:
    category_value = str(category or "").strip()
    if category_value not in _ERROR_GUIDANCE:
        raise ValueError(f"Unsupported error category. Choose one of: {', '.join(_ERROR_GUIDANCE)}.")
    if len(str(operation or "")) > 300:
        raise ValueError("Operation description is limited to 300 characters.")
    if len(str(description or "")) > 5000:
        raise ValueError("Error description is limited to 5000 characters.")
    canonical_tool_id = str(tool_id or "").strip().upper()
    if canonical_tool_id and not re.fullmatch(r"T(?:00[1-9]|0[1-9]\d|100)", canonical_tool_id):
        raise ValueError("Tool ID must be empty or a canonical ID from T001 to T100.")
    redacted = redact_diagnostic_text(description)
    operation_safe = redact_diagnostic_text(operation, max_length=300)
    return {
        "tool_id": "T007",
        "status": "DIAGNOSIS_PREPARED",
        "method": "Rule-based troubleshooting guidance with redaction of user-supplied description",
        "category": category_value,
        "operation": operation_safe["text"],
        "sanitized_description": redacted["text"],
        "selected_tool_id": canonical_tool_id or "NOT_PROVIDED",
        "guidance": list(_ERROR_GUIDANCE[category_value]),
        "metrics": {
            "guidance_steps": len(_ERROR_GUIDANCE[category_value]),
            "redactions_applied": redacted["redactions_applied"] + operation_safe["redactions_applied"],
            "description_truncated": redacted["truncated"],
        },
        "assumptions": [
            "This is a manual diagnostic helper and not automatic inspection of server logs or stack traces.",
            "Only the user-entered operation/description is included after redaction.",
        ],
        "warnings": [
            "Do not paste secrets or personal/customer data; redaction is a safeguard, not a guarantee.",
            "This helper does not submit a support case or independently determine root cause.",
        ],
    }


def build_support_diagnostic_bundle(
    *, app_version: str = "NOT_RECORDED", environment: str = "unknown",
    current_tool_id: str = "", category: str = "Other", operation: str = "",
    description: str = "", persistence_state: str = "UNVERIFIED",
) -> dict[str, Any]:
    """Build a minimal redacted JSON-ready support bundle without host/secret collection."""
    env = str(environment or "unknown").strip().lower()
    if env not in {"development", "test", "staging", "production", "unknown"}:
        raise ValueError("Environment must be development, test, staging, production or unknown.")
    version = str(app_version or "NOT_RECORDED").strip()
    if len(version) > 100:
        raise ValueError("Version label is limited to 100 characters.")
    if len(str(description or "")) > 5000:
        raise ValueError("Error description is limited to 5000 characters.")
    base = diagnose_error(category=category, operation=operation, description=description, tool_id=current_tool_id)
    allowed_persistence = {
        "MANAGED_WORKSPACE_SAVED", "LOCAL_SQLITE_SAVED_MAY_BE_EPHEMERAL",
        "SESSION_ONLY_SAVE_FAILED", "SESSION_ONLY_PERSISTENCE_MODE_UNVERIFIED",
        "UNVERIFIED", "NOT_APPLICABLE",
    }
    state = str(persistence_state or "UNVERIFIED").strip().upper()
    if state not in allowed_persistence:
        state = "UNVERIFIED"
    safe_version = redact_diagnostic_text(version, max_length=100)
    created_at = datetime.now(timezone.utc).isoformat()
    fingerprint_payload = "|".join([
        created_at, env, safe_version["text"], base["category"], base["selected_tool_id"],
        base["sanitized_description"],
    ])
    diagnostic_id = "SHOIR-" + hashlib.sha256(fingerprint_payload.encode("utf-8")).hexdigest()[:12].upper()
    return {
        "tool_id": "T100",
        "status": "DIAGNOSTIC_PREPARED_NOT_SUBMITTED",
        "diagnostic_id": diagnostic_id,
        "created_at_utc": created_at,
        "app_version": safe_version["text"] or "NOT_RECORDED",
        "environment": env,
        "selected_tool_id": base["selected_tool_id"],
        "category": base["category"],
        "operation": base["operation"],
        "sanitized_description": base["sanitized_description"],
        "persistence_state": state,
        "recommended_next_steps": base["guidance"],
        "redaction_count": base["metrics"]["redactions_applied"] + safe_version["redactions_applied"],
        "warnings": [
            "Prepared locally only; no incident was submitted and no support ticket is tracked.",
            "No environment variables, credentials, raw stack traces, customer datasets or server logs were collected.",
            *base["warnings"],
        ],
    }
