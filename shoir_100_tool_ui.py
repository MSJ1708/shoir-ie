"""Localized UI integrations for selected deterministic Shoir-IE tool targets.

These renderers are inserted into existing Workbench areas; they do not add a
new primary-navigation section. Results remain session-scoped until durable
workspace storage is explicitly wired and verified.
"""
from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd

from shoir_100_tool_methods import (
    acceptance_sampling_oc,
    cost_variance,
    generate_synthetic_industrial_data,
    join_dataframes,
    mm1_queue,
    portfolio_score,
    process_time_series,
    profile_dataframe,
    require_tool_access,
)


def _run(st: Any, tier: str, actor: str, tool_id: str, action: Any) -> None:
    try:
        require_tool_access(tier, tool_id, actor)
        result = action()
    except (ValueError, PermissionError) as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        # Keep implementation failures visible, without printing tracebacks or secrets.
        st.error(f"Tool execution failed safely ({tool_id}). Check inputs and application diagnostics.")
        return
    st.session_state[f"{tool_id}_last_result"] = result


def _csv_download(st: Any, frame: pd.DataFrame, label: str, filename: str, key: str) -> None:
    payload = frame.to_csv(index=False).encode("utf-8-sig")
    st.download_button(label, data=payload, file_name=filename, mime="text/csv", key=key)


def _show_result(st: Any, tool_id: str, result: dict[str, Any]) -> None:
    st.caption(f"Status: {result.get('status', 'RESULT')} · Method version: {result.get('method_version', 'not reported')}")
    if result.get("method"):
        st.write(result["method"])
    scalar = {
        key: value for key, value in result.items()
        if isinstance(value, (str, int, float, bool)) and key not in {"method", "status", "tool_id", "method_version"}
    }
    if scalar:
        with st.expander("Summary and diagnostics", expanded=False):
            st.json(scalar)
    for key, value in result.items():
        if isinstance(value, pd.DataFrame):
            st.markdown(f"**{key.replace('_', ' ').title()}**")
            st.dataframe(value, use_container_width=True, hide_index=True)
            safe_name = "".join(ch.lower() if ch.isalnum() else "_" for ch in key).strip("_")
            _csv_download(st, value, f"Download {key.replace('_', ' ')} CSV",
                          f"{tool_id.lower()}_{safe_name}.csv", f"{tool_id}_{safe_name}_download")
    for warning in result.get("warnings", []):
        st.warning(str(warning))
    if result.get("provenance"):
        st.caption(f"Provenance: {result['provenance']}")


