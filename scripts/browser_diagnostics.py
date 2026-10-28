"""Secret-redacted, bounded browser exception diagnostics for staging acceptance."""
from __future__ import annotations

import re


def safe_javascript_diagnostic(value: object, limit: int = 700) -> str:
    """Keep enough browser diagnostics to find a runtime fault without storing secrets."""
    text = str(value or "")
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
        "[REDACTED_JWT]",
        text,
    )
    text = re.sub(
        r"(?i)\b(password|passwd|token|secret|api[_-]?key|authorization|cookie)\b\s*[:=]\s*[^\s,;]+",
        r"\1=[REDACTED]",
        text,
    )
    # Preserve script origins/paths, but never persist query-string values.
    text = re.sub(r"(https?://[^\s?#]+)\?[^\s#]+", r"\1?[REDACTED_QUERY]", text)
    return text[:limit]


def safe_javascript_error(error: object) -> dict[str, str]:
    """Serialize a Playwright pageerror with redaction, bounded size, and source frames."""
    name = safe_javascript_diagnostic(getattr(error, "name", type(error).__name__), 100)
    message = safe_javascript_diagnostic(getattr(error, "message", ""), 700)
    raw_stack = str(getattr(error, "stack", "") or "")
    safe_frames = [
        safe_javascript_diagnostic(line.strip(), 320)
        for line in raw_stack.splitlines()[1:5]
        if line.strip()
    ]
    return {"name": name or "Error", "message": message, "stack_frames": "\n".join(safe_frames)}
