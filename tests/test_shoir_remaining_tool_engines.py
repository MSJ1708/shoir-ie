from __future__ import annotations

import io
import json

import pandas as pd
import pytest

from shoir_remaining_tool_engines import (
    calibrate_digital_twin,
    capa_lifecycle_review,
    dataset_version_lineage,
    evaluate_kpi_alerts,
    get_tool_example_json,
    governance_recovery_action,
    identity_audit_configuration_status,
    integration_configuration_status,
    recovery_action,
    run_additional_tool,
    simulate_industrial_disruptions,
    supply_chain_network_plan,
    validate_api_plugin_manifests,
)


def test_recovery_snapshot_undo_redo_and_integrity():
    first = recovery_action({"action": "snapshot", "history": [], "state": {"value": 1}})
    second = recovery_action({
        "action": "snapshot",
        "history": first["history"],
        "current_index": 0,
        "state": {"value": 2},
    })
    assert second["current_state"] == {"value": 2}
    undone = recovery_action({"action": "undo", "history": second["history"], "current_index": 1})
    assert undone["current_state"] == {"value": 1}
    redone = recovery_action({"action": "redo", "history": second["history"], "current_index": 0})
    assert redone["current_state"] == {"value": 2}
    tampered = json.loads(json.dumps(second["history"]))
    tampered[0]["state"]["value"] = 999
    with pytest.raises(ValueError, match="integrity"):
        recovery_action({"action": "undo", "history": tampered, "current_index": 1})


def test_recovery_refuses_undo_before_first_revision():
    first = recovery_action({"action": "snapshot", "history": [], "state": {"x": 1}})
    with pytest.raises(ValueError, match="earliest revision"):
        recovery_action({"action": "undo", "history": first["history"], "current_index": 0})


def test_dataset_lineage_hashes_schema_and_marks_stale_runs():
    first = dataset_version_lineage({
        "dataset_name": "sample",
        "source": "synthetic_fixture",
        "records": [{"qty": 2}, {"qty": 3}],
        "transformations": ["initial"],
        "history": [],
        "downstream_runs": [],
        "provenance": "SYNTHETIC_EXAMPLE",
    })
    assert first["version"]["content_sha256"]
    assert first["version"]["record_count"] == 2
    changed = dataset_version_lineage({
        "dataset_name": "sample",
        "source": "synthetic_fixture",
        "records": [{"qty": 2}, {"qty": 4}],
        "transformations": ["initial"],
        "history": first["history"],
        "downstream_runs": [{"run_id": "run-old", "dataset_sha256": first["version"]["content_sha256"], "dataset_version_id": first["version"]["version_id"]}],
    })
    assert changed["stale_run_count"] == 1
    assert changed["stale_downstream_runs"][0]["run_id"] == "run-old"
    unchanged = dataset_version_lineage({
        "dataset_name": "sample", "source": "synthetic_fixture",
        "records": [{"qty": 2}, {"qty": 3}], "transformations": ["initial"],
        "history": first["history"],
        "downstream_runs": [{"run_id": "run-same-data", "dataset_sha256": first["version"]["content_sha256"], "dataset_version_id": first["version"]["version_id"]}],
    })
    assert unchanged["stale_run_count"] == 0


def _complete_capa(status="OPEN"):
    return {
        "capa_id": "CAPA-1",
        "title": "Synthetic pump seal issue",
        "status": status,
        "team": "Synthetic team",
        "problem_statement": "Illustrative repeated seal defect",
        "containment_action": "Quarantine sample lot",
        "root_cause": "Pending independent investigation",
        "corrective_action": "Replace sample seals",
        "implementation_evidence": "SYNTHETIC-WO-1",
        "preventive_action": "Add incoming check",
        "closure_review": "Pending review",
        "effectiveness_evidence": "",
        "owner": "Example owner",
        "reviewer": "",
        "approval_reference": "",
        "evidence_reference": "SYNTHETIC-REF-1",
        "opened_date": "2026-10-01",
        "due_date": "2026-11-01",
    }


def test_capa_transition_audit_and_evidence_requirements():
    out = capa_lifecycle_review({
        "records": [_complete_capa()],
        "as_of_date": "2026-10-26",
        "transitions": [{
            "capa_id": "CAPA-1",
            "to_status": "IN_PROGRESS",
            "reviewer": "reviewer-1",
            "reason": "Containment accepted for further review",
            "transitioned_at": "2026-10-26T12:00:00Z",
        }],
    })
    assert out["transition_count"] == 1
    assert out["transition_audit"][0]["from_status"] == "OPEN"
    assert out["records"].iloc[0]["Status"] == "IN_PROGRESS"
    with pytest.raises(ValueError, match="cannot be closed"):
        capa_lifecycle_review({
            "records": [_complete_capa("IN_PROGRESS")],
            "transitions": [{
                "capa_id": "CAPA-1", "to_status": "CLOSED",
                "reviewer": "reviewer-1", "reason": "attempt close without evidence",
            }],
        })


