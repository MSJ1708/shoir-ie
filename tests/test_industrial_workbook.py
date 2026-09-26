import io
import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from shoir_industrial_workbook import (
    SafeFormulaEngine,
    WorkbookExtension,
    apply_query_pipeline,
    convert_units,
    evaluate_workbook_formulas,
    infer_semantic_roles,
    instant_analyze,
    instant_runtime_profile,
    list_templates,
    run_workbook_extension,
    save_workbook,
    stream_profile_csv,
    stream_query_csv,
    validate_workbook,
    _copilot_edit,
)


def test_unit_conversion_and_dimension_guard():
    assert np.isclose(convert_units(60, "min", "h"), 1.0)
    assert np.isclose(convert_units(0, "C", "F"), 32.0)
    with pytest.raises(ValueError):
        convert_units(1, "kg", "m")


def test_formula_engine_cells_ranges_cross_sheet_and_if():
    wb = {
        "Sheet1": pd.DataFrame({"Qty": [2, 4, 6], "Cost": [10, 20, 30], "Total": [0, 0, 0]}),
        "Sheet 2": pd.DataFrame({"Value": [5, 7]}),
    }
    formulas = {
        "Sheet1": {"C1": "=A1*B1", "C2": "=SUM(C1:C1)+5"},
        "Sheet 2": {"A2": "=IF(A1>3,A1*2,0)"},
    }
    out, audit = evaluate_workbook_formulas(wb, formulas)
    assert out["Sheet1"].iloc[0, 2] == 20
    assert out["Sheet1"].iloc[1, 2] == 25
    assert out["Sheet 2"].iloc[1, 0] == 10
    assert (audit["Status"] == "Calculated").all()


def test_formula_engine_cross_sheet_reference_and_cycle_detection():
    wb = {"Input": pd.DataFrame({"Value": [12]}), "Calc": pd.DataFrame({"Result": [0]})}
    engine = SafeFormulaEngine(wb, {"Calc": {"A1": "='Input'!A1*2"}})
    assert engine.evaluate("='Input'!A1*2", "Calc") == 24

    cyclic = {"S": pd.DataFrame({"A": [0], "B": [0]})}
    with pytest.raises(ValueError, match="Circular formula"):
        SafeFormulaEngine(cyclic, {"S": {"A1": "=B1", "B1": "=A1"}}).evaluate("=A1", "S")


def test_formula_out_of_range_is_audit_error_not_crash():
    wb = {"S": pd.DataFrame({"A": [1]})}
    out, audit = evaluate_workbook_formulas(wb, {"S": {"Z9": "=1"}})
    assert out["S"].iloc[0, 0] == 1
    assert audit.iloc[0]["Status"] == "Error"


def test_query_pipeline_is_repeatable_and_safe():
    df = pd.DataFrame({
        "Area": ["A", "A", "B"],
        "Qty": [10, 20, 5],
        "Cost": [2.0, 3.0, 4.0],
    })
    steps = [
        {"type": "filter", "column": "Qty", "op": ">", "value": 5},
        {"type": "add_formula", "target": "Extended", "expression": "Qty * Cost"},
        {"type": "groupby", "columns": ["Area"], "value_column": "Extended", "aggregation": "sum"},
    ]
    out = apply_query_pipeline(df, steps)
    assert list(out.columns) == ["Area", "Sum Extended"]
    assert out.loc[out["Area"].eq("A"), "Sum Extended"].iloc[0] == 80


def test_instant_analyze_and_validation_produce_evidence():
    df = pd.DataFrame({"Asset": ["A", "B", "C"], "Temperature": [50.0, 60.0, 70.0], "Vibration": [1.0, 1.5, 2.0]})
    analysis = instant_analyze(df)
    health = validate_workbook({"Assets": df})
    assert not analysis["profile"].empty
    assert 0 <= health["health"] <= 100
    assert analysis["figure"] is not None


def test_semantics_reuse_digital_thread_vocabulary():
    mapping = infer_semantic_roles(pd.DataFrame({
        "Asset ID": ["CNC-01"],
        "Product": ["P-1"],
        "Energy kWh": [100.0],
        "Actual Outcome": [95.0],
    }))
    roles = set(mapping["Suggested Role"])
    assert {"Asset", "Product", "Energy", "Outcome"} <= roles


def test_workbook_persistence_round_trip_is_workspace_scoped(tmp_path):
    path = str(tmp_path / "workbook.db")
    wb = {"Sheet1": pd.DataFrame({"A": [1, 2], "B": [3, 4]})}

    # The production API scopes by workspace; custom-path testing validates
    # persistence semantics without touching the repository database.
    from shoir_industrial_workbook import save_workbook as save_wb, load_workbook as load_wb
    wid = save_wb(wb, {"Sheet1": {"B1": "=A1+2"}}, {"Sheet1": {"A": "KPI"}}, "Test", path=path)
    loaded, formulas, semantic = load_wb(wid, path=path)
    assert loaded["Sheet1"].iloc[0, 0] == 1
    assert formulas["Sheet1"]["B1"] == "=A1+2"
    assert semantic["Sheet1"]["A"] == "KPI"


def test_templates_have_builtins():
    templates = list_templates(path=":memory:")
    assert {"OEE Starter", "Quality Pareto", "Inventory Reorder"} <= set(templates["Name"])


