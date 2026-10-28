from __future__ import annotations

from types import SimpleNamespace

from scripts.authenticated_browser_matrix import _safe_javascript_error


def test_browser_error_diagnostics_preserve_error_name_message_and_source_frames():
    error = SimpleNamespace(
        name="TypeError",
        message="Cannot read properties of undefined (reading 'map')",
        stack=(
            "TypeError: Cannot read properties of undefined (reading 'map')\\n"
            "    at renderWorkbook (https://shoirieverified.streamlit.app/assets/app.js:2:19)\\n"
            "    at app (https://shoirieverified.streamlit.app/assets/app.js:5:32)"
        ),
    )

    result = _safe_javascript_error(error)

    assert result["name"] == "TypeError"
    assert "undefined" in result["message"]
    assert "renderWorkbook" in result["stack_frames"]
    assert "app.js:2:19" in result["stack_frames"]


def test_browser_error_diagnostics_redact_tokens_and_url_query_values():
    secret_token = "eyJabcdefgh12345678.abcdefghijklmnop.zyxwvutsrqponm"
    error = SimpleNamespace(
        name="Error",
        message=(
            f"Authorization: Bearer {secret_token}; "
            f"token={secret_token}; "
            f"request https://shoirieverified.streamlit.app/api?access_token={secret_token}"
        ),
        stack="Error: diagnostic\\n    at start (https://example.test/app.js?key=secret:3:4)",
    )

    result = _safe_javascript_error(error)
    combined = " ".join([result["message"], result["stack_frames"]])

    assert secret_token not in combined
    assert "Bearer [REDACTED]" in combined or "Authorization=[REDACTED]" in combined
    assert "[REDACTED_QUERY]" in combined