def render_data_intelligence_tools(
    st: Any, tier: str, actor: str, active_dataframe: pd.DataFrame | None = None,
) -> None:
    """Render T013/T017/T018/T019/T082 under the existing Validation Center."""
    st.divider()
    st.subheader("Data Intelligence Tools")
    st.caption("These tools extend the existing data workflow. Imported and synthetic data are kept distinct; session results are not represented as durable saves.")
    frame = active_dataframe if isinstance(active_dataframe, pd.DataFrame) else st.session_state.get("workbench_df")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        frame = pd.DataFrame()

    with st.expander("T013 · Data Quality Profiler · Starter", expanded=False):
        if frame.empty:
            st.info("Add rows in the Validation Center editor or import a dataset before profiling.")
        else:
            st.caption("Read-only profile: missingness, duplicate rows, types, numeric summary and IQR flags.")
            if st.button("Profile current table", key="t013_run", type="primary"):
                _run(st, tier, actor, "T013", lambda: profile_dataframe(frame.copy(deep=True)))
            result = st.session_state.get("T013_last_result")
            if result:
                _show_result(st, "T013", result)

    with st.expander("T017 · Data Join and Merge Studio · Mid-Tier Pro", expanded=False):
        st.caption("The active Validation Center table is the left input. Upload a second CSV as a staged right table; the original active table is not changed.")
        uploaded = st.file_uploader("Right table (CSV)", type=["csv"], key="t017_right_upload")
        right = None
        if uploaded is not None:
            try:
                if uploaded.size > 20 * 1024 * 1024:
                    raise ValueError("The right table is larger than the 20 MiB interactive limit.")
                right = pd.read_csv(io.BytesIO(uploaded.getvalue()))
                if right.empty:
                    raise ValueError("The right table has no data rows.")
            except (ValueError, UnicodeDecodeError, pd.errors.ParserError) as exc:
                st.error(f"Right table could not be staged: {exc}")
        if frame.empty:
            st.info("Create or import a left table in the existing Validation Center first.")
        elif right is not None:
            c1, c2, c3 = st.columns(3)
            with c1:
                left_key = st.selectbox("Left key", [str(c) for c in frame.columns], key="t017_left_key")
            with c2:
                right_key = st.selectbox("Right key", [str(c) for c in right.columns], key="t017_right_key")
            with c3:
                join_type = st.selectbox("Join type", ["left", "inner", "outer", "right"], key="t017_how")
            cardinality = st.selectbox(
                "Expected key relationship",
                ["many_to_one", "one_to_one", "one_to_many", "many_to_many"],
                key="t017_cardinality",
                help="Many-to-many joins may multiply rows and require explicit confirmation.",
            )
            confirm = st.checkbox("I reviewed and accept many-to-many row multiplication", key="t017_confirm_m2m")
            if st.button("Validate and join tables", key="t017_run", type="primary"):
                _run(st, tier, actor, "T017", lambda: join_dataframes(
                    frame.copy(deep=True), right.copy(deep=True), [left_key], [right_key],
                    join_type, cardinality, confirm,
                ))
            result = st.session_state.get("T017_last_result")
            if result:
                _show_result(st, "T017", result)
        else:
            st.info("Upload a second CSV to preview join behavior and cardinality diagnostics.")

    with st.expander("T018 · Time-Series Data Processor · Mid-Tier Pro", expanded=False):
        if frame.empty:
            st.info("Import a table with timestamp and measurement columns first.")
        else:
            timestamp_col = st.selectbox("Timestamp column", list(frame.columns), key="t018_timestamp")
            value_options = [str(c) for c in frame.columns if c != timestamp_col]
            values = st.multiselect("Measurement columns", value_options, default=value_options[:1], key="t018_values")
            timezone = st.selectbox("Output timezone", ["UTC", "Asia/Riyadh", "Europe/London", "America/New_York"], key="t018_timezone")
            resample = st.text_input("Optional pandas resample rule (blank = preserve observations)", key="t018_resample", placeholder="e.g. 15min, 1h, 1D")
            aggregation = st.selectbox("Resampling aggregation", ["mean", "sum", "min", "max", "last", "first"], key="t018_aggregation")
            if st.button("Process time series", key="t018_run", type="primary"):
                _run(st, tier, actor, "T018", lambda: process_time_series(
                    frame.copy(deep=True), timestamp_col, values, timezone, resample.strip(), aggregation,
                ))
            result = st.session_state.get("T018_last_result")
            if result:
                _show_result(st, "T018", result)

    with st.expander("T019 · Synthetic Industrial Data Generator · Starter", expanded=False):
        st.caption("Generated rows are always marked SYNTHETIC and must not be represented as plant observations or measured savings.")
        a, b, c = st.columns(3)
        rows = a.number_input("Rows", min_value=1, max_value=10_000, value=250, step=25, key="t019_rows")
        seed = b.number_input("Reproducible seed", min_value=0, max_value=4_294_967_295, value=42, step=1, key="t019_seed")
        start = c.date_input("Start date", key="t019_start_date")
        if st.button("Generate synthetic dataset", key="t019_run", type="primary"):
            _run(st, tier, actor, "T019", lambda: generate_synthetic_industrial_data(rows, seed, start.isoformat()))
        result = st.session_state.get("T019_last_result")
        if result:
            _show_result(st, "T019", result)
            data = result.get("data")
            if isinstance(data, pd.DataFrame):
                st.warning("This is synthetic data. The active dataset is unchanged unless you explicitly confirm below.")
                accept = st.checkbox("Replace the active Validation Center dataset with this synthetic dataset", key="t019_confirm_replace")
                if st.button("Apply synthetic dataset to current session", key="t019_apply", disabled=not accept):
                    st.session_state["workbench_df"] = data.copy(deep=True)
                    st.session_state["T019_applied"] = True
                    st.success("Synthetic dataset applied to the current session only.")

    with st.expander("T082 · Industrial Costing and Variance Analyzer · Mid-Tier Pro", expanded=False):
        st.caption("Costs must share a declared currency, period, and scope. Positive actual-minus-standard variance is labeled unfavorable.")
        currency = st.selectbox("Currency", ["SAR", "USD", "EUR", "GBP", "AED", "INR", "JPY", "CNY"], key="t082_currency")
        default_costs = pd.DataFrame([
            {"component": "Material", "actual": 1200.0, "standard": 1100.0, "plan": 1150.0},
            {"component": "Labor", "actual": 700.0, "standard": 750.0, "plan": 720.0},
        ])
        costs = st.data_editor(default_costs, num_rows="dynamic", use_container_width=True, key="t082_cost_editor")
        if st.button("Reconcile costs", key="t082_run", type="primary"):
            _run(st, tier, actor, "T082", lambda: cost_variance(costs.to_dict("records"), currency))
        result = st.session_state.get("T082_last_result")
        if result:
            _show_result(st, "T082", result)


