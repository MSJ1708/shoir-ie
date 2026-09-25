import io

import numpy as np
import pandas as pd

from research_statistics import (
    clean_research_dataframe,
    detect_header_row,
    groupable_columns,
    groups_from_column,
    paired_from_long,
    eta_squared,
    holm_adjust,
)


def test_header_detection_removes_metadata_rows_and_unnamed_columns():
    raw = pd.DataFrame([
        ["Study export", None, None],
        ["Generated", "today", None],
        [None, None, None],
        ["Experiment", "Decision Regret", "Completeness"],
        ["001A", 0.10, 1.0],
        ["001B", 0.20, 0.9],
    ])
    clean, header_row = clean_research_dataframe(raw)
    assert header_row == 3
    assert list(clean.columns) == ["Experiment", "Decision Regret", "Completeness"]
    assert clean.shape == (2, 3)


def test_groupable_columns_include_discrete_numeric_and_categorical():
    df = pd.DataFrame({
        "Outcome": [1, 2, 3, 4],
        "Condition": ["A", "A", "B", "B"],
        "Dose": [0, 0, 10, 10],
        "ID": [1001, 1002, 1003, 1004],
    })
    groups = groupable_columns(df, max_unique=5)
    assert "Condition" in groups
    assert "Dose" in groups
    assert "ID" not in groups


def test_groups_from_numeric_column_is_stable():
    df = pd.DataFrame({"Dose": [0, 0, 10, np.nan]})
    result = groups_from_column(df, "Dose")
    assert result.iloc[0] == "0"
    assert result.iloc[2] == "10"
    assert pd.isna(result.iloc[3])


def test_paired_from_long_matches_same_entity_across_conditions():
    df = pd.DataFrame({
        "Scenario ID": [1, 1, 2, 2, 3, 3],
        "Condition": ["A", "B", "A", "B", "A", "B"],
        "Regret": [1.0, 2.0, 2.0, 3.0, 4.0, 3.0],
    })
    paired = paired_from_long(
        df, "Regret", "Scenario ID", "Condition", "A", "B"
    )
    assert list(paired.columns) == ["A", "B"]
    assert len(paired) == 3
    assert paired.loc[1, "A"] == 1.0
    assert paired.loc[1, "B"] == 2.0


def test_eta_squared_is_between_zero_and_one():
    groups = [np.array([1.0, 1.0]), np.array([3.0, 3.0])]
    value = eta_squared(groups)
    assert 0.0 <= value <= 1.0
    assert value > 0.9


def test_holm_adjust_is_monotone_after_sorting_and_bounded():
    p = holm_adjust([0.001, 0.01, 0.2])
    assert np.all((p >= 0) & (p <= 1))
    assert p[0] <= p[1] <= p[2]
