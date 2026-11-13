"""Independent regression tests for the Industrial Resource Intelligence foundation."""
from __future__ import annotations

from pathlib import Path

import pytest

from shoir_resource_intelligence import (
    ResourceValidationError,
    assess_resource_compatibility,
    calculate_exchange_value,
    calculate_resource_balance,
    calculate_supply_reliability,
    detect_resource_loss,
    evaluate_safety_gate,
    forecast_resource_quality,
    optimize_resource_network,
    propagate_network_impact,
    rank_resource_cascade,
    simulate_supplier_disruption,
    validate_import_rows,
    validate_resource_passport,
)


def _supply(resource_id="S1", quantity=100.0, quality=None):
    return {
        "resource_id": resource_id,
        "facility_id": "FAC-A",
        "name": "Recovered water",
        "resource_type": "Water",
        "available_quantity": quantity,
        "unit": "m3/day",
        "quality": quality or {"pH": 7.0, "TDS_mg_l": 250.0},
        "provenance": "IMPORTED",
    }


def _demand(demand_id="D1", quantity=60.0, limits=None):
    return {
        "demand_id": demand_id,
        "name": "Process water requirement",
        "resource_type": "Water",
        "required_quantity": quantity,
        "unit": "m3/day",
        "quality_limits": limits or {"pH": {"min": 6.5, "max": 8.5}, "TDS_mg_l": {"max": 500}},
    }


def _route(supply_id="S1", demand_id="D1", cost=2.0):
    return {
        "supply_id": supply_id,
        "demand_id": demand_id,
        "unit_cost": cost,
        "transport_cost_per_unit": 0.0,
        "treatment_cost_per_unit": 0.0,
        "currency": "SAR",
        "capacity": 100.0,
    }


def test_resource_passport_normalizes_provenance_and_requires_real_inputs():
    passport = validate_resource_passport({
        "facility_id": "FAC-A",
        "name": "Recovered process water",
        "resource_type": "Water",
        "available_quantity": "120",
        "unit": "m3/day",
        "quality": {"pH": "7.2"},
        "provenance": "imported",
        "measured_at": "2026-11-12T10:00:00+03:00",
    })
    assert passport["available_quantity"] == 120
    assert passport["provenance"] == "IMPORTED"
    assert passport["quality"] == {"pH": 7.2}
    assert passport["measured_at"].endswith("+00:00")


@pytest.mark.parametrize("bad", [0, -1, "not-a-number", float("inf"), float("nan")])
def test_resource_passport_rejects_nonpositive_or_nonfinite_quantity(bad):
    with pytest.raises(ResourceValidationError):
        validate_resource_passport({
            "facility_id": "FAC-A", "name": "Water", "resource_type": "Water",
            "available_quantity": bad, "unit": "m3/day", "provenance": "MANUAL",
        })


def test_resource_balance_reconciles_same_unit_and_exposes_signed_difference():
    result = calculate_resource_balance(100, 92, unit="m3/day", tolerance_percent=5)
    assert result["status"] == "ANOMALY_SUSPECTED"
    assert result["unreconciled_quantity"] == 8
    assert result["difference_percent"] == 8


def test_resource_loss_screen_never_confirms_a_loss_from_a_balance_anomaly():
    result = detect_resource_loss(100, 80, unit="kg", evidence_provenance="IMPORTED")
    assert result["finding_type"] == "SUSPECTED_RESOURCE_LOSS"
    assert result["confirmation_status"] == "NOT_CONFIRMED"


def test_compatibility_rejects_different_units_without_implicit_conversion():
    result = assess_resource_compatibility(_supply(), {**_demand(), "unit": "L/s"})
    assert result["status"] == "TECHNICALLY_INCOMPATIBLE"


def test_compatibility_fails_closed_when_required_quality_property_is_missing():
    result = assess_resource_compatibility(
        _supply(quality={"pH": 7.0}),
        _demand(limits={"TDS_mg_l": {"max": 500}}),
    )
    assert result["status"] == "INSUFFICIENT_DATA"


def test_compatibility_identifies_out_of_spec_material_as_incompatible():
    result = assess_resource_compatibility(
        _supply(quality={"pH": 4.0}),
        _demand(limits={"pH": {"min": 6.5, "max": 8.5}}),
    )
    assert result["status"] == "TECHNICALLY_INCOMPATIBLE"


def test_compatibility_treatment_requires_residual_quality_and_recorded_evidence():
    result = assess_resource_compatibility(
        _supply(quality={"pH": 4.0}),
        _demand(limits={"pH": {"min": 6.5, "max": 8.5}}),
        treatment_plan={
            "residual_quality": {"pH": 7.0},
            "qualification_evidence": "LAB-REPORT-17",
            "qualified_by": "Named engineer",
        },
    )
    assert result["status"] == "COMPATIBLE_SUBJECT_TO_TREATMENT"
    assert result["qualification_is_user_asserted"] is True
    assert "not been independently verified" in result["verification_warning"]


def test_compatibility_lab_and_engineering_hold_statuses_are_explicit():
    supply, demand = _supply(), _demand()
    assert assess_resource_compatibility(supply, demand, laboratory_test_required=True)["status"] == "REQUIRES_LAB_TESTING"
    assert assess_resource_compatibility(supply, demand, engineering_review_required=True)["status"] == "REQUIRES_ENGINEERING_REVIEW"


def test_network_lp_respects_supply_capacity_and_fully_reconciles_demand():
    result = optimize_resource_network([_supply()], [_demand()], [_route()])
    assert result["status"] == "OPTIMAL"
    assert result["allocations"][0]["quantity"] == pytest.approx(60)
    assert result["objective_cost"] == pytest.approx(120)


def test_network_lp_returns_infeasible_instead_of_overallocating_shared_supply():
    demands = [_demand("D1", 80), _demand("D2", 80)]
    routes = [_route("S1", "D1"), _route("S1", "D2")]
    result = optimize_resource_network([_supply(quantity=100)], demands, routes)
    assert result["status"] == "INFEASIBLE"
    assert result["allocations"] == []


def test_network_lp_rejects_route_when_quality_gate_fails():
    result = optimize_resource_network(
        [_supply(quality={"pH": 3.0})],
        [_demand(limits={"pH": {"min": 6.5, "max": 8.5}})],
        [_route()],
    )
    assert result["status"] == "INFEASIBLE"
    assert result["rejected_routes"][0]["status"] == "TECHNICALLY_INCOMPATIBLE"


def test_supplier_disruption_reports_shortage_without_inventing_recovery_time():
    result = simulate_supplier_disruption(
        [_supply(quantity=100)], [_demand(quantity=80)], [_route()],
        supplier_id="S1", supply_reduction_fraction=0.5,
        shortage_penalty_per_unit=1_000_000,
        shortage_penalty_currency="SAR",
    )
    assert result["allocation_result"]["status"] == "FEASIBLE_WITH_SHORTAGE"
    assert result["allocation_result"]["unmet_demand"][0]["quantity"] == pytest.approx(30)
    assert result["recovery_time"] is None


def test_safety_gate_blocks_critical_failure_even_when_references_are_recorded():
    result = evaluate_safety_gate(
        critical_failure=True,
        laboratory_required=True,
        laboratory_passed=True,
        engineering_approval_reference="ENG-1",
        safety_approval_reference="HSE-1",
        environmental_approval_reference="ENV-1",
    )
    assert result["status"] == "REJECTED"
    assert result["operational_authorization"] is False


def test_safety_gate_does_not_promote_missing_approval_references():
    result = evaluate_safety_gate(
        critical_failure=False,
        laboratory_required=True,
        laboratory_passed=None,
    )
    assert result["status"] == "APPROVAL_PENDING"
    assert len(result["blockers"]) == 4


def test_network_value_excludes_internal_transfer_from_network_benefit():
    result = calculate_exchange_value(
        avoided_disposal_cost=100,
        supplier_sale_revenue=20,
        supplier_preparation_cost=10,
        supplier_testing_cost=5,
        supplier_handling_delivery_cost=5,
        avoided_alternative_purchase_cost=200,
        buyer_treatment_cost=50,
        buyer_transport_cost=10,
        buyer_testing_cost=5,
        buyer_additional_operating_cost=5,
        currency="SAR",
        evidence_status="INDEPENDENTLY_VERIFIED",
    )
    assert result["supplier_benefit"] == pytest.approx(100)
    assert result["buyer_benefit"] == pytest.approx(130)
    assert result["network_benefit_transfer_neutral"] == pytest.approx(210)
    assert result["evidence_status"] == "MEASURED_PENDING_INDEPENDENT_EVIDENCE"
    assert result["independent_verification"] == "NOT_ESTABLISHED"


