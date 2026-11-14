from __future__ import annotations

import pytest

import shoir_industrial_intelligence as ii


def _payloads():
    return {
        "mission-control": {
            "event_id": "SYN-EVT-001", "severity": 4, "urgency": 4,
            "operational_impact_score": 4, "affected_domains": ["Production", "Maintenance"],
            "evidence_refs": ["SYNTHETIC:event-001"],
        },
        "process-mining": {
            "events": [
                {"case_id": "C1", "activity": "Receive", "timestamp": "2026-10-01T08:00:00Z"},
                {"case_id": "C1", "activity": "Inspect", "timestamp": "2026-10-01T10:00:00Z", "explicit_wait_minutes": 20},
                {"case_id": "C1", "activity": "Inspect", "timestamp": "2026-10-01T10:30:00Z"},
                {"case_id": "C1", "activity": "Pack", "timestamp": "2026-10-01T11:00:00Z"},
            ],
            "approved_sequence": ["Receive", "Inspect", "Pack"],
        },
        "engineering-change": {
            "change_title": "Synthetic gasket material change",
            "source_entity_id": "MAT-01",
            "dependencies": [
                {"source_id": "MAT-01", "target_id": "PROC-01", "relation": "USED_IN"},
                {"source_id": "PROC-01", "target_id": "QC-01", "relation": "REQUIRES_INSPECTION"},
            ],
            "required_reviews": ["Process Engineering", "Quality"],
        },
        "turnaround": {
            "tasks": [
                {"task_id": "JOB-1", "duration_hours": 4, "skill": "mechanical", "dependencies": [], "permit_required": True, "permit_status": "APPROVED"},
                {"task_id": "JOB-2", "duration_hours": 3, "skill": "electrical", "dependencies": ["JOB-1"], "inspection_required": True, "inspection_status": "PASSED"},
            ],
            "resources": [{"id": "TECH-M", "skills": ["mechanical"]}, {"id": "TECH-E", "skills": ["electrical"]}],
        },
        "data-trust": {
            "measurements": [
                {"meter_id": "FM-01", "value": 100, "unit": "m3/h", "source": "meter-A", "timestamp": "2026-10-01T08:00:00Z", "provenance": "SYNTHETIC"},
                {"meter_id": "FM-01", "value": 108, "unit": "m3/h", "source": "meter-B", "timestamp": "2026-10-01T08:00:00Z", "provenance": "SYNTHETIC"},
            ],
            "balances": [{"name": "Water", "input": 100, "output": 88, "losses": 10, "unit": "m3/h", "tolerance": 1}],
        },
        "asset-reliability": {
            "assets": [
                {"asset_id": "P-01", "criticality": 5, "failure_count": 4, "downtime_hours": 20, "production_impact_score": 5},
                {"asset_id": "P-02", "criticality": 2, "failure_count": 0, "downtime_hours": 0, "production_impact_score": 1},
            ],
            "dependencies": [{"asset_id": "P-01", "affected_entity_id": "LINE-01", "impact": "PRODUCTION"}],
        },
        "yield-intelligence": {"input_units": 1000, "first_pass_good_units": 900, "rework_recovered_units": 50, "scrap_units": 30},
        "commissioning": {"required_checks": [
            {"check_id": "TEST-01", "status": "PASSED", "evidence_id": "SYNTHETIC:TEST-01"},
            {"check_id": "TEST-02", "status": "PENDING"},
        ]},
        "experimentation": {"factors": ["temperature", "speed"]},
        "procurement-assurance": {
            "requirements": [{"requirement_id": "R1", "description": "Capacity >= 10"}, {"requirement_id": "R2", "description": "Material compatibility"}],
            "offers": [{"supplier": "Vendor A", "claims": [
                {"requirement_id": "R1", "compliance": "COMPLIANT", "evidence_id": "SYNTHETIC:DATASHEET-01"},
                {"requirement_id": "R2", "compliance": "NON_COMPLIANT"},
            ]}],
        },
        "energy-flexibility": {
            "periods": [
                {"period_id": "P1", "tariff": 0.4, "capacity_kwh": 150, "base_kwh": 40},
                {"period_id": "P2", "tariff": 0.2, "capacity_kwh": 150, "base_kwh": 40},
            ],
            "loads": [{"load_id": "LOAD-01", "energy_kwh": 60, "flexible": True, "earliest_period": "P1", "latest_period": "P2"}],
        },
        "spare-parts": {
            "part_id": "BRG-01", "transfer_quantity": 3, "compatible": True,
            "source": {"on_hand": 8, "minimum_stock": 6}, "destination": {"on_hand": 1},
        },
        "ot-assurance": {
            "asset_id": "PLC-01", "approved_baseline": {"firmware": "1.0", "config_hash": "BASE"},
            "observed_configuration": {"firmware": "1.1", "config_hash": "OBSERVED"},
            "observed_provenance": "SYNTHETIC",
        },
        "batch-genealogy": {
            "lot_id": "FG-01", "direction": "backward",
            "genealogy": [
                {"parent_lot": "RM-01", "child_lot": "FG-01", "status": "CONFIRMED"},
                {"parent_lot": "RM-02", "child_lot": "FG-01", "status": "SUSPECTED"},
            ],
        },
        "shift-handover": {
            "outgoing_shift": "Shift A", "incoming_shift": "Shift B",
            "issues": [{"issue_id": "ISSUE-01", "owner": "engineer-01", "status": "OPEN", "acknowledged_by_incoming": False}],
        },
        "benchmarking": {
            "observations": [
                {"name": "Line A", "metric": "Energy intensity", "unit": "kWh/t", "period": "2026-10", "value": 120},
                {"name": "Line B", "metric": "Energy intensity", "unit": "kWh/t", "period": "2026-10", "value": 110},
            ],
        },
    }


