"""Numerical, resilience and persistence regression tests for new workspaces."""

import pandas as pd

from shoir_resilience_suite import (
    AKDT,
    CLOSED_LOOP,
    GLOBAL_SUPPLY,
    HUMANITARIAN,
    LSIMS,
    MODULE_DEFINITIONS,
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


def test_new_workspaces_have_catalogued_tiers_and_descriptions():
    assert len(RESILIENCE_MODULES) == 6
    assert set(RESILIENCE_MODULES) == set(MODULE_DEFINITIONS)
    assert {MODULE_DEFINITIONS[n]["tier"] for n in RESILIENCE_MODULES} <= {"Enterprise", "Enterprise Plus"}
    assert all(MODULE_DEFINITIONS[n]["when"] and MODULE_DEFINITIONS[n]["example"] for n in RESILIENCE_MODULES)


def test_transport_model_makes_shortages_explicit_and_respects_capacity():
    suppliers = _default_data(GLOBAL_SUPPLY)["suppliers"]
    demands = _default_data(GLOBAL_SUPPLY)["demands"]
    result = solve_transport_allocation(suppliers, demands)
    assert result["status"] == "Optimal"
    assert result["metrics"]["delivered"] + result["metrics"]["unmet_demand"] == result["metrics"]["total_demand"]
    if not result["routes"].empty:
        used = result["routes"].groupby("Supplier")["Allocated units"].sum()
        capacity = suppliers.set_index("Supplier")["Capacity"]
        assert all(float(qty) <= float(capacity[name]) + 1e-6 for name, qty in used.items())
    assert 0 <= result["metrics"]["service_level_pct"] <= 100


def test_integer_mode_allocates_whole_units_and_lp_mode_can_fractionate():
    suppliers = pd.DataFrame([{
        "Supplier": "S1", "Capacity": 2.7, "Unit Cost": 1, "Lead Days": 1,
        "Risk %": 1, "Carbon kg/unit": 1, "Local Share %": 100,
    }])
    demands = pd.DataFrame([{"Destination": "D1", "Demand": 2.2, "Priority": 3, "Due Days": 4}])
    integer_result = solve_transport_allocation(suppliers, demands, integer_units=True)
    assert integer_result["status"] == "Optimal"
    assert integer_result["routes"]["Allocated units"].map(lambda x: abs(float(x) - round(float(x))) < 1e-8).all()
    assert integer_result["metrics"]["total_demand"] == 3.0
    fractional_result = solve_transport_allocation(suppliers, demands, integer_units=False)
    assert fractional_result["status"] == "Optimal"
    assert abs(float(fractional_result["metrics"]["total_demand"]) - 2.2) < 1e-7


def test_supplier_disruption_does_not_hide_lost_capacity():
    suppliers = _default_data(GLOBAL_SUPPLY)["suppliers"]
    demands = _default_data(GLOBAL_SUPPLY)["demands"]
    supplier = suppliers.iloc[0]["Supplier"]
    baseline = solve_transport_allocation(suppliers, demands)
    disrupted = solve_transport_allocation(suppliers, demands, disabled_suppliers=[supplier])
    assert disrupted["supplier_summary"].loc[disrupted["supplier_summary"]["Supplier"] == supplier, "Effective capacity"].iloc[0] == 0
    assert disrupted["metrics"]["unmet_demand"] >= 0
    assert baseline["metrics"]["total_demand"] == disrupted["metrics"]["total_demand"]


def test_monte_carlo_stress_test_is_reproducible_and_bounded():
    suppliers = _default_data(GLOBAL_SUPPLY)["suppliers"]
    demands = _default_data(GLOBAL_SUPPLY)["demands"]
    a = simulate_disruption_scenarios(suppliers, demands, iterations=8, seed=123, outage_probability=0.2)
    b = simulate_disruption_scenarios(suppliers, demands, iterations=8, seed=123, outage_probability=0.2)
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 8
    assert a["Service %"].between(0, 100).all()


def test_closed_loop_outputs_are_finite_and_respect_capture_rates():
    streams = _default_data(CLOSED_LOOP)["streams"]
    result = analyze_closed_loop(streams, material_capture_pct=0, heat_capture_pct=0, water_capture_pct=0)
    assert result["metrics"]["material_reused_kg"] == 0
    assert result["metrics"]["recovered_heat_kwh"] == 0
    assert result["metrics"]["water_reused_m3"] == 0
    high = analyze_closed_loop(streams, material_capture_pct=100, heat_capture_pct=100, water_capture_pct=100)
    assert high["metrics"]["material_reused_kg"] >= result["metrics"]["material_reused_kg"]
    assert high["metrics"]["residual_material_kg"] <= result["metrics"]["residual_material_kg"]
    assert high["metrics"]["modeled_value"] >= 0


def test_urban_mobility_scenario_returns_capacity_and_emissions_columns():
    junctions = _default_data(URBAN_MOBILITY)["junctions"]
    result = analyze_urban_mobility(junctions, car_mode_share_pct=45, signal_efficiency_gain_pct=10, transit_capacity_gain_pct=20)
    assert len(result["results"]) == len(junctions)
    assert "Road utilization %" in result["results"]
    assert "Modeled delay min" in result["results"]
    assert result["metrics"]["served_demand_pct"] >= 0
    assert result["metrics"]["modeled_emissions_kg_hr"] >= 0


def test_asset_health_and_edge_buffering_have_bounded_scores():
    assets = _default_data(AKDT)["assets"]
    edge = score_asset_health(assets, telemetry_dropout_pct=40, disruption_pct=25, mode="Edge")
    cloud = score_asset_health(assets, telemetry_dropout_pct=40, disruption_pct=25, mode="Cloud")
    assert edge["results"]["Modeled health index %"].between(0, 100).all()
    assert edge["metrics"]["telemetry_coverage_pct"] >= cloud["metrics"]["telemetry_coverage_pct"]
    assert edge["metrics"]["high_risk_assets"] >= 0


def test_local_capability_matches_by_part_family_and_exposes_shortage():
    data = _default_data(LSIMS)
    data["demands"] = pd.concat([
        data["demands"],
        pd.DataFrame([{
            "Plant / depot": "Unmatched plant", "Part family": "Uncovered family",
            "Monthly demand": 55, "Priority": 4, "Due days": 9,
        }]),
    ], ignore_index=True)
    result = analyze_local_capability(data["suppliers"], data["demands"])
    assert result["metrics"]["supplier_count"] == len(data["suppliers"])
    assert result["metrics"]["demand_fulfilled_pct"] >= 0
    assert result["metrics"]["local_content_proxy_pct"] <= 100
    assert not result["shortages"].empty
    assert {"Part family", "Shortage", "Demand"} <= set(result["shortages"].columns)
    missing_family = result["shortages"].loc[result["shortages"]["Part family"] == "Uncovered family"]
    assert len(missing_family) == 1
    assert float(missing_family.iloc[0]["Shortage"]) == 55


def test_run_snapshots_are_owner_and_module_scoped(tmp_path):
    path = str(tmp_path / "resilience.db")
    sample = pd.DataFrame({"value": [1.0, 2.0]})
    saved = persist_resilience_run(GLOBAL_SUPPLY, "Alice", {"inputs": sample}, {"results": sample}, db_path=path)
    assert len(saved["input_sha256"]) == 64
    assert len(list_resilience_runs(GLOBAL_SUPPLY, "Alice", db_path=path)) == 1
    assert list_resilience_runs(GLOBAL_SUPPLY, "Bob", db_path=path).empty
    assert list_resilience_runs(HUMANITARIAN, "Alice", db_path=path).empty
    assert load_resilience_run(saved["run_id"], GLOBAL_SUPPLY, "Alice", db_path=path)["inputs"]["inputs"][0]["value"] == 1.0
    assert load_resilience_run(saved["run_id"], GLOBAL_SUPPLY, "Bob", db_path=path) is None
    assert load_resilience_run(saved["run_id"], HUMANITARIAN, "Alice", db_path=path) is None
