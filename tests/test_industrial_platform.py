import pandas as pd
import numpy as np

from industrial_platform import (
    validate_table,
    calculate_takt_time,
    finite_schedule,
    mes_work_order_table,
    spc_limits,
    process_capability,
    pareto_frontier,
    weighted_objective,
    robust_scenario_bounds,
    discrete_event_simulation,
    economics,
    lca_inventory,
    model_hash,
    ensure_model_registry,
)

def test_data_quality_detects_duplicates_and_missing():
    df = pd.DataFrame({"SKU": ["A", "A"], "Demand": [10, None]})
    result = validate_table(df)
    assert result["duplicates"] == 1
    assert result["missing_cells"] == 1
    assert result["score"] < 100

def test_takt_time():
    assert calculate_takt_time(480, 120) == 4

def test_finite_schedule_respects_capacity():
    jobs = pd.DataFrame([
        {"Job": "A", "Machine": "M1", "Duration": 5, "Due Date": "2000-01-03", "Priority": 2},
        {"Job": "B", "Machine": "M1", "Duration": 6, "Due Date": "2000-01-03", "Priority": 1},
    ])
    machines = pd.DataFrame([{"Machine": "M1", "Available Hours": 10}])
    result, summary = finite_schedule(jobs, machines)
    assert len(result) == 2
    assert summary["late_or_capacity_exceptions"] == 1
    assert not summary["feasible"]

def test_mes_yield_and_remaining():
    result = mes_work_order_table(pd.DataFrame([
        {"Order": "WO1", "Quantity": 100, "Produced": 80, "Scrap": 5, "Status": "In Process"}
    ]))
    row = result["orders"].iloc[0]
    assert row["Remaining"] == 20
    assert row["Yield_pct"] == 95

def test_spc_and_capability():
    values = [10, 10.1, 9.9, 10.05, 9.95]
    limits = spc_limits(values)
    assert limits["ucl"] > limits["mean"] > limits["lcl"]
    cap = process_capability(values, 10.5, 9.5)
    assert cap["Cp"] > 0
    assert cap["Cpk"] > 0

def test_pareto_and_weighted_objective():
    points = pd.DataFrame([
        {"Scenario": "A", "Cost": 100, "Carbon": 80, "Service": 95},
        {"Scenario": "B", "Cost": 110, "Carbon": 60, "Service": 99},
        {"Scenario": "C", "Cost": 120, "Carbon": 90, "Service": 90},
    ])
    pareto = pareto_frontier(points, ["Cost", "Carbon"], ["Service"])
    assert pareto["Pareto Optimal"].sum() >= 2
    scored = weighted_objective(points, {"Cost": 0.5, "Carbon": 0.5})
    assert "Weighted Objective" in scored.columns

def test_risk_simulation_is_reproducible():
    a = robust_scenario_bounds({"Demand": 100}, {"Demand": 0.2}, 50, 42)
    b = robust_scenario_bounds({"Demand": 100}, {"Demand": 0.2}, 50, 42)
    pd.testing.assert_frame_equal(a, b)

def test_discrete_event_simulation():
    result = discrete_event_simulation([0, 1, 2], [1, 1, 1], servers=1)
    assert len(result["events"]) == 3
    assert result["summary"]["avg_wait"] >= 0

def test_economics_and_lca():
    econ = economics([-100, 60, 60], 0.1)
    assert econ["NPV"] > 0
    lca = lca_inventory(pd.DataFrame([
        {"Activity": "Electricity", "Quantity": 100, "Unit": "kWh", "Factor_kgCO2e_per_unit": 0.4}
    ]))
    assert lca.iloc[0]["CO2e_kg"] == 40

def test_model_hash_is_deterministic():
    assert model_hash({"b": 2, "a": 1}) == model_hash({"a": 1, "b": 2})

def test_registry_schema_initializes(tmp_path):
    db = tmp_path / "registry.db"
    ensure_model_registry(str(db))
    import sqlite3
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert {"model_registry", "experiment_runs", "security_events", "industrial_entities"} <= tables