def test_catalog_contains_all_16_tools_and_search_aliases():
    assert len(ii.TOOL_CATALOG) == 16
    assert len({tool["id"] for tool in ii.TOOL_CATALOG}) == 16
    assert sum(len(suite["tools"]) for suite in ii.SUITES) == 16
    assert len(ii.SUITES) == 6
    assert len(ii.SHARED_CAPABILITIES) == 8
    assert len(ii.INDUSTRY_TEMPLATES) == 5
    assert ii.search_tools("turnaround recovery optimizer")[0]["id"] == "turnaround"
    assert any(item["id"] == "data-trust" for item in ii.search_tools("measurement reconciliation"))


@pytest.mark.parametrize("tool_id", [tool["id"] for tool in ii.TOOL_CATALOG])
def test_each_industrial_tool_accepts_deterministic_synthetic_fixture(tool_id):
    result = ii.analyze_tool(tool_id, _payloads()[tool_id])
    assert result["tool_id"] == tool_id
    assert result["status"]
    assert result["model_version"] == "shoir-industrial-intelligence-core/1.0"
    assert len(result["input_hash"]) == 64
    assert result["calculated_at"]


def test_mission_control_priority_is_transparent_and_cause_not_confirmed():
    result = ii.analyze_tool("mission-control", _payloads()["mission-control"])
    assert result["priority"] == "CRITICAL"
    assert result["cause_status"] == "NOT_CONFIRMED"
    assert "SYNTHETIC:event-001" in result["evidence_refs"]


def test_process_mining_separates_elapsed_and_explicit_wait_and_flags_rework_candidate():
    result = ii.analyze_tool("process-mining", _payloads()["process-mining"])
    assert result["case_count"] == 1
    assert result["total_inter_event_elapsed_minutes"] == pytest.approx(180)
    assert result["explicitly_recorded_wait_minutes"] == pytest.approx(20)
    assert result["rework_candidates"] == [
        {"case_id": "C1", "activity": "Inspect", "classification": "REPEATED_ACTIVITY_CANDIDATE"}
    ]
    assert result["conformance_deviations"]


def test_engineering_change_follows_direct_and_downstream_dependencies():
    result = ii.analyze_tool("engineering-change", _payloads()["engineering-change"])
    assert [item["entity_id"] for item in result["direct_impacts"]] == ["PROC-01"]
    assert [item["entity_id"] for item in result["downstream_impacts"]] == ["QC-01"]
    assert result["approval_state"] == "PENDING_REVIEW"


def test_turnaround_scheduler_respects_dependencies_and_reports_infeasible_prerequisites():
    result = ii.analyze_tool("turnaround", _payloads()["turnaround"])
    assert result["status"] == "FEASIBLE"
    schedule = {item["task_id"]: item for item in result["scheduled_tasks"]}
    assert schedule["JOB-2"]["start_hour"] >= schedule["JOB-1"]["finish_hour"]
    assert result["makespan_hours"] == pytest.approx(7)
    blocked = _payloads()["turnaround"]
    blocked["tasks"][0]["safety_hold"] = True
    failed = ii.analyze_tool("turnaround", blocked)
    assert failed["status"] == "INFEASIBLE"
    assert any(item["task_id"] == "JOB-2" for item in failed["unscheduled_tasks"])


