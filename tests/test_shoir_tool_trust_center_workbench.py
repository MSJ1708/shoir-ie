"""Authenticated Workbench integration tests for the trust/help tool runners."""
from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "Industrial_Engineering_Workbench.py"


def _open_workbench():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(PAGE, default_timeout=45)
    at.session_state["current_user"] = "trust-center-checker"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    return at


def _choose_tool(at, label):
    at.selectbox(key="shoir_100_tool_inspector").select(label)
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)


def test_workbench_error_inspector_redacts_before_persisting_result():
    at = _open_workbench()
    _choose_tool(at, "T007 · Engineering Error Inspector")
    at.text_area(key="tool007_diagnostic").set_value(
        "403 permission denied api_key=very-secret-value owner@example.com"
    )
    at.button(key="tool007_run").click()
    at.run(timeout=45)

    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    result = at.session_state.get("shoir_tool_result_T007")
    saved_inputs = at.session_state.get("shoir_tool_inputs_T007")
    assert result is not None
    assert result["category"] == "AUTHORIZATION_OR_ACCESS"
    assert "very-secret-value" not in result["safe_summary"]
    assert "owner@example.com" not in result["safe_summary"]
    assert saved_inputs["raw_input_stored"] is False
    assert "very-secret-value" not in str(saved_inputs)


def test_workbench_capability_status_and_contextual_help_are_searchable():
    at = _open_workbench()
    _choose_tool(at, "T009 · Capability Status Center")
    at.button(key="tool009_run").click()
    at.run(timeout=45)

    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    status = at.session_state.get("shoir_tool_result_T009")
    assert status is not None
    assert status["registry_target_count"] == 100
    assert status["registry_integrity"] == "VALID"
    assert "not a live service-health check" in status["interpretation"]

    _choose_tool(at, "T010 · Interactive Learning and Help Center")
    at.text_input(key="tool010_query").set_value("facility layout")
    at.button(key="tool010_run").click()
    at.run(timeout=45)

    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    help_result = at.session_state.get("shoir_tool_result_T010")
    assert help_result is not None
    assert any(row["tool_id"] == "T065" for row in help_result["results"])


def test_workbench_support_bundle_is_downloadable_and_never_claims_delivery():
    at = _open_workbench()
    _choose_tool(at, "T100 · Support, Diagnostics, and Incident Center")
    at.text_area(key="tool100_diagnostic").set_value(
        "T017 failed api_key=do-not-share-this owner@example.com"
    )
    at.selectbox(key="tool100_severity").select("HIGH")
    at.button(key="tool100_run").click()
    at.run(timeout=45)

    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    bundle = at.session_state.get("shoir_tool_result_T100")
    saved_inputs = at.session_state.get("shoir_tool_inputs_T100")
    assert bundle is not None
    assert bundle["delivery_status"] == "PREPARED_NOT_SENT"
    assert bundle["raw_diagnostic_stored"] is False
    assert "do-not-share-this" not in str(bundle)
    assert "owner@example.com" not in str(bundle)
    assert "do-not-share-this" not in str(saved_inputs)
    assert 'key="tool100_download_bundle"' in PAGE.read_text(encoding="utf-8")