def test_dependency_propagation_is_downstream_and_does_not_claim_causality():
    result = propagate_network_impact(
        [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}, {"from": "X", "to": "Y"}],
        affected_node="A",
    )
    assert result["affected_nodes"] == ["B", "C"]
    assert result["causality_verified"] is False


def test_quality_forecast_refuses_insufficient_history_and_reports_backtest_when_available():
    assert forecast_resource_quality([])["status"] == "INSUFFICIENT_DATA"
    observations = [
        {"timestamp": f"2026-01-{day:02d}T00:00:00+00:00", "value": 7.0 + day * 0.01}
        for day in range(1, 26)
    ]
    result = forecast_resource_quality(observations)
    assert result["status"] == "EXPLORATORY_FORECAST_NOT_VALIDATED"
    assert result["holdout_sample_count"] == 5
    assert result["prediction_interval_approx_95"][0] <= result["forecast"] <= result["prediction_interval_approx_95"][1]


def test_supply_reliability_reports_empirical_history_not_future_probability():
    history = [
        {"delivered_quantity": 100, "required_quantity": 100, "quality_pass": True}
        for _ in range(20)
    ]
    result = calculate_supply_reliability(history)
    assert result["historical_pass_rate"] == 1
    assert result["future_reliability_probability"] is None


def test_cascade_ranks_prevention_before_external_exchange_and_disposal():
    result = rank_resource_cascade([
        {"opportunity_id": "C", "action": "DISPOSE"},
        {"opportunity_id": "B", "action": "EXTERNAL_EXCHANGE"},
        {"opportunity_id": "A", "action": "PREVENT"},
    ])
    assert [x["action"] for x in result] == ["PREVENT", "EXTERNAL_EXCHANGE", "DISPOSE"]


def test_import_validation_preserves_invalid_source_rows_and_does_not_mutate_them():
    row = {
        "facility_id": "FAC-A", "name": "Water", "resource_type": "Water",
        "available_quantity": -1, "unit": "m3/day", "provenance": "IMPORTED",
    }
    original = dict(row)
    result = validate_import_rows([row])
    assert result["status"] == "INVALID"
    assert row == original
    assert result["source_rows_modified"] is False


def test_workbench_discovery_alias_launch_and_entitlement(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    page = Path(__file__).resolve().parents[1] / "pages" / "Industrial_Engineering_Workbench.py"
    at = AppTest.from_file(page, default_timeout=60)
    at.session_state["current_user"] = "resource-intelligence-test"
    at.session_state["authenticated"] = True
    at.session_state["user_tier"] = "Enterprise Plus Tier"
    at.run(timeout=60)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)

    at.text_input(key="workbench_module_search").set_value("IEIT")
    at.run(timeout=60)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    selector = at.selectbox(key="workbench_module_selector")
    assert "Resource Intelligence · Industrial Resource Intelligence" in selector.options
    for query in ("Industrial Resource Intelligence & Resilience System", "ذكاء الموارد الصناعية"):
        at.text_input(key="workbench_module_search").set_value(query)
        at.run(timeout=60)
        assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
        assert "Resource Intelligence · Industrial Resource Intelligence" in at.selectbox(key="workbench_module_selector").options
    at.text_input(key="workbench_module_search").set_value("IEIT")
    at.run(timeout=60)
    selector = at.selectbox(key="workbench_module_selector")
    selector.select("Resource Intelligence · Industrial Resource Intelligence")
    at.run(timeout=60)
    assert not at.exception, "\\n".join(str(error.value) for error in at.exception)
    assert any("Industrial Resource Intelligence" in item.value for item in at.subheader)

    # The same route is not discoverable through the available module menu to Starter.
    denied = AppTest.from_file(page, default_timeout=60)
    denied.session_state["current_user"] = "resource-starter-test"
    denied.session_state["authenticated"] = True
    denied.session_state["user_tier"] = "Starter"
    denied.run(timeout=60)
    assert not denied.exception, "\\n".join(str(error.value) for error in denied.exception)
    denied.text_input(key="workbench_module_search").set_value("industrial symbiosis")
    denied.run(timeout=60)
    assert not denied.exception, "\\n".join(str(error.value) for error in denied.exception)
    assert any("Enterprise" in warning.value for warning in denied.warning)



def test_over_reconciliation_is_flagged_as_anomaly_not_ignored():
    result = detect_resource_loss(100, 105, unit="m3/day", tolerance_percent=1)
    assert result["status"] == "ANOMALY_SUSPECTED"
    assert result["finding_type"] == "UNRECONCILED_BALANCE"
    assert result["confirmation_status"] == "NOT_CONFIRMED"


def test_compatibility_can_check_temperature_and_pressure_limits():
    supply = {
        **_supply(),
        "temperature_c": 45.0,
        "pressure_kpa": 250.0,
    }
    demand = {
        **_demand(),
        "quality_limits": {
            "pH": {"min": 6.5, "max": 8.5},
            "temperature_c": {"max": 40.0},
            "pressure_kpa": {"min": 100.0, "max": 300.0},
        },
    }
    result = assess_resource_compatibility(supply, demand)
    assert result["status"] == "TECHNICALLY_INCOMPATIBLE"
    assert any("temperature_c" in reason for reason in result["reasons"])


def test_network_optimizer_does_not_treat_treatment_assertion_as_automatic_route_approval():
    result = optimize_resource_network(
        [_supply(quality={"pH": 4.0})],
        [_demand(limits={"pH": {"min": 6.5, "max": 8.5}})],
        [{
            **_route(),
            "treatment_plan": {
                "residual_quality": {"pH": 7.0},
                "qualification_evidence": "LAB-REF",
                "qualified_by": "Engineer",
            },
        }],
    )
    assert result["status"] == "INFEASIBLE"
    assert result["rejected_routes"][0]["status"] == "COMPATIBLE_SUBJECT_TO_TREATMENT"


def test_explore_catalog_and_shared_tier_policy_are_registered():
    from industrial_platform import PLATFORM_CATALOG
    from shoir_tier_capabilities import module_required_tier

    item = next(x for x in PLATFORM_CATALOG if x["name"] == "Industrial Resource Intelligence")
    assert item["tier"] == "Enterprise"
    assert item["category"] == "Resource Intelligence"
    assert module_required_tier("Industrial Resource Intelligence") == "Enterprise"


def test_resource_bottleneck_identifies_the_smallest_capacity_constraint():
    from shoir_resource_intelligence import detect_resource_bottleneck

    result = detect_resource_bottleneck(
        75,
        unit="m3/day",
        capacity_constraints=[
            {"constraint": "Treatment", "capacity": 90, "unit": "m3/day"},
            {"constraint": "Storage withdrawal", "capacity": 60, "unit": "m3/day"},
        ],
    )
    assert result["status"] == "BOTTLENECK"
    assert result["limiting_constraint"]["constraint"] == "Storage withdrawal"
    assert result["shortfall_quantity"] == pytest.approx(15)


def test_bottleneck_refuses_mixed_capacity_units():
    from shoir_resource_intelligence import detect_resource_bottleneck

    with pytest.raises(ResourceValidationError):
        detect_resource_bottleneck(
            10,
            unit="m3/day",
            capacity_constraints=[{"constraint": "Pump", "capacity": 20, "unit": "L/s"}],
        )


def test_infrastructure_route_requires_connection_evidence_capacity_and_approvals():
    from shoir_resource_intelligence import assess_infrastructure_route

    unknown = assess_infrastructure_route({"connection_confirmed": None})
    assert unknown["status"] == "INSUFFICIENT_DATA"
    short = assess_infrastructure_route({
        "connection_confirmed": True, "distance_km": 5, "capacity": 20,
        "required_quantity": 30, "unit": "m3/day",
    })
    assert short["status"] == "INFEASIBLE_CAPACITY"
    pending = assess_infrastructure_route({
        "connection_confirmed": True, "distance_km": 5, "capacity": 40,
        "required_quantity": 30, "unit": "m3/day",
    })
    assert pending["status"] == "APPROVAL_PENDING"
    feasible = assess_infrastructure_route({
        "connection_confirmed": True, "distance_km": 5, "capacity": 40,
        "required_quantity": 30, "unit": "m3/day",
        "route_access_evidence": "SURVEY-1",
        "permit_reference": "PERMIT-1",
        "engineering_review_reference": "ENG-1",
    })
    assert feasible["status"] == "PRELIMINARY_FEASIBILITY_ONLY"
    assert feasible["operational_authorization"] is False
    assert feasible["independent_verification"] == "NOT_PERFORMED"