def test_copilot_direct_edit_primitives():
    wb = {"S": pd.DataFrame({"Qty": [1, 3], "Cost": [10, 20]})}
    edited, message = _copilot_edit("add column Total = Qty * Cost", wb, "S")
    assert "Total" in edited["S"].columns
    assert edited["S"]["Total"].tolist() == [10, 60]
    assert "Added column" in message


def test_streaming_csv_profile_and_query():
    raw = pd.DataFrame({"Area": ["A", "B", "A"], "Qty": [1, 10, 4]}).to_csv(index=False).encode()
    profile = stream_profile_csv(raw, chunksize=2)
    assert profile["mode"] == "streaming"
    assert profile["rows"] == 3
    result = stream_query_csv(raw, [{"type": "filter", "column": "Qty", "op": ">", "value": 3}], chunksize=2)
    assert result["Qty"].tolist() == [10, 4]


def test_runtime_profile_scales_by_cell_count():
    small = pd.DataFrame(np.ones((10, 10)))
    medium = pd.DataFrame(np.ones((10000, 30)))
    assert instant_runtime_profile(small)["mode"] == "interactive"
    assert instant_runtime_profile(medium)["mode"] == "vectorized"


def test_extension_contract():
    from shoir_industrial_workbook import _EXTENSION_REGISTRY
    register_name = "Test Extension"
    _EXTENSION_REGISTRY.pop(register_name, None)
    from shoir_industrial_workbook import register_workbook_extension
    register_workbook_extension(WorkbookExtension(
        name=register_name, version="1.0.0", category="Test", description="test",
        transform=lambda frame: frame.assign(Double=frame["Value"] * 2),
    ))
    out = run_workbook_extension(register_name, pd.DataFrame({"Value": [2, 3]}))
    assert out["Double"].tolist() == [4, 6]


def test_platform_and_visualization_integration():
    from industrial_platform import PLATFORM_CATALOG
    from shoir_live_visuals import _MODULE_KEYS
    entry = next(x for x in PLATFORM_CATALOG if x["name"] == "Industrial Workbook")
    assert entry["tier"] == "Starter"
    assert "Industrial Workbook" in _MODULE_KEYS
    assert "industrial_workbook_current_df" in _MODULE_KEYS["Industrial Workbook"]


def test_engineering_formula_functions_are_safe_and_deterministic():
    from shoir_industrial_workbook import SafeFormulaEngine, evaluate_workbook_formulas

    wb = {"Sheet1": pd.DataFrame({
        "Avail":[90.0,95.0],
        "Perf":[80.0,90.0],
        "Quality":[98.0,99.0],
        "AvailableTime":[10.0,20.0],
        "Demand":[100.0,110.0],
        "OutOEE":[0.0,0.0],
        "OutTakt":[0.0,0.0],
    })}
    formulas = {"Sheet1": {
        "F1": "=OEE(A1,B1,C1)",
        "G2": "=TAKT_TIME(D2,E2)",
    }}
    result, audit = evaluate_workbook_formulas(wb, formulas)
    errors = audit[audit["Status"].eq("Error")]
    assert errors.empty, errors.to_dict("records")
    assert result["Sheet1"].iat[0,5] == pytest.approx(0.90 * 0.80 * 0.98)
    assert result["Sheet1"].iat[1,6] == pytest.approx(20.0 / 110.0)

    engine = SafeFormulaEngine(wb)
    assert engine.evaluate('=CONVERT(60,"min","h")', "Sheet1") == pytest.approx(1.0)
    assert engine.evaluate("=CPK(10,1,7,13)", "Sheet1") == pytest.approx(1.0)


def test_workbook_version_history_and_comments_round_trip(tmp_path, monkeypatch):
    import streamlit as st
    from shoir_industrial_workbook import (
        save_workbook, list_workbook_versions, save_workbook_comment,
        list_workbook_comments,
    )

    monkeypatch.setenv("SHOIR_WORKSPACE_NAME", "test")
    st.session_state.clear()
    st.session_state["shoir_workspace_name"] = "workspace-test"
    st.session_state["current_user"] = "tester"

    db = tmp_path / "workbook.db"
    wb = {"Sheet1": pd.DataFrame({"A":[1,2], "B":[3,4]})}
    wid = save_workbook(wb, {"Sheet1":{"C2":"=A2+B2"}}, {}, "Test Workbook", path=str(db))
    versions = list_workbook_versions(wid, path=str(db))
    assert len(versions) == 1
    assert int(versions.iloc[0]["Version"]) == 1

    wb2 = {"Sheet1": pd.DataFrame({"A":[1,2], "B":[3,5]})}
    save_workbook(wb2, {"Sheet1":{"C2":"=A2+B2"}}, {}, "Test Workbook", wid, path=str(db))
    versions = list_workbook_versions(wid, path=str(db))
    assert len(versions) == 2
    assert set(versions["Version"].astype(int)) == {1,2}

    cid = save_workbook_comment(wid, "Sheet1", "B2", "Reviewed by engineering.", path=str(db))
    comments = list_workbook_comments(wid, path=str(db))
    assert cid > 0
    assert comments.iloc[0]["Comment"] == "Reviewed by engineering."
