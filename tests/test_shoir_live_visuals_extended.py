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
    assert _auto_chart_choice(health) == "Bar"

    network = pd.DataFrame({
        "Source": ["Plant A", "Plant B"],
        "Target": ["Market 1", "Market 2"],
        "Value": [100, 150],
    })
    assert _auto_chart_choice(network) == "Sankey"