def test_supply_chain_network_optimizes_and_reports_shortages():
    out = supply_chain_network_plan({
        "suppliers": [{"id": "S1", "supply": 70}, {"id": "S2", "supply": 30}],
        "customers": [{"id": "C1", "demand": 60}, {"id": "C2", "demand": 50}],
        "routes": [
            {"supplier": "S1", "customer": "C1", "capacity": 70, "unit_cost": 1},
            {"supplier": "S1", "customer": "C2", "capacity": 30, "unit_cost": 5},
            {"supplier": "S2", "customer": "C1", "capacity": 30, "unit_cost": 2},
            {"supplier": "S2", "customer": "C2", "capacity": 30, "unit_cost": 1},
        ],
    })
    assert out["solver_status"] == "OPTIMAL"
    assert out["units_shipped"] == pytest.approx(100)
    assert out["units_short"] == pytest.approx(10)
    assert 0 <= out["fill_rate_pct"] <= 100


def test_supply_chain_rejects_unknown_route_nodes():
    with pytest.raises(ValueError, match="unknown supplier/customer"):
        supply_chain_network_plan({
            "suppliers": [{"id": "S1", "supply": 10}],
            "customers": [{"id": "C1", "demand": 10}],
            "routes": [{"supplier": "MISSING", "customer": "C1", "capacity": 10, "unit_cost": 1}],
        })
    with pytest.raises(ValueError, match="Duplicate route"):
        supply_chain_network_plan({
            "suppliers": [{"id": "S1", "supply": 10}],
            "customers": [{"id": "C1", "demand": 10}],
            "routes": [
                {"supplier": "S1", "customer": "C1", "capacity": 10, "unit_cost": 1},
                {"supplier": "S1", "customer": "C1", "capacity": 10, "unit_cost": 1},
            ],
        })


def test_digital_twin_calibration_returns_fit_and_residuals():
    out = calibrate_digital_twin({
        "simulated_values": [1, 2, 3, 4, 5],
        "measured_values": [3, 5, 7, 9, 11],
        "scale_bounds": [0, 5],
        "offset_bounds": [-20, 20],
        "data_provenance": "SYNTHETIC_EXAMPLE",
    })
    assert out["scale"] == pytest.approx(2, abs=1e-6)
    assert out["offset"] == pytest.approx(1, abs=1e-6)
    assert out["rmse"] < 1e-6
    assert len(out["fit_data"]) == 5
    assert "not calibration of a physical" in out["warning"]


def test_digital_twin_calibration_rejects_constant_input():
    with pytest.raises(ValueError, match="must vary"):
        calibrate_digital_twin({"simulated_values": [1, 1, 1], "measured_values": [1, 2, 3]})
    with pytest.raises(ValueError, match="strictly below"):
        calibrate_digital_twin({"simulated_values": [1, 2, 3], "measured_values": [2, 4, 6], "scale_bounds": [1, 1], "offset_bounds": [-1, 1]})


def test_disruption_scenario_math_and_baseline_comparison():
    out = simulate_industrial_disruptions({
        "baseline_capacity": 100,
        "baseline_demand": 90,
        "unit_cost": 10,
        "baseline_lead_time_hours": 24,
        "scenarios": [
            {"scenario": "outage", "capacity_loss_pct": 50, "demand_change_pct": 0, "lead_time_multiplier": 2},
        ],
    })
    assert out["scenario_count"] == 1
    baseline, outage = out["results"].iloc[0], out["results"].iloc[1]
    assert baseline["shortage_units"] == pytest.approx(0)
    assert outage["shortage_units"] == pytest.approx(40)
    assert outage["lead_time_hours"] == pytest.approx(48)


def test_kpi_alert_evaluation_handles_threshold_freshness_and_dedupe():
    out = evaluate_kpi_alerts({
        "as_of": "2026-10-26T12:00:00Z",
        "kpis": [
            {"name": "scrap", "value": 4, "threshold": 3, "operator": "gt", "measured_at": "2026-10-26T11:00:00Z", "max_age_minutes": 120, "unit": "%"},
            {"name": "output", "value": 70, "threshold": 80, "operator": "lt", "measured_at": "2026-10-20T11:00:00Z", "max_age_minutes": 120, "unit": "units"},
        ],
        "existing_alerts": [],
    })
    assert out["kpi_count"] == 2
    assert out["stale_kpi_count"] == 1
    assert out["breached_kpi_count"] == 1
    assert out["new_alert_count"] == 1
    fp = out["alert_records"][0]["fingerprint"]
    again = evaluate_kpi_alerts({
        "as_of": "2026-10-26T12:00:00Z",
        "kpis": [{"name": "scrap", "value": 4, "threshold": 3, "operator": "gt", "measured_at": "2026-10-26T11:00:00Z", "max_age_minutes": 120}],
        "existing_alerts": [{"fingerprint": fp, "state": "OPEN"}],
    })
    assert again["new_alert_count"] == 0


