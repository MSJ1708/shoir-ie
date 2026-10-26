from __future__ import annotations

import json

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
    with pytest.raises(ValueError, match="earliest revision"):
        recovery_action({
            "action": "undo",
            "history": [{"snapshot_id": "rev-1", "revision": 0, "state": {"x": 1}}],
            "current_index": 0,
        })


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
    assert "never-return-this-secret" not in json.dumps(out)


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


def test_identity_config_reports_readiness_without_claiming_sso_active(monkeypatch):
    values = {
        "SHOIR_OIDC_ISSUER_URL": "https://idp.example.test",
        "SHOIR_OIDC_CLIENT_ID": "shoir-staging",
        "SHOIR_OIDC_CLIENT_SECRET": "do-not-return",
        "SHOIR_OIDC_REDIRECT_URI": "https://staging.example.test/auth/callback",
        "SHOIR_OIDC_SCOPES": "openid profile email",
        "SHOIR_MFA_ENFORCED": "true",
        "SHOIR_AUDIT_LOG_ENABLED": "true",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    out = identity_audit_configuration_status()
    assert out["status"] == "READY_FOR_AUTHORIZED_IDP_TEST"
    assert out["sso_active"] is False
    assert out["mfa_active"] is False
    assert "do-not-return" not in json.dumps(out)


def test_identity_config_fails_closed_when_provider_is_missing(monkeypatch):
    for key in (
        "SHOIR_OIDC_ISSUER_URL", "SHOIR_OIDC_CLIENT_ID", "SHOIR_OIDC_CLIENT_SECRET",
        "SHOIR_OIDC_REDIRECT_URI", "SHOIR_OIDC_SCOPES", "SHOIR_MFA_ENFORCED",
        "SHOIR_AUDIT_LOG_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    out = identity_audit_configuration_status()
    assert out["status"] == "NOT_CONFIGURED"
    assert out["sso_active"] is False
    assert len(out["missing_variables"]) >= 7


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


def test_all_target_examples_are_valid_json():
    for tool_id in ("T006", "T020", "T060", "T074", "T080", "T094", "T096", "T097", "T098", "T099"):
        value = json.loads(get_tool_example_json(tool_id))
        assert isinstance(value, dict)
        out = run_additional_tool(tool_id, value)
        assert out["tool_id"] == tool_id
