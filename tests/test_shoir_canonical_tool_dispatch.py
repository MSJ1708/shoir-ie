from __future__ import annotations

import pandas as pd
import pytest

from shoir_canonical_tool_dispatch import CANONICAL_TOOL_IDS, execute_canonical_tool
from shoir_tool_registry import TOOL_BY_ID


def _tier(tool_id: str) -> str:
    return str(TOOL_BY_ID[tool_id]["target_minimum_tier"])


def _run(tool_id: str, payload: dict, state: dict | None = None):
    return execute_canonical_tool(tool_id, payload, _tier(tool_id), "canonical-dispatch-test-user", state or {})


def test_dispatch_is_exactly_the_nine_previously_unwired_ids():
    assert CANONICAL_TOOL_IDS == ("T001", "T003", "T008", "T053", "T057", "T064", "T088", "T090", "T093")


def test_t001_home_is_session_scoped_and_tier_filters_recent_tools():
    state = {
        "shoir_workspace_name": "test-workspace",
        "shoir_tool_result_T001": {"status": "RESULT"},
        "shoir_tool_result_T096": {"status": "CONNECTOR_NOT_CONFIGURED"},
    }
    result = _run("T001", {}, state)
    assert result["workspace"] == "test-workspace"
    assert result["recent_tool_count"] == 1
    assert result["recent_tools"].iloc[0]["tool_id"] == "T001"
    assert "cross-tenant" in result["warning"]


def test_t003_searches_permitted_registry_and_current_session_only():
    result = _run("T003", {"query": "inventory"}, {
        "shoir_tool_result_T055": {"status": "CALCULATED"},
    })
    assert result["result_count"] >= 1
    assert "T055" in set(result["results"]["id"])
    assert set(result["results"]["kind"]).issubset({"TOOL", "CURRENT_SESSION_RESULT"})


def test_t008_inspector_discloses_missing_fields_and_redacts_secret_metadata():
    result = _run("T008", {
        "result_tool_id": "MANUAL",
        "record_json": '{"method":"EOQ","api_token":"do-not-return","unit":"units","assumptions":["constant demand"]}',
    })
    assert result["details"]["method"] == "EOQ"
    assert "api_token" not in str(result["details"])
    assert "limits/boundary" in result["missing_metadata"]
    assert len(result["metadata_sha256"]) == 64


def test_t053_scheduler_applies_material_limit_and_maintenance_window():
    payload = {
        "orders_json": (
            '[{"Order":"O1","Product":"P1","Qty":4,"DueDate":"2026-11-20T10:00:00Z",'
            '"ProcessingMin":60,"Machine":"M1","SetupMin":5,"Priority":2,'
            '"MaterialReady":"2026-11-16T08:00:00Z"}]'
        ),
        "maintenance_json": (
            '[{"Machine":"M1","Start":"2026-11-16T08:00:00Z","End":"2026-11-16T09:00:00Z"}]'
        ),
        "materials_json": '{"P1":4}',
        "start_time_utc": "2026-11-16T08:00:00Z",
    }
    result = _run("T053", payload)
    assert result["diagnostics"]["scheduled_orders"] == 1
    assert result["diagnostics"]["blocked_orders"] == 0
    assert result["schedule"].iloc[0]["Start"] >= pd.Timestamp("2026-11-16T09:00:00")
    assert "not a globally optimal" in result["warning"]

    payload["materials_json"] = '{"P1":2}'
    blocked = _run("T053", payload)
    assert blocked["diagnostics"]["blocked_orders"] == 1
    assert blocked["schedule"].empty

    payload["materials_json"] = '{"P1":4}'
    payload["orders_json"] = (
        '[{"Order":"O1","Product":"P1","Qty":4,"DueDate":"2026-11-20T10:00:00",'
        '"ProcessingMin":60,"Machine":"M1","SetupMin":5,"Priority":2,"MaterialReady":"2026-11-16T08:00:00"}]'
    )
    with pytest.raises(ValueError, match="timezone offset or Z"):
        _run("T053", payload)


def test_t057_roster_prevents_overlap_and_reports_skill_coverage_gaps():
    result = _run("T057", {
        "staff_json": '[{"staff_id":"A","skills":["Mechanical"],"available_shifts":["D","N"]},{"staff_id":"B","skills":["Electrical"],"available_shifts":["D"]}]',
        "shifts_json": (
            '[{"shift_id":"D","start_utc":"2026-11-17T06:00:00Z","end_utc":"2026-11-17T14:00:00Z","required_skills":{"Mechanical":1,"Electrical":1}},'
            '{"shift_id":"N","start_utc":"2026-11-17T10:00:00Z","end_utc":"2026-11-17T18:00:00Z","required_skills":{"Mechanical":1}}]'
        ),
        "max_hours_per_person": 40,
    })
    assert len(result["assignments"]) == 2
    assert len(result["unmet_coverage"]) == 1
    assert not result["feasible"]