def test_kpi_alert_adapter_keeps_existing_breach_open_until_fresh_recovery():
    initial = evaluate_kpi_alerts({
        "as_of": "2026-11-20T10:01:00Z",
        "kpis": [{
            "name": "Scrap Rate",
            "value": 4.2,
            "threshold": 3.0,
            "operator": "gt",
            "measured_at": "2026-11-20T10:00:00Z",
            "max_age_minutes": 120,
            "rule_id": "scrap-high",
            "severity": "HIGH",
        }],
        "existing_alerts": [],
    })
    assert initial["new_alert_count"] == 1
    prior = initial["alert_records"]

    stale = evaluate_kpi_alerts({
        "as_of": "2026-11-20T12:30:00Z",
        "kpis": [{
            "name": "Scrap Rate",
            "value": 2.0,
            "threshold": 3.0,
            "operator": "gt",
            "measured_at": "2026-11-20T09:00:00Z",
            "max_age_minutes": 120,
            "rule_id": "scrap-high",
            "severity": "HIGH",
        }],
        "existing_alerts": prior,
    })
    assert stale["resolved_alert_count"] == 0
    assert stale["open_alert_count"] == 1
    assert stale["unverified_open_alert_count"] == 1
    assert stale["alert_records"][0]["state"] == "OPEN_UNVERIFIED"
    assert stale["alerts"].iloc[0]["Event"] == "UNVERIFIED"

    recovered = evaluate_kpi_alerts({
        "as_of": "2026-11-20T12:31:00Z",
        "kpis": [{
            "name": "Scrap Rate",
            "value": 2.0,
            "threshold": 3.0,
            "operator": "gt",
            "measured_at": "2026-11-20T12:30:00Z",
            "max_age_minutes": 120,
            "rule_id": "scrap-high",
            "severity": "HIGH",
        }],
        "existing_alerts": stale["alert_records"],
    })
    assert recovered["resolved_alert_count"] == 1
    assert recovered["open_alert_count"] == 0
    assert recovered["alert_records"] == []


def test_kpi_alert_adapter_preserves_per_record_maximum_age_and_user_provenance():
    out = evaluate_kpi_alerts({
        "as_of": "2026-11-20T12:00:00Z",
        "kpis": [
            {"name": "Fresh", "value": 10, "threshold": 5, "operator": "gt",
             "measured_at": "2026-11-20T11:59:00Z", "max_age_minutes": 5},
            {"name": "Stale", "value": 10, "threshold": 5, "operator": "gt",
             "measured_at": "2026-11-20T11:50:00Z", "max_age_minutes": 5},
        ],
        "existing_alerts": [],
    })
    assert out["data_provenance"] == "USER_ENTERED_UNVERIFIED"
    states = out["kpis"].set_index("kpi")["status"].to_dict()
    assert states == {"Fresh": "OPEN", "Stale": "STALE_DATA"}
    assert out["new_alert_count"] == 1
    assert out["stale_kpi_count"] == 1


def test_kpi_alert_evaluation_blocks_future_dated_measurements():
    out = evaluate_kpi_alerts({
        "as_of": "2026-10-26T12:00:00Z",
        "kpis": [{
            "name": "future-scrap",
            "value": 9,
            "threshold": 3,
            "operator": "gt",
            "measured_at": "2026-10-26T12:30:00Z",
            "max_age_minutes": 120,
            "rule_id": "future-scrap-high",
            "severity": "CRITICAL",
            "source": "SYNTHETIC acceptance fixture",
        }],
        "existing_alerts": [],
    })
    row = out["kpis"].iloc[0]
    assert row["status"] == "FUTURE_TIMESTAMP"
    assert row["freshness"] == "FUTURE"
    assert row["minutes_until_observation"] == pytest.approx(30.0)
    assert out["future_kpi_count"] == 1
    assert out["stale_kpi_count"] == 0
    assert out["breached_kpi_count"] == 0
    assert out["open_alert_count"] == 0
    assert out["new_alert_count"] == 0
    assert out["alert_records"] == []


