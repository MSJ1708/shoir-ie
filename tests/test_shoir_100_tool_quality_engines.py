"""Golden/boundary fixtures for FMEA and CAPA/8D record methods."""
import pandas as pd
import pytest

from shoir_100_tool_quality_engines import build_capa_8d_record, score_fmea_register


def test_fmea_rpn_sorting_and_severity_are_reported_separately():
    rows = pd.DataFrame([
        {"failure_mode":"Seal leak","effect":"Fluid loss","cause":"Wear","current_controls":"Inspection",
         "severity":8,"occurrence":3,"detection":4,"recommended_action":"Change interval","owner":"A","due_date":"2026-11-01","action_status":"Open"},
        {"failure_mode":"Guard missing","effect":"Exposure","cause":"Bypass","current_controls":"Visual check",
         "severity":10,"occurrence":2,"detection":2,"recommended_action":"Restore guard","owner":"B","due_date":"2026-10-30","action_status":"In Progress"},
    ])
    result = score_fmea_register(rows)
    assert result["status"] == "CALCULATED"
    assert result["metrics"]["failure_mode_count"] == 2
    assert result["metrics"]["maximum_rpn"] == 96
    assert result["metrics"]["severity_9_or_10_count"] == 1
    assert result["register"].iloc[0]["failure_mode"] == "Seal leak"
    assert result["metrics"]["actions_not_closed"] == 2
    assert any("not an objective probability" in warning for warning in result["warnings"])


def test_fmea_rejects_duplicate_modes_bad_scores_and_invalid_dates():
    base = {"effect":"Effect","cause":"Cause","current_controls":"","severity":5,"occurrence":4,"detection":3,
            "recommended_action":"Action","owner":"Owner","due_date":"","action_status":"Open"}
    with pytest.raises(ValueError, match="repeated"):
        score_fmea_register([{**base,"failure_mode":"Failure"},{**base,"failure_mode":"failure"}])
    with pytest.raises(ValueError, match="whole-number"):
        score_fmea_register([{**base,"failure_mode":"Failure","severity":11}])
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        score_fmea_register([{**base,"failure_mode":"Failure","due_date":"11/01/2026"}])


def test_capa_record_open_state_never_claims_independent_verification():
    result = build_capa_8d_record(
        record_id="CAPA-001", problem_statement="Repeat defects", owner="Quality lead", team="Quality team",
        opened_date="2026-10-24", due_date="2026-11-20", status="Verification",
        containment="Quarantined the affected lot",
        root_cause="Seal setup drift",
        corrective_actions="Update setup standard",
        verification_evidence="Inspection report Q-22",
        preventive_action="Add weekly process audit",
        lessons_learned="Review all similar lines",
        verified_by="Reviewer", verification_date="2026-10-24",
    )
    assert result["status"] == "CALCULATED"
    assert result["metrics"]["sections_completed"] == 7
    assert result["metrics"]["closure_ready"] is False
    assert result["metrics"]["evidence_independently_verified"] is False
    assert result["record"]["evidence_state"] == "USER_ENTERED_UNVERIFIED"


def test_capa_cannot_be_closed_without_all_sections_and_verifier():
    with pytest.raises(ValueError, match="cannot be marked Closed"):
        build_capa_8d_record(
            record_id="CAPA-002", problem_statement="Missing checklist", owner="Manager",
            opened_date="2026-10-24", due_date="2026-11-01", status="Closed",
        )
