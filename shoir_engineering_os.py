"""Shoir-IE Industrial Engineering Operating System integration layer.

This module is a thin orchestration layer over existing Shoir-IE authorities.
It does not replace domain calculators; it connects problem framing, resource
analysis, scenario trade-offs, verification, method discovery, personas and
the universal visualization contract into one engineering workflow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


WORKFLOW_STAGES = (
    "Observe",
    "Understand",
    "Diagnose",
    "Model",
    "Experiment",
    "Optimize",
    "Decide",
    "Execute",
    "Verify",
    "Learn",
)

INDUSTRY_PROFILES = {
    "Discrete Manufacturing": ("asset", "machine", "line", "cycle", "quality", "order", "workforce"),
    "Process Manufacturing": ("batch", "yield", "energy", "process", "quality", "material"),
    "Warehouse & Logistics": ("sku", "inventory", "order", "route", "travel", "dock", "warehouse"),
    "Healthcare Operations": ("patient", "capacity", "wait", "staff", "bed", "service"),
    "Utilities & Energy": ("asset", "load", "energy", "outage", "capacity", "emissions"),
    "Mining / Oil & Gas": ("asset", "production", "maintenance", "energy", "safety", "material"),
    "Construction": ("project", "schedule", "resource", "cost", "risk", "workforce"),
    "Service & Retail Operations": ("customer", "queue", "service", "staff", "demand", "inventory"),
    "Public Sector Operations": ("case", "service", "queue", "staff", "cost", "capacity"),
}

PERSONA_VIEWS = {
    "Operator": ("Current state", "Exceptions", "Next action", "Safety"),
    "Industrial Engineer": ("Process", "Root cause", "Method", "Scenario", "Verification"),
    "Manager": ("KPI", "Capacity", "Cost", "Risk", "Actions"),
    "Executive": ("Value", "Strategic trade-offs", "Risk", "Outcome"),
    "Researcher": ("Protocol", "Data lineage", "Model", "Uncertainty", "Reproducibility"),
}

RESOURCE_FAMILIES = {
    "People / Labor": ("labor", "labour", "operator", "staff", "workforce", "headcount", "hours worked"),
    "Machines / Capacity": ("machine", "equipment", "asset", "capacity", "utilization", "utilisation", "runtime"),
    "Materials / Inventory": ("material", "inventory", "stock", "sku", "quantity", "component", "wip"),
    "Time / Flow": ("time", "cycle", "lead", "duration", "wait", "takt", "throughput"),
    "Space": ("space", "area", "warehouse", "floor", "travel distance", "distance"),
    "Energy": ("energy", "kwh", "mwh", "power", "electric"),
    "Cost / Capital": ("cost", "price", "capex", "opex", "investment", "cash", "revenue"),
    "Carbon / Waste": ("carbon", "co2", "co2e", "emission", "waste", "scrap"),
}

METHOD_LIBRARY = [
    # Work measurement / Lean
    ("Time Study", "Work Measurement", "industrial_platform", "native"),
    ("Standard Work", "Work Measurement", "industrial_platform", "workflow"),
    ("Work Sampling", "Work Measurement", "industrial_platform", "workflow"),
    ("Learning Curve", "Work Measurement", "industrial_platform", "workflow"),
    ("Value Stream Mapping", "Process Improvement", "industrial_platform", "workflow"),
    ("SIPOC", "Process Improvement", "industrial_platform", "workflow"),
    ("Process Mapping", "Process Improvement", "industrial_platform", "workflow"),
    ("Spaghetti Diagram", "Process Improvement", "shoir_engineering_os", "workflow"),
    ("Bottleneck Analysis", "Process Improvement", "industrial_platform", "native"),
    ("Theory of Constraints", "Process Improvement", "industrial_platform", "workflow"),
    ("Kaizen / A3", "Process Improvement", "industrial_platform", "workflow"),
    ("5S", "Process Improvement", "industrial_platform", "workflow"),
    ("SMED", "Process Improvement", "industrial_platform", "workflow"),
    ("Kanban", "Process Improvement", "industrial_platform", "workflow"),
    # Operations research / optimization
    ("Linear Programming", "Operations Research", "industrial_platform", "native"),
    ("MILP", "Operations Research", "industrial_platform", "native"),
    ("Nonlinear Optimization", "Operations Research", "shoir_optimization", "linked"),
    ("Multi-objective Optimization", "Operations Research", "industrial_platform", "native"),
    ("Robust Optimization", "Operations Research", "industrial_platform", "native"),
    ("Stochastic Optimization", "Operations Research", "industrial_platform", "workflow"),
    ("Assignment", "Operations Research", "industrial_platform", "workflow"),
    ("Transportation", "Operations Research", "industrial_platform", "workflow"),
    ("Facility Location", "Operations Research", "industrial_platform", "workflow"),
    ("Vehicle Routing", "Operations Research", "industrial_platform", "workflow"),
    ("Production Scheduling", "Planning", "industrial_platform", "native"),
    ("Finite Capacity Scheduling", "Planning", "industrial_platform", "native"),
    ("Aggregate Planning", "Planning", "industrial_platform", "workflow"),
    ("MPS / MRP", "Planning", "industrial_platform", "native"),
    ("S&OP", "Planning", "shoir_engineering_os", "workflow"),
    # Statistics / experiments
    ("Descriptive Statistics", "Statistics", "industrial_platform", "native"),
    ("Confidence Intervals", "Statistics", "research_statistics", "native"),
    ("Hypothesis Testing", "Statistics", "research_statistics", "native"),
    ("ANOVA", "Statistics", "industrial_platform", "native"),
    ("Regression", "Statistics", "industrial_platform", "native"),
    ("DOE / Factorial", "Experiments", "research_experiment_engine", "native"),
    ("Response Surface Methodology", "Experiments", "shoir_experiment_engine", "linked"),
    ("Monte Carlo", "Uncertainty", "shoir_experiment_engine", "native"),
    ("Bootstrap", "Uncertainty", "shoir_experiment_engine", "native"),
    ("Sensitivity Analysis", "Uncertainty", "shoir_experiment_engine", "native"),
    ("Uncertainty Propagation", "Uncertainty", "shoir_experiment_engine", "workflow"),
    ("Effect Sizes", "Statistics", "research_statistics", "native"),
    ("Statistical Power", "Statistics", "research_statistics", "workflow"),
    # Quality / reliability
    ("SPC", "Quality", "industrial_platform", "native"),
    ("Process Capability", "Quality", "industrial_platform", "native"),
    ("Cp / Cpk / Pp / Ppk", "Quality", "industrial_platform", "native"),
    ("Gage R&R", "Quality", "industrial_platform", "native"),
    ("Acceptance Sampling", "Quality", "industrial_platform", "workflow"),
    ("Pareto Analysis", "Quality", "industrial_platform", "native"),
    ("FMEA", "Quality", "industrial_platform", "native"),
    ("8D / CAPA", "Quality", "industrial_platform", "workflow"),
    ("Weibull Analysis", "Reliability", "industrial_platform", "native"),
    ("MTBF / MTTR", "Reliability", "industrial_platform", "native"),
    ("Availability", "Reliability", "industrial_platform", "native"),
    ("Fault Tree Analysis", "Reliability", "industrial_platform", "workflow"),
    ("Event Tree Analysis", "Reliability", "industrial_platform", "workflow"),
    ("RCM", "Reliability", "industrial_platform", "workflow"),
    # Supply chain / facilities / people
    ("EOQ", "Supply Chain", "industrial_platform", "native"),
    ("Safety Stock", "Supply Chain", "industrial_platform", "native"),
    ("Reorder Point", "Supply Chain", "industrial_platform", "workflow"),
    ("ABC / XYZ", "Supply Chain", "industrial_platform", "workflow"),
    ("Inventory Optimization", "Supply Chain", "industrial_platform", "native"),
    ("Network Design", "Supply Chain", "industrial_platform", "workflow"),
    ("Systematic Layout Planning", "Facilities", "shoir_engineering_os", "workflow"),
    ("From-To Analysis", "Facilities", "shoir_engineering_os", "workflow"),
    ("Load-Distance", "Facilities", "shoir_engineering_os", "workflow"),
    ("Facility Layout", "Facilities", "industrial_platform", "workflow"),
    ("RULA / REBA", "Ergonomics", "industrial_platform", "workflow"),
    ("NIOSH Lifting", "Ergonomics", "industrial_platform", "workflow"),
    ("Anthropometrics", "Ergonomics", "industrial_platform", "workflow"),
    # Economics / sustainability / safety
    ("CPM / PERT", "Project Engineering", "industrial_platform", "workflow"),
    ("Gantt", "Project Engineering", "industrial_platform", "native"),
    ("Earned Value", "Project Engineering", "industrial_platform", "workflow"),
    ("NPV / IRR / ROI", "Engineering Economics", "industrial_platform", "native"),
    ("Life-cycle Cost", "Engineering Economics", "industrial_platform", "workflow"),
    ("Make / Buy", "Engineering Economics", "shoir_engineering_os", "workflow"),
    ("Carbon Accounting", "Sustainability", "industrial_platform", "native"),
    ("Life-cycle Assessment", "Sustainability", "industrial_platform", "native"),
    ("FMEA Risk Layer", "Safety & Risk", "industrial_platform", "native"),
    ("HAZOP", "Safety & Risk", "shoir_engineering_os", "workflow"),
    ("HAZID", "Safety & Risk", "shoir_engineering_os", "workflow"),
    ("Bowtie", "Safety & Risk", "shoir_engineering_os", "workflow"),
    ("JSA / JHA", "Safety & Risk", "shoir_engineering_os", "workflow"),
]

PROBLEM_ROUTES = {
    "throughput": ("Bottleneck Analysis", "OEE", "Line Balancing", "Simulation", "Scheduling"),
    "downtime": ("MTBF / MTTR", "Reliability", "Predictive Maintenance", "Simulation"),
    "quality": ("SPC", "Process Capability", "Pareto Analysis", "DOE", "FMEA"),
    "inventory": ("EOQ", "Safety Stock", "Reorder Point", "Inventory Optimization"),
    "demand": ("Forecasting", "S&OP", "Capacity Planning", "Simulation"),
    "capacity": ("Capacity Planning", "Line Balancing", "Scheduling", "Optimization"),
    "cost": ("Cost Analysis", "Engineering Economics", "Optimization", "Scenario Analysis"),
    "energy": ("Energy Intensity", "Carbon Accounting", "Scenario Analysis", "Optimization"),
    "safety": ("FMEA", "HAZOP", "Fault Tree Analysis", "Risk Analysis"),
    "layout": ("Systematic Layout Planning", "From-To Analysis", "Load-Distance", "Facility Layout"),
    "workforce": ("Staffing", "Work Measurement", "Ergonomics", "Scheduling"),
    "supply": ("Inventory Optimization", "Network Design", "Routing", "Robust Optimization"),
    "research": ("DOE / Factorial", "Hypothesis Testing", "Effect Sizes", "Monte Carlo"),
}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def method_library_frame() -> pd.DataFrame:
    return pd.DataFrame(METHOD_LIBRARY, columns=["Method", "Category", "Authority", "Coverage"])

def classify_industrial_problem(prompt: str, module: str = "") -> dict[str, Any]:
    text = f"{prompt} {module}".lower()
    hits: list[tuple[int, str, tuple[str, ...]]] = []
    for keyword, methods in PROBLEM_ROUTES.items():
        score = text.count(keyword)
        if score:
            hits.append((score, keyword, methods))
    hits.sort(key=lambda x: (-x[0], x[1]))
    if not hits:
        intent = "general industrial engineering"
        methods = ("Data Readiness", "Descriptive Statistics", "Scenario Analysis", "Optimization")
    else:
        intent = hits[0][1]
        methods = hits[0][2]
    method_rows = method_library_frame()
    available = method_rows[method_rows["Method"].isin(methods)]["Method"].tolist()
    return {
        "intent": intent,
        "methods": list(dict.fromkeys([*available, *methods])),
        "candidate_modules": [
            str(module),
            "Industrial Operating System",
            "Industrial Simulation Lab",
            "Engineering Decision Center",
        ],
        "workflow": list(WORKFLOW_STAGES),
        "reason": "Deterministic evidence-oriented routing from the problem language and active module; no external action is executed.",
    }

def _numeric_columns(df: pd.DataFrame) -> list[str]:
    return [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

def _matched_columns(df: pd.DataFrame, tokens: Sequence[str]) -> list[str]:
    return [
        str(c) for c in df.columns
        if any(token in str(c).lower() for token in tokens)
    ]

def resource_efficiency_analysis(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame(columns=["Resource Family", "Detected Fields", "Numeric Fields", "Observations", "Total", "Mean"]), list(RESOURCE_FAMILIES)
    rows: list[dict[str, Any]] = []
    gaps: list[str] = []
    for family, tokens in RESOURCE_FAMILIES.items():
        fields = _matched_columns(df, tokens)
        nums = [c for c in fields if c in _numeric_columns(df)]
        if not fields:
            gaps.append(family)
            rows.append({"Resource Family": family, "Detected Fields": "", "Numeric Fields": "", "Observations": 0, "Total": np.nan, "Mean": np.nan})
            continue
        numeric = pd.concat([pd.to_numeric(df[c], errors="coerce") for c in nums], ignore_index=True).dropna() if nums else pd.Series(dtype=float)
        rows.append({
            "Resource Family": family,
            "Detected Fields": ", ".join(fields),
            "Numeric Fields": ", ".join(nums),
            "Observations": int(len(numeric)),
            "Total": float(numeric.sum()) if not numeric.empty else np.nan,
            "Mean": float(numeric.mean()) if not numeric.empty else np.nan,
        })
    return pd.DataFrame(rows), gaps

def scenario_tradeoff_matrix(
    df: pd.DataFrame,
    scenario_column: str = "Scenario",
    metrics: Sequence[str] | None = None,
) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    scenario_col = scenario_column if scenario_column in df.columns else next(
        (str(c) for c in df.columns if str(c).lower() in {"scenario", "alternative", "option"}), None
    )
    if not scenario_col:
        raise KeyError("A Scenario/Alternative/Option column is required.")
    numeric = _numeric_columns(df)
    chosen = [str(c) for c in (metrics or numeric) if str(c) in numeric]
    if not chosen:
        raise ValueError("At least one numeric scenario metric is required.")
    work = df[[scenario_col, *chosen]].copy()
    for c in chosen:
        work[c] = pd.to_numeric(work[c], errors="coerce")
    grouped = work.groupby(scenario_col, dropna=False)[chosen].mean().reset_index()
    baseline = grouped.iloc[0]
    for metric in chosen:
        grouped[f"{metric} Δ"] = grouped[metric] - float(baseline[metric])
        base = float(baseline[metric])
        grouped[f"{metric} Δ %"] = np.where(base == 0, np.nan, (grouped[metric] - base) / abs(base) * 100.0)
    return grouped

def pareto_tradeoff_flags(df: pd.DataFrame, objectives: Mapping[str, bool]) -> pd.DataFrame:
    """Mark non-dominated rows; objectives values are True for minimize."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    cols = [c for c in objectives if c in df.columns]
    if not cols:
        raise ValueError("No objective columns were found.")
    work = df[cols].apply(pd.to_numeric, errors="coerce")
    valid = work.notna().all(axis=1)
    flags = pd.Series(False, index=df.index, dtype=bool)
    indices = list(df.index[valid])
    for i in indices:
        dominated = False
        for j in indices:
            if i == j:
                continue
            better_or_equal = True
            strictly_better = False
            for c in cols:
                ai, aj = float(work.loc[i, c]), float(work.loc[j, c])
                minimize = bool(objectives[c])
                if minimize:
                    if aj > ai:
                        better_or_equal = False
                        break
                    if aj < ai:
                        strictly_better = True
                else:
                    if aj < ai:
                        better_or_equal = False
                        break
                    if aj > ai:
                        strictly_better = True
            if better_or_equal and strictly_better:
                dominated = True
                break
        flags.loc[i] = not dominated
    out = df.copy(deep=True)
    out["Pareto"] = flags.to_numpy()
    return out