def test_kpi_alert_evaluation_accepts_measurement_exactly_at_as_of_boundary():
    out = evaluate_kpi_alerts({
        "as_of": "2026-10-26T12:00:00Z",
        "kpis": [{
            "name": "boundary-scrap",
            "value": 4,
            "threshold": 3,
            "operator": "gt",
            "measured_at": "2026-10-26T12:00:00Z",
            "max_age_minutes": 0,
            "rule_id": "boundary-scrap-high",
        }],
        "existing_alerts": [],
    })
    assert out["future_kpi_count"] == 0
    assert out["breached_kpi_count"] == 1
    assert out["new_alert_count"] == 1
    assert out["alert_records"][0]["new_alert"] is True


def test_integration_status_checks_env_presence_without_returning_secret(monkeypatch):
    monkeypatch.setenv("SHOIR_CONNECTOR_PLANT_ENDPOINT", "https://plant.example.test/api")
    monkeypatch.setenv("SHOIR_CONNECTOR_PLANT_TOKEN", "never-return-this-secret")
    out = integration_configuration_status({
        "profiles": [{
            "name": "Plant API", "protocol": "REST",
            "endpoint_env": "SHOIR_CONNECTOR_PLANT_ENDPOINT",
            "credential_env": "SHOIR_CONNECTOR_PLANT_TOKEN",
        }],
    })
    row = out["profile_records"][0]
    assert row["status"] == "READY_FOR_AUTHORIZED_STAGING_TEST"
    assert row["endpoint_configured"] and row["credential_configured"]
    assert "never-return-this-secret" not in json.dumps({"status": out["status"], "profile_records": out["profile_records"]})


def test_integration_status_refuses_invalid_env_names():
    with pytest.raises(ValueError, match="must use a SHOIR_CONNECTOR"):
        integration_configuration_status({
            "profiles": [{
                "name": "bad", "protocol": "REST",
                "endpoint_env": "HOME", "credential_env": "PASSWORD",
            }],
        })


def test_plugin_manifest_validated_but_never_enabled():
    base = {
        "id": "safe-plugin",
        "name": "Safe plugin manifest",
        "version": "1.0.0",
        "api_version": "v1",
        "minimum_tier": "Enterprise",
        "scopes": ["read", "export"],
        "entrypoint": "plugins/safe_plugin.py",
        "request_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
        "response_schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
        "enabled": False,
    }
    out = validate_api_plugin_manifests({"plugins": [base, {**base, "id": "enabled-plugin", "enabled": True}]})
    assert out["valid_count"] == 1
    assert out["blocked_count"] == 1
    assert out["plugin_records"][0]["executable"] is False
    assert out["plugin_records"][1]["validation_status"] == "BLOCKED_INVALID_MANIFEST"


def test_identity_config_inspects_nested_streamlit_auth_without_claiming_sso_active():
    auth = {
        "redirect_uri": "https://staging.example.test/oauth2callback",
        "cookie_secret": "x" * 48,
        "expose_tokens": "id",
        "enterprise": {
            "client_id": "shoir-staging",
            "client_secret": "do-not-return",
            "server_metadata_url": "https://idp.example.test/.well-known/openid-configuration",
        },
    }
    out = identity_audit_configuration_status({"auth": auth})
    assert out["status"] == "STREAMLIT_CONFIGURATION_READY_EDGE_SETTINGS_UNVERIFIED"
    assert out["streamlit_configuration_ready"] is True
    assert out["edge_configuration_visibility"] == "NOT_INSPECTABLE_FROM_STREAMLIT"
    assert out["oidc_login_flow_implemented"] is True
    assert out["sso_active"] is False
    assert out["mfa_active"] is False
    assert out["provider_authentication_tested"] is False
    assert out["provider_mfa_evidence_verified"] is False
    assert out["audit_sink_configured"] is False
    assert out["audit_persistence_verified"] is False
    assert out["verified_at"] is None
    assert "SHOIR_OIDC_ISSUER" in out["expected_edge_secret_names"]
    assert all(row["value_exposed"] is False for row in out["environment_variables"].to_dict("records"))
    assert "do-not-return" not in json.dumps({key: value for key, value in out.items() if key != "environment_variables"})


def test_identity_config_rejects_private_ip_metadata_endpoint():
    out = identity_audit_configuration_status({
        "auth": {
            "redirect_uri": "https://staging.example.test/oauth2callback",
            "cookie_secret": "x" * 48,
            "expose_tokens": "id",
            "enterprise": {
                "client_id": "shoir-staging",
                "client_secret": "do-not-return",
                "server_metadata_url": "https://192.168.1.20/.well-known/openid-configuration",
            },
        }
    })
    assert out["status"] == "CONFIGURATION_INVALID"
    assert out["streamlit_configuration_ready"] is False
    assert out["oidc_issuer_syntax_valid"] is None
    assert not out["provider_metadata_url_syntax_valid"]
    assert any("server_metadata_url" in item for item in out["configuration_problems"])
    assert "do-not-return" not in json.dumps({key: value for key, value in out.items() if key != "environment_variables"})