def test_resource_intensity_comparison_normalizes_usage_by_production():
    from shoir_resource_intelligence import calculate_resource_intensity_change

    result = calculate_resource_intensity_change(
        1000, 100, 900, 100,
        usage_unit="m3", production_unit="tonne",
    )
    assert result["baseline_intensity"] == pytest.approx(10)
    assert result["reporting_intensity"] == pytest.approx(9)
    assert result["change_percent"] == pytest.approx(-10)
    assert result["evidence_status"] == "COMPARISON_ONLY_NOT_INDEPENDENTLY_VERIFIED"


def test_resource_passport_preserves_owner_and_bilingual_descriptions():
    passport = validate_resource_passport({
        "facility_id": "FAC-A", "name": "Recovered water",
        "resource_type": "Water", "available_quantity": 15,
        "unit": "m3/day", "provenance": "MANUAL",
        "owner": "Utilities Department",
        "description_en": "Treated process-water stream",
        "description_ar": "مياه معالجة",
        "source_process": "Cooling loop",
        "source_equipment": "HX-100",
        "laboratory_evidence_reference": "LAB-12",
    })
    assert passport["owner"] == "Utilities Department"
    assert passport["description_ar"] == "مياه معالجة"
    assert passport["source_equipment"] == "HX-100"
    assert passport["laboratory_evidence_reference"] == "LAB-12"


def test_manual_resource_passports_cannot_claim_live_without_verified_connector():
    with pytest.raises(ResourceValidationError, match="LIVE provenance is reserved"):
        validate_resource_passport({
            "facility_id": "FAC-A", "name": "Water", "resource_type": "Water",
            "available_quantity": 10, "unit": "m3/day", "provenance": "LIVE",
        })


def test_loss_screen_does_not_accept_live_as_user_entered_provenance():
    with pytest.raises(ResourceValidationError, match="LIVE requires a verified connector"):
        detect_resource_loss(100, 90, unit="m3/day", evidence_provenance="LIVE")


def test_complete_supplier_shutdown_returns_full_unmet_demand_not_false_infeasibility():
    result = simulate_supplier_disruption(
        [_supply(quantity=100)], [_demand(quantity=80)], [_route()],
        supplier_id="S1", supply_reduction_fraction=1.0,
        shortage_penalty_per_unit=1_000_000,
        shortage_penalty_currency="SAR",
    )
    assert result["allocation_result"]["status"] == "FEASIBLE_WITH_SHORTAGE"
    assert result["allocation_result"]["allocations"] == []
    assert result["allocation_result"]["unmet_demand"][0]["quantity"] == pytest.approx(80)


def test_small_balance_difference_inside_tolerance_is_not_a_suspected_loss():
    result = detect_resource_loss(100, 99.5, unit="m3/day", tolerance_percent=1)
    assert result["status"] == "WITHIN_TOLERANCE"
    assert result["finding_type"] == "NO_MATERIAL_ANOMALY"
    assert result["confirmation_status"] == "NOT_CONFIRMED"


def test_missing_excel_text_cells_are_not_coerced_to_the_literal_nan_string():
    from shoir_resource_intelligence import _text
    import numpy as np

    with pytest.raises(ResourceValidationError):
        _text(float("nan"), "resource name")
    with pytest.raises(ResourceValidationError):
        _text(np.float64("nan"), "resource name")


def test_resource_passport_rejects_invalid_certificate_date_and_approval_status():
    base = {
        "facility_id": "FAC-A", "name": "Recovered water",
        "resource_type": "Water", "available_quantity": 10,
        "unit": "m3/day", "provenance": "MANUAL",
    }
    with pytest.raises(ResourceValidationError, match="YYYY-MM-DD"):
        validate_resource_passport({**base, "certificate_valid_until": "31-12-2026"})
    with pytest.raises(ResourceValidationError, match="approval_status"):
        validate_resource_passport({**base, "approval_status": "AUTO_APPROVED"})


def test_blank_spreadsheet_optional_cells_remain_blank_in_resource_passports():
    passport = validate_resource_passport({
        "resource_id": float("nan"),
        "facility_id": "FAC-A",
        "name": "Recovered water",
        "resource_type": "Water",
        "available_quantity": 20,
        "unit": "m3/day",
        "quality": float("nan"),
        "temperature_c": float("nan"),
        "pressure_kpa": float("nan"),
        "owner": float("nan"),
        "measured_at": float("nan"),
        "certificate_valid_until": float("nan"),
        "provenance": "IMPORTED",
    })
    assert passport["resource_id"] != "nan"
    assert passport["quality"] == {}
    assert passport["temperature_c"] is None
    assert passport["pressure_kpa"] is None
    assert passport["owner"] == ""
    assert passport["measured_at"] is None
    assert passport["certificate_valid_until"] == ""


def test_boolean_is_not_accepted_as_a_numeric_measurement():
    with pytest.raises(ResourceValidationError, match="not a boolean"):
        validate_resource_passport({
            "facility_id": "FAC-A", "name": "Water", "resource_type": "Water",
            "available_quantity": True, "unit": "m3/day", "provenance": "MANUAL",
        })


def _exchange_agreement_payload():
    return {
        "supplier": "Supplier Facility A",
        "buyer": "Buyer Facility B",
        "resource_id": "S1",
        "resource_name": "Recovered process water",
        "agreed_quantity": 100,
        "unit": "m3/day",
        "quantity_tolerance_percent": 5,
        "quality_limits": {
            "pH": {"min": 6.5, "max": 8.5},
            "TDS_mg_l": {"max": 500},
        },
        "delivery_schedule": "Daily, 06:00–08:00",
        "certificate_required": True,
        "treatment_responsibility": "Supplier",
        "testing_requirements": "Certificate per delivery",
        "shortage_response": "Buyer to be notified",
        "rejection_procedure": "Quarantine pending review",
        "approval_references": {},
    }


def test_exchange_agreement_is_a_draft_until_human_references_are_recorded():
    from shoir_resource_intelligence import validate_exchange_agreement

    agreement = validate_exchange_agreement(_exchange_agreement_payload())
    assert agreement["status"] == "APPROVAL_PENDING"
    assert agreement["contract_status"] == "DRAFT_NOT_A_SIGNED_CONTRACT"
    assert agreement["operational_authorization"] is False
    assert len(agreement["missing_approval_references"]) == 4


def test_exchange_agreement_with_approval_references_still_is_not_signed():
    from shoir_resource_intelligence import validate_exchange_agreement

    payload = _exchange_agreement_payload()
    payload["approval_references"] = {
        "engineering": "ENG-1",
        "safety": "HSE-1",
        "environmental": "ENV-1",
        "commercial": "COM-1",
    }
    agreement = validate_exchange_agreement(payload)
    assert agreement["status"] == "APPROVAL_REFERENCES_RECORDED_NOT_SIGNED"
    assert agreement["contract_status"] == "DRAFT_NOT_A_SIGNED_CONTRACT"
    assert agreement["operational_authorization"] is False


def test_delivery_assurance_compares_quantity_quality_and_certificate_terms():
    from shoir_resource_intelligence import validate_exchange_agreement, assess_exchange_delivery

    agreement = validate_exchange_agreement(_exchange_agreement_payload())
    result = assess_exchange_delivery(agreement, {
        "delivery_date": "2026-11-12",
        "delivered_quantity": 98,
        "quality": {"pH": 7.1, "TDS_mg_l": 300},
        "certificate_reference": "CERT-100",
        "certificate_valid_until": "2026-12-31",
        "delivery_evidence_reference": "TICKET-100",
    })
    assert result["status"] == "WITHIN_ENTERED_TOLERANCES_PENDING_HUMAN_ACCEPTANCE"
    assert result["deviations"] == []
    assert result["human_acceptance_required"] is True
    assert result["contractual_effect"] == "NOT_CALCULATED"
    assert result["operational_authorization"] is False