def render_acceptance_sampling_tool(st: Any, tier: str, actor: str) -> None:
    with st.expander("T034 · Acceptance Sampling Planner · Professional", expanded=False):
        st.caption("Evaluates a specified single-sample binomial operating-characteristic plan. It does not certify compliance with a sampling standard.")
        c1, c2, c3, c4 = st.columns(4)
        n = c1.number_input("Sample size (n)", min_value=1, max_value=100_000, value=80, step=1, key="t034_n")
        acceptance = c2.number_input("Acceptance number (c)", min_value=0, max_value=99_999, value=2, step=1, key="t034_c")
        aql = c3.number_input("AQL (%)", min_value=0.1, max_value=99.8, value=1.0, step=0.1, key="t034_aql")
        ltpd = c4.number_input("LTPD (%)", min_value=0.2, max_value=99.9, value=8.0, step=0.1, key="t034_ltpd")
        if st.button("Calculate operating characteristics", key="t034_run", type="primary"):
            _run(st, tier, actor, "T034", lambda: acceptance_sampling_oc(n, acceptance, aql, ltpd))
        result = st.session_state.get("T034_last_result")
        if result:
            _show_result(st, "T034", result)


def render_queueing_tool(st: Any, tier: str, actor: str) -> None:
    with st.expander("T070 · Queuing and Service-System Analyzer · Professional", expanded=False):
        st.caption("Steady-state analytical M/M/1 model only; rates must use the same time unit. This is not a discrete-event simulation.")
        c1, c2, c3 = st.columns(3)
        arrival = c1.number_input("Arrival rate (λ)", min_value=0.001, value=4.0, step=0.5, key="t070_lambda")
        service = c2.number_input("Service rate (μ)", min_value=0.001, value=5.0, step=0.5, key="t070_mu")
        unit = c3.selectbox("Common time unit", ["hour", "minute", "second", "day"], key="t070_unit")
        if st.button("Analyze M/M/1 queue", key="t070_run", type="primary"):
            _run(st, tier, actor, "T070", lambda: mm1_queue(arrival, service, unit))
        result = st.session_state.get("T070_last_result")
        if result:
            _show_result(st, "T070", result)


def render_portfolio_scoring_tool(st: Any, tier: str, actor: str) -> None:
    with st.expander("T084 · Engineering Project Portfolio Scorer · Professional", expanded=False):
        st.caption("Scores and weights are subjective decisions. Review the disclosed weighting and limited sensitivity screen before using results.")
        weights_frame = st.data_editor(
            pd.DataFrame([{"criterion": "Strategic fit", "weight": 3.0},
                          {"criterion": "Safety impact", "weight": 5.0},
                          {"criterion": "Economic value", "weight": 4.0}]),
            num_rows="dynamic", use_container_width=True, key="t084_weights",
        )
        project_frame = st.data_editor(
            pd.DataFrame([
                {"project": "Option A", "Strategic fit": 4.0, "Safety impact": 4.0, "Economic value": 3.0},
                {"project": "Option B", "Strategic fit": 3.0, "Safety impact": 5.0, "Economic value": 4.0},
            ]),
            num_rows="dynamic", use_container_width=True, key="t084_projects",
        )
        criteria = [str(x).strip() for x in weights_frame.get("criterion", pd.Series(dtype=str)).tolist()]
        weights = {str(row["criterion"]).strip(): row["weight"] for _, row in weights_frame.iterrows()
                   if str(row.get("criterion", "")).strip()}
        projects = []
        for _, row in project_frame.iterrows():
            scores = {criterion: row[criterion] for criterion in criteria if criterion in project_frame.columns}
            projects.append({"name": row.get("project", ""), "scores": scores})
        if st.button("Score and compare portfolio", key="t084_run", type="primary"):
            _run(st, tier, actor, "T084", lambda: portfolio_score(projects, weights))
        result = st.session_state.get("T084_last_result")
        if result:
            _show_result(st, "T084", result)
