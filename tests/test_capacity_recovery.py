"""Regression coverage for validated production bottleneck and capacity recovery."""
import math

import pandas as pd
import pytest

from shoir_capacity_recovery import (
    CALCULATION_VERSION,
    analyze_capacity_recovery,
    calculate_capacity_value_sensitivity,
    list_capacity_outcomes,
    list_capacity_studies,
    load_capacity_study,
    map_imported_station_data,
    record_capacity_outcome,
    save_capacity_study,
    starter_station_table,
)


def reference_stations() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Station": "Prep",
            "Cycle Time (sec/unit)": 30.0,
            "Available Time (min/shift)": 60.0,
            "Availability (%)": 100.0,
            "Parallel Resources": 1,
            "Scenario Cycle Time (sec/unit)": 30.0,
            "Scenario Availability (%)": 100.0,
            "Scenario Parallel Resources": 1,
        },
        {
            "Station": "Inspect",
            "Cycle Time (sec/unit)": 60.0,
            "Available Time (min/shift)": 60.0,
            "Availability (%)": 100.0,
            "Parallel Resources": 1,
            "Scenario Cycle Time (sec/unit)": 50.0,
            "Scenario Availability (%)": 100.0,
            "Scenario Parallel Resources": 1,
        },
    ])


def test_reference_capacity_case_identifies_bottleneck_and_scenario_delta():
    result = analyze_capacity_recovery(reference_stations(), 70)

    assert result["calculation_version"] == CALCULATION_VERSION
    assert result["classification"] == "Calculated deterministic capacity estimate"
    assert result["baseline"]["bottleneck_stations"] == ["Inspect"]
    assert result["baseline"]["gross_capacity_units_per_shift"] == pytest.approx(60)
    assert result["baseline"]["good_capacity_units_per_shift"] == pytest.approx(60)
    assert result["baseline"]["shortfall_units_per_shift"] == pytest.approx(10)
    assert result["scenario"]["bottleneck_stations"] == ["Inspect"]
    assert result["scenario"]["good_capacity_units_per_shift"] == pytest.approx(72)
    assert result["scenario"]["shortfall_units_per_shift"] == pytest.approx(0)
    assert result["delta"]["additional_good_units_per_shift"] == pytest.approx(12)
    assert result["delta"]["capacity_change_pct"] == pytest.approx(20)
    assert result["station_results"]["Baseline Binding Constraint"].tolist() == [False, True]


def test_yield_is_applied_once_to_line_capacity():
    stations = reference_stations().iloc[[0]].copy()
    result = analyze_capacity_recovery(stations, demand_units_per_shift=50, overall_first_pass_yield_pct=75)
    assert result["baseline"]["gross_capacity_units_per_shift"] == pytest.approx(120)
    assert result["baseline"]["good_capacity_units_per_shift"] == pytest.approx(90)
    assert result["baseline"]["shortfall_units_per_shift"] == pytest.approx(0)


@pytest.mark.parametrize("demand", [-1, float("nan"), float("inf"), "not a number"])
def test_demand_rejects_negative_nonfinite_or_nonnumeric_values(demand):
    with pytest.raises(ValueError):
        analyze_capacity_recovery(reference_stations(), demand)


@pytest.mark.parametrize("yield_pct", [-0.1, 100.1, float("nan"), float("inf")])
def test_yield_rejects_out_of_range_or_nonfinite_values(yield_pct):
    with pytest.raises(ValueError):
        analyze_capacity_recovery(reference_stations(), 70, yield_pct)


@pytest.mark.parametrize(
    "column,value",
    [
        ("Cycle Time (sec/unit)", 0),
        ("Cycle Time (sec/unit)", -1),
        ("Cycle Time (sec/unit)", float("inf")),
        ("Available Time (min/shift)", -1),
        ("Availability (%)", 100.1),
        ("Availability (%)", -0.1),
        ("Parallel Resources", 1.5),
        ("Scenario Parallel Resources", 0),
        ("Scenario Cycle Time (sec/unit)", 0),
        ("Scenario Availability (%)", float("nan")),
    ],
)
def test_station_inputs_reject_invalid_values(column, value):
    stations = reference_stations()
    # Keep the fixture assignable on modern pandas even for fractional / NaN cases.
    stations[column] = stations[column].astype(float)
    stations.loc[0, column] = value
    with pytest.raises(ValueError):
        analyze_capacity_recovery(stations, 70)


def test_empty_missing_duplicate_and_ambiguous_station_names_are_rejected():
    with pytest.raises(ValueError, match="at least one station"):
        analyze_capacity_recovery(reference_stations().iloc[0:0], 10)
    with pytest.raises(ValueError, match="missing required columns"):
        analyze_capacity_recovery(pd.DataFrame({"Station": ["A"]}), 10)
    duplicated = reference_stations()
    duplicated.loc[1, "Station"] = "prep"
    with pytest.raises(ValueError, match="unique"):
        analyze_capacity_recovery(duplicated, 10)


def test_deterministic_hash_is_stable_and_changes_when_inputs_change():
    stations = reference_stations()
    first = analyze_capacity_recovery(stations, 70)
    second = analyze_capacity_recovery(stations.copy(), 70)
    changed = stations.copy()
    changed.loc[1, "Scenario Cycle Time (sec/unit)"] = 45
    third = analyze_capacity_recovery(changed, 70)

    assert len(first["input_sha256"]) == 64
    assert first["input_sha256"] == second["input_sha256"]
    assert first["input_sha256"] != third["input_sha256"]