def test_delivery_assurance_blocks_out_of_spec_quality_and_expired_certificate():
    from shoir_resource_intelligence import validate_exchange_agreement, assess_exchange_delivery

    agreement = validate_exchange_agreement(_exchange_agreement_payload())
    result = assess_exchange_delivery(agreement, {
        "delivery_date": "2026-11-12",
        "delivered_quantity": 98,
        "quality": {"pH": 4.0, "TDS_mg_l": 900},
        "certificate_reference": "CERT-OLD",
        "certificate_valid_until": "2026-11-01",
        "delivery_evidence_reference": "TICKET-101",
    })
    assert result["status"] == "REJECTED_PENDING_REVIEW"
    assert "QUALITY_OUT_OF_SPECIFICATION" in result["deviations"]
    assert "CERTIFICATE_EXPIRED" in result["deviations"]


def test_delivery_assurance_reports_shortage_and_missing_evidence_without_contract_penalty():
    from shoir_resource_intelligence import validate_exchange_agreement, assess_exchange_delivery

    agreement = validate_exchange_agreement(_exchange_agreement_payload())
    result = assess_exchange_delivery(agreement, {
        "delivery_date": "2026-11-12",
        "delivered_quantity": 60,
        "quality": {"pH": 7.0, "TDS_mg_l": 300},
        "certificate_reference": "CERT-OK",
        "certificate_valid_until": "2026-12-31",
    })
    assert result["status"] == "EVIDENCE_INCOMPLETE"
    assert "SHORTAGE" in result["deviations"]
    assert "DELIVERY_EVIDENCE_MISSING" in result["deviations"]
    assert result["contractual_effect"] == "NOT_CALCULATED"


def test_energy_balance_reports_reconciliation_and_never_confirms_a_loss():
    from shoir_resource_intelligence import calculate_energy_balance

    result = calculate_energy_balance(
        1000, 700, 200, 50, tolerance_percent=1,
    )
    assert result["status"] == "ANOMALY_SUSPECTED"
    assert result["unreconciled_energy_kwh"] == pytest.approx(50)
    assert result["useful_energy_ratio_percent"] == pytest.approx(70)
    assert "not proof" in result["interpretation"]


def test_energy_balance_within_tolerance_is_reported_without_a_loss_claim():
    from shoir_resource_intelligence import calculate_energy_balance

    result = calculate_energy_balance(
        1000, 700, 200, 95, tolerance_percent=1,
    )
    assert result["status"] == "WITHIN_TOLERANCE"
    assert result["unreconciled_percent"] == pytest.approx(0.5)


def test_waste_heat_screen_requires_temperature_approach_and_never_claims_recovery():
    from shoir_resource_intelligence import screen_waste_heat_recovery

    passed = screen_waste_heat_recovery(
        150, 80, 500,
        minimum_approach_temperature_c=15,
        annual_operating_hours=4000,
        energy_value_per_kwh=0.2,
    )
    assert passed["status"] == "TEMPERATURE_APPROACH_PASSED_REQUIRES_HX_DESIGN"
    assert passed["temperature_margin_c"] == pytest.approx(55)
    assert passed["screened_annual_thermal_energy_kwh"] == pytest.approx(2_000_000)
    assert passed["verified_recovered_energy_kwh"] is None
    assert passed["verified_savings"] is None

    failed = screen_waste_heat_recovery(
        90, 80, 500,
        minimum_approach_temperature_c=15,
    )
    assert failed["status"] == "INFEASIBLE_TEMPERATURE_APPROACH"


def test_exchange_agreement_requires_valid_quality_bounds_and_approval_reference_shape():
    from shoir_resource_intelligence import validate_exchange_agreement

    bad = _exchange_agreement_payload()
    bad["quality_limits"] = {"pH": {"min": 9, "max": 7}}
    with pytest.raises(ResourceValidationError, match="minimum exceeds maximum"):
        validate_exchange_agreement(bad)

    bad = _exchange_agreement_payload()
    bad["approval_references"] = "not-an-object"
    with pytest.raises(ResourceValidationError, match="approval_references"):
        validate_exchange_agreement(bad)


def test_water_reuse_lp_maximizes_flow_while_respecting_blended_quality_limit():
    from shoir_resource_intelligence import optimize_single_contaminant_water_reuse

    sources = [
        {"source_id": "S1", "available_flow": 50, "flow_unit": "m3/day", "concentration": 100, "concentration_unit": "mg/L"},
        {"source_id": "S2", "available_flow": 50, "flow_unit": "m3/day", "concentration": 0, "concentration_unit": "mg/L"},
    ]
    sinks = [
        {"sink_id": "D1", "required_flow": 80, "flow_unit": "m3/day", "maximum_concentration": 50, "concentration_unit": "mg/L"},
    ]
    connections = [
        {"source_id": "S1", "sink_id": "D1", "connection_confirmed": True, "connection_evidence_reference": "ROUTE-1"},
        {"source_id": "S2", "sink_id": "D1", "connection_confirmed": True, "connection_evidence_reference": "ROUTE-2"},
    ]
    result = optimize_single_contaminant_water_reuse(
        sources, sinks, connections,
        contaminant="TDS", concentration_unit="mg/L", flow_unit="m3/day",
    )
    assert result["status"] == "PRELIMINARY_SINGLE_CONTAMINANT_REUSE_ALLOCATION"
    assert result["total_reuse_flow"] == pytest.approx(80)
    check = result["sink_quality_checks"][0]
    assert check["blended_concentration"] <= check["maximum_concentration"] + 1e-7
    assert result["operational_authorization"] is False


def test_water_reuse_does_not_assume_physical_connections():
    from shoir_resource_intelligence import optimize_single_contaminant_water_reuse

    result = optimize_single_contaminant_water_reuse(
        [{"source_id": "S1", "available_flow": 10, "flow_unit": "m3/day", "concentration": 1, "concentration_unit": "mg/L"}],
        [{"sink_id": "D1", "required_flow": 10, "flow_unit": "m3/day", "maximum_concentration": 5, "concentration_unit": "mg/L"}],
        [{"source_id": "S1", "sink_id": "D1", "connection_confirmed": False}],
        contaminant="TDS", concentration_unit="mg/L", flow_unit="m3/day",
    )
    assert result["status"] == "NO_CONFIRMED_REUSE_CONNECTION"
    assert result["total_reuse_flow"] == 0


def test_water_reuse_requires_matching_flow_and_concentration_units():
    from shoir_resource_intelligence import optimize_single_contaminant_water_reuse

    with pytest.raises(ResourceValidationError, match="flow unit"):
        optimize_single_contaminant_water_reuse(
            [{"source_id": "S1", "available_flow": 10, "flow_unit": "L/s", "concentration": 1, "concentration_unit": "mg/L"}],
            [{"sink_id": "D1", "required_flow": 10, "flow_unit": "m3/day", "maximum_concentration": 5, "concentration_unit": "mg/L"}],
            [],
            contaminant="TDS", concentration_unit="mg/L", flow_unit="m3/day",
        )


