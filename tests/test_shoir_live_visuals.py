import pandas as pd

from shoir_live_visuals import _make_figure, _suggest_chart


def test_chart_suggestion_for_time_series():
    df = pd.DataFrame({"Date": pd.date_range("2026-01-01", periods=5), "Demand": [1,2,3,4,5]})
    assert _suggest_chart(df, "Date", "Demand") == "Line"


def test_bar_and_heatmap_can_render():
    df = pd.DataFrame({"Scenario": ["A","B","C"], "Cost": [10,20,15], "Risk": [2,4,3]})
    assert _make_figure(df, "Bar", "Scenario", "Cost", None, "Cost").data
    assert _make_figure(df, "Heatmap", None, None, None, "Corr").data