def test_identity_config_fails_closed_when_provider_is_missing():
    out = identity_audit_configuration_status({"auth": {}})
    assert out["status"] == "NOT_CONFIGURED"
    assert out["sso_active"] is False
    assert len(out["missing_settings"]) >= 6
    assert out["edge_configuration_visibility"] == "NOT_INSPECTABLE_FROM_STREAMLIT"


def test_identity_config_rejects_invalid_nested_streamlit_auth_settings():
    out = identity_audit_configuration_status({
        "auth": {
            "redirect_uri": "http://staging.example.test/oauth2callback",
            "cookie_secret": "too-short",
            "expose_tokens": "access",
            "enterprise": {
                "client_id": "shoir-staging",
                "client_secret": "do-not-return",
                "server_metadata_url": "http://idp.example.test/.well-known/openid-configuration",
            },
        }
    })
    assert out["status"] == "CONFIGURATION_INVALID"
    assert out["streamlit_configuration_ready"] is False
    assert not out["redirect_uri_syntax_valid"]
    assert out["oidc_issuer_syntax_valid"] is None
    assert not out["provider_metadata_url_syntax_valid"]
    assert len(out["configuration_problems"]) >= 3
    assert "do-not-return" not in json.dumps({key: value for key, value in out.items() if key != "environment_variables"})


def test_governance_snapshot_checksum_verify_and_tamper_detection():
    created = governance_recovery_action({
        "action": "create_snapshot",
        "workspace_reference": "synthetic-workspace",
        "content": {"dataset": [{"x": 1}], "label": "SYNTHETIC"},
    })
    verified = governance_recovery_action({"action": "verify_snapshot", "snapshot": created["snapshot"]})
    assert verified["checksum_verified"] is True
    tampered = json.loads(json.dumps(created["snapshot"]))
    tampered["content"]["label"] = "ALTERED"
    failed = governance_recovery_action({"action": "verify_snapshot", "snapshot": tampered})
    assert failed["checksum_verified"] is False
    assert failed["content"] is None


def test_governance_retention_and_delete_plans_do_not_delete_data():
    retention = governance_recovery_action({
        "action": "retention_review",
        "policies": [{"category": "audit", "retention_days": 365, "legal_hold": True}],
    })
    assert retention["policy_records"][0]["action"] == "HOLD_FOR_REVIEW"
    assert retention["policy_records"][0]["delete_executed"] is False
    deletion = governance_recovery_action({
        "action": "deletion_plan",
        "request_reference": "REQ-SYN-1",
        "categories": ["workspace exports", "backups"],
    })
    assert deletion["delete_executed"] is False
    assert "backups" in deletion["systems_to_review"]
    with pytest.raises(ValueError, match="whole number"):
        governance_recovery_action({
            "action": "retention_review",
            "policies": [{"category": "audit", "retention_days": 3.5, "legal_hold": False}],
        })


def test_all_target_examples_are_valid_json():
    for tool_id in ("T004", "T005", "T006", "T039", "T060", "T061", "T067", "T068", "T073", "T074", "T080", "T086", "T092", "T094", "T096", "T097", "T098", "T099"):
        value = json.loads(get_tool_example_json(tool_id))
        assert isinstance(value, dict)
        out = run_additional_tool(tool_id, value)
        assert out["tool_id"] == tool_id

def test_identity_config_ignores_obsolete_flat_environment_contract(monkeypatch):
    # The application reads Streamlit's nested [auth] settings. Legacy flat
    # variables and client-secret values must never be used as a substitute.
    values = {
        "SHOIR_OIDC_ISSUER_URL": "http://legacy-idp.example.test",
        "SHOIR_OIDC_CLIENT_ID": "legacy-client",
        "SHOIR_OIDC_CLIENT_SECRET": "do-not-return",
        "SHOIR_OIDC_REDIRECT_URI": "https://legacy.example.test/auth/callback",
        "SHOIR_OIDC_SCOPES": "profile email",
        "SHOIR_MFA_ENFORCED": "true",
        "SHOIR_AUDIT_LOG_ENABLED": "true",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)

    out = identity_audit_configuration_status({
        "auth": {
            "redirect_uri": "https://staging.example.test/oauth2callback",
            "cookie_secret": "x" * 48,
            "expose_tokens": "id",
            "enterprise": {
                "client_id": "shoir-staging",
                "client_secret": "streamlit-secret-not-returned",
                "server_metadata_url": "https://idp.example.test/.well-known/openid-configuration",
            },
        }
    })
    assert out["status"] == "STREAMLIT_CONFIGURATION_READY_EDGE_SETTINGS_UNVERIFIED"
    assert out["streamlit_configuration_ready"] is True
    assert out["sso_active"] is False
    assert out["mfa_active"] is False
    assert out["provider_mfa_evidence_verified"] is False
    assert out["oidc_issuer_syntax_valid"] is None
    assert out["openid_scope_present"] is None
    assert out["mfa_enforced_flag"] is None
    assert out["audit_logging_flag"] is None
    assert out["edge_configuration_visibility"] == "NOT_INSPECTABLE_FROM_STREAMLIT"
    serialized = json.dumps({key: value for key, value in out.items() if key != "environment_variables"})
    assert "do-not-return" not in serialized
    assert "streamlit-secret-not-returned" not in serialized


