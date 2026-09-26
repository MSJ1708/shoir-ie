import math

import numpy as np
import pandas as pd
import pytest

from shoir_adoption_engine import (
    compile_shoir_script,
    evaluate_engineering_function,
    industrial_pivot,
    build_dependency_graph,
    explain_number,
    choose_runtime,
    run_shoir_script,
)


def test_engineering_formula_library_core_functions():
    assert np.isclose(evaluate_engineering_function("OEE", [0.92, 0.95, 0.99]), 0.92 * 0.95 * 0.99)
    assert np.isclose(evaluate_engineering_function("OEE", [92, 95, 99]), 0.92 * 0.95 * 0.99)
    assert np.isclose(evaluate_engineering_function("TAKTTIME", [480, 120]), 4.0)
    assert np.isclose(evaluate_engineering_function("LITTLELAW", [12, 0.5]), 6.0)
    assert np.isclose(evaluate_engineering_function("EOQ", [12000, 50, 2]), math.sqrt(600000))
    assert np.isclose(evaluate_engineering_function("SAFETYSTOCK", [1.65, 120, 5]), 1.65 * 120 * math.sqrt(5))
    assert np.isclose(evaluate_engineering_function("NPV", [0.10, [100, 100]]), 100 / 1.1 + 100 / 1.21)
    assert np.isclose(evaluate_engineering_function("CO2E", [1000, 0.42]), 420.0)
    assert np.isclose(evaluate_engineering_function("CONVERT", [60, "min", "h"]), 1.0)


def test_engineering_formula_validation_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        evaluate_engineering_function("EOQ", [100, 10, 0])
    with pytest.raises(ValueError):
        evaluate_engineering_function("CPK", [[1], 0, 2])
    with pytest.raises(ValueError):
        evaluate_engineering_function("UNKNOWN", [1])


def test_industrial_pivot_supports_multidimensional_summary():
    df = pd.DataFrame(
        {
            "Plant": ["A", "A", "B", "B"],
            "Line": ["L1", "L2", "L1", "L2"],
            "Month": ["Jan", "Jan", "Jan", "Jan"],
            "Output": [10, 20, 30, 40],
        }
    )
    result = industrial_pivot(
        df,
        index=["Plant"],
        columns="Line",
        values="Output",
        aggfunc="sum",
    )
    assert "Plant" in result.columns
    assert set(result["Plant"]) == {"A", "B"}
    assert float(result.loc[result["Plant"].eq("A"), "Output · L1"].iloc[0]) == 10.0
    assert float(result.loc[result["Plant"].eq("B"), "Output · L2"].iloc[0]) == 40.0


def test_shoir_script_is_deterministic_and_python_execution_is_rejected():
    script = 'load("Sheet1")\nadd_column("Extended","Qty * Cost")\nfilter("Extended",">",10)\nanalyze()'
    compiled = compile_shoir_script(script)
    assert [x["command"] for x in compiled] == ["load", "add_column", "filter", "analyze"]

    workbook = {"Sheet1": pd.DataFrame({"Qty": [1, 3], "Cost": [10, 20]})}
    run = run_shoir_script(script, workbook)
    out = run["workbook"]["Sheet1"]
    assert out["Extended"].tolist() == [10, 60]
    assert len(out) == 1
    assert run["script_hash"]

    with pytest.raises(ValueError):
        compile_shoir_script('__import__("os").system("echo unsafe")')


def test_dependency_graph_and_explain_number_show_formula_lineage():
    workbook = {"Calc": pd.DataFrame({"Input": [3], "Output": [0]})}
    formulas = {"Calc": {"B1": "=A1*2"}}
    evaluated = run_shoir_script('load("Calc")\nformula(cell="B1",expression="=A1*2")', workbook, formulas=formulas)
    updated = evaluated["workbook"]
    nodes, edges = build_dependency_graph(updated, evaluated["formulas"], {"Calc": {"Output": "KPI"}})
    assert "Formula" in set(nodes["Type"])
    assert "depends on" in set(edges["Relation"])

    explanation = explain_number(updated, evaluated["formulas"], "Calc", "B1", {"Calc": {"Output": "KPI"}})
    assert explanation["Value"] == 6
    assert explanation["Formula"] == "=A1*2"
    assert explanation["Dependencies"][0]["Cell"] == "A1"


def test_runtime_selection_is_capability_aware():
    runtime = choose_runtime(10, 10)
    assert runtime["selected_runtime"] == "Pandas / interactive"
    assert "Pandas" in runtime["available_runtimes"]


def test_cpk_uses_sample_standard_deviation():
    values = [9.8, 10.0, 10.1, 10.2, 9.9, 10.0]
    sigma = np.std(values, ddof=1)
    expected = min((10.5 - np.mean(values)) / (3 * sigma), (np.mean(values) - 9.5) / (3 * sigma))
    assert np.isclose(evaluate_engineering_function("CPK", [values, 9.5, 10.5]), expected)