def test_data_trust_flags_conflict_and_never_changes_originals():
    payload = _payloads()["data-trust"]
    original = [dict(item) for item in payload["measurements"]]
    result = ii.analyze_tool("data-trust", payload)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["meter_conflicts"][0]["reason"] == "CONFLICTING_READINGS"
    assert result["original_measurements"] == original
    assert result["originals_modified"] is False
    assert result["balances"][0]["closes"] is False


def test_asset_reliability_ranks_from_input_history_without_failure_date():
    result = ii.analyze_tool("asset-reliability", _payloads()["asset-reliability"])
    assert result["assets"][0]["asset_id"] == "P-01"
    assert result["production_dependencies"][0]["affected_entity_id"] == "LINE-01"
    assert "failure date" in " ".join(result["limitations"]).casefold()


def test_yield_math_reconciles_input_good_rework_and_scrap():
    result = ii.analyze_tool("yield-intelligence", _payloads()["yield-intelligence"])
    assert result["first_pass_yield_pct"] == pytest.approx(90)
    assert result["final_yield_pct"] == pytest.approx(95)
    assert result["scrap_rate_pct"] == pytest.approx(3)
    assert result["unaccounted_units"] == pytest.approx(20)


def test_commissioning_missing_required_evidence_blocks_readiness():
    result = ii.analyze_tool("commissioning", _payloads()["commissioning"])
    assert result["status"] == "NOT_READY"
    assert result["readiness_approved"] is False
    assert result["missing_or_unverified_checks"][0]["check_id"] == "TEST-02"


def test_experiment_design_is_reproducible_and_coded_full_factorial():
    result = ii.analyze_tool("experimentation", _payloads()["experimentation"])
    assert result["run_count"] == 4
    assert {tuple(sorted(row.items())) for row in result["design"]} == {
        (("speed", -1), ("temperature", -1)),
        (("speed", 1), ("temperature", -1)),
        (("speed", -1), ("temperature", 1)),
        (("speed", 1), ("temperature", 1)),
    }
    repeated = ii.analyze_tool("experimentation", _payloads()["experimentation"])
    assert result["input_hash"] == repeated["input_hash"]


def test_procurement_assurance_keeps_unverified_and_deviation_separate():
    result = ii.analyze_tool("procurement-assurance", _payloads()["procurement-assurance"])
    supplier = result["supplier_results"][0]
    assert supplier["compliant_count"] == 1
    assert supplier["deviation_count"] == 1
    assert supplier["unverified_count"] == 0
    assert supplier["review_completeness_pct"] == pytest.approx(100)


def test_energy_flexibility_respects_capacity_and_selects_low_cost_period():
    result = ii.analyze_tool("energy-flexibility", _payloads()["energy-flexibility"])
    assert result["status"] == "FEASIBLE"
    assert result["allocations"][0]["period_id"] == "P2"
    payload = _payloads()["energy-flexibility"]
    payload["periods"][1]["capacity_kwh"] = 80
    failed = ii.analyze_tool("energy-flexibility", payload)
    assert failed["status"] == "INFEASIBLE"
    assert failed["unallocated_loads"]


def test_spare_parts_refuses_transfer_below_source_minimum():
    result = ii.analyze_tool("spare-parts", _payloads()["spare-parts"])
    assert result["status"] == "REJECTED"
    assert result["source_after_transfer"] == pytest.approx(5)
    assert any("minimum stock" in reason for reason in result["reasons"])


def test_ot_configuration_assurance_detects_passively_supplied_difference():
    result = ii.analyze_tool("ot-assurance", _payloads()["ot-assurance"])
    assert result["status"] == "INVESTIGATION_REQUIRED"
    assert result["difference_count"] == 2
    assert result["observed_provenance"] == "SYNTHETIC"
    assert any("no active discovery" in item.casefold() for item in result["limitations"])


def test_batch_genealogy_traverses_confirmed_links_and_excludes_suspected():
    result = ii.analyze_tool("batch-genealogy", _payloads()["batch-genealogy"])
    assert result["confirmed_related_lots"] == ["RM-01"]
    assert result["suspected_links_excluded"][0]["parent_lot"] == "RM-02"


def test_shift_handover_carries_open_action_and_requires_acknowledgement():
    result = ii.analyze_tool("shift-handover", _payloads()["shift-handover"])
    assert result["status"] == "ACKNOWLEDGEMENT_REQUIRED"
    assert result["handover_acknowledged"] is False
    assert result["carried_forward"][0]["issue_id"] == "ISSUE-01"


def test_benchmarking_suppresses_incompatible_comparison():
    payload = _payloads()["benchmarking"]
    payload["observations"][1]["unit"] = "MJ/t"
    result = ii.analyze_tool("benchmarking", payload)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["comparison_suppressed"] is True
    assert result["observations"] == []


