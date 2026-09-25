"""Research-grade experiment utilities for Shoir-IE.

The engine is deterministic when a seed is supplied and never fabricates a
scientific conclusion. It provides design generation, factorial effects,
Monte Carlo uncertainty propagation, bootstrap confidence intervals,
replication summaries and sensitivity measures.
"""
from __future__ import annotations

import itertools
import math
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import stats


def full_factorial_design(factors: Mapping[str, Sequence[Any]]) -> pd.DataFrame:
    """Create a full factorial design from named factor levels."""
    if not factors:
        raise ValueError("At least one factor is required.")
    cleaned = {}
    for name, levels in factors.items():
        key = str(name).strip()
        vals = list(levels)
        if not key:
            raise ValueError("Factor names cannot be empty.")
        if len(vals) < 2:
            raise ValueError(f"Factor '{key}' needs at least two levels.")
        if any(v is None or (isinstance(v, float) and not np.isfinite(v)) for v in vals):
            raise ValueError(f"Factor '{key}' contains an invalid level.")
        cleaned[key] = vals
    rows = [dict(zip(cleaned.keys(), combo)) for combo in itertools.product(*cleaned.values())]
    return pd.DataFrame(rows)


def _coded_factor(series: pd.Series, levels: Sequence[Any]) -> pd.Series:
    vals = list(levels)
    if len(vals) != 2:
        raise ValueError("Factorial effect analysis currently requires two levels per factor.")
    low, high = vals
    out = pd.Series(np.nan, index=series.index, dtype=float)
    out.loc[series == low] = -1.0
    out.loc[series == high] = 1.0
    if out.isna().any():
        # Numeric/string round-trip can be the source of this mismatch.
        left = series.astype(str)
        out = np.where(left == str(low), -1.0, np.where(left == str(high), 1.0, np.nan))
        out = pd.Series(out, index=series.index, dtype=float)
    return out


