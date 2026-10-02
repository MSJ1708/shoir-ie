import pandas as pd

from industrial_platform import model_health, validate_table


def test_validation_center_detects_range_errors_and_reports_health():
    frame = pd.DataFrame({
        "Metric": ["Capacity", "Service Level"],
        "Value": [12000, 125],
        "Unit": ["units", "%"],
    })
    result = validate_table(
        frame,
        required=["Metric", "Value", "Unit"],
        numeric_ranges={"Value": (0, 100)},
    )
    assert result["valid"] is False
    assert result["errors"]
    health = model_health(frame, feasible=False, solver_status="Blocked")
    assert health["feasibility"] == "Fail"
    assert "data_quality" in health


def test_validation_center_accepts_clean_inputs():
    frame = pd.DataFrame({
        "Metric": ["Capacity", "Service Level"],
        "Value": [12000, 95],
        "Unit": ["units", "%"],
    })
    result = validate_table(
        frame,
        required=["Metric", "Value", "Unit"],
        numeric_ranges={"Value": (0, 20000)},
    )
    assert result["valid"] is True