def test_invalid_provenance_and_bad_inputs_are_rejected():
    with pytest.raises(ii.IndustrialIntelligenceError):
        ii.analyze_tool("yield-intelligence", {"input_units": 10, "first_pass_good_units": 8, "rework_recovered_units": 3})
    with pytest.raises(ii.IndustrialIntelligenceError):
        ii.analyze_tool("process-mining", {"events": [{"case_id": "C1", "activity": "A", "timestamp": "2026-10-01T08:00:00"}]})
    with pytest.raises(ii.IndustrialIntelligenceError):
        ii.analyze_tool("turnaround", {"tasks": [{"task_id": "A", "duration_hours": 1, "skill": "x", "dependencies": ["B"]}], "resources": [{"id": "R1", "skills": ["x"]}]})


def _configure_personal_session(monkeypatch, username="synthetic-owner", role="owner"):
    session = {
        "authenticated": True,
        "current_user": username,
        "user_role": role,
        "user_tier": "Enterprise",
    }
    monkeypatch.setattr(ii.st, "session_state", session, raising=False)
    monkeypatch.setattr("workspace_persistence.save_user_workspace", lambda _username, _state: True)
    return session


def _configure_org_session(monkeypatch, username="synthetic-owner", role="owner"):
    organization_id = "00000000-0000-4000-8000-000000000001"
    workspace_id = "00000000-0000-4000-8000-000000000002"
    session = {
        "authenticated": True,
        "current_user": username,
        "remote_session_token": "synthetic-session-token",
        "user_tier": "Enterprise",
        "shoir_active_organization_workspace": {
            "organization_id": organization_id,
            "organization_workspace_id": workspace_id,
            "display_name": "Synthetic Test Workspace",
        },
    }
    monkeypatch.setattr(ii.st, "session_state", session, raising=False)
    import durable_account_store as store
    monkeypatch.setattr(store, "validate_remote_organization_workspace_access", lambda _username: True)
    monkeypatch.setattr(
        store,
        "edge_organization_action",
        lambda _action, actor, _token, **_kwargs: {
            "organizations": [
                {"organization_id": organization_id, "role": role, "status": "active"}
            ]
        },
    )
    monkeypatch.setattr("workspace_persistence.save_user_workspace", lambda _username, _state: True)
    return session


def test_records_persist_and_create_digital_thread_lineage(monkeypatch):
    session = _configure_personal_session(monkeypatch)
    record = ii.create_record(
        "synthetic-owner", "Enterprise", "equipment_inspection", "Pump inspection",
        {"asset_id": "P-100", "result": "PASS", "thread_node_type": "Equipment"},
        provenance="SYNTHETIC",
    )
    saved = ii.list_records("synthetic-owner", "Enterprise", "equipment_inspection")
    assert saved[0]["record_id"] == record["record_id"]
    assert saved[0]["provenance"] == "SYNTHETIC"
    assert record["thread_node_id"]
    assert session["global_thread_nodes"]
    assert any(item.get("record_id") == record["record_id"] for item in session[ii.STATE_PREFIX + "records"])


def test_confirmed_relationship_requires_existing_nodes_and_evidence(monkeypatch):
    _configure_personal_session(monkeypatch)
    ii.add_entity("synthetic-owner", "Enterprise", "Asset", "ASSET-01", "Pump 01", {"tag": "P-01"})
    ii.add_entity("synthetic-owner", "Enterprise", "Process", "PROC-01", "Cooling", {"unit": "A"})
    with pytest.raises(ii.IndustrialIntelligenceError, match="evidence"):
        ii.add_relationship("synthetic-owner", "Enterprise", "ASSET-01", "PROC-01", "SERVES", "CONFIRMED", [])
    evidence = ii.create_record("synthetic-owner", "Enterprise", "evidence", "Inspection report", {"source": "synthetic fixture"}, provenance="SYNTHETIC")
    edge = ii.add_relationship("synthetic-owner", "Enterprise", "ASSET-01", "PROC-01", "SERVES", "CONFIRMED", [evidence["record_id"]])
    assert edge["status"] == "CONFIRMED"
    assert edge["evidence_refs"] == ["SYNTHETIC:relationship-test"]


def test_workspace_records_are_isolated_between_personal_accounts(monkeypatch):
    first = _configure_personal_session(monkeypatch, "synthetic-alice", "owner")
    ii.create_record("synthetic-alice", "Enterprise", "note", "Alice private", {"value": "A"})
    second = {
        "authenticated": True,
        "current_user": "synthetic-bob",
        "user_role": "owner",
        "user_tier": "Enterprise",
    }
    monkeypatch.setattr(ii.st, "session_state", second, raising=False)
    assert ii.list_records("synthetic-bob", "Enterprise") == []
    assert first[ii.STATE_PREFIX + "records"][0]["name"] == "Alice private"