def test_t064_routing_requires_complete_directed_matrix_and_reports_unserved_stops():
    payload = {
        "depot": "D",
        "stops_json": '[{"id":"A","demand":4,"earliest_minute":0,"latest_minute":100,"service_minutes":5},{"id":"B","demand":5,"earliest_minute":0,"latest_minute":100,"service_minutes":5}]',
        "vehicles_json": '[{"id":"V1","capacity":4,"max_route_minutes":120}]',
        "travel_matrix_json": (
            '[{"from":"D","to":"A","distance":2,"travel_minutes":2},{"from":"A","to":"D","distance":2,"travel_minutes":2},'
            '{"from":"D","to":"B","distance":3,"travel_minutes":3},{"from":"B","to":"D","distance":3,"travel_minutes":3},'
            '{"from":"A","to":"B","distance":1,"travel_minutes":1},{"from":"B","to":"A","distance":1,"travel_minutes":1}]'
        ),
    }
    result = _run("T064", payload)
    assert result["served_stop_count"] == 1
    assert result["unserved_stop_count"] == 1
    assert not result["feasible"]
    payload["vehicles_json"] = '[{"id":"V1","capacity":1,"max_route_minutes":120}]'
    no_assignment = _run("T064", payload)
    assert no_assignment["served_stop_count"] == 0
    assert no_assignment["unserved_stop_count"] == 2
    payload["vehicles_json"] = '[{"id":"V1","capacity":4,"max_route_minutes":120}]'
    payload["travel_matrix_json"] = "[]"
    with pytest.raises(ValueError, match="Travel matrix"):
        _run("T064", payload)
    payload["travel_matrix_json"] = (
        '[{"from":"D","to":"A","distance":2,"travel_minutes":2},{"from":"A","to":"D","distance":2,"travel_minutes":2},'
        '{"from":"D","to":"B","distance":3,"travel_minutes":3},{"from":"B","to":"D","distance":3,"travel_minutes":3},'
        '{"from":"A","to":"B","distance":1,"travel_minutes":1},{"from":"B","to":"A","distance":1,"travel_minutes":1},'
        '{"from":"D","to":"A","distance":9,"travel_minutes":9}]'
    )
    with pytest.raises(ValueError, match="Duplicate travel-matrix arc"):
        _run("T064", payload)


def test_t088_citation_matrix_never_claims_source_verification():
    result = _run("T088", {
        "records_json": '[{"title":"Study","authors":"A","year":2025,"source":"10.1234/example","claim":"Claim","method":"Method"},{"title":"Duplicate","year":2024,"source":"10.1234/example","claim":"Claim 2","method":"Method"}]'
    })
    assert result["format_valid_count"] == 2
    assert result["duplicate_source_count"] == 1
    assert set(result["evidence_matrix"]["source_status"]) == {"FORMAT_VALID_NOT_VERIFIED"}
    assert "not verified" in result["warning"].lower()


def test_t090_report_builder_hashes_and_labels_unverified_inputs():
    result = _run("T090", {
        "study_title": "Capacity study", "objective": "Estimate capacity under supplied conditions.",
        "method": "Deterministic capacity calculation", "method_version": "1.0",
        "data_provenance": "SYNTHETIC", "inputs_json": '{"demand":10}',
        "results_json": '{"capacity":12}', "assumptions_json": '[{"assumption":"One shift"}]',
        "sources_json": "[]", "limitations": "Synthetic input; no plant validation.",
    })
    assert result["sha256"] == __import__("hashlib").sha256(result["report_markdown"].encode()).hexdigest()
    assert "not independently verify" in result["warning"].lower()
    assert "SYNTHETIC" in result["report_markdown"]


def test_t093_workflow_builder_topologically_orders_and_never_executes():
    result = _run("T093", {
        "steps_json": (
            '[{"step_id":"profile","tool_id":"T011","depends_on":[],"required_inputs":["dataset"],'
            '"inputs":{"dataset":{"value":"DS-1","type":"string"}},"outputs":{"profile":"object"}},'
            '{"step_id":"quality","tool_id":"T024","depends_on":["profile"],"required_inputs":["profile"],'
            '"inputs":{"profile":{"from_step":"profile","output":"profile","type":"object"}},"outputs":{"quality":"object"}}]'
        )
    })
    assert list(result["steps"]["step_id"]) == ["profile", "quality"]
    assert result["plan_only"] is True
    assert result["execution_permitted"] is False
    assert not result["steps"]["execution_permitted"].any()


def test_t093_rejects_cycles_and_incompatible_linked_types():
    cycle = '[{"step_id":"A","tool_id":"T011","depends_on":["B"],"inputs":{},"outputs":{}},{"step_id":"B","tool_id":"T024","depends_on":["A"],"inputs":{},"outputs":{}}]'
    with pytest.raises(ValueError, match="cycle"):
        _run("T093", {"steps_json": cycle})
    incompatible = '[{"step_id":"A","tool_id":"T011","depends_on":[],"inputs":{},"outputs":{"table":"object"}},{"step_id":"B","tool_id":"T024","depends_on":["A"],"inputs":{"table":{"from_step":"A","output":"table","type":"string"}},"outputs":{}}]'
    with pytest.raises(ValueError, match="incompatible"):
        _run("T093", {"steps_json": incompatible})
    duplicate_dependency = '[{"step_id":"A","tool_id":"T011","depends_on":[],"inputs":{},"outputs":{"table":"object"}},{"step_id":"B","tool_id":"T024","depends_on":["A","A"],"inputs":{},"outputs":{}}]'
    with pytest.raises(ValueError, match="more than once"):
        _run("T093", {"steps_json": duplicate_dependency})
    invalid_output_type = '[{"step_id":"A","tool_id":"T011","depends_on":[],"inputs":{},"outputs":{"table":"arbitrary"}}]'
    with pytest.raises(ValueError, match="invalid output"):
        _run("T093", {"steps_json": invalid_output_type})


def test_dispatch_rejects_guest_and_unimplemented_ids():
    with pytest.raises(PermissionError, match="Sign in"):
        execute_canonical_tool("T001", {}, _tier("T001"), "guest", {})
    with pytest.raises(ValueError, match="Unsupported"):
        execute_canonical_tool("T002", {}, _tier("T002"), "test-user", {})