def factorial_effects(
    design: pd.DataFrame,
    response: str,
    factors: Sequence[str],
    *,
    bootstrap: int = 2000,
    seed: int = 42,
    confidence: float = 0.95,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Estimate main and two-factor interaction effects for a 2-level design."""
    if not isinstance(design, pd.DataFrame) or design.empty:
        raise ValueError("A non-empty design table is required.")
    factors = [str(x) for x in factors]
    missing = [x for x in [response, *factors] if x not in design.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if len(factors) == 0:
        raise ValueError("At least one factor is required.")

    d = design[[response, *factors]].copy()
    d[response] = pd.to_numeric(d[response], errors="coerce")
    d = d.dropna(subset=[response]).copy()
    coded = {}
    levels = {}
    for f in factors:
        vals = list(pd.unique(d[f].dropna()))
        if len(vals) != 2:
            raise ValueError(f"Factor '{f}' must contain exactly two observed levels.")
        levels[f] = vals
        coded[f] = _coded_factor(d[f], vals)
    coded_df = pd.DataFrame(coded, index=d.index)
    d = d.loc[coded_df.notna().all(axis=1)].copy()
    coded_df = coded_df.loc[d.index]
    if len(d) < max(4, len(factors) + 2):
        raise ValueError("Not enough complete observations for factorial analysis.")

    terms = [("Intercept", None)]
    columns = [np.ones(len(d))]
    for f in factors:
        terms.append((f, (f,)))
        columns.append(coded_df[f].to_numpy(dtype=float))
    for a_idx, a in enumerate(factors):
        for b in factors[a_idx + 1 :]:
            terms.append((f"{a} × {b}", (a, b)))
            columns.append((coded_df[a] * coded_df[b]).to_numpy(dtype=float))

    X = np.column_stack(columns)
    y = d[response].to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ beta
    residual = y - fitted
    df_resid = max(0, len(y) - X.shape[1])
    sse = float(np.sum(residual ** 2))
    mse = sse / df_resid if df_resid > 0 else float("nan")
    try:
        cov = mse * np.linalg.pinv(X.T @ X) if df_resid > 0 else np.full((X.shape[1], X.shape[1]), np.nan)
        se_beta = np.sqrt(np.maximum(np.diag(cov), 0.0))
    except Exception:
        se_beta = np.full(len(beta), np.nan)

    rng = np.random.default_rng(seed)
    records = []
    for idx, (label, _) in enumerate(terms):
        if label == "Intercept":
            continue
        coefficient = float(beta[idx])
        effect = 2.0 * coefficient
        se = float(2.0 * se_beta[idx]) if np.isfinite(se_beta[idx]) else float("nan")
        t_stat = effect / se if np.isfinite(se) and se > 0 else float("nan")
        p_value = float(2 * stats.t.sf(abs(t_stat), df_resid)) if np.isfinite(t_stat) and df_resid > 0 else float("nan")

        if " × " not in label:
            f = label
            high = pd.to_numeric(d.loc[d[f] == levels[f][1], response], errors="coerce").dropna().to_numpy()
            low = pd.to_numeric(d.loc[d[f] == levels[f][0], response], errors="coerce").dropna().to_numpy()
            pooled_sd = math.sqrt(
                ((len(high) - 1) * np.var(high, ddof=1) + (len(low) - 1) * np.var(low, ddof=1))
                / max(1, len(high) + len(low) - 2)
            ) if len(high) > 1 and len(low) > 1 else float("nan")
            cohen_d = effect / pooled_sd if np.isfinite(pooled_sd) and pooled_sd > 0 else float("nan")
        else:
            cohen_d = float("nan")

        records.append({
            "Term": label,
            "Effect": effect,
            "Coefficient": coefficient,
            "Std Error": se,
            "t": t_stat,
            "p-value": p_value,
            "Significant @ alpha": bool(np.isfinite(p_value) and p_value < (1.0 - confidence)),
            "Effect Size (Cohen d)": cohen_d,
        })

    effects = pd.DataFrame(records)
    # Bootstrap the absolute term effect distribution from complete rows.
    if bootstrap and len(d) >= 4:
        boot_effects = {label: [] for label, _ in terms if label != "Intercept"}
        for _ in range(int(bootstrap)):
            idxs = rng.integers(0, len(d), len(d))
            xb = X[idxs]
            yb = y[idxs]
            try:
                bb, *_ = np.linalg.lstsq(xb, yb, rcond=None)
                for j, (label, _) in enumerate(terms):
                    if label != "Intercept":
                        boot_effects[label].append(float(2 * bb[j]))
            except Exception:
                continue
        alpha = max(0.0, min(0.49, (1.0 - confidence) / 2.0))
        lows, highs = [], []
        for label in effects["Term"]:
            vals = np.asarray(boot_effects.get(label, []), dtype=float)
            vals = vals[np.isfinite(vals)]
            lows.append(float(np.quantile(vals, alpha)) if len(vals) else float("nan"))
            highs.append(float(np.quantile(vals, 1.0 - alpha)) if len(vals) else float("nan"))
        effects["Bootstrap CI Low"] = lows
        effects["Bootstrap CI High"] = highs

    summary = {
        "n": int(len(d)),
        "response": response,
        "factors": factors,
        "levels": levels,
        "residual_df": int(df_resid),
        "SSE": sse,
        "RMSE": float(math.sqrt(mse)) if np.isfinite(mse) and mse >= 0 else float("nan"),
        "R2": float(1.0 - sse / max(np.sum((y - y.mean()) ** 2), 1e-12)),
        "confidence": float(confidence),
        "bootstrap_replicates": int(bootstrap),
        "seed": int(seed),
    }
    return effects, summary


def bootstrap_statistic(
    values: Sequence[float],
    *,
    statistic: str = "mean",
    replicates: int = 2000,
    seed: int = 42,
    confidence: float = 0.95,
) -> tuple[dict[str, float], pd.DataFrame]:
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    if len(x) < 3:
        raise ValueError("At least three numeric observations are required for bootstrap analysis.")
    stat_name = statistic.lower()
    if stat_name not in {"mean", "median", "std"}:
        raise ValueError("Statistic must be mean, median or std.")
    func = {"mean": np.mean, "median": np.median, "std": lambda a: np.std(a, ddof=1)}[stat_name]
    rng = np.random.default_rng(seed)
    draws = np.empty(int(replicates), dtype=float)
    for i in range(len(draws)):
        draws[i] = float(func(rng.choice(x, size=len(x), replace=True)))
    alpha = max(0.0, min(0.49, (1.0 - confidence) / 2.0))
    summary = {
        "Estimate": float(func(x)),
        "Bootstrap Mean": float(np.mean(draws)),
        "Bootstrap SD": float(np.std(draws, ddof=1)),
        "CI Low": float(np.quantile(draws, alpha)),
        "CI High": float(np.quantile(draws, 1.0 - alpha)),
        "Observations": float(len(x)),
        "Replicates": float(len(draws)),
    }
    return summary, pd.DataFrame({"Bootstrap Statistic": draws})


def bootstrap_group_effect(
    df: pd.DataFrame,
    group_col: str,
    value_col: str,
    group_a: Any,
    group_b: Any,
    *,
    replicates: int = 2000,
    seed: int = 42,
    confidence: float = 0.95,
) -> tuple[dict[str, float], pd.DataFrame]:
    if group_col not in df.columns or value_col not in df.columns:
        raise ValueError("Group and response columns are required.")
    a = pd.to_numeric(df.loc[df[group_col].astype(str) == str(group_a), value_col], errors="coerce").dropna().to_numpy()
    b = pd.to_numeric(df.loc[df[group_col].astype(str) == str(group_b), value_col], errors="coerce").dropna().to_numpy()
    if len(a) < 2 or len(b) < 2:
        raise ValueError("Each group needs at least two numeric observations.")
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(int(replicates)):
        aa = rng.choice(a, size=len(a), replace=True)
        bb = rng.choice(b, size=len(b), replace=True)
        draws.append(float(np.mean(aa) - np.mean(bb)))
    draws = np.asarray(draws)
    pooled = math.sqrt(((len(a)-1)*np.var(a,ddof=1)+(len(b)-1)*np.var(b,ddof=1))/max(1,len(a)+len(b)-2))
    observed = float(np.mean(a)-np.mean(b))
    alpha = max(0.0, min(0.49, (1.0-confidence)/2.0))
    summary = {
        "Mean A": float(np.mean(a)),
        "Mean B": float(np.mean(b)),
        "Mean Difference (A-B)": observed,
        "Cohen d": observed / pooled if pooled > 0 else float("nan"),
        "CI Low": float(np.quantile(draws, alpha)),
        "CI High": float(np.quantile(draws, 1-alpha)),
        "A n": float(len(a)),
        "B n": float(len(b)),
        "Replicates": float(len(draws)),
    }
    return summary, pd.DataFrame({"Bootstrap Effect": draws})


def monte_carlo_uncertainty(
    specs: Mapping[str, Mapping[str, Any]],
    *,
    runs: int = 10000,
    seed: int = 42,
    confidence: float = 0.95,
) -> tuple[dict[str, float], pd.DataFrame]:
    """Propagate input uncertainty through a weighted-sum KPI model.

    This is deliberately explicit: the caller supplies each distribution's
    parameters and weight, so there is no hidden formula or fabricated model.
    """
    if not specs:
        raise ValueError("At least one uncertain input is required.")
    rng = np.random.default_rng(seed)
    draws: dict[str, np.ndarray] = {}
    for name, spec in specs.items():
        mean = float(spec.get("mean", 0.0))
        std = max(0.0, float(spec.get("std", 0.0)))
        weight = float(spec.get("weight", 1.0))
        dist = str(spec.get("distribution", "Normal")).lower()
        if dist == "normal":
            sample = rng.normal(mean, std, int(runs))
        elif dist == "lognormal":
            if mean <= 0 or std <= 0:
                sample = np.full(int(runs), max(mean, 0.0))
            else:
                sigma2 = math.log(1.0 + (std*std)/(mean*mean))
                sigma = math.sqrt(max(sigma2, 0.0))
                mu = math.log(mean) - sigma2/2
                sample = rng.lognormal(mu, sigma, int(runs))
        elif dist == "uniform":
            half = std * math.sqrt(3.0)
            sample = rng.uniform(mean-half, mean+half, int(runs))
        elif dist == "triangular":
            lo = float(spec.get("min", mean-std))
            hi = float(spec.get("max", mean+std))
            mode = float(spec.get("mode", mean))
            sample = rng.triangular(lo, mode, hi, int(runs))
        else:
            raise ValueError(f"Unsupported distribution: {dist}")
        draws[name] = sample
    out = pd.DataFrame(draws)
    weights = {name: float(spec.get("weight", 1.0)) for name, spec in specs.items()}
    out["Propagated KPI"] = sum(out[name] * weights[name] for name in out.columns if name in weights)
    alpha = max(0.0, min(0.49, (1.0-confidence)/2.0))
    q = out["Propagated KPI"].quantile([alpha, 0.5, 1-alpha])
    summary = {
        "Mean": float(out["Propagated KPI"].mean()),
        "Std": float(out["Propagated KPI"].std(ddof=1)),
        "P_low": float(q.iloc[0]),
        "P50": float(q.iloc[1]),
        "P_high": float(q.iloc[2]),
        "Runs": float(len(out)),
        "Confidence": float(confidence),
    }
    return summary, out


def replication_summary(
    df: pd.DataFrame,
    response_col: str,
    *,
    scenario_col: str | None = None,
    replication_col: str | None = None,
    confidence: float = 0.95,
) -> pd.DataFrame:
    if response_col not in df.columns:
        raise ValueError(f"Response column '{response_col}' not found.")
    d = df.copy()
    d[response_col] = pd.to_numeric(d[response_col], errors="coerce")
    d = d.dropna(subset=[response_col])
    group_cols = [c for c in [scenario_col] if c and c in d.columns]
    if replication_col and replication_col in d.columns and replication_col not in group_cols:
        group_cols.append(replication_col)
    grouped = d.groupby(group_cols, dropna=False)[response_col] if group_cols else [((), d[response_col])]
    rows = []
    alpha = max(0.0, min(0.49, (1.0-confidence)/2.0))
    if group_cols:
        iterator = grouped
    else:
        iterator = [((), d)]
    for keys, part in iterator:
        if group_cols:
            part_values = pd.to_numeric(part[response_col], errors="coerce").dropna()
            labels = keys if isinstance(keys, tuple) else (keys,)
            row = {col: val for col, val in zip(group_cols, labels)}
        else:
            part_values = part[response_col]
            row = {}
        n = len(part_values)
        mean = float(part_values.mean()) if n else float("nan")
        sd = float(part_values.std(ddof=1)) if n > 1 else float("nan")
        margin = float(stats.t.ppf(1-alpha, max(1,n-1)) * sd / math.sqrt(n)) if n > 1 else float("nan")
        row.update({"n": n, "Mean": mean, "Std": sd, "CI Low": mean-margin if np.isfinite(margin) else float("nan"), "CI High": mean+margin if np.isfinite(margin) else float("nan")})
        rows.append(row)
    return pd.DataFrame(rows)


def sensitivity_table(df: pd.DataFrame, outcome: str, inputs: Sequence[str]) -> pd.DataFrame:
    if outcome not in df.columns:
        raise ValueError(f"Outcome column '{outcome}' not found.")
    rows = []
    y = pd.to_numeric(df[outcome], errors="coerce")
    for col in inputs:
        if col not in df.columns or col == outcome:
            continue
        x = pd.to_numeric(df[col], errors="coerce")
        pair = pd.DataFrame({"x": x, "y": y}).dropna()
        if len(pair) < 3:
            continue
        pearson = float(pair["x"].corr(pair["y"], method="pearson"))
        spearman = float(pair["x"].corr(pair["y"], method="spearman"))
        rows.append({"Driver": col, "Pearson": pearson, "Spearman": spearman, "Sensitivity": abs(spearman), "Direction": np.sign(spearman)})
    return pd.DataFrame(rows).sort_values("Sensitivity", ascending=False).reset_index(drop=True) if rows else pd.DataFrame(columns=["Driver","Pearson","Spearman","Sensitivity","Direction"])


def render_experiment_engine(module: str, username: str, protocol: Mapping[str, Any] | None = None) -> None:
    """Interactive Experiment Engine embedded in the Research Workspace."""
    import streamlit as st
    import plotly.express as px

    st.markdown("### 🧪 Experiment Engine")
    st.caption("DOE, factorial effects, Monte Carlo uncertainty propagation, bootstrap confidence intervals, sensitivity and replication diagnostics share one reproducible workspace.")
    if protocol:
        st.info(f"Protocol: **{protocol.get('title','Untitled')}** · α={float(protocol.get('alpha',0.05)):.3f} · seed={int(protocol.get('random_seed',42))}")
    st.markdown("All generated designs and analyses are evidence artifacts. The engine does not infer a scientific conclusion for you.")

    tabs = st.tabs(["🧬 DOE / Factorial", "🎲 Monte Carlo", "🔁 Bootstrap / Effect", "📈 Replications / Sensitivity"])

    with tabs[0]:
        defaults = st.session_state.get("experiment_factor_config", pd.DataFrame({
            "Factor":["Evidence Quality","Shock Severity","Uncertainty"],
            "Low":[50,0,0],
            "High":[100,3,20],
        }))
        factors_df = st.data_editor(defaults, num_rows="dynamic", use_container_width=True, key="experiment_factor_editor")
        c1,c2,c3 = st.columns(3)
        with c1:
            response_col = st.selectbox("Response column (after measurements)", ["(none)"] + [str(c) for c in st.session_state.get("experiment_df", pd.DataFrame()).columns], key="experiment_doe_response")
        with c2:
            boot = st.number_input("Effect bootstrap", 200, 10000, 2000, 200, key="experiment_doe_boot")
        with c3:
            seed = st.number_input("DOE seed", 0, 2147483647, int((protocol or {}).get("random_seed",42)), 1, key="experiment_doe_seed")

        if st.button("🧬 Generate Full Factorial Design", type="primary", use_container_width=True, key="experiment_generate_factorial"):
            try:
                factors = {}
                for row in factors_df.to_dict("records"):
                    name = str(row.get("Factor","")).strip()
                    if not name:
                        continue
                    factors[name] = [row.get("Low"), row.get("High")]
                design = full_factorial_design(factors)
                design["Response"] = np.nan
                st.session_state["experiment_doe_design"] = design
                st.success(f"Generated {len(design):,} factorial runs ({len(factors)} factors × 2 levels).")
            except Exception as exc:
                st.error(f"DOE generation failed safely: {exc}")

        if "experiment_doe_design" in st.session_state:
            st.markdown("#### Editable run sheet")
            design = st.data_editor(st.session_state["experiment_doe_design"], num_rows="dynamic", use_container_width=True, key="experiment_doe_results_editor")
            st.session_state["experiment_doe_design"] = design.copy(deep=True)
            if response_col != "(none)" and response_col in st.session_state.get("experiment_df", pd.DataFrame()).columns:
                st.caption("The selected response column is reference data only; the generated DOE run sheet remains editable so you can paste measured results.")
            if st.button("📐 Analyze Factor Effects", use_container_width=True, key="experiment_factorial_analyze"):
                try:
                    effects, summary = factorial_effects(design, "Response" if "Response" in design.columns else response_col, [c for c in factors_df["Factor"].astype(str).tolist() if c in design.columns], bootstrap=int(boot), seed=int(seed), confidence=float((protocol or {}).get("confidence_level",0.95)))
                    st.session_state["experiment_factorial_effects"] = effects
                    st.session_state["experiment_factorial_summary"] = summary
                except Exception as exc:
                    st.error(f"Factorial analysis failed safely: {exc}")
            if "experiment_factorial_effects" in st.session_state:
                eff = st.session_state["experiment_factorial_effects"]
                st.dataframe(eff, use_container_width=True, hide_index=True)
                fig = px.bar(eff.sort_values("Effect"), x="Effect", y="Term", orientation="h", error_x=None, title="Factorial Effects")
                st.plotly_chart(fig, use_container_width=True)
                st.json(st.session_state.get("experiment_factorial_summary", {}))

    with tabs[1]:
        source = st.session_state.get("experiment_df", pd.DataFrame())
        nums = [str(c) for c in source.columns if pd.api.types.is_numeric_dtype(source[c])]
        if not nums:
            st.info("Load numeric experiment or workspace data first.")
        else:
            chosen = st.multiselect("Uncertain inputs", nums, default=nums[:min(4,len(nums))], key="experiment_mc_inputs")
            specs_rows=[]
            for c in chosen:
                s = pd.to_numeric(source[c], errors="coerce").dropna()
                mean = float(s.mean()) if not s.empty else 0.0
                std = float(s.std(ddof=1)) if len(s) > 1 else 0.0
                specs_rows.append({"Input":c,"Mean":mean,"Std":std,"Weight":1.0,"Distribution":"Normal"})
            specs_df=st.data_editor(pd.DataFrame(specs_rows),num_rows="dynamic",use_container_width=True,key="experiment_mc_specs")
            mc1,mc2,mc3=st.columns(3)
            with mc1: runs_n=st.number_input("Simulation runs",500,200000,10000,500,key="experiment_mc_runs")
            with mc2: mc_seed=st.number_input("MC seed",0,2147483647,int((protocol or {}).get("random_seed",42)),1,key="experiment_mc_seed")
            with mc3: confidence=st.number_input("Confidence",0.80,0.999,float((protocol or {}).get("confidence_level",0.95)),0.01,key="experiment_mc_conf")
            if st.button("🎲 Propagate Uncertainty",type="primary",use_container_width=True,key="experiment_mc_run"):
                try:
                    specs={str(r["Input"]):{"mean":float(r["Mean"]),"std":float(r["Std"]),"weight":float(r["Weight"]),"distribution":str(r["Distribution"]),"min":float(r["Mean"])-float(r["Std"]),"max":float(r["Mean"])+float(r["Std"]),"mode":float(r["Mean"])} for r in specs_df.to_dict("records") if str(r["Input"]).strip()}
                    summary, draws=monte_carlo_uncertainty(specs,runs=int(runs_n),seed=int(mc_seed),confidence=float(confidence))
                    st.session_state["experiment_mc_result_summary"]=summary
                    st.session_state["experiment_mc_results"]=draws
                    st.success(f"Completed {len(draws):,} uncertainty simulations.")
                except Exception as exc: st.error(f"Monte Carlo failed safely: {exc}")
            if "experiment_mc_result_summary" in st.session_state:
                st.metric("Mean propagated KPI",f'{st.session_state["experiment_mc_result_summary"]["Mean"]:,.4g}')
                st.dataframe(pd.DataFrame([st.session_state["experiment_mc_result_summary"]]),use_container_width=True,hide_index=True)
                st.plotly_chart(px.histogram(st.session_state["experiment_mc_results"],x="Propagated KPI",nbins=50,title="Monte Carlo Propagated KPI Distribution"),use_container_width=True)

    with tabs[2]:
        source = st.session_state.get("experiment_df", pd.DataFrame())
        nums = [str(c) for c in source.columns if pd.api.types.is_numeric_dtype(source[c])]
        if not nums:
            st.info("Load experiment data first.")
        else:
            metric = st.selectbox("Metric", nums, key="experiment_boot_metric")
            group_cols=[str(c) for c in source.columns if not pd.api.types.is_numeric_dtype(source[c])]
            group_col=st.selectbox("Optional group / treatment", ["(none)"]+group_cols,key="experiment_boot_groupcol")
            conf=st.number_input("Bootstrap confidence",0.80,0.999,float((protocol or {}).get("confidence_level",0.95)),0.01,key="experiment_boot_conf")
            reps=st.number_input("Bootstrap replicates",200,20000,2000,200,key="experiment_boot_reps")
            boot_seed=st.number_input("Bootstrap seed",0,2147483647,int((protocol or {}).get("random_seed",42)),1,key="experiment_boot_seed")
            if group_col!="(none)":
                values=[str(x) for x in source[group_col].dropna().unique()]
                if len(values)>=2:
                    a,b=values[0],values[1]
                    st.caption(f"Comparing first two observed groups: {a} vs {b}")
                    if st.button("🔁 Bootstrap Group Effect",type="primary",use_container_width=True,key="experiment_boot_group_run"):
                        try:
                            summ,dist=bootstrap_group_effect(source,group_col,metric,a,b,replicates=int(reps),seed=int(boot_seed),confidence=float(conf))
                            st.session_state["experiment_bootstrap_summary"]=summ; st.session_state["experiment_bootstrap_results"]=dist
                        except Exception as exc: st.error(f"Bootstrap group effect failed safely: {exc}")
            if st.button("🔁 Bootstrap Single-Metric CI",use_container_width=True,key="experiment_boot_single_run"):
                try:
                    summ,dist=bootstrap_statistic(source[metric],statistic="mean",replicates=int(reps),seed=int(boot_seed),confidence=float(conf))
                    st.session_state["experiment_bootstrap_summary"]=summ; st.session_state["experiment_bootstrap_results"]=dist
                except Exception as exc: st.error(f"Bootstrap failed safely: {exc}")
            if "experiment_bootstrap_summary" in st.session_state:
                st.dataframe(pd.DataFrame([st.session_state["experiment_bootstrap_summary"]]),use_container_width=True,hide_index=True)
                st.plotly_chart(px.histogram(st.session_state["experiment_bootstrap_results"],x=st.session_state["experiment_bootstrap_results"].columns[0],nbins=50,title="Bootstrap Distribution"),use_container_width=True)

    with tabs[3]:
        source = st.session_state.get("experiment_df", pd.DataFrame())
        if source.empty:
            st.info("Load experiment data first.")
        else:
            nums=[str(c) for c in source.columns if pd.api.types.is_numeric_dtype(source[c])]
            cats=[str(c) for c in source.columns if not pd.api.types.is_numeric_dtype(source[c])]
            resp=st.selectbox("Response",nums,key="experiment_rep_response")
            scen=st.selectbox("Scenario / group",["(none)"]+cats,key="experiment_rep_scenario")
            repl=st.selectbox("Replication ID (optional)",["(none)"]+cats,key="experiment_replication_id")
            if st.button("📊 Summarize Replications",use_container_width=True,key="experiment_rep_summary"):
                try:
                    st.session_state["experiment_replication_summary"]=replication_summary(source,resp,scenario_col=None if scen=="(none)" else scen,replication_col=None if repl=="(none)" else repl,confidence=float((protocol or {}).get("confidence_level",0.95)))
                except Exception as exc: st.error(f"Replication summary failed safely: {exc}")
            if "experiment_replication_summary" in st.session_state:
                st.dataframe(st.session_state["experiment_replication_summary"],use_container_width=True,hide_index=True)
            inputs=[c for c in nums if c!=resp]
            selected_inputs=st.multiselect("Sensitivity drivers",inputs,default=inputs[:min(5,len(inputs))],key="experiment_sensitivity_inputs")
            if st.button("🌪️ Compute Sensitivity",use_container_width=True,key="experiment_sensitivity_run"):
                try: st.session_state["experiment_sensitivity_results"]=sensitivity_table(source,resp,selected_inputs)
                except Exception as exc: st.error(f"Sensitivity analysis failed safely: {exc}")
            if "experiment_sensitivity_results" in st.session_state:
                sens=st.session_state["experiment_sensitivity_results"]; st.dataframe(sens,use_container_width=True,hide_index=True)
                if not sens.empty: st.plotly_chart(px.bar(sens.sort_values("Sensitivity"),x="Sensitivity",y="Driver",orientation="h",hover_data=["Direction"],title="Sensitivity Strength"),use_container_width=True)
