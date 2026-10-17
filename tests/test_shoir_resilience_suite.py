"""Regression tests for the Shoir-IE resilience suite's calculation contracts."""
from __future__ import annotations

import pandas as pd
import pytest

from shoir_resilience_suite import (
    AKDT,
    CLOSED_LOOP,
    GLOBAL_SUPPLY,
    HUMANITARIAN,
    LSIMS,
    RESILIENCE_MODULES,
    URBAN_MOBILITY,
    _default_data,
    analyze_closed_loop,
    analyze_local_capability,
    analyze_urban_mobility,
    list_resilience_runs,
    load_resilience_run,
    persist_resilience_run,
    score_asset_health,
    simulate_disruption_scenarios,
    solve_transport_allocation,
)


def test_resilience_module_catalog_is_complete_and_unique():
    assert len(RESILIENCE_MODULES) == 6
    assert len(set(RESILIENCE_MODULES)) == 6
    assert set(RESILIENCE_MODULES) == {
        GLOBAL_SUPPLY, CLOSED_LOOP, URBAN_MOBILITY, HUMANITARIAN, LSIMS, AKDT
    }


@pytest.mark.parametrize("module", RESILIENCE_MODULES)
def test_each_module_has_nonempty_starter_tables(module):
    data = _default_data(module)
    assert data, module
    assert all(isinstance(frame, pd.DataFrame) and not frame.empty for frame in data.values()), module


def test_transport_solver_reports_allocation_and_capacity_constraints():
    data = _default_data(GLOBAL_SUPPLY)
    result = solve_transport_allocation(data["suppliers"], data["demands"])
    assert result["status"] == "Optimal"
    assert not result["routes"].empty
    assert {"Supplier", "Destination", "Allocated units"}.issubset(result["routes"].columns)
    assert result["metrics"]["delivered"] + result["metrics"]["unmet_demand"] == pytest.approx(
        result["metrics"]["total_demand"], abs=1e-5
    )
    for supplier, group in result["routes"].groupby("Supplier"):
        cap = float(data["suppliers"].loc[data["suppliers"]["Supplier"].eq(supplier), "Capacity"].sum())
        assert group["Allocated units"].sum() <= cap + 1e-5


def test_transport_solver_keeps_shortage_visible_after_supplier_outage():
    data = _default_data(GLOBAL_SUPPLY)
    suppliers = data["suppliers"]
    disabled = suppliers["Supplier"].iloc[0]
    result = solve_transport_allocation(suppliers, data["demands"], disabled_suppliers=[disabled])
    assert result["status"] == "Optimal"
    assert result["metrics"]["unmet_demand"] >= 0
    assert result["metrics"]["service_level_pct"] <= 100
    summary = result["supplier_summary"].set_index("Supplier")
    assert summary.loc[disabled, "Effective capacity"] == 0
    assert result["shortages"]["Shortage"].sum() == pytest.approx(result["metrics"]["unmet_demand"], abs=1e-5)


def test_transport_solver_handles_no_available_suppliers_without_losing_demand():
    data = _default_data(GLOBAL_SUPPLY)
    result = solve_transport_allocation(data["suppliers"], data["demands"],
                                        disabled_suppliers=data["suppliers"]["Supplier"].astype(str).tolist())
    assert result["metrics"]["delivered"] == pytest.approx(0)
    assert result["metrics"]["unmet_demand"] == pytest.approx(result["metrics"]["total_demand"])
    assert result["shortages"]["Shortage"].sum() == pytest.approx(result["metrics"]["total_demand"])


def test_monte_carlo_stress_test_is_reproducible_and_bounded():
    data = _default_data(GLOBAL_SUPPLY)
    first = simulate_disruption_scenarios(data["suppliers"], data["demands"], iterations=4, seed=42)
    second = simulate_disruption_scenarios(data["suppliers"], data["demands"], iterations=4, seed=42)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 4
    assert first["Service %"].between(0, 100).all()
    assert (first["Shortage units"] >= 0).all()


