"""Research-quality utilities for Shoir-IE.

Deterministic, local research helpers used by the Research Pack QA surface and
specialist modules. They explicitly distinguish computed evidence from demo data.
"""
from __future__ import annotations

import ast
import hashlib
import json
import platform
import sys
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures


@dataclass
class ResearchRun:
    run_id: str
    started_at: str
    duration_ms: float
    seed: int


def _finite_series(values: Iterable[Any]) -> np.ndarray:
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        raise ValueError("At least two finite numeric observations are required.")
    return arr


def hypothesis_test(
    df: pd.DataFrame,
    test: str,
    alpha: float = 0.05,
    value_col: str | None = None,
    group_col: str | None = None,
    group_a: str | None = None,
    group_b: str | None = None,
    expected: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Run a real scipy test and return structured statistics."""
    if not 0 < float(alpha) < 1:
        raise ValueError("alpha must be between 0 and 1.")
    name = str(test).strip().lower()
    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError("A non-empty DataFrame is required.")

    if name in {"one-sample t-test", "one sample t-test", "ttest_1samp"}:
        if value_col is None:
            raise ValueError("value_col is required.")
        sample = _finite_series(df[value_col])
        target = float(expected[0]) if expected else 0.0
        result = stats.ttest_1samp(sample, popmean=target)
        dof = sample.size - 1
        effect = float((sample.mean() - target) / sample.std(ddof=1)) if sample.std(ddof=1) else 0.0
    elif name in {"independent two-sample t-test", "two-sample t-test", "ttest_ind"}:
        if value_col is None or group_col is None or group_a is None or group_b is None:
            raise ValueError("value_col, group_col, group_a and group_b are required.")
        a = _finite_series(df.loc[df[group_col].astype(str) == str(group_a), value_col])
        b = _finite_series(df.loc[df[group_col].astype(str) == str(group_b), value_col])
        result = stats.ttest_ind(a, b, equal_var=False)
        dof = max(1, int(a.size + b.size - 2))
        pooled = np.sqrt(((a.size - 1) * a.var(ddof=1) + (b.size - 1) * b.var(ddof=1)) / dof)
        effect = float((a.mean() - b.mean()) / pooled) if pooled else 0.0
    elif name in {"mann-whitney u", "mann-whitney", "mannwhitneyu"}:
        if value_col is None or group_col is None or group_a is None or group_b is None:
            raise ValueError("value_col, group_col, group_a and group_b are required.")
        a = _finite_series(df.loc[df[group_col].astype(str) == str(group_a), value_col])
        b = _finite_series(df.loc[df[group_col].astype(str) == str(group_b), value_col])
        result = stats.mannwhitneyu(a, b, alternative="two-sided")
        dof = None
        effect = float(1 - (2 * result.statistic) / (a.size * b.size)) if a.size and b.size else 0.0
    elif name in {"one-way anova", "anova", "f_oneway"}:
        if value_col is None or group_col is None:
            raise ValueError("value_col and group_col are required.")
        groups = [_finite_series(g[value_col]) for _, g in df.groupby(group_col)]
        if len(groups) < 2:
            raise ValueError("ANOVA requires at least two groups.")
        result = stats.f_oneway(*groups)
        dof = len(groups) - 1
        effect = float(result.statistic)
    elif name in {"chi-square", "chi square", "chi2"}:
        if expected is None:
            raise ValueError("expected counts are required for chi-square.")
        observed = _finite_series(df[value_col]) if value_col else np.array([], dtype=float)
        if observed.size != len(expected):
            raise ValueError("Observed and expected counts must have the same length.")
        result = stats.chisquare(observed, f_exp=np.asarray(expected, dtype=float))
        dof = int(observed.size - 1)
        effect = float(result.statistic)
    else:
        raise ValueError(f"Unsupported test: {test}")

    p = float(result.pvalue)
    return {
        "test": str(test),
        "statistic": float(result.statistic),
        "p_value": p,
        "alpha": float(alpha),
        "degrees_of_freedom": dof,
        "significant_at_alpha": bool(p < alpha),
        "effect_metric": effect,
        "n": int(sum(len(x) for x in locals().values() if isinstance(x, np.ndarray))) if name in {"anova"} else None,
        "evidence_status": "Computed from supplied data",
    }


def regression_analysis(
    df: pd.DataFrame,
    target: str,
    features: Sequence[str],
    polynomial_degree: int = 1,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    if target not in df.columns or not features:
        raise ValueError("Target and at least one feature are required.")
    cols = [target, *features]
    clean = df[cols].apply(pd.to_numeric, errors="coerce").dropna()
    if len(clean) < max(4, len(features) + 2):
        raise ValueError("Not enough complete numeric observations for regression.")
    X = clean[list(features)].to_numpy(dtype=float)
    y = clean[target].to_numpy(dtype=float)
    if polynomial_degree > 1:
        model = make_pipeline(PolynomialFeatures(degree=polynomial_degree, include_bias=False), LinearRegression())
    else:
        model = LinearRegression()
    model.fit(X, y)
    pred = model.predict(X)
    coefs = model[-1].coef_ if hasattr(model, "__getitem__") else model.coef_
    if np.ndim(coefs) > 1:
        coefs = np.ravel(coefs)
    coef_df = pd.DataFrame({"Feature": list(features), "Coefficient": np.asarray(coefs, dtype=float)})
    residuals = pd.DataFrame({"Observed": y, "Predicted": pred, "Residual": y - pred})
    metrics = {
        "R2": float(r2_score(y, pred)),
        "MAE": float(mean_absolute_error(y, pred)),
        "RMSE": float(np.sqrt(mean_squared_error(y, pred))),
        "n": int(len(clean)),
        "polynomial_degree": int(polynomial_degree),
        "evidence_status": "Computed from supplied data",
    }
    return coef_df, metrics, residuals


def bootstrap_mean_ci(values: Iterable[Any], confidence: float = 0.95, resamples: int = 3000, seed: int = 2026) -> dict[str, float]:
    x = _finite_series(values)
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1.")
    if resamples < 100:
        raise ValueError("Use at least 100 bootstrap resamples.")
    rng = np.random.default_rng(int(seed))
    means = np.empty(int(resamples), dtype=float)
    for i in range(int(resamples)):
        means[i] = rng.choice(x, size=x.size, replace=True).mean()
    alpha = 1.0 - confidence
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return {"mean": float(x.mean()), "lower": float(lo), "upper": float(hi), "confidence": float(confidence), "resamples": int(resamples), "seed": int(seed)}


def fit_surrogate(
    X: pd.DataFrame,
    y: Sequence[float],
    seed: int = 2026,
    model_kind: str = "Random Forest",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    x = X.apply(pd.to_numeric, errors="coerce").dropna()
    y_arr = pd.to_numeric(pd.Series(y), errors="coerce")
    aligned = x.index.intersection(y_arr.index)
    x = x.loc[aligned]
    yv = y_arr.loc[aligned].to_numpy(dtype=float)
    mask = np.isfinite(yv)
    x = x.loc[mask]
    yv = yv[mask]
    if len(x) < 8:
        raise ValueError("At least eight complete observations are required for a surrogate fit.")
    split = max(4, int(round(len(x) * 0.8)))
    rng = np.random.default_rng(int(seed))
    idx = rng.permutation(len(x))
    train_idx, test_idx = idx[:split], idx[split:]
    if len(test_idx) < 2:
        test_idx = idx[-2:]
        train_idx = idx[:-2]
    if model_kind.lower().startswith("gaussian"):
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import Matern, WhiteKernel
        model = GaussianProcessRegressor(kernel=Matern(nu=2.5) + WhiteKernel(noise_level=1.0), random_state=int(seed), normalize_y=True)
    else:
        model = RandomForestRegressor(n_estimators=250, max_depth=10, random_state=int(seed), n_jobs=1)
    model.fit(x.iloc[train_idx], yv[train_idx])
    pred = model.predict(x.iloc[test_idx])
    metrics = {
        "R2_test": float(r2_score(yv[test_idx], pred)) if len(test_idx) >= 2 else float("nan"),
        "MAE_test": float(mean_absolute_error(yv[test_idx], pred)),
        "RMSE_test": float(np.sqrt(mean_squared_error(yv[test_idx], pred))),
        "train_rows": int(len(train_idx)),
        "test_rows": int(len(test_idx)),
        "seed": int(seed),
        "model": model_kind,
        "evidence_status": "Computed hold-out validation",
    }
    return pd.DataFrame({"Observed": yv[test_idx], "Predicted": pred, "Residual": yv[test_idx] - pred}), metrics


def audit_code(code: str) -> dict[str, Any]:
    """Static safety audit; never executes supplied code."""
    findings: list[dict[str, str]] = []
    try:
        tree = ast.parse(str(code))
    except SyntaxError as exc:
        return {"valid_syntax": False, "findings": [{"severity": "ERROR", "message": f"Syntax error: {exc}"}], "execution": "Never executed"}

    forbidden_imports = {"os", "subprocess", "socket", "shutil", "pathlib", "requests"}
    forbidden_calls = {"eval", "exec", "compile", "__import__", "open"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in forbidden_imports:
                    findings.append({"severity": "HIGH", "message": f"Restricted import: {alias.name}"})
        elif isinstance(node, ast.ImportFrom):
            root = str(node.module or "").split(".")[0]
            if root in forbidden_imports:
                findings.append({"severity": "HIGH", "message": f"Restricted import: {node.module}"})
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
            findings.append({"severity": "HIGH", "message": f"Restricted call: {node.func.id}()"})
    return {
        "valid_syntax": True,
        "findings": findings,
        "safe_for_static_review": not any(f["severity"] == "HIGH" for f in findings),
        "execution": "Never executed",
    }


def reproducibility_manifest(payload: Mapping[str, Any], seed: int = 2026) -> dict[str, Any]:
    canonical = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "algorithm": "SHA-256",
        "input_hash": digest,
        "seed": int(seed),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }


def verify_manifest(payload: Mapping[str, Any], manifest: Mapping[str, Any]) -> bool:
    expected = reproducibility_manifest(payload, int(manifest.get("seed", 2026)))
    return expected["input_hash"] == manifest.get("input_hash")


def shock_matrix(
    baseline: Mapping[str, float],
    shocks: Sequence[Mapping[str, float]],
    seed: int = 2026,
    noise_pct: float = 0.0,
    replications: int = 250,
) -> pd.DataFrame:
    rng = np.random.default_rng(int(seed))
    rows = []
    for case_id, shock in enumerate(shocks, start=1):
        vals = {k: float(v) for k, v in baseline.items()}
        vals.update({k: float(vals.get(k, 0.0) * (1.0 + float(delta))) for k, delta in shock.items()})
        for rep in range(int(replications)):
            row = {"Scenario": f"Shock-{case_id}", "Replication": rep + 1, **vals}
            if noise_pct:
                for key, value in vals.items():
                    row[key] = float(value * (1.0 + rng.normal(0, float(noise_pct) / 100.0)))
            rows.append(row)
    return pd.DataFrame(rows)


def peer_review_diagnostics(text: str, sample_size: int | None = None) -> pd.DataFrame:
    raw = str(text or "")
    checks = [
        ("Methods", bool("method" in raw.lower() or "methodology" in raw.lower()), "Describe the method and data-generating process."),
        ("Sample size", bool(sample_size is not None or "n=" in raw.lower() or "sample size" in raw.lower()), "State the analyzed sample size."),
        ("Uncertainty", any(token in raw.lower() for token in ("confidence interval", "ci", "uncertainty")), "Report uncertainty intervals where appropriate."),
        ("Effect size", any(token in raw.lower() for token in ("effect size", "cohen", "odds ratio")), "Report an interpretable effect-size measure."),
        ("Limitations", "limitation" in raw.lower(), "Include limitations and boundary conditions."),
        ("Reproducibility", any(token in raw.lower() for token in ("seed", "version", "reproducib")), "Document seeds, versions and data lineage."),
        ("Causal language", not any(token in raw.lower() for token in ("causes", "proves", "guarantees")), "Avoid unsupported causal or guarantee language."),
    ]
    return pd.DataFrame([{"Check": name, "Status": "PASS" if ok else "REVIEW", "Guidance": guidance} for name, ok, guidance in checks])


def run_timer() -> tuple[ResearchRun, callable]:
    started = time.perf_counter_ns()
    run_id = "RQA-" + hashlib.sha1(f"{started}-{time.time_ns()}".encode()).hexdigest()[:10].upper()
    started_at = pd.Timestamp.utcnow().isoformat()
    seed = 2026
    def finish() -> ResearchRun:
        return ResearchRun(run_id, started_at, (time.perf_counter_ns() - started) / 1_000_000.0, seed)
    return finish(), finish
