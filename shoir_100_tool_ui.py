"""Localized UI integrations for selected deterministic Shoir-IE tool targets.

These renderers are inserted into existing Workbench areas; they do not add a
new primary-navigation section. Results remain session-scoped until durable
workspace storage is explicitly wired and verified.
"""
from __future__ import annotations

import io
import json
import logging
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
    st.session_state.pop(f"{tool_id}_last_result", None)
    try:
        require_tool_access(tier, tool_id, actor)
        result = action()
    except (ValueError, PermissionError) as exc:
        st.error(str(exc))
        return
    except Exception:
        # Detailed diagnostics go to server logs; never show stack traces or secrets in the UI.
        logging.exception("Shoir-IE target tool execution failed: %s", tool_id)
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


def render_operational_improvement_tools(
    st: Any, tier: str, actor: str,
) -> None:
    """Render additional scoped tools as collapsed panels in the existing Workbench."""
    from shoir_100_tool_methods import (
        a3_improvement, abc_xyz_analysis, audit_5s, inventory_policy,
        line_balance, quality_cost_analysis, root_cause_analysis,
    )
    st.divider()
    st.subheader("Operational Improvement Tools")
    st.caption("Targeted add-ons to the existing Workbench. These records/results are session-scoped; they are not claimed as durable audit records.")

    with st.expander("T024 · Production Line Balancer · Mid-Tier Pro", expanded=False):
        st.caption("Precedence-aware largest-eligible-task heuristic; compare the result with a validated industrial-engineering study.")
        task_frame = st.data_editor(pd.DataFrame([
            {"task": "A", "duration": 4.0, "predecessors": ""},
            {"task": "B", "duration": 3.0, "predecessors": "A"},
            {"task": "C", "duration": 2.0, "predecessors": "A"},
            {"task": "D", "duration": 4.0, "predecessors": "B, C"},
        ]), num_rows="dynamic", use_container_width=True, key="t024_tasks")
        cycle = st.number_input("Target cycle time", min_value=0.1, value=6.0, step=0.5, key="t024_cycle")
        if st.button("Balance tasks", key="t024_run", type="primary"):
            _run(st, tier, actor, "T024", lambda: line_balance(task_frame.to_dict("records"), cycle))
        result = st.session_state.get("T024_last_result")
        if result:
            _show_result(st, "T024", result)

    with st.expander("T028 · Root-Cause Analysis Toolkit · Starter", expanded=False):
        st.caption("Pareto ranking supports prioritization; a five-why chain is recorded as a hypothesis requiring evidence, not causal proof.")
        causes = st.data_editor(pd.DataFrame([
            {"category": "Short stops", "count": 18},
            {"category": "Material wait", "count": 11},
            {"category": "Quality rework", "count": 6},
            {"category": "Other", "count": 3},
        ]), num_rows="dynamic", use_container_width=True, key="t028_causes")
        st.markdown("**Five-why hypothesis and action**")
        why_answers = [
            st.text_input(f"Why {i}", key=f"t028_why_{i}") for i in range(1, 6)
        ]
        action = st.text_input("Countermeasure / next experiment", key="t028_action")
        owner = st.text_input("Action owner", key="t028_owner")
        due = st.date_input("Action due date", key="t028_due")
        if st.button("Analyze causes", key="t028_run", type="primary"):
            _run(st, tier, actor, "T028", lambda: root_cause_analysis(
                causes.to_dict("records"), why_answers if any(why_answers) else [],
                owner, action, due.isoformat(),
            ))
        result = st.session_state.get("T028_last_result")
        if result:
            _show_result(st, "T028", result)

    with st.expander("T029 · 5S and Workplace Audit · Starter", expanded=False):
        st.caption("Use the same documented 0–5 rubric across areas; attach evidence and an accountable action owner to gaps.")
        audit = st.data_editor(pd.DataFrame([
            {"area": "Workcell 1", "category": "Sort", "score": 3, "evidence": "", "owner": "", "action": "Remove obsolete tooling", "due_date": ""},
            {"area": "Workcell 1", "category": "Set in order", "score": 4, "evidence": "", "owner": "", "action": "", "due_date": ""},
            {"area": "Workcell 1", "category": "Shine", "score": 3, "evidence": "", "owner": "", "action": "", "due_date": ""},
            {"area": "Workcell 1", "category": "Standardize", "score": 2, "evidence": "", "owner": "", "action": "Update visual standards", "due_date": ""},
            {"area": "Workcell 1", "category": "Sustain", "score": 3, "evidence": "", "owner": "", "action": "", "due_date": ""},
        ]), num_rows="dynamic", use_container_width=True, key="t029_audit")
        if st.button("Score 5S audit", key="t029_run", type="primary"):
            _run(st, tier, actor, "T029", lambda: audit_5s(audit.to_dict("records")))
        result = st.session_state.get("T029_last_result")
        if result:
            _show_result(st, "T029", result)

    with st.expander("T030 · Kaizen and A3 Improvement Manager · Mid-Tier Pro", expanded=False):
        c1, c2 = st.columns(2)
        title = c1.text_input("A3 title", "Reduce changeover time", key="t030_title")
        metric = c2.text_input("Metric name", "Changeover time", key="t030_metric")
        problem = st.text_area("Problem statement", key="t030_problem")
        c3, c4, c5 = st.columns(3)
        unit = c3.text_input("Unit", "min", key="t030_unit")
        baseline = c4.number_input("Baseline", value=45.0, key="t030_baseline")
        target = c5.number_input("Target", value=30.0, key="t030_target")
        direction = st.selectbox("Desired direction", ["lower", "higher"], key="t030_direction")
        countermeasure = st.text_area("Countermeasure / experiment", key="t030_countermeasure")
        owner = st.text_input("Owner", key="t030_owner")
        due = st.date_input("Due date", key="t030_due")
        cost = st.number_input("Implementation cost (declared currency)", min_value=0.0, value=0.0, key="t030_cost")
        has_actual = st.checkbox("Enter an actual post-change measurement", key="t030_has_actual")
        actual = st.number_input("Actual result", value=32.0, key="t030_actual") if has_actual else None
        evidence = st.text_input("Evidence reference (required to mark outcome evidence-recorded)", key="t030_evidence")
        if st.button("Build / update A3 record", key="t030_run", type="primary"):
            _run(st, tier, actor, "T030", lambda: a3_improvement(
                title, problem, metric, unit, baseline, target, direction,
                countermeasure, owner, due.isoformat(), actual, evidence, cost,
            ))
        result = st.session_state.get("T030_last_result")
        if result:
            _show_result(st, "T030", result)
            if result.get("outcome_verified"):
                st.success("Actual value and evidence reference are recorded. A project owner must still verify the evidence quality.")

    with st.expander("T040 · Quality Cost and Defect Analyzer · Mid-Tier Pro", expanded=False):
        st.caption("Separate modeled scrap and rework costs from inspection costs. Use one period and avoid double counting.")
        currency = st.selectbox("Cost currency", ["SAR", "USD", "EUR", "GBP", "AED"], key="t040_currency")
        defects = st.data_editor(pd.DataFrame([
            {"defect_type": "Scrap", "scrap_qty": 12.0, "scrap_unit_cost": 20.0, "rework_hours": 0.0, "rework_cost_per_hour": 35.0, "inspection_cost": 100.0},
            {"defect_type": "Rework", "scrap_qty": 0.0, "scrap_unit_cost": 20.0, "rework_hours": 6.0, "rework_cost_per_hour": 35.0, "inspection_cost": 40.0},
        ]), num_rows="dynamic", use_container_width=True, key="t040_defects")
        if st.button("Calculate cost of poor quality", key="t040_run", type="primary"):
            _run(st, tier, actor, "T040", lambda: quality_cost_analysis(defects.to_dict("records"), currency))
        result = st.session_state.get("T040_last_result")
        if result:
            _show_result(st, "T040", result)

    with st.expander("T055 · Inventory Policy Optimizer · Mid-Tier Pro", expanded=False):
        st.caption("Simple EOQ and demand-only safety stock; validate service-level convention and lead-time assumptions before operational use.")
        c1, c2, c3 = st.columns(3)
        annual_demand = c1.number_input("Annual demand (units)", min_value=0.1, value=10000.0, key="t055_demand")
        order_cost = c2.number_input("Cost per order", min_value=0.1, value=25.0, key="t055_order_cost")
        holding = c3.number_input("Annual holding cost per unit", min_value=0.1, value=4.0, key="t055_holding")
        c4, c5, c6 = st.columns(3)
        mean = c4.number_input("Mean demand per lead period", min_value=0.0, value=100.0, key="t055_mean")
        std = c5.number_input("Demand standard deviation per period", min_value=0.0, value=20.0, key="t055_std")
        lead = c6.number_input("Lead time (same demand periods)", min_value=0.0, value=4.0, key="t055_lead")
        z = st.selectbox("Service Z", [1.282, 1.645, 1.96, 2.326], index=1, key="t055_z",
                         help="Approximate normal quantiles, commonly associated with 90%, 95%, 97.5%, and 99% one-sided service targets.")
        if st.button("Calculate EOQ and reorder point", key="t055_run", type="primary"):
            _run(st, tier, actor, "T055", lambda: inventory_policy(annual_demand, order_cost, holding, mean, std, lead, z))
        result = st.session_state.get("T055_last_result")
        if result:
            _show_result(st, "T055", result)

    with st.expander("T056 · ABC/XYZ Inventory Analyzer · Mid-Tier Pro", expanded=False):
        st.caption("ABC classes use the value of the selected periods; XYZ classes use demand coefficient of variation. Period totals are not annualized automatically.")
        sku = st.data_editor(pd.DataFrame([
            {"SKU": "SKU-A", "unit_cost": 5.0, "P1": 40, "P2": 42, "P3": 41, "P4": 40, "P5": 43, "P6": 42},
            {"SKU": "SKU-B", "unit_cost": 30.0, "P1": 8, "P2": 2, "P3": 12, "P4": 0, "P5": 9, "P6": 1},
            {"SKU": "SKU-C", "unit_cost": 2.0, "P1": 60, "P2": 62, "P3": 61, "P4": 59, "P5": 62, "P6": 60},
        ]), num_rows="dynamic", use_container_width=True, key="t056_inventory")
        periods = [c for c in sku.columns if str(c).startswith("P")]
        if st.button("Segment inventory", key="t056_run", type="primary"):
            _run(st, tier, actor, "T056", lambda: abc_xyz_analysis(sku, "SKU", "unit_cost", periods))
        result = st.session_state.get("T056_last_result")
        if result:
            _show_result(st, "T056", result)