def verification_table(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    tolerance: float | Mapping[str, float] = 0.05,
) -> pd.DataFrame:
    keys = sorted(set(map(str, expected)) | set(map(str, actual)))
    rows: list[dict[str, Any]] = []
    for key in keys:
        try:
            exp = float(expected.get(key, np.nan))
            act = float(actual.get(key, np.nan))
        except (TypeError, ValueError):
            exp, act = np.nan, np.nan
        if not np.isfinite(exp) or not np.isfinite(act):
            rows.append({"KPI": key, "Expected": expected.get(key), "Actual": actual.get(key), "Delta": np.nan, "Relative Error %": np.nan, "Tolerance %": np.nan, "Status": "Insufficient numeric evidence"})
            continue
        delta = act - exp
        rel = abs(delta) / max(abs(exp), 1e-12) * 100.0
        tol_pct = float(tolerance.get(key, 0.05) if isinstance(tolerance, Mapping) else tolerance) * 100.0
        rows.append({"KPI": key, "Expected": exp, "Actual": act, "Delta": delta, "Relative Error %": rel, "Tolerance %": tol_pct, "Status": "Within tolerance" if rel <= tol_pct else "Outside tolerance"})
    return pd.DataFrame(rows)

def operating_system_contract(
    module: str,
    df: pd.DataFrame | None = None,
    *,
    session_state: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    state = session_state or {}
    frame = df if isinstance(df, pd.DataFrame) else pd.DataFrame()
    has_data = not frame.empty
    has_validation = bool(state.get("industrial_workbook_formula_audit_df") is not None or state.get("unified_readiness_score") is not None)
    has_analysis = isinstance(state.get("industrial_workbook_analysis_df"), pd.DataFrame) and not state.get("industrial_workbook_analysis_df").empty
    has_visual = bool(state.get("shoir_universal_postflight", {}).get("graph_available")) if isinstance(state.get("shoir_universal_postflight"), Mapping) else False
    rows = [
        ("Observe", has_data, "A real table is available in the active workspace."),
        ("Understand", has_data, "Data profile/readiness can be inspected."),
        ("Diagnose", has_analysis or has_data, "Native analysis or universal inspection is available."),
        ("Model", True, "Existing domain engines and model registry remain authorities."),
        ("Experiment", True, "Experiment Engine / Research Studio are available where entitled."),
        ("Optimize", True, "Optimization engines are available where inputs and tier permit."),
        ("Decide", bool(state.get("unified_decision_id")), "Governed Decision Center record."),
        ("Execute", False, "Execution is approval-gated and never implied by analysis."),
        ("Verify", bool(state.get("decision_outcomes") or state.get("unified_verification_df")), "Actual-vs-expected evidence."),
        ("Learn", bool(state.get("industrial_memory") or state.get("experience_memory")), "Decision memory / lessons."),
    ]
    return pd.DataFrame(
        [{"Stage": stage, "Ready": bool(ready), "Evidence": evidence, "Module": module} for stage, ready, evidence in rows]
    )

def event_contract(kind: str, module: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    allowed = {
        "data_changed", "kpi_changed", "failure_occurred", "scenario_created",
        "decision_approved", "action_executed", "result_verified",
    }
    event_kind = str(kind)
    if event_kind not in allowed:
        raise ValueError(f"Unsupported industrial event: {event_kind}")
    safe = dict(payload or {})
    return {"event": event_kind, "module": str(module), "timestamp": _now(), "payload": safe}

def render_operating_system_layer(module: str, username: str = "unknown") -> None:
    import streamlit as st
    from shoir_live_visuals import discover_visual_tables, ensure_visualization_suite

    tables = discover_visual_tables(str(module))
    frame = tables[0][2] if tables else pd.DataFrame()
    st.markdown("### Industrial Engineering Operating System")
    st.caption("One continuous engineering loop over the existing Shoir-IE engines: observe → decide → verify → learn.")
    profile = st.selectbox("Industry profile", list(INDUSTRY_PROFILES), key="ieos_profile")
    persona = st.selectbox("View", list(PERSONA_VIEWS), key="ieos_persona")
    c1, c2, c3 = st.columns(3)
    c1.metric("Methods", f"{len(METHOD_LIBRARY):,}")
    c2.metric("Resource fields", f"{len(RESOURCE_FAMILIES):,}")
    c3.metric("Current table", f"{len(frame):,} × {len(frame.columns):,}")

    tabs = st.tabs(["Problem Solver", "Resource Efficiency", "Scenario & Verify", "Method Library", "OS Contract"])

    with tabs[0]:
        prompt = st.text_area("Engineering problem / objective", placeholder="Example: throughput fell 12% and downtime increased.", key="ieos_problem")
        if prompt.strip():
            plan = classify_industrial_problem(prompt, module)
            st.write(f"**Intent:** {plan['intent']}")
            st.dataframe(pd.DataFrame({"Candidate method": plan["methods"]}), use_container_width=True, hide_index=True)
            st.info("Recommended workflow: " + " → ".join(plan["workflow"]))
            st.caption("Candidate routing only; calculation and execution remain with the selected governed engines.")
            if st.button("Record problem-solving plan", key="ieos_record_plan"):
                try:
                    from shoir_universal_engine import record_action
                    record_action("problem_solver_plan", {"module": module, "intent": plan["intent"], "methods": plan["methods"], "profile": profile, "persona": persona}, username)
                    st.success("Plan recorded in the Industrial Black Box.")
                except Exception as exc:
                    st.warning(f"Plan record unavailable: {type(exc).__name__}: {exc}")

    with tabs[1]:
        st.markdown("#### People + machines + materials + time + space + energy + cost + carbon")
        resource_df, gaps = resource_efficiency_analysis(frame)
        st.dataframe(resource_df, use_container_width=True, hide_index=True)
        if gaps:
            st.caption("Evidence gaps: " + ", ".join(gaps))
        suite = ensure_visualization_suite(resource_df, context=f"{module} · Resource efficiency", max_figures=2)
        for title, fig in suite:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.caption("Resource totals are measured only from matching numeric fields in the active table; no values are invented.")

    with tabs[2]:
        if frame.empty:
            st.info("Load or produce a scenario table first.")
        else:
            scenario_col = st.selectbox(
                "Scenario field",
                [str(c) for c in frame.columns if str(c).lower() in {"scenario", "alternative", "option"}] or list(map(str, frame.columns)),
                key="ieos_scenario_col",
            )
            metrics = [c for c in _numeric_columns(frame)]
            chosen = st.multiselect("Metrics", metrics, default=metrics[:3], key="ieos_scenario_metrics")
            if chosen:
                try:
                    comparison = scenario_tradeoff_matrix(frame, scenario_col, chosen)
                    st.dataframe(comparison, use_container_width=True, hide_index=True)
                    suite = ensure_visualization_suite(comparison, context=f"{module} · Scenario trade-offs", max_figures=2)
                    for title, fig in suite:
                        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                except Exception as exc:
                    st.warning(f"Scenario comparison unavailable: {type(exc).__name__}: {exc}")
        st.markdown("#### Expected vs actual verification")
        expected_text = st.text_area("Expected KPIs (one per line: KPI=value)", key="ieos_expected")
        actual_text = st.text_area("Actual KPIs (one per line: KPI=value)", key="ieos_actual")
        if st.button("Compare expected vs actual", key="ieos_verify"):
            def parse_lines(raw: str) -> dict[str, float]:
                out = {}
                for line in str(raw).splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        try:
                            out[k.strip()] = float(v.strip())
                        except ValueError:
                            continue
                return out
            table = verification_table(parse_lines(expected_text), parse_lines(actual_text))
            st.session_state["unified_verification_df"] = table
            st.dataframe(table, use_container_width=True, hide_index=True)
            suite = ensure_visualization_suite(table, context=f"{module} · Verification", max_figures=1)
            for title, fig in suite:
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with tabs[3]:
        search = st.text_input("Find an IE method", key="ieos_method_search")
        methods = method_library_frame()
        if search.strip():
            terms = [x for x in str(search).lower().split() if x]
            mask = methods.apply(lambda row: all(any(t in str(v).lower() for v in row) for t in terms), axis=1)
            methods = methods.loc[mask]
        st.dataframe(methods, use_container_width=True, hide_index=True)
        st.caption("Coverage distinguishes native engines from workflow adapters; no unimplemented method is presented as a completed solver.")

    with tabs[4]:
        contract = operating_system_contract(module, frame, session_state=st.session_state)
        st.dataframe(contract, use_container_width=True, hide_index=True)
        st.caption("Profile: " + profile + " · Persona: " + persona + " · Actor: " + str(username))

__all__ = [
    "WORKFLOW_STAGES",
    "INDUSTRY_PROFILES",
    "PERSONA_VIEWS",
    "RESOURCE_FAMILIES",
    "METHOD_LIBRARY",
    "method_library_frame",
    "classify_industrial_problem",
    "resource_efficiency_analysis",
    "scenario_tradeoff_matrix",
    "pareto_tradeoff_flags",
    "verification_table",
    "operating_system_contract",
    "event_contract",
    "render_operating_system_layer",
]
