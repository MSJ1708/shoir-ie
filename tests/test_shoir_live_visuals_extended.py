import pandas as pd

from shoir_live_visuals import _auto_chart_choice, _make_figure


def test_extended_engineering_visualizations_render():
    flow = pd.DataFrame({"Source": ["Supplier A", "Supplier B"], "Target": ["Plant", "Plant"], "Value": [10, 20]})
    assert _make_figure(flow, "Sankey", None, None, None, "Flow") is not None

    waterfall = pd.DataFrame({"Step": ["Baseline", "Labor", "Energy", "End"], "Delta": [100, -10, 5, 95]})
    assert _make_figure(waterfall, "Waterfall", "Step", "Delta", None, "Cost") is not None

    spc = pd.DataFrame({"Date": pd.date_range("2026-01-01", periods=6), "Measurement": [10, 11, 9, 10, 12, 8]})
    assert _make_figure(spc, "SPC", "Date", "Measurement", None, "SPC") is not None

    sensitivity = pd.DataFrame({"Demand": [10, 20, 30, 40], "Fuel": [2, 2, 3, 4], "Labor": [5, 6, 6, 8]})
    assert _make_figure(sensitivity, "Sensitivity Plot", None, "Demand", None, "Sensitivity") is not None

    gantt = pd.DataFrame({
        "Task": ["WO-1", "WO-2"],
        "Start": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "Finish": pd.to_datetime(["2026-01-03", "2026-01-05"]),
    })
    assert _make_figure(gantt, "Gantt", None, None, None, "Schedule") is not None

    network = pd.DataFrame({"Source": ["A", "B"], "Target": ["B", "C"]})
    assert _make_figure(network, "Network Map", None, None, None, "Network") is not None


def test_auto_chart_detects_flow_and_gantt():
    flow = pd.DataFrame({"Source": ["A"], "Target": ["B"], "Value": [3]})
    assert _auto_chart_choice(flow) == "Sankey"

    gantt = pd.DataFrame({
        "Task": ["A"],
        "Start": pd.to_datetime(["2026-01-01"]),
        "Finish": pd.to_datetime(["2026-01-02"]),
    })
    assert _auto_chart_choice(gantt) == "Gantt"


def test_auto_visualization_routes_specialized_engine_outputs():
    effects = pd.DataFrame({
        "Term": ["A", "B"],
        "Effect (2×coef)": [4.2, -1.7],
        "p_value": [0.01, 0.20],
    })
    assert _auto_chart_choice(effects) == "Bar"

    sensitivity = pd.DataFrame({
        "Driver": ["Demand", "Lead Time"],
        "Sensitivity": [0.82, 0.44],
        "Direction": ["Positive", "Negative"],
    })
    assert _auto_chart_choice(sensitivity) == "Sensitivity Plot"

    control = pd.DataFrame({
        "Measurement": [10, 11, 10, 12, 9],
        "UCL": [13, 13, 13, 13, 13],
        "LCL": [7, 7, 7, 7, 7],
    })
    assert _auto_chart_choice(control) == "Control Chart"

    pareto = pd.DataFrame({
        "Failure Mode": ["Leak", "Crack", "Wear"],
        "RPN": [120, 80, 30],
    })
    assert _auto_chart_choice(pareto) == "Pareto"


def test_enterprise_operations_visualizations_render():
    twin = pd.DataFrame({
        "Tick": [1, 2, 3],
        "WIP": [10, 12, 9],
        "Utilization %": [80, 90, 70],
    })
    assert _make_figure(twin, "Line", "Tick", "WIP", None, "Twin Replay") is not None

    health = pd.DataFrame({
        "Area": ["Production", "Supply"],
        "Health %": [90, 70],
        "Status": ["Observed", "Review"],
    })
    assert _auto_chart_choice(health) == "Health Heatmap"

    network = pd.DataFrame({
        "Source": ["Plant A", "Plant B"],
        "Target": ["Market 1", "Market 2"],
        "Value": [100, 150],
    })
    assert _auto_chart_choice(network) == "Sankey"


def test_enterprise_capability_visualization_registry_covers_requested_outputs():
    from shoir_live_visuals import _MODULE_KEYS
    required = {
        "Digital Twin & Discrete-Event Simulation": {"digital_twin_replay_df", "digital_twin_state_snapshot"},
        "Control Tower": {"control_tower_unified_health_df"},
        "Industrial Connectivity Hub": {"connectivity_health_df"},
        "Enterprise Security & Governance": {"enterprise_security_posture_df"},
        "Engineering Model Registry": {"model_reproducibility_catalog"},
        "Industrial Data Platform": {"data_platform_latest_df"},
        "Capital Investment & Engineering Economics": {"engineering_economics_tco_df"},
        "Industrial Sustainability & LCA": {"sustainability_decision_bridge_df"},
        "Human Factors & Ergonomics (NIOSH)": {"human_factors_metrics_df"},
        "Geospatial Network Designer": {"geospatial_network_routes_df"},
        "Team Workspaces & RBAC": {"workspace_members_df"},
        "Executive Report Center": {"exec_report_df"},
        "Experiment Engine": {"experiment_engine_effects_df", "experiment_engine_mc_samples", "experiment_engine_sensitivity_df"},
        "Advanced ML Demand Forecasting": {"forecast_result", "forecast_metrics"},
    }
    for module, keys in required.items():
        assert module in _MODULE_KEYS, module
        assert keys.intersection(set(_MODULE_KEYS[module])), module


def test_universal_fallback_visualizations_render():
    from shoir_live_visuals import build_visualization_suite

    categorical = pd.DataFrame({"Station": ["A", "A", "B", "C", "C"]})
    suite = build_visualization_suite(categorical, context="Categorical", max_figures=3)
    assert suite
    assert any("Category counts" in label for label, _ in suite)

    sparse = pd.DataFrame({"KPI": [None, None, None], "Status": ["Missing"] * 3})
    sparse_suite = build_visualization_suite(sparse, context="Sparse", max_figures=3)
    assert sparse_suite

    date_only = pd.DataFrame({"Timestamp": pd.date_range("2026-01-01", periods=4, freq="h")})
    date_suite = build_visualization_suite(date_only, context="Time", max_figures=3)
    assert date_suite


import pandas as pd

from shoir_live_visuals import ensure_visualization_suite, visualization_contract_report


def test_universal_visualization_suite_falls_back_for_unknown_semantics():
    df = pd.DataFrame({"Unusual Field": [1, 2, 3], "Another Value": [4, 5, 6]})
    suite = ensure_visualization_suite(df, "Unknown Engineering Table", max_figures=2)
    assert suite
    assert suite[0][1].data


def test_visualization_contract_report_requires_no_cross_module_data():
    report = visualization_contract_report("Industrial Workbook")
    assert list(report.columns) == [
        "Module", "Table", "State Key", "Rows", "Columns", "Graphs", "Status", "Primary Chart"
    ]
