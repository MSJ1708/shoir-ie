import io
import math

import pandas as pd
import pytest

from shoir_capacity_recovery import (
    FORMULA_VERSION,
    analyze_capacity_recovery,
    build_capacity_recovery_excel,
    build_evidence_manifest,
    calculate_line_metrics,
    estimate_downtime_recovery,
    validate_production_events,
)


def sample_events():
    return pd.DataFrame({
        "Line": ["A", "B"],
        "PlannedMin": [480, 480],
        "DowntimeMin": [60, 120],
        "IdealCycleSec": [60, 120],
        "TotalCount": [400, 150],
        "GoodCount": [380, 145],
    })


def test_reference_metrics_match_independent_calculation():
    result = calculate_line_metrics(sample_events()).set_index("Line")

    # Line A: availability 420/480, performance 400/420, quality 380/400.
    assert result.loc["A", "AvailabilityPct"] == pytest.approx(87.5)
    assert result.loc["A", "PerformancePct"] == pytest.approx(400 / 420 * 100)
    assert result.loc["A", "QualityPct"] == pytest.approx(95.0)
    assert result.loc["A", "OEEPct"] == pytest.approx(79.1666666667)
    assert result.loc["A", "TheoreticalCapacityUnits"] == pytest.approx(480.0)
    assert result.loc["A", "CapacityAtTargetOEE_85Pct"] == pytest.approx(408.0)
    assert result.loc["A", "ConstraintSignal"] == "No lowest-OEE signal"

    # Line B is calculated independently from its own planned/runtime/count values.
    assert result.loc["B", "AvailabilityPct"] == pytest.approx(75.0)
    assert result.loc["B", "PerformancePct"] == pytest.approx(150 / 360 * 2 * 100)
    assert result.loc["B", "QualityPct"] == pytest.approx(145 / 150 * 100)
    assert result.loc["B", "OEEPct"] == pytest.approx(60.4166666667)
    assert result.loc["B", "ConstraintSignal"] == "Candidate — lowest OEE; review flow data"


def test_validator_does_not_mutate_input_and_flags_bad_values():
    events = sample_events()
    original = events.copy(deep=True)
    # Keep the test column permissive so pandas does not reject the bad value
    # before the production validator receives it.
    events["TotalCount"] = events["TotalCount"].astype("object")
    events.loc[0, "TotalCount"] = "not-a-count"

    validation_input = events.copy(deep=True)
    normalized, report = validate_production_events(events)

    assert not report["valid"]
    assert any("TotalCount" in error for error in report["errors"])
    assert normalized.loc[0, "TotalCount"] != 0
    pd.testing.assert_frame_equal(events, validation_input)
    assert original.loc[0, "TotalCount"] == 400


@pytest.mark.parametrize(
    "column,value,expected",
    [
        ("PlannedMin", 0, "PlannedMin must be greater than zero"),
        ("IdealCycleSec", -1, "IdealCycleSec must be greater than zero"),
        ("DowntimeMin", 481, "DowntimeMin exceeds PlannedMin"),
        ("GoodCount", 401, "GoodCount exceeds TotalCount"),
        ("TotalCount", float("inf"), "non-finite"),
    ],
)
def test_invalid_engineering_inputs_are_rejected(column, value, expected):
    events = sample_events()
    # Test the engine’s validation, not pandas’ typed-assignment guard.
    events[column] = events[column].astype("object")
    events.loc[0, column] = value
    with pytest.raises(ValueError, match=expected):
        calculate_line_metrics(events)


def test_duplicate_columns_are_reported_without_crashing():
    events = sample_events()
    duplicated = pd.concat([events, events[["TotalCount"]]], axis=1)

    _, report = validate_production_events(duplicated)

    assert not report["valid"]
    assert "Duplicate column names are not allowed." in report["errors"]


def test_missing_columns_and_empty_data_are_reported():
    _, missing = validate_production_events(pd.DataFrame({"Line": ["A"]}))
    assert not missing["valid"]
    assert any("Missing required column" in error for error in missing["errors"])

    _, empty = validate_production_events(pd.DataFrame(columns=[
        "Line", "PlannedMin", "DowntimeMin", "IdealCycleSec", "TotalCount", "GoodCount"
    ]))
    assert not empty["valid"]
    assert "Production events are empty." in empty["errors"]


