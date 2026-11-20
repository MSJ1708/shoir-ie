"""Deterministic engines for the remaining Shoir-IE 100-tool targets.

The functions are deliberately explicit, input-driven and fail closed. They do
not execute arbitrary plugins, contact arbitrary connector endpoints, alter
production data, or claim that an external identity provider is active.
"""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

import numpy as np
import pandas as pd
from scipy.optimize import linprog

from shoir_rest_connector import verify_readonly_rest_connector


def _json_clone(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("Input must contain JSON-safe values only.") from exc


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _nonempty_text(value: Any, field: str, limit: int = 500) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required.")
    if len(text) > limit:
        raise ValueError(f"{field} must be at most {limit} characters.")
    return text


def _number(value: Any, field: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{field} must be a finite number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number.")
    if minimum is not None and result < minimum:
        raise ValueError(f"{field} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise ValueError(f"{field} must be at most {maximum}.")
    return result


def _records(value: Any, field: str, *, minimum: int = 1, maximum: int = 5000) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{field} must be a JSON list containing {minimum} to {maximum} records.")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError(f"Every item in {field} must be a JSON object.")
    return _json_clone(value)


def _configuration_value(name: str) -> str:
    """Read a named secret/config value without ever returning it to the UI."""
    value = os.environ.get(name, "")
    if value and value.strip():
        return value.strip()
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
        return str(value or "").strip()
    except Exception:
        # Secrets may be absent in local tests or a non-Streamlit invocation.
        return ""


def _utc_timestamp(value: Any, field: str, *, allow_missing: bool = False) -> datetime | None:
    if value is None or not str(value).strip():
        if allow_missing:
            return None
        raise ValueError(f"{field} is required and must include a UTC offset or Z.")
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a UTC offset or Z.")
    return parsed.astimezone(timezone.utc)


def recovery_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Apply an undo/redo/recover action to a caller-supplied revision history."""
    action = str(payload.get("action", "snapshot")).strip().lower()
    if action not in {"snapshot", "undo", "redo", "recover"}:
        raise ValueError("action must be one of snapshot, undo, redo, or recover.")
    state_history = payload.get("history", [])
    if not isinstance(state_history, list):
        raise ValueError("history must be a JSON list.")
    history = _json_clone(state_history)
    if any(not isinstance(item, dict) or not {"state", "snapshot_id", "state_hash"}.issubset(item) for item in history):
        raise ValueError("Every history entry must include state, snapshot_id and state_hash.")
    if len(history) > 1000:
        raise ValueError("history may contain at most 1,000 snapshots.")
    seen_snapshot_ids: set[str] = set()
    for item in history:
        snapshot_id = _nonempty_text(item.get("snapshot_id"), "history.snapshot_id", 120)
        if snapshot_id in seen_snapshot_ids:
            raise ValueError("Revision history contains duplicate snapshot IDs; refusing ambiguous recovery.")
        seen_snapshot_ids.add(snapshot_id)
        if item["state_hash"] != _canonical_hash(item["state"]):
            raise ValueError("Revision history integrity check failed; refusing to recover altered state.")
    index = int(payload.get("current_index", len(history) - 1))
    if history:
        if index < 0 or index >= len(history):
            raise ValueError("current_index is outside the supplied history.")
    elif action in {"undo", "redo", "recover"}:
        raise ValueError(f"{action} requires at least one valid snapshot.")
    if action == "snapshot":
        if "state" not in payload:
            raise ValueError("state is required when action is snapshot.")
        state = payload.get("state")
        cloned = _json_clone(state)
        # Discard redo history after a new edit, following standard editor semantics.
        history = history[: index + 1] if history else []
        next_revision = (int(history[index].get("revision", index)) + 1) if history else 0
        snapshot_id = f"rev-{next_revision}-{_canonical_hash(cloned)[:16]}"
        history.append({
            "snapshot_id": snapshot_id,
            "revision": next_revision,
            "created_at": str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
            "state_hash": _canonical_hash(cloned),
            "state": cloned,
        })
        index = len(history) - 1
    elif action == "undo":
        if index == 0:
            raise ValueError("Cannot undo: the current snapshot is already the earliest revision.")
        index -= 1
    elif action == "redo":
        if index >= len(history) - 1:
            raise ValueError("Cannot redo: there is no later revision in the supplied history.")
        index += 1
    else:  # explicit recovery to a known snapshot
        wanted = _nonempty_text(payload.get("snapshot_id"), "snapshot_id", 120)
        matches = [i for i, item in enumerate(history) if str(item.get("snapshot_id", "")) == wanted]
        if not matches:
            raise ValueError("snapshot_id was not found in the verified revision history.")
        index = matches[0]
    active = _json_clone(history[index]["state"])
    return {
        "tool_id": "T006",
        "status": "RECOVERY_ACTION_APPLIED",
        "action": action,
        "current_index": index,
        "current_revision": history[index].get("revision", index),
        "current_snapshot_id": history[index].get("snapshot_id"),
        "state_hash": _canonical_hash(active),
        "current_state": active,
        "history": history,
        "can_undo": index > 0,
        "can_redo": index < len(history) - 1,
        "warning": "This engine operates on the history supplied in this request. Durable cross-session recovery depends on the caller saving the returned history to the authenticated workspace store.",
    }


def dataset_version_lineage(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create a content-addressed dataset version and flag stale downstream runs."""
    name = _nonempty_text(payload.get("dataset_name"), "dataset_name", 200)
    source = _nonempty_text(payload.get("source"), "source", 500)
    dataset = payload.get("records", payload.get("dataset"))
    if not isinstance(dataset, (dict, list)):
        raise ValueError("records (list/object) or dataset (list/object) is required.")
    dataset = _json_clone(dataset)
    transformations = payload.get("transformations", [])
    if not isinstance(transformations, list):
        raise ValueError("transformations must be a JSON list.")
    transformations = _json_clone(transformations)
    history = payload.get("history", [])
    if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
        raise ValueError("history must be a list of version objects.")
    if len(history) > 1000:
        raise ValueError("history may contain at most 1,000 version objects.")
    digest = _canonical_hash({"dataset": dataset, "transformations": transformations})
    previous = history[-1] if history else None
    supplied_parent = str(payload.get("parent_version_id") or (previous or {}).get("version_id") or "").strip()
    version_number = len(history) + 1
    version_id = f"ds-{digest[:12]}-v{version_number}"
    record = {
        "version_id": version_id,
        "dataset_name": name,
        "version_number": version_number,
        "content_sha256": digest,
        "source": source,
        "created_at": str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "parent_version_id": supplied_parent or None,
        "transformations": transformations,
        "schema": sorted(dataset[0].keys()) if isinstance(dataset, list) and dataset and isinstance(dataset[0], dict) else (sorted(dataset.keys()) if isinstance(dataset, dict) else []),
        "record_count": len(dataset) if isinstance(dataset, list) else None,
        "provenance": str(payload.get("provenance") or "USER_ENTERED_UNVERIFIED"),
    }
    downstream = payload.get("downstream_runs", [])
    if not isinstance(downstream, list) or any(not isinstance(item, dict) for item in downstream):
        raise ValueError("downstream_runs must be a list of run objects.")
    stale = []
    for run in downstream:
        run_hash = str(run.get("dataset_sha256") or run.get("dataset_hash") or "")
        run_version = str(run.get("dataset_version_id") or "")
        stale_run = (run_hash != digest) if run_hash else (bool(run_version) and run_version != version_id)
        if stale_run:
            stale.append({
                "run_id": str(run.get("run_id") or "UNNAMED_RUN"),
                "reason": "The run references a different dataset hash or version.",
                "referenced_hash": run_hash or None,
                "referenced_version_id": run_version or None,
            })
    updated_history = _json_clone(history) + [record]
    return {
        "tool_id": "T020",
        "status": "DATASET_VERSION_CREATED",
        "version": record,
        "history": updated_history,
        "history_count": len(updated_history),
        "stale_downstream_runs": stale,
        "stale_run_count": len(stale),
        "warning": "The record is content-addressed, but immutability and downstream invalidation are enforced only when the calling workspace persists this returned history and gates later runs on its hash.",
    }


def capa_lifecycle_review(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run the existing 8D completeness checks and append explicit transition audit."""
    from shoir_target_engines import assess_capa_8d_records

    records = _records(payload.get("records"), "records", maximum=5000)
    base = assess_capa_8d_records(records, as_of_date=payload.get("as_of_date"))
    requested = payload.get("transitions", [])
    if not isinstance(requested, list) or any(not isinstance(item, dict) for item in requested):
        raise ValueError("transitions must be a list of transition objects.")
    by_id = {str(row.get("capa_id", "")).casefold(): row for row in records}
    allowed = {
        "OPEN": {"IN_PROGRESS"},
        "IN_PROGRESS": {"PENDING_EFFECTIVENESS", "CLOSED"},
        "PENDING_EFFECTIVENESS": {"IN_PROGRESS", "CLOSED"},
        "CLOSED": set(),
    }
    audit = []
    for transition in requested:
        capa_id = _nonempty_text(transition.get("capa_id"), "transition.capa_id", 100)
        if capa_id.casefold() not in by_id:
            raise ValueError(f"Transition refers to unknown CAPA ID: {capa_id}.")
        before = str(by_id[capa_id.casefold()].get("status", "OPEN")).upper()
        after = str(transition.get("to_status", "")).upper()
        if after not in allowed.get(before, set()):
            raise ValueError(f"Invalid CAPA transition for {capa_id}: {before} -> {after}.")
        reviewer = _nonempty_text(transition.get("reviewer"), "transition.reviewer", 200)
        reason = _nonempty_text(transition.get("reason"), "transition.reason", 1000)
        approval = str(transition.get("approval_reference") or "").strip()
        if after == "CLOSED" and (not approval or not str(by_id[capa_id.casefold()].get("effectiveness_evidence") or "").strip()):
            raise ValueError(f"CAPA {capa_id} cannot be closed without an approval_reference and effectiveness_evidence.")
        transition_time = _utc_timestamp(transition.get("transitioned_at"), "transition.transitioned_at", allow_missing=True) or datetime.now(timezone.utc)
        audit.append({
            "capa_id": capa_id,
            "from_status": before,
            "to_status": after,
            "reviewer": reviewer,
            "reason": reason,
            "approval_reference": approval or None,
            "transitioned_at": transition_time.isoformat(),
            "source": "USER_ENTERED_UNVERIFIED",
        })
        by_id[capa_id.casefold()]["status"] = after
        if approval:
            by_id[capa_id.casefold()]["approval_reference"] = approval
        by_id[capa_id.casefold()]["reviewer"] = reviewer
    if requested:
        base = assess_capa_8d_records(list(by_id.values()), as_of_date=payload.get("as_of_date"))
    base.update({
        "tool_id": "T039",
        "transition_audit": audit,
        "transition_count": len(audit),
        "warning": "CAPA/8D lifecycle checks validate record completeness and allowed status transitions. They do not certify cause validity, action effectiveness, regulatory compliance, or engineering safety.",
    })
    return base


def supply_chain_network_plan(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Solve a minimum-cost supplier-to-customer allocation with explicit shortages."""
    suppliers = _records(payload.get("suppliers"), "suppliers", maximum=2000)
    customers = _records(payload.get("customers"), "customers", maximum=2000)
    routes = _records(payload.get("routes"), "routes", maximum=10000)
    sids = [_nonempty_text(s.get("id"), "supplier.id", 120) for s in suppliers]
    cids = [_nonempty_text(c.get("id"), "customer.id", 120) for c in customers]
    if len(set(sids)) != len(sids) or len(set(cids)) != len(cids):
        raise ValueError("Supplier IDs and customer IDs must be unique.")
    supply = [_number(s.get("supply"), f"supplier {sids[i]} supply", minimum=0) for i, s in enumerate(suppliers)]
    demand = [_number(c.get("demand"), f"customer {cids[i]} demand", minimum=0) for i, c in enumerate(customers)]
    supplier_idx = {key: i for i, key in enumerate(sids)}
    customer_idx = {key: i for i, key in enumerate(cids)}
    parsed_routes = []
    max_cost = 0.0
    for route in routes:
        src = _nonempty_text(route.get("supplier"), "route.supplier", 120)
        dst = _nonempty_text(route.get("customer"), "route.customer", 120)
        if src not in supplier_idx or dst not in customer_idx:
            raise ValueError(f"Route {src} -> {dst} refers to an unknown supplier/customer.")
        cap = _number(route.get("capacity"), f"route {src}->{dst} capacity", minimum=0)
        cost = _number(route.get("unit_cost"), f"route {src}->{dst} unit_cost", minimum=0)
        if any(item["supplier"] == src and item["customer"] == dst for item in parsed_routes):
            raise ValueError(f"Duplicate route {src} -> {dst} is not allowed; merge its capacity/cost definition explicitly.")
        max_cost = max(max_cost, cost)
        parsed_routes.append({"supplier": src, "customer": dst, "capacity": cap, "unit_cost": cost})
    if not parsed_routes:
        raise ValueError("At least one permitted route is required.")
    # Penalize shortage by more than every single route cost so the solver fills
    # feasible demand before trading it for lower-cost shortage variables.
    penalty = _number(payload.get("shortage_penalty", max(1.0, max_cost + 1.0) * 1000.0), "shortage_penalty", minimum=max_cost + 1e-9)
    nr, nc = len(parsed_routes), len(customers)
    objective = np.array([r["unit_cost"] for r in parsed_routes] + [penalty] * nc, dtype=float)
    a_ub, b_ub = [], []
    for si, sid in enumerate(sids):
        row = [1.0 if route["supplier"] == sid else 0.0 for route in parsed_routes] + [0.0] * nc
        a_ub.append(row)
        b_ub.append(supply[si])
    a_eq, b_eq = [], []
    for ci, cid in enumerate(cids):
        row = [-1.0 if route["customer"] == cid else 0.0 for route in parsed_routes] + [1.0 if j == ci else 0.0 for j in range(nc)]
        a_eq.append(row)
        b_eq.append(-demand[ci])
    # Rewrite equality as inflow + shortage = demand.
    a_eq = [[-value for value in row[:-nc]] + row[-nc:] for row in a_eq]
    b_eq = demand
    bounds = [(0.0, r["capacity"]) for r in parsed_routes] + [(0.0, d) for d in demand]
    solved = linprog(
        objective,
        A_ub=np.array(a_ub, dtype=float) if a_ub else None,
        b_ub=np.array(b_ub, dtype=float) if b_ub else None,
        A_eq=np.array(a_eq, dtype=float),
        b_eq=np.array(b_eq, dtype=float),
        bounds=bounds,
        method="highs",
    )
    if not solved.success or solved.x is None:
        raise ValueError(f"Supply-chain optimization failed safely: {solved.message}")
    allocations = []
    for i, route in enumerate(parsed_routes):
        amount = float(solved.x[i])
        if amount > 1e-8:
            allocations.append({**route, "allocated_units": amount, "extended_cost": amount * route["unit_cost"]})
    shortages = [
        {"customer": cid, "demand": demand[i], "shortage_units": float(solved.x[nr + i])}
        for i, cid in enumerate(cids)
    ]
    total_demand = sum(demand)
    total_shipped = sum(item["allocated_units"] for item in allocations)
    return {
        "tool_id": "T060",
        "status": "OPTIMAL_ALLOCATION_WITH_SHORTAGE_CHECK",
        "solver_status": "OPTIMAL",
        "total_supply": float(sum(supply)),
        "total_demand": float(total_demand),
        "units_shipped": float(total_shipped),
        "units_short": float(sum(item["shortage_units"] for item in shortages)),
        "fill_rate_pct": (100.0 * total_shipped / total_demand) if total_demand else 100.0,
        "transport_cost": float(sum(item["extended_cost"] for item in allocations)),
        "shortage_penalty_used": penalty,
        "allocations": allocations,
        "customer_shortages": shortages,
        "assumptions": "Single-period direct supplier-to-customer network; no intermediate nodes, fixed costs, lead-time constraints or multi-period inventory.",
        "warning": "This deterministic allocation is only as valid as its supplied capacities, costs, routes and demand. It is not a live supply-chain feed or an approved dispatch instruction.",
    }


def calibrate_digital_twin(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Fit an affine calibration from simulated to measured observations."""
    simulated = payload.get("simulated_values")
    measured = payload.get("measured_values")
    if not isinstance(simulated, list) or not isinstance(measured, list) or len(simulated) != len(measured) or len(simulated) < 3:
        raise ValueError("simulated_values and measured_values must be equal-length numeric lists with at least three pairs.")
    x = np.array([_number(v, "simulated value") for v in simulated], dtype=float)
    y = np.array([_number(v, "measured value") for v in measured], dtype=float)
    if np.ptp(x) <= 1e-12:
        raise ValueError("simulated_values must vary; a calibration scale cannot be estimated from a constant series.")
    scale_bounds = payload.get("scale_bounds", [0.0, float("inf")])
    offset_bounds = payload.get("offset_bounds", [float("-inf"), float("inf")])
    if not isinstance(scale_bounds, list) or len(scale_bounds) != 2 or not isinstance(offset_bounds, list) or len(offset_bounds) != 2:
        raise ValueError("scale_bounds and offset_bounds must be [lower, upper] lists.")
    lo_scale = float(scale_bounds[0])
    hi_scale = float(scale_bounds[1])
    lo_offset = float(offset_bounds[0])
    hi_offset = float(offset_bounds[1])
    if math.isnan(lo_scale) or math.isnan(hi_scale) or math.isnan(lo_offset) or math.isnan(hi_offset) or lo_scale >= hi_scale or lo_offset >= hi_offset:
        raise ValueError("Calibration bounds must be ordered with lower values strictly below upper values, and cannot be NaN.")
    from scipy.optimize import lsq_linear
    design = np.column_stack([x, np.ones_like(x)])
    try:
        fitted = lsq_linear(design, y, bounds=([lo_scale, lo_offset], [hi_scale, hi_offset]))
    except (ValueError, RuntimeError) as exc:
        raise ValueError("Calibration optimizer rejected the bounds or input; no calibrated parameters were returned.") from exc
    if not fitted.success:
        raise ValueError("Calibration optimizer did not converge; no calibrated parameters were returned.")
    scale, offset = map(float, fitted.x)
    predicted = scale * x + offset
    residual = y - predicted
    ss_total = float(np.sum((y - np.mean(y)) ** 2))
    ss_res = float(np.sum(residual ** 2))
    r2 = 1.0 if ss_total <= 1e-12 and ss_res <= 1e-12 else (None if ss_total <= 1e-12 else 1.0 - ss_res / ss_total)
    data = pd.DataFrame({
        "observation": list(range(1, len(x) + 1)),
        "simulated": x,
        "measured": y,
        "calibrated_prediction": predicted,
        "residual_measured_minus_prediction": residual,
    })
    return {
        "tool_id": "T074",
        "status": "CALIBRATION_FIT_COMPUTED",
        "method": "Bounded least-squares affine correction y_calibrated = scale * y_simulated + offset",
        "scale": scale,
        "offset": offset,
        "rmse": float(np.sqrt(np.mean(residual ** 2))),
        "mae": float(np.mean(np.abs(residual))),
        "r_squared": r2,
        "sample_count": int(len(x)),
        "fit_success": True,
        "fit_data": data,
        "warning": "This is an empirical affine fit, not calibration of a physical/digital-twin model's internal parameters. Use approved measured data, preserve units/time alignment, and validate on a separate holdout set before operational decisions.",
        "data_provenance": str(payload.get("data_provenance") or "USER_ENTERED_UNVERIFIED"),
    }


def simulate_industrial_disruptions(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compare explicit production/logistics capacity and demand shock scenarios."""
    base_capacity = _number(payload.get("baseline_capacity"), "baseline_capacity", minimum=0)
    base_demand = _number(payload.get("baseline_demand"), "baseline_demand", minimum=0)
    unit_cost = _number(payload.get("unit_cost", 0), "unit_cost", minimum=0)
    base_lead = _number(payload.get("baseline_lead_time_hours", 0), "baseline_lead_time_hours", minimum=0)
    scenarios = _records(payload.get("scenarios"), "scenarios", maximum=1000)
    expanded = [{"scenario": "BASELINE", "capacity_loss_pct": 0, "demand_change_pct": 0, "lead_time_multiplier": 1, "recovery_capacity_add": 0, "unit_cost_change_pct": 0}] + scenarios
    rows = []
    for raw in expanded:
        name = _nonempty_text(raw.get("scenario"), "scenario", 150)
        capacity_loss = _number(raw.get("capacity_loss_pct", 0), f"{name}.capacity_loss_pct", minimum=0, maximum=100)
        demand_change = _number(raw.get("demand_change_pct", 0), f"{name}.demand_change_pct", minimum=-100)
        lead_mult = _number(raw.get("lead_time_multiplier", 1), f"{name}.lead_time_multiplier", minimum=0)
        recovery_add = _number(raw.get("recovery_capacity_add", 0), f"{name}.recovery_capacity_add", minimum=0)
        cost_change = _number(raw.get("unit_cost_change_pct", 0), f"{name}.unit_cost_change_pct", minimum=-100)
        capacity = base_capacity * (1.0 - capacity_loss / 100.0) + recovery_add
        demand = base_demand * (1.0 + demand_change / 100.0)
        throughput = min(capacity, demand)
        shortage = max(0.0, demand - throughput)
        rows.append({
            "scenario": name,
            "effective_capacity": capacity,
            "demand": demand,
            "throughput": throughput,
            "shortage_units": shortage,
            "service_level_pct": (100.0 * throughput / demand) if demand else 100.0,
            "lead_time_hours": base_lead * lead_mult,
            "unit_cost": unit_cost * (1 + cost_change / 100.0),
            "throughput_cost": throughput * unit_cost * (1 + cost_change / 100.0),
            "capacity_loss_pct": capacity_loss,
            "recovery_capacity_add": recovery_add,
        })
    frame = pd.DataFrame(rows)
    baseline = frame.iloc[0]
    frame["shortage_delta_vs_baseline"] = frame["shortage_units"] - float(baseline["shortage_units"])
    frame["throughput_delta_vs_baseline"] = frame["throughput"] - float(baseline["throughput"])
    return {
        "tool_id": "T080",
        "status": "SCENARIOS_SIMULATED",
        "scenario_count": len(frame) - 1,
        "results": frame,
        "baseline": frame.iloc[0].to_dict(),
        "best_service_scenario": str(frame.iloc[1:]["scenario"].iloc[int(frame.iloc[1:]["service_level_pct"].to_numpy().argmax())]) if len(frame) > 1 else "BASELINE",
        "warning": "Deterministic what-if analysis from declared assumptions. Values are not forecasts, calibrated plant behavior or proof of recovery feasibility; all inputs and units require review.",
        "data_provenance": str(payload.get("data_provenance") or "SYNTHETIC_SCENARIO"),
    }


def evaluate_kpi_alerts(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Backward-compatible T094 adapter to the single canonical KPI alert engine.

    Older callers provide one threshold per KPI record and use measured_at /
    max_age_minutes. Normalize that contract here; do not maintain a second alert
    identity or freshness implementation.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("KPI alert input must be a JSON object.")
    raw_kpis = _records(payload.get("kpis"), "kpis", maximum=5000)
    if not raw_kpis:
        raise ValueError("Provide at least one KPI record.")
    history = payload.get("existing_alerts", [])
    if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
        raise ValueError("existing_alerts must be a list of prior alert objects.")

    normalized_records: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []
    canonical_id_by_legacy_fingerprint: dict[str, str] = {}
    canonical_id_by_legacy_alert_id: dict[str, str] = {}
    canonical_id_by_rule_name: dict[tuple[str, str], str] = {}

    for index, item in enumerate(raw_kpis, start=1):
        name = _nonempty_text(item.get("name", item.get("kpi", "")), f"kpis[{index}].name", 200)
        value = _number(item.get("value"), f"{name}.value")
        threshold = _number(item.get("threshold"), f"{name}.threshold")
        operator = str(item.get("operator", "gt")).strip().lower()
        operator = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte"}.get(operator, operator)
        if operator not in {"gt", "gte", "lt", "lte", "=="}:
            raise ValueError(f"{name}.operator must be one of gt, gte, lt, lte, >, >=, <, <=, ==.")
        supplied_rule_id = str(item.get("rule_id") or "").strip()
        legacy_fingerprint_payload: dict[str, Any] = {
            "name": name.casefold(),
            "operator": operator,
            "threshold": threshold,
        }
        if supplied_rule_id:
            legacy_fingerprint_payload["rule_id"] = supplied_rule_id
        legacy_fingerprint = _canonical_hash(legacy_fingerprint_payload)
        rule_id = supplied_rule_id or (
            "KPI-" + _canonical_hash({
                "name": name.casefold(),
                "operator": operator,
                "threshold": threshold,
            })[:24].upper()
        )
        canonical_identity = rule_id + "::" + name.casefold()
        canonical_id = "ALT-" + hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest()[:20].upper()
        canonical_id_by_legacy_fingerprint[legacy_fingerprint] = canonical_id
        canonical_id_by_legacy_alert_id["alert-" + legacy_fingerprint[:16]] = canonical_id
        canonical_id_by_rule_name[(rule_id.casefold(), name.casefold())] = canonical_id

        severity = str(item.get("severity") or "WARNING").strip().upper()
        source = str(item.get("source") or "USER_ENTERED_UNVERIFIED").strip()
        measured_at = item.get("measured_at", item.get("observed_at"))
        record: dict[str, Any] = {
            "kpi": name,
            "value": value,
            "unit": str(item.get("unit") or ""),
            "observed_at": measured_at,
            "source": source,
        }
        record["max_age_minutes"] = _number(
            item.get("max_age_minutes", 60), f"{name}.max_age_minutes"
        )
        normalized_records.append(record)
        rules.append({
            "rule_id": rule_id,
            "kpi": name,
            "operator": operator,
            "threshold": threshold,
            "severity": severity,
        })

    previous_open_ids: set[str] = set()
    for prior in history:
        if str(prior.get("state", "OPEN")).upper() not in {"OPEN", "OPEN_UNVERIFIED"}:
            continue
        fingerprint = str(prior.get("fingerprint") or "").strip()
        prior_id = str(prior.get("alert_id") or "").strip()
        mapped_id = (
            canonical_id_by_legacy_fingerprint.get(fingerprint)
            or canonical_id_by_legacy_alert_id.get(prior_id)
        )
        if not mapped_id:
            prior_rule_id = str(prior.get("rule_id") or "").strip()
            prior_name = str(prior.get("name") or prior.get("kpi") or "").strip()
            if prior_rule_id and prior_name:
                mapped_id = canonical_id_by_rule_name.get((prior_rule_id.casefold(), prior_name.casefold()))
        if mapped_id:
            previous_open_ids.add(mapped_id)
        elif prior_id.startswith("ALT-"):
            previous_open_ids.add(prior_id)
        elif fingerprint.startswith("ALT-"):
            previous_open_ids.add(fingerprint)

    as_of = payload.get("as_of")
    try:
        from shoir_target_engines import evaluate_kpi_alerts as evaluate_canonical_kpi_alerts
    except Exception as exc:
        raise RuntimeError("The canonical KPI alert engine is unavailable.") from exc
    result = evaluate_canonical_kpi_alerts(
        normalized_records,
        rules,
        as_of=as_of,
        stale_after_hours=float(payload.get("stale_after_hours", 24.0)),
        previous_open_alert_ids=sorted(previous_open_ids),
    )
    kpi_frame = result["kpis"]
    stale_count = int((kpi_frame["freshness"] == "STALE").sum()) if not kpi_frame.empty else 0
    alert_frame = result["alerts"]
    if not alert_frame.empty:
        alert_frame = alert_frame[alert_frame["Event"].isin(["NEW", "CONTINUING", "UNVERIFIED"])].copy()
    result.update({
        "tool_id": "T094",
        "status": "KPI_EVALUATION_COMPLETE",
        "stale_kpi_count": stale_count,
        "kpis": kpi_frame,
        "alerts": alert_frame,
        "data_provenance": "USER_ENTERED_UNVERIFIED",
        "warning": (
            "KPI rules use user-entered readings unless an approved source is explicitly supplied. "
            "Stale, future, invalid-timestamp, missing or unidentified-source readings cannot create a new alert "
            "or resolve an existing one. An existing alert remains open-but-unverified until a fresh valid reading "
            "proves recovery. No email, SMS or external notification is sent."
        ),
    })
    return result


def _require_connector_operator() -> None:
    """Require an authenticated, entitled admin before a live connector operation."""
    try:
        import streamlit as st
        state = st.session_state
        authenticated = bool(state.get("authenticated"))
        actor = str(state.get("current_user") or "").strip()
        role = str(state.get("user_role") or state.get("current_role") or "").strip().casefold()
        role = role.replace("_", " ").replace("-", " ")
        tier = state.get("user_tier")
    except Exception as exc:
        raise PermissionError("Sign in with an authorized Enterprise administrator account before testing a connector.") from exc
    if not authenticated or not actor or actor.casefold() in {"guest", "unknown", "anonymous"}:
        raise PermissionError("Sign in with an authorized Enterprise administrator account before testing a connector.")
    if role not in {"owner", "admin", "enterprise admin"}:
        raise PermissionError("Only an authorized workspace owner or administrator may run a live connector test.")
    try:
        from shoir_tool_registry import tier_allows_tool
        if not tier_allows_tool(tier, "T096"):
            raise PermissionError("The current subscription tier does not permit Integration Management Center operations.")
    except PermissionError:
        raise
    except Exception as exc:
        raise PermissionError("Connector access could not be verified; the operation was denied.") from exc



def _verify_provider_erp_read(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run a server-configured, staging-only SAP/Oracle read and return metadata only."""
    profile = payload.get("profile")
    if not isinstance(profile, Mapping):
        raise ValueError("profile must be a JSON object containing connection_id and resource_key.")
    connection_id = _nonempty_text(profile.get("connection_id"), "connection_id", 120)
    resource_key = _nonempty_text(profile.get("resource_key"), "resource_key", 80)

    _require_connector_operator()
    try:
        import durable_account_store
        environment = str(durable_account_store.APP_ENVIRONMENT or "").strip().casefold()
    except Exception as exc:
        raise PermissionError("The application environment could not be verified; provider reads are denied.") from exc
    if environment != "staging":
        raise PermissionError("SAP/Oracle provider reads are available only in the authorized staging environment.")

    try:
        import streamlit as st
        state = st.session_state
        actor = str(state.get("current_user") or "").strip()
        session_token = str(state.get("remote_session_token") or "").strip()
    except Exception as exc:
        raise PermissionError("The active user and session could not be verified; no provider request was sent.") from exc
    if not actor or not session_token:
        raise PermissionError("An active Shoir-IE session is required for provider reads.")

    # Verify the actual server-side account/session and entitlement. The UI's
    # role/tier values are only a preliminary gate; they are not authoritative.
    server_session = durable_account_store._edge_call(
        "session_verify",
        {"username": actor, "token": session_token},
    )
    if (
        not isinstance(server_session, dict)
        or server_session.get("ok") is not True
        or str(server_session.get("username") or "").casefold() != actor.casefold()
        or server_session.get("active") is not True
    ):
        raise PermissionError("The server could not verify an active Shoir-IE session.")
    server_role = str(server_session.get("role") or "").strip().casefold().replace("_", " ").replace("-", " ")
    if server_role not in {"owner", "admin", "enterprise admin"}:
        raise PermissionError("The server-side account role does not permit an ERP integration read.")
    from shoir_tool_registry import tier_allows_tool
    server_tier = server_session.get("tier")
    if not tier_allows_tool(server_tier, "T096"):
        raise PermissionError("The server-side subscription tier does not permit Integration Management Center operations.")

    # Resolve shared workspace context from the canonical account-store helper,
    # then ask the Edge Function to enforce the Owner/Admin manage permission.
    shared_context = durable_account_store._active_organization_workspace_context()
    if shared_context is not None:
        manage_result = durable_account_store.edge_organization_action(
            "workspace_manage_check",
            actor,
            session_token,
            organization_id=shared_context["organization_id"],
            organization_workspace_id=shared_context["organization_workspace_id"],
        )
        if not isinstance(manage_result, dict) or manage_result.get("ok") is not True:
            raise PermissionError("Owner/Admin permission for the selected organization workspace could not be verified.")
        active_workspace_id = shared_context["organization_workspace_id"]
    else:
        active_workspace_id = str(
            state.get("active_workspace_id")
            or state.get("workspace_id")
            or "default"
        ).strip()
    if not active_workspace_id:
        raise PermissionError("An active workspace is required for provider reads.")

    def load_server_json(setting: str) -> dict[str, Any]:
        raw = _configuration_value(setting)
        if not raw:
            raise PermissionError(f"Required server-side setting {setting} is not configured.")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Server-side setting {setting} must contain valid JSON.") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Server-side setting {setting} must be a JSON object.")
        return value

    connection_catalog = load_server_json("SHOIR_ERP_CONNECTIONS_JSON")
    credential_catalog = load_server_json("SHOIR_ERP_CREDENTIALS_JSON")
    entry = connection_catalog.get(connection_id)
    if not isinstance(entry, Mapping):
        raise PermissionError("The selected ERP connection is not present in the server-side allowlist.")
    connection_data = entry.get("connection", entry)
    bindings = entry.get("bindings")
    if not isinstance(connection_data, Mapping) or not isinstance(bindings, Mapping):
        raise ValueError("The server-side ERP connection must define connection metadata and resource bindings.")
    binding_data = bindings.get(resource_key)
    if not isinstance(binding_data, Mapping):
        raise PermissionError("The selected ERP resource is not configured for this connection.")

    product_id = _nonempty_text(connection_data.get("product_id"), "connection.product_id", 80).upper()
    if product_id not in {
        "SAP_S4HANA_CLOUD_PUBLIC",
        "SAP_S4HANA_CLOUD_PRIVATE",
        "ORACLE_FUSION_ERP",
        "ORACLE_FUSION_SCM",
    }:
        raise PermissionError("Only the supported SAP S/4HANA Cloud and Oracle Fusion product profiles have a provider transport.")
    configured_workspace = _nonempty_text(connection_data.get("workspace_id"), "connection.workspace_id", 120)
    if configured_workspace != active_workspace_id:
        raise PermissionError("The ERP connection is not scoped to the currently active workspace.")
    if connection_data.get("enabled") is not True or connection_data.get("read_only") is not True:
        raise PermissionError("The server-side ERP connection must be explicitly enabled and read-only.")

    from shoir_erp_connectors import (
        ERPConnectionProfile,
        ERPResourceBinding,
        _host_port_from_allowlist,
    )
    from shoir_erp_provider_transport import read_provider_resource
    from shoir_rest_connector import _parse_approved_private_cidrs

    allowed_hosts_raw = _configuration_value("SHOIR_ERP_ALLOWED_HOSTS")
    if not allowed_hosts_raw:
        raise PermissionError("The server-side ERP hostname allowlist is not configured.")
    allowed_hosts = {
        _host_port_from_allowlist(item.strip())
        for item in re.split(r"[;,]", allowed_hosts_raw)
        if item.strip()
    }
    if not allowed_hosts:
        raise PermissionError("The server-side ERP hostname allowlist is empty.")
    approved_private_networks = _parse_approved_private_cidrs(
        _configuration_value("SHOIR_ERP_APPROVED_PRIVATE_CIDRS")
    )
    timeout_raw = _configuration_value("SHOIR_ERP_TIMEOUT_SECONDS") or "8"
    try:
        timeout_seconds = float(timeout_raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("SHOIR_ERP_TIMEOUT_SECONDS must be a finite number between 0.5 and 10.") from exc
    if not math.isfinite(timeout_seconds) or not 0.5 <= timeout_seconds <= 10:
        raise ValueError("SHOIR_ERP_TIMEOUT_SECONDS must be a finite number between 0.5 and 10.")

    credential_ref = _nonempty_text(connection_data.get("credential_ref"), "connection.credential_ref", 400)

    def resolve_credential(reference: str) -> Mapping[str, Any]:
        value = credential_catalog.get(reference)
        if not isinstance(value, Mapping):
            raise PermissionError("The server-side OAuth credential reference is not configured.")
        return value

    connection = ERPConnectionProfile(
        product_id=product_id,
        workspace_id=configured_workspace,
        connection_id=connection_id,
        tenant_ref=_nonempty_text(connection_data.get("tenant_ref"), "connection.tenant_ref", 100),
        base_url=_nonempty_text(connection_data.get("base_url"), "connection.base_url", 2048),
        credential_ref=credential_ref,
        enabled=True,
        read_only=True,
    )
    binding = ERPResourceBinding(
        resource_key=resource_key,
        source_path=_nonempty_text(binding_data.get("source_path"), "binding.source_path", 512),
        records_path=str(binding_data.get("records_path") or ""),
        entity_type=_nonempty_text(binding_data.get("entity_type"), "binding.entity_type", 40),
        id_path=_nonempty_text(binding_data.get("id_path"), "binding.id_path", 256),
        field_map=binding_data.get("field_map") if isinstance(binding_data.get("field_map"), Mapping) else {},
        required_fields=tuple(binding_data.get("required_fields") or ()),
        units=binding_data.get("units") if isinstance(binding_data.get("units"), Mapping) else {},
        currency_path=str(binding_data.get("currency_path") or ""),
        source_timestamp_path=str(binding_data.get("source_timestamp_path") or ""),
        source_timezone=str(binding_data.get("source_timezone") or ""),
        mapping_version=str(binding_data.get("mapping_version") or "1"),
        max_records=int(binding_data.get("max_records") or 5000),
        max_pages=int(binding_data.get("max_pages") or 20),
    )

    def authorize(request_actor: str, request_workspace: str, request_connection: str, request_resource: str) -> bool:
        return (
            request_actor == actor
            and request_workspace == active_workspace_id
            and request_connection == connection_id
            and request_resource == resource_key
        )

    result = read_provider_resource(
        connection,
        binding,
        actor_id=actor,
        active_workspace_id=active_workspace_id,
        allowed_hosts=allowed_hosts,
        authorize=authorize,
        credential_resolver=resolve_credential,
        approved_private_networks=approved_private_networks,
        timeout_seconds=timeout_seconds,
    )
    # Do not hydrate or persist provider records from this verification action.
    # Return only bounded status, counts and a content digest to the Workbench.
    return {
        "tool_id": "T096",
        "status": result["status"],
        "product_id": result["product_id"],
        "connection_ref": connection_id,
        "resource_key": result["resource_key"],
        "read_only": True,
        "pages_read": int(result["pages_read"]),
        "record_count": int(result["record_count"]),
        "rejected_record_count": int(result["rejected_record_count"]),
        "duplicate_record_count": int(result["duplicate_record_count"]),
        "conflicting_duplicate_count": int(result["conflicting_duplicate_count"]),
        "truncated": bool(result["truncated"]),
        "mapping_version": result["mapping_version"],
        "records_sha256": result["records_sha256"],
        "read_at_utc": result["read_at_utc"],
        "data_provenance": "EXTERNAL_PROVIDER_READ_UNVERIFIED",
        "warning": (
            "A staging provider read completed. No provider records were persisted or synchronized. "
            "This does not establish ongoing connectivity, production readiness or independent vendor acceptance."
        ),
    }



def integration_configuration_status(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Inspect configuration or explicitly test a server-configured read-only REST connector.

    Configuration inspection is the default and never performs network access.
    Live REST reads and provider-aware SAP/Oracle reads are separate, explicit,
    staging-only actions. Credentials, connection metadata and host allowlists
    are resolved from server-side configuration, not from Workbench payloads.
    """
    action = str(payload.get("action") or "inspect").strip().lower()
    if action == "verify_provider_read":
        return _verify_provider_erp_read(payload)
    if action == "verify_rest_read":
        profile = payload.get("profile")
        if not isinstance(profile, dict):
            raise ValueError("profile must be a JSON object for the approved REST connector.")
        _require_connector_operator()
        # Validate the request shape before checking the target environment.
        # This does not perform network access or weaken the staging-only gate.
        include_sample_data = payload.get("include_sample_data", False)
        if not isinstance(include_sample_data, bool):
            raise ValueError("include_sample_data must be a JSON boolean.")
        # A live connector test is a stateful outbound operation. Keep it out
        # of production until the full provider/security/cutover gates have
        # passed and an explicit release authorization exists.
        try:
            import durable_account_store
            environment = str(durable_account_store.APP_ENVIRONMENT or "").strip().casefold()
        except Exception as exc:
            raise PermissionError(
                "The application environment could not be verified; live connector testing is denied."
            ) from exc
        if environment != "staging":
            raise PermissionError(
                "Live connector verification is available only in the authorized staging environment."
            )
        return verify_readonly_rest_connector(
            profile,
            include_sample_data=include_sample_data,
        )
    if action not in {"inspect", "check_configuration"}:
        raise ValueError("action must be inspect, verify_rest_read or verify_provider_read.")
    profiles = _records(payload.get("profiles"), "profiles", maximum=500)
    output = []
    for profile in profiles:
        name = _nonempty_text(profile.get("name"), "profile.name", 150)
        protocol = str(profile.get("protocol", "")).strip().upper()
        if protocol not in {"REST", "SQL", "MQTT", "OPC-UA", "SAP", "ORACLE", "WMS", "MES", "ERP"}:
            raise ValueError(f"{name}.protocol is not in the supported configuration catalog.")
        endpoint_env = _nonempty_text(profile.get("endpoint_env"), f"{name}.endpoint_env", 100)
        credential_env = _nonempty_text(profile.get("credential_env"), f"{name}.credential_env", 100)
        if not re.fullmatch(r"SHOIR_CONNECTOR_[A-Z0-9_]+_(ENDPOINT|URL|DSN)", endpoint_env):
            raise ValueError(f"{name}.endpoint_env must use a SHOIR_CONNECTOR_*_ENDPOINT/URL/DSN variable name.")
        if not re.fullmatch(r"SHOIR_CONNECTOR_[A-Z0-9_]+_(TOKEN|CREDENTIAL|PASSWORD|DSN)", credential_env):
            raise ValueError(f"{name}.credential_env must use a SHOIR_CONNECTOR_*_TOKEN/CREDENTIAL/PASSWORD/DSN variable name.")
        endpoint_value = _configuration_value(endpoint_env)
        credential_value = _configuration_value(credential_env)
        endpoint_valid = False
        if endpoint_value:
            parsed = urlparse(endpoint_value)
            allowed_schemes = {
                "REST": {"https"}, "SQL": {"postgres", "postgresql", "mssql", "mysql"},
                "MQTT": {"mqtts", "mqtt"}, "OPC-UA": {"opc.tcp", "opc.tls"},
                "SAP": {"https"}, "ORACLE": {"oracle", "tcps"},
                "WMS": {"https"}, "MES": {"https"}, "ERP": {"https"},
            }[protocol]
            endpoint_valid = parsed.scheme.lower() in allowed_schemes and bool(parsed.netloc or parsed.path)
        ready = bool(endpoint_value and credential_value and endpoint_valid)
        output.append({
            "name": name,
            "protocol": protocol,
            "endpoint_env": endpoint_env,
            "endpoint_configured": bool(endpoint_value),
            "endpoint_syntax_valid": endpoint_valid if endpoint_value else False,
            "credential_env": credential_env,
            "credential_configured": bool(credential_value),
            "status": "READY_FOR_AUTHORIZED_STAGING_TEST" if ready else "NOT_CONNECTED_CONFIGURATION_INCOMPLETE",
            "last_test_at": None,
            "last_sync_at": None,
            "warning": "Secrets are never returned. No outbound network call was attempted; configuration presence is not connection proof.",
        })
    return {
        "tool_id": "T096",
        "status": "CONFIGURATION_INSPECTED",
        "profiles": pd.DataFrame(output),
        "profile_records": output,
        "connected_count": 0,
        "warning": "Connection state is intentionally not reported as CONNECTED. An authorized provider-specific staging test, permission-scope review and redacted health result are required before enabling a connector.",
    }


def validate_api_plugin_manifests(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate inert, versioned plugin manifests; never imports or executes plugin code."""
    manifests = _records(payload.get("plugins"), "plugins", maximum=500)
    scopes_allowed = {"read", "write", "execute", "export", "admin"}
    output = []
    ids: set[str] = set()
    semver = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
    for manifest in manifests:
        errors = []
        plugin_id = str(manifest.get("id", "")).strip()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{2,63}", plugin_id):
            errors.append("id must be 3-64 lowercase letters/numbers/underscores/hyphens and start with a letter.")
        if plugin_id and plugin_id in ids:
            errors.append("plugin id is duplicated.")
        ids.add(plugin_id)
        if not str(manifest.get("name", "")).strip():
            errors.append("name is required.")
        version = str(manifest.get("version", "")).strip()
        if not semver.fullmatch(version):
            errors.append("version must follow semantic version format MAJOR.MINOR.PATCH.")
        if not str(manifest.get("api_version", "")).strip():
            errors.append("api_version is required.")
        tier = str(manifest.get("minimum_tier", "")).strip()
        if tier not in {"Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus", "Research Pack"}:
            errors.append("minimum_tier must be one of the six canonical packages.")
        scopes = manifest.get("scopes", [])
        if not isinstance(scopes, list) or not scopes or any(not isinstance(s, str) or s not in scopes_allowed for s in scopes):
            errors.append("scopes must be a non-empty list drawn from read/write/execute/export/admin.")
        request_schema = manifest.get("request_schema")
        response_schema = manifest.get("response_schema")
        if not isinstance(request_schema, dict) or request_schema.get("type") not in {"object", "array", "string", "number", "integer", "boolean"}:
            errors.append("request_schema must be a supported JSON Schema object.")
        if not isinstance(response_schema, dict) or response_schema.get("type") not in {"object", "array", "string", "number", "integer", "boolean"}:
            errors.append("response_schema must be a supported JSON Schema object.")
        entrypoint = str(manifest.get("entrypoint", "")).strip()
        if entrypoint and (entrypoint.startswith(("/", "\\")) or ".." in entrypoint.split("/") or ".." in entrypoint.split("\\")):
            errors.append("entrypoint must be a repository-relative safe path without traversal.")
        if manifest.get("enabled") is True:
            errors.append("A manifest cannot self-enable execution; deployment registry approval is required.")
        output.append({
            "id": plugin_id or "INVALID",
            "name": str(manifest.get("name") or ""),
            "version": version or None,
            "minimum_tier": tier or None,
            "scopes": scopes if isinstance(scopes, list) else [],
            "validation_status": "VALIDATED_INERT_MANIFEST" if not errors else "BLOCKED_INVALID_MANIFEST",
            "errors": errors,
            "executable": False,
            "entrypoint": entrypoint or None,
        })
    return {
        "tool_id": "T097",
        "status": "MANIFEST_VALIDATION_COMPLETE",
        "plugin_count": len(output),
        "valid_count": sum(item["validation_status"] == "VALIDATED_INERT_MANIFEST" for item in output),
        "blocked_count": sum(item["validation_status"] != "VALIDATED_INERT_MANIFEST" for item in output),
        "plugins": pd.DataFrame(output),
        "plugin_records": output,
        "warning": "This validates declarations only. It does not create a public API server or execute plugin code; runtime auth scopes, schema validation, rate limits, audit and deployment approvals remain mandatory.",
    }


def identity_audit_configuration_status(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Inspect visible Streamlit OIDC settings without pretending to inspect Edge secrets."""
    if isinstance(payload, Mapping):
        root = payload
    else:
        try:
            import streamlit as st
            root = st.secrets
        except Exception:
            root = {}

    auth = root.get("auth", {}) if isinstance(root, Mapping) else {}
    auth = auth if isinstance(auth, Mapping) else {}
    provider = auth.get("enterprise", {})
    provider = provider if isinstance(provider, Mapping) else {}

    raw_exposed = auth.get("expose_tokens")
    if isinstance(raw_exposed, str) and raw_exposed.strip():
        exposed_tokens = {
            token.strip().casefold()
            for token in re.split(r"[,\\s]+", raw_exposed)
            if token.strip()
        }
    elif isinstance(raw_exposed, (list, tuple, set)):
        exposed_tokens = {
            str(value).strip().casefold()
            for value in raw_exposed
            if isinstance(value, str) and value.strip()
        }
    else:
        exposed_tokens = set()

    visible_settings = {
        "redirect_uri": ("auth.redirect_uri", auth.get("redirect_uri")),
        "cookie_secret": ("auth.cookie_secret", auth.get("cookie_secret")),
        "expose_tokens_id": ("auth.expose_tokens includes id", raw_exposed),
        "client_id": ("auth.enterprise.client_id", provider.get("client_id")),
        "client_secret": ("auth.enterprise.client_secret", provider.get("client_secret")),
        "server_metadata_url": ("auth.enterprise.server_metadata_url", provider.get("server_metadata_url")),
    }
    configured = {
        key: isinstance(value, str) and bool(value.strip())
        for key, (_, value) in visible_settings.items()
    }
    configured["expose_tokens_id"] = bool(exposed_tokens)
    missing = [
        visible_settings[key][0]
        for key, is_present in configured.items()
        if not is_present
    ]

    def public_https_url(value: Any) -> bool:
        if not isinstance(value, str) or not value.strip():
            return False
        try:
            parsed = urlparse(value.strip())
            host = (parsed.hostname or "").casefold()
            if not host:
                return False
            try:
                ipaddress.ip_address(host)
                return False
            except ValueError:
                pass
            return (
                parsed.scheme.casefold() == "https"
                and not parsed.username
                and not parsed.password
                and host != "localhost"
                and not host.endswith((".localhost", ".local", ".internal"))
                and parsed.port in (None, 443)
            )
        except (TypeError, ValueError):
            return False

    redirect_valid = public_https_url(auth.get("redirect_uri"))
    metadata_valid = public_https_url(provider.get("server_metadata_url"))
    cookie_secret = auth.get("cookie_secret")
    cookie_valid = isinstance(cookie_secret, str) and len(cookie_secret) >= 32
    problems = []
    if configured["redirect_uri"] and not redirect_valid:
        problems.append("auth.redirect_uri must be a public HTTPS URL.")
    if configured["cookie_secret"] and not cookie_valid:
        problems.append("auth.cookie_secret must contain at least 32 characters.")
    if configured["server_metadata_url"] and not metadata_valid:
        problems.append("auth.enterprise.server_metadata_url must be a public HTTPS URL.")
    if configured["expose_tokens_id"] and "id" not in exposed_tokens:
        problems.append("auth.expose_tokens must include the ID token value `id`.")
    complete = not missing and not problems and redirect_valid and cookie_valid and metadata_valid
    status = (
        "CONFIGURATION_INVALID" if problems
        else "NOT_CONFIGURED" if missing
        else "STREAMLIT_CONFIGURATION_READY_EDGE_SETTINGS_UNVERIFIED"
    )

    setting_rows = [
        {
            "setting": key,
            "configuration_path": path,
            "configured": configured[key],
            "value_exposed": False,
        }
        for key, (path, _) in visible_settings.items()
    ]
    expected_edge_secrets = [
        "SHOIR_OIDC_ENABLED",
        "SHOIR_OIDC_ISSUER",
        "SHOIR_OIDC_CLIENT_ID",
        "SHOIR_OIDC_JWKS_URL",
        "SHOIR_OIDC_REQUIRE_MFA",
        "SHOIR_OIDC_MFA_AMR_VALUES",
        "SHOIR_OIDC_MFA_ACR_VALUES",
    ]
    return {
        "tool_id": "T098",
        "status": status,
        "streamlit_configuration_ready": complete,
        "provider": "OIDC-compatible identity provider (not detected/activated by this check)",
        "environment_variables": pd.DataFrame(setting_rows),
        "missing_settings": missing,
        "missing_variables": missing,
        "configuration_problems": problems,
        # Issuer, MFA and audit verifier values live in the Supabase Edge
        # secret manager. A Streamlit process cannot inspect them.
        "oidc_issuer_syntax_valid": None,
        "provider_metadata_url_syntax_valid": metadata_valid,
        "redirect_uri_syntax_valid": redirect_valid,
        "openid_scope_present": None,
        "mfa_enforced_flag": None,
        "audit_logging_flag": None,
        "edge_configuration_visibility": "NOT_INSPECTABLE_FROM_STREAMLIT",
        "expected_edge_secret_names": expected_edge_secrets,
        "sso_active": False,
        "mfa_active": False,
        "oidc_login_flow_implemented": True,
        "provider_authentication_tested": False,
        "provider_mfa_evidence_verified": False,
        "audit_sink_configured": False,
        "audit_persistence_verified": False,
        "verified_at": None,
        "required_external_actions": [
            "Select an approved identity provider and configure its application/client and exact callback/logout URIs.",
            "Configure the named SHOIR_OIDC_* verifier secrets in the staging Supabase Edge Function secret manager; this Streamlit checker cannot read those remote secrets.",
            "Verify issuer, audience, signature, state, nonce, expiry, redirect and logout/revocation behavior using the existing login and token-verification path.",
            "Map a validated provider identity to the existing application account, role, tier and workspace without privilege elevation.",
            "Prove provider-backed MFA from the actual amr/acr claims and the staging Edge verifier configuration; environment flags alone are not evidence.",
            "Apply the reviewed staging OIDC audit migration and verify protected audit writes, reads and fail-closed behavior.",
            "Run authenticated staging allow/deny, cross-workspace, expired/revoked session and audit-failure tests.",
        ],
        "warning": (
            "This is a readiness check only. It inspects Streamlit auth settings but cannot inspect Supabase Edge Function secrets or deployment state. "
            "The repository contains the Streamlit OIDC login and Edge Function token-verification/session-exchange path; provider authentication, "
            "MFA claims and durable audit persistence remain unverified until accepted on authorized staging."
        ),
    }


def governance_recovery_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create/verify a hashed recovery package or produce a non-destructive governance plan."""
    action = str(payload.get("action", "retention_review")).strip().lower()
    if action == "create_snapshot":
        content = _json_clone(payload.get("content"))
        package = {
            "format": "shoir-ie-governance-snapshot-v1",
            "created_at": str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
            "workspace_reference": str(payload.get("workspace_reference") or "UNSPECIFIED"),
            "content": content,
        }
        package["sha256"] = _canonical_hash(package)
        return {
            "tool_id": "T099",
            "status": "SNAPSHOT_PACKAGE_CREATED",
            "snapshot": package,
            "checksum_verified": True,
            "warning": "This creates a portable integrity-checked package only. Store it in the authenticated workspace/backup system and prove an isolated restore before relying on it.",
        }
    if action == "verify_snapshot":
        snapshot = payload.get("snapshot")
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("sha256"), str):
            raise ValueError("snapshot must be a governance snapshot package with a sha256 field.")
        clone = _json_clone(snapshot)
        expected = clone.pop("sha256")
        actual = _canonical_hash(clone)
        return {
            "tool_id": "T099",
            "status": "SNAPSHOT_VERIFIED" if actual == expected else "SNAPSHOT_INTEGRITY_FAILED",
            "checksum_verified": actual == expected,
            "expected_sha256": expected,
            "actual_sha256": actual,
            "content": clone.get("content") if actual == expected else None,
            "warning": "Integrity verification is not proof of authenticity or permission to restore. Restore only after workspace ownership, schema compatibility and approval are verified.",
        }
    if action == "retention_review":
        policies = _records(payload.get("policies"), "policies", maximum=500)
        out = []
        for row in policies:
            category = _nonempty_text(row.get("category"), "policy.category", 150)
            retention_value = _number(row.get("retention_days"), f"{category}.retention_days", minimum=1, maximum=36500)
            if not retention_value.is_integer():
                raise ValueError(f"{category}.retention_days must be a whole number of days.")
            retention = int(retention_value)
            hold = bool(row.get("legal_hold", False))
            out.append({
                "category": category,
                "retention_days": retention,
                "legal_hold": hold,
                "action": "HOLD_FOR_REVIEW" if hold else "RETENTION_REVIEW_REQUIRED",
                "delete_executed": False,
                "review_owner": str(row.get("review_owner") or "NOT_ASSIGNED"),
            })
        return {
            "tool_id": "T099",
            "status": "RETENTION_REVIEW_PLAN_CREATED",
            "policies": pd.DataFrame(out),
            "policy_records": out,
            "warning": "Retention numbers are user-supplied proposals, not legal determinations. No records were deleted; a qualified owner must approve retention and validate backups/logs/vendor deletion paths.",
        }
    if action == "deletion_plan":
        categories = payload.get("categories")
        if not isinstance(categories, list) or not categories:
            raise ValueError("categories must be a non-empty list of data-category names.")
        if any(not str(c).strip() for c in categories):
            raise ValueError("Data-category names cannot be blank.")
        ticket = _nonempty_text(payload.get("request_reference"), "request_reference", 120)
        return {
            "tool_id": "T099",
            "status": "DELETION_PLAN_REQUIRES_APPROVAL",
            "request_reference": ticket,
            "categories": list(dict.fromkeys(str(c).strip() for c in categories)),
            "systems_to_review": ["primary database", "object/file storage", "application caches", "audit/security logs", "vendor processors", "backups", "derived exports"],
            "delete_executed": False,
            "warning": "This only builds a checklist. It does not delete data or override retention, legal-hold, ownership or mandatory-record rules.",
        }
    raise ValueError("action must be create_snapshot, verify_snapshot, retention_review, or deletion_plan.")


def linear_mixed_integer_optimization(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run the existing bounded LP/MILP solver behind canonical T061."""
    if not isinstance(payload, Mapping):
        raise ValueError("T061 payload must be a JSON object.")
    variable_spec = payload.get("variable_spec")
    objective_coefficients = payload.get("objective_coefficients")
    constraints = payload.get("constraints", [])
    if not isinstance(variable_spec, Mapping) or not variable_spec:
        raise ValueError("T061 requires a non-empty variable_spec object.")
    if not isinstance(objective_coefficients, Mapping) or not objective_coefficients:
        raise ValueError("T061 requires objective_coefficients keyed by variable name.")
    if isinstance(constraints, (str, bytes)) or not isinstance(constraints, Sequence):
        raise ValueError("T061 constraints must be a JSON list.")
    from shoir_target_engines import run_solver_diagnostics

    result = run_solver_diagnostics(
        variable_spec,
        objective_coefficients,
        constraints,
        direction=str(payload.get("direction") or "minimize"),
        time_limit_seconds=_number(payload.get("time_limit_seconds", 10), "time_limit_seconds", minimum=0.1),
        feasibility_tolerance=_number(payload.get("feasibility_tolerance", 1e-7), "feasibility_tolerance", minimum=1e-10),
    )
    result.update({
        "tool_id": "T061",
        "method": "PuLP/CBC linear or mixed-integer model with independent feasibility diagnostics",
        "data_provenance": str(payload.get("data_provenance") or "USER_ENTERED_UNVERIFIED"),
        "warning": (
            "The solver validates and solves the supplied mathematical formulation; it cannot prove that "
            "the model represents the real plant, that coefficients/units are correct, or that the model "
            "has received engineering approval. A solver error or time limit is not an optimal solution."
        ),
    })
    return result


def multiobjective_optimization(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create a weighted ranking and Pareto candidate set for declared alternatives (T067)."""
    if not isinstance(payload, Mapping):
        raise ValueError("T067 payload must be a JSON object.")
    alternatives = _records(payload.get("alternatives"), "alternatives", minimum=2, maximum=2000)
    objective_specs = _records(payload.get("objectives"), "objectives", minimum=2, maximum=20)
    names = [str(row.get("name") or "").strip() for row in alternatives]
    if any(not name for name in names) or len({name.casefold() for name in names}) != len(names):
        raise ValueError("Every alternative needs a unique non-empty name.")
    fields: list[str] = []
    weights: list[float] = []
    minimize: list[bool] = []
    for index, spec in enumerate(objective_specs, start=1):
        field = _nonempty_text(spec.get("field"), f"objectives[{index}].field", 120)
        if field in fields or field.casefold() == "name":
            raise ValueError("Objective fields must be unique and cannot use the alternative name field.")
        weight = _number(spec.get("weight"), f"objectives[{index}].weight", minimum=0)
        direction = str(spec.get("direction") or "").strip().casefold()
        if direction not in {"minimize", "maximize"}:
            raise ValueError(f"Objective {field} direction must be minimize or maximize.")
        fields.append(field)
        weights.append(weight)
        minimize.append(direction == "minimize")
    if not any(weight > 0 for weight in weights):
        raise ValueError("At least one objective weight must be greater than zero.")
    for row_index, row in enumerate(alternatives, start=1):
        for field in fields:
            _number(row.get(field), f"alternatives[{row_index}].{field}")
    frame = pd.DataFrame(alternatives)
    from shoir_optimization import pareto_weight_sweep

    ranked = pareto_weight_sweep(frame, fields, weights=weights, minimize=minimize)
    candidate_count = int(ranked["Pareto Candidate"].fillna(False).astype(bool).sum())
    return {
        "tool_id": "T067",
        "status": "PARETO_TRADEOFFS_ANALYZED",
        "alternative_count": len(ranked),
        "objective_count": len(fields),
        "pareto_candidate_count": candidate_count,
        "objective_definitions": [
            {"field": field, "weight": weight, "direction": "minimize" if mn else "maximize"}
            for field, weight, mn in zip(fields, weights, minimize)
        ],
        "ranked_alternatives": ranked,
        "data_provenance": str(payload.get("data_provenance") or "USER_ENTERED_UNVERIFIED"),
        "warning": (
            "The weighted score is a user-weighted comparison aid, not a universal optimum. Pareto "
            "candidates are based only on the declared numeric objectives; omitted constraints, units, "
            "uncertainties and engineering feasibility are not inferred."
        ),
    }


def robust_linear_optimization(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Minimize the worst-case linear objective over an explicitly declared scenario set (T068)."""
    if not isinstance(payload, Mapping):
        raise ValueError("T068 payload must be a JSON object.")
    raw_scenarios = payload.get("scenario_objectives")
    if isinstance(raw_scenarios, (str, bytes)) or not isinstance(raw_scenarios, Sequence) or len(raw_scenarios) < 2:
        raise ValueError("T068 requires at least two scenario objective vectors.")
    scenarios: list[list[float]] = []
    variable_count: int | None = None
    for row_index, row in enumerate(raw_scenarios, start=1):
        if isinstance(row, (str, bytes)) or not isinstance(row, Sequence) or not row:
            raise ValueError(f"scenario_objectives[{row_index}] must be a non-empty numeric vector.")
        values = [_number(value, f"scenario_objectives[{row_index}][{column_index}]") for column_index, value in enumerate(row, start=1)]
        if variable_count is None:
            variable_count = len(values)
        elif len(values) != variable_count:
            raise ValueError("All scenario objective vectors must have the same number of variables.")
        scenarios.append(values)
    if variable_count is None:
        raise ValueError("T068 needs at least one decision variable.")

    def matrix(name: str) -> list[list[float]] | None:
        raw = payload.get(name)
        if raw is None:
            return None
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise ValueError(f"{name} must be a matrix of numeric rows.")
        parsed = []
        for row_index, row in enumerate(raw, start=1):
            if isinstance(row, (str, bytes)) or not isinstance(row, Sequence) or len(row) != variable_count:
                raise ValueError(f"{name}[{row_index}] must contain {variable_count} coefficients.")
            parsed.append([_number(value, f"{name}[{row_index}][{column_index}]") for column_index, value in enumerate(row, start=1)])
        return parsed

    def vector(name: str, row_count: int | None) -> list[float] | None:
        raw = payload.get(name)
        if raw is None:
            return None
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise ValueError(f"{name} must be a numeric vector.")
        parsed = [_number(value, f"{name}[{index}]") for index, value in enumerate(raw, start=1)]
        if row_count is not None and len(parsed) != row_count:
            raise ValueError(f"{name} length must match its constraint matrix row count.")
        return parsed

    a_ub, a_eq = matrix("A_ub"), matrix("A_eq")
    b_ub = vector("b_ub", len(a_ub) if a_ub is not None else None)
    b_eq = vector("b_eq", len(a_eq) if a_eq is not None else None)
    if (a_ub is None) != (b_ub is None) or (a_eq is None) != (b_eq is None):
        raise ValueError("Each supplied constraint matrix must have its matching right-hand-side vector.")
    raw_bounds = payload.get("bounds")
    bounds = None
    if raw_bounds is not None:
        if isinstance(raw_bounds, (str, bytes)) or not isinstance(raw_bounds, Sequence) or len(raw_bounds) != variable_count:
            raise ValueError("bounds must have one [lower, upper] pair per decision variable.")
        bounds = []
        for index, pair in enumerate(raw_bounds, start=1):
            if isinstance(pair, (str, bytes)) or not isinstance(pair, Sequence) or len(pair) != 2:
                raise ValueError(f"bounds[{index}] must be a [lower, upper] pair.")
            lower = None if pair[0] is None else _number(pair[0], f"bounds[{index}].lower")
            upper = None if pair[1] is None else _number(pair[1], f"bounds[{index}].upper")
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"bounds[{index}] lower limit exceeds upper limit.")
            bounds.append((lower, upper))

    from shoir_optimization import solve_robust_linear_program

    result = solve_robust_linear_program(
        scenarios, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds,
    )
    solved = bool(result.get("success"))
    variables = np.asarray(result.get("variables"), dtype=float)
    return {
        "tool_id": "T068",
        "status": "ROBUST_OPTIMAL" if solved else "ROBUST_NOT_SOLVED",
        "success": solved,
        "worst_case_objective": float(result["worst_case_objective"]) if solved else None,
        "decision_variables": variables.tolist() if solved else [],
        "scenario_objectives": scenarios,
        "solver_message": str(result.get("message") or ""),
        "data_provenance": str(payload.get("data_provenance") or "USER_ENTERED_UNVERIFIED"),
        "warning": (
            "This is a static worst-case linear objective over the scenarios supplied by the user, "
            "using one common linear feasible region. It is not a general nonlinear, stochastic, "
            "multi-period or uncertainty-distribution model. Validate scenario coverage and units."
        ),
    }


def project_manager_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create and list owner-scoped engineering project records (T004)."""
    if not isinstance(payload, Mapping):
        raise ValueError("T004 payload must be a JSON object.")
    owner = _nonempty_text(payload.get("owner"), "owner", 160)
    action = str(payload.get("action") or "list").strip().casefold()
    import industrial_experience as experience

    if action == "create":
        name = _nonempty_text(payload.get("name"), "name", 160)
        module = _nonempty_text(payload.get("module") or "Engineering Project", "module", 120)
        linked = payload.get("linked_artifact_ids", [])
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata must be a JSON object.")
        if isinstance(linked, (str, bytes)) or not isinstance(linked, Sequence):
            raise ValueError("linked_artifact_ids must be a list of artifact references.")
        linked_ids = [_nonempty_text(item, "linked_artifact_id", 200) for item in linked]
        state = _json_clone({
            "description": str(payload.get("description") or "")[:4000],
            "site": str(payload.get("site") or "")[:160],
            "owner": owner,
            "linked_artifact_ids": list(dict.fromkeys(linked_ids)),
            "project_metadata": dict(metadata),
        })
        project_id = experience.save_project(name, module, owner, state)
        return {
            "tool_id": "T004", "status": "PROJECT_CREATED", "project_id": project_id,
            "name": name, "module": module, "linked_artifact_count": len(state["linked_artifact_ids"]),
            "data_provenance": "MANUAL",
            "warning": "Project and artifact references are owner-scoped metadata. Referenced artifacts are not copied, shared, or independently verified.",
        }
    if action == "list":
        experience.ensure_experience_db()
        with experience._db() as conn:
            rows = conn.execute(
                "SELECT project_id,name,module,status,created_at,updated_at "
                "FROM experience_projects WHERE owner=? ORDER BY updated_at DESC",
                (owner,),
            ).fetchall()
        return {
            "tool_id": "T004", "status": "PROJECTS_LISTED", "project_count": len(rows),
            "projects": pd.DataFrame(rows, columns=["project_id","name","module","status","created_at","updated_at"]),
            "data_provenance": "MANUAL",
        }
    raise ValueError("T004 action must be create or list.")


def project_version_history_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Append and inspect project snapshots with owner checks (T005)."""
    if not isinstance(payload, Mapping):
        raise ValueError("T005 payload must be a JSON object.")
    owner = _nonempty_text(payload.get("owner"), "owner", 160)
    action = str(payload.get("action") or "list").strip().casefold()
    import industrial_experience as experience

    if action == "create":
        name = _nonempty_text(payload.get("name"), "name", 160)
        module = _nonempty_text(payload.get("module") or "Engineering Project", "module", 120)
        state = payload.get("state")
        if not isinstance(state, Mapping):
            raise ValueError("state must be a JSON object.")
        project_id = experience.save_project(name, module, owner, _json_clone(dict(state)))
        return {"tool_id": "T005", "status": "PROJECT_SNAPSHOT_CREATED", "project_id": project_id, "snapshot_no": 1, "data_provenance": "MANUAL"}
    if action in {"autosave", "history", "restore"}:
        project_id = _nonempty_text(payload.get("project_id"), "project_id", 80)
        experience.ensure_experience_db()
        if action == "autosave":
            state = payload.get("state")
            if not isinstance(state, Mapping):
                raise ValueError("state must be a JSON object.")
            number = experience.autosave_project(project_id, _json_clone(dict(state)), owner)
            return {"tool_id": "T005", "status": "PROJECT_SNAPSHOT_SAVED", "project_id": project_id, "snapshot_no": number, "data_provenance": "MANUAL"}
        with experience._db() as conn:
            project = conn.execute("SELECT owner FROM experience_projects WHERE project_id=?", (project_id,)).fetchone()
            if not project or str(project[0] or "") != owner:
                raise PermissionError("Project not found or not owned by this user.")
            rows = conn.execute(
                "SELECT snapshot_no,payload_json,created_at FROM experience_project_snapshots "
                "WHERE project_id=? ORDER BY snapshot_no ASC", (project_id,),
            ).fetchall()
        history = []
        for number, raw_json, created_at in rows:
            try:
                saved = json.loads(raw_json or "{}")
            except (TypeError, ValueError) as exc:
                raise ValueError("A saved project snapshot is corrupt and cannot be restored.") from exc
            if not isinstance(saved, dict):
                raise ValueError("A saved project snapshot is not a JSON object.")
            history.append({"snapshot_no": int(number), "payload": saved, "created_at": created_at})
        if action == "history":
            return {"tool_id": "T005", "status": "PROJECT_HISTORY_LOADED", "project_id": project_id, "snapshot_count": len(history), "history": history, "data_provenance": "MANUAL"}
        number = payload.get("snapshot_no")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ValueError("snapshot_no must be a positive whole number.")
        chosen = next((item for item in history if item["snapshot_no"] == number), None)
        if chosen is None:
            raise ValueError("The requested snapshot does not exist.")
        new_number = experience.autosave_project(project_id, chosen["payload"], owner)
        return {"tool_id": "T005", "status": "PROJECT_VERSION_RESTORED_AS_NEW_SNAPSHOT", "project_id": project_id, "restored_from_snapshot": number, "snapshot_no": new_number, "data_provenance": "MANUAL"}
    if action == "list":
        experience.ensure_experience_db()
        with experience._db() as conn:
            rows = conn.execute(
                "SELECT project_id,name,module,status,created_at,updated_at "
                "FROM experience_projects WHERE owner=? ORDER BY updated_at DESC", (owner,),
            ).fetchall()
        return {"tool_id": "T005", "status": "PROJECTS_LISTED", "projects": pd.DataFrame(rows, columns=["project_id","name","module","status","created_at","updated_at"]), "data_provenance": "MANUAL"}
    raise ValueError("T005 action must be create, autosave, history, restore, or list.")


def research_hypothesis_register_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Record and retrieve owner-scoped research protocols and hypothesis metadata (T086)."""
    if not isinstance(payload, Mapping):
        raise ValueError("T086 payload must be a JSON object.")
    owner = _nonempty_text(payload.get("owner"), "owner", 160)
    action = str(payload.get("action") or "list").strip().casefold()
    import industrial_experience as experience

    if action == "list":
        frame = experience.list_research_studies(owner)
        return {
            "tool_id": "T086", "status": "RESEARCH_STUDIES_LISTED",
            "study_count": len(frame), "studies": frame, "data_provenance": "MANUAL",
            "warning": "Research protocol metadata is owner-scoped. Listing a study does not mean its evidence or scientific claims are verified.",
        }
    if action in {"create", "update"}:
        title = _nonempty_text(payload.get("title"), "title", 240)
        question = _nonempty_text(payload.get("research_question"), "research_question", 3000)
        hypothesis = _nonempty_text(payload.get("hypothesis"), "hypothesis", 3000)
        null_hypothesis = _nonempty_text(payload.get("null_hypothesis"), "null_hypothesis", 3000)
        methodology = _nonempty_text(payload.get("methodology"), "methodology", 240)
        endpoint = _nonempty_text(payload.get("primary_endpoint"), "primary_endpoint", 500)
        raw_refs = payload.get("evidence_references", [])
        if isinstance(raw_refs, (str, bytes)) or not isinstance(raw_refs, Sequence):
            raise ValueError("evidence_references must be a list of user-supplied source references.")
        evidence_refs = [_nonempty_text(item, "evidence_reference", 500) for item in raw_refs]
        def positive_integer(key: str, default: int, maximum: int = 1_000_000) -> int:
            value = payload.get(key, default)
            numeric = _number(value, key, minimum=1, maximum=maximum)
            if not float(numeric).is_integer():
                raise ValueError(f"{key} must be a whole number.")
            return int(numeric)
        sample_size = positive_integer("sample_size", 100)
        replications = positive_integer("replications", 30, 100_000)
        seed_raw = payload.get("random_seed", 2026)
        seed_numeric = _number(seed_raw, "random_seed", minimum=0, maximum=2_147_483_647)
        if not float(seed_numeric).is_integer():
            raise ValueError("random_seed must be a whole number.")
        alpha = _number(payload.get("alpha", 0.05), "alpha", minimum=1e-9, maximum=0.999999)
        confidence = _number(payload.get("confidence_level", 0.95), "confidence_level", minimum=1e-9, maximum=0.999999)
        study_id = str(payload.get("study_id") or "").strip()
        if not study_id:
            seed = f"{owner}|{title}|{datetime.now(timezone.utc).isoformat(timespec='microseconds')}"
            study_id = "STUDY-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16].upper()
        protocol = {
            "title": title,
            "objective": str(payload.get("objective") or "")[:1500],
            "research_question": question,
            "hypothesis": hypothesis,
            "null_hypothesis": null_hypothesis,
            "methodology": methodology,
            "primary_domain": str(payload.get("primary_domain") or "Industrial Engineering")[:120],
            "transfer_domain": str(payload.get("transfer_domain") or "")[:120],
            "primary_endpoint": endpoint,
            "secondary_metrics": payload.get("secondary_metrics") or [],
            "independent_variables": payload.get("independent_variables") or [],
            "controls": payload.get("controls") or [],
            "baseline_definition": str(payload.get("baseline_definition") or "")[:2000],
            "treatment_definition": str(payload.get("treatment_definition") or "")[:2000],
            "sample_size": sample_size,
            "replications": replications,
            "random_seed": int(seed_numeric),
            "alpha": alpha,
            "confidence_level": confidence,
            "planned_tests": payload.get("planned_tests") or [],
            "inclusion_criteria": str(payload.get("inclusion_criteria") or "")[:2000],
            "exclusion_criteria": str(payload.get("exclusion_criteria") or "")[:2000],
            "data_source": str(payload.get("data_source") or "")[:1200],
            "protocol_notes": str(payload.get("protocol_notes") or "")[:3000],
            "evidence_references": evidence_refs,
            "protocol_locked": False,
        }
        research_id, protocol_hash = experience.create_research_protocol(study_id, protocol, owner)
        return {
            "tool_id": "T086", "status": "HYPOTHESIS_PROTOCOL_RECORDED",
            "study_id": study_id, "research_id": research_id, "protocol_hash": protocol_hash,
            "owner": owner, "evidence_reference_count": len(evidence_refs), "protocol_status": "DRAFT",
            "data_provenance": "MANUAL",
            "warning": "Evidence references are user-supplied metadata and are not independently authenticated, peer-reviewed, or verified by this register.",
        }
    if action == "load":
        study_id = _nonempty_text(payload.get("study_id"), "study_id", 120)
        protocol = experience.load_research_protocol(study_id, owner=owner)
        if not protocol:
            raise PermissionError("Research study not found or not owned by this user.")
        return {"tool_id": "T086", "status": "RESEARCH_PROTOCOL_LOADED", "study_id": study_id, "protocol": protocol, "data_provenance": "MANUAL"}
    if action == "export":
        study_id = _nonempty_text(payload.get("study_id"), "study_id", 120)
        bundle = experience.research_evidence_bundle(study_id, owner)
        return {"tool_id": "T086", "status": "RESEARCH_EVIDENCE_BUNDLE_CREATED", "study_id": study_id, "bundle_bytes": bundle, "bundle_size_bytes": len(bundle), "data_provenance": "MANUAL", "warning": "The bundle exports saved owner-scoped research records; it does not certify scientific validity."}
    raise ValueError("T086 action must be create, update, list, load, or export.")


def decision_register_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create/list owner-scoped decisions and request human review without self-approval (T092)."""
    if not isinstance(payload, Mapping):
        raise ValueError("T092 payload must be a JSON object.")
    owner = _nonempty_text(payload.get("owner"), "owner", 160)
    action = str(payload.get("action") or "list").strip().casefold()
    import industrial_experience as experience

    if action == "list":
        frame = experience.research_decisions_frame(owner)
        return {"tool_id": "T092", "status": "DECISIONS_LISTED", "decision_count": len(frame), "decisions": frame, "data_provenance": "MANUAL"}
    if action == "create":
        title = _nonempty_text(payload.get("title"), "title", 180)
        module = _nonempty_text(payload.get("module") or "Engineering Decision Center", "module", 120)
        metrics, assumptions, uncertainty = payload.get("metrics") or {}, payload.get("assumptions") or {}, payload.get("uncertainty") or {}
        if not all(isinstance(item, Mapping) for item in (metrics, assumptions, uncertainty)):
            raise ValueError("metrics, assumptions and uncertainty must be JSON objects.")
        dependencies = payload.get("dataset_dependencies") or []
        if isinstance(dependencies, (str, bytes)) or not isinstance(dependencies, Sequence) or any(not isinstance(item, Mapping) for item in dependencies):
            raise ValueError("dataset_dependencies must be a list of registered dataset version objects.")
        did = experience.create_decision(
            title, module, _json_clone(dict(metrics)), _json_clone(dict(assumptions)),
            _json_clone(dict(uncertainty)), owner, status="Draft",
            dataset_dependencies=[dict(item) for item in dependencies],
        )
        return {
            "tool_id": "T092", "status": "DECISION_DRAFT_CREATED", "decision_id": did,
            "owner": owner, "workflow_status": "Draft", "dataset_dependency_count": len(dependencies),
            "data_provenance": "MANUAL",
            "warning": "This creates a draft only. Approval, implementation and verification remain separate human-governed transitions.",
        }
    if action in {"request_review", "history"}:
        decision_id = _nonempty_text(payload.get("decision_id"), "decision_id", 80)
        if action == "request_review":
            experience.transition_decision(decision_id, owner, "Review", str(payload.get("comment") or "Review requested by decision owner")[:500], require_owner=True)
        frame = experience.decision_approval_history(decision_id, owner=owner)
        return {
            "tool_id": "T092", "status": "DECISION_REVIEW_REQUESTED" if action == "request_review" else "DECISION_HISTORY_LOADED",
            "decision_id": decision_id, "approval_history": frame, "data_provenance": "MANUAL",
            "warning": "This tool does not approve a decision. Approval requires a separately authorized reviewer.",
        }
    raise ValueError("T092 action must be create, list, request_review, or history.")


def excel_workbook_target_action(tool_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run the existing governed workbook pipeline for canonical T011–T014."""
    selected = str(tool_id or "").strip().upper()
    if selected not in {"T011", "T012", "T013", "T014"}:
        raise ValueError("Excel workbook target action must be T011, T012, T013 or T014.")
    if not isinstance(payload, Mapping):
        raise ValueError(f"{selected} payload must be a JSON object.")
    filename = _nonempty_text(payload.get("filename"), "filename", 240)
    raw = payload.get("raw_bytes")
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("Select a non-empty supported workbook before running this tool.")
    if len(raw) > 50 * 1024 * 1024:
        raise ValueError("Workbook exceeds the 50 MiB upload limit.")
    if os.path.splitext(filename.casefold())[1] not in {".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".txt"}:
        raise ValueError("Supported workbook formats are XLSX, XLSM, XLS, CSV, TSV and TXT.")
    if selected == "T014" and payload.get("confirm_cleaning") is not True:
        raise ValueError("Review the reversible cleaning preview and explicitly confirm before applying the cleaned copy.")
    from shoir_excel_studio import process_uploaded_workbook

    workbook = process_uploaded_workbook(raw, filename)
    raw_sheets = workbook.get("raw_sheets", {})
    cleaned_sheets = workbook.get("cleaned_sheets", {})
    profiles = workbook.get("profiles", {})
    catalog = workbook.get("table_catalog", [])
    if selected == "T011":
        status = "WORKBOOK_IMPORTED"
        detail = {
            "import_diagnostics": workbook.get("import_diagnostics", {}),
            "sheet_summary": pd.DataFrame([{"Sheet": name, "Rows": len(frame), "Columns": len(frame.columns)} for name, frame in raw_sheets.items()]),
        }
    elif selected == "T012":
        status = "WORKBOOK_STRUCTURE_MAPPED"
        detail = {
            "table_catalog": pd.DataFrame(catalog),
            "cross_sheet_map": pd.DataFrame(workbook.get("cross_sheet_map", [])),
            "relationships": pd.DataFrame(workbook.get("relationship_integrity", [])),
        }
    elif selected == "T013":
        status = "WORKBOOK_PROFILED"
        detail = {"profiles": pd.DataFrame([{"Sheet": name, **dict(profile)} for name, profile in profiles.items() if isinstance(profile, Mapping)])}
    else:
        status = "CLEANED_COPY_READY"
        detail = {
            "cleaning_audit": pd.DataFrame(workbook.get("audits", [])),
            "review_register": pd.DataFrame(workbook.get("review_register", [])),
            "sheet_comparison": pd.DataFrame([{
                "Sheet": name,
                "Original rows": len(raw_sheets.get(name, pd.DataFrame())),
                "Cleaned rows": len(cleaned_sheets.get(name, pd.DataFrame())),
                "Original columns": len(raw_sheets.get(name, pd.DataFrame()).columns),
                "Cleaned columns": len(cleaned_sheets.get(name, pd.DataFrame()).columns),
            } for name in cleaned_sheets]),
        }
    return {
        "tool_id": selected, "status": status, "filename": filename,
        "source_sha256": str(workbook.get("signature") or workbook.get("import_diagnostics", {}).get("SHA256") or hashlib.sha256(raw).hexdigest()),
        "source_size_bytes": len(raw), "sheet_count": len(raw_sheets), "table_count": len(catalog),
        "original_source_preserved_in_workbook_record": bool(workbook.get("_raw_bytes") == raw),
        "data_provenance": "IMPORTED", "details": detail, "excel_workbook_result": workbook,
        "warning": "The original source bytes and raw sheets remain in the Excel Studio workbook record. Cleaning creates a governed copy; it never overwrites the original sheet values.",
    }


def scenario_manager_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Compare and persist owner-scoped What-If scenario branches (T073)."""
    if not isinstance(payload, Mapping):
        raise ValueError("T073 payload must be a JSON object.")
    owner = _nonempty_text(payload.get("owner"), "owner", 160)
    action = str(payload.get("action") or "compare").strip().casefold()
    import industrial_experience as experience
    from industrial_platform import analyze_experiment_scenarios

    if action in {"compare", "create", "branch"}:
        raw_rows = _records(payload.get("scenarios"), "scenarios", minimum=2, maximum=500)
        baseline = _nonempty_text(payload.get("baseline_scenario") or raw_rows[0].get("Scenario"), "baseline_scenario", 160)
        comparison = analyze_experiment_scenarios(pd.DataFrame(raw_rows), baseline_scenario=baseline)
        if action == "compare":
            return {
                "tool_id": "T073", "status": "SCENARIOS_COMPARED",
                "scenario_count": len(comparison), "baseline_scenario": baseline,
                "comparison": comparison, "data_provenance": str(payload.get("data_provenance") or "USER_ENTERED_UNVERIFIED"),
                "warning": "This is a user-input KPI comparison, not an optimizer recommendation or verified operational outcome.",
            }
        name = _nonempty_text(payload.get("name") or "What-If Scenario Study", "name", 160)
        parent_project_id = str(payload.get("parent_project_id") or "").strip()
        if action == "branch":
            if not parent_project_id:
                raise ValueError("branch requires a parent_project_id owned by the authenticated user.")
            experience.ensure_experience_db()
            with experience._db() as conn:
                parent = conn.execute(
                    "SELECT name,module,owner FROM experience_projects WHERE project_id=?",
                    (parent_project_id,),
                ).fetchone()
            if not parent or str(parent[2] or "") != owner or str(parent[1] or "") != "Scenario Manager":
                raise PermissionError("Parent scenario project not found or not owned by this user.")
            name = _nonempty_text(payload.get("name") or (str(parent[0]) + " · Branch"), "name", 160)
        stored = {
            "scenario_name": name,
            "baseline_scenario": baseline,
            "scenarios": raw_rows,
            "comparison": comparison.to_dict(orient="records"),
            "parent_project_id": parent_project_id or None,
            "data_provenance": str(payload.get("data_provenance") or "USER_ENTERED_UNVERIFIED"),
        }
        project_id = experience.save_project(name, "Scenario Manager", owner, _json_clone(stored))
        return {
            "tool_id": "T073", "status": "SCENARIO_BRANCH_SAVED" if action == "branch" else "SCENARIO_SET_SAVED",
            "project_id": project_id, "parent_project_id": parent_project_id or None,
            "scenario_count": len(comparison), "baseline_scenario": baseline,
            "comparison": comparison, "data_provenance": stored["data_provenance"],
            "warning": "Scenario assumptions and KPI deltas are saved as a versioned owner-scoped project. They are not forecasts, optimized plans or verified savings.",
        }
    if action == "list":
        experience.ensure_experience_db()
        with experience._db() as conn:
            rows = conn.execute(
                "SELECT project_id,name,status,created_at,updated_at FROM experience_projects "
                "WHERE owner=? AND module='Scenario Manager' ORDER BY updated_at DESC",
                (owner,),
            ).fetchall()
        return {
            "tool_id": "T073", "status": "SCENARIO_PROJECTS_LISTED",
            "project_count": len(rows),
            "projects": pd.DataFrame(rows, columns=["project_id","name","status","created_at","updated_at"]),
            "data_provenance": "MANUAL",
        }
    if action == "history":
        project_id = _nonempty_text(payload.get("project_id"), "project_id", 80)
        experience.ensure_experience_db()
        with experience._db() as conn:
            parent = conn.execute("SELECT owner,module FROM experience_projects WHERE project_id=?", (project_id,)).fetchone()
            if not parent or str(parent[0] or "") != owner or str(parent[1] or "") != "Scenario Manager":
                raise PermissionError("Scenario project not found or not owned by this user.")
            rows = conn.execute(
                "SELECT snapshot_no,payload_json,created_at FROM experience_project_snapshots "
                "WHERE project_id=? ORDER BY snapshot_no ASC",
                (project_id,),
            ).fetchall()
        history = []
        for number, raw, stamp in rows:
            data = json.loads(raw or "{}")
            if not isinstance(data, dict):
                raise ValueError("A scenario snapshot is not a valid JSON object.")
            history.append({"snapshot_no": int(number), "payload": data, "created_at": stamp})
        return {"tool_id": "T073", "status": "SCENARIO_HISTORY_LOADED", "project_id": project_id, "snapshot_count": len(history), "history": history, "data_provenance": "MANUAL"}
    raise ValueError("T073 action must be compare, create, branch, list, or history.")


def dataset_version_register_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Register an immutable workbook-derived dataset version through the existing managed API (T020)."""
    if not isinstance(payload, Mapping):
        raise ValueError("T020 payload must be a JSON object.")
    filename = _nonempty_text(payload.get("filename"), "filename", 240)
    raw = payload.get("raw_bytes")
    if not isinstance(raw, bytes) or not raw:
        raise ValueError("Upload a non-empty supported workbook before registering a dataset version.")
    if len(raw) > 50 * 1024 * 1024:
        raise ValueError("Workbook exceeds the 50 MiB upload limit.")
    dataset_name = _nonempty_text(payload.get("dataset_name"), "dataset_name", 160)
    sheet_requested = str(payload.get("sheet_name") or "").strip()
    existing_dataset_id = str(payload.get("dataset_id") or "").strip().upper() or None
    username = _nonempty_text(payload.get("username"), "username", 160)
    token = str(payload.get("token") or "").strip()
    workspace = str(payload.get("workspace") or "default").strip() or "default"
    from shoir_excel_studio import process_uploaded_workbook
    from industrial_platform import register_dataset

    workbook = process_uploaded_workbook(raw, filename)
    cleaned_sheets = workbook.get("cleaned_sheets", {})
    available_sheets = list(cleaned_sheets)
    if not available_sheets:
        raise ValueError("The workbook contains no cleanable sheets.")
    sheet = sheet_requested or available_sheets[0]
    if sheet not in cleaned_sheets:
        raise ValueError("Selected sheet not found. Available sheets: " + ", ".join(available_sheets[:50]))
    frame = cleaned_sheets[sheet]
    if frame.empty or len(frame.columns) == 0:
        raise ValueError("The selected sheet has no usable rows or columns.")
    transformations = [
        {
            "operation": "Excel Studio validated import",
            "filename": filename,
            "source_sha256": str(workbook.get("signature") or hashlib.sha256(raw).hexdigest()),
            "sheet": sheet,
            "provenance": "IMPORTED",
        }
    ]
    dataset_id = register_dataset(
        dataset_name,
        filename,
        frame,
        username=username,
        workspace=workspace,
        token=token,
        transformations=transformations,
        dataset_id=existing_dataset_id,
    )
    state = None
    try:
        from industrial_platform import _industrial_platform_session_state
        state = _industrial_platform_session_state()
    except Exception:
        state = {}
    registration = dict((state or {}).get("data_platform_latest_registration") or {})
    if str(registration.get("dataset_id") or dataset_id).upper() != dataset_id.upper():
        raise RuntimeError("Dataset registration returned a different dataset identity than the active version metadata.")
    return {
        "tool_id": "T020",
        "status": "IMMUTABLE_DATASET_VERSION_REGISTERED",
        "dataset_id": dataset_id,
        "version": int(registration.get("version") or (state or {}).get("data_platform_latest_version") or 1),
        "data_hash": str(registration.get("data_hash") or ""),
        "version_fingerprint": str(registration.get("version_fingerprint") or ""),
        "created_new_version": bool(registration.get("created_new_version")),
        "sheet_name": sheet,
        "row_count": int(len(frame)),
        "column_count": int(len(frame.columns)),
        "available_sheets": available_sheets,
        "data_provenance": "IMPORTED",
        "excel_workbook_result": workbook,
        "warning": "The immutable dataset registry stores normalized CSV content and version metadata. The original workbook is retained in the separate Excel Studio workspace record only when that workspace save succeeds; this tool does not claim resumable uploads or orphan cleanup.",
    }


def run_additional_tool(tool_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch only the explicitly implemented, deterministic tool IDs."""
    if not isinstance(payload, Mapping):
        raise ValueError("Tool payload must be a JSON object.")
    dispatch = {
        "T004": project_manager_action,
        "T006": recovery_action,
        "T073": scenario_manager_action,
        "T005": project_version_history_action,
        "T086": research_hypothesis_register_action,
        "T092": decision_register_action,
        "T061": linear_mixed_integer_optimization,
        "T067": multiobjective_optimization,
        "T068": robust_linear_optimization,
        "T039": capa_lifecycle_review,
        "T060": supply_chain_network_plan,
        "T074": calibrate_digital_twin,
        "T080": simulate_industrial_disruptions,
        "T094": evaluate_kpi_alerts,
        "T096": integration_configuration_status,
        "T097": validate_api_plugin_manifests,
        "T098": identity_audit_configuration_status,
        "T099": governance_recovery_action,
    }
    selected = str(tool_id or "").strip().upper()
    if selected == "T020":
        return dataset_version_register_action(payload)
    if selected in {"T011", "T012", "T013", "T014"}:
        return excel_workbook_target_action(selected, payload)
    if selected not in dispatch:
        raise ValueError(f"No additional deterministic handler is registered for {selected or 'blank tool ID'}.")
    return dispatch[selected](payload)


def get_tool_example_json(tool_id: str) -> str:
    """Return clearly synthetic example inputs for the Workbench JSON editor."""
    examples = {
        "T004": {"action": "create", "owner": "synthetic-project-owner", "name": "Synthetic capacity improvement study", "module": "Capacity Planning", "description": "Synthetic project metadata", "site": "SYNTHETIC", "linked_artifact_ids": ["RUN-SYN-001"], "metadata": {"provenance": "SYNTHETIC"}},
        "T005": {"action": "create", "owner": "synthetic-project-owner", "name": "Synthetic versioned project", "module": "Engineering Project", "state": {"scope": "SYNTHETIC", "baseline": {"capacity": 100}}},
        "T073": {
            "action": "create",
            "owner": "synthetic-scenario-owner",
            "name": "Synthetic what-if study",
            "baseline_scenario": "Baseline",
            "scenarios": [
                {"Scenario": "Baseline", "Cost": 100, "Service": 90},
                {"Scenario": "Alternative A", "Cost": 90, "Service": 92},
                {"Scenario": "Alternative B", "Cost": 110, "Service": 95},
            ],
            "data_provenance": "SYNTHETIC_EXAMPLE",
        },
        "T086": {"action": "create", "owner": "synthetic-research-owner", "title": "Synthetic process variability study", "research_question": "Does the controlled change alter measured variation?", "hypothesis": "The post-change variation is lower.", "null_hypothesis": "The post-change variation is not lower.", "methodology": "Controlled comparison", "primary_endpoint": "Standard deviation", "data_source": "SYNTHETIC_EXAMPLE", "evidence_references": ["SYNTHETIC-REF-001"]},
        "T092": {"action": "create", "owner": "synthetic-decision-owner", "title": "Synthetic capacity decision", "module": "Engineering Decision Center", "metrics": {"capacity_delta_units": 10}, "assumptions": {"provenance": "SYNTHETIC"}, "uncertainty": {"demand_range": "illustrative"}},
        "T061": {
            "variable_spec": {"x": {"low": 0, "up": 4, "category": "Continuous"}, "y": {"low": 0, "up": 8, "category": "Integer"}},
            "objective_coefficients": {"x": 3, "y": 5},
            "constraints": [{"name": "minimum_output", "coefficients": {"x": 1, "y": 1}, "sense": ">=", "rhs": 10}],
            "direction": "minimize",
            "time_limit_seconds": 10,
            "feasibility_tolerance": 1e-7,
            "data_provenance": "SYNTHETIC_EXAMPLE",
        },
        "T067": {
            "alternatives": [
                {"name": "Alternative A", "cost": 100, "quality": 80, "carbon": 25},
                {"name": "Alternative B", "cost": 90, "quality": 70, "carbon": 20},
                {"name": "Alternative C", "cost": 110, "quality": 95, "carbon": 30},
                {"name": "Alternative D", "cost": 120, "quality": 65, "carbon": 40},
            ],
            "objectives": [
                {"field": "cost", "weight": 0.4, "direction": "minimize"},
                {"field": "quality", "weight": 0.35, "direction": "maximize"},
                {"field": "carbon", "weight": 0.25, "direction": "minimize"},
            ],
            "data_provenance": "SYNTHETIC_EXAMPLE",
        },
        "T068": {
            "scenario_objectives": [[3, 2], [2, 4]],
            "A_eq": [[1, 1]],
            "b_eq": [10],
            "bounds": [[0, 10], [0, 10]],
            "data_provenance": "SYNTHETIC_EXAMPLE",
        },
        "T006": {
            "action": "snapshot",
            "current_index": 0,
            "history": [],
            "state": {"dataset": "SYNTHETIC-example", "accepted_rows": 10},
        },
        "T020": {
            "dataset_name": "SYNTHETIC-production-sample",
            "source": "synthetic_fixture",
            "provenance": "SYNTHETIC_EXAMPLE",
            "records": [{"period": "P1", "units": 100}, {"period": "P2", "units": 120}],
            "transformations": ["normalized column names", "validated units"],
            "history": [],
            "downstream_runs": [],
        },
        "T039": {
            "as_of_date": "2026-10-26",
            "records": [
                {
                    "capa_id": "SYN-CAPA-001",
                    "title": "Synthetic repeated seal defect",
                    "status": "OPEN",
                    "team": "Synthetic review team",
                    "problem_statement": "Illustrative repeated seal defect; not a plant record",
                    "containment_action": "Quarantine synthetic example lot",
                    "root_cause": "Pending investigation",
                    "corrective_action": "Validate replacement seal",
                    "implementation_evidence": "SYNTHETIC-WO-001",
                    "preventive_action": "Add receiving inspection",
                    "closure_review": "Effectiveness not yet confirmed",
                    "effectiveness_evidence": "",
                    "owner": "Example owner",
                    "reviewer": "",
                    "approval_reference": "",
                    "evidence_reference": "SYNTHETIC-REF-001",
                    "opened_date": "2026-10-01",
                    "due_date": "2026-11-01"
                }
            ],
            "transitions": [
                {
                    "capa_id": "SYN-CAPA-001",
                    "to_status": "IN_PROGRESS",
                    "reviewer": "Example reviewer",
                    "reason": "Move illustrative record to investigation",
                    "transitioned_at": "2026-10-26T12:00:00Z"
                }
            ]
        },
        "T060": {
            "suppliers": [{"id": "S1", "supply": 70}, {"id": "S2", "supply": 50}],
            "customers": [{"id": "C1", "demand": 60}, {"id": "C2", "demand": 40}],
            "routes": [
                {"supplier": "S1", "customer": "C1", "capacity": 70, "unit_cost": 2},
                {"supplier": "S1", "customer": "C2", "capacity": 30, "unit_cost": 5},
                {"supplier": "S2", "customer": "C1", "capacity": 20, "unit_cost": 3},
                {"supplier": "S2", "customer": "C2", "capacity": 50, "unit_cost": 1},
            ],
        },
        "T074": {
            "simulated_values": [10, 20, 30, 40, 50],
            "measured_values": [11, 21, 30, 41, 49],
            "scale_bounds": [0, 3],
            "offset_bounds": [-100, 100],
            "data_provenance": "SYNTHETIC_EXAMPLE",
        },
        "T080": {
            "baseline_capacity": 100,
            "baseline_demand": 90,
            "unit_cost": 12,
            "baseline_lead_time_hours": 24,
            "data_provenance": "SYNTHETIC_SCENARIO",
            "scenarios": [
                {"scenario": "supplier outage", "capacity_loss_pct": 35, "demand_change_pct": 10, "lead_time_multiplier": 1.5},
                {"scenario": "overtime recovery", "capacity_loss_pct": 10, "demand_change_pct": 0, "lead_time_multiplier": 1.1, "recovery_capacity_add": 20, "unit_cost_change_pct": 15},
            ],
        },
        "T094": {
            "as_of": "2026-10-26T00:00:00Z",
            "kpis": [
                {"name": "scrap_rate_pct", "value": 4.2, "threshold": 3.0, "operator": "gt", "unit": "%", "measured_at": "2026-10-26T00:00:00Z", "max_age_minutes": 1440},
                {"name": "planned_output", "value": 98, "threshold": 90, "operator": "lt", "unit": "units", "measured_at": "2026-10-26T00:00:00Z", "max_age_minutes": 1440},
            ],
            "existing_alerts": [],
        },
        "T096": {
            "profiles": [
                {"name": "Plant REST API", "protocol": "REST", "endpoint_env": "SHOIR_CONNECTOR_PLANT_ENDPOINT", "credential_env": "SHOIR_CONNECTOR_PLANT_TOKEN"},
                {"name": "MES", "protocol": "MES", "endpoint_env": "SHOIR_CONNECTOR_MES_ENDPOINT", "credential_env": "SHOIR_CONNECTOR_MES_CREDENTIAL"},
            ],
        },
        "T097": {
            "plugins": [
                {
                    "id": "example-report",
                    "name": "Example report contract",
                    "version": "1.0.0",
                    "api_version": "v1",
                    "minimum_tier": "Enterprise",
                    "scopes": ["read", "export"],
                    "entrypoint": "plugins/example_report.py",
                    "request_schema": {"type": "object", "properties": {"report_id": {"type": "string"}}, "required": ["report_id"]},
                    "response_schema": {"type": "object", "properties": {"status": {"type": "string"}}},
                    "enabled": False,
                }
            ],
        },
        "T098": {},
        "T099": {
            "action": "retention_review",
            "policies": [
                {"category": "workspace_exports", "retention_days": 365, "legal_hold": False, "review_owner": "NOT_ASSIGNED"},
                {"category": "audit_events", "retention_days": 730, "legal_hold": True, "review_owner": "NOT_ASSIGNED"},
            ],
        },
    }
    selected = str(tool_id or "").strip().upper()
    if selected not in examples:
        raise ValueError(f"No example is registered for {selected}.")
    return json.dumps(examples[selected], ensure_ascii=False, indent=2)
