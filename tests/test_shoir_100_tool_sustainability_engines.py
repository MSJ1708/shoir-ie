"""Golden/boundary fixtures for normalized energy, water/waste, and ROI calculations."""
import pandas as pd
import pytest

from shoir_100_tool_sustainability_engines import analyze_energy_intensity, analyze_water_waste_efficiency, calculate_roi_evidence


def test_energy_intensity_normalizes_baseline_and_keeps_negative_savings_visible():
    result = analyze_energy_intensity([
        {"period":"baseline","production_units":100,"energy_kwh":1000},
        {"period":"after","production_units":120,"energy_kwh":900},
    ], "baseline", tariff_per_kwh=0.2, emission_factor_kg_per_kwh=0.4,
       factor_source="fixture factor", factor_date="2026-10-01")
    metrics = result["metrics"]
    assert metrics["baseline_kwh_per_unit"] == pytest.approx(10)
    assert metrics["total_normalized_baseline_energy_kwh"] == pytest.approx(2200)
    assert metrics["estimated_energy_difference_kwh"] == pytest.approx(1300)
    assert result["period_comparison"].loc[1,"energy_kwh_per_unit"] == pytest.approx(7.5)
    assert result["period_comparison"].loc[1,"estimated_emissions_kg_co2e"] == pytest.approx(360)


def test_energy_comparison_requires_valid_baseline_and_factor_provenance():
    rows=[{"period":"base","production_units":10,"energy_kwh":0}]
    with pytest.raises(ValueError, match="not found"):
        analyze_energy_intensity(rows,"missing")
    with pytest.raises(ValueError, match="source and YYYY-MM-DD"):
        analyze_energy_intensity(rows,"base",emission_factor_kg_per_kwh=0.3)


def test_water_waste_normalization_and_recycling_ratio():
    result=analyze_water_waste_efficiency([
        {"period":"P1","production_units":10,"water_input_m3":100,"wastewater_m3":60,"waste_generated_kg":20,"waste_recycled_kg":5},
        {"period":"P2","production_units":20,"water_input_m3":160,"wastewater_m3":100,"waste_generated_kg":40,"waste_recycled_kg":20},
    ])
    assert result["metrics"]["total_water_input_m3"] == 260
    assert result["metrics"]["total_recycling_rate_percent"] == pytest.approx(25)
    assert result["period_comparison"].loc[0,"water_m3_per_unit"] == pytest.approx(10)


def test_water_waste_rejects_recycled_mass_above_generated_mass():
    with pytest.raises(ValueError, match="cannot exceed"):
        analyze_water_waste_efficiency([{"period":"P1","production_units":10,"water_input_m3":3,"wastewater_m3":2,"waste_generated_kg":1,"waste_recycled_kg":2}])


def test_roi_tracker_never_claims_verified_savings_and_checks_comparable_dates():
    result=calculate_roi_evidence(
        baseline_cost=10000, post_intervention_cost=7000, implementation_cost=1000,
        currency="SAR", measurement_start="2026-01-01", measurement_end="2026-03-31",
        baseline_evidence_reference="BASE-1", post_evidence_reference="POST-1",
        implementation_cost_reference="COST-1", verifier_name="Review Lead", evidence_reviewed=True,
    )
    metrics=result["metrics"]
    assert metrics["gross_cost_change"] == 3000
    assert metrics["net_benefit_after_implementation_cost"] == 2000
    assert metrics["roi_percent"] == 200
    assert metrics["evidence_state"] == "USER_MARKED_REVIEWED_NOT_INDEPENDENTLY_VERIFIED"
    assert metrics["verified_savings"] is False
    with pytest.raises(ValueError, match="earlier than start"):
        calculate_roi_evidence(
            baseline_cost=10,post_intervention_cost=5,implementation_cost=1,currency="SAR",
            measurement_start="2026-03-01",measurement_end="2026-02-01",
            baseline_evidence_reference="",post_evidence_reference="",implementation_cost_reference="",
        )