def test_viewer_can_read_but_cannot_write(monkeypatch):
    _configure_personal_session(monkeypatch, "synthetic-viewer", "viewer")
    assert ii.list_records("synthetic-viewer", "Enterprise") == []
    with pytest.raises(PermissionError, match="read-only"):
        ii.create_record("synthetic-viewer", "Enterprise", "note", "Denied", {})


def test_shared_organization_role_is_revalidated_and_viewer_cannot_write(monkeypatch):
    _configure_org_session(monkeypatch, "synthetic-org-viewer", "viewer")
    access = ii._session_authorize("synthetic-org-viewer", "Enterprise", "read")
    assert access["scope"] == "ORGANIZATION"
    assert access["organization_id"].endswith("0001")
    with pytest.raises(PermissionError, match="read-only"):
        ii.create_record("synthetic-org-viewer", "Enterprise", "note", "Denied", {})


def test_organization_switch_filters_stale_in_memory_records(monkeypatch):
    session = _configure_org_session(monkeypatch, "synthetic-org-owner", "owner")
    record = ii.create_record("synthetic-org-owner", "Enterprise", "note", "Organization A confidential", {"secret_scope": "A"})
    assert ii.list_records("synthetic-org-owner", "Enterprise")[0]["record_id"] == record["record_id"]

    other_org = "00000000-0000-4000-8000-000000000099"
    other_workspace = "00000000-0000-4000-8000-000000000098"
    session["shoir_active_organization_workspace"] = {
        "organization_id": other_org,
        "organization_workspace_id": other_workspace,
        "display_name": "Synthetic Organization B",
    }
    monkeypatch.setattr(
        __import__("durable_account_store"),
        "edge_organization_action",
        lambda _action, _actor, _token, **_kwargs: {
            "organizations": [{"organization_id": other_org, "role": "owner", "status": "active"}]
        },
    )
    assert ii.list_records("synthetic-org-owner", "Enterprise") == []


def test_shared_workspace_write_fails_closed_when_managed_persistence_fails(monkeypatch):
    session = _configure_org_session(monkeypatch, "synthetic-org-engineer", "engineer")
    monkeypatch.setattr("workspace_persistence.save_user_workspace", lambda _username, _state: False)
    with pytest.raises(RuntimeError, match="did not confirm"):
        ii.create_record("synthetic-org-engineer", "Enterprise", "note", "Not saved", {})
    assert session.get(ii.STATE_PREFIX + "records", []) == []


def test_live_and_stale_records_require_source_reference_and_timestamp(monkeypatch):
    _configure_personal_session(monkeypatch)
    with pytest.raises(ii.IndustrialIntelligenceError, match="source reference"):
        ii.create_record("synthetic-owner", "Enterprise", "measurement", "Missing source", {}, provenance="LIVE")
    with pytest.raises(ii.IndustrialIntelligenceError, match="source timestamp"):
        ii.create_record("synthetic-owner", "Enterprise", "measurement", "Missing time", {}, provenance="LIVE", source_ref="DCS:FM-01")


def test_action_approval_is_independent_and_verification_follows_implementation(monkeypatch):
    session = _configure_org_session(monkeypatch, "synthetic-owner", "owner")
    action_evidence = ii.create_record(
        "synthetic-owner", "Enterprise", "evidence", "Pump inspection baseline",
        {"scope": "Synthetic maintenance request evidence"}, provenance="SYNTHETIC",
    )
    action = ii.create_action(
        "synthetic-owner", "Enterprise", "Inspect Pump 01", "synthetic-engineer",
        "2026-12-01T00:00:00Z", "HIGH", "Inspection report recorded.",
        [action_evidence["record_id"]], required_approvals=1,
    )
    with pytest.raises(PermissionError, match="cannot approve their own"):
        ii.approve_action("synthetic-owner", "Enterprise", action["action_id"])
    with pytest.raises(PermissionError, match="Use approve_action"):
        ii.update_action("synthetic-owner", "Enterprise", action["action_id"], "APPROVED")

    session["current_user"] = "synthetic-approver"
    monkeypatch.setattr(
        __import__("durable_account_store"),
        "edge_organization_action",
        lambda _action, _actor, _token, **_kwargs: {
            "organizations": [{
                "organization_id": "00000000-0000-4000-8000-000000000001",
                "role": "approver", "status": "active",
            }]
        },
    )
    approved = ii.approve_action("synthetic-approver", "Enterprise", action["action_id"], "Approved for inspection only.")
    assert approved["status"] == "APPROVED"
    with pytest.raises(PermissionError, match="must be recorded as IMPLEMENTED"):
        ii.update_action("synthetic-approver", "Enterprise", action["action_id"], "VERIFIED", "Done", ["SYNTHETIC:verification"])
    ii.update_action("synthetic-approver", "Enterprise", action["action_id"], "IN_PROGRESS")
    ii.update_action("synthetic-approver", "Enterprise", action["action_id"], "IMPLEMENTED", "Inspection executed")
    verification_evidence = ii.create_record("synthetic-approver", "Enterprise", "evidence", "Independent inspection verification", {"result": "PASS"}, provenance="SYNTHETIC")
    verified = ii.update_action("synthetic-approver", "Enterprise", action["action_id"], "VERIFIED", "Inspection passed", [verification_evidence["record_id"]])
    assert verified["status"] == "VERIFIED"
    assert verified["verification"]["verifier"] == "synthetic-approver"