def test_recovery_scenario_is_bounded_and_explicitly_simulated():
    result = estimate_downtime_recovery(sample_events(), 0.5).set_index("Line")
    assert result.loc["A", "RecoveredDowntimeMin"] == pytest.approx(30)
    assert result.loc["A", "EstimatedAdditionalGoodUnits"] == pytest.approx(27.1428571429)
    assert result.loc["B", "RecoveredDowntimeMin"] == pytest.approx(60)
    assert result.loc["B", "EstimatedAdditionalGoodUnits"] == pytest.approx(24.1666666667)
    assert set(result["ScenarioClassification"]) == {"Simulated"}
    assert result.loc["A", "Assumption"]

    for invalid in (-0.01, 1.01, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            estimate_downtime_recovery(sample_events(), invalid)


def test_zero_output_is_not_fabricated_into_a_zero_quality_claim():
    events = sample_events()
    events.loc[0, ["TotalCount", "GoodCount"]] = [0, 0]
    _, validation = validate_production_events(events)
    assert validation["valid"]
    assert any("zero output" in warning for warning in validation["warnings"])
    metrics = calculate_line_metrics(events).set_index("Line")
    assert math.isnan(metrics.loc["A", "QualityPct"])
    assert metrics.loc["A", "OEEStatus"] == "Not available"
    assert metrics.loc["A", "ConstraintSignal"] == "Not assessed — OEE unavailable"


def test_evidence_manifest_has_stable_input_hash_and_versioned_formulas():
    events = sample_events()
    first = analyze_capacity_recovery(
        events, downtime_reduction_fraction=0.25,
        source_name="shift-data.csv", source_type="imported",
    )
    second = analyze_capacity_recovery(
        events, downtime_reduction_fraction=0.25,
        source_name="shift-data.csv", source_type="imported",
    )
    evidence = first["evidence"]
    assert first["validation"]["valid"]
    assert evidence["formula_version"] == FORMULA_VERSION
    assert evidence["source_type"] == "imported"
    assert evidence["input_sha256"] == second["evidence"]["input_sha256"]
    assert evidence["result_sha256"] == second["evidence"]["result_sha256"]
    assert evidence["result_classification"] == "Calculated"
    assert evidence["scenario_classification"] == "Simulated"
    assert evidence["scenario_parameters"] == {"downtime_reduction_fraction": 0.25}
    assert "not independent verification" in evidence["assumptions"][-1]


def test_scenario_parameter_is_required_for_scenario_evidence():
    events = sample_events()
    metrics = calculate_line_metrics(events)
    scenario = estimate_downtime_recovery(events, 0.25)

    with pytest.raises(ValueError, match="fraction is required"):
        build_evidence_manifest(events, metrics, scenario)


def test_excel_export_keeps_untrusted_line_labels_as_text():
    from openpyxl import load_workbook

    events = sample_events()
    malicious_label = '=HYPERLINK("https://example.invalid","open")'
    events.loc[0, "Line"] = malicious_label
    result = analyze_capacity_recovery(events, downtime_reduction_fraction=0.25)

    workbook_bytes = build_capacity_recovery_excel(
        result["line_metrics"], result["recovery_scenario"], result["evidence"]
    )
    workbook = load_workbook(io.BytesIO(workbook_bytes), data_only=False)
    cell = workbook["Baseline Metrics"]["A2"]

    assert cell.value == malicious_label
    assert cell.data_type != "f"


def test_invalid_data_cannot_produce_evidence_or_scenario_results():
    events = sample_events()
    events.loc[0, "GoodCount"] = 999
    result = analyze_capacity_recovery(events)
    assert not result["validation"]["valid"]
    assert result["evidence"] is None
    assert result["line_metrics"].empty
    assert result["recovery_scenario"].empty
    with pytest.raises(ValueError, match="Cannot create evidence"):
        build_evidence_manifest(events, pd.DataFrame())