def test_synthetic_end_to_end_resource_intelligence_engine_flow():
    import json
    from shoir_resource_intelligence import (
        validate_import_rows,
        detect_resource_loss,
        optimize_resource_network,
        evaluate_safety_gate,
        validate_exchange_agreement,
        assess_exchange_delivery,
        calculate_exchange_value,
        simulate_supplier_disruption,
    )

    # Synthetic factory source, demand and network evidence only.
    passport = validate_resource_passport({
        "facility_id": "SYN-FAC-001",
        "name": "Synthetic recovered process water",
        "resource_type": "Water",
        "available_quantity": 100,
        "unit": "m3/day",
        "quality": {"pH": 7.2, "TDS_mg_l": 250},
        "provenance": "SYNTHETIC",
    })
    imported = validate_import_rows([passport])
    assert imported["status"] == "VALID"
    assert imported["accepted"][0]["provenance"] == "SYNTHETIC"

    loss = detect_resource_loss(
        100, 95, unit="m3/day", tolerance_percent=1,
        evidence_provenance="SYNTHETIC",
    )
    assert loss["finding_type"] == "SUSPECTED_RESOURCE_LOSS"
    assert loss["confirmation_status"] == "NOT_CONFIRMED"

    demand = _demand(quantity=70)
    route = _route()
    optimized = optimize_resource_network([{
        **passport,
        "resource_id": passport["resource_id"],
    }], [demand], [{
        **route,
        "supply_id": passport["resource_id"],
    }])
    assert optimized["status"] == "OPTIMAL"
    assert optimized["allocations"][0]["quantity"] == pytest.approx(70)

    disruption = simulate_supplier_disruption(
        [{**passport, "resource_id": passport["resource_id"]}],
        [demand],
        [{**route, "supply_id": passport["resource_id"]}],
        supplier_id=passport["resource_id"],
        supply_reduction_fraction=0.5,
        shortage_penalty_per_unit=1_000_000,
        shortage_penalty_currency="SAR",
    )
    assert disruption["allocation_result"]["status"] == "FEASIBLE_WITH_SHORTAGE"

    safety = evaluate_safety_gate(
        critical_failure=False,
        laboratory_required=True,
        laboratory_passed=True,
        engineering_approval_reference="SYN-ENG-APPROVAL",
        safety_approval_reference="SYN-HSE-APPROVAL",
        environmental_approval_reference="SYN-ENV-APPROVAL",
    )
    assert safety["status"] == "APPROVAL_EVIDENCE_RECORDED"
    assert safety["operational_authorization"] is False

    agreement_payload = _exchange_agreement_payload()
    agreement_payload["supplier"] = "Synthetic Supplier"
    agreement_payload["buyer"] = "Synthetic Buyer"
    agreement_payload["resource_id"] = passport["resource_id"]
    agreement_payload["resource_name"] = passport["name"]
    agreement_payload["approval_references"] = {
        "engineering": "SYN-ENG-1",
        "safety": "SYN-HSE-1",
        "environmental": "SYN-ENV-1",
        "commercial": "SYN-COM-1",
    }
    agreement = validate_exchange_agreement(agreement_payload)
    delivery = assess_exchange_delivery(agreement, {
        "delivery_date": "2026-11-12",
        "delivered_quantity": 98,
        "quality": {"pH": 7.1, "TDS_mg_l": 260},
        "certificate_reference": "SYN-CERT-1",
        "certificate_valid_until": "2026-12-31",
        "delivery_evidence_reference": "SYN-TICKET-1",
    })
    assert delivery["status"] == "WITHIN_ENTERED_TOLERANCES_PENDING_HUMAN_ACCEPTANCE"

    value = calculate_exchange_value(
        avoided_disposal_cost=100,
        supplier_sale_revenue=20,
        supplier_preparation_cost=10,
        supplier_testing_cost=5,
        supplier_handling_delivery_cost=5,
        avoided_alternative_purchase_cost=200,
        buyer_treatment_cost=50,
        buyer_transport_cost=10,
        buyer_testing_cost=5,
        buyer_additional_operating_cost=5,
        currency="SAR",
        evidence_status="ESTIMATED",
    )
    evidence_bundle = {
        "provenance": "SYNTHETIC",
        "passport": passport,
        "loss_screen": loss,
        "optimization": optimized,
        "disruption": disruption,
        "safety": safety,
        "agreement": agreement,
        "delivery": delivery,
        "value": value,
    }
    serialized = json.dumps(evidence_bundle, ensure_ascii=False, default=str)
    assert "SYNTHETIC" in serialized
    assert "NOT_CONFIRMED" in serialized
    assert "NOT_CALCULATED" in serialized
    assert "operational_authorization" in serialized


def test_resource_ui_refuses_to_save_resource_data_into_shared_org_workspace():
    from types import SimpleNamespace
    from shoir_resource_intelligence_ui import _persist_workspace

    fake_streamlit = SimpleNamespace(session_state={
        "shoir_active_organization_workspace": {
            "organization_id": "ORG-B",
            "organization_workspace_id": "WORKSPACE-B",
        }
    })
    ok, message = _persist_workspace(fake_streamlit, "synthetic-resource-user")
    assert ok is False
    assert "No resource data was written" in message


def test_quality_forecast_rejects_minimum_sample_setting_without_holdout_capacity():
    with pytest.raises(ResourceValidationError, match="at least 12"):
        forecast_resource_quality([], minimum_samples=5)


def test_supply_reliability_rejects_nonpositive_minimum_periods():
    with pytest.raises(ResourceValidationError, match="at least 1"):
        calculate_supply_reliability([], minimum_periods=0)


def test_delivery_assessment_revalidates_tampered_agreement_quality_limits():
    from shoir_resource_intelligence import validate_exchange_agreement, assess_exchange_delivery

    agreement = validate_exchange_agreement(_exchange_agreement_payload())
    agreement["quality_limits"] = {"pH": {"min": 9, "max": 7}}
    with pytest.raises(ResourceValidationError, match="minimum exceeds maximum"):
        assess_exchange_delivery(agreement, {
            "delivery_date": "2026-11-12",
            "delivered_quantity": 100,
            "quality": {"pH": 7.0},
        })


def test_network_optimizer_rejects_missing_route_capacity_and_costs_instead_of_assuming_zero():
    with pytest.raises(ResourceValidationError):
        optimize_resource_network([_supply()], [_demand()], [{
            "supply_id": "S1", "demand_id": "D1",
            "unit_cost": 1.0, "transport_cost_per_unit": 0.0,
            "treatment_cost_per_unit": 0.0, "currency": "SAR",
            # Deliberately no physical route capacity.
        }])
    with pytest.raises(ResourceValidationError):
        optimize_resource_network([_supply()], [_demand()], [{
            "supply_id": "S1", "demand_id": "D1",
            "unit_cost": 1.0, "capacity": 100.0, "currency": "SAR",
            # Deliberately no transport or treatment cost inputs.
        }])


def test_main_app_explorer_launch_and_direct_module_dispatch_are_registered():
    import ast

    root = Path(__file__).resolve().parents[1]
    app_source = (root / "app.py").read_text(encoding="utf-8")
    ast.parse(app_source)
    assert 'key="explore_open_industrial_resource_intelligence"' in app_source
    assert 'disabled=not _resource_has_access' in app_source
    assert 'st.session_state["shoir_pending_tool_module"] = "Industrial Resource Intelligence"' in app_source
    assert 'elif mod == "Industrial Resource Intelligence":' in app_source
    assert "render_resource_intelligence_workbench(" in app_source


def test_safety_gate_rejects_truthy_string_flags_instead_of_interpreting_them():
    with pytest.raises(ResourceValidationError, match="critical_failure must be a boolean"):
        evaluate_safety_gate(
            critical_failure="false",
            laboratory_required=False,
            laboratory_passed=True,
        )
    with pytest.raises(ResourceValidationError, match="laboratory_passed must be a boolean"):
        evaluate_safety_gate(
            critical_failure=False,
            laboratory_required=True,
            laboratory_passed="pass",
        )


def test_delivery_assessment_rejects_malformed_certificate_requirement():
    from shoir_resource_intelligence import validate_exchange_agreement, assess_exchange_delivery

    agreement = validate_exchange_agreement(_exchange_agreement_payload())
    agreement["certificate_required"] = "false"
    with pytest.raises(ResourceValidationError, match="certificate_required must be a boolean"):
        assess_exchange_delivery(agreement, {
            "delivery_date": "2026-11-12",
            "delivered_quantity": 100,
            "quality": {"pH": 7.0, "TDS_mg_l": 300},
        })


def test_resource_passport_revision_history_verifies_parent_and_content_hashes():
    from shoir_resource_intelligence import (
        append_resource_passport_revision,
        verify_resource_passport_history,
    )

    passport = validate_resource_passport({
        "facility_id": "FAC-A", "resource_id": "RES-1",
        "name": "Recovered water", "resource_type": "Water",
        "available_quantity": 10, "unit": "m3/day",
        "provenance": "IMPORTED", "quality": {"pH": 7.2},
    })
    history = append_resource_passport_revision([], passport, actor="engineer-a")
    second_passport = {**passport, "available_quantity": 12}
    history = append_resource_passport_revision(history, second_passport, actor="engineer-b")
    checked = verify_resource_passport_history(history)
    assert checked["status"] == "VALID_HASH_CHAINS"
    assert checked["resources"][0]["revision_count"] == 2
    assert history[1]["previous_revision_sha256"] == history[0]["revision_sha256"]


def test_resource_passport_revision_verifier_detects_snapshot_tampering():
    from shoir_resource_intelligence import (
        append_resource_passport_revision,
        verify_resource_passport_history,
    )

    passport = validate_resource_passport({
        "facility_id": "FAC-A", "resource_id": "RES-2",
        "name": "Recovered water", "resource_type": "Water",
        "available_quantity": 10, "unit": "m3/day",
        "provenance": "MANUAL",
    })
    history = append_resource_passport_revision([], passport, actor="engineer-a")
    tampered = [dict(history[0])]
    tampered[0]["passport_snapshot"] = {
        **tampered[0]["passport_snapshot"],
        "available_quantity": 999,
    }
    result = verify_resource_passport_history(tampered)
    assert result["status"] == "INTEGRITY_CHECK_FAILED"
    assert "content hash does not match" in result["resources"][0]["issues"][0]