def test_t061_linear_mixed_integer_optimization_runs_and_checks_constraints():
    out = run_additional_tool("T061", json.loads(get_tool_example_json("T061")))
    assert out["tool_id"] == "T061"
    assert out["status"] in {
        "OPTIMAL_FEASIBLE",
        "FEASIBLE_NOT_PROVEN_OPTIMAL",
        "NO_VERIFIED_FEASIBLE_SOLUTION",
        "SOLVER_ERROR",
    }
    if out["status"] != "SOLVER_ERROR":
        assert out["variable_count"] == 2
        assert out["constraint_count"] == 1
    if out["status"] in {"OPTIMAL_FEASIBLE", "FEASIBLE_NOT_PROVEN_OPTIMAL"}:
        assert out["independent_feasibility_check"] is True
        assert out["objective_value"] == pytest.approx(42.0, abs=1e-5)


def test_t067_multiobjective_pareto_rejects_invalid_contracts_and_finds_frontier():
    out = run_additional_tool("T067", json.loads(get_tool_example_json("T067")))
    assert out["status"] == "PARETO_TRADEOFFS_ANALYZED"
    assert out["alternative_count"] == 4
    assert out["pareto_candidate_count"] == 3
    assert bool(out["ranked_alternatives"].iloc[0]["Pareto Candidate"]) is True
    bad = json.loads(get_tool_example_json("T067"))
    for objective in bad["objectives"]:
        objective["weight"] = 0
    with pytest.raises(ValueError, match="At least one objective weight"):
        run_additional_tool("T067", bad)


def test_t068_robust_linear_optimization_solves_worst_case_scenario():
    out = run_additional_tool("T068", json.loads(get_tool_example_json("T068")))
    assert out["tool_id"] == "T068"
    assert out["status"] == "ROBUST_OPTIMAL"
    assert out["success"] is True
    assert out["worst_case_objective"] == pytest.approx(80.0 / 3.0, abs=1e-6)
    assert out["decision_variables"][0] == pytest.approx(20.0 / 3.0, abs=1e-6)
    bad = {"scenario_objectives": [[1, 2], [3]], "bounds": [[0, 1], [0, 1]]}
    with pytest.raises(ValueError, match="same number"):
        run_additional_tool("T068", bad)


def _isolate_experience_database(monkeypatch, tmp_path):
    import industrial_experience as experience

    db_path = str(tmp_path / "experience_acceptance.db")
    original_db = experience._db
    original_ensure = experience.ensure_experience_db
    monkeypatch.setattr(experience, "_db", lambda path="enterprise_full_workspace.db": original_db(db_path))
    monkeypatch.setattr(experience, "ensure_experience_db", lambda path="enterprise_full_workspace.db": original_ensure(db_path))
    monkeypatch.setattr(experience, "durable_backend_configured", lambda: False)
    return experience


def test_t004_project_manager_creates_and_lists_only_owner_projects(monkeypatch, tmp_path):
    _isolate_experience_database(monkeypatch, tmp_path)
    created = run_additional_tool("T004", {
        "action": "create", "owner": "project-owner-a", "name": "Capacity improvement",
        "module": "Capacity Planning", "description": "Synthetic engineering project",
        "linked_artifact_ids": ["DATASET-SYN-1", "RUN-SYN-2"],
    })
    assert created["status"] == "PROJECT_CREATED"
    assert created["linked_artifact_count"] == 2
    own = run_additional_tool("T004", {"action": "list", "owner": "project-owner-a"})
    other = run_additional_tool("T004", {"action": "list", "owner": "project-owner-b"})
    assert own["project_count"] == 1
    assert own["projects"].iloc[0]["project_id"] == created["project_id"]
    assert other["project_count"] == 0


