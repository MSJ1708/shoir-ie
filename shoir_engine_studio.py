"""Unified engineering experiment, forecasting, and optimization engines.

The functions in this module are deterministic by default, explicit about their
assumptions, and return tabular evidence suitable for Shoir-IE persistence and
Universal Visualization.  No function fabricates observations.
"""

from __future__ import annotations

import io
import json
import math
import zipfile
from itertools import product
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats
from scipy.optimize import minimize, linprog
import pulp


# ---------------------------------------------------------------------------
# Experiment Engine
# ---------------------------------------------------------------------------

def _require_numeric(values: Sequence[Any], name: str, minimum: int = 2) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").dropna().astype(float).to_numpy()
    if len(arr) < minimum:
        raise ValueError(f"{name} needs at least {minimum} numeric observations.")
    return arr


def build_factorial_design(
    factors: pd.DataFrame,
    center_points: int = 0,
    replications: int = 1,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a randomized 2-level full-factorial design with optional centers and replications.

    Required columns: Factor, Low, High.
    """
    required = {"Factor", "Low", "High"}
    if not required <= set(factors.columns):
        raise ValueError("Factor table requires Factor, Low and High columns.")
    specs = factors[["Factor", "Low", "High"]].copy()
    specs["Factor"] = specs["Factor"].astype(str).str.strip()
    specs = specs[specs["Factor"] != ""].drop_duplicates("Factor")
    if specs.empty:
        raise ValueError("At least one factor is required.")
    if len(specs) > 12:
        raise ValueError("Full factorial is limited to 12 factors (4,096 base runs).")
    replications = int(replications)
    center_points = int(center_points)
    if replications < 1 or center_points < 0:
        raise ValueError("Replications must be >= 1 and center points must be >= 0.")

    factor_names = specs["Factor"].tolist()
    for col in ["Low", "High"]:
        specs[col] = pd.to_numeric(specs[col], errors="coerce")
    if specs[["Low", "High"]].isna().any().any():
        raise ValueError("Low and High levels must be numeric for the current factorial engine.")
    if (specs["High"] <= specs["Low"]).any():
        bad = specs.loc[specs["High"] <= specs["Low"], "Factor"].tolist()
        raise ValueError(f"High must be greater than Low for: {bad}")

    rows: list[dict[str, Any]] = []
    for codes in product([-1, 1], repeat=len(factor_names)):
        row: dict[str, Any] = {}
        for name, code in zip(factor_names, codes):
            low = float(specs.loc[specs["Factor"] == name, "Low"].iloc[0])
            high = float(specs.loc[specs["Factor"] == name, "High"].iloc[0])
            row[name] = low if code < 0 else high
            row[f"__code__{name}"] = code
        row["DesignPoint"] = "Factorial"
        rows.append(row)

    if center_points:
        for _ in range(center_points):
            row = {name: float((specs.loc[specs["Factor"] == name, "Low"].iloc[0] +
                                specs.loc[specs["Factor"] == name, "High"].iloc[0]) / 2)
                   for name in factor_names}
            row.update({f"__code__{name}": 0 for name in factor_names})
            row["DesignPoint"] = "Center"
            rows.append(row)

    base = pd.DataFrame(rows)
    base = pd.concat([base] * replications, ignore_index=True)
    base["Replication"] = np.tile(np.arange(1, replications + 1), int(math.ceil(len(base) / replications)))[:len(base)]
    base["Run"] = np.arange(1, len(base) + 1)
    rng = np.random.default_rng(int(seed))
    base["RandomizedOrder"] = rng.permutation(np.arange(1, len(base) + 1))
    base = base.sort_values("RandomizedOrder").reset_index(drop=True)
    return base


def _model_matrix(design: pd.DataFrame, factor_names: Sequence[str], max_interaction_order: int = 2) -> tuple[pd.DataFrame, list[str]]:
    cols = [f"__code__{f}" for f in factor_names]
    missing = [c for c in cols if c not in design.columns]
    if missing:
        raise ValueError(f"Design is missing coded factor columns: {missing}")
    x = pd.DataFrame({"Intercept": np.ones(len(design), dtype=float)}, index=design.index)
    terms = ["Intercept"]
    for f in factor_names:
        key = f"__code__{f}"
        x[f] = pd.to_numeric(design[key], errors="coerce")
        terms.append(f)
    if max_interaction_order >= 2:
        for i, f1 in enumerate(factor_names):
            for f2 in factor_names[i + 1:]:
                x[f"{f1} × {f2}"] = x[f1] * x[f2]
                terms.append(f"{f1} × {f2}")
    if max_interaction_order >= 3 and len(factor_names) >= 3:
        for i, f1 in enumerate(factor_names):
            for j in range(i + 1, len(factor_names)):
                f2 = factor_names[j]
                for f3 in factor_names[j + 1:]:
                    x[f"{f1} × {f2} × {f3}"] = x[f1] * x[f2] * x[f3]
                    terms.append(f"{f1} × {f2} × {f3}")
    return x, terms


def analyze_factorial(
    design_with_response: pd.DataFrame,
    response_col: str,
    factor_names: Sequence[str],
    max_interaction_order: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Fit a coded factorial model and return coefficient/effect/residual evidence."""
    if response_col not in design_with_response.columns:
        raise ValueError(f"Response column '{response_col}' is missing.")
    d = design_with_response.copy()
    y = pd.to_numeric(d[response_col], errors="coerce")
    valid = y.notna()
    d = d.loc[valid].copy()
    y = y.loc[valid].astype(float)
    if len(d) < max(6, len(factor_names) + 2):
        raise ValueError("Not enough completed response observations for factorial analysis.")

    x, terms = _model_matrix(d, factor_names, max_interaction_order=max_interaction_order)
    x = x.loc[d.index]
    matrix = x.to_numpy(dtype=float)
    response = y.to_numpy(dtype=float)
    coef, *_ = np.linalg.lstsq(matrix, response, rcond=None)
    fitted = matrix @ coef
    residuals = response - fitted
    n, p = matrix.shape
    df_resid = max(1, n - p)
    sse = float(np.sum(residuals ** 2))
    mse = sse / df_resid
    try:
        cov = mse * np.linalg.pinv(matrix.T @ matrix)
        se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    except Exception:
        se = np.full(len(coef), np.nan)
    tvals = np.divide(coef, se, out=np.full_like(coef, np.nan), where=se > 0)
    pvals = 2 * stats.t.sf(np.abs(tvals), df_resid)
    ybar = float(np.mean(response))
    sst = float(np.sum((response - ybar) ** 2))
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    adj_r2 = 1.0 - (1.0 - r2) * (n - 1) / max(1, n - p)
    effect = 2.0 * coef
    ci_low = coef - stats.t.ppf(0.975, df_resid) * se
    ci_high = coef + stats.t.ppf(0.975, df_resid) * se
    effects = pd.DataFrame({
        "Term": terms,
        "Coefficient": coef,
        "Effect (2×coef)": effect,
        "Std Error": se,
        "t": tvals,
        "p_value": pvals,
        "CI Lower": ci_low,
        "CI Upper": ci_high,
    })
    fitted_df = d.reset_index(drop=False).copy()
    fitted_df["Predicted"] = fitted
    fitted_df["Residual"] = residuals
    summary = {
        "Observations": int(n),
        "Parameters": int(p),
        "Residual DF": int(df_resid),
        "SSE": sse,
        "RMSE": float(math.sqrt(max(mse, 0.0))),
        "R2": float(r2),
        "Adjusted R2": float(adj_r2),
        "Response Mean": ybar,
        "Response Std": float(np.std(response, ddof=1)) if n > 1 else 0.0,
        "Model Terms": terms,
    }
    return effects, fitted_df, summary


def summarize_replications(
    data: pd.DataFrame,
    metric_col: str,
    replication_col: str = "Replication",
    confidence: float = 0.95,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if metric_col not in data.columns:
        raise ValueError(f"Metric column '{metric_col}' is missing.")
    d = data.copy()
    d[metric_col] = pd.to_numeric(d[metric_col], errors="coerce")
    if replication_col not in d.columns:
        d[replication_col] = np.arange(1, len(d) + 1)
    d = d.dropna(subset=[metric_col])
    if d.empty:
        raise ValueError("No numeric replication observations are available.")
    grouped = d.groupby(replication_col)[metric_col].agg(["count", "mean", "std"]).reset_index()
    grouped = grouped.rename(columns={"count": "N", "mean": "Mean", "std": "Std Dev"})
    grouped["SEM"] = grouped["Std Dev"] / np.sqrt(grouped["N"].clip(lower=1))
    grouped["CI Lower"] = grouped["Mean"] - stats.t.ppf((1 + confidence) / 2, grouped["N"].clip(lower=1) - 1).fillna(0) * grouped["SEM"].fillna(0)
    grouped["CI Upper"] = grouped["Mean"] + stats.t.ppf((1 + confidence) / 2, grouped["N"].clip(lower=1) - 1).fillna(0) * grouped["SEM"].fillna(0)
    values = d[metric_col].to_numpy(dtype=float)
    overall = {
        "Replications": int(d[replication_col].nunique()),
        "Observations": int(len(values)),
        "Mean": float(np.mean(values)),
        "Std Dev": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "SEM": float(np.std(values, ddof=1) / math.sqrt(len(values))) if len(values) > 1 else 0.0,
        "CI Lower": float(np.mean(values) - stats.t.ppf((1 + confidence) / 2, max(1, len(values) - 1)) * (np.std(values, ddof=1) / math.sqrt(len(values)))) if len(values) > 1 else float(np.mean(values)),
        "CI Upper": float(np.mean(values) + stats.t.ppf((1 + confidence) / 2, max(1, len(values) - 1)) * (np.std(values, ddof=1) / math.sqrt(len(values)))) if len(values) > 1 else float(np.mean(values)),
        "Half Width": float(stats.t.ppf((1 + confidence) / 2, max(1, len(values) - 1)) * (np.std(values, ddof=1) / math.sqrt(len(values)))) if len(values) > 1 else 0.0,
    }
    return grouped, overall


def bootstrap_difference(
    group_a: Sequence[Any],
    group_b: Sequence[Any],
    iterations: int = 4000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    a = _require_numeric(group_a, "Group A", minimum=3)
    b = _require_numeric(group_b, "Group B", minimum=3)
    iterations = int(iterations)
    if iterations < 500:
        raise ValueError("Bootstrap iterations must be at least 500.")
    rng = np.random.default_rng(int(seed))
    means_a = rng.choice(a, size=(iterations, len(a)), replace=True).mean(axis=1)
    means_b = rng.choice(b, size=(iterations, len(b)), replace=True).mean(axis=1)
    diffs = means_a - means_b
    alpha = 1 - confidence
    summary = {
        "Group A Mean": float(a.mean()),
        "Group B Mean": float(b.mean()),
        "Observed Difference (A-B)": float(a.mean() - b.mean()),
        "Bootstrap Mean Difference": float(diffs.mean()),
        "CI Lower": float(np.quantile(diffs, alpha / 2)),
        "CI Upper": float(np.quantile(diffs, 1 - alpha / 2)),
        "P(Difference > 0)": float(np.mean(diffs > 0)),
        "Iterations": iterations,
        "Seed": int(seed),
    }
    return pd.DataFrame({"Bootstrap Difference": diffs}), summary


def effect_size(a: Sequence[Any], b: Sequence[Any]) -> dict[str, float]:
    x = _require_numeric(a, "Group A", minimum=3)
    y = _require_numeric(b, "Group B", minimum=3)
    nx, ny = len(x), len(y)
    vx, vy = np.var(x, ddof=1), np.var(y, ddof=1)
    pooled = math.sqrt(max(1e-12, ((nx - 1) * vx + (ny - 1) * vy) / max(1, nx + ny - 2)))
    d = float((x.mean() - y.mean()) / pooled)
    correction = 1 - 3 / max(1e-12, 4 * (nx + ny) - 9)
    return {"Cohen's d": d, "Hedges' g": float(d * correction), "Pooled SD": float(pooled)}


def monte_carlo_uncertainty(
    specs: pd.DataFrame,
    simulations: int = 10000,
    seed: int = 42,
    intercept: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"Name", "Mean", "Std", "Distribution", "Coefficient"}
    if not required <= set(specs.columns):
        raise ValueError("Uncertainty table requires Name, Mean, Std, Distribution and Coefficient.")
    simulations = int(simulations)
    if simulations < 500:
        raise ValueError("Monte Carlo simulations must be at least 500.")
    rng = np.random.default_rng(int(seed))
    draws: dict[str, np.ndarray] = {}
    for _, row in specs.iterrows():
        name = str(row["Name"]).strip()
        if not name:
            continue
        mean = float(row["Mean"])
        std = max(0.0, float(row["Std"]))
        dist = str(row["Distribution"]).strip().lower()
        if dist == "normal":
            sample = rng.normal(mean, max(std, 1e-12), simulations)
        elif dist == "uniform":
            low = float(row.get("Low", mean - math.sqrt(3) * std))
            high = float(row.get("High", mean + math.sqrt(3) * std))
            if high <= low:
                raise ValueError(f"Uniform bounds invalid for {name}.")
            sample = rng.uniform(low, high, simulations)
        elif dist == "triangular":
            low = float(row.get("Low", mean - math.sqrt(6) * std))
            high = float(row.get("High", mean + math.sqrt(6) * std))
            if high <= low:
                raise ValueError(f"Triangular bounds invalid for {name}.")
            mode = min(high, max(low, mean))
            sample = rng.triangular(low, mode, high, simulations)
        else:
            raise ValueError(f"Unsupported distribution '{row['Distribution']}' for {name}.")
        draws[name] = sample
    if not draws:
        raise ValueError("At least one uncertainty input is required.")
    out = pd.DataFrame(draws)
    for _, row in specs.iterrows():
        name = str(row["Name"]).strip()
        if name in out.columns:
            out[f"Contribution · {name}"] = out[name] * float(row["Coefficient"])
    contribution_cols = [c for c in out.columns if c.startswith("Contribution · ")]
    out["Output"] = float(intercept) + out[contribution_cols].sum(axis=1)
    q = np.quantile(out["Output"], [0.01, 0.05, 0.5, 0.95, 0.99])
    summary = {
        "Mean": float(out["Output"].mean()),
        "Std Dev": float(out["Output"].std(ddof=1)),
        "P01": float(q[0]),
        "P05": float(q[1]),
        "P50": float(q[2]),
        "P95": float(q[3]),
        "P99": float(q[4]),
        "P(Output <= 0)": float(np.mean(out["Output"] <= 0)),
        "Simulations": simulations,
        "Seed": int(seed),
        "Intercept": float(intercept),
    }
    return out, summary


def sensitivity_screen(
    df: pd.DataFrame,
    outcome: str,
    inputs: Sequence[str] | None = None,
) -> pd.DataFrame:
    if outcome not in df.columns:
        raise ValueError(f"Outcome '{outcome}' is missing.")
    numeric = [str(c) for c in df.select_dtypes(include=np.number).columns if str(c) != str(outcome)]
    inputs = list(inputs or numeric)
    inputs = [c for c in inputs if c in df.columns and c != outcome]
    if not inputs:
        raise ValueError("At least one numeric input is required.")
    rows = []
    base = df[[outcome] + inputs].apply(pd.to_numeric, errors="coerce").dropna()
    if len(base) < 3:
        raise ValueError("Sensitivity analysis needs at least 3 complete observations.")
    y = base[outcome].to_numpy(dtype=float)
    yz = (y - y.mean()) / max(y.std(ddof=1), 1e-12)
    for col in inputs:
        x = base[col].to_numpy(dtype=float)
        corr = float(np.corrcoef(x, y)[0, 1]) if np.std(x) > 0 else 0.0
        xz = (x - x.mean()) / max(x.std(ddof=1), 1e-12)
        slope = float(np.dot(xz, yz) / max(1, len(x) - 1))
        rows.append({
            "Driver": col,
            "Pearson r": corr,
            "Sensitivity": abs(corr),
            "Direction": "Positive" if corr >= 0 else "Negative",
            "Standardized Slope": slope,
        })
    return pd.DataFrame(rows).sort_values("Sensitivity", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

def _forecast_features(dates: pd.Series, start_index: int, external: Mapping[str, Sequence[float]] | None = None) -> pd.DataFrame:
    dates = pd.to_datetime(dates)
    x = pd.DataFrame(index=np.arange(len(dates)))
    x["trend"] = np.arange(start_index, start_index + len(dates), dtype=float)
    month = dates.dt.month.to_numpy()
    x["sin_month"] = np.sin(2 * np.pi * month / 12)
    x["cos_month"] = np.cos(2 * np.pi * month / 12)
    for name, values in (external or {}).items():
        x[name] = np.asarray(values, dtype=float)
    return x


def forecast_series(
    df: pd.DataFrame,
    date_col: str,
    target_col: str,
    external_cols: Sequence[str] = (),
    horizon: int = 12,
    holdout_fraction: float = 0.2,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if date_col not in df.columns or target_col not in df.columns:
        raise ValueError("Forecast requires a date column and target column.")
    d = df.copy()
    d[date_col] = pd.to_datetime(d[date_col], errors="coerce")
    d[target_col] = pd.to_numeric(d[target_col], errors="coerce")
    d = d.dropna(subset=[date_col, target_col]).sort_values(date_col).reset_index(drop=True)
    if len(d) < 10:
        raise ValueError("At least 10 observations are required for time-aware validation.")
    ext = []
    for c in external_cols:
        if c in d.columns and pd.to_numeric(d[c], errors="coerce").notna().sum() >= max(5, len(d) // 2):
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(pd.to_numeric(d[c], errors="coerce").median())
            ext.append(c)

    holdout = max(2, min(len(d) // 3, int(round(len(d) * float(holdout_fraction)))))
    train = d.iloc[:-holdout].copy()
    test = d.iloc[-holdout:].copy()
    train_external = {c: train[c].to_numpy(dtype=float) for c in ext}
    x_train = _forecast_features(train[date_col], 0, train_external)
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    model = LinearRegression().fit(x_train, train[target_col].to_numpy(dtype=float))
    test_external = {c: test[c].to_numpy(dtype=float) for c in ext}
    x_test = _forecast_features(test[date_col], len(train), test_external)
    test_pred = np.maximum(0, model.predict(x_test))
    y_test = test[target_col].to_numpy(dtype=float)
    residuals = y_test - test_pred
    sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(train[target_col] - model.predict(x_train)))
    future_dates = pd.date_range(d[date_col].iloc[-1], periods=int(horizon) + 1, freq=pd.infer_freq(d[date_col]) or "D")[1:]
    future_external = {c: np.repeat(float(train[c].iloc[-1]), int(horizon)) for c in ext}
    x_future = _forecast_features(future_dates, len(d), future_external)
    forecast = np.maximum(0, model.predict(x_future))
    z = 1.96
    result = pd.DataFrame({
        "Date": future_dates,
        "Forecast": forecast,
        "Lower 95%": np.maximum(0, forecast - z * sigma),
        "Upper 95%": forecast + z * sigma,
        "Model": "Trend + Seasonality + External Drivers",
    })
    history = d[[date_col, target_col]].rename(columns={date_col: "Date", target_col: "Actual"}).copy()
    combined = pd.concat([history, result], ignore_index=True, sort=False)
    metrics = {
        "Holdout Observations": int(len(test)),
        "Validation R2": float(r2_score(y_test, test_pred)) if len(np.unique(y_test)) > 1 else 0.0,
        "Validation MAE": float(mean_absolute_error(y_test, test_pred)),
        "Validation RMSE": float(math.sqrt(mean_squared_error(y_test, test_pred))),
        "Residual Std": sigma,
        "External Drivers": ext,
        "Future Driver Assumption": "Last observed driver value held constant.",
        "Horizon": int(horizon),
    }
    return combined, metrics


# ---------------------------------------------------------------------------
# Optimization engines
# ---------------------------------------------------------------------------

def _clean_variable_specs(specs: pd.DataFrame) -> pd.DataFrame:
    required = {"Variable", "Objective Coef", "Lower", "Upper", "Integer", "Binary"}
    if not required <= set(specs.columns):
        raise ValueError("Variable table requires Variable, Objective Coef, Lower, Upper, Integer and Binary.")
    d = specs.copy()
    d["Variable"] = d["Variable"].astype(str).str.strip()
    d = d[d["Variable"] != ""].drop_duplicates("Variable").reset_index(drop=True)
    for c in ["Objective Coef", "Lower", "Upper"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    if d[["Objective Coef", "Lower", "Upper"]].isna().any().any():
        raise ValueError("Objective and bounds must be numeric.")
    if (d["Upper"] < d["Lower"]).any():
        raise ValueError("Every upper bound must be >= lower bound.")
    return d


def _constraint_system(constraints: pd.DataFrame, variables: Sequence[str]) -> list[tuple[str, float, dict[str, float]]]:
    if constraints is None or constraints.empty:
        return []
    needed = {"Constraint", "Sense", "RHS"}
    if not needed <= set(constraints.columns):
        raise ValueError("Constraint table requires Constraint, Sense and RHS columns.")
    rows = []
    for _, r in constraints.iterrows():
        coeffs = {v: float(pd.to_numeric(r.get(v, 0), errors="coerce") or 0) for v in variables}
        sense = str(r["Sense"]).strip()
        if sense not in {"<=", ">=", "="}:
            raise ValueError("Constraint Sense must be <=, >= or =.")
        rows.append((str(r["Constraint"]), sense, float(r["RHS"]), coeffs))
    return rows


def solve_lp_or_milp(
    variables: pd.DataFrame,
    constraints: pd.DataFrame,
    objective_sense: str = "min",
    method: str = "LP",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    d = _clean_variable_specs(variables)
    method = str(method).upper()
    sense = str(objective_sense).lower()
    if sense not in {"min", "max"}:
        raise ValueError("Objective sense must be min or max.")
    names = d["Variable"].tolist()
    if method == "LP" and (d["Integer"].astype(bool) | d["Binary"].astype(bool)).any():
        raise ValueError("LP cannot use integer/binary variable flags. Choose MILP.")
    cons = _constraint_system(constraints, names)

    if method == "MILP":
        prob = pulp.LpProblem("ShoirIE_MILP", pulp.LpMinimize if sense == "min" else pulp.LpMaximize)
        vars_: dict[str, Any] = {}
        for _, r in d.iterrows():
            low = float(r["Lower"])
            up = float(r["Upper"])
            cat = pulp.LpBinary if bool(r["Binary"]) else (pulp.LpInteger if bool(r["Integer"]) else pulp.LpContinuous)
            vars_[r["Variable"]] = pulp.LpVariable(r["Variable"], lowBound=low, upBound=up, cat=cat)
        objective = pulp.lpSum(float(r["Objective Coef"]) * vars_[r["Variable"]] for _, r in d.iterrows())
        prob += objective
        for cname, csense, rhs, coeffs in cons:
            expr = pulp.lpSum(coeffs[v] * vars_[v] for v in names)
            if csense == "<=":
                prob += expr <= rhs, cname
            elif csense == ">=":
                prob += expr >= rhs, cname
            else:
                prob += expr == rhs, cname
        status_code = prob.solve(pulp.PULP_CBC_CMD(msg=False))
        status = pulp.LpStatus.get(status_code, "Unknown")
        if status != "Optimal":
            raise ValueError(f"MILP solver status: {status}")
        solution = pd.DataFrame({"Variable": names, "Value": [float(pulp.value(vars_[v])) for v in names]})
        objective_value = float(pulp.value(prob.objective))
        return solution, {"Method": "MILP", "Status": status, "Objective": objective_value, "Variables": len(names), "Constraints": len(cons)}

    c = d["Objective Coef"].to_numpy(dtype=float)
    if sense == "max":
        c = -c
    bounds = list(zip(d["Lower"], d["Upper"]))
    a_ub, b_ub, a_eq, b_eq = [], [], [], []
    for _, csense, rhs, coeffs in cons:
        row = [coeffs[v] for v in names]
        if csense == "<=":
            a_ub.append(row); b_ub.append(rhs)
        elif csense == ">=":
            a_ub.append([-x for x in row]); b_ub.append(-rhs)
        else:
            a_eq.append(row); b_eq.append(rhs)
    res = linprog(c, A_ub=np.array(a_ub) if a_ub else None, b_ub=np.array(b_ub) if b_ub else None,
                  A_eq=np.array(a_eq) if a_eq else None, b_eq=np.array(b_eq) if b_eq else None,
                  bounds=bounds, method="highs")
    if not res.success:
        raise ValueError(f"LP solver failed: {res.message}")
    obj = float(np.dot(d["Objective Coef"], res.x))
    return pd.DataFrame({"Variable": names, "Value": res.x}), {
        "Method": "LP", "Status": "Optimal", "Objective": obj, "Variables": len(names), "Constraints": len(cons)
    }


def solve_nonlinear_quadratic(
    variables: pd.DataFrame,
    constraints: pd.DataFrame,
    objective_sense: str = "min",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {"Variable", "Linear Coef", "Quadratic Coef", "Lower", "Upper"}
    if not required <= set(variables.columns):
        raise ValueError("Nonlinear variable table requires Variable, Linear Coef, Quadratic Coef, Lower and Upper.")
    d = variables.copy()
    for c in ["Linear Coef", "Quadratic Coef", "Lower", "Upper"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    names = d["Variable"].astype(str).tolist()
    bounds = list(zip(d["Lower"], d["Upper"]))
    cons = _constraint_system(constraints, names)
    sign = 1.0 if str(objective_sense).lower() == "min" else -1.0

    def obj(x: np.ndarray) -> float:
        return sign * float(np.sum(d["Linear Coef"].to_numpy() * x + 0.5 * d["Quadratic Coef"].to_numpy() * x * x))

    scipy_cons = []
    for _, csense, rhs, coeffs in cons:
        a = np.array([coeffs[v] for v in names], dtype=float)
        if csense == "<=":
            scipy_cons.append({"type": "ineq", "fun": lambda x, a=a, rhs=rhs: rhs - np.dot(a, x)})
        elif csense == ">=":
            scipy_cons.append({"type": "ineq", "fun": lambda x, a=a, rhs=rhs: np.dot(a, x) - rhs})
        else:
            scipy_cons.append({"type": "eq", "fun": lambda x, a=a, rhs=rhs: np.dot(a, x) - rhs})
    x0 = np.array([(lo + hi) / 2 for lo, hi in bounds], dtype=float)
    res = minimize(obj, x0, method="SLSQP", bounds=bounds, constraints=scipy_cons,
                   options={"maxiter": 2000, "ftol": 1e-9})
    if not res.success:
        raise ValueError(f"Nonlinear solver failed: {res.message}")
    actual_obj = float(-res.fun if sign < 0 else res.fun)
    return pd.DataFrame({"Variable": names, "Value": res.x}), {
        "Method": "Nonlinear Quadratic", "Status": "Converged", "Objective": actual_obj, "Iterations": int(res.nit)
    }


def robust_stochastic_scenario_analysis(
    df: pd.DataFrame,
    decision_col: str,
    state_col: str,
    metrics: Sequence[str],
    minimize: Mapping[str, bool],
    probability_col: str | None = "Probability",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {decision_col, state_col, *metrics}
    if not required <= set(df.columns):
        raise ValueError(f"Scenario table is missing required columns: {sorted(required - set(df.columns))}")
    d = df.copy()
    for m in metrics:
        d[m] = pd.to_numeric(d[m], errors="coerce")
    d = d.dropna(subset=list(metrics))
    if probability_col and probability_col in d.columns:
        d[probability_col] = pd.to_numeric(d[probability_col], errors="coerce").fillna(0)
    groups = []
    for decision, g in d.groupby(decision_col, sort=False):
        weights = g[probability_col].to_numpy(float) if probability_col and probability_col in g.columns else np.ones(len(g))
        if weights.sum() <= 0:
            weights = np.ones(len(g))
        weights = weights / weights.sum()
        row: dict[str, Any] = {decision_col: decision}
        for metric in metrics:
            vals = g[metric].to_numpy(float)
            row[f"Expected {metric}"] = float(np.dot(weights, vals))
            row[f"Worst {metric}"] = float(np.min(vals) if minimize.get(metric, True) else np.max(vals))
            row[f"P95 {metric}"] = float(np.quantile(vals, 0.95))
        groups.append(row)
    summary = pd.DataFrame(groups)
    normalized = summary.copy()
    for metric in metrics:
        exp = f"Expected {metric}"
        worst = f"Worst {metric}"
        normalized[f"Score · {metric}"] = _minmax(normalized[exp], minimize.get(metric, True))
        normalized[f"Robust Score · {metric}"] = _minmax(normalized[worst], minimize.get(metric, True))
    score_cols = [c for c in normalized.columns if c.startswith("Robust Score · ")]
    exp_cols = [c for c in normalized.columns if c.startswith("Score · ")]
    normalized["Robust Composite"] = normalized[score_cols].mean(axis=1) if score_cols else 0.0
    normalized["Stochastic Expected Composite"] = normalized[exp_cols].mean(axis=1) if exp_cols else 0.0
    return summary, normalized.sort_values("Stochastic Expected Composite").reset_index(drop=True)


def _minmax(series: pd.Series, minimize_flag: bool) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce").astype(float)
    lo, hi = x.min(), x.max()
    if not np.isfinite(lo) or hi == lo:
        return pd.Series(np.zeros(len(x)), index=x.index)
    z = (x - lo) / (hi - lo)
    return z if minimize_flag else (1 - z)


def pareto_candidates(df: pd.DataFrame, objectives: Mapping[str, bool]) -> pd.DataFrame:
    """Return non-dominated candidate decisions for a configurable objective set."""
    cols = list(objectives)
    d = df.copy()
    arr = d[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if len(arr) == 0:
        return d
    mask = np.ones(len(arr), dtype=bool)
    for i in range(len(arr)):
        if not np.isfinite(arr[i]).all():
            mask[i] = False
            continue
        for j in range(len(arr)):
            if i == j or not np.isfinite(arr[j]).all():
                continue
            better_or_equal = True
            strict = False
            for k, col in enumerate(cols):
                if objectives[col]:
                    if arr[j, k] > arr[i, k]:
                        better_or_equal = False
                        break
                    if arr[j, k] < arr[i, k]:
                        strict = True
                else:
                    if arr[j, k] < arr[i, k]:
                        better_or_equal = False
                        break
                    if arr[j, k] > arr[i, k]:
                        strict = True
            if better_or_equal and strict:
                mask[i] = False
                break
    return d.loc[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _save_experiment_evidence(name: str, scenarios: Any, results: Any, username: str) -> str:
    """Persist an engineering/research run without creating a module import cycle at load time."""
    try:
        from industrial_platform import save_experiment
        return save_experiment(name, "Experiment Engine", scenarios, results, username)
    except Exception:
        return ""


def _df_download(df: pd.DataFrame, filename: str) -> None:
    st.download_button(
        "📥 Download CSV evidence",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
    )


def _json_download(payload: Any, filename: str) -> None:
    st.download_button(
        "📥 Download JSON evidence",
        data=json.dumps(payload, default=str, indent=2).encode("utf-8"),
        file_name=filename,
        mime="application/json",
        use_container_width=True,
    )


def render_experiment_engine(tier: str, username: str) -> None:
    st.subheader("🧪 Experiment Engine")
    st.caption("DOE, factorial effects, Monte Carlo uncertainty, bootstrap evidence, sensitivity and replication analysis in one research-ready workspace.")
    tabs = st.tabs(["DOE & Factorial", "Monte Carlo", "Bootstrap & Effects", "Sensitivity", "Replications"])

    with tabs[0]:
        factors = st.data_editor(
            st.session_state.setdefault(
                "experiment_engine_factors",
                pd.DataFrame({"Factor": ["Temperature", "Speed", "Pressure"], "Low": [180, 800, 1.2], "High": [220, 1200, 1.8]}),
            ),
            num_rows="dynamic", use_container_width=True, key="experiment_engine_factor_editor",
        )
        c1, c2, c3 = st.columns(3)
        center = c1.number_input("Center points", min_value=0, max_value=64, value=2, key="experiment_engine_center")
        reps = c2.number_input("Replications", min_value=1, max_value=50, value=2, key="experiment_engine_reps")
        seed = c3.number_input("Random seed", min_value=0, max_value=999999, value=42, key="experiment_engine_seed")
        if st.button("🧪 Generate randomized factorial design", type="primary", use_container_width=True, key="experiment_engine_generate"):
            try:
                design = build_factorial_design(factors, int(center), int(reps), int(seed))
                st.session_state["experiment_engine_design_df"] = design
                st.session_state["experiment_engine_results_df"] = pd.DataFrame()
                st.success(f"Generated {len(design):,} randomized runs.")
            except Exception as exc:
                st.error(f"DOE generation failed safely: {exc}")
        design = st.session_state.get("experiment_engine_design_df", pd.DataFrame())
        if isinstance(design, pd.DataFrame) and not design.empty:
            factor_names = factors["Factor"].astype(str).str.strip().replace("", np.nan).dropna().drop_duplicates().tolist()
            visible = [c for c in design.columns if not c.startswith("__code__")]
            edited = st.data_editor(design[visible], num_rows="dynamic", use_container_width=True, key="experiment_engine_design_editor")
            for f in factor_names:
                if f in edited.columns:
                    design.loc[edited.index, f] = edited[f]
            if "Response" not in design.columns:
                design["Response"] = np.nan
            response = st.data_editor(design[[*factor_names, "Replication", "Run", "Response"]].copy(), num_rows="dynamic", use_container_width=True, key="experiment_engine_response_editor")
            design.loc[response.index, "Response"] = pd.to_numeric(response["Response"], errors="coerce")
            st.session_state["experiment_engine_design_df"] = design
            if st.button("📐 Analyze factorial effects", type="primary", use_container_width=True, key="experiment_engine_analyze"):
                try:
                    effects, fitted, summary = analyze_factorial(design, "Response", factor_names)
                    st.session_state["experiment_engine_effects_df"] = effects
                    st.session_state["experiment_engine_fitted_df"] = fitted
                    st.session_state["experiment_engine_summary"] = summary
                    run_id = _save_experiment_evidence(
                        "Factorial DOE",
                        design.to_dict("records"),
                        {"effects": effects.to_dict("records"), "model_summary": summary},
                        username,
                    )
                    st.session_state["experiment_engine_run_id"] = run_id
                    st.success("Factorial model fitted; coefficients, effects, p-values and confidence intervals are ready.")
                except Exception as exc:
                    st.error(f"Factorial analysis failed safely: {exc}")
        if isinstance(st.session_state.get("experiment_engine_effects_df"), pd.DataFrame):
            st.dataframe(st.session_state["experiment_engine_effects_df"], use_container_width=True, hide_index=True)
            st.json(st.session_state.get("experiment_engine_summary", {}))
            _df_download(st.session_state["experiment_engine_effects_df"], "shoir_ie_factorial_effects.csv")

    with tabs[1]:
        specs = st.data_editor(
            st.session_state.setdefault(
                "experiment_engine_mc_specs",
                pd.DataFrame({
                    "Name": ["Demand", "Lead Time"],
                    "Mean": [1000, 7],
                    "Std": [120, 1.2],
                    "Distribution": ["Normal", "Normal"],
                    "Low": [700, 4],
                    "High": [1300, 10],
                    "Coefficient": [1.0, -25.0],
                }),
            ),
            num_rows="dynamic", use_container_width=True, key="experiment_engine_mc_editor",
        )
        c1, c2 = st.columns(2)
        sims = c1.number_input("Simulations", 500, 100000, 10000, 500, key="experiment_engine_mc_sims")
        intercept = c2.number_input("Output intercept", -1e9, 1e9, 0.0, key="experiment_engine_mc_intercept")
        if st.button("🎲 Propagate uncertainty", type="primary", use_container_width=True, key="experiment_engine_mc_run"):
            try:
                samples, summary = monte_carlo_uncertainty(specs, int(sims), 42, float(intercept))
                st.session_state["experiment_engine_mc_samples"] = samples
                st.session_state["experiment_engine_mc_summary"] = summary
                run_id = _save_experiment_evidence(
                    "Monte Carlo Uncertainty Propagation",
                    specs.to_dict("records"),
                    {"summary": summary},
                    username,
                )
                st.session_state["experiment_engine_run_id"] = run_id
                st.success("Monte Carlo uncertainty propagation completed.")
            except Exception as exc:
                st.error(f"Monte Carlo failed safely: {exc}")
        if st.session_state.get("experiment_engine_mc_summary"):
            st.json(st.session_state["experiment_engine_mc_summary"])
        if isinstance(st.session_state.get("experiment_engine_mc_samples"), pd.DataFrame):
            st.dataframe(st.session_state["experiment_engine_mc_samples"].head(200), use_container_width=True, hide_index=True)
            _df_download(st.session_state["experiment_engine_mc_samples"], "shoir_ie_monte_carlo_samples.csv")

    with tabs[2]:
        a = st.data_editor(st.session_state.setdefault("experiment_engine_group_a", pd.DataFrame({"Group A": [10, 11, 9, 12, 10, 13]})), num_rows="dynamic", use_container_width=True, key="experiment_engine_a_editor")
        b = st.data_editor(st.session_state.setdefault("experiment_engine_group_b", pd.DataFrame({"Group B": [8, 9, 10, 8, 7, 9]})), num_rows="dynamic", use_container_width=True, key="experiment_engine_b_editor")
        iterations = st.number_input("Bootstrap iterations", 500, 50000, 4000, 500, key="experiment_engine_boot_iters")
        if st.button("📊 Bootstrap difference + effect size", type="primary", use_container_width=True, key="experiment_engine_boot_run"):
            try:
                boot, boot_summary = bootstrap_difference(a.iloc[:, 0], b.iloc[:, 0], int(iterations))
                boot_summary.update(effect_size(a.iloc[:, 0], b.iloc[:, 0]))
                st.session_state["experiment_engine_bootstrap_df"] = boot
                st.session_state["experiment_engine_bootstrap_summary"] = boot_summary
                run_id = _save_experiment_evidence(
                    "Bootstrap Difference + Effect Size",
                    {"Group A": a.iloc[:, 0].dropna().tolist(), "Group B": b.iloc[:, 0].dropna().tolist()},
                    boot_summary,
                    username,
                )
                st.session_state["experiment_engine_run_id"] = run_id
                st.success("Bootstrap confidence interval and effect-size evidence calculated.")
            except Exception as exc:
                st.error(f"Bootstrap/effect-size analysis failed safely: {exc}")
        if st.session_state.get("experiment_engine_bootstrap_summary"):
            st.json(st.session_state["experiment_engine_bootstrap_summary"])
        if isinstance(st.session_state.get("experiment_engine_bootstrap_df"), pd.DataFrame):
            st.dataframe(st.session_state["experiment_engine_bootstrap_df"].head(250), use_container_width=True, hide_index=True)
            _df_download(st.session_state["experiment_engine_bootstrap_df"], "shoir_ie_bootstrap_distribution.csv")

    with tabs[3]:
        source = st.session_state.get("experiment_engine_design_df")
        if not isinstance(source, pd.DataFrame) or source.empty:
            st.info("Generate a DOE or provide a result table first.")
        else:
            numeric = [c for c in source.columns if pd.api.types.is_numeric_dtype(source[c]) and not str(c).startswith("__code__")]
            if len(numeric) >= 2:
                outcome = st.selectbox("Outcome", numeric, key="experiment_engine_sens_outcome")
                drivers = st.multiselect("Input drivers", [c for c in numeric if c != outcome], default=[c for c in numeric if c != outcome][:4], key="experiment_engine_sens_drivers")
                if st.button("🔎 Screen sensitivity", use_container_width=True, key="experiment_engine_sens_run"):
                    try:
                        sens = sensitivity_screen(source, outcome, drivers)
                        st.session_state["experiment_engine_sensitivity_df"] = sens
                        run_id = _save_experiment_evidence(
                            "Sensitivity Screening",
                            source.to_dict("records"),
                            {"sensitivity": sens.to_dict("records"), "outcome": outcome, "drivers": drivers},
                            username,
                        )
                        st.session_state["experiment_engine_run_id"] = run_id
                        st.dataframe(sens, use_container_width=True, hide_index=True)
                    except Exception as exc:
                        st.error(f"Sensitivity screening failed safely: {exc}")
            if isinstance(st.session_state.get("experiment_engine_sensitivity_df"), pd.DataFrame):
                _df_download(st.session_state["experiment_engine_sensitivity_df"], "shoir_ie_sensitivity.csv")

    with tabs[4]:
        source_options = []
        for key in ["experiment_engine_fitted_df", "experiment_engine_bootstrap_df", "experiment_engine_mc_samples"]:
            val = st.session_state.get(key)
            if isinstance(val, pd.DataFrame) and not val.empty:
                source_options.append(key)
        if not source_options:
            st.info("Run a simulation or experiment with replication identifiers to summarize.")
        else:
            key = st.selectbox("Replication evidence source", source_options, key="experiment_engine_rep_source")
            src = st.session_state[key]
            nums = [c for c in src.columns if pd.api.types.is_numeric_dtype(src[c])]
            metric = st.selectbox("Metric", nums, key="experiment_engine_rep_metric")
            rep_col = "Replication" if "Replication" in src.columns else st.selectbox("Replication column", ["(none)"] + nums, key="experiment_engine_rep_col")
            if st.button("📏 Summarize replications", use_container_width=True, key="experiment_engine_rep_run"):
                try:
                    summary_df, summary = summarize_replications(src, metric, "Replication" if rep_col == "Replication" else rep_col)
                    st.session_state["experiment_engine_replication_df"] = summary_df
                    st.session_state["experiment_engine_replication_summary"] = summary
                    st.dataframe(summary_df, use_container_width=True, hide_index=True)
                    st.json(summary)
                except Exception as exc:
                    st.error(f"Replication summary failed safely: {exc}")
            if isinstance(st.session_state.get("experiment_engine_replication_df"), pd.DataFrame):
                _df_download(st.session_state["experiment_engine_replication_df"], "shoir_ie_replication_summary.csv")


def render_forecasting_studio(tier: str, username: str) -> None:
    st.markdown("#### 📈 Universal Industrial Forecasting Studio")
    st.caption("Forecast demand, capacity, downtime, inventory, lead time, quality or energy using the same transparent time-aware engine.")
    df = st.data_editor(
        st.session_state.setdefault(
            "forecast_universal_df",
            pd.DataFrame({
                "Date": pd.date_range("2026-01-01", periods=24, freq="MS"),
                "Demand": np.maximum(100, np.linspace(500, 700, 24) + np.sin(np.arange(24)) * 60),
                "Capacity": np.repeat(650.0, 24),
                "Downtime": np.repeat(35.0, 24),
                "Inventory": np.linspace(800, 500, 24),
                "Lead Time": np.repeat(6.5, 24),
                "Quality": np.repeat(98.0, 24),
                "Energy": np.linspace(12000, 13500, 24),
                "Promotion": [0, 0, 1, 0] * 6,
            }),
        ),
        num_rows="dynamic", use_container_width=True, key="forecast_universal_editor",
    )
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    date_cols = [c for c in df.columns if str(c).lower().find("date") >= 0]
    date_col = st.selectbox("Time column", date_cols or list(df.columns), key="forecast_universal_date")
    target_col = st.selectbox("Forecast KPI", numeric or list(df.columns), key="forecast_universal_target")
    drivers = st.multiselect("Known/assumed external drivers", [c for c in numeric if c != target_col], key="forecast_universal_drivers")
    horizon = st.number_input("Forecast horizon", 1, 104, 12, key="forecast_universal_horizon")
    if st.button("🔮 Generate forecast", type="primary", use_container_width=True, key="forecast_universal_run"):
        try:
            result, metrics = forecast_series(df, date_col, target_col, drivers, int(horizon))
            st.session_state["forecast_universal_result"] = result
            st.session_state["forecast_universal_metrics"] = metrics
            st.success(f"Forecast generated for {target_col}.")
        except Exception as exc:
            st.error(f"Forecast failed safely: {exc}")
    if isinstance(st.session_state.get("forecast_universal_result"), pd.DataFrame):
        st.dataframe(st.session_state["forecast_universal_result"], use_container_width=True, hide_index=True)
        st.json(st.session_state.get("forecast_universal_metrics", {}))
        _df_download(st.session_state["forecast_universal_result"], "shoir_ie_forecast_evidence.csv")


def render_optimization_studio(tier: str, username: str) -> None:
    st.markdown("#### ⚙️ Unified Optimization Studio")
    st.caption("LP, MILP, nonlinear quadratic, multi-objective Pareto, and scenario-based robust/stochastic optimization.")
    tabs = st.tabs(["LP / MILP", "Nonlinear", "Pareto / Multi-objective", "Robust / Stochastic"])

    with tabs[0]:
        variables = st.data_editor(
            st.session_state.setdefault(
                "optimization_solver_variables",
                pd.DataFrame({
                    "Variable": ["x", "y"],
                    "Objective Coef": [4.0, 6.0],
                    "Lower": [0.0, 0.0],
                    "Upper": [100.0, 100.0],
                    "Integer": [False, False],
                    "Binary": [False, False],
                }),
            ),
            num_rows="dynamic", use_container_width=True, key="optimization_variables_editor",
        )
        constraints = st.data_editor(
            st.session_state.setdefault(
                "optimization_solver_constraints",
                pd.DataFrame({"Constraint": ["Capacity"], "Sense": ["<="], "RHS": [100.0], "x": [1.0], "y": [1.0]}),
            ),
            num_rows="dynamic", use_container_width=True, key="optimization_constraints_editor",
        )
        c1, c2 = st.columns(2)
        sense = c1.selectbox("Objective", ["min", "max"], key="optimization_objective_sense")
        method = c2.selectbox("Solver class", ["LP", "MILP"], key="optimization_method")
        if st.button("⚙️ Solve model", type="primary", use_container_width=True, key="optimization_solver_run"):
            try:
                sol, summary = solve_lp_or_milp(variables, constraints, sense, method)
                st.session_state["optimization_solution_df"] = sol
                st.session_state["optimization_solution_summary"] = summary
                st.success(f"{summary['Method']} solved successfully.")
            except Exception as exc:
                st.error(f"Optimization failed safely: {exc}")
        if isinstance(st.session_state.get("optimization_solution_df"), pd.DataFrame):
            st.dataframe(st.session_state["optimization_solution_df"], use_container_width=True, hide_index=True)
            st.json(st.session_state.get("optimization_solution_summary", {}))
            _df_download(st.session_state["optimization_solution_df"], "shoir_ie_optimization_solution.csv")

    with tabs[1]:
        nl_vars = st.data_editor(
            st.session_state.setdefault(
                "optimization_nonlinear_variables",
                pd.DataFrame({
                    "Variable": ["x", "y"],
                    "Linear Coef": [1.0, 2.0],
                    "Quadratic Coef": [0.08, 0.12],
                    "Lower": [0.0, 0.0],
                    "Upper": [100.0, 100.0],
                }),
            ),
            num_rows="dynamic", use_container_width=True, key="optimization_nl_variables_editor",
        )
        nl_cons = st.data_editor(
            st.session_state.setdefault(
                "optimization_nonlinear_constraints",
                pd.DataFrame({"Constraint": ["Minimum Output"], "Sense": [">="], "RHS": [60.0], "x": [1.0], "y": [1.0]}),
            ),
            num_rows="dynamic", use_container_width=True, key="optimization_nl_constraints_editor",
        )
        nl_sense = st.selectbox("Objective", ["min", "max"], key="optimization_nl_sense")
        if st.button("∿ Solve nonlinear model", type="primary", use_container_width=True, key="optimization_nl_run"):
            try:
                sol, summary = solve_nonlinear_quadratic(nl_vars, nl_cons, nl_sense)
                st.session_state["optimization_nonlinear_solution_df"] = sol
                st.session_state["optimization_nonlinear_summary"] = summary
                st.success("Nonlinear optimization converged.")
            except Exception as exc:
                st.error(f"Nonlinear optimization failed safely: {exc}")
        if isinstance(st.session_state.get("optimization_nonlinear_solution_df"), pd.DataFrame):
            st.dataframe(st.session_state["optimization_nonlinear_solution_df"], use_container_width=True, hide_index=True)
            st.json(st.session_state.get("optimization_nonlinear_summary", {}))

    with tabs[2]:
        candidates = st.data_editor(
            st.session_state.setdefault(
                "optimization_candidates_df",
                pd.DataFrame({
                    "Scenario": ["A", "B", "C", "D"],
                    "Cost": [100, 90, 130, 110],
                    "Carbon": [80, 120, 60, 75],
                    "Service": [94, 97, 99, 96],
                    "Risk": [12, 20, 8, 15],
                }),
            ),
            num_rows="dynamic", use_container_width=True, key="optimization_candidates_editor",
        )
        objectives = st.multiselect("Pareto objectives", [c for c in candidates.columns if c != "Scenario" and pd.api.types.is_numeric_dtype(candidates[c])],
                                    default=[c for c in ["Cost", "Carbon", "Service"] if c in candidates.columns], key="optimization_pareto_objectives")
        if objectives:
            minimize_flags = {}
            for col in objectives:
                minimize_flags[col] = st.checkbox(f"Minimize {col}", value=col not in {"Service"}, key=f"optimization_min_{col}")
            if st.button("📈 Build Pareto frontier", type="primary", use_container_width=True, key="optimization_pareto_run"):
                try:
                    pareto = pareto_candidates(candidates, minimize_flags)
                    st.session_state["optimization_pareto_df"] = pareto
                    st.success(f"Pareto frontier generated with {len(pareto)} non-dominated candidates.")
                except Exception as exc:
                    st.error(f"Pareto analysis failed safely: {exc}")
            if isinstance(st.session_state.get("optimization_pareto_df"), pd.DataFrame):
                st.dataframe(st.session_state["optimization_pareto_df"], use_container_width=True, hide_index=True)

    with tabs[3]:
        scenario = st.data_editor(
            st.session_state.setdefault(
                "optimization_scenario_states_df",
                pd.DataFrame({
                    "Decision": ["A", "A", "B", "B", "C", "C"],
                    "State": ["Base", "Shock", "Base", "Shock", "Base", "Shock"],
                    "Probability": [0.8, 0.2, 0.8, 0.2, 0.8, 0.2],
                    "Cost": [100, 140, 90, 155, 130, 170],
                    "Service": [95, 84, 97, 83, 99, 89],
                    "Risk": [10, 35, 20, 42, 8, 20],
                }),
            ),
            num_rows="dynamic", use_container_width=True, key="optimization_scenario_editor",
        )
        metric_cols = [c for c in scenario.columns if c not in {"Decision", "State", "Probability"} and pd.api.types.is_numeric_dtype(scenario[c])]
        metrics = st.multiselect("Scenario KPIs", metric_cols, default=[c for c in ["Cost", "Service", "Risk"] if c in metric_cols], key="optimization_scenario_metrics")
        if metrics and st.button("🛡️ Run robust + stochastic scenario optimization", type="primary", use_container_width=True, key="optimization_robust_run"):
            try:
                minimize_flags = {m: m not in {"Service"} for m in metrics}
                summary, scored = robust_stochastic_scenario_analysis(scenario, "Decision", "State", metrics, minimize_flags, "Probability")
                st.session_state["optimization_stochastic_summary_df"] = summary
                st.session_state["optimization_robust_scored_df"] = scored
                st.success("Expected and worst-state decision evidence generated.")
            except Exception as exc:
                st.error(f"Robust/stochastic analysis failed safely: {exc}")
        if isinstance(st.session_state.get("optimization_stochastic_summary_df"), pd.DataFrame):
            st.dataframe(st.session_state["optimization_stochastic_summary_df"], use_container_width=True, hide_index=True)
        if isinstance(st.session_state.get("optimization_robust_scored_df"), pd.DataFrame):
            st.dataframe(st.session_state["optimization_robust_scored_df"], use_container_width=True, hide_index=True)


def render_decision_center_studio(tier: str, username: str) -> None:
    st.markdown("#### 🎯 Decision Governance Studio")
    st.caption("Decision cards now capture baseline, alternatives, constraints, KPIs, uncertainty, evidence, approvals and verification.")
    title = st.text_input("Decision title", value="Engineering Decision", key="decision_governance_title")
    baseline = st.text_area("Baseline JSON", value='{"description":"Current network","Cost":100000,"Service":95}', key="decision_baseline_json")
    metrics = st.text_area("KPI / metrics JSON", value='{"Cost Delta %":-8.2,"Service Delta %":2.1,"Carbon Delta %":-4.5}', key="decision_kpi_json")
    uncertainty = st.text_area("Uncertainty JSON", value='{"P95 cost exposure":"12%","Service CI":"±1.8 pp"}', key="decision_unc_json")
    alternatives = st.data_editor(
        st.session_state.setdefault(
            "decision_alternatives_df",
            pd.DataFrame({"Alternative": ["Baseline", "Network Redesign"], "Cost": [100000, 91800], "Service": [95, 97], "Risk": [10, 12]}),
        ),
        num_rows="dynamic", use_container_width=True, key="decision_alternatives_editor",
    )
    constraints = st.data_editor(
        st.session_state.setdefault(
            "decision_constraints_df",
            pd.DataFrame({"Constraint": ["Service minimum", "Budget"], "Rule": [">= 95", "<= 100000"], "Status": ["Pass", "Pass"]}),
        ),
        num_rows="dynamic", use_container_width=True, key="decision_constraints_editor",
    )
    evidence = st.data_editor(
        st.session_state.setdefault(
            "decision_evidence_df",
            pd.DataFrame({"Source": ["Forecast run", "Optimization run"], "Reference": ["forecast_universal_result", "optimization_solution_df"], "Note": ["Time-aware validation", "Solver output"]}),
        ),
        num_rows="dynamic", use_container_width=True, key="decision_evidence_editor",
    )
    approvals = st.data_editor(
        st.session_state.setdefault(
            "decision_approvals_df",
            pd.DataFrame({"Role": ["Engineering Owner", "Manager"], "Approver": [username, ""], "Status": ["Prepared", "Pending"]}),
        ),
        num_rows="dynamic", use_container_width=True, key="decision_approvals_editor",
    )
    verification = st.data_editor(
        st.session_state.setdefault(
            "decision_verification_df",
            pd.DataFrame({"KPI": ["Service"], "Target": [95.0], "Due Date": ["2026-12-31"], "Owner": [username], "Observed": [np.nan], "Status": ["Pending"]}),
        ),
        num_rows="dynamic", use_container_width=True, key="decision_verification_editor",
    )
    status = st.selectbox("Decision status", ["Draft", "Proposed", "Under Review", "Approved", "Implemented", "Verified"], key="decision_governance_status")
    selected = st.text_input("Selected alternative", "Network Redesign", key="decision_selected_alt")
    if st.button("🎯 Save governed decision card", type="primary", use_container_width=True, key="decision_governance_save"):
        try:
            from industrial_platform import create_decision_card, save_decision_card
            card = create_decision_card(
                title,
                "Engineering Decision Center",
                json.loads(metrics),
                {"baseline": json.loads(baseline)},
                json.loads(uncertainty),
                status,
                baseline=json.loads(baseline),
                alternatives=alternatives.to_dict("records"),
                constraints=constraints.to_dict("records"),
                evidence=evidence.to_dict("records"),
                approvals=approvals.to_dict("records"),
                verification=verification.to_dict("records"),
                selected_alternative=selected,
            )
            decision_id = save_decision_card(card, username)
            card["decision_id"] = decision_id
            completeness = {
                "Baseline": bool(card.get("baseline")),
                "Alternatives": bool(card.get("alternatives")),
                "Constraints": bool(card.get("constraints")),
                "KPIs": bool(card.get("metrics")),
                "Uncertainty": bool(card.get("uncertainty")),
                "Evidence": bool(card.get("evidence")),
                "Approvals": bool(card.get("approvals")),
                "Verification": bool(card.get("verification")),
            }
            card["package_completeness_pct"] = round(100 * sum(completeness.values()) / len(completeness), 1)
            card["readiness_checks"] = completeness
            st.session_state["decision_governed_card"] = card
            st.success(f"Governed decision card saved: {decision_id}")
        except Exception as exc:
            st.error(f"Decision package is not valid JSON: {exc}")
    if isinstance(st.session_state.get("decision_governed_card"), dict):
        card = st.session_state["decision_governed_card"]
        st.metric("Decision package completeness", f"{card.get('package_completeness_pct', 0):.0f}%")
        st.dataframe(
            pd.DataFrame(
                [{"Section": k, "Complete": "✅" if v else "⚠️"} for k, v in card.get("readiness_checks", {}).items()]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.json(card)
        _json_download(st.session_state["decision_governed_card"], "shoir_ie_decision_package.json")