def test_resource_passport_revision_append_refuses_to_extend_a_broken_chain():
    from shoir_resource_intelligence import (
        append_resource_passport_revision,
        verify_resource_passport_history,
    )

    passport = validate_resource_passport({
        "facility_id": "FAC-A", "resource_id": "RES-3",
        "name": "Recovered water", "resource_type": "Water",
        "available_quantity": 10, "unit": "m3/day",
        "provenance": "MANUAL",
    })
    history = append_resource_passport_revision([], passport, actor="engineer-a")
    history[0]["recorded_by"] = "tampered-actor"
    assert verify_resource_passport_history(history)["status"] == "INTEGRITY_CHECK_FAILED"
    with pytest.raises(ResourceValidationError, match="failed its integrity check"):
        append_resource_passport_revision(history, passport, actor="engineer-b")


def test_performance_persistence_monitor_flags_repeated_normalized_degradation():
    from shoir_resource_intelligence import monitor_resource_intensity_persistence

    observations = [
        {"timestamp": "2026-11-01T00:00:00+00:00", "usage": 90, "production": 100},
        {"timestamp": "2026-11-08T00:00:00+00:00", "usage": 110, "production": 100},
        {"timestamp": "2026-11-15T00:00:00+00:00", "usage": 112, "production": 100},
    ]
    result = monitor_resource_intensity_persistence(
        baseline_usage=100,
        baseline_production=100,
        observations=observations,
        usage_unit="m3",
        production_unit="tonne",
        degradation_threshold_percent=5,
        required_consecutive_periods=2,
    )
    assert result["status"] == "PERSISTENCE_ALERT"
    assert result["trailing_degradation_periods"] == 2
    assert result["persistence_alert"] is True
    assert result["verified_savings"] is None
    assert result["causality_verified"] is False


def test_performance_persistence_monitor_requires_unique_ascending_timezone_aware_periods():
    from shoir_resource_intelligence import monitor_resource_intensity_persistence

    with pytest.raises(ResourceValidationError, match="timezone-aware"):
        monitor_resource_intensity_persistence(
            100, 100,
            [
                {"timestamp": "2026-11-01", "usage": 100, "production": 100},
                {"timestamp": "2026-11-02", "usage": 100, "production": 100},
            ],
            usage_unit="m3", production_unit="tonne",
        )
    with pytest.raises(ResourceValidationError, match="unique, ascending"):
        monitor_resource_intensity_persistence(
            100, 100,
            [
                {"timestamp": "2026-11-02T00:00:00+00:00", "usage": 100, "production": 100},
                {"timestamp": "2026-11-01T00:00:00+00:00", "usage": 100, "production": 100},
            ],
            usage_unit="m3", production_unit="tonne",
        )


def test_period_aligned_optimizer_solves_each_period_within_its_own_supply_pool():
    from shoir_resource_intelligence import optimize_period_aligned_resource_network

    supplies = [
        {**_supply("S-MON", 100), "period_id": "2026-11-16"},
        {**_supply("S-TUE", 60), "period_id": "2026-11-17"},
    ]
    demands = [
        {**_demand("D-MON", 80), "period_id": "2026-11-16"},
        {**_demand("D-TUE", 50), "period_id": "2026-11-17"},
    ]
    routes = [
        {**_route("S-MON", "D-MON"), "capacity": 90, "period_id": "2026-11-16"},
        {**_route("S-TUE", "D-TUE"), "capacity": 55, "period_id": "2026-11-17"},
    ]
    result = optimize_period_aligned_resource_network(supplies, demands, routes)
    assert result["status"] == "OPTIMAL_BY_PERIOD"
    assert result["period_count"] == 2
    assert len(result["allocations"]) == 2
    assert {item["period_id"] for item in result["allocations"]} == {"2026-11-16", "2026-11-17"}
    assert result["storage_or_carryover"] == "NOT_MODELED"


def test_period_aligned_optimizer_does_not_carry_surplus_into_a_later_period():
    from shoir_resource_intelligence import optimize_period_aligned_resource_network

    supplies = [
        {**_supply("S-MON", 100), "period_id": "2026-11-16"},
    ]
    demands = [
        {**_demand("D-TUE", 80), "period_id": "2026-11-17"},
    ]
    routes = [
        {**_route("S-MON", "D-TUE"), "period_id": "2026-11-17"},
    ]
    result = optimize_period_aligned_resource_network(
        supplies, demands, routes, allow_shortage=True,
        shortage_penalty_per_unit=1_000_000,
        shortage_penalty_currency="SAR",
    )
    assert result["status"] == "FEASIBLE_WITH_SHORTAGE"
    assert result["allocations"] == []
    assert result["unmet_demand_total"] == pytest.approx(80)
    assert result["unused_supply_periods"] == ["2026-11-16"]
    assert result["periods"][0]["period_id"] == "2026-11-17"


def test_period_aligned_optimizer_rejects_missing_period_identifiers():
    from shoir_resource_intelligence import optimize_period_aligned_resource_network

    with pytest.raises(ResourceValidationError, match="period_id"):
        optimize_period_aligned_resource_network(
            [_supply()],
            [{**_demand(), "period_id": "2026-11-16"}],
            [],
        )


def test_period_aligned_optimizer_keeps_period_route_capacity_and_quality_gates():
    from shoir_resource_intelligence import optimize_period_aligned_resource_network

    supply = {**_supply(quality={"pH": 3.0}), "period_id": "2026-11-16"}
    demand = {
        **_demand(limits={"pH": {"min": 6.5, "max": 8.5}}),
        "period_id": "2026-11-16",
    }
    route = {**_route(), "capacity": 40, "period_id": "2026-11-16"}
    result = optimize_period_aligned_resource_network([supply], [demand], [route])
    assert result["status"] == "INFEASIBLE"
    assert result["periods"][0]["rejected_routes"][0]["status"] == "TECHNICALLY_INCOMPATIBLE"


def test_period_optimizer_reports_complete_shortage_when_all_supply_is_unavailable():
    from shoir_resource_intelligence import optimize_period_aligned_resource_network

    result = optimize_period_aligned_resource_network(
        supplies=[],
        demands=[{**_demand("D-NONE", 25), "period_id": "2026-11-20"}],
        routes=[],
        allow_shortage=True,
        shortage_penalty_per_unit=1_000_000,
        shortage_penalty_currency="SAR",
    )
    assert result["status"] == "FEASIBLE_WITH_SHORTAGE"
    assert result["allocations"] == []
    assert result["unmet_demand_total"] == pytest.approx(25)
    assert result["periods"][0]["unmet_demand"][0]["quantity"] == pytest.approx(25)


def test_period_optimizer_rejects_routes_without_same_period_supply():
    from shoir_resource_intelligence import optimize_period_aligned_resource_network

    result = optimize_period_aligned_resource_network(
        supplies=[{**_supply("S-MON", 100), "period_id": "2026-11-16"}],
        demands=[{**_demand("D-TUE", 80), "period_id": "2026-11-17"}],
        routes=[{**_route("S-MON", "D-TUE"), "period_id": "2026-11-17"}],
        allow_shortage=True,
        shortage_penalty_per_unit=1_000_000,
        shortage_penalty_currency="SAR",
    )
    assert result["status"] == "FEASIBLE_WITH_SHORTAGE"
    rejected = result["periods"][0]["rejected_routes"]
    assert rejected[0]["status"] == "REJECTED_NO_SAME_PERIOD_SUPPLY"
    assert result["unmet_demand_total"] == pytest.approx(80)


def test_period_optimizer_reports_routes_outside_all_demand_periods():
    from shoir_resource_intelligence import optimize_period_aligned_resource_network

    result = optimize_period_aligned_resource_network(
        supplies=[{**_supply("S-1", 100), "period_id": "2026-11-16"}],
        demands=[{**_demand("D-1", 50), "period_id": "2026-11-16"}],
        routes=[
            {**_route("S-1", "D-1"), "period_id": "2026-11-16"},
            {**_route("S-1", "D-1"), "period_id": "2026-11-18"},
        ],
    )
    assert result["status"] == "OPTIMAL_BY_PERIOD"
    assert result["unexpected_route_periods"] == ["2026-11-18"]
    assert result["rejected_routes_outside_demand_periods"][0]["status"] == "REJECTED_ROUTE_PERIOD_WITHOUT_DEMAND"