def test_t005_project_version_history_appends_restore_and_rejects_other_owner(monkeypatch, tmp_path):
    _isolate_experience_database(monkeypatch, tmp_path)
    created = run_additional_tool("T005", {
        "action": "create", "owner": "version-owner", "name": "Versioned study",
        "state": {"revision": 1, "value": "original"},
    })
    project_id = created["project_id"]
    saved = run_additional_tool("T005", {
        "action": "autosave", "owner": "version-owner", "project_id": project_id,
        "state": {"revision": 2, "value": "updated"},
    })
    assert saved["snapshot_no"] == 2
    history = run_additional_tool("T005", {"action": "history", "owner": "version-owner", "project_id": project_id})
    assert history["snapshot_count"] == 2
    restored = run_additional_tool("T005", {
        "action": "restore", "owner": "version-owner", "project_id": project_id, "snapshot_no": 1,
    })
    assert restored["snapshot_no"] == 3
    final_history = run_additional_tool("T005", {"action": "history", "owner": "version-owner", "project_id": project_id})
    assert final_history["history"][-1]["payload"] == {"revision": 1, "value": "original"}
    with pytest.raises(PermissionError, match="not owned"):
        run_additional_tool("T005", {
            "action": "autosave", "owner": "different-owner", "project_id": project_id,
            "state": {"revision": 4},
        })


def test_t086_hypothesis_register_persists_evidence_references_and_enforces_owner(monkeypatch, tmp_path):
    _isolate_experience_database(monkeypatch, tmp_path)
    created = run_additional_tool("T086", {
        "action": "create", "owner": "research-owner-a", "study_id": "STUDY-SYNTHETIC-001",
        "title": "Synthetic process variability study",
        "research_question": "Does the intervention reduce variation?",
        "hypothesis": "Post-intervention variation is lower.",
        "null_hypothesis": "Post-intervention variation is not lower.",
        "methodology": "Controlled comparison", "primary_endpoint": "Standard deviation",
        "evidence_references": ["SYNTHETIC-REF-1"],
    })
    assert created["status"] == "HYPOTHESIS_PROTOCOL_RECORDED"
    loaded = run_additional_tool("T086", {
        "action": "load", "owner": "research-owner-a", "study_id": "STUDY-SYNTHETIC-001",
    })
    assert loaded["protocol"]["hypothesis"] == "Post-intervention variation is lower."
    assert loaded["protocol"]["evidence_references"] == ["SYNTHETIC-REF-1"]
    listed = run_additional_tool("T086", {"action": "list", "owner": "research-owner-a"})
    assert listed["study_count"] == 1
    with pytest.raises(PermissionError):
        run_additional_tool("T086", {"action": "load", "owner": "research-owner-b", "study_id": "STUDY-SYNTHETIC-001"})
    bad = {
        "action": "create", "owner": "research-owner-a", "title": "Bad study",
        "research_question": "Q", "hypothesis": "H", "null_hypothesis": "H0",
        "methodology": "Controlled", "primary_endpoint": "Endpoint", "alpha": 1.2,
    }
    with pytest.raises(ValueError, match="alpha"):
        run_additional_tool("T086", bad)


def test_t092_decision_register_creates_draft_and_requests_review_without_approval(monkeypatch, tmp_path):
    _isolate_experience_database(monkeypatch, tmp_path)
    created = run_additional_tool("T092", {
        "action": "create", "owner": "decision-owner-a", "title": "Synthetic capacity decision",
        "metrics": {"capacity_delta_units": 10}, "assumptions": {"provenance": "SYNTHETIC"},
        "uncertainty": {"demand_range": "illustrative"},
    })
    assert created["workflow_status"] == "Draft"
    review = run_additional_tool("T092", {
        "action": "request_review", "owner": "decision-owner-a", "decision_id": created["decision_id"],
        "comment": "Please review the synthetic scenario.",
    })
    assert review["status"] == "DECISION_REVIEW_REQUESTED"
    assert "does not approve" in review["warning"]
    own = run_additional_tool("T092", {"action": "list", "owner": "decision-owner-a"})
    other = run_additional_tool("T092", {"action": "list", "owner": "decision-owner-b"})
    assert own["decision_count"] == 1
    assert other["decision_count"] == 0
    with pytest.raises(ValueError, match="dataset_dependencies"):
        run_additional_tool("T092", {
            "action": "create", "owner": "decision-owner-a", "title": "Bad dependencies",
            "metrics": {}, "assumptions": {}, "uncertainty": {}, "dataset_dependencies": ["not-an-object"],
        })