def test_model_validation_uses_actual_expected_values_and_independent_reviewer(monkeypatch):
    session = _configure_org_session(monkeypatch, "synthetic-model-author", "owner")
    failed = ii.register_model_version(
        "synthetic-model-author", "Enterprise", "Yield model", "1.0", "calculation",
        {"formula": "good/input"}, ["same input units"], [
            {"test_id": "golden-bad", "expected": 100, "actual": 90, "passed": True}
        ],
    )
    assert failed["passed_test_count"] == 0
    with pytest.raises(ii.IndustrialIntelligenceError, match="all registered test cases pass"):
        ii.validate_model_version("synthetic-model-author", "Enterprise", failed["model_id"])

    good = ii.register_model_version(
        "synthetic-model-author", "Enterprise", "Yield model", "1.1", "calculation",
        {"formula": "good/input"}, ["same input units"], [
            {"test_id": "golden-good", "expected": 95.0, "actual": 95.0, "passed": False}
        ],
    )
    assert good["passed_test_count"] == 1
    session["current_user"] = "synthetic-model-approver"
    monkeypatch.setattr(
        __import__("durable_account_store"),
        "edge_organization_action",
        lambda _action, _actor, _token, **_kwargs: {
            "organizations": [{
                "organization_id": "00000000-0000-4000-8000-000000000001",
                "role": "approver", "status": "active",
            }]
        },
    )
    validated = ii.validate_model_version("synthetic-model-approver", "Enterprise", good["model_id"])
    assert validated["status"] == "VALIDATED_BY_REVIEWER"


def test_event_to_action_to_approval_to_verified_outcome_stays_linked(monkeypatch):
    session = _configure_org_session(monkeypatch, "synthetic-ops-owner", "owner")
    asset = ii.add_entity("synthetic-ops-owner", "Enterprise", "Equipment", "PUMP-OPS-01", "Cooling Pump", {"line": "LINE-01"}, "SYNTHETIC")
    line = ii.add_entity("synthetic-ops-owner", "Enterprise", "ProductionLine", "LINE-01", "Cooling Line", {"facility": "SITE-01"}, "SYNTHETIC")
    relation_evidence = ii.create_record("synthetic-ops-owner", "Enterprise", "evidence", "Asset map", {"source": "synthetic fixture"}, provenance="SYNTHETIC")
    ii.add_relationship("synthetic-ops-owner", "Enterprise", "PUMP-OPS-01", "LINE-01", "SUPPLIES_COOLING_TO", "CONFIRMED", [relation_evidence["record_id"]])
    event = ii.create_operational_event(
        "synthetic-ops-owner", "Enterprise", "UNPLANNED_DOWNTIME",
        "Synthetic pump trip; production line stopped.", "PUMP-OPS-01",
        "2026-10-15T08:00:00Z", "SYNTHETIC", [relation_evidence["record_id"]],
    )
    action = ii.create_action(
        "synthetic-ops-owner", "Enterprise", "Inspect cooling pump",
        "synthetic-maintenance-engineer", "2026-12-02T00:00:00Z",
        "HIGH", "Inspection and corrective work completed.",
        [relation_evidence["record_id"]],
    )
    assert event["record_id"]
    assert action["status"] == "PROPOSED"

    session["current_user"] = "synthetic-ops-approver"
    monkeypatch.setattr(
        __import__("durable_account_store"),
        "edge_organization_action",
        lambda _action, _actor, _token, **_kwargs: {
            "organizations": [{
                "organization_id": "00000000-0000-4000-8000-000000000001",
                "role": "approver", "status": "active",
            }]
        },
    )
    approved = ii.approve_action("synthetic-ops-approver", "Enterprise", action["action_id"], "Approved for controlled inspection.")
    assert approved["status"] == "APPROVED"
    ii.update_action("synthetic-ops-approver", "Enterprise", action["action_id"], "IN_PROGRESS")
    ii.update_action("synthetic-ops-approver", "Enterprise", action["action_id"], "IMPLEMENTED", "Inspection completed.")
    verification = ii.create_record(
        "synthetic-ops-approver", "Enterprise", "evidence",
        "Post-action inspection results", {"result": "PASS", "event_reference": event["record_id"]},
        provenance="SYNTHETIC",
    )
    verified = ii.update_action(
        "synthetic-ops-approver", "Enterprise", action["action_id"],
        "VERIFIED", "Post-action check passed.", [verification["record_id"]],
    )
    assert verified["status"] == "VERIFIED"
    assert asset["thread_node_id"] and line["thread_node_id"]
    assert any(item.get("record_id") == event["record_id"] for item in ii.list_records("synthetic-ops-approver", "Enterprise"))
    assert any(item.get("action_id") == action["action_id"] for item in ii._state_list("actions"))


