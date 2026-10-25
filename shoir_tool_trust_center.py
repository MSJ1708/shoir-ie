"""Safe help and diagnostic utilities for the Shoir-IE Workbench.

This module deliberately does not read application logs, secrets, environment
variables, or send telemetry. It turns user-supplied diagnostic text into a
redacted, bounded summary and produces support material that is explicitly
marked as not sent.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from uuid import uuid4

STATUS_VALUES = (
    "VERIFIED_WORKING",
    "IMPLEMENTED_NEEDS_VALIDATION",
    "FOUNDATION_ONLY",
    "MISSING",
    "EXTERNAL_CONFIGURATION_REQUIRED",
    "BLOCKED",
)

_SECRET_PATTERNS = (
    re.compile(
        r"(?i)\b(password|passwd|secret|api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|service[_ -]?role[_ -]?key)\b\s*[:=]\s*(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|sbp_[A-Za-z0-9_-]{16,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"),
    re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    re.compile(r"(?i)\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"(?i)\b[A-Z]:\\(?:[^\\\r\n]+\\)*[^\\\r\n]+"),
)
_TRACEBACK_FRAME = re.compile(r'^\s*File ["\'].*["\'], line \d+')


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def redact_diagnostic_text(value: Any, *, max_chars: int = 12000) -> dict[str, Any]:
    """Return a bounded, redacted summary; never return the raw submitted text."""
    raw = str(value or "")
    truncated = len(raw) > max_chars
    raw = raw[:max_chars]
    raw = "".join(ch for ch in raw if ch in "\n\r\t" or ord(ch) >= 32)
    redactions = 0
    cleaned = raw
    for pattern in _SECRET_PATTERNS:
        cleaned, count = pattern.subn(
            lambda match: (
                f"{match.group(1)}=[REDACTED]"
                if pattern is _SECRET_PATTERNS[0]
                else "[REDACTED]"
            ),
            cleaned,
        )
        redactions += count

    # A support summary should not reproduce a complete stack trace or source lines.
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if any(line.startswith("Traceback (most recent call last)") for line in lines):
        useful = [
            line for line in lines
            if not line.startswith("Traceback (most recent call last)")
            and not _TRACEBACK_FRAME.search(line)
            and not line.startswith(("^", "~~~"))
        ]
        cleaned = useful[-2:] and " | ".join(useful[-2:]) or "A traceback was supplied; frames were omitted."
    else:
        cleaned = " ".join(lines)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "No diagnostic details were supplied."
    summary = cleaned[:500]
    return {
        "safe_summary": summary,
        "redactions_applied": redactions,
        "input_truncated": truncated,
        "raw_input_stored": False,
        "raw_input_returned": False,
    }


def classify_diagnostic(value: Any) -> dict[str, Any]:
    """Classify a sanitized diagnostic into practical next checks."""
    scrubbed = redact_diagnostic_text(value)
    text = scrubbed["safe_summary"].casefold()
    if any(word in text for word in ("permission", "forbidden", "unauthorized", "sign in", "401", "403", "entitlement")):
        category = "AUTHORIZATION_OR_ACCESS"
        severity = "HIGH"
        checks = [
            "Confirm the account is signed in and the subscription is active.",
            "Confirm the tool is included in the account's package.",
            "Do not bypass server-side authorization; report a reproducible denial to support.",
        ]
    elif any(word in text for word in ("database", "postgres", "supabase", "connection", "timeout", "socket", "network")):
        category = "CONNECTIVITY_OR_PERSISTENCE"
        severity = "MEDIUM"
        checks = [
            "Check configured service availability and deployment parity.",
            "Confirm the last successful saved state remains available before retrying.",
            "Share only the redacted diagnostic bundle; never include connection strings or keys.",
        ]
    elif any(word in text for word in ("excel", "xlsx", "csv", "workbook", "import", "export", "zip", "pdf", "pptx")):
        category = "IMPORT_OR_EXPORT"
        severity = "MEDIUM"
        checks = [
            "Check file type, size, required sheets/columns and validation messages.",
            "Keep the original file until the new import or export has been verified.",
            "Reopen the generated file and confirm expected values and units.",
        ]
    elif any(word in text for word in ("valueerror", "calculation", "unit", "division", "nan", "infinite", "solver", "infeasible", "invalid")):
        category = "INPUT_OR_CALCULATION"
        severity = "MEDIUM"
        checks = [
            "Validate required fields, ranges, dimensions, units and measurement periods.",
            "Check the displayed method and assumptions against a hand-calculated fixture.",
            "Record the tool ID and reproducible, synthetic input—not sensitive plant data.",
        ]
    elif any(word in text for word in ("rate limit", "429", "too many requests")):
        category = "RATE_LIMIT"
        severity = "LOW"
        checks = [
            "Avoid rapid repeated submissions and retry according to the service's policy.",
            "Check for a duplicate operation before submitting again.",
        ]
    else:
        category = "UNCLASSIFIED"
        severity = "LOW"
        checks = [
            "Repeat the action once with a small synthetic example.",
            "Record the target tool ID, what you expected, and what happened.",
            "Include the redacted summary only; remove customer and production data.",
        ]
    return {
        **scrubbed,
        "category": category,
        "severity": severity,
        "recommended_checks": checks,
        "scope_note": "This is rule-based triage, not a diagnosis of the live service or its logs.",
    }


def summarize_capability_registry(
    targets: Iterable[Mapping[str, Any]],
    *,
    status_filter: str = "All statuses",
    limit: int = 100,
    expected_count: int = 100,
) -> dict[str, Any]:
    """Summarize the source registry without presenting it as live runtime health."""
    target_list = list(targets)
    ids = [str(row.get("tool_id", "")).strip() for row in target_list]
    nonempty_ids = [item for item in ids if item]
    counts = Counter(str(row.get("implementation_status", "UNRESOLVED")) for row in target_list)
    duplicates = sorted({item for item in nonempty_ids if nonempty_ids.count(item) > 1})
    expected_ids = {f"T{i:03d}" for i in range(1, expected_count + 1)}
    missing_ids = sorted(expected_ids - set(nonempty_ids))
    unknown_statuses = sorted(set(counts) - set(STATUS_VALUES))
    valid_filter = status_filter if status_filter in STATUS_VALUES else "All statuses"
    selected = [
        row for row in target_list
        if valid_filter == "All statuses" or row.get("implementation_status") == valid_filter
    ]
    selected.sort(key=lambda row: str(row.get("tool_id", "")))
    safe_rows = [
        {
            "tool_id": str(row.get("tool_id", "")),
            "name": str(row.get("canonical_name", "")),
            "workbench": str(row.get("workbench", "")),
            "minimum_tier": str(row.get("target_minimum_tier", "")),
            "status": str(row.get("implementation_status", "UNRESOLVED")),
            "open_gap": str(row.get("remaining_gap", ""))[:300],
        }
        for row in selected[: max(1, min(int(limit), 100))]
    ]
    return {
        "generated_at_utc": _now_utc(),
        "registry_target_count": len(target_list),
        "expected_target_count": expected_count,
        "unique_nonempty_ids": len(set(nonempty_ids)),
        "missing_expected_ids": missing_ids,
        "duplicate_ids": duplicates,
        "unknown_statuses": unknown_statuses,
        "registry_integrity": "VALID" if (
            len(target_list) == expected_count
            and len(set(nonempty_ids)) == expected_count
            and not missing_ids and not duplicates and not unknown_statuses
        ) else "NEEDS_REVIEW",
        "status_counts": {status: counts.get(status, 0) for status in STATUS_VALUES},
        "filtered_status": valid_filter,
        "rows_returned": len(safe_rows),
        "capabilities": safe_rows,
        "interpretation": "Registry metadata only: not a live service-health check, authenticated browser test, or proof that the listed tools passed end-to-end acceptance.",
    }


def search_tool_help(
    targets: Iterable[Mapping[str, Any]],
    query: str = "",
    *,
    workbench_filter: str = "All workbenches",
    limit: int = 20,
) -> dict[str, Any]:
    """Search canonical tool metadata and give safe, action-oriented onboarding guidance."""
    target_list = list(targets)
    areas = sorted({str(row.get("workbench", "")) for row in target_list if row.get("workbench")})
    requested_area = workbench_filter if workbench_filter in areas else "All workbenches"
    terms = [term for term in re.findall(r"[a-zA-Z0-9_-]+", str(query).casefold()) if len(term) > 1]
    ranked: list[tuple[int, Mapping[str, Any]]] = []
    for row in target_list:
        if requested_area != "All workbenches" and row.get("workbench") != requested_area:
            continue
        haystack = " ".join(
            str(row.get(key, "")) for key in (
                "tool_id", "canonical_name", "workbench", "calculation_or_action",
                "input_contract", "output_contract", "remaining_gap",
            )
        ).casefold()
        score = sum(2 if term in str(row.get("canonical_name", "")).casefold() else 1 for term in terms if term in haystack)
        if not terms or score:
            ranked.append((score, row))
    ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("tool_id", ""))))
    results = []
    for score, row in ranked[: max(1, min(int(limit), 50))]:
        results.append({
            "tool_id": str(row.get("tool_id", "")),
            "name": str(row.get("canonical_name", "")),
            "workbench": str(row.get("workbench", "")),
            "minimum_tier": str(row.get("target_minimum_tier", "")),
            "status": str(row.get("implementation_status", "UNRESOLVED")),
            "purpose": str(row.get("calculation_or_action", "")),
            "required_inputs": str(row.get("input_contract", "")),
            "expected_outputs": str(row.get("output_contract", "")),
            "known_limitations": str(row.get("remaining_gap", "")),
            "relevance_score": score,
        })
    return {
        "generated_at_utc": _now_utc(),
        "query_was_empty": not bool(terms),
        "workbench_filter": requested_area,
        "match_count_returned": len(results),
        "results": results,
        "getting_started": [
            "Confirm the minimum tier and the tool's current readiness label.",
            "Prepare the required fields and check units, dates, and measurement periods.",
            "Start with a synthetic example if the method is unfamiliar; replace it with validated source data before operational use.",
            "Inspect warnings and assumptions, then save/export only after validating the result.",
        ],
        "interpretation": "Help is derived from the current tool registry. It does not certify the calculation method or replace tool-specific validation.",
    }


def build_redacted_support_bundle(
    targets: Iterable[Mapping[str, Any]],
    *,
    diagnostic_text: Any,
    component: str,
    severity: str,
) -> dict[str, Any]:
    """Create a redacted support packet; this function never transmits or stores raw text."""
    diagnosis = classify_diagnostic(diagnostic_text)
    registry = summarize_capability_registry(targets, limit=0)
    severity_value = severity.strip().upper() if severity.strip().upper() in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else "MEDIUM"
    component_value = component.strip()[:80] or "Not specified"
    return {
        "support_reference": "SHOIR-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid4().hex[:8].upper(),
        "created_at_utc": _now_utc(),
        "component": component_value,
        "reported_severity": severity_value,
        "diagnostic_category": diagnosis["category"],
        "redacted_summary": diagnosis["safe_summary"],
        "redactions_applied": diagnosis["redactions_applied"],
        "input_truncated": diagnosis["input_truncated"],
        "raw_diagnostic_stored": False,
        "raw_diagnostic_returned": False,
        "registry_target_count": registry["registry_target_count"],
        "registry_status_counts": registry["status_counts"],
        "registry_integrity": registry["registry_integrity"],
        "recommended_checks": diagnosis["recommended_checks"],
        "delivery_status": "PREPARED_NOT_SENT",
        "support_backend_configured": False,
        "next_action": "Download and review this redacted JSON bundle before sharing it through an approved support channel. No ticket was opened and no data was transmitted.",
    }
