"""Deterministic engines for the remaining Shoir-IE 100-tool targets.

The functions are deliberately explicit, input-driven and fail closed. They do
not execute arbitrary plugins, contact arbitrary connector endpoints, alter
production data, or claim that an external identity provider is active.
"""
from __future__ import annotations

import copy
import hashlib
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
    """Evaluate threshold, freshness and duplicate-suppression states for KPI records."""
    kpis = _records(payload.get("kpis"), "kpis", maximum=5000)
    as_of = _utc_timestamp(payload.get("as_of"), "as_of", allow_missing=True) or datetime.now(timezone.utc)
    history = payload.get("existing_alerts", [])
    if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
        raise ValueError("existing_alerts must be a list of prior alert objects.")
    seen = {
        str(item.get("fingerprint"))
        for item in history
        if str(item.get("state", "OPEN")).upper() == "OPEN" and item.get("fingerprint")
    }
    results, alerts, stale_count = [], [], 0
    valid_ops = {"gt": lambda v, t: v > t, "gte": lambda v, t: v >= t, "lt": lambda v, t: v < t, "lte": lambda v, t: v <= t}
    for item in kpis:
        name = _nonempty_text(item.get("name"), "KPI name", 200)
        val = _number(item.get("value"), f"{name}.value")
        threshold = _number(item.get("threshold"), f"{name}.threshold")
        op = str(item.get("operator", "gt")).lower()
        if op not in valid_ops:
            raise ValueError(f"{name}.operator must be one of gt, gte, lt, lte.")
        measured_at = _utc_timestamp(item.get("measured_at"), f"{name}.measured_at")
        max_age = _number(item.get("max_age_minutes", 60), f"{name}.max_age_minutes", minimum=0)
        age_minutes = max(0.0, (as_of - measured_at).total_seconds() / 60.0)
        stale = age_minutes > max_age
        breached = bool(valid_ops[op](val, threshold))
        state = "STALE" if stale else ("BREACHED" if breached else "OK")
        if stale:
            stale_count += 1
        row = {
            "name": name, "value": val, "threshold": threshold, "operator": op,
            "unit": str(item.get("unit") or ""), "measured_at": measured_at.isoformat(),
            "age_minutes": age_minutes, "max_age_minutes": max_age,
            "freshness": "STALE" if stale else "FRESH", "status": state,
        }
        results.append(row)
        if not stale and breached:
            fp = _canonical_hash({"name": name.casefold(), "operator": op, "threshold": threshold})
            alert = {**row, "fingerprint": fp, "alert_id": "alert-" + fp[:16], "new_alert": fp not in seen}
            alerts.append(alert)
            seen.add(fp)
    return {
        "tool_id": "T094",
        "status": "KPI_EVALUATION_COMPLETE",
        "as_of": as_of.isoformat(),
        "kpi_count": len(results),
        "stale_kpi_count": stale_count,
        "breached_kpi_count": sum(r["status"] == "BREACHED" for r in results),
        "new_alert_count": sum(bool(a["new_alert"]) for a in alerts),
        "kpis": pd.DataFrame(results),
        "alerts": pd.DataFrame(alerts),
        "alert_records": alerts,
        "warning": "Alerts are computed from the KPI records supplied to this run. Cross-session deduplication and notification delivery require saving alert_records to a protected durable store and configuring an approved notification service.",
    }


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


