"""Shared industrial intelligence foundation for Shoir-IE.

The module provides deterministic, evidence-bounded analysis contracts for the
16 Industrial Intelligence Suite tools, shared workflow services, and a single
organization-scoped workspace repository. It deliberately does not connect to
live OT/ERP systems, invent measurements, authorize safety work, or self-certify
financial benefits. Shared organization writes go through the existing managed
organization-workspace persistence path with server-side membership checks.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import pandas as pd
import streamlit as st


MODULE_NAME = "Industrial Operating System"
STATE_PREFIX = "shoir_industrial_intelligence_"
MAX_RECORDS = 5000
MAX_RECORD_BYTES = 64000
MAX_GRAPH_NODES = 10000
MAX_GRAPH_EDGES = 20000
VISUAL_STATE_KEYS = {
    "records": "shoir_industrial_intelligence_records",
    "nodes": "shoir_industrial_intelligence_nodes",
    "edges": "shoir_industrial_intelligence_edges",
    "actions": "shoir_industrial_intelligence_actions",
    "events": "shoir_industrial_intelligence_events",
    "models": "shoir_industrial_intelligence_models",
}

PROVENANCE = (
    "LIVE", "IMPORTED", "MANUAL", "SYNTHETIC", "SIMULATED", "MOCK", "STALE",
)
PROVENANCE_RELIABILITY = {
    "LIVE": "Source freshness and connector health still require validation.",
    "IMPORTED": "Imported source; validate schema, timestamp, units and completeness.",
    "MANUAL": "User-entered information; independent source verification is not implied.",
    "SYNTHETIC": "Deterministic test or demonstration data; not plant evidence.",
    "SIMULATED": "Model output; not an observed plant measurement.",
    "MOCK": "Mock fixture; never evidence of a live integration.",
    "STALE": "Stale information; not suitable for an unqualified current-state decision.",
}

SUITES = [
    {"id": "operations", "name": "Operations Intelligence", "tools": ["mission-control", "process-mining", "shift-handover"]},
    {"id": "engineering", "name": "Engineering Intelligence", "tools": ["engineering-change", "data-trust", "experimentation"]},
    {"id": "maintenance", "name": "Maintenance and Project Intelligence", "tools": ["asset-reliability", "turnaround", "commissioning"]},
    {"id": "production", "name": "Production and Quality Intelligence", "tools": ["yield-intelligence", "batch-genealogy"]},
    {"id": "supply", "name": "Supply Chain and Procurement Intelligence", "tools": ["procurement-assurance", "spare-parts"]},
    {"id": "enterprise", "name": "Energy and Enterprise Assurance", "tools": ["energy-flexibility", "ot-assurance", "benchmarking"]},
]

TOOL_CATALOG = [
    {"tool_code": "II-001", "id": "mission-control", "name": "Industrial Operations Mission Control", "suite": "operations", "aliases": ["operations mission control", "plant mission control", "operational exception resolution"], "purpose": "Correlate evidenced operational exceptions and turn them into owned, traceable actions.", "input": "event, severity, urgency, affected domains, operational impact and evidence references", "method": "Transparent rule-based triage; suspected cause is not confirmed cause."},
    {"tool_code": "II-002", "id": "process-mining", "name": "Industrial Process Mining and Hidden Inefficiency Intelligence", "suite": "operations", "aliases": ["process mining", "hidden lost time finder", "process conformance"], "purpose": "Reconstruct actual event-log variants, inter-event elapsed time, rework loops and conformance.", "input": "event list with case_id, activity, timestamp; optional lifecycle, explicit wait minutes and approved sequence", "method": "Chronological event-log analysis; gaps are elapsed time, not automatically waiting time."},
    {"tool_code": "II-003", "id": "engineering-change", "name": "Engineering Change Impact Twin", "suite": "engineering", "aliases": ["change impact twin", "engineering change impact", "management of change"], "purpose": "Traverse explicit dependencies from a proposed change and create a reviewable impact register.", "input": "change details, source entity and directed dependency edges", "method": "Graph reachability; only supplied dependencies are reported."},
    {"tool_code": "II-004", "id": "turnaround", "name": "Shutdown and Turnaround Intelligence Optimizer", "suite": "maintenance", "aliases": ["shutdown optimizer", "turnaround recovery optimizer", "shutdown planning"], "purpose": "Create a resource- and dependency-constrained task schedule with hard permit and inspection gates.", "input": "work packages, dependencies, resource skills/capacity, permit, SIMOPS and inspection state", "method": "Deterministic earliest-feasible list schedule; infeasible tasks remain unscheduled."},
    {"tool_code": "II-005", "id": "data-trust", "name": "Industrial Data Trust and Measurement Reconciliation Engine", "suite": "engineering", "aliases": ["measurement reconciliation", "data confidence map", "industrial data trust"], "purpose": "Flag missing, conflicting and out-of-tolerance measurements without overwriting source values.", "input": "measurements with IDs, units, source, timestamps and optional balance streams", "method": "Explicit unit-group checks, same-meter conflict checks and balance residuals."},
    {"tool_code": "II-006", "id": "asset-reliability", "name": "Asset Reliability Mission Board", "suite": "maintenance", "aliases": ["asset reliability", "reliability mission board", "failure to production impact"], "purpose": "Rank supplied asset histories and expose documented production dependencies.", "input": "asset criticality, failure/downtime history and explicit dependency edges", "method": "Transparent heuristic ranking; no failure date or RUL claim."},
    {"tool_code": "II-007", "id": "yield-intelligence", "name": "Production Yield and Process Variability Intelligence", "suite": "production", "aliases": ["yield loss autopsy", "process variability", "production yield"], "purpose": "Calculate first-pass yield, final yield, rework and scrap from a documented production denominator.", "input": "input units, first-pass good units, recovered rework units and scrap units", "method": "Reconciled unit-count ratios; no inferred root cause."},
    {"tool_code": "II-008", "id": "commissioning", "name": "New Factory Commissioning and Production Ramp-up Intelligence", "suite": "maintenance", "aliases": ["digital commissioning dossier", "factory commissioning", "ramp up readiness"], "purpose": "Evaluate system readiness against required tests, evidence and approvals.", "input": "equipment/system identity and required commissioning checks", "method": "Fail-closed checklist gate; missing required evidence blocks readiness."},
    {"tool_code": "II-009", "id": "experimentation", "name": "Industrial Experimentation and Process Improvement Laboratory", "suite": "engineering", "aliases": ["engineering experiment vault", "DOE laboratory", "process improvement lab"], "purpose": "Generate a full two-level design or analyze supplied coded factorial runs reproducibly.", "input": "factor names and optional complete -1/+1 runs with numeric response", "method": "Deterministic factorial design and least-squares effects; randomized run order is not assumed."},
    {"tool_code": "II-010", "id": "procurement-assurance", "name": "Technical Procurement and Supplier Engineering Assurance", "suite": "supply", "aliases": ["technical bid evaluation", "supplier engineering assurance", "specification to offer"], "purpose": "Compare supplier claims against exact requirements and evidence references.", "input": "requirements and supplier offer claim records", "method": "Explicit compliance classification; missing proof remains unverified."},
    {"tool_code": "II-011", "id": "energy-flexibility", "name": "Industrial Energy Flexibility and Peak-Demand Optimizer", "suite": "enterprise", "aliases": ["energy flexibility envelope", "peak demand optimizer", "load shifting"], "purpose": "Place flexible loads into allowed periods under demand capacity and production windows.", "input": "time periods, tariffs, capacity and flexible loads with permitted windows", "method": "Deterministic least-cost assignment; no live tariff or plant control."},
    {"tool_code": "II-012", "id": "spare-parts", "name": "Critical Spare Parts and Multi-Site Inventory Intelligence", "suite": "supply", "aliases": ["spare parts dependency twin", "critical spares", "multi site inventory"], "purpose": "Evaluate proposed stock transfers against compatibility, source minimums and destination needs.", "input": "part identity, site stock/minimums, compatibility and proposed transfer", "method": "Hard inventory constraints; unsafe transfers are rejected."},
    {"tool_code": "II-013", "id": "ot-assurance", "name": "Industrial OT Asset and Configuration Assurance", "suite": "enterprise", "aliases": ["OT configuration change watch", "OT inventory", "industrial OT assurance"], "purpose": "Compare approved OT configuration baselines with manually supplied or authorized inventory evidence.", "input": "asset ID, approved baseline and observed configuration snapshots", "method": "Passive record diff only; no network scanning or device writes."},
    {"tool_code": "II-014", "id": "batch-genealogy", "name": "Product and Batch Genealogy Intelligence", "suite": "production", "aliases": ["batch genealogy", "product traceability", "defect to source"], "purpose": "Trace confirmed parent-child lot links forward and backward while keeping suspected links separate.", "input": "lot relationship edges and a start lot", "method": "Directed graph traversal; only configured confirmed links form confirmed genealogy."},
    {"tool_code": "II-015", "id": "shift-handover", "name": "Intelligent Shift Handover and Operational Learning", "suite": "operations", "aliases": ["shift handover", "recurring problem memory", "shift management"], "purpose": "Carry unresolved work into a following shift with explicit owner and acknowledgement.", "input": "outstanding issues/actions and outgoing/incoming shift identities", "method": "Status/ownership validation; similar issue text is not proof of common cause."},
    {"tool_code": "II-016", "id": "benchmarking", "name": "Industrial Benchmarking and Improvement Radar", "suite": "enterprise", "aliases": ["improvement radar", "industrial benchmarking", "next best improvement"], "purpose": "Compare explicitly comparable KPIs and flag incompatible units, periods or denominators.", "input": "metric, unit, period, value and optional output/operating-hour denominator", "method": "Transparent per-unit/per-hour normalization; incomparable records are not ranked."},
]

SHARED_CAPABILITIES = [
    {"id": "cause-effect", "name": "Industrial Cause-and-Effect Intelligence", "purpose": "Evidence-linked observations, temporal relationships, candidate mechanisms and counter-evidence; correlation alone never confirms causality."},
    {"id": "risk-barrier", "name": "Industrial Risk and Barrier Assurance", "purpose": "Risk register, barrier owners, inspection evidence, overdue controls and residual-risk screening; not formal process-safety approval."},
    {"id": "knowledge-graph", "name": "Engineering Knowledge Graph", "purpose": "Permission-scoped entities and directed relationships across facilities, assets, processes, materials, events, models and decisions."},
    {"id": "action-management", "name": "Industrial Decision and Action Management", "purpose": "Owned actions, due dates, role-aware approval, evidence and independent completion verification."},
    {"id": "benefits", "name": "Industrial Investment and Benefits Realization", "purpose": "Separate forecast, target, actual and independently reviewed benefit records."},
    {"id": "model-registry", "name": "Engineering Model Validation and Registry", "purpose": "Immutable version hashes, assumptions, test cases and authorized validation state."},
    {"id": "event-intelligence", "name": "Operational Event Intelligence", "purpose": "Common provenance-bearing event timeline linked to canonical entities."},
    {"id": "knowledge-copilot", "name": "Industrial Knowledge Copilot", "purpose": "Permission-checked evidence retrieval with record citations and explicit evidence gaps; no autonomous approvals."},
]

INDUSTRY_TEMPLATES = {
    "Oil, Gas and Petrochemicals": {"focus": ["turnaround", "asset-reliability", "engineering-change", "data-trust", "energy-flexibility", "procurement-assurance", "commissioning"], "kpis": ["availability", "unplanned downtime", "energy intensity", "flare/loss balance", "turnaround duration"], "warning": "Configure site process-safety, permit, MOC and unit-specific engineering standards before operational use."},
    "Mining and Minerals": {"focus": ["asset-reliability", "yield-intelligence", "data-trust", "spare-parts", "energy-flexibility", "benchmarking"], "kpis": ["recovery yield", "availability", "water intensity", "energy per tonne", "maintenance backlog"], "warning": "Configure ore, geometallurgical, water and mobile-equipment measurement boundaries."},
    "Steel, Aluminium and Metals": {"focus": ["yield-intelligence", "energy-flexibility", "data-trust", "asset-reliability", "benchmarking", "engineering-change"], "kpis": ["yield", "scrap rate", "energy per tonne", "equipment availability", "peak demand"], "warning": "Configure heat, batch, furnace and alloy-specific process constraints."},
    "Food and Manufacturing": {"focus": ["batch-genealogy", "yield-intelligence", "commissioning", "shift-handover", "procurement-assurance", "data-trust"], "kpis": ["first-pass yield", "traceability coverage", "waste rate", "line availability", "supplier compliance"], "warning": "Configure product-specific quality, allergen, hygiene and statutory traceability controls."},
    "Water and Utilities": {"focus": ["data-trust", "energy-flexibility", "asset-reliability", "engineering-change", "benchmarking", "ot-assurance"], "kpis": ["water balance closure", "kWh/m3", "non-revenue water", "pump availability", "treatment yield"], "warning": "Configure water chemistry, metrology, regulatory sample and operational safety requirements."},
}

THREAD_NODE_TYPES = {
    "mission-control": "Event",
    "process-mining": "Process",
    "engineering-change": "Decision",
    "turnaround": "WorkPackage",
    "data-trust": "Dataset",
    "asset-reliability": "Asset",
    "yield-intelligence": "Quality",
    "commissioning": "Equipment",
    "experimentation": "Experiment",
    "procurement-assurance": "Supplier",
    "energy-flexibility": "Energy",
    "spare-parts": "Material",
    "ot-assurance": "Equipment",
    "batch-genealogy": "Batch",
    "shift-handover": "Event",
    "benchmarking": "KPI",
}

class IndustrialIntelligenceError(ValueError):
    """Input or workflow state does not satisfy an industrial contract."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _finite(value: Any, label: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise IndustrialIntelligenceError(f"{label} must be a finite number, not a boolean.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise IndustrialIntelligenceError(f"{label} must be a finite number.") from exc
    if not math.isfinite(number):
        raise IndustrialIntelligenceError(f"{label} must be a finite number.")
    if minimum is not None and number < minimum:
        raise IndustrialIntelligenceError(f"{label} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise IndustrialIntelligenceError(f"{label} must be at most {maximum}.")
    return number


def _required_text(value: Any, label: str, max_length: int = 240) -> str:
    text = str(value or "").strip()
    if not text:
        raise IndustrialIntelligenceError(f"{label} is required.")
    if len(text) > max_length:
        raise IndustrialIntelligenceError(f"{label} exceeds {max_length} characters.")
    return text


def _provenance(value: Any) -> str:
    label = str(value or "MANUAL").strip().upper()
    if label not in PROVENANCE:
        raise IndustrialIntelligenceError(f"Unsupported provenance {label!r}.")
    return label


def _iso_timestamp(value: Any, label: str = "timestamp") -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except Exception as exc:
        raise IndustrialIntelligenceError(f"{label} is not a valid timestamp.") from exc
    if pd.isna(timestamp):
        raise IndustrialIntelligenceError(f"{label} is missing.")
    if timestamp.tzinfo is None:
        raise IndustrialIntelligenceError(f"{label} must include a timezone offset.")
    return timestamp.tz_convert("UTC")


def _json_safe(value: Any, depth: int = 0) -> Any:
    if depth > 24:
        raise IndustrialIntelligenceError("Record nesting exceeds the 24-level safety limit.")
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise IndustrialIntelligenceError("Record contains a non-finite number.")
        return value
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is None:
            raise IndustrialIntelligenceError("Naive timestamps cannot be stored as industrial evidence.")
        return value.tz_convert("UTC").isoformat()
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            label = _required_text(key, "record field name", 120)
            if label.casefold() in {"password", "token", "secret", "api_key", "authorization", "access_token", "refresh_token"}:
                raise IndustrialIntelligenceError(f"Sensitive field {label!r} cannot be stored in an industrial record.")
            result[label] = _json_safe(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        if len(value) > 10000:
            raise IndustrialIntelligenceError("Record arrays are limited to 10,000 items.")
        return [_json_safe(item, depth + 1) for item in value]
    raise IndustrialIntelligenceError(f"Unsupported record value type: {type(value).__name__}.")


def _hash_payload(payload: Any) -> str:
    raw = json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def search_tools(query: str, suite_id: str | None = None) -> list[dict[str, Any]]:
    term = str(query or "").strip().casefold()
    suite = str(suite_id or "").strip()
    results = []
    for item in TOOL_CATALOG:
        if suite and item["suite"] != suite:
            continue
        haystack = " ".join([item["tool_code"], item["id"], item["name"], item["purpose"], item["input"], item["method"], *item["aliases"]]).casefold()
        if not term or term in haystack:
            results.append(dict(item))
    return results


def tool_definition(tool_id: str) -> dict[str, Any]:
    requested = str(tool_id).strip()
    for item in TOOL_CATALOG:
        if item["id"] == requested or item["tool_code"] == requested.upper():
            return dict(item)
    raise IndustrialIntelligenceError(f"Unknown Industrial Intelligence tool: {tool_id!r}.")


def _process_mining(payload: Mapping[str, Any]) -> dict[str, Any]:
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise IndustrialIntelligenceError("Process Mining requires a non-empty events list.")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    normalized = []
    for index, row in enumerate(events, start=1):
        if not isinstance(row, Mapping):
            raise IndustrialIntelligenceError(f"Event row {index} must be an object.")
        case_id = _required_text(row.get("case_id"), f"events[{index}].case_id", 120)
        activity = _required_text(row.get("activity"), f"events[{index}].activity", 160)
        ts = _iso_timestamp(row.get("timestamp"), f"events[{index}].timestamp")
        item = dict(row)
        item["case_id"] = case_id
        item["activity"] = activity
        item["_ts"] = ts
        normalized.append(item)
        grouped[case_id].append(item)
    total_elapsed = 0.0
    explicit_wait = 0.0
    inter_event = 0.0
    variants: dict[tuple[str, ...], int] = defaultdict(int)
    transitions: dict[tuple[str, str], int] = defaultdict(int)
    repeated = []
    deviations = []
    for case_id, rows in grouped.items():
        rows.sort(key=lambda item: item["_ts"])
        activities = tuple(item["activity"] for item in rows)
        variants[activities] += 1
        total_elapsed += max(0.0, (rows[-1]["_ts"] - rows[0]["_ts"]).total_seconds() / 60.0)
        seen = set()
        for activity in activities:
            if activity in seen:
                repeated.append({"case_id": case_id, "activity": activity, "classification": "REPEATED_ACTIVITY_CANDIDATE"})
            seen.add(activity)
        for left, right in zip(rows, rows[1:]):
            delta = max(0.0, (right["_ts"] - left["_ts"]).total_seconds() / 60.0)
            inter_event += delta
            transitions[(left["activity"], right["activity"])] += 1
            explicit_wait += _finite(right.get("explicit_wait_minutes", 0), f"event {case_id} explicit_wait_minutes", minimum=0)
        approved = payload.get("approved_sequence")
        if isinstance(approved, list) and approved and list(activities) != [str(item) for item in approved]:
            deviations.append({"case_id": case_id, "actual_sequence": list(activities), "approved_sequence": list(approved)})
    variant_rows = [{"variant": " → ".join(key), "cases": count} for key, count in sorted(variants.items(), key=lambda item: (-item[1], item[0]))]
    transition_rows = [{"from": key[0], "to": key[1], "occurrences": count} for key, count in sorted(transitions.items(), key=lambda item: (-item[1], item[0]))]
    return {
        "status": "EVENT_LOG_ANALYZED",
        "event_count": len(normalized),
        "case_count": len(grouped),
        "variant_count": len(variants),
        "median_case_elapsed_minutes": float(pd.Series([max(0.0, (sorted(rows, key=lambda r: r["_ts"])[-1]["_ts"] - sorted(rows, key=lambda r: r["_ts"])[0]["_ts"]).total_seconds() / 60.0) for rows in grouped.values()]).median()),
        "total_inter_event_elapsed_minutes": inter_event,
        "explicitly_recorded_wait_minutes": explicit_wait,
        "rework_candidates": repeated,
        "conformance_deviations": deviations,
        "variants": variant_rows,
        "directly_follows": transition_rows,
        "limitations": ["Inter-event elapsed time is not automatically waiting time.", "Repeated activities are candidates for review, not proven rework.", "Correlation and sequence deviation do not establish root cause."],
    }


def _engineering_change(payload: Mapping[str, Any]) -> dict[str, Any]:
    change = _required_text(payload.get("change_title"), "change_title")
    source = _required_text(payload.get("source_entity_id"), "source_entity_id", 160)
    edges = payload.get("dependencies", [])
    if not isinstance(edges, list):
        raise IndustrialIntelligenceError("dependencies must be a list of source_id/target_id objects.")
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for index, edge in enumerate(edges, start=1):
        if not isinstance(edge, Mapping):
            raise IndustrialIntelligenceError(f"dependency {index} must be an object.")
        src = _required_text(edge.get("source_id"), f"dependency {index} source_id", 160)
        dst = _required_text(edge.get("target_id"), f"dependency {index} target_id", 160)
        relation = str(edge.get("relation") or "DEPENDS_ON")[:160]
        adjacency[src].append((dst, relation))
    visited = {source}
    queue = deque([(source, 0)])
    impact = []
    while queue:
        current, depth = queue.popleft()
        if depth >= 50:
            raise IndustrialIntelligenceError("Dependency depth exceeds 50; inspect the graph for cycles or excessive scope.")
        for target, relation in adjacency.get(current, []):
            if target in visited:
                continue
            visited.add(target)
            impact.append({"entity_id": target, "depth": depth + 1, "relationship": relation})
            queue.append((target, depth + 1))
    checks = payload.get("required_reviews", [])
    if not isinstance(checks, list):
        raise IndustrialIntelligenceError("required_reviews must be a list.")
    return {
        "status": "IMPACT_ASSESSMENT_DRAFT",
        "change_title": change,
        "source_entity_id": source,
        "direct_impacts": [item for item in impact if item["depth"] == 1],
        "downstream_impacts": [item for item in impact if item["depth"] > 1],
        "required_reviews": [_json_safe(item) for item in checks],
        "approval_state": "PENDING_REVIEW",
        "limitations": ["Only explicitly supplied dependency edges are traversed.", "This assessment does not approve or implement the change."],
    }


def _turnaround(payload: Mapping[str, Any]) -> dict[str, Any]:
    tasks = payload.get("tasks")
    resources = payload.get("resources")
    if not isinstance(tasks, list) or not tasks:
        raise IndustrialIntelligenceError("Turnaround requires a non-empty tasks list.")
    if not isinstance(resources, list) or not resources:
        raise IndustrialIntelligenceError("Turnaround requires explicit qualified resources.")
    resource_map: dict[str, list[str]] = defaultdict(list)
    resource_state: dict[str, dict[str, Any]] = {}
    for index, resource in enumerate(resources, start=1):
        if not isinstance(resource, Mapping):
            raise IndustrialIntelligenceError("Each resource must be an object.")
        resource_id = _required_text(resource.get("id"), f"resource {index} id")
        if resource_id in resource_state:
            raise IndustrialIntelligenceError(f"Duplicate resource ID: {resource_id}.")
        skills = resource.get("skills", [])
        if not isinstance(skills, list) or not skills:
            raise IndustrialIntelligenceError("Each resource must have at least one qualified skill.")
        normalized_skills = {_required_text(skill, f"resource {resource_id} skill", 100).casefold() for skill in skills}
        resource_state[resource_id] = {"available_at": _finite(resource.get("available_from_hour", 0), f"resource {resource_id} available_from_hour", minimum=0), "skills": normalized_skills}
        for skill in normalized_skills:
            resource_map[skill].append(resource_id)
    by_id = {}
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, Mapping):
            raise IndustrialIntelligenceError(f"Task {index} must be an object.")
        task_id = _required_text(task.get("task_id"), f"task {index} task_id", 120)
        if task_id in by_id:
            raise IndustrialIntelligenceError(f"Duplicate task_id: {task_id}.")
        by_id[task_id] = dict(task)
    for task_id, task in by_id.items():
        deps = task.get("dependencies", [])
        if not isinstance(deps, list):
            raise IndustrialIntelligenceError(f"Task {task_id} dependencies must be a list.")
        unknown = sorted(set(map(str, deps)) - set(by_id))
        if unknown:
            raise IndustrialIntelligenceError(f"Task {task_id} references unknown dependencies: {unknown}.")
    indegree = {task_id: 0 for task_id in by_id}
    successors: dict[str, list[str]] = defaultdict(list)
    for task_id, task in by_id.items():
        for dep in task.get("dependencies", []):
            indegree[task_id] += 1
            successors[str(dep)].append(task_id)
    ready = deque(sorted(task_id for task_id, degree in indegree.items() if degree == 0))
    order = []
    while ready:
        task_id = ready.popleft()
        order.append(task_id)
        for successor in sorted(successors.get(task_id, [])):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
    if len(order) != len(by_id):
        return {"status": "INFEASIBLE", "reason": "Dependency cycle detected.", "scheduled_tasks": [], "unscheduled_tasks": sorted(set(by_id) - set(order))}
    result_by_id = {}
    scheduled = []
    unscheduled = []
    for task_id in order:
        task = by_id[task_id]
        if bool(task.get("safety_hold")):
            unscheduled.append({"task_id": task_id, "reason": "Safety hold is active."})
            continue
        if bool(task.get("permit_required")) and str(task.get("permit_status", "")).upper() != "APPROVED":
            unscheduled.append({"task_id": task_id, "reason": "Required permit is not approved."})
            continue
        if bool(task.get("inspection_required")) and str(task.get("inspection_status", "")).upper() != "PASSED":
            unscheduled.append({"task_id": task_id, "reason": "Required inspection is not passed."})
            continue
        if str(task.get("simops_status", "CLEAR")).upper() not in {"CLEAR", "APPROVED"}:
            unscheduled.append({"task_id": task_id, "reason": "SIMOPS restriction is not cleared."})
            continue
        skill = _required_text(task.get("skill"), f"Task {task_id} skill").casefold()
        options = resource_map.get(skill, [])
        if not options:
            unscheduled.append({"task_id": task_id, "reason": f"No qualified resource is configured for skill {skill}."})
            continue
        duration = _finite(task.get("duration_hours"), f"Task {task_id} duration_hours", minimum=0.000001)
        blocked_dependencies = [str(dep) for dep in task.get("dependencies", []) if str(dep) not in result_by_id]
        if blocked_dependencies:
            unscheduled.append({"task_id": task_id, "reason": "A prerequisite task is not schedulable.", "blocked_dependencies": blocked_dependencies})
            continue
        dependency_finish = max((result_by_id[str(dep)]["finish_hour"] for dep in task.get("dependencies", [])), default=0.0)
        resource_id = min(options, key=lambda rid: (max(resource_state[rid]["available_at"], dependency_finish), rid))
        resource = resource_state[resource_id]
        start = max(resource["available_at"], dependency_finish, _finite(task.get("earliest_start_hour", 0), f"Task {task_id} earliest_start_hour", minimum=0))
        finish = start + duration
        resource["available_at"] = finish
        row = {"task_id": task_id, "resource_id": resource_id, "start_hour": start, "finish_hour": finish, "duration_hours": duration, "status": "SCHEDULED"}
        scheduled.append(row)
        result_by_id[task_id] = row
    makespan = max((row["finish_hour"] for row in scheduled), default=0.0)
    return {
        "status": "FEASIBLE" if not unscheduled else "INFEASIBLE",
        "scheduled_tasks": scheduled,
        "unscheduled_tasks": unscheduled,
        "makespan_hours": makespan if not unscheduled else None,
        "schedule_basis": "Earliest feasible start under supplied precedence, skill, resource, permit, inspection and SIMOPS constraints.",
        "limitations": ["No shift calendars, work/rest rules, weather, crane envelopes or site-specific SIMOPS model are inferred.", "An optimizer schedule is not a permit or safety authorization."],
    }


def _data_trust(payload: Mapping[str, Any]) -> dict[str, Any]:
    measurements = payload.get("measurements")
    if not isinstance(measurements, list) or not measurements:
        raise IndustrialIntelligenceError("Data Trust requires a non-empty measurements list.")
    originals = []
    by_meter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, item in enumerate(measurements, start=1):
        if not isinstance(item, Mapping):
            raise IndustrialIntelligenceError(f"Measurement {index} must be an object.")
        meter = _required_text(item.get("meter_id"), f"measurement {index} meter_id")
        value = _finite(item.get("value"), f"measurement {index} value")
        unit = _required_text(item.get("unit"), f"measurement {index} unit", 40)
        source = _required_text(item.get("source"), f"measurement {index} source")
        ts = _iso_timestamp(item.get("timestamp"), f"measurement {index} timestamp").isoformat()
        row = {"meter_id": meter, "value": value, "unit": unit, "source": source, "timestamp": ts, "provenance": _provenance(item.get("provenance"))}
        originals.append(row)
        by_meter[meter].append(row)
    conflicts = []
    for meter, rows in by_meter.items():
        units = {row["unit"] for row in rows}
        if len(units) > 1:
            conflicts.append({"meter_id": meter, "reason": "UNIT_CONFLICT", "units": sorted(units)})
        elif len(rows) > 1:
            values = [row["value"] for row in rows]
            tolerance = _finite(payload.get("meter_conflict_tolerance_pct", 1.0), "meter_conflict_tolerance_pct", minimum=0)
            mean = sum(values) / len(values)
            spread = (max(values) - min(values)) / max(abs(mean), 1e-12) * 100.0
            if spread > tolerance:
                conflicts.append({"meter_id": meter, "reason": "CONFLICTING_READINGS", "spread_pct": spread, "tolerance_pct": tolerance})
    balances = []
    for index, stream in enumerate(payload.get("balances", []), start=1):
        if not isinstance(stream, Mapping):
            raise IndustrialIntelligenceError(f"Balance {index} must be an object.")
        incoming = _finite(stream.get("input"), f"balance {index} input", minimum=0)
        outgoing = _finite(stream.get("output"), f"balance {index} output", minimum=0)
        losses = _finite(stream.get("losses", 0), f"balance {index} losses", minimum=0)
        tolerance = _finite(stream.get("tolerance", 0), f"balance {index} tolerance", minimum=0)
        residual = incoming - outgoing - losses
        balances.append({"name": str(stream.get("name") or f"Balance {index}"), "unit": _required_text(stream.get("unit"), f"balance {index} unit"), "input": incoming, "output": outgoing, "losses": losses, "residual": residual, "tolerance": tolerance, "closes": abs(residual) <= tolerance})
    return {
        "status": "REVIEW_REQUIRED" if conflicts or any(not row["closes"] for row in balances) else "NO_CONFIGURED_CONFLICTS_DETECTED",
        "original_measurements": originals,
        "meter_conflicts": conflicts,
        "balances": balances,
        "originals_modified": False,
        "limitations": ["No original value is overwritten or averaged.", "No unit conversion, sensor calibration or uncertainty model is inferred.", "Absence of detected conflicts does not prove instrument calibration or overall data fitness."],
    }


def _asset_reliability(payload: Mapping[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets")
    if not isinstance(assets, list) or not assets:
        raise IndustrialIntelligenceError("Asset Reliability requires an assets list.")
    rows = []
    for index, asset in enumerate(assets, start=1):
        if not isinstance(asset, Mapping):
            raise IndustrialIntelligenceError(f"Asset {index} must be an object.")
        asset_id = _required_text(asset.get("asset_id"), f"asset {index} asset_id")
        criticality = _finite(asset.get("criticality", 3), f"{asset_id} criticality", minimum=1, maximum=5)
        failures = _finite(asset.get("failure_count", 0), f"{asset_id} failure_count", minimum=0)
        downtime = _finite(asset.get("downtime_hours", 0), f"{asset_id} downtime_hours", minimum=0)
        production = _finite(asset.get("production_impact_score", 1), f"{asset_id} production_impact_score", minimum=0, maximum=5)
        safety = 5.0 if bool(asset.get("safety_critical")) else 0.0
        score = min(100.0, criticality * 8.0 + min(failures, 10) * 2.0 + min(downtime, 100) * 0.2 + production * 4.0 + safety)
        rows.append({"asset_id": asset_id, "priority_score": round(score, 2), "criticality": criticality, "failure_count": failures, "downtime_hours": downtime, "production_impact_score": production, "safety_critical": bool(asset.get("safety_critical")), "evidence_status": "USER_SUPPLIED_HISTORY"})
    rows.sort(key=lambda item: (-item["priority_score"], item["asset_id"]))
    edges = payload.get("dependencies", [])
    dependencies = []
    for item in edges:
        if not isinstance(item, Mapping):
            raise IndustrialIntelligenceError("Asset dependencies must be objects.")
        dependencies.append({"asset_id": _required_text(item.get("asset_id"), "dependency asset_id"), "affected_entity_id": _required_text(item.get("affected_entity_id"), "dependency affected_entity_id"), "impact": str(item.get("impact") or "UNSPECIFIED")})
    return {"status": "PRIORITIZED_FROM_SUPPLIED_HISTORY", "assets": rows, "production_dependencies": dependencies, "limitations": ["Priority scores are explicit heuristic rankings, not probability-of-failure estimates.", "No exact failure date or remaining-useful-life result is produced."]}


def _yield_intelligence(payload: Mapping[str, Any]) -> dict[str, Any]:
    incoming = _finite(payload.get("input_units"), "input_units", minimum=0.000001)
    first_pass = _finite(payload.get("first_pass_good_units"), "first_pass_good_units", minimum=0)
    rework = _finite(payload.get("rework_recovered_units", 0), "rework_recovered_units", minimum=0)
    scrap = _finite(payload.get("scrap_units", 0), "scrap_units", minimum=0)
    if first_pass + rework + scrap > incoming + 1e-9:
        raise IndustrialIntelligenceError("First-pass good + rework recovered + scrap cannot exceed input_units.")
    final_good = first_pass + rework
    return {
        "status": "YIELD_CALCULATED",
        "input_units": incoming,
        "first_pass_good_units": first_pass,
        "rework_recovered_units": rework,
        "scrap_units": scrap,
        "final_good_units": final_good,
        "first_pass_yield_pct": first_pass / incoming * 100.0,
        "final_yield_pct": final_good / incoming * 100.0,
        "rework_rate_pct": rework / incoming * 100.0,
        "scrap_rate_pct": scrap / incoming * 100.0,
        "unaccounted_units": incoming - first_pass - rework - scrap,
        "limitations": ["All quantities must use the same batch boundary and unit.", "No process cause is confirmed from yield arithmetic alone."],
    }


def _commissioning(payload: Mapping[str, Any]) -> dict[str, Any]:
    tests = payload.get("required_checks")
    if not isinstance(tests, list) or not tests:
        raise IndustrialIntelligenceError("Commissioning requires a non-empty required_checks list.")
    missing = []
    failed = []
    passed = []
    for index, item in enumerate(tests, start=1):
        if not isinstance(item, Mapping):
            raise IndustrialIntelligenceError(f"Commissioning check {index} must be an object.")
        check_id = _required_text(item.get("check_id"), f"check {index} check_id")
        status = str(item.get("status") or "MISSING").upper()
        evidence = str(item.get("evidence_id") or "").strip()
        if status == "PASSED" and evidence:
            passed.append(check_id)
        elif status == "FAILED":
            failed.append({"check_id": check_id, "evidence_id": evidence or None})
        else:
            missing.append({"check_id": check_id, "status": status, "evidence_required": True})
    ready = not missing and not failed
    return {
        "status": "READY_FOR_AUTHORIZED_REVIEW" if ready else "NOT_READY",
        "readiness_approved": False,
        "passed_checks": passed,
        "missing_or_unverified_checks": missing,
        "failed_checks": failed,
        "required_check_count": len(tests),
        "passed_check_count": len(passed),
        "limitations": ["All tests require authorized acceptance and sign-off.", "This checklist does not replace statutory commissioning, permit or vendor acceptance procedures."],
    }


def _experimentation(payload: Mapping[str, Any]) -> dict[str, Any]:
    factors = payload.get("factors")
    if not isinstance(factors, list) or not 1 <= len(factors) <= 8:
        raise IndustrialIntelligenceError("Experimentation requires between 1 and 8 factor names.")
    names = [_required_text(item, "factor name", 80) for item in factors]
    if len(set(names)) != len(names):
        raise IndustrialIntelligenceError("Factor names must be unique.")
    runs = payload.get("runs")
    if runs is None:
        design = []
        for mask in range(2 ** len(names)):
            design.append({name: (1 if mask & (1 << index) else -1) for index, name in enumerate(names)})
        return {"status": "FACTORIAL_DESIGN_GENERATED", "design_type": "FULL_2_LEVEL_FACTORIAL", "factors": names, "run_count": len(design), "design": design, "limitations": ["Run order is not randomized.", "The design itself is not evidence of a process effect."]}
    if not isinstance(runs, list) or not runs:
        raise IndustrialIntelligenceError("runs must be omitted for design generation or supplied as a non-empty list.")
    response_col = str(payload.get("response_column") or "response")
    matrix = []
    responses = []
    for index, run in enumerate(runs, start=1):
        if not isinstance(run, Mapping):
            raise IndustrialIntelligenceError(f"Run {index} must be an object.")
        values = []
        for name in names:
            value = _finite(run.get(name), f"run {index} factor {name}", minimum=-1, maximum=1)
            if value not in {-1.0, 1.0}:
                raise IndustrialIntelligenceError(f"Run {index} factor {name} must be coded exactly -1 or +1.")
            values.append(value)
        matrix.append([1.0, *values])
        responses.append(_finite(run.get(response_col), f"run {index} response"))
    if len(runs) < len(names) + 2:
        raise IndustrialIntelligenceError("At least factors + 2 runs are required for an estimable first-order fit.")
    import numpy as np
    x = np.asarray(matrix, dtype=float)
    y = np.asarray(responses, dtype=float)
    coef, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    fitted = x @ coef
    residual = y - fitted
    ss_total = float(((y - y.mean()) ** 2).sum())
    ss_error = float((residual ** 2).sum())
    r2 = 1.0 - ss_error / ss_total if ss_total > 0 else None
    return {
        "status": "FACTORIAL_FIRST_ORDER_MODEL_FITTED" if rank == x.shape[1] else "DESIGN_RANK_DEFICIENT",
        "factors": names,
        "response_column": response_col,
        "run_count": len(runs),
        "coefficients": {"intercept": float(coef[0]), **{name: float(coef[i + 1]) for i, name in enumerate(names)}},
        "r_squared": r2,
        "residual_sum_squares": ss_error,
        "design_rank": int(rank),
        "input_hash": _hash_payload({"factors": names, "runs": runs, "response_column": response_col}),
        "limitations": ["This first-order fit omits interaction and curvature terms.", "No p-values or causal claims are produced.", "Randomization, blocking, replication and measurement-system adequacy require study design review."],
    }


def _procurement(payload: Mapping[str, Any]) -> dict[str, Any]:
    requirements = payload.get("requirements")
    offers = payload.get("offers")
    if not isinstance(requirements, list) or not requirements or not isinstance(offers, list) or not offers:
        raise IndustrialIntelligenceError("Procurement Assurance requires requirements and offers lists.")
    reqs = {}
    for item in requirements:
        if not isinstance(item, Mapping):
            raise IndustrialIntelligenceError("Each requirement must be an object.")
        rid = _required_text(item.get("requirement_id"), "requirement_id")
        reqs[rid] = dict(item)
    results = []
    for offer in offers:
        if not isinstance(offer, Mapping):
            raise IndustrialIntelligenceError("Each supplier offer must be an object.")
        supplier = _required_text(offer.get("supplier"), "supplier")
        claims = offer.get("claims", [])
        if not isinstance(claims, list):
            raise IndustrialIntelligenceError(f"{supplier} claims must be a list.")
        claim_by_id = {str(item.get("requirement_id")): item for item in claims if isinstance(item, Mapping)}
        rows = []
        complete = 0
        compliant = 0
        deviations = 0
        unverified = 0
        for rid, requirement in reqs.items():
            claim = claim_by_id.get(rid)
            if claim is None:
                state = "UNVERIFIED"
                unverified += 1
            else:
                declared = str(claim.get("compliance") or "UNVERIFIED").upper()
                evidence = str(claim.get("evidence_id") or "").strip()
                if declared == "COMPLIANT" and evidence:
                    state = "COMPLIANT"
                    compliant += 1
                    complete += 1
                elif declared == "NON_COMPLIANT":
                    state = "DEVIATION"
                    deviations += 1
                    complete += 1
                else:
                    state = "UNVERIFIED"
                    unverified += 1
            rows.append({"requirement_id": rid, "requirement": str(requirement.get("description") or ""), "status": state, "evidence_id": str(claim.get("evidence_id")) if claim and claim.get("evidence_id") else None})
        results.append({"supplier": supplier, "requirement_results": rows, "compliant_count": compliant, "deviation_count": deviations, "unverified_count": unverified, "review_completeness_pct": complete / len(reqs) * 100.0})
    return {"status": "TECHNICAL_BID_COMPARISON", "requirements_count": len(reqs), "supplier_results": results, "limitations": ["A supplier statement without a supporting evidence ID remains unverified.", "No technical compliance is inferred from price or marketing text."]}


def _energy_flexibility(payload: Mapping[str, Any]) -> dict[str, Any]:
    periods = payload.get("periods")
    loads = payload.get("loads")
    if not isinstance(periods, list) or not periods or not isinstance(loads, list):
        raise IndustrialIntelligenceError("Energy Flexibility requires periods and loads lists.")
    period_rows = {}
    for item in periods:
        if not isinstance(item, Mapping):
            raise IndustrialIntelligenceError("Each period must be an object.")
        period_id = _required_text(item.get("period_id"), "period_id")
        period_rows[period_id] = {"tariff": _finite(item.get("tariff"), f"{period_id} tariff", minimum=0), "capacity_kwh": _finite(item.get("capacity_kwh"), f"{period_id} capacity_kwh", minimum=0), "base_kwh": _finite(item.get("base_kwh", 0), f"{period_id} base_kwh", minimum=0), "scheduled_kwh": 0.0}
    allocations = []
    infeasible = []
    if any(not isinstance(item, Mapping) for item in loads):
        raise IndustrialIntelligenceError("Each load must be an object.")
    ordered_loads = sorted(loads, key=lambda item: (bool(item.get("flexible")), _required_text(item.get("load_id"), "load_id")))
    for load in ordered_loads:
        if not isinstance(load, Mapping):
            raise IndustrialIntelligenceError("Each load must be an object.")
        load_id = _required_text(load.get("load_id"), "load_id")
        energy = _finite(load.get("energy_kwh"), f"{load_id} energy_kwh", minimum=0)
        earliest = str(load.get("earliest_period") or "")
        latest = str(load.get("latest_period") or earliest)
        allowed = list(period_rows)
        if earliest and latest:
            start = list(period_rows).index(earliest) if earliest in period_rows else -1
            end = list(period_rows).index(latest) if latest in period_rows else -1
            if start < 0 or end < start:
                infeasible.append({"load_id": load_id, "reason": "Invalid allowed period window."})
                continue
            allowed = list(period_rows)[start:end + 1]
        if not bool(load.get("flexible")):
            allowed = [earliest] if earliest in period_rows else []
        candidates = []
        for period_id in allowed:
            period = period_rows[period_id]
            if period["base_kwh"] + period["scheduled_kwh"] + energy <= period["capacity_kwh"] + 1e-9:
                candidates.append((period["tariff"], period_id))
        if not candidates:
            infeasible.append({"load_id": load_id, "reason": "No allowed period has sufficient remaining capacity."})
            continue
        tariff, period_id = min(candidates)
        period_rows[period_id]["scheduled_kwh"] += energy
        allocations.append({"load_id": load_id, "period_id": period_id, "energy_kwh": energy, "tariff": tariff, "estimated_cost": energy * tariff, "flexible": bool(load.get("flexible"))})
    total_cost = sum(row["estimated_cost"] for row in allocations)
    return {"status": "FEASIBLE" if not infeasible else "INFEASIBLE", "allocations": allocations, "unallocated_loads": infeasible, "period_summary": [{"period_id": key, **value, "total_kwh": value["base_kwh"] + value["scheduled_kwh"]} for key, value in period_rows.items()], "modeled_energy_cost": total_cost if not infeasible else None, "limitations": ["Tariffs and load data are user-supplied.", "Only supplied period capacities and flexible windows are enforced.", "This is a planning result; it does not dispatch or control equipment."]}


def _spare_parts(payload: Mapping[str, Any]) -> dict[str, Any]:
    part = _required_text(payload.get("part_id"), "part_id")
    qty = _finite(payload.get("transfer_quantity"), "transfer_quantity", minimum=0.000001)
    source = payload.get("source")
    destination = payload.get("destination")
    if not isinstance(source, Mapping) or not isinstance(destination, Mapping):
        raise IndustrialIntelligenceError("Source and destination inventory objects are required.")
    compatible = payload.get("compatible") is True
    source_on = _finite(source.get("on_hand"), "source on_hand", minimum=0)
    source_min = _finite(source.get("minimum_stock"), "source minimum_stock", minimum=0)
    dest_on = _finite(destination.get("on_hand"), "destination on_hand", minimum=0)
    dest_max = payload.get("destination_maximum_stock")
    after_source = source_on - qty
    after_destination = dest_on + qty
    reasons = []
    if not compatible:
        reasons.append("Part compatibility has not been confirmed.")
    if after_source < source_min:
        reasons.append("Transfer would take the supplying facility below its configured minimum stock.")
    if dest_max is not None and after_destination > _finite(dest_max, "destination_maximum_stock", minimum=0):
        reasons.append("Transfer would exceed the destination maximum stock.")
    return {"status": "REJECTED" if reasons else "ELIGIBLE_FOR_APPROVAL", "part_id": part, "transfer_quantity": qty, "source_after_transfer": after_source, "source_minimum_stock": source_min, "destination_after_transfer": after_destination, "reasons": reasons, "transfer_approved": False, "limitations": ["No transfer is executed.", "Compatibility and inventory reservations must be verified against the authoritative inventory system."]}


def _ot_assurance(payload: Mapping[str, Any]) -> dict[str, Any]:
    asset_id = _required_text(payload.get("asset_id"), "asset_id")
    baseline = payload.get("approved_baseline")
    observed = payload.get("observed_configuration")
    if not isinstance(baseline, Mapping) or not isinstance(observed, Mapping):
        raise IndustrialIntelligenceError("approved_baseline and observed_configuration must be objects.")
    changes = []
    keys = sorted(set(baseline) | set(observed))
    for key in keys:
        if baseline.get(key) != observed.get(key):
            changes.append({"field": str(key), "approved_value": baseline.get(key), "observed_value": observed.get(key), "status": "UNDOCUMENTED_DIFFERENCE"})
    return {"status": "INVESTIGATION_REQUIRED" if changes else "NO_DIFFERENCE_IN_SUPPLIED_SNAPSHOT", "asset_id": asset_id, "differences": changes, "difference_count": len(changes), "observed_provenance": _provenance(payload.get("observed_provenance", "IMPORTED")), "limitations": ["Passive record comparison only; no active discovery, network scan or device modification is performed.", "A clean snapshot comparison does not prove live OT integrity."]}


def _genealogy(payload: Mapping[str, Any]) -> dict[str, Any]:
    edges = payload.get("genealogy")
    start = _required_text(payload.get("lot_id"), "lot_id")
    direction = str(payload.get("direction") or "backward").casefold()
    if direction not in {"backward", "forward"}:
        raise IndustrialIntelligenceError("direction must be backward or forward.")
    if not isinstance(edges, list):
        raise IndustrialIntelligenceError("genealogy must be a list.")
    adjacency: dict[str, list[str]] = defaultdict(list)
    excluded = []
    for index, item in enumerate(edges, start=1):
        if not isinstance(item, Mapping):
            raise IndustrialIntelligenceError(f"Genealogy edge {index} must be an object.")
        parent = _required_text(item.get("parent_lot"), f"genealogy {index} parent_lot")
        child = _required_text(item.get("child_lot"), f"genealogy {index} child_lot")
        if str(item.get("status") or "SUSPECTED").upper() != "CONFIRMED":
            excluded.append({"parent_lot": parent, "child_lot": child, "status": str(item.get("status") or "SUSPECTED")})
            continue
        if direction == "backward":
            adjacency[child].append(parent)
        else:
            adjacency[parent].append(child)
    visited = {start}
    queue = deque([start])
    traced = []
    while queue:
        current = queue.popleft()
        for next_lot in sorted(adjacency.get(current, [])):
            if next_lot not in visited:
                visited.add(next_lot)
                traced.append(next_lot)
                queue.append(next_lot)
    return {"status": "GENEALOGY_TRACE_COMPLETE", "start_lot": start, "direction": direction, "confirmed_related_lots": traced, "suspected_links_excluded": excluded, "limitations": ["Only supplied CONFIRMED genealogy edges are traversed.", "Suspected contributors are listed separately and are not treated as confirmed genealogy."]}


def _shift_handover(payload: Mapping[str, Any]) -> dict[str, Any]:
    outgoing = _required_text(payload.get("outgoing_shift"), "outgoing_shift")
    incoming = _required_text(payload.get("incoming_shift"), "incoming_shift")
    issues = payload.get("issues", [])
    if not isinstance(issues, list):
        raise IndustrialIntelligenceError("issues must be a list.")
    carried = []
    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, Mapping):
            raise IndustrialIntelligenceError(f"Issue {index} must be an object.")
        status = str(issue.get("status") or "OPEN").upper()
        if status not in {"CLOSED", "VERIFIED"}:
            carried.append({"issue_id": _required_text(issue.get("issue_id"), f"issue {index} issue_id"), "owner": str(issue.get("owner") or "").strip() or None, "status": status, "acknowledged_by_incoming": bool(issue.get("acknowledged_by_incoming", False)), "required_evidence": _json_safe(issue.get("evidence_refs", []))})
    unowned = [row["issue_id"] for row in carried if not row["owner"]]
    return {"status": "ACKNOWLEDGEMENT_REQUIRED" if carried else "NO_OPEN_ITEMS", "outgoing_shift": outgoing, "incoming_shift": incoming, "carried_forward": carried, "unowned_issue_ids": unowned, "handover_acknowledged": bool(carried) and all(row["acknowledged_by_incoming"] and row["owner"] for row in carried), "limitations": ["Similar issue descriptions do not prove common root cause.", "A carried item remains open until a separately verified closure." ]}


def _benchmarking(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("observations")
    if not isinstance(rows, list) or len(rows) < 2:
        raise IndustrialIntelligenceError("Benchmarking requires at least two observations.")
    parsed = []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, Mapping):
            raise IndustrialIntelligenceError(f"Observation {index} must be an object.")
        metric = _required_text(item.get("metric"), f"observation {index} metric")
        unit = _required_text(item.get("unit"), f"observation {index} unit", 40)
        period = _required_text(item.get("period"), f"observation {index} period", 80)
        value = _finite(item.get("value"), f"observation {index} value")
        denominator = item.get("denominator")
        denominator_name = str(item.get("denominator_name") or "").strip()
        normalized = value
        if denominator is not None:
            d = _finite(denominator, f"observation {index} denominator", minimum=0.000001)
            denominator_name = _required_text(denominator_name, f"observation {index} denominator_name")
            normalized = value / d
        parsed.append({"name": str(item.get("name") or f"Observation {index}"), "metric": metric, "unit": unit, "period": period, "value": value, "denominator_name": denominator_name, "normalized_value": normalized})
    metric_set = {row["metric"] for row in parsed}
    unit_set = {row["unit"] for row in parsed}
    period_set = {row["period"] for row in parsed}
    denom_set = {row["denominator_name"] for row in parsed}
    comparable = len(metric_set) == 1 and len(unit_set) == 1 and len(period_set) == 1 and len(denom_set) == 1
    return {"status": "COMPARABLE" if comparable else "NOT_COMPARABLE", "observations": parsed if comparable else [], "comparison_suppressed": not comparable, "comparability_gaps": {"metrics": sorted(metric_set), "units": sorted(unit_set), "periods": sorted(period_set), "denominators": sorted(denom_set)}, "limitations": ["Normalization is only applied using explicitly supplied denominators.", "Incompatible metrics, units, periods or denominators are not ranked."]}


def _mission_control(payload: Mapping[str, Any]) -> dict[str, Any]:
    event_id = _required_text(payload.get("event_id"), "event_id")
    severity = _finite(payload.get("severity"), "severity", minimum=1, maximum=5)
    urgency = _finite(payload.get("urgency"), "urgency", minimum=1, maximum=5)
    operational_impact = _finite(payload.get("operational_impact_score", 1), "operational_impact_score", minimum=0, maximum=5)
    affected = payload.get("affected_domains", [])
    if not isinstance(affected, list):
        raise IndustrialIntelligenceError("affected_domains must be a list.")
    evidence = payload.get("evidence_refs", [])
    if not isinstance(evidence, list):
        raise IndustrialIntelligenceError("evidence_refs must be a list.")
    score = min(100.0, severity * 10.0 + urgency * 8.0 + operational_impact * 4.0 + min(len(set(map(str, affected))), 5) * 2.0)
    priority = "CRITICAL" if score >= 85 else "HIGH" if score >= 65 else "MEDIUM" if score >= 40 else "LOW"
    return {"status": "OPERATIONAL_EXCEPTION_RECORDED", "event_id": event_id, "triage_score": score, "priority": priority, "affected_domains": sorted(set(map(str, affected))), "evidence_refs": _json_safe(evidence), "cause_status": "NOT_CONFIRMED", "limitations": ["Priority is a transparent triage heuristic, not a safety or risk approval.", "Correlation between affected domains does not confirm root cause."]}


def analyze_tool(tool_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise IndustrialIntelligenceError("Tool input must be a JSON object.")
    engines = {
        "mission-control": _mission_control,
        "process-mining": _process_mining,
        "engineering-change": _engineering_change,
        "turnaround": _turnaround,
        "data-trust": _data_trust,
        "asset-reliability": _asset_reliability,
        "yield-intelligence": _yield_intelligence,
        "commissioning": _commissioning,
        "experimentation": _experimentation,
        "procurement-assurance": _procurement,
        "energy-flexibility": _energy_flexibility,
        "spare-parts": _spare_parts,
        "ot-assurance": _ot_assurance,
        "batch-genealogy": _genealogy,
        "shift-handover": _shift_handover,
        "benchmarking": _benchmarking,
    }
    definition = tool_definition(tool_id)
    canonical_id = definition["id"]
    result = engines[canonical_id](payload)
    result["tool_id"] = canonical_id
    result["tool_code"] = definition["tool_code"]
    result["tool_name"] = definition["name"]
    result["calculated_at"] = _utc_now()
    result["input_hash"] = _hash_payload(payload)
    result["model_version"] = "shoir-industrial-intelligence-core/1.0"
    return result


def _session_authorize(username: str, tier: str, action: str = "read") -> dict[str, Any]:
    from shoir_tier_capabilities import tier_allows
    actor = str(st.session_state.get("current_user") or "").strip()
    requested = str(username or "").strip()
    if st.session_state.get("authenticated") is not True or not actor or actor.casefold() in {"guest", "guest visitor", "anonymous"} or actor.casefold() != requested.casefold():
        raise PermissionError("An authenticated session matching the requested account is required.")
    if not tier_allows(str(tier or ""), "Enterprise"):
        raise PermissionError("Industrial Intelligence Suite requires the existing Enterprise capability level.")
    context = st.session_state.get("shoir_active_organization_workspace")
    if context is not None:
        if not isinstance(context, dict):
            raise PermissionError("The active organization workspace context is invalid.")
        organization_id = str(context.get("organization_id") or "").strip()
        workspace_id = str(context.get("organization_workspace_id") or "").strip()
        token = str(st.session_state.get("remote_session_token") or "").strip()
        if not organization_id or not workspace_id or not token:
            raise PermissionError("A valid managed organization workspace session is required.")
        import durable_account_store as account_store
        account_store.validate_remote_organization_workspace_access(actor)
        response = account_store.edge_organization_action("org_list_session", actor, token)
        organizations = response.get("organizations", [])
        membership = next((item for item in organizations if isinstance(item, dict) and str(item.get("organization_id")) == organization_id), None)
        if not membership or str(membership.get("status") or "").casefold() != "active":
            raise PermissionError("Active organization membership could not be verified.")
        role = str(membership.get("role") or "").casefold()
        scope = {"organization_id": organization_id, "workspace_id": workspace_id, "scope": "ORGANIZATION"}
    else:
        role = str(st.session_state.get("user_role") or "").casefold()
        scope = {"organization_id": None, "workspace_id": str(st.session_state.get("shoir_workspace_name") or st.session_state.get("workspace") or "personal"), "scope": "PERSONAL"}
    if not role:
        raise PermissionError("The current workspace role is missing; access is denied.")
    if scope["scope"] == "ORGANIZATION":
        read_roles = {"owner", "admin", "administrator", "enterprise admin", "engineer", "approver", "viewer"}
        write_roles = {"owner", "admin", "administrator", "enterprise admin", "engineer", "approver"}
        approve_roles = {"owner", "admin", "administrator", "enterprise admin", "approver"}
    else:
        # Personal workspaces retain the account roles used by the existing login
        # and subscription flows; organization writes use the stricter five-role map.
        read_roles = {"owner", "admin", "administrator", "enterprise admin", "engineer", "approver", "viewer", "manager", "planner", "user", "member"}
        write_roles = {"owner", "admin", "administrator", "enterprise admin", "engineer", "approver", "manager", "planner", "user", "member"}
        approve_roles = {"owner", "admin", "administrator", "enterprise admin", "approver"}
    if action == "read" and role not in read_roles:
        raise PermissionError("The current workspace role cannot read Industrial Intelligence records.")
    if action == "write" and role not in write_roles:
        raise PermissionError("The current workspace role is read-only.")
    if action == "approve" and role not in approve_roles:
        raise PermissionError("Only an organization Owner, Admin or Approver may approve this action.")
    return {"actor": actor, "role": role, **scope}


def _state_list(key: str) -> list[dict[str, Any]]:
    value = st.session_state.get(STATE_PREFIX + key, [])
    if not isinstance(value, list):
        return []
    context = st.session_state.get("shoir_active_organization_workspace")
    if isinstance(context, Mapping):
        organization_id = str(context.get("organization_id") or "").strip()
        workspace_id = str(context.get("organization_workspace_id") or "").strip()
        if not organization_id or not workspace_id:
            return []
        return [
            row for row in value
            if isinstance(row, Mapping)
            and str(row.get("organization_id") or "") == organization_id
            and str(row.get("workspace_id") or "") == workspace_id
        ]
    actor = str(st.session_state.get("current_user") or "").strip()
    workspace_id = str(st.session_state.get("shoir_workspace_name") or st.session_state.get("workspace") or "personal")
    return [
        row for row in value
        if isinstance(row, Mapping)
        and row.get("organization_id") is None
        and str(row.get("workspace_id") or "") == workspace_id
        and actor.casefold() in {
            str(row.get("created_by") or "").casefold(),
            str(row.get("owner") or "").casefold(),
            str(row.get("actor") or "").casefold(),
            str(row.get("reviewer") or "").casefold(),
        }
    ]


def _save_state_list(username: str, tier: str, key: str, rows: list[dict[str, Any]], action: str = "write") -> None:
    access = _session_authorize(username, tier, action)
    if len(rows) > MAX_RECORDS:
        raise IndustrialIntelligenceError(f"{key} exceeds the {MAX_RECORDS} record limit.")
    storage_key = STATE_PREFIX + key
    snapshot = copy.deepcopy(st.session_state.get(storage_key, []))
    if not isinstance(snapshot, list):
        snapshot = []
    # A managed workspace snapshot is tenant-scoped. Never carry records from a
    # different organization/workspace into the active organization's serialized
    # session payload. The previous workspace's copy remains durable in its own
    # remote snapshot and is restored when that workspace is opened again.
    if access["scope"] == "ORGANIZATION":
        scoped_rows = [
            item for item in rows
            if isinstance(item, Mapping)
            and str(item.get("organization_id") or "") == str(access["organization_id"])
            and str(item.get("workspace_id") or "") == str(access["workspace_id"])
        ]
    else:
        actor_fields = ("created_by", "owner", "actor", "reviewer")
        scoped_rows = [
            item for item in rows
            if isinstance(item, Mapping)
            and item.get("organization_id") is None
            and str(item.get("workspace_id") or "") == str(access["workspace_id"])
            and any(str(item.get(field) or "").casefold() == access["actor"].casefold() for field in actor_fields)
        ]
    if len(scoped_rows) > MAX_RECORDS:
        raise IndustrialIntelligenceError(f"{key} exceeds the {MAX_RECORDS} active-workspace record limit.")
    st.session_state[storage_key] = copy.deepcopy(scoped_rows)
    try:
        from workspace_persistence import save_user_workspace
        saved = save_user_workspace(username, st.session_state)
        if not saved:
            raise RuntimeError(str(st.session_state.get("_workspace_save_error") or "Workspace persistence did not confirm the save."))
        visual_key = VISUAL_STATE_KEYS.get(key)
        if visual_key:
            scoped_rows = _state_list(key)
            st.session_state[visual_key] = pd.DataFrame(copy.deepcopy(scoped_rows))
    except Exception:
        st.session_state[storage_key] = snapshot
        raise


def _require_evidence_refs(evidence_refs: Sequence[str], label: str) -> list[str]:
    if isinstance(evidence_refs, (str, bytes)) or not isinstance(evidence_refs, Sequence):
        raise IndustrialIntelligenceError(f"{label} evidence references must be a list of registered record IDs or source references.")
    refs = [_required_text(item, f"{label} evidence reference", 240) for item in evidence_refs]
    if not refs:
        raise IndustrialIntelligenceError(f"{label} requires at least one evidence reference.")
    records = _state_list("records")
    available = set()
    for record in records:
        record_id = str(record.get("record_id") or "").strip()
        source_ref = str(record.get("source_ref") or "").strip()
        if record_id:
            available.add(record_id)
        if source_ref:
            available.add(source_ref)
    missing = sorted(set(refs) - available)
    if missing:
        raise IndustrialIntelligenceError(
            f"{label} references evidence that is not registered in this workspace: {missing}. "
            "Register the source as an evidence record first."
        )
    return refs


def _append_audit(username: str, tier: str, event_type: str, record_id: str, payload: Mapping[str, Any]) -> str:
    access = _session_authorize(username, tier, "write")
    audits = list(_state_list("audit"))
    audit_id = "AUD-" + uuid.uuid4().hex[:12].upper()
    audits.append({
        "audit_id": audit_id,
        "event_type": str(event_type)[:120],
        "record_id": str(record_id)[:120],
        "actor": access["actor"],
        "role": access["role"],
        "organization_id": access["organization_id"],
        "workspace_id": access["workspace_id"],
        "created_at": _utc_now(),
        "payload_hash": _hash_payload(payload),
    })
    _save_state_list(username, tier, "audit", audits)
    return audit_id


def _sync_thread_node(username: str, tier: str, node_type: str, name: str, record_id: str, status: str, metadata: Mapping[str, Any]) -> str:
    access = _session_authorize(username, tier, "write")
    import shoir_digital_thread as thread
    thread.ensure_thread_state(username)
    organization_id = str(access["organization_id"] or "")
    workspace_id = str(access["workspace_id"] or "")
    scope_namespace = f"{organization_id or access['actor']}::{workspace_id}"
    node_id = thread._upsert_node(
        node_type,
        name,
        source=f"industrial-intelligence:{scope_namespace}:{record_id}",
        module=MODULE_NAME,
        status=status,
        metadata={
            "industrial_record_id": record_id,
            "organization_id": organization_id or None,
            "workspace_id": workspace_id,
            "workspace_scope": access["scope"],
            **_json_safe(metadata),
        },
        identity_key=f"{scope_namespace}:{record_id}",
    )
    return node_id


def create_record(
    username: str,
    tier: str,
    record_type: str,
    name: str,
    payload: Mapping[str, Any],
    provenance: str = "MANUAL",
    source_ref: str = "",
    entity_id: str = "",
) -> dict[str, Any]:
    access = _session_authorize(username, tier, "write")
    provenance_value = _provenance(provenance)
    body = _json_safe(payload)
    safe_source_ref = str(source_ref or "").strip()[:500]
    source_timestamp = str(body.get("source_timestamp") or "").strip()
    if provenance_value in {"LIVE", "IMPORTED", "STALE"} and not safe_source_ref:
        raise IndustrialIntelligenceError(f"{provenance_value} records require a source reference.")
    if provenance_value in {"LIVE", "STALE"} and not source_timestamp:
        raise IndustrialIntelligenceError(f"{provenance_value} records require an explicit source timestamp.")
    if source_timestamp:
        _iso_timestamp(source_timestamp, "source_timestamp")
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_RECORD_BYTES:
        raise IndustrialIntelligenceError(f"Record payload exceeds {MAX_RECORD_BYTES} bytes.")
    record_id = "IIR-" + uuid.uuid4().hex[:14].upper()
    created_at = _utc_now()
    record = {
        "record_id": record_id,
        "record_type": _required_text(record_type, "record_type", 100),
        "name": _required_text(name, "record name", 240),
        "payload": body,
        "payload_hash": hashlib.sha256(encoded).hexdigest(),
        "provenance": provenance_value,
        "provenance_limit": PROVENANCE_RELIABILITY[provenance_value],
        "source_ref": safe_source_ref or None,
        "source_timestamp": source_timestamp or None,
        "entity_id": str(entity_id or "").strip()[:160] or None,
        "organization_id": access["organization_id"],
        "workspace_id": access["workspace_id"],
        "workspace_scope": access["scope"],
        "created_by": access["actor"],
        "created_at": created_at,
        "record_status": "RECORDED",
    }
    rows = list(_state_list("records"))
    rows.append(record)
    _save_state_list(username, tier, "records", rows)
    node_type = str(body.get("thread_node_type") or "Dataset")
    node_id = _sync_thread_node(username, tier, node_type, record["name"], record_id, "Observed", {"record_type": record["record_type"], "provenance": provenance_value, "payload_hash": record["payload_hash"]})
    record["thread_node_id"] = node_id
    rows[-1] = record
    _save_state_list(username, tier, "records", rows)
    _append_audit(username, tier, "record.created", record_id, {"record_type": record["record_type"], "provenance": provenance_value, "payload_hash": record["payload_hash"]})
    return copy.deepcopy(record)


def send_analysis_to_workbook(
    username: str,
    tier: str,
    tool_id: str,
    inputs: Mapping[str, Any],
    result: Mapping[str, Any],
    provenance: str,
    source_ref: str = "",
) -> dict[str, Any]:
    """Save a result as a new sheet in the existing Industrial Workbook session.

    Existing sheets are never renamed or removed. On a new workbook, the
    platform's standard nine engineering tabs are initialized.
    """
    _session_authorize(username, tier, "write")
    from shoir_industrial_workbook import WORKBOOK_STATE_KEY, FORMULA_STATE_KEY

    tool = tool_definition(tool_id)
    saved_record = create_record(
        username,
        tier,
        "tool_analysis",
        tool["name"],
        {
            "tool_id": tool_id,
            "input": _json_safe(inputs),
            "result": _json_safe(result),
            "input_hash": _hash_payload(inputs),
            "result_hash": _hash_payload(result),
            "thread_node_type": THREAD_NODE_TYPES[tool_id],
        },
        provenance=provenance,
        source_ref=source_ref,
    )
    previous_book = st.session_state.get(WORKBOOK_STATE_KEY)
    previous_formulas = st.session_state.get(FORMULA_STATE_KEY)
    if previous_book is None:
        workbook = {
            name: pd.DataFrame()
            for name in (
                "Inputs", "Data", "Calculations", "KPIs", "Simulation",
                "Optimization", "Scenarios", "Decisions", "Dashboard",
            )
        }
    elif isinstance(previous_book, Mapping):
        workbook = {
            str(name): frame.copy(deep=True) if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)
            for name, frame in previous_book.items()
        }
    else:
        raise IndustrialIntelligenceError("The active Industrial Workbook state is not a workbook mapping.")
    suffix = str(saved_record["record_id"]).replace("IIR-", "")[:10].lower()
    sheet_name = f"II_{tool_id[:12]}_{suffix}"[:31]
    if sheet_name in workbook:
        raise IndustrialIntelligenceError("The generated workbook sheet name already exists; save the analysis again for a new record ID.")
    rows = []
    for section, values in (("Input", inputs), ("Result", result)):
        for field, value in values.items():
            rendered = (
                json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)
                if isinstance(value, (Mapping, list, tuple))
                else str(value)
            )
            rows.append({"Section": section, "Field": str(field), "Value": rendered})
    rows.extend([
        {"Section": "Governance", "Field": "Record ID", "Value": saved_record["record_id"]},
        {"Section": "Governance", "Field": "Tool ID", "Value": tool_id},
        {"Section": "Governance", "Field": "Provenance", "Value": _provenance(provenance)},
        {"Section": "Governance", "Field": "Source Reference", "Value": str(source_ref or "")},
        {"Section": "Governance", "Field": "Input Hash", "Value": saved_record["payload"]["input_hash"]},
        {"Section": "Governance", "Field": "Model Version", "Value": str(result.get("model_version") or "UNSPECIFIED")},
        {"Section": "Governance", "Field": "Independent Verification", "Value": "NOT_VERIFIED"},
    ])
    workbook[sheet_name] = pd.DataFrame(rows, columns=["Section", "Field", "Value"])
    formulas = dict(previous_formulas) if isinstance(previous_formulas, Mapping) else {}
    formulas[sheet_name] = {}
    st.session_state[WORKBOOK_STATE_KEY] = workbook
    st.session_state[FORMULA_STATE_KEY] = formulas
    try:
        from workspace_persistence import save_user_workspace
        if not save_user_workspace(username, st.session_state):
            raise RuntimeError(str(st.session_state.get("_workspace_save_error") or "Managed workspace did not confirm the Industrial Workbook update."))
    except Exception:
        if previous_book is None:
            st.session_state.pop(WORKBOOK_STATE_KEY, None)
        else:
            st.session_state[WORKBOOK_STATE_KEY] = previous_book
        if previous_formulas is None:
            st.session_state.pop(FORMULA_STATE_KEY, None)
        else:
            st.session_state[FORMULA_STATE_KEY] = previous_formulas
        raise
    _append_audit(username, tier, "workbook.analysis_handoff", saved_record["record_id"], {"tool_id": tool_id, "sheet_name": sheet_name})
    return {"record_id": saved_record["record_id"], "workbook_sheet": sheet_name, "workbook_sheet_count": len(workbook), "preserved_sheets": list(workbook)}


def list_records(username: str, tier: str, record_type: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    _session_authorize(username, tier, "read")
    if isinstance(limit, bool) or not 1 <= int(limit) <= 1000:
        raise IndustrialIntelligenceError("Record list limit must be between 1 and 1,000.")
    rows = list(_state_list("records"))
    if record_type:
        rows = [row for row in rows if row.get("record_type") == record_type]
    rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return copy.deepcopy(rows[:int(limit)])


def add_entity(username: str, tier: str, entity_type: str, entity_id: str, name: str, attributes: Mapping[str, Any], provenance: str = "MANUAL") -> dict[str, Any]:
    node_type = _required_text(entity_type, "entity_type", 80)
    business_id = _required_text(entity_id, "entity_id", 160)
    access = _session_authorize(username, tier, "write")
    existing = next((item for item in _state_list("nodes") if str(item.get("entity_id")) == business_id), None)
    if existing:
        raise IndustrialIntelligenceError(f"Entity {business_id} already exists; create a versioned change record instead of overwriting it.")
    attrs = _json_safe(attributes)
    provenance_value = _provenance(provenance)
    source_ref = str(attrs.get("source_ref") or "").strip()
    source_timestamp = str(attrs.get("source_timestamp") or "").strip()
    if provenance_value in {"LIVE", "IMPORTED", "STALE"} and not source_ref:
        raise IndustrialIntelligenceError(f"{provenance_value} entities require source_ref in attributes.")
    if provenance_value in {"LIVE", "STALE"} and not source_timestamp:
        raise IndustrialIntelligenceError(f"{provenance_value} entities require source_timestamp in attributes.")
    if source_timestamp:
        _iso_timestamp(source_timestamp, "entity source_timestamp")
    record = {
        "entity_id": business_id,
        "entity_type": node_type,
        "name": _required_text(name, "entity name", 180),
        "attributes": attrs,
        "source_ref": source_ref or None,
        "source_timestamp": source_timestamp or None,
        "provenance": provenance_value,
        "organization_id": access["organization_id"],
        "workspace_id": access["workspace_id"],
        "created_by": access["actor"],
        "created_at": _utc_now(),
    }
    nodes = list(_state_list("nodes"))
    nodes.append(record)
    _save_state_list(username, tier, "nodes", nodes)
    thread_id = _sync_thread_node(username, tier, node_type, record["name"], business_id, "Observed", {"entity_id": business_id, "provenance": record["provenance"], **attrs})
    record["thread_node_id"] = thread_id
    nodes[-1] = record
    _save_state_list(username, tier, "nodes", nodes)
    _append_audit(username, tier, "entity.created", business_id, {"entity_type": node_type, "provenance": record["provenance"]})
    return copy.deepcopy(record)


def add_relationship(username: str, tier: str, source_id: str, target_id: str, relation: str, status: str = "CONFIRMED", evidence_refs: Sequence[str] = ()) -> dict[str, Any]:
    access = _session_authorize(username, tier, "write")
    source = _required_text(source_id, "source_id", 160)
    target = _required_text(target_id, "target_id", 160)
    relation_name = _required_text(relation, "relation", 160)
    if source == target:
        raise IndustrialIntelligenceError("Self-referential relationships are not accepted.")
    nodes = {str(row.get("entity_id")): row for row in _state_list("nodes")}
    if source not in nodes or target not in nodes:
        raise IndustrialIntelligenceError("Both relationship endpoints must exist in the active workspace.")
    state = str(status or "CONFIRMED").upper()
    if state not in {"CONFIRMED", "SUSPECTED", "PROPOSED"}:
        raise IndustrialIntelligenceError("Relationship status must be CONFIRMED, SUSPECTED or PROPOSED.")
    refs = [_required_text(item, "evidence reference", 240) for item in evidence_refs]
    if state == "CONFIRMED":
        refs = _require_evidence_refs(refs, "A CONFIRMED relationship")
    edge_id = "IIE-" + hashlib.sha256(f"{source}|{target}|{relation_name}".encode("utf-8")).hexdigest()[:14].upper()
    edges = list(_state_list("edges"))
    existing = next((item for item in edges if item.get("edge_id") == edge_id), None)
    if existing:
        raise IndustrialIntelligenceError("This relationship already exists; use a new evidence revision rather than replacing it.")
    edge = {"edge_id": edge_id, "source_id": source, "target_id": target, "relation": relation_name, "status": state, "evidence_refs": refs, "created_by": access["actor"], "organization_id": access["organization_id"], "workspace_id": access["workspace_id"], "created_at": _utc_now()}
    edges.append(edge)
    _save_state_list(username, tier, "edges", edges)
    import shoir_digital_thread as thread
    thread.ensure_thread_state(username)
    thread._upsert_edge(nodes[source].get("thread_node_id", source), nodes[target].get("thread_node_id", target), relation_name, state, {"evidence_refs": refs, "industrial_edge_id": edge_id})
    from workspace_persistence import save_user_workspace
    if not save_user_workspace(username, st.session_state):
        edges.pop()
        _save_state_list(username, tier, "edges", edges)
        raise RuntimeError(str(st.session_state.get("_workspace_save_error") or "Digital Thread relationship persistence failed."))
    _append_audit(username, tier, "relationship.created", edge_id, edge)
    return copy.deepcopy(edge)


def create_operational_event(username: str, tier: str, event_type: str, description: str, entity_id: str = "", timestamp: str | None = None, provenance: str = "MANUAL", evidence_refs: Sequence[str] = (), source_ref: str = "") -> dict[str, Any]:
    _session_authorize(username, tier, "write")
    event_time = _iso_timestamp(timestamp, "event timestamp").isoformat() if timestamp else _utc_now()
    refs = [_required_text(item, "evidence reference", 240) for item in evidence_refs]
    if refs:
        refs = _require_evidence_refs(refs, "Operational event")
    event_payload = {"event_type": _required_text(event_type, "event_type"), "description": _required_text(description, "description", 4000), "entity_id": str(entity_id or "").strip(), "event_timestamp": event_time, "source_timestamp": event_time, "evidence_refs": refs, "thread_node_type": "Event"}
    event = create_record(username, tier, "operational_event", event_type, event_payload, provenance, source_ref=source_ref, entity_id=entity_id)
    events = list(_state_list("events"))
    events.append({**event, "event_timestamp": event_time})
    _save_state_list(username, tier, "events", events)
    _append_audit(username, tier, "event.recorded", event["record_id"], {"event_type": event_type, "event_timestamp": event_time, "evidence_refs": refs})
    return copy.deepcopy(event)


def create_action(username: str, tier: str, title: str, owner: str, due_date: str, priority: str, expected_result: str, evidence_refs: Sequence[str] = (), created_by: str | None = None, required_approvals: int = 1) -> dict[str, Any]:
    access = _session_authorize(username, tier, "write")
    due = _iso_timestamp(due_date, "action due_date").date().isoformat()
    if isinstance(required_approvals, bool) or not 1 <= int(required_approvals) <= 3:
        raise IndustrialIntelligenceError("required_approvals must be between 1 and 3.")
    refs = [_required_text(item, "evidence reference", 240) for item in evidence_refs]
    if refs:
        refs = _require_evidence_refs(refs, "Action")
    action_id = "IIA-" + uuid.uuid4().hex[:12].upper()
    row = {
        "action_id": action_id,
        "title": _required_text(title, "action title"),
        "owner": _required_text(owner, "action owner", 128),
        "due_date": due,
        "priority": str(priority or "MEDIUM").upper(),
        "expected_result": _required_text(expected_result, "expected_result", 2000),
        "evidence_refs": refs,
        "created_by": access["actor"],
        "role_at_creation": access["role"],
        "organization_id": access["organization_id"],
        "workspace_id": access["workspace_id"],
        "status": "PROPOSED",
        "required_approvals": int(required_approvals),
        "approvals": [],
        "actual_result": None,
        "verification": None,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    actions = list(_state_list("actions"))
    actions.append(row)
    _save_state_list(username, tier, "actions", actions)
    row["thread_node_id"] = _sync_thread_node(
        username, tier, "Action", row["title"], action_id, "Proposed",
        {"owner": row["owner"], "status": row["status"]},
    )
    actions[-1] = row
    _save_state_list(username, tier, "actions", actions)
    _append_audit(username, tier, "action.created", action_id, {"owner": row["owner"], "due_date": due, "priority": row["priority"]})
    return copy.deepcopy(row)


def approve_action(username: str, tier: str, action_id: str, comment: str = "") -> dict[str, Any]:
    access = _session_authorize(username, tier, "approve")
    actions = list(_state_list("actions"))
    action = next((item for item in actions if item.get("action_id") == str(action_id)), None)
    if not action:
        raise IndustrialIntelligenceError("Action does not exist in this workspace.")
    if action.get("status") not in {"PROPOSED", "PENDING_APPROVAL"}:
        raise IndustrialIntelligenceError("Only proposed actions can receive approval.")
    _require_evidence_refs(action.get("evidence_refs", []), "Action approval")
    if str(action.get("created_by", "")).casefold() == access["actor"].casefold():
        raise PermissionError("The action creator cannot approve their own action.")
    approvals = list(action.get("approvals", []))
    if any(str(item.get("approver", "")).casefold() == access["actor"].casefold() for item in approvals):
        raise IndustrialIntelligenceError("This approver has already approved the action.")
    approvals.append({"approver": access["actor"], "role": access["role"], "comment": str(comment or "")[:2000], "approved_at": _utc_now()})
    action["approvals"] = approvals
    action["status"] = "APPROVED" if len(approvals) >= int(action.get("required_approvals", 1)) else "PENDING_APPROVAL"
    action["updated_at"] = _utc_now()
    index = actions.index(next(item for item in actions if item.get("action_id") == str(action_id)))
    actions[index] = action
    _save_state_list(username, tier, "actions", actions, action="approve")
    _sync_thread_node(username, tier, "Action", action["title"], action_id, action["status"].title(), {"owner": action["owner"], "status": action["status"], "approval_count": len(approvals), "organization_id": access["organization_id"], "workspace_id": access["workspace_id"]})
    _append_audit(username, tier, "action.approved", action_id, {"approver": access["actor"], "approval_count": len(approvals), "status": action["status"]})
    return copy.deepcopy(action)


def update_action(username: str, tier: str, action_id: str, new_status: str, actual_result: str = "", verification_evidence: Sequence[str] = ()) -> dict[str, Any]:
    access = _session_authorize(username, tier, "write")
    actions = list(_state_list("actions"))
    index = next((i for i, item in enumerate(actions) if item.get("action_id") == str(action_id)), None)
    if index is None:
        raise IndustrialIntelligenceError("Action does not exist in this workspace.")
    action = actions[index]
    target = str(new_status or "").upper()
    allowed = {"PROPOSED", "PENDING_APPROVAL", "APPROVED", "IN_PROGRESS", "IMPLEMENTED", "CLOSED", "VERIFIED", "BLOCKED"}
    if target not in allowed:
        raise IndustrialIntelligenceError(f"Unsupported action status: {target}.")
    current = str(action.get("status") or "").upper()
    if target == "APPROVED":
        raise PermissionError("Use approve_action so the authenticated approver, role and audit record are enforced.")
    transitions = {
        "PROPOSED": {"BLOCKED"},
        "PENDING_APPROVAL": {"BLOCKED"},
        "APPROVED": {"IN_PROGRESS", "BLOCKED"},
        "IN_PROGRESS": {"IMPLEMENTED", "BLOCKED"},
        "IMPLEMENTED": {"BLOCKED", "VERIFIED"},
        "VERIFIED": {"CLOSED"},
        "BLOCKED": {str(action.get("blocked_from_status") or "").upper()},
    }
    if target not in transitions.get(current, set()):
        raise PermissionError(f"Invalid action transition: {current} → {target}.")
    if target == "BLOCKED":
        action["blocked_from_status"] = current
    elif current == "BLOCKED":
        action.pop("blocked_from_status", None)
    if target == "VERIFIED":
        if action.get("status") != "IMPLEMENTED":
            raise PermissionError("An action must be recorded as IMPLEMENTED before independent verification.")
        refs = _require_evidence_refs(verification_evidence, "Verified action closure")
        if not str(actual_result or "").strip():
            raise IndustrialIntelligenceError("Verified closure requires an actual result and verification evidence.")
        if str(action.get("created_by", "")).casefold() == access["actor"].casefold():
            raise PermissionError("The action creator cannot independently verify their own outcome.")
        if access["role"] not in {"owner", "admin", "administrator", "enterprise admin", "approver"}:
            raise PermissionError("Independent verification requires an Owner, Admin or Approver role.")
        action["verification"] = {"verifier": access["actor"], "evidence_refs": refs, "verified_at": _utc_now()}
        action["actual_result"] = str(actual_result)[:4000]
    action["status"] = target
    action["updated_at"] = _utc_now()
    actions[index] = action
    _save_state_list(username, tier, "actions", actions)
    _sync_thread_node(username, tier, "Action", action["title"], action_id, target.title(), {"owner": action["owner"], "status": target, "verification": action.get("verification")})
    _append_audit(username, tier, "action.status_changed", action_id, {"status": target, "actual_result": actual_result if target == "VERIFIED" else None})
    return copy.deepcopy(action)


def record_risk_barrier(username: str, tier: str, hazard: str, severity: int, likelihood: int, barriers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    sev = _finite(severity, "severity", minimum=1, maximum=5)
    like = _finite(likelihood, "likelihood", minimum=1, maximum=5)
    rows = []
    effectiveness = []
    for index, barrier in enumerate(barriers, start=1):
        if not isinstance(barrier, Mapping):
            raise IndustrialIntelligenceError(f"Barrier {index} must be an object.")
        owner = str(barrier.get("owner") or "").strip()
        evidence = str(barrier.get("evidence_id") or "").strip()
        state = str(barrier.get("status") or "UNKNOWN").upper()
        evidence_valid = False
        if evidence:
            try:
                _require_evidence_refs([evidence], f"Barrier {index}")
                evidence_valid = True
            except IndustrialIntelligenceError:
                evidence_valid = False
        barrier_id = _required_text(barrier.get("barrier_id"), f"barrier {index} barrier_id")
        # User-reported EFFECTIVE is not independently verified. Only the separate
        # reviewer workflow may count a barrier toward the reviewed screening score.
        rows.append({"barrier_id": barrier_id, "owner": owner or None, "evidence_id": evidence or None, "evidence_registered": evidence_valid, "reported_status": state, "status": "EFFECTIVENESS_NOT_INDEPENDENTLY_REVIEWED", "counts_as_effective": False})
        effectiveness.append(0.0)
    initial = sev * like
    reduction = sum(effectiveness) / len(effectiveness) if effectiveness else 0.0
    residual = initial * (1.0 - 0.6 * reduction)
    record = create_record(username, tier, "risk_barrier_assurance", hazard, {"hazard": _required_text(hazard, "hazard"), "severity": sev, "likelihood": like, "initial_screening_score": initial, "barriers": rows, "residual_screening_score": residual, "formal_safety_approval": False, "thread_node_type": "Risk"}, "MANUAL")
    return record


def review_barrier_effectiveness(
    username: str,
    tier: str,
    risk_record_id: str,
    barrier_id: str,
    decision: str,
    evidence_ref: str,
    reviewer_comment: str = "",
) -> dict[str, Any]:
    access = _session_authorize(username, tier, "approve")
    records = list(_state_list("records"))
    risk_record = next(
        (item for item in records if item.get("record_id") == str(risk_record_id) and item.get("record_type") == "risk_barrier_assurance"),
        None,
    )
    if not risk_record:
        raise IndustrialIntelligenceError("Risk/barrier record does not exist in this workspace.")
    if str(risk_record.get("created_by", "")).casefold() == access["actor"].casefold():
        raise PermissionError("The risk/barrier record creator cannot independently review its barriers.")
    key = _required_text(barrier_id, "barrier_id")
    barriers = risk_record.get("payload", {}).get("barriers", [])
    barrier = next((item for item in barriers if str(item.get("barrier_id")) == key), None)
    if not barrier:
        raise IndustrialIntelligenceError("Barrier ID does not exist in the selected risk record.")
    if str(barrier.get("owner") or "").casefold() == access["actor"].casefold():
        raise PermissionError("The barrier owner cannot independently review their own barrier.")
    status = str(decision or "").upper()
    if status not in {"VERIFIED_EFFECTIVE", "NOT_EFFECTIVE"}:
        raise IndustrialIntelligenceError("Barrier review decision must be VERIFIED_EFFECTIVE or NOT_EFFECTIVE.")
    ref = _require_evidence_refs([evidence_ref], "Independent barrier review")[0]
    prior = _state_list("barrier_reviews")
    if any(
        row.get("risk_record_id") == str(risk_record_id)
        and row.get("barrier_id") == key
        for row in prior
    ):
        raise IndustrialIntelligenceError("This barrier already has an independent review. Create a separately versioned risk record before reassessment.")
    review = {
        "review_id": "IIB-" + uuid.uuid4().hex[:12].upper(),
        "organization_id": access["organization_id"],
        "workspace_id": access["workspace_id"],
        "risk_record_id": str(risk_record_id),
        "barrier_id": key,
        "decision": status,
        "evidence_ref": ref,
        "reviewer": access["actor"],
        "role": access["role"],
        "comment": str(reviewer_comment or "")[:2000],
        "reviewed_at": _utc_now(),
    }
    prior.append(review)
    _save_state_list(username, tier, "barrier_reviews", prior, action="approve")
    reviewed = [row for row in prior if row.get("risk_record_id") == str(risk_record_id)]
    effective_ids = {row["barrier_id"] for row in reviewed if row.get("decision") == "VERIFIED_EFFECTIVE"}
    initial = _finite(risk_record.get("payload", {}).get("initial_screening_score"), "initial screening score", minimum=0)
    residual = initial * (1.0 - 0.6 * len(effective_ids) / max(1, len(barriers)))
    review_record = create_record(
        username, tier, "risk_barrier_review", f"Barrier review {key}",
        {
            "risk_record_id": str(risk_record_id),
            "barrier_id": key,
            "thread_node_type": "Risk",
            "decision": status,
            "evidence_ref": ref,
            "reviewer": access["actor"],
            "residual_screening_score": residual,
            "formal_safety_approval": False,
        },
        "MANUAL",
    )
    _append_audit(username, tier, "risk_barrier.independent_review", review_record["record_id"], review)
    return {"review": copy.deepcopy(review), "review_record": review_record, "residual_screening_score": residual, "formal_safety_approval": False}


def record_benefit(username: str, tier: str, project: str, metric: str, baseline: float, actual: float, unit: str, evidence_refs: Sequence[str]) -> dict[str, Any]:
    """Record an actual outcome without self-certifying a realized benefit."""
    base = _finite(baseline, "baseline")
    value = _finite(actual, "actual")
    refs = _require_evidence_refs(evidence_refs, "Actual benefit record")
    return create_record(username, tier, "benefit_realization", project, {"project": _required_text(project, "project"), "metric": _required_text(metric, "metric"), "baseline": base, "actual": value, "unit": _required_text(unit, "unit", 40), "delta": value - base, "evidence_refs": refs, "benefit_status": "ACTUAL_RECORDED_UNVERIFIED", "realized_financial_savings_claimed": False, "thread_node_type": "Outcome"}, "MANUAL")


def verify_benefit_record(username: str, tier: str, record_id: str, verification_evidence: Sequence[str], reviewer_comment: str = "") -> dict[str, Any]:
    access = _session_authorize(username, tier, "approve")
    records = list(_state_list("records"))
    record = next((item for item in records if item.get("record_id") == str(record_id) and item.get("record_type") == "benefit_realization"), None)
    if not record:
        raise IndustrialIntelligenceError("Benefit record does not exist in this workspace.")
    if str(record.get("created_by", "")).casefold() == access["actor"].casefold():
        raise PermissionError("The benefit record creator cannot independently verify the outcome.")
    refs = _require_evidence_refs(verification_evidence, "Independent benefit verification")
    verifications = list(_state_list("benefit_verifications"))
    if any(item.get("record_id") == str(record_id) for item in verifications):
        raise IndustrialIntelligenceError("A verification decision already exists for this benefit record.")
    review = {"verification_id": "IIV-" + uuid.uuid4().hex[:12].upper(), "organization_id": access["organization_id"], "workspace_id": access["workspace_id"], "record_id": str(record_id), "reviewer": access["actor"], "role": access["role"], "evidence_refs": refs, "comment": str(reviewer_comment or "")[:2000], "status": "VERIFIED_BY_INDEPENDENT_REVIEWER", "reviewed_at": _utc_now()}
    verifications.append(review)
    _save_state_list(username, tier, "benefit_verifications", verifications, action="approve")
    _append_audit(username, tier, "benefit.independently_verified", str(record_id), review)
    return copy.deepcopy(review)


def register_model_version(username: str, tier: str, name: str, version: str, model_type: str, definition: Mapping[str, Any], assumptions: Sequence[str], test_cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    access = _session_authorize(username, tier, "write")
    model_id = _required_text(name, "model name", 180)
    version_id = _required_text(version, "model version", 80)
    models = list(_state_list("models"))
    if any(row.get("name") == model_id and row.get("version") == version_id for row in models):
        raise IndustrialIntelligenceError("Model version is immutable and already exists.")
    if not isinstance(test_cases, Sequence) or isinstance(test_cases, (str, bytes)):
        raise IndustrialIntelligenceError("Model test_cases must be a sequence of test-case objects.")
    if isinstance(assumptions, (str, bytes)) or not isinstance(assumptions, Sequence):
        raise IndustrialIntelligenceError("Model assumptions must be a sequence of text statements.")
    tests = []
    for index, case in enumerate(test_cases, start=1):
        if not isinstance(case, Mapping):
            raise IndustrialIntelligenceError(f"Model test case {index} must be an object.")
        if "expected" not in case or "actual" not in case:
            raise IndustrialIntelligenceError(f"Model test case {index} must include expected and actual values.")
        expected = _json_safe(case.get("expected"))
        actual = _json_safe(case.get("actual"))
        if isinstance(expected, (int, float)) and not isinstance(expected, bool) and isinstance(actual, (int, float)) and not isinstance(actual, bool):
            passed = math.isclose(float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-9)
        else:
            passed = expected == actual
        test_evidence = str(case.get("evidence_id") or "").strip()
        if test_evidence:
            _require_evidence_refs([test_evidence], f"Model test {index}")
        tests.append({"test_id": _required_text(case.get("test_id"), f"model test {index} test_id"), "expected": expected, "actual": actual, "passed": bool(passed), "evidence_id": test_evidence or None})
    normalized_assumptions = [_required_text(item, "model assumption", 500) for item in assumptions]
    if not tests:
        raise IndustrialIntelligenceError("At least one expected-versus-actual model test case is required.")
    definition_hash = _hash_payload({"definition": definition, "assumptions": normalized_assumptions, "test_cases": tests})
    record = {"model_id": "IIM-" + uuid.uuid4().hex[:12].upper(), "name": model_id, "version": version_id, "model_type": _required_text(model_type, "model_type"), "definition": _json_safe(definition), "definition_hash": definition_hash, "assumptions": normalized_assumptions, "test_cases": tests, "test_count": len(tests), "passed_test_count": sum(1 for test in tests if test["passed"]), "owner": access["actor"], "organization_id": access["organization_id"], "workspace_id": access["workspace_id"], "status": "REGISTERED_UNVALIDATED", "created_at": _utc_now()}
    models.append(record)
    _save_state_list(username, tier, "models", models)
    record["thread_node_id"] = _sync_thread_node(
        username, tier, "Model", f"{model_id} · {version_id}", record["model_id"],
        "Registered", {"version": version_id, "definition_hash": record["definition_hash"], "status": record["status"]},
    )
    models[-1] = record
    _save_state_list(username, tier, "models", models)
    _append_audit(username, tier, "model.version_registered", record["model_id"], {"version": version_id, "definition_hash": record["definition_hash"]})
    return copy.deepcopy(record)


def validate_model_version(username: str, tier: str, model_id: str, verification_evidence: Sequence[str], reviewer_comment: str = "") -> dict[str, Any]:
    access = _session_authorize(username, tier, "approve")
    models = list(_state_list("models"))
    index = next((i for i, item in enumerate(models) if item.get("model_id") == model_id), None)
    if index is None:
        raise IndustrialIntelligenceError("Model version does not exist.")
    model = models[index]
    if not model.get("test_cases") or model["passed_test_count"] != model["test_count"]:
        raise IndustrialIntelligenceError("A model cannot be validated until all registered test cases pass.")
    if model.get("owner", "").casefold() == access["actor"].casefold():
        raise PermissionError("The model author cannot independently approve the model version.")
    refs = _require_evidence_refs(verification_evidence, "Independent model validation")
    model["status"] = "VALIDATED_BY_REVIEWER"
    model["review"] = {"reviewer": access["actor"], "evidence_refs": refs, "comment": str(reviewer_comment or "")[:2000], "reviewed_at": _utc_now()}
    models[index] = model
    _save_state_list(username, tier, "models", models, action="approve")
    _sync_thread_node(username, tier, "Model", f"{model['name']} · {model['version']}", model_id, "Validated", {"version": model["version"], "definition_hash": model["definition_hash"], "status": model["status"], "reviewer": access["actor"]})
    _append_audit(username, tier, "model.version_validated", model_id, model["review"])
    return copy.deepcopy(model)


def record_cause_effect_investigation(username: str, tier: str, title: str, observations: Sequence[str], candidate_links: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    links = []
    for index, item in enumerate(candidate_links, start=1):
        if not isinstance(item, Mapping):
            raise IndustrialIntelligenceError(f"Candidate link {index} must be an object.")
        evidence = [_required_text(value, "evidence reference", 240) for value in item.get("supporting_evidence", [])]
        counter = [_required_text(value, "counter-evidence reference", 240) for value in item.get("contradicting_evidence", [])]
        if evidence:
            evidence = _require_evidence_refs(evidence, f"Cause-effect candidate {index} supporting")
        if counter:
            counter = _require_evidence_refs(counter, f"Cause-effect candidate {index} contradicting")
        validation = str(item.get("validation_status") or "SUSPECTED").upper()
        if validation not in {"SUSPECTED", "SUPPORTED"}:
            raise IndustrialIntelligenceError("Cause-effect links must be recorded as SUSPECTED or SUPPORTED; confirmation requires a separate independent review workflow.")
        if validation == "SUPPORTED":
            evidence = _require_evidence_refs(evidence, f"Cause-effect candidate {index}")
        links.append({"from": _required_text(item.get("from"), "candidate from"), "to": _required_text(item.get("to"), "candidate to"), "relationship": str(item.get("relationship") or "POSSIBLE_CAUSE"), "supporting_evidence": evidence, "contradicting_evidence": counter, "validation_status": validation})
    return create_record(username, tier, "cause_effect_investigation", title, {"title": _required_text(title, "title"), "observations": [_required_text(item, "observation", 1000) for item in observations], "candidate_relationships": links, "causal_claim": "UNCONFIRMED_UNLESS_INDIVIDUALLY_REVIEWED", "thread_node_type": "Decision"}, "MANUAL")


def review_cause_effect_investigation(
    username: str,
    tier: str,
    investigation_record_id: str,
    relationship_index: int,
    decision: str,
    verification_evidence: Sequence[str],
    reviewer_comment: str = "",
) -> dict[str, Any]:
    access = _session_authorize(username, tier, "approve")
    records = list(_state_list("records"))
    investigation = next(
        (item for item in records if item.get("record_id") == str(investigation_record_id) and item.get("record_type") == "cause_effect_investigation"),
        None,
    )
    if not investigation:
        raise IndustrialIntelligenceError("Cause-and-effect investigation does not exist in this workspace.")
    if str(investigation.get("created_by", "")).casefold() == access["actor"].casefold():
        raise PermissionError("The investigation author cannot independently review its causal claims.")
    links = investigation.get("payload", {}).get("candidate_relationships", [])
    if isinstance(relationship_index, bool) or not 0 <= int(relationship_index) < len(links):
        raise IndustrialIntelligenceError("relationship_index does not identify a candidate relationship.")
    candidate = links[int(relationship_index)]
    status = str(decision or "").upper()
    if status not in {"CONFIRMED", "REJECTED"}:
        raise IndustrialIntelligenceError("Independent cause-effect review decision must be CONFIRMED or REJECTED.")
    refs = _require_evidence_refs(verification_evidence, "Independent cause-effect review")
    if any(
        item.get("record_type") == "cause_effect_review"
        and item.get("payload", {}).get("investigation_record_id") == str(investigation_record_id)
        and item.get("payload", {}).get("relationship_index") == int(relationship_index)
        for item in records
    ):
        raise IndustrialIntelligenceError("This candidate relationship already has an independent review. Create a new versioned investigation for reassessment.")
    if status == "CONFIRMED" and not (candidate.get("supporting_evidence") or refs):
        raise IndustrialIntelligenceError("Confirming a causal relationship requires supporting evidence.")
    review = create_record(
        username, tier, "cause_effect_review",
        f"Independent cause-effect review · {investigation.get('name')}",
        {
            "investigation_record_id": str(investigation_record_id),
            "relationship_index": int(relationship_index),
            "candidate_relationship": _json_safe(candidate),
            "decision": status,
            "supporting_evidence": refs,
            "reviewer": access["actor"],
            "role": access["role"],
            "comment": str(reviewer_comment or "")[:2000],
            "confirmation_scope": "THIS_REVIEWED_RELATIONSHIP_ONLY",
            "thread_node_type": "Decision",
        },
        "MANUAL",
    )
    _append_audit(username, tier, "cause_effect.independent_review", review["record_id"], review["payload"])
    return {"review_record": review, "decision": status, "source_investigation_id": str(investigation_record_id)}


def copilot_evidence_context(username: str, tier: str, query: str, limit: int = 15) -> dict[str, Any]:
    _session_authorize(username, tier, "read")
    term = str(query or "").strip().casefold()
    if not term:
        raise IndustrialIntelligenceError("Enter a question or search term.")
    records = _state_list("records")
    tokens = [token for token in re.findall(r"[a-z0-9_-]{3,}", term) if token]
    matches = []
    for row in records:
        haystack = json.dumps({"name": row.get("name"), "type": row.get("record_type"), "payload": row.get("payload")}, ensure_ascii=False, default=str).casefold()
        score = sum(1 for token in tokens if token in haystack)
        if score:
            matches.append((score, row))
    matches.sort(key=lambda item: (-item[0], str(item[1].get("created_at") or "")))
    results = []
    for score, row in matches[:max(1, min(50, int(limit)))]:
        results.append({"citation_id": row.get("record_id"), "record_type": row.get("record_type"), "name": row.get("name"), "created_at": row.get("created_at"), "provenance": row.get("provenance"), "source_ref": row.get("source_ref"), "payload": row.get("payload"), "match_score": score})
    return {"status": "EVIDENCE_RETRIEVED" if results else "INSUFFICIENT_MATCHING_EVIDENCE", "query": query, "citations": results, "answer_boundary": "This is evidence retrieval context, not an AI-generated causal conclusion. Cite record IDs and disclose missing evidence."}


def thread_snapshot(username: str, tier: str) -> dict[str, Any]:
    _session_authorize(username, tier, "read")
    import shoir_digital_thread as thread
    all_nodes = copy.deepcopy(thread.st.session_state.get(thread._keys()["nodes"], []))
    all_edges = copy.deepcopy(thread.st.session_state.get(thread._keys()["edges"], []))
    allowed_node_ids = {
        str(row.get("thread_node_id") or "")
        for collection in ("records", "nodes", "actions", "models")
        for row in _state_list(collection)
        if str(row.get("thread_node_id") or "")
    }
    nodes = [
        node for node in all_nodes
        if str(node.get("node_id") or "") in allowed_node_ids
    ]
    visible_ids = {str(node.get("node_id") or "") for node in nodes}
    edges = [
        edge for edge in all_edges
        if str(edge.get("source_id") or "") in visible_ids
        and str(edge.get("target_id") or "") in visible_ids
        and str(edge.get("source_id") or "") != str(edge.get("target_id") or "")
    ]
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": nodes,
        "edges": edges,
        "record_nodes": len(_state_list("nodes")),
        "record_relationships": len(_state_list("edges")),
    }


def _sample_input(tool_id: str) -> dict[str, Any]:
    samples = {
        "mission-control": {"event_id": "SYN-EVT-001", "severity": 4, "urgency": 4, "operational_impact_score": 4, "affected_domains": ["Production", "Maintenance"], "evidence_refs": ["SYNTHETIC:fixture-001"]},
        "process-mining": {"events": [{"case_id": "SYN-1", "activity": "Receive", "timestamp": "2026-11-01T08:00:00Z"}, {"case_id": "SYN-1", "activity": "Inspect", "timestamp": "2026-11-01T10:00:00Z"}, {"case_id": "SYN-1", "activity": "Pack", "timestamp": "2026-11-01T10:30:00Z"}], "approved_sequence": ["Receive", "Inspect", "Pack"]},
        "engineering-change": {"change_title": "Synthetic material substitution", "source_entity_id": "MAT-SYN-01", "dependencies": [{"source_id": "MAT-SYN-01", "target_id": "PROC-SYN-01", "relation": "USED_IN"}, {"source_id": "PROC-SYN-01", "target_id": "QC-SYN-01", "relation": "REQUIRES_INSPECTION"}], "required_reviews": ["Quality", "Process Engineering", "Procurement"]},
        "turnaround": {"tasks": [{"task_id": "SYN-JOB-1", "duration_hours": 4, "skill": "mechanical", "dependencies": [], "permit_required": True, "permit_status": "APPROVED"}, {"task_id": "SYN-JOB-2", "duration_hours": 3, "skill": "electrical", "dependencies": ["SYN-JOB-1"], "inspection_required": True, "inspection_status": "PASSED"}], "resources": [{"id": "SYN-MECH-1", "skills": ["mechanical"]}, {"id": "SYN-ELEC-1", "skills": ["electrical"]}]},
        "data-trust": {"measurements": [{"meter_id": "SYN-FM-1", "value": 100, "unit": "m3/h", "source": "SYN-METER-A", "timestamp": "2026-11-01T08:00:00Z", "provenance": "SYNTHETIC"}, {"meter_id": "SYN-FM-1", "value": 107, "unit": "m3/h", "source": "SYN-METER-B", "timestamp": "2026-11-01T08:00:00Z", "provenance": "SYNTHETIC"}], "balances": [{"name": "Synthetic water balance", "input": 100, "output": 88, "losses": 10, "unit": "m3/h", "tolerance": 1}]},
        "asset-reliability": {"assets": [{"asset_id": "SYN-PUMP-01", "criticality": 5, "failure_count": 3, "downtime_hours": 18, "production_impact_score": 4, "safety_critical": False}], "dependencies": [{"asset_id": "SYN-PUMP-01", "affected_entity_id": "SYN-LINE-01", "impact": "PRODUCTION"}]},
        "yield-intelligence": {"input_units": 1000, "first_pass_good_units": 910, "rework_recovered_units": 40, "scrap_units": 30},
        "commissioning": {"required_checks": [{"check_id": "SYN-TEST-01", "status": "PASSED", "evidence_id": "SYNTHETIC:calibration-01"}, {"check_id": "SYN-TEST-02", "status": "PENDING"}]},
        "experimentation": {"factors": ["temperature", "speed"]},
        "procurement-assurance": {"requirements": [{"requirement_id": "R1", "description": "Rated capacity >= 10 m3/h"}, {"requirement_id": "R2", "description": "Material compatibility"}], "offers": [{"supplier": "Synthetic Vendor A", "claims": [{"requirement_id": "R1", "compliance": "COMPLIANT", "evidence_id": "SYNTHETIC:DATASHEET-1"}, {"requirement_id": "R2", "compliance": "UNVERIFIED"}]}]},
        "energy-flexibility": {"periods": [{"period_id": "P1", "tariff": 0.4, "capacity_kwh": 200, "base_kwh": 40}, {"period_id": "P2", "tariff": 0.2, "capacity_kwh": 200, "base_kwh": 50}], "loads": [{"load_id": "SYN-LOAD-1", "energy_kwh": 80, "flexible": True, "earliest_period": "P1", "latest_period": "P2"}]},
        "spare-parts": {"part_id": "SYN-BRG-001", "transfer_quantity": 3, "compatible": True, "source": {"on_hand": 8, "minimum_stock": 6}, "destination": {"on_hand": 1}},
        "ot-assurance": {"asset_id": "SYN-PLC-01", "approved_baseline": {"firmware": "1.0", "config_hash": "SYN-BASE"}, "observed_configuration": {"firmware": "1.0", "config_hash": "SYN-OBS"}, "observed_provenance": "SYNTHETIC"},
        "batch-genealogy": {"lot_id": "SYN-FG-01", "direction": "backward", "genealogy": [{"parent_lot": "SYN-RM-01", "child_lot": "SYN-FG-01", "status": "CONFIRMED"}, {"parent_lot": "SYN-RM-02", "child_lot": "SYN-FG-01", "status": "SUSPECTED"}]},
        "shift-handover": {"outgoing_shift": "Synthetic Shift A", "incoming_shift": "Synthetic Shift B", "issues": [{"issue_id": "SYN-ISSUE-01", "owner": "synthetic-engineer", "status": "OPEN", "acknowledged_by_incoming": False}]},
        "benchmarking": {"observations": [{"name": "Synthetic Line A", "metric": "Energy intensity", "unit": "kWh/t", "period": "2026-10", "value": 120}, {"name": "Synthetic Line B", "metric": "Energy intensity", "unit": "kWh/t", "period": "2026-10", "value": 110}]},
    }
    return copy.deepcopy(samples[tool_id])


def _record_to_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _record_to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_record_to_json(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def render_industrial_intelligence_suite(streamlit_module, username: str, tier: str) -> None:
    ui = streamlit_module
    pending_tool_id = ui.session_state.pop("shoir_pending_industrial_tool", None)
    if pending_tool_id in {item["id"] for item in TOOL_CATALOG}:
        # Workbench search can deep-link to a specialist capability without
        # changing the existing navigation or creating a duplicate page.
        ui.session_state["shoir_ii_tool_search"] = ""
        ui.session_state["shoir_ii_suite_filter"] = "All suites"
        ui.session_state["shoir_ii_selected_tool"] = pending_tool_id
    ui.markdown("## Industrial Intelligence Suite")
    ui.caption("Six connected suites · 16 deterministic tool engines · shared evidence, Digital Thread, decisions, actions and model governance.")
    try:
        access = _session_authorize(username, tier, "read")
        ui.caption(f"Workspace scope: {access['scope']} · Role: {access['role']} · Organization data is checked by the staging workspace service on access.")
    except Exception as exc:
        ui.warning(f"Industrial Intelligence workspace access is not available: {exc}")
        return

    suite_tabs = ui.tabs([item["name"] for item in SUITES])
    for tab, suite in zip(suite_tabs, SUITES):
        with tab:
            ui.markdown(f"**{suite['name']}**")
            for tool_id in suite["tools"]:
                definition = tool_definition(tool_id)
                ui.markdown(f"**{definition['name']}**")
                ui.caption(definition["purpose"])
                ui.caption(f"Input contract: {definition['input']}")
                ui.caption(f"Method and limit: {definition['method']}")
                ui.divider()

    search_col, suite_col = ui.columns([2, 1])
    query = search_col.text_input("Search Industrial Intelligence tools and aliases", key="shoir_ii_tool_search")
    selected_suite = suite_col.selectbox("Suite filter", ["All suites"] + [item["name"] for item in SUITES], key="shoir_ii_suite_filter")
    suite_id = next((item["id"] for item in SUITES if item["name"] == selected_suite), None)
    search_results = search_tools(query, suite_id)
    if not search_results:
        ui.info("No tool matches this search. Try an equipment, process, data trust, turnaround, genealogy or energy term.")
        return
    tool_options = [item["id"] for item in search_results]
    if ui.session_state.get("shoir_ii_selected_tool") not in tool_options:
        ui.session_state["shoir_ii_selected_tool"] = tool_options[0]
    selected_id = ui.selectbox("Open tool", tool_options, format_func=lambda value: next(f"{item['tool_code']} · {item['name']}" for item in search_results if item["id"] == value), key="shoir_ii_selected_tool")
    definition = tool_definition(selected_id)
    ui.markdown(f"### {definition['tool_code']} · {definition['name']}")
    ui.write(definition["purpose"])
    ui.caption("Enter validated JSON input. The populated example is explicitly synthetic and must not be represented as plant data.")
    saved_records = list(_state_list("records"))
    saved_record_options = [""] + [str(item.get("record_id")) for item in saved_records]
    selected_saved_record = ui.selectbox(
        "Reuse a record already saved in this workspace (optional)",
        saved_record_options,
        format_func=lambda value: "Do not reuse a saved record" if not value else next(
            f"{item.get('name')} · {item.get('record_type')} · {value}"
            for item in saved_records if str(item.get("record_id")) == value
        ),
        key=f"shoir_ii_saved_source_{selected_id}",
    )
    if ui.button("Load saved record payload into this tool", disabled=not selected_saved_record, key=f"shoir_ii_load_saved_{selected_id}"):
        try:
            source_record = next(item for item in saved_records if str(item.get("record_id")) == selected_saved_record)
            source_payload = source_record.get("payload", {})
            candidate = source_payload.get("input") if source_record.get("record_type") == "tool_analysis" and isinstance(source_payload, Mapping) else source_payload
            if not isinstance(candidate, Mapping):
                raise IndustrialIntelligenceError("The selected record does not contain a reusable JSON object.")
            ui.session_state[f"shoir_ii_input_{selected_id}"] = json.dumps(candidate, ensure_ascii=False, indent=2)
            ui.session_state[f"shoir_ii_provenance_{selected_id}"] = source_record.get("provenance", "IMPORTED")
            ui.session_state[f"shoir_ii_source_{selected_id}"] = source_record.get("source_ref") or selected_saved_record
            ui.success(f"Loaded authorized record {selected_saved_record}. Review the fields before running.")
        except Exception as exc:
            ui.error(f"Saved record could not be reused: {exc}")
    defaults = json.dumps(_sample_input(selected_id), ensure_ascii=False, indent=2)
    input_text = ui.text_area("Tool input JSON", value=defaults, height=280, key=f"shoir_ii_input_{selected_id}")
    provenance_options = list(PROVENANCE)
    provenance = ui.selectbox("Input provenance", provenance_options, index=3, key=f"shoir_ii_provenance_{selected_id}")
    source_ref = ui.text_input("Source / evidence reference (optional)", key=f"shoir_ii_source_{selected_id}")
    if ui.button("Run deterministic analysis", type="primary", key=f"shoir_ii_run_{selected_id}"):
        try:
            parsed = json.loads(input_text)
            if not isinstance(parsed, dict):
                raise IndustrialIntelligenceError("Tool input JSON root must be an object.")
            result = analyze_tool(selected_id, parsed)
            ui.session_state[STATE_PREFIX + "last_analysis"] = {"tool_id": selected_id, "input": parsed, "result": result, "provenance": provenance, "source_ref": source_ref}
            ui.success("Analysis completed. Results are calculated from the submitted inputs only.")
        except Exception as exc:
            ui.error(f"Analysis could not be completed: {exc}")
    last = ui.session_state.get(STATE_PREFIX + "last_analysis")
    if isinstance(last, dict) and last.get("tool_id") == selected_id:
        ui.markdown("#### Analysis result")
        ui.json(_record_to_json(last.get("result", {})))
        ui.caption(f"Input provenance: {last.get('provenance')} · Model: {last.get('result', {}).get('model_version')} · Input hash: {last.get('result', {}).get('input_hash')}")
        export_bundle = {
            "tool_id": selected_id,
            "tool_name": definition["name"],
            "input": last.get("input", {}),
            "result": last.get("result", {}),
            "provenance": last.get("provenance"),
            "source_ref": last.get("source_ref"),
            "exported_at": _utc_now(),
            "export_status": "MODEL_OUTPUT_NOT_INDEPENDENTLY_VERIFIED",
        }
        ui.download_button(
            "Download analysis and evidence JSON",
            data=json.dumps(_record_to_json(export_bundle), ensure_ascii=False, indent=2).encode("utf-8"),
            file_name=f"shoir_ie_{selected_id}_evidence.json",
            mime="application/json",
            key=f"shoir_ii_export_json_{selected_id}",
        )
        try:
            from industrial_operating_system import render_exports
            input_table = pd.DataFrame([
                {"Field": str(key), "Value": json.dumps(_record_to_json(value), ensure_ascii=False) if isinstance(value, (Mapping, list, tuple)) else str(value)}
                for key, value in last.get("input", {}).items()
            ])
            summary_table = pd.DataFrame([
                {"Field": str(key), "Value": json.dumps(_record_to_json(value), ensure_ascii=False) if isinstance(value, (Mapping, list, tuple)) else str(value)}
                for key, value in last.get("result", {}).items()
                if not isinstance(value, list)
            ])
            output_tables = [("Input Contract", input_table), ("Result Summary", summary_table)]
            for result_key, result_value in last.get("result", {}).items():
                if isinstance(result_value, list) and result_value and all(isinstance(item, Mapping) for item in result_value):
                    output_tables.append((str(result_key)[:31], pd.DataFrame([_record_to_json(item) for item in result_value]).head(10000)))
            render_exports(definition["name"], output_tables, [], tier, username)
        except Exception as exc:
            ui.warning(f"Shared Excel/PDF/PowerPoint export is not available for this result: {exc}")
        save_col, workbook_col = ui.columns(2)
        if save_col.button("Save analysis and add it to the Digital Thread", key=f"shoir_ii_save_{selected_id}"):
            try:
                saved = create_record(username, tier, "tool_analysis", definition["name"], {"tool_id": selected_id, "input": last["input"], "result": last["result"], "thread_node_type": THREAD_NODE_TYPES[selected_id]}, provenance=last["provenance"], source_ref=last.get("source_ref") or "")
                ui.success(f"Saved record {saved['record_id']} and created its Digital Thread node.")
            except Exception as exc:
                ui.error(f"Record was not confirmed saved: {exc}")
        if workbook_col.button("Send result to Industrial Workbook", key=f"shoir_ii_workbook_{selected_id}"):
            try:
                handoff = send_analysis_to_workbook(
                    username, tier, selected_id, last["input"], last["result"],
                    last["provenance"], last.get("source_ref") or "",
                )
                ui.success(f"Added {handoff['workbook_sheet']} to the Industrial Workbook and saved record {handoff['record_id']}. Existing sheets were preserved.")
            except Exception as exc:
                ui.error(f"Industrial Workbook handoff was not confirmed: {exc}")

    ui.divider()
    workspace_tabs = ui.tabs(["Digital Thread and Evidence", "Decisions, Actions and Approvals", "Model Registry and Benefits", "Industry Templates and Copilot"])
    with workspace_tabs[0]:
        col1, col2 = ui.columns(2)
        with col1:
            ui.markdown("#### Register an industrial entity")
            entity_type = ui.selectbox("Entity type", ["Facility", "ProductionLine", "Process", "Asset", "Equipment", "Instrument", "Material", "Product", "Batch", "Supplier", "WorkOrder", "Project", "Document"], key="shoir_ii_entity_type")
            entity_id = ui.text_input("Stable entity ID", key="shoir_ii_entity_id")
            entity_name = ui.text_input("Entity display name", key="shoir_ii_entity_name")
            entity_json = ui.text_area("Entity attributes JSON", value="{}", key="shoir_ii_entity_attrs", height=100)
            entity_prov = ui.selectbox("Entity provenance", list(PROVENANCE), index=2, key="shoir_ii_entity_prov")
            if ui.button("Register entity", key="shoir_ii_entity_save"):
                try:
                    attrs = json.loads(entity_json)
                    if not isinstance(attrs, dict):
                        raise IndustrialIntelligenceError("Entity attributes must be a JSON object.")
                    entity = add_entity(username, tier, entity_type, entity_id, entity_name, attrs, entity_prov)
                    ui.success(f"Entity {entity['entity_id']} saved.")
                except Exception as exc:
                    ui.error(f"Entity was not saved: {exc}")
        with col2:
            ui.markdown("#### Link two registered entities")
            nodes = _state_list("nodes")
            choices = [str(item.get("entity_id")) for item in nodes]
            source_id = ui.selectbox("Source entity", choices, key="shoir_ii_edge_source") if choices else ""
            target_options = [value for value in choices if value != source_id]
            target_id = ui.selectbox("Target entity", target_options, key="shoir_ii_edge_target") if target_options else ""
            relation = ui.text_input("Relationship", value="DEPENDS_ON", key="shoir_ii_edge_relation")
            relation_status = ui.selectbox("Relationship status", ["CONFIRMED", "SUSPECTED", "PROPOSED"], key="shoir_ii_edge_status")
            evidence = ui.text_input("Evidence record ID(s) or registered source reference(s)", key="shoir_ii_edge_evidence")
            if ui.button("Create Digital Thread relationship", disabled=not source_id or not target_id, key="shoir_ii_edge_save"):
                try:
                    edge = add_relationship(username, tier, source_id, target_id, relation, relation_status, [item.strip() for item in evidence.split(",") if item.strip()])
                    ui.success(f"Relationship {edge['edge_id']} saved.")
                except Exception as exc:
                    ui.error(f"Relationship was not saved: {exc}")
        ui.markdown("#### Register evidence in the active workspace")
        ev1, ev2 = ui.columns(2)
        with ev1:
            evidence_name = ui.text_input("Evidence name", key="shoir_ii_evidence_name")
            evidence_source = ui.text_input("Source reference / document ID", key="shoir_ii_evidence_source")
            evidence_provenance = ui.selectbox("Evidence provenance", list(PROVENANCE), index=2, key="shoir_ii_evidence_provenance")
        with ev2:
            evidence_timestamp = ui.text_input("Source timestamp (timezone-aware ISO-8601)", key="shoir_ii_evidence_timestamp")
            evidence_description = ui.text_area("Evidence description / scope", height=80, key="shoir_ii_evidence_description")
            if ui.button("Register evidence record", key="shoir_ii_evidence_save"):
                try:
                    evidence_record = create_record(
                        username, tier, "evidence", evidence_name,
                        {"description": evidence_description, "thread_node_type": "Document", "source_timestamp": evidence_timestamp},
                        provenance=evidence_provenance, source_ref=evidence_source,
                    )
                    ui.success(f"Evidence registered: {evidence_record['record_id']}. Use this ID on confirmed relationships and verification steps.")
                except Exception as exc:
                    ui.error(f"Evidence was not registered: {exc}")
        evidence_records = [item for item in _state_list("records") if item.get("record_type") == "evidence"]
        if evidence_records:
            ui.dataframe(pd.DataFrame([
                {"Evidence ID": item.get("record_id"), "Name": item.get("name"), "Source": item.get("source_ref"), "Provenance": item.get("provenance"), "Created": item.get("created_at")}
                for item in evidence_records
            ]), use_container_width=True, hide_index=True)
        ui.markdown("#### Record an operational event")
        event_col1, event_col2 = ui.columns(2)
        with event_col1:
            event_type = ui.text_input("Event type", key="shoir_ii_event_type")
            event_entity = ui.text_input("Related entity ID (optional)", key="shoir_ii_event_entity")
            event_timestamp = ui.text_input("Event timestamp (blank = current UTC)", key="shoir_ii_event_timestamp")
        with event_col2:
            event_description = ui.text_area("Observed event description", height=80, key="shoir_ii_event_description")
            event_provenance = ui.selectbox("Event provenance", list(PROVENANCE), index=2, key="shoir_ii_event_provenance")
            event_source_ref = ui.text_input("Original source reference (required for LIVE/IMPORTED/STALE)", key="shoir_ii_event_source")
            event_evidence = ui.text_input("Registered evidence IDs / source refs", key="shoir_ii_event_evidence")
        if ui.button("Record operational event", key="shoir_ii_event_save"):
            try:
                event = create_operational_event(
                    username, tier, event_type, event_description, event_entity,
                    event_timestamp or None, event_provenance,
                    [item.strip() for item in event_evidence.split(",") if item.strip()],
                    source_ref=event_source_ref,
                )
                ui.success(f"Operational event saved: {event['record_id']}.")
            except Exception as exc:
                ui.error(f"Operational event was not saved: {exc}")
        operational_events = _state_list("events")
        if operational_events:
            ui.dataframe(pd.DataFrame([
                {"Event ID": item.get("record_id"), "Type": item.get("name"), "Event time": item.get("event_timestamp"), "Provenance": item.get("provenance"), "Entity": item.get("entity_id")}
                for item in operational_events
            ]), use_container_width=True, hide_index=True)
        try:
            graph = thread_snapshot(username, tier)
            ui.metric("Industrial entities", graph["record_nodes"])
            ui.metric("Industrial relationships", graph["record_relationships"])
            ui.dataframe(pd.DataFrame(_state_list("nodes")), use_container_width=True, hide_index=True)
            ui.dataframe(pd.DataFrame(_state_list("edges")), use_container_width=True, hide_index=True)
        except Exception as exc:
            ui.info(f"No Digital Thread graph is available yet: {exc}")

    with workspace_tabs[1]:
        ui.markdown("#### Create an accountable action")
        c1, c2 = ui.columns(2)
        with c1:
            action_title = ui.text_input("Action title", key="shoir_ii_action_title")
            action_owner = ui.text_input("Action owner", key="shoir_ii_action_owner")
            action_due = ui.text_input("Due date with timezone", value="2026-12-01T00:00:00Z", key="shoir_ii_action_due")
        with c2:
            action_priority = ui.selectbox("Priority", ["LOW", "MEDIUM", "HIGH", "CRITICAL"], key="shoir_ii_action_priority")
            expected_result = ui.text_area("Expected result", key="shoir_ii_action_expected")
            action_evidence = ui.text_input("Registered evidence record ID(s) / source refs, comma-separated", key="shoir_ii_action_evidence")
        if ui.button("Create proposed action", key="shoir_ii_action_create"):
            try:
                created = create_action(username, tier, action_title, action_owner, action_due, action_priority, expected_result, [item.strip() for item in action_evidence.split(",") if item.strip()])
                ui.success(f"Created {created['action_id']} as PROPOSED. It is not yet approved.")
            except Exception as exc:
                ui.error(f"Action was not created: {exc}")
        actions = _state_list("actions")
        if actions:
            ui.markdown("#### Action register")
            ui.dataframe(pd.DataFrame(actions), use_container_width=True, hide_index=True)
            action_ids = [str(item.get("action_id")) for item in actions]
            selected_action = ui.selectbox("Action to review", action_ids, key="shoir_ii_action_selected")
            selected_record = next(item for item in actions if item.get("action_id") == selected_action)
            if selected_record.get("status") in {"PROPOSED", "PENDING_APPROVAL"}:
                approval_comment = ui.text_input("Approval comment", key="shoir_ii_approval_comment")
                if ui.button("Approve action (authorized approver only)", key="shoir_ii_approve"):
                    try:
                        approved = approve_action(username, tier, selected_action, approval_comment)
                        ui.success(f"Approval recorded. Current status: {approved['status']}.")
                    except Exception as exc:
                        ui.error(f"Approval was not recorded: {exc}")
            transition = ui.selectbox("Move action to", ["IN_PROGRESS", "IMPLEMENTED", "CLOSED", "VERIFIED", "BLOCKED"], key="shoir_ii_action_transition")
            actual = ui.text_area("Actual result / verification note", key="shoir_ii_action_actual")
            verify_refs = ui.text_input("Verification evidence record ID(s) / source references", key="shoir_ii_verify_refs")
            if ui.button("Update action status", key="shoir_ii_action_update"):
                try:
                    updated = update_action(username, tier, selected_action, transition, actual, [item.strip() for item in verify_refs.split(",") if item.strip()])
                    ui.success(f"Action status updated to {updated['status']}.")
                except Exception as exc:
                    ui.error(f"Action status was not changed: {exc}")
        ui.markdown("#### Risk and barrier screening register")
        risk_title = ui.text_input("Hazard / risk title", key="shoir_ii_risk_title")
        rc1, rc2 = ui.columns(2)
        risk_severity = rc1.selectbox("Severity (1–5)", [1, 2, 3, 4, 5], index=2, key="shoir_ii_risk_severity")
        risk_likelihood = rc2.selectbox("Likelihood (1–5)", [1, 2, 3, 4, 5], index=2, key="shoir_ii_risk_likelihood")
        barriers_json = ui.text_area(
            "Barrier records JSON (barrier_id, owner, evidence_id, status)",
            value='[{"barrier_id":"B-01","owner":"engineer-01","evidence_id":"","status":"UNKNOWN"}]',
            key="shoir_ii_risk_barriers",
        )
        if ui.button("Save risk/barrier screening (not safety approval)", key="shoir_ii_risk_save"):
            try:
                barriers = json.loads(barriers_json)
                if not isinstance(barriers, list):
                    raise IndustrialIntelligenceError("Barrier records must be a JSON list.")
                risk_record = record_risk_barrier(username, tier, risk_title, risk_severity, risk_likelihood, barriers)
                ui.success(f"Risk/barrier screening saved: {risk_record['record_id']}. Formal safety approval is not granted.")
            except Exception as exc:
                ui.error(f"Risk/barrier screening was not saved: {exc}")
        risk_records = [item for item in _state_list("records") if item.get("record_type") == "risk_barrier_assurance"]
        if risk_records:
            ui.dataframe(pd.DataFrame([
                {"Record ID": item.get("record_id"), "Hazard": item.get("name"), "Status": item.get("record_status"), "Created": item.get("created_at")}
                for item in risk_records
            ]), use_container_width=True, hide_index=True)
            ui.markdown("#### Independent barrier-effectiveness review")
            selected_risk = ui.selectbox("Risk/barrier record", [item["record_id"] for item in risk_records], key="shoir_ii_barrier_risk_record")
            risk_record = next(item for item in risk_records if item["record_id"] == selected_risk)
            barrier_rows = risk_record.get("payload", {}).get("barriers", [])
            if barrier_rows:
                selected_barrier = ui.selectbox("Barrier to review", [item["barrier_id"] for item in barrier_rows], key="shoir_ii_barrier_review_id")
                barrier_decision = ui.selectbox("Review decision", ["VERIFIED_EFFECTIVE", "NOT_EFFECTIVE"], key="shoir_ii_barrier_review_decision")
                barrier_evidence = ui.text_input("Registered evidence record ID", key="shoir_ii_barrier_review_evidence")
                barrier_comment = ui.text_input("Independent reviewer comment", key="shoir_ii_barrier_review_comment")
                if ui.button("Submit independent barrier review", key="shoir_ii_barrier_review_submit"):
                    try:
                        review = review_barrier_effectiveness(username, tier, selected_risk, selected_barrier, barrier_decision, barrier_evidence, barrier_comment)
                        ui.success(f"Independent barrier review saved: {review['review_record']['record_id']}. Screening score: {review['residual_screening_score']:.2f}. This is not formal safety approval.")
                    except Exception as exc:
                        ui.error(f"Barrier review was not saved: {exc}")

    with workspace_tabs[2]:
        ui.markdown("#### Register immutable engineering model versions")
        model_name = ui.text_input("Model name", key="shoir_ii_model_name")
        model_version = ui.text_input("Version", key="shoir_ii_model_version")
        model_type = ui.text_input("Model type / method", key="shoir_ii_model_type")
        model_def = ui.text_area("Model definition JSON", value="{}", key="shoir_ii_model_def")
        model_assumptions = ui.text_area("Assumptions, one per line", key="shoir_ii_model_assumptions")
        model_tests = ui.text_area("Test cases JSON", value='[{"test_id":"golden-1","expected":1,"actual":1,"passed":true,"evidence_id":"SYNTHETIC:test-1"}]', key="shoir_ii_model_tests")
        if ui.button("Register model version", key="shoir_ii_model_register"):
            try:
                definition_json = json.loads(model_def)
                tests_json = json.loads(model_tests)
                if not isinstance(definition_json, dict) or not isinstance(tests_json, list):
                    raise IndustrialIntelligenceError("Model definition must be an object and test cases a list.")
                model = register_model_version(username, tier, model_name, model_version, model_type, definition_json, [item.strip() for item in model_assumptions.splitlines() if item.strip()], tests_json)
                ui.success(f"Registered immutable model version {model['model_id']}.")
            except Exception as exc:
                ui.error(f"Model version was not registered: {exc}")
        models = _state_list("models")
        if models:
            ui.dataframe(pd.DataFrame(models), use_container_width=True, hide_index=True)
            model_ids = [str(item.get("model_id")) for item in models if item.get("status") == "REGISTERED_UNVALIDATED"]
            if model_ids:
                model_to_review = ui.selectbox("Model version to validate", model_ids, key="shoir_ii_model_review")
                model_review_evidence = ui.text_input("Registered model validation evidence ID(s)", key="shoir_ii_model_review_evidence")
                model_review_comment = ui.text_input("Independent model review comment", key="shoir_ii_model_review_comment")
                if ui.button("Validate model version (independent approver)", key="shoir_ii_model_validate"):
                    try:
                        validated = validate_model_version(
                            username, tier, model_to_review,
                            [item.strip() for item in model_review_evidence.split(",") if item.strip()],
                            model_review_comment,
                        )
                        ui.success(f"Model status: {validated['status']}.")
                    except Exception as exc:
                        ui.error(f"Model version was not validated: {exc}")
        ui.markdown("#### Record outcome / benefit evidence")
        benefit_project = ui.text_input("Project", key="shoir_ii_benefit_project")
        benefit_metric = ui.text_input("Metric", key="shoir_ii_benefit_metric")
        b1, b2, b3 = ui.columns(3)
        baseline = b1.number_input("Baseline", value=0.0, key="shoir_ii_benefit_baseline")
        actual_value = b2.number_input("Actual", value=0.0, key="shoir_ii_benefit_actual")
        benefit_unit = b3.text_input("Unit", key="shoir_ii_benefit_unit")
        benefit_refs = ui.text_input("Actual evidence references", key="shoir_ii_benefit_refs")
        if ui.button("Record actual benefit (unverified until reviewed)", key="shoir_ii_benefit_save"):
            try:
                benefit = record_benefit(username, tier, benefit_project, benefit_metric, baseline, actual_value, benefit_unit, [item.strip() for item in benefit_refs.split(",") if item.strip()])
                ui.success(f"Recorded {benefit['record_id']} as {benefit['payload']['benefit_status']}.")
            except Exception as exc:
                ui.error(f"Benefit record was not saved: {exc}")
        benefit_records = [item for item in _state_list("records") if item.get("record_type") == "benefit_realization"]
        unverified_benefits = [item for item in benefit_records if not any(v.get("record_id") == item.get("record_id") for v in _state_list("benefit_verifications"))]
        if unverified_benefits:
            ui.markdown("#### Independent benefit review")
            benefit_to_review = ui.selectbox("Benefit record", [item["record_id"] for item in unverified_benefits], key="shoir_ii_benefit_review_id")
            review_evidence = ui.text_input("Independent verification evidence references", key="shoir_ii_benefit_review_refs")
            review_comment = ui.text_input("Reviewer comment", key="shoir_ii_benefit_review_comment")
            if ui.button("Independently verify benefit (Owner/Admin/Approver)", key="shoir_ii_benefit_review"):
                try:
                    review = verify_benefit_record(username, tier, benefit_to_review, [item.strip() for item in review_evidence.split(",") if item.strip()], review_comment)
                    ui.success(f"Independent review recorded: {review['verification_id']}.")
                except Exception as exc:
                    ui.error(f"Independent review was not recorded: {exc}")

    with workspace_tabs[3]:
        ui.markdown("#### Industry configuration")
        industry = ui.selectbox("Industry template", list(INDUSTRY_TEMPLATES), key="shoir_ii_industry_template")
        template = INDUSTRY_TEMPLATES[industry]
        ui.write("Recommended tools:", ", ".join(tool_definition(tool_id)["name"] for tool_id in template["focus"]))
        ui.write("Starter KPIs:", ", ".join(template["kpis"]))
        ui.warning(template["warning"])
        if ui.button("Save industry template selection", key="shoir_ii_industry_save"):
            try:
                create_record(username, tier, "industry_template", industry, {"industry": industry, **template}, "MANUAL")
                ui.success("Industry template configuration saved to the active workspace.")
            except Exception as exc:
                ui.error(f"Industry template selection was not saved: {exc}")
        ui.markdown("#### Cause-and-effect investigation")
        cause_title = ui.text_input("Investigation title", key="shoir_ii_cause_title")
        cause_observations = ui.text_area("Observed facts (one per line)", key="shoir_ii_cause_observations")
        cause_links_json = ui.text_area(
            "Candidate relationships JSON (SUSPECTED or SUPPORTED; supported links require registered evidence IDs)",
            value='[{"from":"material lot","to":"yield variation","relationship":"POSSIBLE_CAUSE","supporting_evidence":[],"contradicting_evidence":[],"validation_status":"SUSPECTED"}]',
            key="shoir_ii_cause_links",
        )
        if ui.button("Save cause-and-effect investigation", key="shoir_ii_cause_save"):
            try:
                links = json.loads(cause_links_json)
                if not isinstance(links, list):
                    raise IndustrialIntelligenceError("Candidate relationships must be a JSON list.")
                investigation = record_cause_effect_investigation(
                    username, tier, cause_title,
                    [item.strip() for item in cause_observations.splitlines() if item.strip()],
                    links,
                )
                ui.success(f"Investigation saved: {investigation['record_id']}. Causation remains unconfirmed.")
            except Exception as exc:
                ui.error(f"Cause-and-effect investigation was not saved: {exc}")
        investigations = [item for item in _state_list("records") if item.get("record_type") == "cause_effect_investigation"]
        if investigations:
            ui.markdown("#### Independent cause-effect review")
            selected_investigation = ui.selectbox("Investigation to review", [item["record_id"] for item in investigations], key="shoir_ii_cause_review_record")
            investigation = next(item for item in investigations if item["record_id"] == selected_investigation)
            candidate_links = investigation.get("payload", {}).get("candidate_relationships", [])
            if candidate_links:
                candidate_index = ui.selectbox(
                    "Candidate relationship",
                    list(range(len(candidate_links))),
                    format_func=lambda index: f"{candidate_links[index].get('from')} → {candidate_links[index].get('to')} · {candidate_links[index].get('validation_status')}",
                    key="shoir_ii_cause_review_link",
                )
                cause_decision = ui.selectbox("Independent review decision", ["CONFIRMED", "REJECTED"], key="shoir_ii_cause_review_decision")
                cause_evidence = ui.text_input("Registered supporting evidence record ID(s)", key="shoir_ii_cause_review_evidence")
                cause_comment = ui.text_input("Independent reviewer comment", key="shoir_ii_cause_review_comment")
                if ui.button("Submit independent cause-effect review", key="shoir_ii_cause_review_submit"):
                    try:
                        review = review_cause_effect_investigation(
                            username, tier, selected_investigation, int(candidate_index), cause_decision,
                            [item.strip() for item in cause_evidence.split(",") if item.strip()], cause_comment,
                        )
                        ui.success(f"Independent cause-effect review saved: {review['review_record']['record_id']}. Decision: {review['decision']}.")
                    except Exception as exc:
                        ui.error(f"Cause-effect review was not saved: {exc}")
        ui.markdown("#### Evidence-backed Knowledge Copilot context")
        copilot_query = ui.text_input("Question / evidence search", key="shoir_ii_copilot_query")
        if ui.button("Retrieve authorized evidence", key="shoir_ii_copilot_search"):
            try:
                result = copilot_evidence_context(username, tier, copilot_query)
                ui.session_state[STATE_PREFIX + "copilot_context"] = result
            except Exception as exc:
                ui.error(f"Evidence retrieval was blocked: {exc}")
        if ui.session_state.get(STATE_PREFIX + "copilot_context"):
            ui.json(ui.session_state[STATE_PREFIX + "copilot_context"])
            ui.caption("The returned records are evidence citations for the existing Copilot. They are not a generated root-cause conclusion.")

