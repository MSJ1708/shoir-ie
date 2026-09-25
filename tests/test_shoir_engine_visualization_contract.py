import pandas as pd

from shoir_live_visuals import _MODULE_KEYS, _auto_chart_choice


def test_engine_result_families_are_registered_for_universal_visualization():
    assert "milp_allocation_flow_df" in _MODULE_KEYS["MILP Solvers"]
    assert "experiment_factorial_effects" in _MODULE_KEYS["Experiment Lab"]
    assert "optimization_result_df" in _MODULE_KEYS["Multi-Objective Optimization"]
    assert "forecast_result" in _MODULE_KEYS["Advanced ML Demand Forecasting"]
    assert "decision_verification_df" in _MODULE_KEYS["Engineering Decision Center"]


def test_auto_visualization_uses_engine_semantics():
    flow = pd.DataFrame({"Customer":["C1","C2"],"Warehouse":["W1","W1"],"Quantity":[10,20]})
    assert _auto_chart_choice(flow) == "Sankey"

    waterfall = pd.DataFrame({"KPI":["Cost","Carbon"],"Baseline":[100,100],"Delta":[-8,-12]})
    assert _auto_chart_choice(waterfall) == "Waterfall"

    mc = pd.DataFrame({"Demand":[90,100,110],"Capacity":[120,120,120],"Propagated KPI":[-30,-20,-10]})
    assert _auto_chart_choice(mc) == "Distribution"

    effects = pd.DataFrame({"Term":["A","B"],"Effect":[4.0,-2.0],"p-value":[0.01,0.20]})
    assert _auto_chart_choice(effects) == "Bar"

    verification = pd.DataFrame({"KPI":["Cost","Service"],"Target":[100,95],"Actual":[98,96]})
    assert _auto_chart_choice(verification) == "Bar"