def test_closed_loop_balance_respects_capture_and_reuse_limits():
    data = _default_data(CLOSED_LOOP)["streams"]
    result = analyze_closed_loop(data, material_capture_pct=50, heat_capture_pct=40, water_capture_pct=60)
    frame, metrics = result["results"], result["metrics"]
    assert (frame["Reused material kg"] <= frame["Recoverable waste kg"] + 1e-9).all()
    assert (frame["Residual material kg"] >= -1e-9).all()
    assert (frame["Reused water m3"] <= frame["Water reuse demand m3"] + 1e-9).all()
    assert 0 <= metrics["material_circularity_pct"] <= 100
    assert metrics["residual_material_kg"] >= 0


def test_urban_mobility_service_and_emissions_are_finite():
    data = _default_data(URBAN_MOBILITY)["junctions"]
    result = analyze_urban_mobility(data, car_mode_share_pct=60, signal_efficiency_gain_pct=8,
                                    transit_capacity_gain_pct=15, demand_shock_pct=20)
    frame, metrics = result["results"], result["metrics"]
    assert not frame.empty
    assert frame.select_dtypes(include="number").apply(lambda s: s.map(pd.notna).all()).all()
    assert 0 <= metrics["served_demand_pct"] <= 100 + 1e-8
    assert metrics["modeled_emissions_kg_hr"] >= 0
    assert metrics["average_delay_min"] >= 0


def test_asset_health_sandbox_discloses_telemetry_loss_and_bounded_scores():
    assets = _default_data(AKDT)["assets"]
    full = score_asset_health(assets, telemetry_dropout_pct=0, mode="Cloud")
    edge = score_asset_health(assets, telemetry_dropout_pct=40, mode="Edge")
    assert 0 <= full["metrics"]["asset_health_index_pct"] <= 100
    assert 0 <= edge["metrics"]["telemetry_coverage_pct"] <= 100
    assert edge["metrics"]["telemetry_coverage_pct"] > (100 - 40)
    assert "Modeled health index %" in edge["results"]
    assert edge["metrics"]["high_risk_assets"] >= 0


def test_local_capability_model_preserves_demand_gaps_and_bounds_metrics():
    data = _default_data(LSIMS)
    result = analyze_local_capability(data["suppliers"], data["demands"])
    assert "demand_fulfilled_pct" in result["metrics"]
    assert 0 <= result["metrics"]["demand_fulfilled_pct"] <= 100 + 1e-8
    assert result["metrics"]["monthly_unmet_demand"] >= 0
    if not result["shortages"].empty:
        assert (result["shortages"]["Shortage"] >= -1e-8).all()


def test_resilience_run_history_is_hashed_and_owner_scoped(tmp_path):
    db = str(tmp_path / "resilience.db")
    inputs = {"suppliers": _default_data(GLOBAL_SUPPLY)["suppliers"]}
    results = {"metrics": {"service_level_pct": 97.5}, "routes": pd.DataFrame({"Allocated units": [5]})}
    record = persist_resilience_run(GLOBAL_SUPPLY, "Alice", inputs, results, db_path=db)
    assert len(record["input_sha256"]) == 64
    assert len(list_resilience_runs(GLOBAL_SUPPLY, "Alice", db_path=db)) == 1
    assert list_resilience_runs(GLOBAL_SUPPLY, "Bob", db_path=db).empty
    assert load_resilience_run(record["run_id"], GLOBAL_SUPPLY, "Bob", db_path=db) is None
    loaded = load_resilience_run(record["run_id"], GLOBAL_SUPPLY, "Alice", db_path=db)
    assert loaded is not None
    assert loaded["input_sha256"] == record["input_sha256"]
    assert loaded["results"]["metrics"]["service_level_pct"] == pytest.approx(97.5)


def test_persistence_rejects_oversized_or_non_json_safe_payload(tmp_path):
    db = str(tmp_path / "resilience.db")
    with pytest.raises(ValueError):
        persist_resilience_run(GLOBAL_SUPPLY, "Alice", {"large": pd.DataFrame({"x": ["x" * 9_000_000]})},
                               {}, db_path=db)


def test_module_renderer_has_access_gate_and_explicit_sandbox_disclosures():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "shoir_resilience_suite.py").read_text(encoding="utf-8")
    assert "def render_resilience_module(" in source
    assert "if not tier_allows(tier, required):" in source
    assert "Starter workspace uses editable synthetic data" in source
    assert "persist_resilience_run" in source
    assert "simulate_disruption_scenarios" in source
