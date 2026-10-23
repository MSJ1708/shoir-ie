"""Grouped target-tool library for Shoir-IE.

This registry is deliberately distinct from the legacy module catalog: an entry
is a target specification, not proof that its specialist engine is complete.
Related module routes are navigation aids only and must not be interpreted as
verified one-to-one implementations.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

import streamlit as st

from shoir_tier_capabilities import TIER_ORDER, module_required_tier, tier_allows

TARGET_TOOL_ROWS = r"""T001|Personalized Engineering Home|Core workspace and productivity|Starter|FOUNDATION_ONLY||Show useful projects, recent tools, saved studies, and role-appropriate next actions; empty state works for new accounts.
T002|Guided Study Wizard|Core workspace and productivity|Starter|FOUNDATION_ONLY|AI Copilot|Turn a selected problem into an explainable sequence of valid steps and ask for missing inputs; never fabricate analysis results.
T003|Universal Search and Command Center|Core workspace and productivity|Starter|FOUNDATION_ONLY|AI Copilot|Search canonical tools, aliases, projects, datasets, studies, reports, and permitted actions; results respect user and tier permissions.
T004|Engineering Project Manager|Core workspace and productivity|Starter|FOUNDATION_ONLY|Global Project & Digital Thread|Associate supported datasets, runs, scenarios, decisions, and reports with a project and preserve ownership/isolation.
T005|Autosave and Version History|Core workspace and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Persistence|Safely persist changes and restore a prior version; show last-save state and retain recoverability after refresh/relogin.
T006|Undo, Redo, and Recovery|Core workspace and productivity|Starter|FOUNDATION_ONLY|Industrial Workbook|Undo reversible edits and recover from failed operations without destroying the last known-good state.
T007|Engineering Error Inspector|Core workspace and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Enterprise Integration & Collaboration|Give actionable error messages and validation details; keep diagnostic secrets/internal details out of user-visible output.
T008|Formula and Assumption Inspector|Core workspace and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Engineering Validation Center|Display method, formula, units, inputs, assumptions, constraints, and limitations for supported results.
T009|Capability Status Center|Core workspace and productivity|Starter|FOUNDATION_ONLY||Report each capability's implementation/readiness state accurately; separate working tools from prototypes and unconfigured integrations.
T010|Interactive Learning and Help Center|Core workspace and productivity|Starter|FOUNDATION_ONLY||Provide searchable help, worked examples, contextual guidance, and a route from guidance to the relevant tool.
T011|Universal Data Importer|Data and Excel intelligence|Starter|IMPLEMENTED_NEEDS_VALIDATION|Excel Data Cleaning & Import|Import supported CSV/XLSX files with clear sheet/table preview, type/size validation, encoding/error messages, and no destructive partial import.
T012|Multi-Sheet Workbook Mapper|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Industrial Data Platform|Preview workbook sheets and let users map related tables and keys; preserve original source sheets and report join cardinality problems.
T013|Data Quality Profiler|Data and Excel intelligence|Starter|IMPLEMENTED_NEEDS_VALIDATION|Excel Data Cleaning & Import|Report missingness, duplicates, types, distributions, outliers, and data-quality issues without silently deleting records.
T014|Reversible Data Cleaner|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Excel Data Cleaning & Import|Preview proposed changes, provide an audit/change summary, and allow undo; preserve source data until user confirms.
T015|Industrial Field Mapper|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Excel Data Cleaning & Import|Map source columns to canonical industrial fields with confidence/confirmation and preserve original field names.
T016|Unit and Currency Converter|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Localization & Multi-Currency|Convert compatible units; explicitly identify exchange rate, date/source, dimensions, rounding, and unsupported conversions.
T017|Data Join and Merge Studio|Data and Excel intelligence|Mid-Tier Pro|FOUNDATION_ONLY|Industrial Data Platform|Join/merge tables with key profiling, duplicate-key warnings, row-count reconciliation, and preview.
T018|Time-Series Data Processor|Data and Excel intelligence|Mid-Tier Pro|FOUNDATION_ONLY|Industrial Data Platform|Parse time zones/timestamps, order observations, detect gaps/duplicates, resample using explicit rules, and show data loss/aggregation.
T019|Synthetic Industrial Data Generator|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Core IE Tools|Generate reproducible, clearly labelled synthetic data for practice/tests; never confuse synthetic data with actual plant observations.
T020|Dataset Versioning and Lineage|Data and Excel intelligence|Professional|FOUNDATION_ONLY|Persistence|Preserve dataset signature/version, source, transformations, mapping, and links to downstream runs; detect when changed input invalidates a result.
T021|Time Study and Standard Time|Lean manufacturing and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Core IE Tools|Calculate observations, mean/appropriate summary, performance rating and allowances using explicit formulas and units.
T022|Work Sampling Analyzer|Lean manufacturing and productivity|Starter|FOUNDATION_ONLY|Core IE Tools|Estimate activity proportions with sampling assumptions and uncertainty; warn when the sample is inadequate.
T023|Takt Time and Capacity Calculator|Lean manufacturing and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Core IE Tools|Calculate takt/capacity from explicit demand and available-time definitions; reject incompatible time units and zero denominators.
T024|Production Line Balancer|Lean manufacturing and productivity|Mid-Tier Pro|FOUNDATION_ONLY|Lean Manufacturing & Shop Floor Operations|Assign tasks to stations subject to cycle time and precedence; report infeasibility and balance metrics.
T025|Bottleneck and Constraint Analyzer|Lean manufacturing and productivity|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Production Bottleneck & Capacity Recovery Study|Identify constraints from compatible measured data, distinguish observed from inferred bottlenecks, and explain throughput limits.
T026|OEE and Loss Analysis|Lean manufacturing and productivity|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability|Calculate availability, performance, quality, OEE, and loss categories consistently; validate definitions and prevent double counting.
T027|Value Stream Mapping Studio|Lean manufacturing and productivity|Mid-Tier Pro|FOUNDATION_ONLY||Map process/material/information flow, cycle/lead time, WIP, and value-added time; provide editable and exportable outputs.
T028|Root-Cause Analysis Toolkit|Lean manufacturing and productivity|Starter|FOUNDATION_ONLY|Core IE Tools|Support Pareto, fishbone, and 5 Whys with saved causes/actions; do not present correlation as proven causation.
T029|5S and Workplace Audit|Lean manufacturing and productivity|Starter|FOUNDATION_ONLY|Lean Manufacturing & Shop Floor Operations|Record checklist results, evidence, owners, due dates, and progress; support printable/exported audit.
T030|Kaizen and A3 Improvement Manager|Lean manufacturing and productivity|Mid-Tier Pro|FOUNDATION_ONLY||Manage baseline, problem statement, cause, countermeasure, owner, deadline, review, and actual post-change evidence.
T031|Statistical Process Control|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability|Support appropriate control charts, control-limit calculation, run rules when configured, and distinction between control and specification limits.
T032|Process Capability Analyzer|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability|Calculate Cp/Cpk/Pp/Ppk with appropriate assumptions, subgroup/normality warnings, specifications, units, and golden fixture tests.
T033|Measurement Systems Analysis|Quality and statistical engineering|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability|Implement documented gauge R&R/measurement-study methods with correct design assumptions and independently checked fixtures.
T034|Acceptance Sampling Planner|Quality and statistical engineering|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability|Support a stated sampling-plan method with lot/sample/AQL/LTPD assumptions and producer/consumer risk explanations.
T035|Design of Experiments|Quality and statistical engineering|Professional|IMPLEMENTED_NEEDS_VALIDATION|Experiment Lab|Build valid designs, estimate treatment effects, assess model assumptions, and report limitations and reproducibility metadata.
T036|Regression and ANOVA Studio|Quality and statistical engineering|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability|Fit supported models with residual/assumption diagnostics, reproducible parameters, and appropriate uncertainty statistics.
T037|Hypothesis Testing Assistant|Quality and statistical engineering|Research Pack|FOUNDATION_ONLY|Statistical Hypothesis Testing|Select from explicitly supported tests, validate assumptions, show hypotheses/statistics/p-values/confidence intervals/effect sizes, and cite the exact method; do not invent unsupported tests.
T038|FMEA Manager|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability|Record failure modes, effects, causes, controls, scoring rationale, actions, and revision history; avoid implying a score is objective truth.
T039|CAPA and 8D Manager|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability|Track containment, root cause, corrective action, owners, due dates, effectiveness, approvals, and attached evidence.
T040|Quality Cost and Defect Analyzer|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability|Analyze defects, scrap, rework, inspection cost, and cost of poor quality with traceable cost definitions.
T041|Weibull Reliability Analyzer|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability|Fit supported reliability distributions, expose sample/censoring assumptions and fit diagnostics, and test against known data.
T042|MTBF and MTTR Analyzer|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability|Calculate from well-defined operating/failure/repair periods and handle censored or missing intervals transparently.
T043|Preventive Maintenance Planner|Maintenance, reliability, safety, and ergonomics|Mid-Tier Pro|FOUNDATION_ONLY|Predictive Maintenance Hub|Create interval-based tasks with asset, skill, downtime-window and due-date constraints and persistent work plans.
T044|Reliability-Centered Maintenance Assistant|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY||Structure failure/consequence/task decisions with explicit source assumptions and human review; do not claim certified RCM without a complete method.
T045|Spare Parts and Criticality Planner|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|MEIO Matrix|Support criticality, demand, lead time, stockout exposure, reorder and carrying-cost scenarios.
T046|Ergonomics Assessment Toolkit|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|Human Factors & Ergonomics (NIOSH)|Support only documented methods with required measurements, method/version, limitations, and professional-review caveats.
T047|Job Safety and Hazard Register|Maintenance, reliability, safety, and ergonomics|Starter|FOUNDATION_ONLY|Core IE Tools|Record hazards, existing controls, assigned actions, residual risk, review date, and accountable owner; not a substitute for professional safety review.
T048|Equipment Anomaly Monitor|Maintenance, reliability, safety, and ergonomics|Enterprise|EXTERNAL_CONFIGURATION_REQUIRED|Predictive Maintenance Hub|Detect configured anomalous patterns from approved time-series data; expose method, false-positive limitations, source freshness, and thresholds.
T049|Maintenance Backlog Optimizer|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|Predictive Maintenance Hub|Prioritize work orders under available labor, skills, criticality, and downtime windows; explain constraints and trade-offs.
T050|Safety Incident Trend Analyzer|Maintenance, reliability, safety, and ergonomics|Mid-Tier Pro|FOUNDATION_ONLY|Quality Control, Six Sigma & Reliability|Trend incident categories, rates and contributing factors with correct denominator/period definitions; avoid unsupported causal conclusions.
T051|Demand Forecasting Studio|Production planning and supply chain|Professional|FOUNDATION_ONLY|Advanced ML Demand Forecasting|Compare supported baselines/models using time-aware holdout/backtesting and suitable error metrics; show forecast intervals when supported.
T052|Sales and Operations Planning|Production planning and supply chain|Professional|FOUNDATION_ONLY|Advanced Planning & Scheduling|Reconcile demand, inventory, and capacity scenarios with visible assumptions and decision-ready comparisons.
T053|Finite-Capacity Production Scheduler|Production planning and supply chain|Professional|FOUNDATION_ONLY|Advanced Planning & Scheduling|Schedule operations with precedence, resources, calendars, setup times and capacity constraints; return feasible status or explain infeasibility.
T054|Material Requirements Planner|Production planning and supply chain|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Production Planning & Control (PPC)|Explode a validated bill of materials and time-phased demand using lead times, inventory, lot sizing and scheduled receipts.
T055|Inventory Policy Optimizer|Production planning and supply chain|Mid-Tier Pro|FOUNDATION_ONLY|MEIO Matrix|Calculate EOQ/reorder points/safety stock only under stated demand/lead-time/service assumptions and compare cost/service trade-offs.
T056|ABC/XYZ Inventory Analyzer|Production planning and supply chain|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Inventory Playback|Segment by an editable, documented value/variability rule and make thresholds/reclassification reproducible.
T057|Workforce and Shift Planner|Production planning and supply chain|Professional|FOUNDATION_ONLY|Workforce Engineering|Assign qualified staff to shifts under availability, skill, coverage, labor-rule and fairness constraints where provided.
T058|Supplier Performance and Risk Scorecard|Production planning and supply chain|Mid-Tier Pro|FOUNDATION_ONLY|Supplier Risk Matrix|Show score components, weights, data dates, missing evidence, mitigations, and alternate-supplier scenarios.
T059|Warehouse Slotting and Picking Optimizer|Production planning and supply chain|Mid-Tier Pro|FOUNDATION_ONLY|Slotting & Gantt|Use SKU velocity, dimensions, compatibility, capacity and travel assumptions; validate that proposed slots do not exceed capacity.
T060|Supply Chain Network Planner|Production planning and supply chain|Enterprise|FOUNDATION_ONLY|Autonomous Global Supply Chain & Resilient Logistics Network|Model suppliers/sites/routes/capacity/costs and disruptions with transparent data scope and scenario comparisons.
T061|Linear and Mixed-Integer Optimization|Optimization and facilities|Starter|IMPLEMENTED_NEEDS_VALIDATION|MILP Solvers|Retain existing basic MILP access; validate model structure, bounds/units and solver result independently. Advanced workload quotas may be tiered without blocking basic learning models.
T062|Constraint and Solver Diagnostics|Optimization and facilities|Professional|FOUNDATION_ONLY|MILP Solvers|Distinguish infeasible, unbounded, optimal, feasible, time-limit and solver-error states; report actionable constraint diagnostics only where supported by the solver.
T063|Assignment and Scheduling Optimizer|Optimization and facilities|Professional|FOUNDATION_ONLY|MILP Solvers|Build valid assignment/scheduling models with explicit capacity/precedence and independently validate objective and constraints.
T064|Vehicle Routing Optimizer|Optimization and facilities|Mid-Tier Pro|FOUNDATION_ONLY|Fleet Routing|Validate depots, time windows, vehicle capacities, shifts, service times, reachable stops, route cost/distance and unserved customers.
T065|Facility Layout and SLP Studio|Optimization and facilities|Starter|IMPLEMENTED_NEEDS_VALIDATION|Facility Layout & Warehousing|Fix and strengthen the existing facility layout workflow: department CRUD, from-to matrix, relationship chart, SLP scoring, heatmap/block layout, distances, handling cost and usable export. Every department must appear; blank/missing flows must have clear states.
T066|Cutting Stock and Bin Packing|Optimization and facilities|Professional|FOUNDATION_ONLY|MILP Solvers|Solve supported packing/cutting cases and validate item dimensions, capacity, material balance, feasibility and waste calculation.
T067|Multi-Objective Optimization|Optimization and facilities|Enterprise|FOUNDATION_ONLY|Multi-Objective Optimization|Show objectives, constraints, trade-off/Pareto solutions, and units; do not label a weighted solution universally optimal.
T068|Sensitivity and Robust Optimization|Optimization and facilities|Enterprise|FOUNDATION_ONLY|Robust & Resilient Optimization|Test stated parameter ranges/scenarios, explain model limits, and preserve random seeds/solver settings where relevant.
T069|Network Flow and Location Optimization|Optimization and facilities|Enterprise|FOUNDATION_ONLY|Geospatial Network Designer|Optimize supported flow/location problems under capacity and demand constraints; independently recompute flow balance/cost.
T070|Queuing and Service-System Analyzer|Optimization and facilities|Professional|FOUNDATION_ONLY|Core IE Tools|Implement supported queue models with explicit distribution/utilization assumptions, stability conditions and units; distinguish analytical approximations from simulation.
T071|Discrete-Event Simulation|Simulation, forecasting, and digital twins|Enterprise|FOUNDATION_ONLY|Industrial Simulation Lab|Implement a real, documented event simulation for supported processes with event logic, resource queues, warm-up/replications and output checks; do not present a generic KPI screen as a simulator.
T072|Monte Carlo Risk Simulator|Simulation, forecasting, and digital twins|Enterprise|IMPLEMENTED_NEEDS_VALIDATION|Monte Carlo Sim|Support distributions, reproducible seeds, correlated inputs only when correctly modeled, outcome percentiles, convergence checks and sensitivity.
T073|What-If Scenario Manager|Simulation, forecasting, and digital twins|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Scenarios|Save/branch baseline and scenario inputs, compare KPI deltas, expose input differences and require rerun after relevant source/model changes.
T074|Digital Twin Calibration Studio|Simulation, forecasting, and digital twins|Enterprise Plus|EXTERNAL_CONFIGURATION_REQUIRED|Live Industrial Digital Twin|Compare a simulated model with approved measured data, show calibration fit/residuals, data freshness, limitations and versioning.
T075|Forecast and Model Drift Monitor|Simulation, forecasting, and digital twins|Enterprise|FOUNDATION_ONLY|Advanced ML Demand Forecasting|Compare predictions with later actual observations, monitor documented thresholds and preserve model/data versions.
T076|Process Mining Analyzer|Simulation, forecasting, and digital twins|Professional|FOUNDATION_ONLY|Industrial Data Platform|Reconstruct flows from event logs with case/activity/timestamp validation, conformance and delay metrics; support data filtering and export.
T077|Energy Performance Optimizer|Simulation, forecasting, and digital twins|Professional|FOUNDATION_ONLY|Industrial Sustainability & LCA|Analyze measured consumption and constrained alternatives with unit/baseline transparency; do not imply automatic control of equipment.
T078|Carbon Emissions Calculator|Simulation, forecasting, and digital twins|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Carbon Accounting|Version factors, factor source/date, units and boundaries; report scope and uncertainty; never imply audited disclosure without audit.
T079|Water and Waste Efficiency Analyzer|Simulation, forecasting, and digital twins|Mid-Tier Pro|FOUNDATION_ONLY|Green IE & Sustainability|Trend input/output flows, explain balances and normalized measures, and disclose missing factor/data assumptions.
T080|Industrial Disruption Simulator|Simulation, forecasting, and digital twins|Enterprise Plus|FOUNDATION_ONLY|Autonomous Kinetic-Digital Twin (AKDT) for Industrial Logistics Resilience|Stress-test connected production/logistics assumptions and compare recovery choices; label synthetic versus live inputs and model limitations.
T081|Engineering Economics Calculator|Economics, research, and education|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Engineering Economics & Finance|Support documented NPV/IRR/payback and cash-flow conventions with units, currency, discount rate and boundary tests.
T082|Industrial Costing and Variance Analyzer|Economics, research, and education|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Engineering Economics & Finance|Reconcile actual/standard/plan costs, explain variance components and preserve source/currency/time scope.
T083|Evidence-Based ROI Tracker|Economics, research, and education|Professional|IMPLEMENTED_NEEDS_VALIDATION|Venture Studio|Keep baseline, intervention, measurement window, implementation cost, actual outcome, evidence source and verifier separate; estimates are not verified savings.
T084|Engineering Project Portfolio Scorer|Economics, research, and education|Professional|FOUNDATION_ONLY|Capital Investment & Engineering Economics|Show criteria, weights, normalization and sensitivity; do not conceal subjective weighting.
T085|Statistical Power and Sample-Size Planner|Economics, research, and education|Research Pack|FOUNDATION_ONLY|Statistical Hypothesis Testing|Calculate only supported designs and tests; show alpha, power, effect size, assumptions and method/version.
T086|Hypothesis and Evidence Register|Economics, research, and education|Research Pack|FOUNDATION_ONLY|Research AI|Link claims/hypotheses to datasets, methods, findings, limitations, sources and review decisions.
T087|Reproducibility Pack Generator|Economics, research, and education|Research Pack|IMPLEMENTED_NEEDS_VALIDATION|Live Reproducible Paper Canvas|Package configuration, version/seed/data fingerprints, environment/dependency metadata and outputs without embedding secrets or unauthorized source data.
T088|Research and Literature Evidence Matrix|Economics, research, and education|Research Pack|IMPLEMENTED_NEEDS_VALIDATION|Literature & Citation Matrix|Track bibliographic metadata, source links, claims and evidence gaps; verify cited sources rather than inventing references.
T089|Student Learning and Practice Mode|Economics, research, and education|Starter|FOUNDATION_ONLY|Core IE Tools|Provide worked examples, guided steps and practice problems with correct answer checks and transparent solution methods.
T090|Research Report and Methods Builder|Economics, research, and education|Research Pack|FOUNDATION_ONLY|Live Reproducible Paper Canvas|Generate structured technical reports with method, assumptions, equations, figures, limitations and reproducibility details; verify the generated file opens.
T091|Team Collaboration and Review|Enterprise, collaboration, and trust|Enterprise|FOUNDATION_ONLY|Team Workspaces & RBAC|Enforce project membership and workspace boundaries for sharing, comments, assignments and review history.
T092|Decision Register and Approval Workflow|Enterprise, collaboration, and trust|Enterprise|IMPLEMENTED_NEEDS_VALIDATION|Engineering Decision Center|Persist decision owner, evidence, status transitions, approval actor/time, reasons and implementation follow-up with auditability.
T093|Cross-Module Workflow Builder|Enterprise, collaboration, and trust|Enterprise|FOUNDATION_ONLY|Agentic Workflows|Chain existing tools through a typed workflow with declared inputs/outputs, validation, dependency tracking and per-step failures. No fake successful downstream step.
T094|KPI Dashboard and Alert Center|Enterprise, collaboration, and trust|Enterprise|IMPLEMENTED_NEEDS_VALIDATION|Control Tower|Aggregate authorized datasets, apply configurable thresholds, state data freshness and prevent duplicate/noisy alerts where feasible.
T095|Verified Reporting and Export Studio|Enterprise, collaboration, and trust|Professional|IMPLEMENTED_NEEDS_VALIDATION|Executive Report Center|Produce actual XLSX/PDF/PPTX/ZIP files as advertised, reopen/parse them in tests, validate key content and carry data source, assumptions and result status into exports. Keep basic necessary exports available under existing Starter rules if already promised.
T096|Integration Management Center|Enterprise, collaboration, and trust|Enterprise|EXTERNAL_CONFIGURATION_REQUIRED|Industrial Connectivity Hub|Show real adapter status, configuration needs, auth/test/sync times, data freshness, error/retry logs and permissions; mark metadata-only adapters as not connected.
T097|API, SDK, and Plugin Toolkit|Enterprise, collaboration, and trust|Enterprise|EXTERNAL_CONFIGURATION_REQUIRED|FastAPI Gateway|Document and validate supported interfaces, schema/versioning, auth, permission scopes, rate/error handling and plugin execution; metadata-only plugins must not appear executable.
T098|Enterprise Identity and Audit Center|Enterprise, collaboration, and trust|Enterprise Plus|EXTERNAL_CONFIGURATION_REQUIRED|Enterprise Security & Governance|Integrate only supported identity/audit controls; test role boundaries, session expiry and audit coverage. Never claim SSO/MFA is active unless configured and verified.
T099|Data Governance and Recovery Center|Enterprise, collaboration, and trust|Enterprise Plus|EXTERNAL_CONFIGURATION_REQUIRED|Persistence|Provide access-controlled retention/export/delete/backup/restore workflows where supported, audit their outcomes, and test restore in isolated non-production. Never test with destructive production operations.
T100|Support, Diagnostics, and Incident Center|Enterprise, collaboration, and trust|Enterprise|IMPLEMENTED_NEEDS_VALIDATION|Enterprise Integration & Collaboration|Provide actionable status, diagnostic bundles with secrets/PII redacted, incident/recovery instructions and support reference IDs; do not expose stack traces or secrets to ordinary users."""

TOOL_STATUS_VALUES = (
    "VERIFIED_WORKING",
    "IMPLEMENTED_NEEDS_VALIDATION",
    "FOUNDATION_ONLY",
    "MISSING",
    "EXTERNAL_CONFIGURATION_REQUIRED",
    "BLOCKED",
)

def load_tool_catalog() -> list[dict[str, str]]:
    """Load the stable T001–T100 manifest and validate its minimum metadata."""
    catalog: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in TARGET_TOOL_ROWS.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 6)
        if len(parts) != 7:
            raise ValueError("100-tool catalog row must have seven fields.")
        tool_id, name, workbench, tier, status, route, acceptance = (part.strip() for part in parts)
        if not tool_id or tool_id in seen:
            raise ValueError(f"Duplicate or empty target-tool identity: {tool_id!r}")
        if tier not in TIER_ORDER:
            raise ValueError(f"Unrecognized tier for {tool_id}: {tier!r}")
        if status not in TOOL_STATUS_VALUES:
            raise ValueError(f"Unrecognized readiness status for {tool_id}: {status!r}")
        seen.add(tool_id)
        catalog.append({
            "tool_id": tool_id,
            "canonical_name": name,
            "workbench": workbench,
            "target_minimum_tier": tier,
            "implementation_status": status,
            "related_module_or_route": route,
            "target_acceptance": acceptance,
        })
    expected = {f"T{i:03d}" for i in range(1, 101)}
    if seen != expected:
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        raise ValueError(f"100-tool catalog identity mismatch; missing={missing}, extra={extra}")
    return catalog


TOOL_CATALOG = load_tool_catalog()

def tool_access_decision(tool: dict[str, str], tier: str, allowed_modules: Iterable[str]) -> tuple[bool, str]:
    """Guard launch links with both target-tier and existing route entitlement."""
    required = tool["target_minimum_tier"]
    if not tier_allows(tier, required):
        return False, f"This target requires {required}; current package is {tier}."
    route = tool.get("related_module_or_route", "")
    if not route:
        return False, "No existing route was confirmed for this target; no launch action is advertised."
    route_tier = module_required_tier(route)
    if route_tier not in TIER_ORDER or not tier_allows(tier, route_tier):
        return False, "The related route has no verified matching access policy for this package."
    if route not in set(str(x) for x in allowed_modules):
        return False, "The related module is not available to this account; access is not bypassed."
    return True, route


def _request_existing_route(route: str, section: str) -> None:
    """Request a route through the shell's normal module/tier checks."""
    st.session_state["_shoir_requested_module"] = route
    st.session_state["shoir_shell_section"] = section
    st.session_state["shoir_shell_section_radio"] = section


