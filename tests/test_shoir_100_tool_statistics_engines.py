"""Golden and validation fixtures for Shoir-IE's bounded T036/T037 statistics."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from shoir_100_tool_statistics_engines import ordinary_least_squares, supported_t_test


def test_ols_recovers_known_line_and_emits_coefficient_and_residual_tables():
    frame = pd.DataFrame({"load": [1, 2, 3, 4, 5, 6], "output": [3, 5, 7, 9, 11, 13]})
    result = ordinary_least_squares(frame, "output", ["load"])
    assert result["tool_id"] == "T036"
    assert result["status"] == "CALCULATED"
    coef = result["coefficient_table"].set_index("Term")["Coefficient"]
    assert coef["Intercept"] == pytest.approx(1.0)
    assert coef["load"] == pytest.approx(2.0)
    assert result["metrics"]["R_squared"] == pytest.approx(1.0)
    assert len(result["prediction_residuals"]) == len(frame)
    assert any("Near-perfect fit" in warning for warning in result["warnings"])


def test_ols_noisy_fixture_matches_independent_linear_algebra_recalculation():
    frame = pd.DataFrame({"x": [0, 1, 2, 3, 4, 5], "y": [1, 2, 1, 4, 3, 6]})
    result = ordinary_least_squares(frame, "y", ["x"])
    design = np.column_stack([np.ones(len(frame)), frame["x"].to_numpy(dtype=float)])
    beta = np.linalg.solve(design.T @ design, design.T @ frame["y"].to_numpy(dtype=float))
    assert result["coefficient_table"]["Coefficient"].to_numpy() == pytest.approx(beta)
    assert result["metrics"]["R_squared"] == pytest.approx(1.0 - result["metrics"]["SSE"] / result["metrics"]["SST"])
    assert math.isfinite(result["metrics"]["model_F_p_value"])
    assert result["coefficient_table"]["Std. Error (classical)"].gt(0).all()


def test_ols_rejects_non_numeric_missing_rank_deficient_and_overparameterized_inputs():
    with pytest.raises(ValueError, match="numeric values"):
        ordinary_least_squares(pd.DataFrame({"x": [1, 2, "oops"], "y": [3, 5, 7]}), "y", ["x"])
    with pytest.raises(ValueError, match="missing or non-finite"):
        ordinary_least_squares(pd.DataFrame({"x": [1, np.nan, 3], "y": [3, 5, 7]}), "y", ["x"])
    with pytest.raises(ValueError, match="rank-deficient"):
        ordinary_least_squares(pd.DataFrame({"x": [1, 2, 3, 4], "x2": [2, 4, 6, 8], "y": [3, 5, 7, 9]}), "y", ["x", "x2"])
    with pytest.raises(ValueError, match="more rows than parameters"):
        ordinary_least_squares(pd.DataFrame({"x": [1, 2], "y": [3, 5]}), "y", ["x"])


def test_one_sample_t_test_golden_fixture():
    result = supported_t_test([2, 4, 6], test_type="one_sample", null_difference=0, alpha=0.05)
    expected = stats.ttest_1samp([2, 4, 6], popmean=0)
    assert result["metrics"]["estimated_mean_difference"] == pytest.approx(4)
    assert result["metrics"]["t_statistic"] == pytest.approx(expected.statistic)
    assert result["metrics"]["p_value"] == pytest.approx(expected.pvalue)
    assert result["metrics"]["degrees_of_freedom"] == 2


def test_welch_and_paired_tests_match_scipy_and_validate_pairs():
    welch = supported_t_test([1, 2, 3], test_type="independent_welch", sample_b=[4, 5, 6])
    expected_welch = stats.ttest_ind([1, 2, 3], [4, 5, 6], equal_var=False)
    assert welch["metrics"]["estimated_mean_difference"] == pytest.approx(-3)
    assert welch["metrics"]["t_statistic"] == pytest.approx(expected_welch.statistic)
    assert welch["metrics"]["p_value"] == pytest.approx(expected_welch.pvalue)

    paired = supported_t_test([2, 4, 6], test_type="paired", sample_b=[1, 2, 3])
    expected_paired = stats.ttest_rel([2, 4, 6], [1, 2, 3])
    assert paired["metrics"]["estimated_mean_difference"] == pytest.approx(2)
    assert paired["metrics"]["t_statistic"] == pytest.approx(expected_paired.statistic)
    assert paired["metrics"]["p_value"] == pytest.approx(expected_paired.pvalue)

    with pytest.raises(ValueError, match="same number"):
        supported_t_test([1, 2, 3], test_type="paired", sample_b=[1, 2])


def test_t_test_rejects_unknown_mode_alpha_and_non_finite_samples():
    with pytest.raises(ValueError, match="Supported test type"):
        supported_t_test([1, 2, 3], test_type="anova")
    with pytest.raises(ValueError, match="strictly between"):
        supported_t_test([1, 2], alpha=1.0)
    with pytest.raises(ValueError, match="non-finite"):
        supported_t_test([1, np.inf, 3])
