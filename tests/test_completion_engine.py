import json
import pandas as pd
import pytest

from shoir_completion_engine import (
    UniversalModuleContract,
    module_contract_audit,
    fractional_factorial,
    replication_plan,
    seasonal_decomposition,
    forecast_backtest,
    optimization_diagnostics,
    connector_probe,
    roi_evidence,
    classify_exception,
    verification_suite,
    build_report_pack,
)


def test_universal_contract_covers_all_required_stages():
    contract = UniversalModuleContract(module="Test Module", purpose="test", run_entrypoint="module:test")
    audit = module_contract_audit([contract])
    assert audit.iloc[0]["Coverage"] == "COMPLETE"
    assert audit.iloc[0]["Missing Stages"] == ""


def test_fractional_factorial_is_reproducible_and_randomized():
    factors = {"A": [-1, 1], "B": [-1, 1], "C": [-1, 1], "D": [-1, 1]}
    first = fractional_factorial(factors, seed=2026)
    second = fractional_factorial(factors, seed=2026)
    assert first.equals(second)
    assert len(first) == 8
    assert first["RunOrder"].tolist() == list(range(1, 9))
    assert set(first["DesignType"]) == {"fractional_factorial_R3"}


def test_replication_planner_creates_blocks_and_replicates():
    design = fractional_factorial({"A": [-1, 1], "B": [-1, 1], "C": [-1, 1]}, randomized=False)
    planned = replication_plan(design, replicates=3, blocks=2, randomize=False)
    assert len(planned) == len(design) * 6
    assert planned["Replication"].nunique() == 3
    assert planned["Block"].nunique() == 2
    assert planned["RunOrder"].tolist() == list(range(1, len(planned) + 1))


def test_forecast_backtest_competes_models_and_returns_intervals():
    series = [100 + 2*i + (5 if i % 7 == 0 else 0) for i in range(40)]
    result = forecast_backtest(series, horizon=5, seasonal_period=7)
    assert result["status"] == "OK"
    assert result["best_model"] in {"naive", "mean", "drift", "moving_average", "seasonal_naive"}
    assert len(result["forecast"]) == 5
    assert len(result["lower_95"]) == 5
    assert len(result["upper_95"]) == 5
    assert "MAPE" in result["comparison"][0]
    assert result["seasonality"]["status"] == "OK"


def test_optimization_diagnostics_exposes_solver_transparency():
    result = optimization_diagnostics(
        objective=123.4,
        constraints=[{"name": "capacity", "value": 105, "max": 100}],
        feasible=None,
        optimal=True,
        gap=0.01,
        runtime_s=2.5,
        iterations=42,
        binding_constraints=["labor"],
        shadow_prices={"capacity": 12.0},
        sensitivity={"demand": "+5%"},
    )
    assert result["objective"] == pytest.approx(123.4)
    assert result["feasible"] is False
    assert result["optimal"] is True
    assert result["optimality_gap"] == pytest.approx(0.01)
    assert "capacity" in result["violated_constraints"]
    assert result["shadow_prices"]["capacity"] == 12.0


def test_connector_probe_does_not_claim_unconfigured_connection():
    result = connector_probe("REST", {})
    assert result["status"] == "NOT_CONFIGURED"
    assert result["connector"] == "REST"


def test_roi_is_baseline_target_actual_evidence_chain():
    result = roi_evidence({"Throughput": 100}, {"Throughput": 120}, {"Throughput": 115}, hourly_value=10)
    row = result["table"][0]
    assert row["Baseline"] == 100
    assert row["Target"] == 120
    assert row["Actual"] == 115
    assert row["Target Delta"] == 20
    assert row["Actual Delta"] == 15
    assert result["financial_impact"] == 150


def test_error_governance_classifies_input_and_integration_failures():
    assert classify_exception(ValueError("bad column"))["category"] == "input_validation"
    assert classify_exception(ConnectionError("timeout"))["category"] == "integration"


def test_verification_suite_checks_dataset_integrity():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
    result = verification_suite(df)
    assert result["passed"] == result["total"]
    assert result["status"] == "PASS"


def test_report_profiles_are_distinct_and_hashed():
    pack = build_report_pack("Audit Pack", project={"id": "P-1"}, evidence=[{"id": "E-1"}])
    assert pack["profile"] == "Audit Pack"
    assert pack["schema_version"]
    assert len(pack["pack_hash"]) == 64


def test_report_profile_rejects_unknown_profile():
    with pytest.raises(ValueError):
        build_report_pack("Unknown", project={})