def render_tool_library(username: str, tier: str, allowed_modules: Iterable[str]) -> None:
    """Render a compact, searchable catalogue inside the existing Shoir-IE shell."""
    catalog = TOOL_CATALOG
    allowed = tuple(str(x) for x in allowed_modules)
    st.markdown("## Tool Library")
    st.caption("100 target capabilities, grouped into 10 workbenches. This adds a discovery sector without replacing the current navigation or module renderers.")
    st.info(
        "A catalog card is not proof of a working engineering engine. Readiness labels reflect the source-level audit; "
        "authenticated browser, calculation, persistence and export checks remain incomplete until evidence is recorded."
    )

    counts = Counter(item["implementation_status"] for item in catalog)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Target tools", len(catalog))
    metric_cols[1].metric("Needs validation", counts["IMPLEMENTED_NEEDS_VALIDATION"])
    metric_cols[2].metric("Foundation only", counts["FOUNDATION_ONLY"])
    metric_cols[3].metric("External configuration", counts["EXTERNAL_CONFIGURATION_REQUIRED"])
    st.caption(f"Verified end-to-end on the currently audited revision: {counts['VERIFIED_WORKING']}. This count intentionally remains zero unless required acceptance evidence has passed.")

    filter_cols = st.columns([2, 2, 2])
    query = filter_cols[0].text_input("Search tool library", placeholder="Search a tool or related module", key="shoir_100_tool_search")
    workbenches = ["All workbenches"] + list(dict.fromkeys(item["workbench"] for item in catalog))
    selected_workbench = filter_cols[1].selectbox("Workbench", workbenches, key="shoir_100_tool_workbench")
    status_filter = filter_cols[2].selectbox("Readiness", ["All statuses", *TOOL_STATUS_VALUES], key="shoir_100_tool_status")

    filtered = []
    needle = query.strip().casefold()
    for item in catalog:
        if selected_workbench != "All workbenches" and item["workbench"] != selected_workbench:
            continue
        if status_filter != "All statuses" and item["implementation_status"] != status_filter:
            continue
        if needle and needle not in " ".join((
            item["tool_id"], item["canonical_name"], item["workbench"],
            item["target_minimum_tier"], item["related_module_or_route"],
        )).casefold():
            continue
        filtered.append(item)
    st.caption(f"Showing {len(filtered)} of {len(catalog)} target capabilities.")

    workbench_order = list(dict.fromkeys(item["workbench"] for item in catalog))
    for workbench in workbench_order:
        group = [item for item in filtered if item["workbench"] == workbench]
        if not group:
            continue
        with st.expander(f"{workbench} · {len(group)} tools", expanded=bool(needle or selected_workbench != "All workbenches")):
            for item in group:
                with st.container(border=True):
                    st.markdown(f"**{item['tool_id']} · {item['canonical_name']}**")
                    cols = st.columns([2, 1])
                    with cols[0]:
                        st.caption(f"Workbench: {item['workbench']}")
                        st.write(f"Minimum target tier: **{item['target_minimum_tier']}**")
                        st.markdown("**Target acceptance**")
                        st.write(item["target_acceptance"])
                        route = item["related_module_or_route"]
                        if route:
                            st.write(f"Related existing module: **{route}**")
                            st.caption("The related module may not implement every requirement of this target tool.")
                        else:
                            st.caption("No one-to-one module route confirmed in the source audit.")
                    with cols[1]:
                        st.code(item["implementation_status"], language="text")
                        can_open, reason = tool_access_decision(item, tier, allowed)
                        if route := item["related_module_or_route"]:
                            route_section = {
                                "Industrial Workbook": "DATA",
                                "Excel Data Cleaning & Import": "DATA",
                                "Industrial Data Platform": "DATA",
                                "Engineering Validation Center": "DATA",
                                "Persistence": "WORKBENCH",
                                "AI Copilot": "KNOWLEDGE",
                                "Global Project & Digital Thread": "DECISIONS",
                                "Core IE Tools": "ANALYZE",
                                "Lean Manufacturing & Shop Floor Operations": "ANALYZE",
                                "Production Bottleneck & Capacity Recovery Study": "ANALYZE",
                                "Quality Control, Six Sigma & Reliability": "ANALYZE",
                                "Quality Engineering & Reliability": "ANALYZE",
                                "Experiment Lab": "RESEARCH",
                                "Statistical Hypothesis Testing": "RESEARCH",
                                "Literature & Citation Matrix": "RESEARCH",
                                "Research AI": "RESEARCH",
                                "Live Reproducible Paper Canvas": "RESEARCH",
                                "Localization & Multi-Currency": "DATA",
                                "Inventory Playback": "DATA",
                                "Scenarios": "SIMULATE",
                                "Monte Carlo Sim": "SIMULATE",
                                "Industrial Simulation Lab": "SIMULATE",
                                "Live Industrial Digital Twin": "SIMULATE",
                                "Advanced ML Demand Forecasting": "SIMULATE",
                                "Carbon Accounting": "ANALYZE",
                                "Industrial Sustainability & LCA": "ANALYZE",
                                "Green IE & Sustainability": "ANALYZE",
                                "Autonomous Kinetic-Digital Twin (AKDT) for Industrial Logistics Resilience": "SIMULATE",
                                "Autonomous Global Supply Chain & Resilient Logistics Network": "OPTIMIZE",
                                "Advanced Planning & Scheduling": "OPTIMIZE",
                                "Production Planning & Control (PPC)": "OPTIMIZE",
                                "MEIO Matrix": "OPTIMIZE",
                                "MILP Solvers": "OPTIMIZE",
                                "Fleet Routing": "OPTIMIZE",
                                "Facility Layout & Warehousing": "ANALYZE",
                                "Multi-Objective Optimization": "OPTIMIZE",
                                "Robust & Resilient Optimization": "OPTIMIZE",
                                "Geospatial Network Designer": "OPTIMIZE",
                                "Engineering Economics & Finance": "ANALYZE",
                                "Capital Investment & Engineering Economics": "DECISIONS",
                                "Venture Studio": "DECISIONS",
                                "Workforce Engineering": "OPERATIONS",
                                "Predictive Maintenance Hub": "OPERATIONS",
                                "Human Factors & Ergonomics (NIOSH)": "OPERATIONS",
                                "Supplier Risk Matrix": "OPERATIONS",
                                "Slotting & Gantt": "OPTIMIZE",
                                "Quality Control, Six Sigma & Reliability": "ANALYZE",
                                "Team Workspaces & RBAC": "OPERATIONS",
                                "Engineering Decision Center": "DECISIONS",
                                "Agentic Workflows": "KNOWLEDGE",
                                "Control Tower": "OPERATIONS",
                                "Executive Report Center": "DECISIONS",
                                "Industrial Connectivity Hub": "OPERATIONS",
                                "FastAPI Gateway": "OPERATIONS",
                                "Enterprise Security & Governance": "OPERATIONS",
                                "Enterprise Integration & Collaboration": "OPERATIONS",
                                "Human Factors & Ergonomics (NIOSH)": "OPERATIONS",
                                "Predictive Maintenance Hub": "OPERATIONS",
                            }.get(route, "WORKBENCH")
                            st.button(
                                "Open related module",
                                key=f"shoir_100_open_{item['tool_id']}",
                                disabled=not can_open,
                                on_click=_request_existing_route,
                                args=(route, route_section),
                                use_container_width=True,
                            )
                        if not can_open:
                            st.caption(reason)
                        elif item["implementation_status"] != "VERIFIED_WORKING":
                            st.caption("Discovery link only; target-specific readiness checks have not passed.")