def integration_configuration_status(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Inspect connector configuration; only the secure generic REST adapter can be tested.

    Configuration inspection is always network-free. Other named vendors/transports
    remain metadata-only until separately reviewed adapters exist.
    """
    action = str(payload.get("action") or "inspect").strip().lower()
    if action == "verify_rest_read":
        profile = payload.get("profile")
        if not isinstance(profile, dict):
            raise ValueError("profile must be a JSON object for the approved REST connector.")
        _require_connector_operator()
        include_sample_data = payload.get("include_sample_data", False)
        if not isinstance(include_sample_data, bool):
            raise ValueError("include_sample_data must be a JSON boolean.")
        return verify_readonly_rest_connector(
            profile,
            include_sample_data=include_sample_data,
        )
    if action not in {"inspect", "check_configuration"}:
        raise ValueError("action must be inspect or verify_rest_read.")
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

        rest_env_match = re.fullmatch(r"(SHOIR_CONNECTOR_[A-Z0-9_]+)_ENDPOINT", endpoint_env)
        rest_names_match = bool(
            rest_env_match and credential_env == rest_env_match.group(1) + "_TOKEN"
        )
        if protocol != "REST":
            status = "PROVIDER_ADAPTER_NOT_IMPLEMENTED"
            warning = (
                "Configuration metadata only. No provider-specific network adapter is implemented; "
                "SAP/Oracle/WMS/MES/ERP, SQL, MQTT and OPC-UA are not live-connected by this tool."
            )
        elif endpoint_value and credential_value and endpoint_valid and rest_names_match:
            status = "CONFIGURED_AWAITING_HOST_ALLOWLIST_AND_AUTHORIZED_TEST"
            warning = (
                "No outbound network call was attempted. Live T096 verification additionally requires "
                "the matching *_ENABLED setting, an exact host allowlist, TLS/DNS checks and an authorized test."
            )
        else:
            status = "NOT_CONNECTED_CONFIGURATION_INCOMPLETE"
            warning = (
                "No outbound network call was attempted. The generic T096 adapter requires an HTTPS endpoint "
                "variable ending in _ENDPOINT and its paired _TOKEN secret variable."
            )
        output.append({
            "name": name,
            "protocol": protocol,
            "endpoint_env": endpoint_env,
            "endpoint_configured": bool(endpoint_value),
            "endpoint_syntax_valid": endpoint_valid if endpoint_value else False,
            "credential_env": credential_env,
            "credential_configured": bool(credential_value),
            "status": status,
            "last_test_at": None,
            "last_sync_at": None,
            "warning": warning,
        })
    return {
        "tool_id": "T096",
        "status": "CONFIGURATION_INSPECTED",
        "profiles": pd.DataFrame(output),
        "profile_records": output,
        "connected_count": 0,
        "warning": (
            "Connection state is intentionally not reported as CONNECTED. The only generic live path is the "
            "authorized HTTPS REST verifier; provider-specific adapters require implementation and evidence."
        ),
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
    """Report OIDC/MFA/audit configuration readiness without revealing configured values."""
    env_map = {
        "issuer_url": "SHOIR_OIDC_ISSUER_URL",
        "client_id": "SHOIR_OIDC_CLIENT_ID",
        "client_secret": "SHOIR_OIDC_CLIENT_SECRET",
        "redirect_uri": "SHOIR_OIDC_REDIRECT_URI",
        "scopes": "SHOIR_OIDC_SCOPES",
        "mfa_enforced": "SHOIR_MFA_ENFORCED",
        "audit_log_enabled": "SHOIR_AUDIT_LOG_ENABLED",
    }
    configured_values = {key: _configuration_value(name) for key, name in env_map.items()}
    present = {key: bool(value) for key, value in configured_values.items()}
    issuer = configured_values["issuer_url"]
    redirect = configured_values["redirect_uri"]
    scopes = set(configured_values["scopes"].lower().split())
    issuer_parsed = urlparse(issuer) if issuer else None
    redirect_parsed = urlparse(redirect) if redirect else None
    issuer_valid = bool(issuer_parsed and issuer_parsed.scheme == "https" and issuer_parsed.netloc)
    redirect_valid = bool(redirect_parsed and redirect_parsed.scheme == "https" and redirect_parsed.netloc)
    mfa_enforced = configured_values["mfa_enforced"].lower() in {"true", "1", "yes", "enforced"}
    audit_enabled = configured_values["audit_log_enabled"].lower() in {"true", "1", "yes", "enabled"}
    missing = [env_map[key] for key, value in present.items() if not value]
    problems = []
    if present["issuer_url"] and not issuer_valid:
        problems.append("OIDC issuer URL must use HTTPS and include a host.")
    if present["redirect_uri"] and not redirect_valid:
        problems.append("OIDC redirect URI must use HTTPS and include a host.")
    if present["scopes"] and "openid" not in scopes:
        problems.append("OIDC scopes must include openid.")
    if present["mfa_enforced"] and not mfa_enforced:
        problems.append("MFA enforcement is not explicitly enabled.")
    if present["audit_log_enabled"] and not audit_enabled:
        problems.append("Audit logging is not explicitly enabled.")
    complete = not missing and not problems and issuer_valid and redirect_valid and "openid" in scopes and mfa_enforced and audit_enabled
    status = (
        "NOT_CONFIGURED" if missing
        else "CONFIGURATION_INVALID" if problems or not complete
        else "READY_FOR_AUTHORIZED_IDP_TEST"
    )
    return {
        "tool_id": "T098",
        "status": status,
        "provider": "OIDC-compatible identity provider (not detected/activated by this check)",
        "environment_variables": pd.DataFrame([
            {"setting": key, "environment_variable": env_name, "configured": present[key], "value_exposed": False}
            for key, env_name in env_map.items()
        ]),
        "missing_variables": missing,
        "configuration_problems": problems,
        "oidc_issuer_syntax_valid": issuer_valid,
        "redirect_uri_syntax_valid": redirect_valid,
        "openid_scope_present": "openid" in scopes,
        "mfa_enforced_flag": mfa_enforced,
        "audit_logging_flag": audit_enabled,
        "sso_active": False,
        "mfa_active": False,
        "oidc_login_flow_implemented": False,
        "provider_authentication_tested": False,
        "provider_mfa_evidence_verified": False,
        "audit_sink_configured": False,
        "audit_persistence_verified": False,
        "verified_at": None,
        "required_external_actions": [
            "Select an approved identity provider and configure its application/client and exact callback/logout URIs.",
            "Implement and review the provider-supported login/callback/session integration in the existing authentication architecture.",
            "Validate issuer, audience, signature, state, nonce, expiry, redirect and logout/revocation behavior using a maintained protocol implementation.",
            "Map a validated provider identity to the existing application account, role, tier and workspace without privilege elevation.",
            "Prove MFA from the provider's documented policy/result; environment flags alone are not evidence.",
            "Configure a protected durable audit destination and verify representative events were written and can be read under authorized access.",
            "Run authenticated staging allow/deny, cross-workspace, expired/revoked session and audit-failure tests."
        ],
        "warning": "This is a readiness check only. Configuration is not authentication, provider policy is not verified MFA evidence, and an audit toggle is not proof of a durable audit write. SSO/MFA and audit persistence remain unverified until the external protocol flow and durable event path are implemented and tested on authorized staging.",
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


def run_additional_tool(tool_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Dispatch only the explicitly implemented, deterministic tool IDs."""
    if not isinstance(payload, Mapping):
        raise ValueError("Tool payload must be a JSON object.")
    dispatch = {
        "T006": recovery_action,
        "T020": dataset_version_lineage,
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
    if selected not in dispatch:
        raise ValueError(f"No additional deterministic handler is registered for {selected or 'blank tool ID'}.")
    return dispatch[selected](payload)


def get_tool_example_json(tool_id: str) -> str:
    """Return clearly synthetic example inputs for the Workbench JSON editor."""
    examples = {
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
                {"name": "MES REST API (generic REST only)", "protocol": "REST", "endpoint_env": "SHOIR_CONNECTOR_MES_ENDPOINT", "credential_env": "SHOIR_CONNECTOR_MES_TOKEN"},
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