def test_period_optimizer_rejects_non_boolean_shortage_control():
    from shoir_resource_intelligence import optimize_period_aligned_resource_network

    with pytest.raises(ResourceValidationError, match="allow_shortage must be a boolean"):
        optimize_period_aligned_resource_network(
            supplies=[{**_supply(), "period_id": "2026-11-16"}],
            demands=[{**_demand(), "period_id": "2026-11-16"}],
            routes=[{**_route(), "period_id": "2026-11-16"}],
            allow_shortage="true",
        )


def test_resource_substitution_candidate_requires_product_equipment_lab_and_approval_evidence():
    from shoir_resource_intelligence import assess_resource_substitution

    candidate = _supply(quality={"pH": 7.0, "TDS_mg_l": 250})
    requirement = _demand(limits={"pH": {"min": 6.5, "max": 8.5}, "TDS_mg_l": {"max": 500}})
    pending = assess_resource_substitution(candidate, requirement)
    assert pending["status"] == "CANDIDATE_REQUIRES_QUALIFICATION"
    assert pending["substitution_authorized"] is False
    assert len(pending["blockers"]) >= 6

    qualified = assess_resource_substitution(
        candidate,
        requirement,
        product_quality_status="PASS",
        equipment_compatibility_status="PASS",
        laboratory_evidence_reference="LAB-SUB-1",
        engineering_review_reference="ENG-SUB-1",
        safety_review_reference="HSE-SUB-1",
        environmental_review_reference="ENV-SUB-1",
    )
    assert qualified["status"] == "QUALIFICATION_REFERENCES_RECORDED_PENDING_INDEPENDENT_REVIEW"
    assert qualified["independent_verification"] == "NOT_PERFORMED"
    assert qualified["operational_authorization"] is False


def test_resource_substitution_rejects_incompatible_or_failed_candidates():
    from shoir_resource_intelligence import assess_resource_substitution

    candidate = _supply(quality={"pH": 3.0})
    requirement = _demand(limits={"pH": {"min": 6.5, "max": 8.5}})
    incompatible = assess_resource_substitution(candidate, requirement)
    assert incompatible["status"] == "REJECTED"
    failed = assess_resource_substitution(
        _supply(),
        _demand(),
        product_quality_status="FAIL",
    )
    assert failed["status"] == "REJECTED"


def _environmental_factor_set():
    return {
        "freshwater": {"value": 0.5, "unit": "kgCO2e/m3", "source_reference": "FACTOR-WATER", "version": "v1"},
        "wastewater": {"value": 0.2, "unit": "kgCO2e/m3", "source_reference": "FACTOR-WW", "version": "v1"},
        "electricity": {"value": 0.4, "unit": "kgCO2e/kWh", "source_reference": "FACTOR-ELEC", "version": "v1"},
        "fuel": {"value": 0.25, "unit": "kgCO2e/kWh", "source_reference": "FACTOR-FUEL", "version": "v1"},
        "waste_diversion": {"value": 0.1, "unit": "kgCO2e/kg", "source_reference": "FACTOR-WASTE", "version": "v1"},
        "transport": {"value": 0.08, "unit": "kgCO2e/tonne-km", "source_reference": "FACTOR-TRANSPORT", "version": "v1"},
        "chemical": {"value": 0.3, "unit": "kgCO2e/kg", "source_reference": "FACTOR-CHEM", "version": "v1"},
        "residual_waste": {"value": 0.15, "unit": "kgCO2e/kg", "source_reference": "FACTOR-RESIDUAL", "version": "v1"},
    }


def test_environmental_impact_calculates_avoided_emissions_less_added_burdens():
    from shoir_resource_intelligence import calculate_environmental_impact

    result = calculate_environmental_impact(
        reporting_period="2026-11",
        facility_boundary="FAC-A process water and utilities",
        geography="Saudi Arabia",
        avoided_freshwater_m3=100,
        avoided_wastewater_m3=50,
        avoided_electricity_kwh=1000,
        avoided_fuel_kwh=200,
        diverted_waste_kg=100,
        added_treatment_electricity_kwh=250,
        added_transport_tonne_km=100,
        added_chemical_kg=20,
        added_residual_waste_kg=10,
        factors=_environmental_factor_set(),
        evidence_status="MEASURED",
    )
    assert result["gross_avoided_emissions_kgco2e"] == pytest.approx(520)
    assert result["additional_burden_kgco2e"] == pytest.approx(115.5)
    assert result["net_avoided_emissions_kgco2e"] == pytest.approx(404.5)
    assert result["evidence_status"] == "MEASURED"
    assert result["independent_verification"] == "NOT_ESTABLISHED"


def test_environmental_impact_requires_factor_references_versions_and_exact_units():
    from shoir_resource_intelligence import calculate_environmental_impact

    factors = _environmental_factor_set()
    del factors["transport"]
    with pytest.raises(ResourceValidationError, match="factor transport is required"):
        calculate_environmental_impact(
            reporting_period="2026-11", facility_boundary="FAC-A", geography="Saudi Arabia",
            avoided_freshwater_m3=0, avoided_wastewater_m3=0, avoided_electricity_kwh=0,
            avoided_fuel_kwh=0, diverted_waste_kg=0, added_treatment_electricity_kwh=0,
            added_transport_tonne_km=0, added_chemical_kg=0, added_residual_waste_kg=0,
            factors=factors,
        )
    factors = _environmental_factor_set()
    factors["electricity"]["unit"] = "kWh"
    with pytest.raises(ResourceValidationError, match="kgCO2e/kWh"):
        calculate_environmental_impact(
            reporting_period="2026-11", facility_boundary="FAC-A", geography="Saudi Arabia",
            avoided_freshwater_m3=0, avoided_wastewater_m3=0, avoided_electricity_kwh=0,
            avoided_fuel_kwh=0, diverted_waste_kg=0, added_treatment_electricity_kwh=0,
            added_transport_tonne_km=0, added_chemical_kg=0, added_residual_waste_kg=0,
            factors=factors,
        )


def test_environmental_impact_downgrades_claim_of_independent_verification():
    from shoir_resource_intelligence import calculate_environmental_impact

    result = calculate_environmental_impact(
        reporting_period="2026-11", facility_boundary="FAC-A", geography="Saudi Arabia",
        avoided_freshwater_m3=1, avoided_wastewater_m3=0, avoided_electricity_kwh=0,
        avoided_fuel_kwh=0, diverted_waste_kg=0, added_treatment_electricity_kwh=0,
        added_transport_tonne_km=0, added_chemical_kg=0, added_residual_waste_kg=0,
        factors=_environmental_factor_set(),
        evidence_status="INDEPENDENTLY_VERIFIED",
    )
    assert result["evidence_status"] == "MEASURED_PENDING_INDEPENDENT_EVIDENCE"
    assert result["independent_verification"] == "NOT_ESTABLISHED"


def test_investment_prioritization_is_transparent_and_keeps_safety_rejected_projects_blocked():
    from shoir_resource_intelligence import rank_resource_improvement_projects

    projects = [
        {
            "project_id": "P1", "name": "Water recovery",
            "feasibility_score": 5, "resource_impact_score": 5, "reliability_score": 4,
            "data_confidence_score": 4, "risk_score": 2, "implementation_difficulty_score": 2,
            "capex": 100000, "annual_gross_benefit": 80000, "annual_opex": 20000,
            "currency": "SAR", "safety_status": "APPROVAL_PENDING", "evidence_reference": "CASE-1",
        },
        {
            "project_id": "P2", "name": "Unsafe bypass",
            "feasibility_score": 5, "resource_impact_score": 5, "reliability_score": 5,
            "data_confidence_score": 5, "risk_score": 1, "implementation_difficulty_score": 1,
            "capex": 10000, "annual_gross_benefit": 100000, "annual_opex": 1000,
            "currency": "SAR", "safety_status": "REJECTED", "evidence_reference": "CASE-2",
        },
    ]
    result = rank_resource_improvement_projects(
        projects,
        weights={
            "feasibility": 0.25, "resource_impact": 0.25, "reliability": 0.15,
            "data_confidence": 0.15, "risk": 0.10, "implementation_difficulty": 0.10,
        },
    )
    by_id = {item["project_id"]: item for item in result["ranked_projects"]}
    assert by_id["P1"]["simple_payback_years"] == pytest.approx(1.6666667)
    assert by_id["P1"]["priority_is_financial_roi"] is False
    assert by_id["P2"]["project_status"] == "BLOCKED_SAFETY"
    assert by_id["P2"]["priority_rank"] > by_id["P1"]["priority_rank"]


