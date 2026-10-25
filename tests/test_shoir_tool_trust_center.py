"""Tests for safe diagnostics, registry transparency and searchable tool help."""
from __future__ import annotations

from shoir_tool_registry import TOOL_TARGETS
from shoir_tool_trust_center import (
    STATUS_VALUES,
    build_redacted_support_bundle,
    classify_diagnostic,
    redact_diagnostic_text,
    search_tool_help,
    summarize_capability_registry,
)


def test_redaction_removes_credentials_contact_data_and_network_addresses():
    diagnostic = (
        "Request failed password=hunter2 api_key=secret-demo-token "
        "Authorization: Bearer abc.def.ghi user=owner@example.com "
        "endpoint=https://admin:verysecret@internal.example.com call=192.168.10.4"
    )
    result = redact_diagnostic_text(diagnostic)

    assert result["raw_input_stored"] is False
    assert result["raw_input_returned"] is False
    assert result["redactions_applied"] >= 5
    assert "hunter2" not in result["safe_summary"]
    assert "secret-demo-token" not in result["safe_summary"]
    assert "abc.def.ghi" not in result["safe_summary"]
    assert "owner@example.com" not in result["safe_summary"]
    assert "192.168.10.4" not in result["safe_summary"]
    assert "verysecret" not in result["safe_summary"]


def test_stack_trace_frames_are_removed_and_summary_is_bounded():
    diagnostic = (
        'Traceback (most recent call last):\n'
        '  File "C:\\Users\\private\\app.py", line 123, in run\n'
        '    call_secret()\n'
        'ValueError: invalid quantity email=user@example.com'
    )
    result = redact_diagnostic_text(diagnostic)

    assert "Traceback" not in result["safe_summary"]
    assert "private" not in result["safe_summary"]
    assert "call_secret" not in result["safe_summary"]
    assert "user@example.com" not in result["safe_summary"]
    assert "ValueError" in result["safe_summary"]

    long_result = redact_diagnostic_text("x" * 2000, max_chars=100)
    assert long_result["input_truncated"] is True
    assert len(long_result["safe_summary"]) <= 500


def test_diagnostic_classification_returns_actionable_non_authoritative_guidance():
    auth = classify_diagnostic("403 forbidden: tool entitlement denied")
    database = classify_diagnostic("Postgres socket connection timeout")
    import_error = classify_diagnostic("Excel workbook import failed")
    generic = classify_diagnostic("Something unusual happened")

    assert auth["category"] == "AUTHORIZATION_OR_ACCESS"
    assert auth["severity"] == "HIGH"
    assert database["category"] == "CONNECTIVITY_OR_PERSISTENCE"
    assert import_error["category"] == "IMPORT_OR_EXPORT"
    assert generic["category"] == "UNCLASSIFIED"
    assert all(item["recommended_checks"] for item in (auth, database, import_error, generic))
    assert "not a diagnosis" in auth["scope_note"]


def test_capability_status_report_checks_registry_integrity_and_explains_limitations():
    report = summarize_capability_registry(TOOL_TARGETS)

    assert report["registry_target_count"] == 100
    assert report["expected_target_count"] == 100
    assert report["registry_integrity"] == "VALID"
    assert report["missing_expected_ids"] == []
    assert report["duplicate_ids"] == []
    assert sum(report["status_counts"].values()) == 100
    assert set(report["status_counts"]) == set(STATUS_VALUES)
    assert "not a live service-health check" in report["interpretation"]


def test_capability_status_report_detects_duplicate_missing_and_unknown_metadata():
    rows = [
        {
            "tool_id": "T001",
            "canonical_name": "Example",
            "workbench": "Core",
            "target_minimum_tier": "Starter",
            "implementation_status": "INVENTED_STATUS",
            "remaining_gap": "not validated",
        },
        {
            "tool_id": "T001",
            "canonical_name": "Duplicate",
            "workbench": "Core",
            "target_minimum_tier": "Starter",
            "implementation_status": "FOUNDATION_ONLY",
            "remaining_gap": "",
        },
    ]

    report = summarize_capability_registry(rows, expected_count=2)
    assert report["registry_integrity"] == "NEEDS_REVIEW"
    assert report["duplicate_ids"] == ["T001"]
    assert report["unknown_statuses"] == ["INVENTED_STATUS"]
    assert report["missing_expected_ids"] == ["T002"]


def test_help_search_returns_real_registry_contracts_and_keeps_known_gaps_visible():
    result = search_tool_help(TOOL_TARGETS, "facility layout")

    assert result["match_count_returned"] > 0
    assert any(row["tool_id"] == "T065" for row in result["results"])
    tool = next(row for row in result["results"] if row["tool_id"] == "T065")
    assert tool["required_inputs"]
    assert tool["expected_outputs"]
    assert "status" in tool
    assert "not replace tool-specific validation" in result["interpretation"]


def test_support_bundle_is_redacted_not_sent_and_has_a_reference():
    result = build_redacted_support_bundle(
        TOOL_TARGETS,
        diagnostic_text="Request to api_key=top-secret-key owner@example.com failed: 403 permission denied",
        component="Workbench",
        severity="critical",
    )

    assert result["support_reference"].startswith("SHOIR-")
    assert result["component"] == "Workbench"
    assert result["reported_severity"] == "CRITICAL"
    assert result["raw_diagnostic_stored"] is False
    assert result["raw_diagnostic_returned"] is False
    assert result["delivery_status"] == "PREPARED_NOT_SENT"
    assert result["support_backend_configured"] is False
    assert "top-secret-key" not in result["redacted_summary"]
    assert "owner@example.com" not in result["redacted_summary"]
    assert "No data was transmitted" in result["next_action"]
