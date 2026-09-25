import pandas as pd

from shoir_live_visuals import _make_figure, _suggest_chart


def test_chart_suggestion_for_time_series():
    df = pd.DataFrame({"Date": pd.date_range("2026-01-01", periods=5), "Demand": [1,2,3,4,5]})
    assert _suggest_chart(df, "Date", "Demand") == "Line"


def test_bar_and_heatmap_can_render():
    df = pd.DataFrame({"Scenario": ["A","B","C"], "Cost": [10,20,15], "Risk": [2,4,3]})
    assert _make_figure(df, "Bar", "Scenario", "Cost", None, "Cost").data
    assert _make_figure(df, "Heatmap", None, None, None, "Corr").data


def test_3d_scatter_can_render():
    import pandas as pd
    df = pd.DataFrame({"X":[1,2,3], "Y":[2,3,4], "Z":[3,4,5]})
    assert _make_figure(df, "3D Scatter", "X", "Y", "Z", "3D").data


def test_extended_engineering_visualizations_render():
    from shoir_live_visuals import _make_figure
    import pandas as pd

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
    from shoir_live_visuals import _auto_chart_choice
    import pandas as pd

    flow = pd.DataFrame({"Source": ["A"], "Target": ["B"], "Value": [3]})
    assert _auto_chart_choice(flow) == "Sankey"

    gantt = pd.DataFrame({
        "Task": ["A"],
        "Start": pd.to_datetime(["2026-01-01"]),
        "Finish": pd.to_datetime(["2026-01-02"]),
    })
    assert _auto_chart_choice(gantt) == "Gantt"