def test_t011_to_t014_workbook_tools_use_existing_multisheet_pipeline():
    raw_io = io.BytesIO()
    with pd.ExcelWriter(raw_io, engine="openpyxl") as writer:
        pd.DataFrame({"Asset ID": ["A-1", "A-2"], "Qty": [10, 20]}).to_excel(writer, sheet_name="Assets", index=False)
        pd.DataFrame({"Asset ID": ["A-1", "A-2"], "Cost": [100, 200]}).to_excel(writer, sheet_name="Costs", index=False)
    raw = raw_io.getvalue()

    imported = run_additional_tool("T011", {"filename": "synthetic-assets.xlsx", "raw_bytes": raw})
    assert imported["status"] == "WORKBOOK_IMPORTED"
    assert imported["sheet_count"] == 2
    assert imported["original_source_preserved_in_workbook_record"] is True
    workbook = imported.pop("excel_workbook_result")
    assert workbook["_raw_bytes"] == raw

    mapped = run_additional_tool("T012", {"filename": "synthetic-assets.xlsx", "raw_bytes": raw})
    assert mapped["status"] == "WORKBOOK_STRUCTURE_MAPPED"
    assert "table_catalog" in mapped["details"]

    profiled = run_additional_tool("T013", {"filename": "synthetic-assets.xlsx", "raw_bytes": raw})
    assert profiled["status"] == "WORKBOOK_PROFILED"
    assert len(profiled["details"]["profiles"]) >= 1

    with pytest.raises(ValueError, match="explicitly confirm"):
        run_additional_tool("T014", {"filename": "synthetic-assets.xlsx", "raw_bytes": raw})
    cleaned = run_additional_tool("T014", {
        "filename": "synthetic-assets.xlsx", "raw_bytes": raw, "confirm_cleaning": True,
    })
    assert cleaned["status"] == "CLEANED_COPY_READY"
    assert cleaned["original_source_preserved_in_workbook_record"] is True
    assert len(cleaned["details"]["sheet_comparison"]) == 2


def test_t020_immutable_dataset_version_registration_wraps_existing_managed_pipeline(monkeypatch):
    import io
    import industrial_platform as platform

    state = {}
    monkeypatch.setattr(platform, "_industrial_platform_session_state", lambda: state)
    calls = {}

    def fake_register_dataset(name, source_name, frame, **kwargs):
        calls.update({"name": name, "source_name": source_name, "frame": frame.copy(), **kwargs})
        state["data_platform_latest_registration"] = {
            "dataset_id": "DS-ABCDEF123456",
            "version": 3,
            "data_hash": "a" * 64,
            "version_fingerprint": "b" * 64,
            "created_new_version": True,
        }
        state["data_platform_latest_version"] = 3
        return "DS-ABCDEF123456"

    monkeypatch.setattr(platform, "register_dataset", fake_register_dataset)
    raw_io = io.BytesIO()
    with pd.ExcelWriter(raw_io, engine="openpyxl") as writer:
        pd.DataFrame({"Asset ID": ["A-1", "A-2"], "Qty": [10, 20]}).to_excel(writer, sheet_name="Assets", index=False)
    raw = raw_io.getvalue()

    result = run_additional_tool("T020", {
        "filename": "synthetic-assets.xlsx",
        "raw_bytes": raw,
        "dataset_name": "Synthetic asset register",
        "sheet_name": "Assets",
        "username": "synthetic-owner",
        "token": "synthetic-managed-session-token",
        "workspace": "synthetic-workspace",
    })
    assert result["status"] == "IMMUTABLE_DATASET_VERSION_REGISTERED"
    assert result["dataset_id"] == "DS-ABCDEF123456"
    assert result["version"] == 3
    assert result["row_count"] == 2
    assert calls["username"] == "synthetic-owner"
    assert calls["token"] == "synthetic-managed-session-token"
    assert calls["workspace"] == "synthetic-workspace"
    assert calls["frame"]["Qty"].tolist() == [10, 20]
    workbook = result.pop("excel_workbook_result")
    assert workbook["_raw_bytes"] == raw


def test_t073_scenario_manager_compares_branches_and_enforces_owner(monkeypatch, tmp_path):
    _isolate_experience_database(monkeypatch, tmp_path)
    example = json.loads(get_tool_example_json("T073"))
    created = run_additional_tool("T073", example)
    assert created["status"] == "SCENARIO_SET_SAVED"
    assert created["scenario_count"] == 3
    assert created["baseline_scenario"] == "Baseline"

    branched = run_additional_tool("T073", {
        **example,
        "action": "branch",
        "owner": "synthetic-scenario-owner",
        "parent_project_id": created["project_id"],
        "name": "Synthetic what-if branch B",
    })
    assert branched["status"] == "SCENARIO_BRANCH_SAVED"
    assert branched["parent_project_id"] == created["project_id"]

    history = run_additional_tool("T073", {
        "action": "history",
        "owner": "synthetic-scenario-owner",
        "project_id": created["project_id"],
    })
    assert history["snapshot_count"] == 1
    listed = run_additional_tool("T073", {"action": "list", "owner": "synthetic-scenario-owner"})
    assert listed["project_count"] == 2
    with pytest.raises(PermissionError, match="not owned"):
        run_additional_tool("T073", {
            "action": "history",
            "owner": "different-owner",
            "project_id": created["project_id"],
        })