def test_import_mapping_initializes_scenario_as_baseline_and_checks_mapping():
    imported = pd.DataFrame({
        "Workstation": ["Prep", "Inspect"],
        "Cycle": [30, 60],
        "Available": [60, 60],
        "Run %": [100, 95],
        "Machines": [1, 2],
    })
    mapping = {
        "Station": "Workstation",
        "Cycle Time (sec/unit)": "Cycle",
        "Available Time (min/shift)": "Available",
        "Availability (%)": "Run %",
        "Parallel Resources": "Machines",
    }
    result = map_imported_station_data(imported, mapping)
    assert result["Scenario Cycle Time (sec/unit)"].tolist() == [30.0, 60.0]
    assert result["Scenario Availability (%)"].tolist() == [100.0, 95.0]
    assert result["Scenario Parallel Resources"].tolist() == [1, 2]

    bad_mapping = dict(mapping)
    bad_mapping["Parallel Resources"] = "Cycle"
    with pytest.raises(ValueError, match="different source column"):
        map_imported_station_data(imported, bad_mapping)
    with pytest.raises(ValueError, match="Choose a source column"):
        map_imported_station_data(imported, {k: v for k, v in mapping.items() if k != "Station"})


def test_financial_sensitivity_is_explicit_and_arithmetic_is_independent():
    result = calculate_capacity_value_sensitivity(12, 250, 5, 5000)
    assert result["classification"].startswith("Estimated scenario sensitivity")
    assert result["modeled_incremental_units_per_year"] == pytest.approx(3000)
    assert result["modeled_annual_gross_value"] == pytest.approx(15000)
    assert result["modeled_first_year_net_value"] == pytest.approx(10000)
    assert result["roi_percent"] == pytest.approx(200)
    assert result["payback_months"] == pytest.approx(4)


def test_study_persistence_is_reproducible_and_owner_scoped(tmp_path):
    path = str(tmp_path / "capacity.db")
    saved = save_capacity_study(
        "alice",
        "Reference capacity study",
        reference_stations(),
        70,
        overall_first_pass_yield_pct=100,
        data_source="test fixture / measured reference case",
        operating_shifts_per_year=250,
        contribution_or_avoided_cost_per_unit=5,
        implementation_cost=5000,
        decision="Run controlled pilot",
        rationale="Compare source-referenced actual output before adopting the scenario.",
        db_path=path,
    )
    assert saved["study_id"].startswith("CAP-")
    assert saved["calculation_version"] == CALCULATION_VERSION
    assert len(saved["input_sha256"]) == 64
    assert len(saved["result_sha256"]) == 64
    assert saved["results"]["baseline"]["good_capacity_units_per_shift"] == pytest.approx(60)
    assert saved["results"]["scenario"]["good_capacity_units_per_shift"] == pytest.approx(72)
    assert saved["results"]["financial_sensitivity"]["modeled_annual_gross_value"] == pytest.approx(15000)

    loaded = load_capacity_study(saved["study_id"], "alice", db_path=path)
    assert loaded["inputs"] == saved["inputs"]
    assert loaded["results"] == saved["results"]
    assert load_capacity_study(saved["study_id"], "bob", db_path=path) is None
    assert list_capacity_studies("alice", db_path=path)["study_id"].tolist() == [saved["study_id"]]
    assert list_capacity_studies("bob", db_path=path).empty


def test_outcome_requires_source_and_owner_and_records_tolerance_comparison(tmp_path):
    path = str(tmp_path / "capacity.db")
    study = save_capacity_study(
        "alice", "Outcomes", reference_stations(), 70,
        data_source="synthetic reference case", db_path=path,
    )
    with pytest.raises(ValueError, match="does not exist for this owner"):
        record_capacity_outcome(
            study["study_id"], "bob", 69,
            measurement_period="2026-10-01",
            source_reference="MES export", db_path=path,
        )
    with pytest.raises(ValueError, match="source reference is required"):
        record_capacity_outcome(
            study["study_id"], "alice", 69,
            measurement_period="2026-10-01",
            source_reference=" ", db_path=path,
        )

    outcome = record_capacity_outcome(
        study["study_id"], "alice", 69,
        measurement_period="2026-10-01 day shift",
        source_reference="MES export RUN-42",
        tolerance_pct=5,
        notes="Submitted measurement; source not independently authenticated.",
        db_path=path,
    )
    assert outcome["expected_good_units_per_shift"] == pytest.approx(72)
    assert outcome["variance_units_per_shift"] == pytest.approx(-3)
    assert outcome["variance_pct"] == pytest.approx(-3 / 72 * 100)
    assert outcome["within_tolerance"] is True
    assert outcome["classification"].startswith("Measured input with source reference")
    assert len(outcome["outcome_sha256"]) == 64
    listed = list_capacity_outcomes(study["study_id"], "alice", db_path=path)
    assert len(listed) == 1
    assert listed.iloc[0]["actual_good_units"] == pytest.approx(69)
    assert list_capacity_outcomes(study["study_id"], "bob", db_path=path).empty


def test_starter_data_is_marked_for_demo_and_returns_no_claim_of_verified_savings():
    result = analyze_capacity_recovery(starter_station_table(), 300, 96.0)
    assert result["warnings"]
    assert "not a calibrated digital twin" in " ".join(result["warnings"])
    assert not math.isnan(result["baseline"]["good_capacity_units_per_shift"])