def test_actual_benefit_requires_independent_reviewer_and_evidence(monkeypatch):
    session = _configure_org_session(monkeypatch, "synthetic-benefit-author", "owner")
    record = ii.record_benefit(
        "synthetic-benefit-author", "Enterprise", "Pump efficiency project",
        "kWh per m3", 1.2, 1.1, "kWh/m3", ["SYNTHETIC:actual-meter-data"],
    )
    assert record["payload"]["benefit_status"] == "ACTUAL_RECORDED_UNVERIFIED"
    with pytest.raises(PermissionError, match="cannot independently verify"):
        ii.verify_benefit_record("synthetic-benefit-author", "Enterprise", record["record_id"], ["SYNTHETIC:actual-meter-data"])
    session["current_user"] = "synthetic-benefit-approver"
    monkeypatch.setattr(
        __import__("durable_account_store"),
        "edge_organization_action",
        lambda _action, _actor, _token, **_kwargs: {
            "organizations": [{
                "organization_id": "00000000-0000-4000-8000-000000000001",
                "role": "approver", "status": "active",
            }]
        },
    )
    verification_evidence = ii.create_record("synthetic-benefit-approver", "Enterprise", "evidence", "Independent meter review", {"review": "synthetic independent review"}, provenance="SYNTHETIC")
    review = ii.verify_benefit_record("synthetic-benefit-approver", "Enterprise", record["record_id"], [verification_evidence["record_id"]])
    assert review["status"] == "VERIFIED_BY_INDEPENDENT_REVIEWER"


def test_cause_effect_candidates_require_separate_independent_review_to_confirm(monkeypatch):
    session = _configure_org_session(monkeypatch, "synthetic-cause-author", "owner")
    record = ii.record_cause_effect_investigation(
        "synthetic-cause-author", "Enterprise", "Yield variation investigation",
        ["Yield decreased after a material batch change."],
        [{"from": "material lot", "to": "yield variation", "supporting_evidence": [], "contradicting_evidence": [], "validation_status": "SUSPECTED"}],
    )
    assert record["payload"]["causal_claim"] == "UNCONFIRMED_UNLESS_INDIVIDUALLY_REVIEWED"
    assert record["payload"]["candidate_relationships"][0]["validation_status"] == "SUSPECTED"
    with pytest.raises(ii.IndustrialIntelligenceError, match="SUSPECTED or SUPPORTED"):
        ii.record_cause_effect_investigation(
            "synthetic-cause-author", "Enterprise", "Invalid self-confirmed investigation",
            ["Observation"], [{"from": "A", "to": "B", "supporting_evidence": ["any-string"], "validation_status": "CONFIRMED"}],
        )
    session["current_user"] = "synthetic-cause-approver"
    monkeypatch.setattr(
        __import__("durable_account_store"),
        "edge_organization_action",
        lambda _action, _actor, _token, **_kwargs: {
            "organizations": [{
                "organization_id": "00000000-0000-4000-8000-000000000001",
                "role": "approver", "status": "active",
            }]
        },
    )
    evidence = ii.create_record("synthetic-cause-approver", "Enterprise", "evidence", "Causal review source", {"review": "synthetic independent evidence"}, provenance="SYNTHETIC")
    review = ii.review_cause_effect_investigation(
        "synthetic-cause-approver", "Enterprise", record["record_id"], 0,
        "CONFIRMED", [evidence["record_id"]], "Reviewed supporting and counter-evidence.",
    )
    assert review["decision"] == "CONFIRMED"
    assert review["review_record"]["payload"]["confirmation_scope"] == "THIS_REVIEWED_RELATIONSHIP_ONLY"


