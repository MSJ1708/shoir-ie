"""Bounded statistical tools for Shoir-IE targets T036 and T037.

T036 implements numeric-only ordinary least-squares regression with classical
homoskedastic standard errors. T037 implements one-sample, independent Welch,
and paired t-tests. These methods are not substitutes for study design,
causal analysis, or a full statistical review.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def _finite_series(values: Sequence[Any], label: str, *, minimum: int = 2) -> np.ndarray:
    """Parse a one-dimensional finite numeric sample without dropping rows."""
    try:
        array = np.asarray(list(values), dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain numeric values only; missing or non-numeric rows are not silently dropped.") from exc
    if array.ndim != 1:
        raise ValueError(f"{label} must be one-dimensional.")
    if len(array) < minimum:
        raise ValueError(f"{label} requires at least {minimum} observations.")
    if not np.isfinite(array).all():
        raise ValueError(f"{label} contains missing or non-finite observations; correct them before analysis.")
    return array


def _valid_alpha(alpha: float) -> float:
    try:
        value = float(alpha)
    except (TypeError, ValueError) as exc:
        raise ValueError("Alpha must be numeric and strictly between 0 and 1.") from exc
    if not math.isfinite(value) or not 0 < value < 1:
        raise ValueError("Alpha must be finite and strictly between 0 and 1.")
    return value


def ordinary_least_squares(
    data: pd.DataFrame,
    response: str,
    predictors: Sequence[str],
    *,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Fit OLS with an intercept, classical standard errors, CI, and diagnostics.

    Categorical encoding, imputation, robust standard errors, weighted least
    squares, automatic feature selection and causal identification are not
    performed. Every row is used exactly as entered or rejected.
    """
    alpha = _valid_alpha(alpha)
    if not isinstance(data, pd.DataFrame) or data.empty:
        raise ValueError("Regression data must be a non-empty dataframe.")
    if data.columns.has_duplicates:
        raise ValueError("Regression data must have unique column names.")
    response = str(response or "").strip()
    columns = [str(col).strip() for col in predictors]
    if not response or response not in data.columns:
        raise ValueError("Select a response column that exists in the table.")
    if not columns:
        raise ValueError("Select at least one predictor column.")
    if len(set(columns)) != len(columns):
        raise ValueError("Predictor columns must not be duplicated.")
    if response in columns:
        raise ValueError("The response cannot also be listed as a predictor.")
    unknown = [col for col in [*columns, response] if col not in data.columns]
    if unknown:
        raise ValueError(f"Selected columns are missing: {', '.join(unknown)}.")

    selected = data[[response, *columns]].copy()
    numeric = {}
    for col in selected.columns:
        try:
            converted = pd.to_numeric(selected[col], errors="raise").astype(float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Column '{col}' must contain numeric values only; rows were not dropped.") from exc
        values = converted.to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError(f"Column '{col}' contains missing or non-finite values; correct them before analysis.")
        numeric[col] = values

    y = numeric[response]
    n = int(len(y))
    p = len(columns)
    parameter_count = p + 1
    residual_df = n - parameter_count
    if residual_df <= 0:
        raise ValueError(
            f"Regression needs more rows than parameters: received {n} rows for {parameter_count} coefficients including the intercept."
        )

    x_predictors = np.column_stack([numeric[col] for col in columns])
    design = np.column_stack([np.ones(n, dtype=float), x_predictors])
    rank = int(np.linalg.matrix_rank(design))
    if rank != parameter_count:
        raise ValueError(
            "The model matrix is rank-deficient (a constant or collinear predictor exists). Remove or redesign predictors before fitting."
        )

    beta, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ beta
    residuals = y - fitted
    sse_raw = float(residuals @ residuals)
    centered = y - float(np.mean(y))
    sst = float(centered @ centered)
    numerical_floor = np.finfo(float).eps * max(1.0, sst) * n * 10.0
    sse = 0.0 if sse_raw <= numerical_floor else sse_raw
    ssr = max(0.0, sst - sse)
    mse = sse / residual_df
    covariance = mse * np.linalg.inv(design.T @ design)
    standard_errors = np.sqrt(np.maximum(0.0, np.diag(covariance)))
    t_critical = float(stats.t.ppf(1.0 - alpha / 2.0, residual_df))

    coefficient_rows = []
    terms = ["Intercept", *columns]
    for i, term in enumerate(terms):
        estimate = float(beta[i])
        standard_error = float(standard_errors[i])
        if standard_error > 0:
            t_stat = estimate / standard_error
            p_value = float(2.0 * stats.t.sf(abs(t_stat), residual_df))
        elif estimate > 0:
            t_stat, p_value = math.inf, 0.0
        elif estimate < 0:
            t_stat, p_value = -math.inf, 0.0
        else:
            t_stat, p_value = math.nan, math.nan
        coefficient_rows.append({
            "Term": term,
            "Coefficient": estimate,
            "Std. Error (classical)": standard_error,
            "t statistic": float(t_stat),
            "p value": float(p_value),
            f"{100.0 * (1.0 - alpha):g}% CI lower": estimate - t_critical * standard_error,
            f"{100.0 * (1.0 - alpha):g}% CI upper": estimate + t_critical * standard_error,
        })

    r_squared = 1.0 if sst <= numerical_floor and sse <= numerical_floor else (1.0 - sse / sst if sst > 0 else math.nan)
    adjusted_r_squared = 1.0 - (1.0 - r_squared) * (n - 1) / residual_df if math.isfinite(r_squared) else math.nan
    if sse <= numerical_floor and ssr > numerical_floor:
        f_stat, f_p_value = math.inf, 0.0
    elif p > 0 and residual_df > 0 and sse > 0:
        f_stat = (ssr / p) / mse
        f_p_value = float(stats.f.sf(f_stat, p, residual_df))
    else:
        f_stat, f_p_value = math.nan, math.nan

    warnings = [
        "Classical standard errors and p-values rely on the specified linear model and assumptions including independent errors with constant variance.",
        "A statistically significant association does not establish causation; predictor choice and confounding remain the analyst's responsibility.",
    ]
    if n < 20:
        warnings.append("Small sample: coefficient and residual diagnostics may be unstable; review the study design and residuals.")
    if sse <= numerical_floor:
        warnings.append("Near-perfect fit detected; standard errors and some inferential statistics are degenerate and should not be treated as evidence of predictive performance.")
    if sst <= numerical_floor:
        warnings.append("The response has no material variation; R-squared and overall model inference are not informative.")

    coefficient_table = pd.DataFrame(coefficient_rows)
    prediction_table = pd.DataFrame({
        "Observed": y,
        "Fitted": fitted,
        "Residual": residuals,
    })
    return {
        "tool_id": "T036",
        "status": "CALCULATED",
        "method": "Ordinary least squares (OLS) with intercept and classical homoskedastic standard errors",
        "formula": "beta = (X'X)^(-1)X'y; R² = 1 − SSE/SST; adjusted R² = 1 − (1 − R²)(n − 1)/(n − p − 1)",
        "assumptions": [
            "All selected rows are numeric and finite; no missing rows are imputed or dropped.",
            "The model includes an intercept and uses the predictors exactly as selected.",
            "Confidence intervals and t/F tests use classical OLS assumptions; robust covariance and categorical encoding are not implemented.",
        ],
        "warnings": warnings,
        "metrics": {
            "observations": n,
            "predictors": p,
            "residual_degrees_of_freedom": residual_df,
            "SSE": float(sse),
            "SST": float(sst),
            "R_squared": float(r_squared),
            "adjusted_R_squared": float(adjusted_r_squared),
            "model_F_statistic": float(f_stat),
            "model_F_p_value": float(f_p_value),
            "alpha": alpha,
        },
        "coefficient_table": coefficient_table,
        "prediction_residuals": prediction_table,
    }


def supported_t_test(
    sample_a: Sequence[Any],
    *,
    test_type: str = "one_sample",
    sample_b: Sequence[Any] | None = None,
    null_difference: float = 0.0,
    alpha: float = 0.05,
    alternative: str = "two-sided",
) -> dict[str, Any]:
    """Run a one-sample, independent Welch two-sample, or paired t-test."""
    alpha = _valid_alpha(alpha)
    if alternative not in {"two-sided", "greater", "less"}:
        raise ValueError("Alternative must be 'two-sided', 'greater' or 'less'.")
    try:
        null_value = float(null_difference)
    except (TypeError, ValueError) as exc:
        raise ValueError("Null mean difference must be numeric.") from exc
    if not math.isfinite(null_value):
        raise ValueError("Null mean difference must be finite.")

    kind = str(test_type or "").strip().lower()
    if kind not in {"one_sample", "independent_welch", "paired"}:
        raise ValueError("Supported test type must be one_sample, independent_welch, or paired.")
    a = _finite_series(sample_a, "Sample A")
    b = None if sample_b is None else _finite_series(sample_b, "Sample B")

    if kind == "one_sample":
        if b is not None:
            raise ValueError("Sample B must be omitted for a one-sample t-test.")
        difference = float(np.mean(a) - null_value)
        standard_error = float(np.std(a, ddof=1) / math.sqrt(len(a)))
        df = float(len(a) - 1)
        test = stats.ttest_1samp(a, popmean=null_value, alternative=alternative)
        effect_denominator = float(np.std(a, ddof=1))
        method = "One-sample Student t-test"
        n_b = None
        se_formula = "sA / sqrt(nA)"
    elif kind == "independent_welch":
        if b is None:
            raise ValueError("Sample B is required for an independent Welch t-test.")
        difference = float(np.mean(a) - np.mean(b) - null_value)
        var_a = float(np.var(a, ddof=1))
        var_b = float(np.var(b, ddof=1))
        se2 = var_a / len(a) + var_b / len(b)
        standard_error = math.sqrt(se2)
        denominator = (var_a / len(a)) ** 2 / (len(a) - 1) + (var_b / len(b)) ** 2 / (len(b) - 1)
        if denominator <= 0 or se2 <= 0:
            raise ValueError("The independent samples have zero combined variance; the t statistic and Welch degrees of freedom are undefined.")
        df = float(se2 ** 2 / denominator)
        test = stats.ttest_ind(a, b, equal_var=False, alternative=alternative)
        effect_denominator = math.sqrt(((len(a) - 1) * var_a + (len(b) - 1) * var_b) / (len(a) + len(b) - 2))
        method = "Independent two-sample Welch t-test (unequal variances not pooled)"
        n_b = int(len(b))
        se_formula = "sqrt(sA²/nA + sB²/nB)"
    else:
        if b is None:
            raise ValueError("Sample B is required for a paired t-test.")
        if len(a) != len(b):
            raise ValueError("Paired samples must have exactly the same number of observations in matching order.")
        differences = a - b
        difference = float(np.mean(differences) - null_value)
        standard_error = float(np.std(differences, ddof=1) / math.sqrt(len(differences)))
        df = float(len(differences) - 1)
        test = stats.ttest_1samp(differences, popmean=null_value, alternative=alternative)
        effect_denominator = float(np.std(differences, ddof=1))
        method = "Paired t-test on within-pair differences"
        n_b = int(len(b))
        se_formula = "sd(A − B) / sqrt(n pairs)"

    if standard_error > 0:
        t_statistic = float(test.statistic)
        p_value = float(test.pvalue)
        t_critical = float(stats.t.ppf(1.0 - alpha / 2.0, df))
        ci_lower = difference - t_critical * standard_error
        ci_upper = difference + t_critical * standard_error
    else:
        raise ValueError("Sample variance is zero; this implementation does not report a degenerate t-test.")
    cohen_d = difference / effect_denominator if effect_denominator > 0 else math.nan
    warnings = [
        "A p-value does not measure practical importance and does not establish causation.",
        "The confidence interval shown is two-sided even when a directional alternative is selected.",
        "Independence, measurement quality, representativeness, and model assumptions require human review.",
    ]
    if min(len(a), len(b) if b is not None else len(a)) < 10:
        warnings.append("Small sample: inspect distributions and outliers; inference can be sensitive to assumptions.")
    return {
        "tool_id": "T037",
        "status": "CALCULATED",
        "method": method,
        "formulas": {
            "mean_difference": "mean(A) − reference (one sample), mean(A) − mean(B) (independent), or mean(A − B) (paired)",
            "standard_error": se_formula,
            "test_statistic": "t = (estimated mean difference − null difference) / standard error",
            "confidence_interval": "estimate ± t_(1 − alpha/2, df) × standard error (two-sided)",
        },
        "assumptions": [
            "The selected supported t-test and alpha/alternative are recorded in the result.",
            "Welch's independent test does not assume equal population variances; observations within each sample are still assumed independent.",
            "The paired test requires pairs to be supplied in corresponding order.",
        ],
        "warnings": warnings,
        "metrics": {
            "test_type": kind,
            "n_sample_a": int(len(a)),
            "n_sample_b": n_b,
            "mean_a": float(np.mean(a)),
            "mean_b": float(np.mean(b)) if b is not None else None,
            "estimated_mean_difference": float(difference),
            "null_difference": float(null_value),
            "standard_error": float(standard_error),
            "t_statistic": float(t_statistic),
            "degrees_of_freedom": float(df),
            "p_value": float(p_value),
            "confidence_level": 1.0 - alpha,
            "confidence_interval_lower": float(ci_lower),
            "confidence_interval_upper": float(ci_upper),
            "cohens_d": float(cohen_d),
            "alpha": alpha,
            "alternative": alternative,
        },
    }
