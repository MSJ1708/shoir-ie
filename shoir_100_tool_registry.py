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

TARGET_TOOL_ROWS = r"""T001|Personalized Engineering Home|Core workspace and productivity|Starter|FOUNDATION_ONLY|
T002|Guided Study Wizard|Core workspace and productivity|Starter|FOUNDATION_ONLY|AI Copilot
T003|Universal Search and Command Center|Core workspace and productivity|Starter|FOUNDATION_ONLY|AI Copilot
T004|Engineering Project Manager|Core workspace and productivity|Starter|FOUNDATION_ONLY|Global Project & Digital Thread
T005|Autosave and Version History|Core workspace and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Persistence
T006|Undo, Redo, and Recovery|Core workspace and productivity|Starter|FOUNDATION_ONLY|Industrial Workbook
T007|Engineering Error Inspector|Core workspace and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Enterprise Integration & Collaboration
T008|Formula and Assumption Inspector|Core workspace and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Engineering Validation Center
T009|Capability Status Center|Core workspace and productivity|Starter|FOUNDATION_ONLY|
T010|Interactive Learning and Help Center|Core workspace and productivity|Starter|FOUNDATION_ONLY|
T011|Universal Data Importer|Data and Excel intelligence|Starter|IMPLEMENTED_NEEDS_VALIDATION|Excel Data Cleaning & Import
T012|Multi-Sheet Workbook Mapper|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Industrial Data Platform
T013|Data Quality Profiler|Data and Excel intelligence|Starter|IMPLEMENTED_NEEDS_VALIDATION|Excel Data Cleaning & Import
T014|Reversible Data Cleaner|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Excel Data Cleaning & Import
T015|Industrial Field Mapper|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Excel Data Cleaning & Import
T016|Unit and Currency Converter|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Localization & Multi-Currency
T017|Data Join and Merge Studio|Data and Excel intelligence|Mid-Tier Pro|FOUNDATION_ONLY|Industrial Data Platform
T018|Time-Series Data Processor|Data and Excel intelligence|Mid-Tier Pro|FOUNDATION_ONLY|Industrial Data Platform
T019|Synthetic Industrial Data Generator|Data and Excel intelligence|Starter|FOUNDATION_ONLY|Core IE Tools
T020|Dataset Versioning and Lineage|Data and Excel intelligence|Professional|FOUNDATION_ONLY|Persistence
T021|Time Study and Standard Time|Lean manufacturing and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Core IE Tools
T022|Work Sampling Analyzer|Lean manufacturing and productivity|Starter|FOUNDATION_ONLY|Core IE Tools
T023|Takt Time and Capacity Calculator|Lean manufacturing and productivity|Starter|IMPLEMENTED_NEEDS_VALIDATION|Core IE Tools
T024|Production Line Balancer|Lean manufacturing and productivity|Mid-Tier Pro|FOUNDATION_ONLY|Lean Manufacturing & Shop Floor Operations
T025|Bottleneck and Constraint Analyzer|Lean manufacturing and productivity|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Production Bottleneck & Capacity Recovery Study
T026|OEE and Loss Analysis|Lean manufacturing and productivity|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability
T027|Value Stream Mapping Studio|Lean manufacturing and productivity|Mid-Tier Pro|FOUNDATION_ONLY|
T028|Root-Cause Analysis Toolkit|Lean manufacturing and productivity|Starter|FOUNDATION_ONLY|Core IE Tools
T029|5S and Workplace Audit|Lean manufacturing and productivity|Starter|FOUNDATION_ONLY|Lean Manufacturing & Shop Floor Operations
T030|Kaizen and A3 Improvement Manager|Lean manufacturing and productivity|Mid-Tier Pro|FOUNDATION_ONLY|
T031|Statistical Process Control|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability
T032|Process Capability Analyzer|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability
T033|Measurement Systems Analysis|Quality and statistical engineering|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability
T034|Acceptance Sampling Planner|Quality and statistical engineering|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability
T035|Design of Experiments|Quality and statistical engineering|Professional|IMPLEMENTED_NEEDS_VALIDATION|Experiment Lab
T036|Regression and ANOVA Studio|Quality and statistical engineering|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability
T037|Hypothesis Testing Assistant|Quality and statistical engineering|Research Pack|FOUNDATION_ONLY|Statistical Hypothesis Testing
T038|FMEA Manager|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability
T039|CAPA and 8D Manager|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability
T040|Quality Cost and Defect Analyzer|Quality and statistical engineering|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Quality Control, Six Sigma & Reliability
T041|Weibull Reliability Analyzer|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability
T042|MTBF and MTTR Analyzer|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|Quality Engineering & Reliability
T043|Preventive Maintenance Planner|Maintenance, reliability, safety, and ergonomics|Mid-Tier Pro|FOUNDATION_ONLY|Predictive Maintenance Hub
T044|Reliability-Centered Maintenance Assistant|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|
T045|Spare Parts and Criticality Planner|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|MEIO Matrix
T046|Ergonomics Assessment Toolkit|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|Human Factors & Ergonomics (NIOSH)
T047|Job Safety and Hazard Register|Maintenance, reliability, safety, and ergonomics|Starter|FOUNDATION_ONLY|Core IE Tools
T048|Equipment Anomaly Monitor|Maintenance, reliability, safety, and ergonomics|Enterprise|EXTERNAL_CONFIGURATION_REQUIRED|Predictive Maintenance Hub
T049|Maintenance Backlog Optimizer|Maintenance, reliability, safety, and ergonomics|Professional|FOUNDATION_ONLY|Predictive Maintenance Hub
T050|Safety Incident Trend Analyzer|Maintenance, reliability, safety, and ergonomics|Mid-Tier Pro|FOUNDATION_ONLY|Quality Control, Six Sigma & Reliability
T051|Demand Forecasting Studio|Production planning and supply chain|Professional|FOUNDATION_ONLY|Advanced ML Demand Forecasting
T052|Sales and Operations Planning|Production planning and supply chain|Professional|FOUNDATION_ONLY|Advanced Planning & Scheduling
T053|Finite-Capacity Production Scheduler|Production planning and supply chain|Professional|FOUNDATION_ONLY|Advanced Planning & Scheduling
T054|Material Requirements Planner|Production planning and supply chain|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Production Planning & Control (PPC)
T055|Inventory Policy Optimizer|Production planning and supply chain|Mid-Tier Pro|FOUNDATION_ONLY|MEIO Matrix
T056|ABC/XYZ Inventory Analyzer|Production planning and supply chain|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Inventory Playback
T057|Workforce and Shift Planner|Production planning and supply chain|Professional|FOUNDATION_ONLY|Workforce Engineering
T058|Supplier Performance and Risk Scorecard|Production planning and supply chain|Mid-Tier Pro|FOUNDATION_ONLY|Supplier Risk Matrix
T059|Warehouse Slotting and Picking Optimizer|Production planning and supply chain|Mid-Tier Pro|FOUNDATION_ONLY|Slotting & Gantt
T060|Supply Chain Network Planner|Production planning and supply chain|Enterprise|FOUNDATION_ONLY|Autonomous Global Supply Chain & Resilient Logistics Network
T061|Linear and Mixed-Integer Optimization|Optimization and facilities|Starter|IMPLEMENTED_NEEDS_VALIDATION|MILP Solvers
T062|Constraint and Solver Diagnostics|Optimization and facilities|Professional|FOUNDATION_ONLY|MILP Solvers
T063|Assignment and Scheduling Optimizer|Optimization and facilities|Professional|FOUNDATION_ONLY|MILP Solvers
T064|Vehicle Routing Optimizer|Optimization and facilities|Mid-Tier Pro|FOUNDATION_ONLY|Fleet Routing
T065|Facility Layout and SLP Studio|Optimization and facilities|Starter|IMPLEMENTED_NEEDS_VALIDATION|Facility Layout & Warehousing
T066|Cutting Stock and Bin Packing|Optimization and facilities|Professional|FOUNDATION_ONLY|MILP Solvers
T067|Multi-Objective Optimization|Optimization and facilities|Enterprise|FOUNDATION_ONLY|Multi-Objective Optimization
T068|Sensitivity and Robust Optimization|Optimization and facilities|Enterprise|FOUNDATION_ONLY|Robust & Resilient Optimization
T069|Network Flow and Location Optimization|Optimization and facilities|Enterprise|FOUNDATION_ONLY|Geospatial Network Designer
T070|Queuing and Service-System Analyzer|Optimization and facilities|Professional|FOUNDATION_ONLY|Core IE Tools
T071|Discrete-Event Simulation|Simulation, forecasting, and digital twins|Enterprise|FOUNDATION_ONLY|Industrial Simulation Lab
T072|Monte Carlo Risk Simulator|Simulation, forecasting, and digital twins|Enterprise|IMPLEMENTED_NEEDS_VALIDATION|Monte Carlo Sim
T073|What-If Scenario Manager|Simulation, forecasting, and digital twins|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Scenarios
T074|Digital Twin Calibration Studio|Simulation, forecasting, and digital twins|Enterprise Plus|EXTERNAL_CONFIGURATION_REQUIRED|Live Industrial Digital Twin
T075|Forecast and Model Drift Monitor|Simulation, forecasting, and digital twins|Enterprise|FOUNDATION_ONLY|Advanced ML Demand Forecasting
T076|Process Mining Analyzer|Simulation, forecasting, and digital twins|Professional|FOUNDATION_ONLY|Industrial Data Platform
T077|Energy Performance Optimizer|Simulation, forecasting, and digital twins|Professional|FOUNDATION_ONLY|Industrial Sustainability & LCA
T078|Carbon Emissions Calculator|Simulation, forecasting, and digital twins|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Carbon Accounting
T079|Water and Waste Efficiency Analyzer|Simulation, forecasting, and digital twins|Mid-Tier Pro|FOUNDATION_ONLY|Green IE & Sustainability
T080|Industrial Disruption Simulator|Simulation, forecasting, and digital twins|Enterprise Plus|FOUNDATION_ONLY|Autonomous Kinetic-Digital Twin (AKDT) for Industrial Logistics Resilience
T081|Engineering Economics Calculator|Economics, research, and education|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Engineering Economics & Finance
T082|Industrial Costing and Variance Analyzer|Economics, research, and education|Mid-Tier Pro|IMPLEMENTED_NEEDS_VALIDATION|Engineering Economics & Finance
T083|Evidence-Based ROI Tracker|Economics, research, and education|Professional|IMPLEMENTED_NEEDS_VALIDATION|Venture Studio
T084|Engineering Project Portfolio Scorer|Economics, research, and education|Professional|FOUNDATION_ONLY|Capital Investment & Engineering Economics
T085|Statistical Power and Sample-Size Planner|Economics, research, and education|Research Pack|FOUNDATION_ONLY|Statistical Hypothesis Testing
T086|Hypothesis and Evidence Register|Economics, research, and education|Research Pack|FOUNDATION_ONLY|Research AI
T087|Reproducibility Pack Generator|Economics, research, and education|Research Pack|IMPLEMENTED_NEEDS_VALIDATION|Live Reproducible Paper Canvas
T088|Research and Literature Evidence Matrix|Economics, research, and education|Research Pack|IMPLEMENTED_NEEDS_VALIDATION|Literature & Citation Matrix
T089|Student Learning and Practice Mode|Economics, research, and education|Starter|FOUNDATION_ONLY|Core IE Tools
T090|Research Report and Methods Builder|Economics, research, and education|Research Pack|FOUNDATION_ONLY|Live Reproducible Paper Canvas
T091|Team Collaboration and Review|Enterprise, collaboration, and trust|Enterprise|FOUNDATION_ONLY|Team Workspaces & RBAC
T092|Decision Register and Approval Workflow|Enterprise, collaboration, and trust|Enterprise|IMPLEMENTED_NEEDS_VALIDATION|Engineering Decision Center
T093|Cross-Module Workflow Builder|Enterprise, collaboration, and trust|Enterprise|FOUNDATION_ONLY|Agentic Workflows
T094|KPI Dashboard and Alert Center|Enterprise, collaboration, and trust|Enterprise|IMPLEMENTED_NEEDS_VALIDATION|Control Tower
T095|Verified Reporting and Export Studio|Enterprise, collaboration, and trust|Professional|IMPLEMENTED_NEEDS_VALIDATION|Executive Report Center
T096|Integration Management Center|Enterprise, collaboration, and trust|Enterprise|EXTERNAL_CONFIGURATION_REQUIRED|Industrial Connectivity Hub
T097|API, SDK, and Plugin Toolkit|Enterprise, collaboration, and trust|Enterprise|EXTERNAL_CONFIGURATION_REQUIRED|FastAPI Gateway
T098|Enterprise Identity and Audit Center|Enterprise, collaboration, and trust|Enterprise Plus|EXTERNAL_CONFIGURATION_REQUIRED|Enterprise Security & Governance
T099|Data Governance and Recovery Center|Enterprise, collaboration, and trust|Enterprise Plus|EXTERNAL_CONFIGURATION_REQUIRED|Persistence
T100|Support, Diagnostics, and Incident Center|Enterprise, collaboration, and trust|Enterprise|IMPLEMENTED_NEEDS_VALIDATION|Enterprise Integration & Collaboration"""

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
        parts = line.split("|", 5)
        if len(parts) != 6:
            raise ValueError("100-tool catalog row must have six fields.")
        tool_id, name, workbench, tier, status, route = (part.strip() for part in parts)
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