def test_copilot_retrieves_authorized_records_with_citations(monkeypatch):
    _configure_personal_session(monkeypatch)
    record = ii.create_record("synthetic-owner", "Enterprise", "maintenance_event", "Pump bearing vibration", {"asset": "P-01"}, provenance="SYNTHETIC")
    result = ii.copilot_evidence_context("synthetic-owner", "Enterprise", "pump bearing")
    assert result["status"] == "EVIDENCE_RETRIEVED"
    assert result["citations"][0]["citation_id"] == record["record_id"]
    assert "not an AI-generated" in result["answer_boundary"]


def test_risk_barrier_effectiveness_requires_independent_review(monkeypatch):
    session = _configure_org_session(monkeypatch, "synthetic-risk-author", "owner")
    evidence = ii.create_record("synthetic-risk-author", "Enterprise", "evidence", "Barrier inspection", {"inspection": "synthetic passed"}, provenance="SYNTHETIC")
    record = ii.record_risk_barrier(
        "synthetic-risk-author", "Enterprise", "Synthetic pressure excursion", 4, 3,
        [{"barrier_id": "B-01", "owner": "synthetic-engineer", "evidence_id": evidence["record_id"], "status": "EFFECTIVE"}],
    )
    assert record["payload"]["formal_safety_approval"] is False
    assert record["payload"]["barriers"][0]["counts_as_effective"] is False
    assert record["payload"]["residual_screening_score"] == pytest.approx(12)
    session["current_user"] = "synthetic-risk-approver"
    monkeypatch.setattr(
        __import__("durable_account_store"),
        "edge_organization_action",
        lambda _action, _actor, _token, **_kwargs: {
            "organizations": [{
                "organization_id": "00000000-0000-4000-8000-000000000001",
                "role": "approver", "status": "active",
            }]
        },
    )
    review_evidence = ii.create_record("synthetic-risk-approver", "Enterprise", "evidence", "Independent barrier reinspection", {"result": "synthetic verification"}, provenance="SYNTHETIC")
    review = ii.review_barrier_effectiveness(
        "synthetic-risk-approver", "Enterprise", record["record_id"], "B-01",
        "VERIFIED_EFFECTIVE", review_evidence["record_id"], "Independent check passed.",
    )
    assert review["residual_screening_score"] == pytest.approx(4.8)
    assert review["formal_safety_approval"] is False



def test_analysis_handoff_adds_sheet_and_preserves_existing_workbook(monkeypatch):
    import pandas as pd
    session = _configure_personal_session(monkeypatch, "synthetic-workbook-user", "owner")
    session["industrial_workbook"] = {"Existing Data": pd.DataFrame({"Value": [1, 2]})}
    session["industrial_workbook_formulas"] = {"Existing Data": {}}
    result = ii.analyze_tool("yield-intelligence", _payloads()["yield-intelligence"])
    handoff = ii.send_analysis_to_workbook(
        "synthetic-workbook-user", "Enterprise", "yield-intelligence",
        _payloads()["yield-intelligence"], result, "SYNTHETIC",
    )
    workbook = session["industrial_workbook"]
    assert "Existing Data" in workbook
    assert workbook["Existing Data"]["Value"].tolist() == [1, 2]
    assert handoff["workbook_sheet"] in workbook
    sheet = workbook[handoff["workbook_sheet"]]
    assert {"Input", "Result", "Governance"}.issubset(set(sheet["Section"]))
    assert handoff["record_id"]
    assert handoff["workbook_sheet"] in session["industrial_workbook_formulas"]


def test_analysis_handoff_initializes_standard_workbook_tabs_without_removing_tabs(monkeypatch):
    session = _configure_personal_session(monkeypatch, "synthetic-new-workbook-user", "owner")
    result = ii.analyze_tool("mission-control", _payloads()["mission-control"])
    handoff = ii.send_analysis_to_workbook(
        "synthetic-new-workbook-user", "Enterprise", "mission-control",
        _payloads()["mission-control"], result, "SYNTHETIC",
    )
    expected = {
        "Inputs", "Data", "Calculations", "KPIs", "Simulation",
        "Optimization", "Scenarios", "Decisions", "Dashboard",
    }
    assert expected.issubset(set(session["industrial_workbook"]))
    assert handoff["workbook_sheet"] in session["industrial_workbook"]
    assert session["industrial_workbook"][handoff["workbook_sheet"]]["Field"].str.contains("input_units|event_id", regex=True).any()