def test_project_prioritization_rejects_unknown_weights_currency_and_safety_status():
    from shoir_resource_intelligence import rank_resource_improvement_projects

    project = {
        "project_id": "P-1", "name": "Recovery project",
        "feasibility_score": 4, "resource_impact_score": 4, "reliability_score": 4,
        "data_confidence_score": 4, "risk_score": 2, "implementation_difficulty_score": 2,
        "capex": 1000, "annual_gross_benefit": 2000, "annual_opex": 500,
        "currency": "SAR", "safety_status": "APPROVAL_PENDING",
    }
    weights = {
        "feasibility": 0.2, "resource_impact": 0.2, "reliability": 0.2,
        "data_confidence": 0.2, "risk": 0.1, "implementation_difficulty": 0.1,
    }
    with pytest.raises(ResourceValidationError, match="Unknown project scoring weight"):
        rank_resource_improvement_projects([project], weights={**weights, "unapproved_bonus": 0.5})
    with pytest.raises(ResourceValidationError, match="three-letter currency"):
        rank_resource_improvement_projects([{
            **project, "currency": "dollars",
        }], weights=weights)
    with pytest.raises(ResourceValidationError, match="recognized safety gate status"):
        rank_resource_improvement_projects([{
            **project, "safety_status": "APPROVED_BY_AI",
        }], weights=weights)


def test_environmental_impact_rejects_unknown_factor_categories():
    from shoir_resource_intelligence import calculate_environmental_impact

    with pytest.raises(ResourceValidationError, match="Unknown environmental factor"):
        calculate_environmental_impact(
            reporting_period="2026-11", facility_boundary="FAC-A", geography="Saudi Arabia",
            avoided_freshwater_m3=0, avoided_wastewater_m3=0, avoided_electricity_kwh=0,
            avoided_fuel_kwh=0, diverted_waste_kg=0, added_treatment_electricity_kwh=0,
            added_transport_tonne_km=0, added_chemical_kg=0, added_residual_waste_kg=0,
            factors={**_environmental_factor_set(), "unverified_avoided_carbon": {"value": 99}},
        )


def test_resource_intelligence_ui_declared_tabs_and_indexes_are_consistent():
    import ast
    import re

    root = Path(__file__).resolve().parents[1]
    source = (root / "shoir_resource_intelligence_ui.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    tabs_count = None
    tab_indexes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "tabs" for target in node.targets
        ):
            call = node.value
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "tabs":
                tabs_count = len(ast.literal_eval(call.args[0]))
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "tabs":
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int):
                tab_indexes.append(node.slice.value)
    assert tabs_count == 15
    assert tab_indexes
    assert max(tab_indexes) < tabs_count
    assert '"Environmental Impact"' in source
    assert '"Investment Prioritization"' in source
    assert '"Reports"' in source


def test_combined_network_scenario_applies_supply_demand_and_cost_shocks_together():
    from shoir_resource_intelligence import simulate_resource_network_scenario

    result = simulate_resource_network_scenario(
        [_supply(quantity=100)],
        [_demand(quantity=60)],
        [_route()],
        [
            {"type": "SUPPLY_REDUCTION", "supply_id": "S1", "fraction": 0.5},
            {"type": "DEMAND_MULTIPLIER", "demand_id": "D1", "multiplier": 1.2},
            {"type": "ROUTE_RESOURCE_COST_MULTIPLIER", "supply_id": "S1", "demand_id": "D1", "multiplier": 2},
        ],
        scenario_id="SCN-1",
        scenario_name="Supply loss and demand spike",
        shortage_penalty_per_unit=1000,
            shortage_penalty_currency="SAR",
    )
    assert result["baseline_unmet_quantity"] == pytest.approx(0)
    assert result["stressed_unmet_quantity"] == pytest.approx(22)
    assert result["change_in_unmet_quantity"] == pytest.approx(22)
    assert result["stressed"]["allocations"][0]["quantity"] == pytest.approx(50)
    assert result["recovery_time"] is None
    assert result["probability"] is None


def test_combined_network_scenario_quality_failure_rejects_route_and_reports_shortage():
    from shoir_resource_intelligence import simulate_resource_network_scenario

    result = simulate_resource_network_scenario(
        [_supply(quantity=100)],
        [_demand(quantity=60, limits={"pH": {"min": 6.5, "max": 8.5}})],
        [_route()],
        [{"type": "SUPPLY_QUALITY_OVERRIDE", "supply_id": "S1", "quality": {"pH": 3.0}}],
        scenario_id="SCN-QUALITY",
        scenario_name="Supplier quality failure",
        shortage_penalty_per_unit=500,
        shortage_penalty_currency="SAR",
    )
    assert result["stressed"]["status"] == "FEASIBLE_WITH_SHORTAGE"
    assert result["stressed"]["allocations"] == []
    assert result["stressed_unmet_quantity"] == pytest.approx(60)
    assert result["stressed"]["rejected_routes"][0]["status"] == "TECHNICALLY_INCOMPATIBLE"


def test_combined_network_scenario_requires_explicit_targets_and_supported_shock_types():
    from shoir_resource_intelligence import simulate_resource_network_scenario

    base = ([_supply()], [_demand()], [_route()])
    with pytest.raises(ResourceValidationError, match="exactly one supply"):
        simulate_resource_network_scenario(
            *base, [{"type": "SUPPLY_REDUCTION", "supply_id": "missing", "fraction": 0.2}],
            scenario_id="SCN-X", scenario_name="Unknown target",
            shortage_penalty_per_unit=1000,
            shortage_penalty_currency="SAR",
        )
    with pytest.raises(ResourceValidationError, match="Unsupported resource-network shock type"):
        simulate_resource_network_scenario(
            *base, [{"type": "AI_APPROVAL_OVERRIDE"}],
            scenario_id="SCN-X", scenario_name="Invalid shock",
            shortage_penalty_per_unit=1000,
            shortage_penalty_currency="SAR",
        )




def test_network_optimizer_rejects_mixed_route_currencies():
    route_two = {**_route("S2", "D2"), "currency": "USD"}
    with pytest.raises(ResourceValidationError, match="same currency"):
        optimize_resource_network(
            [_supply("S1"), _supply("S2")],
            [_demand("D1"), _demand("D2")],
            [_route("S1", "D1"), route_two],
        )


def test_shortage_penalty_currency_must_match_route_cost_currency():
    with pytest.raises(ResourceValidationError, match="must match the exchange route currency"):
        optimize_resource_network(
            [_supply()], [_demand()], [_route()],
            allow_shortage=True,
            shortage_penalty_per_unit=1000,
            shortage_penalty_currency="USD",
        )

def test_shortage_optimizers_require_an_explicit_penalty_input():
    with pytest.raises(ResourceValidationError, match="shortage_penalty_per_unit"):
        optimize_resource_network(
            [_supply(quantity=10)], [_demand(quantity=20)], [_route()],
            allow_shortage=True,
        )
    from shoir_resource_intelligence import optimize_period_aligned_resource_network
    with pytest.raises(ResourceValidationError, match="shortage_penalty_per_unit"):
        optimize_period_aligned_resource_network(
            [{**_supply(quantity=10), "period_id": "2026-11-20"}],
            [{**_demand(quantity=20), "period_id": "2026-11-20"}],
            [{**_route(), "period_id": "2026-11-20"}],
            allow_shortage=True,
        )


def test_combined_network_scenario_rejects_zero_demand_multiplier():
    from shoir_resource_intelligence import simulate_resource_network_scenario

    with pytest.raises(ResourceValidationError, match="greater than zero"):
        simulate_resource_network_scenario(
            [_supply()], [_demand()], [_route()],
            [{"type": "DEMAND_MULTIPLIER", "demand_id": "D1", "multiplier": 0}],
            scenario_id="SCN-ZERO", scenario_name="Zero demand",
            shortage_penalty_per_unit=1000,
            shortage_penalty_currency="SAR",
        )
