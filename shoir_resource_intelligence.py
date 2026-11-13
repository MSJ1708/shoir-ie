"""Industrial Resource Intelligence: deterministic engineering foundation.

This module deliberately contains no live plant connector, supplier marketplace,
regulatory certification, or AI-authoritative decision. Inputs are caller supplied
and must retain their declared provenance. The calculations are deterministic and
return explicit incomplete/infeasible states rather than inventing data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping, Sequence
from uuid import uuid4

import numpy as np
from scipy.optimize import linprog

PROVENANCE_VALUES = ("LIVE", "IMPORTED", "MANUAL", "SYNTHETIC", "SIMULATED", "MOCK", "STALE")
COMPATIBILITY_STATUSES = (
    "TECHNICALLY_COMPATIBLE",
    "COMPATIBLE_SUBJECT_TO_TREATMENT",
    "REQUIRES_LAB_TESTING",
    "REQUIRES_ENGINEERING_REVIEW",
    "TECHNICALLY_INCOMPATIBLE",
    "INSUFFICIENT_DATA",
)
CASCADE_ORDER = (
    "PREVENT", "REDUCE", "RECOVER", "REUSE_IN_PROCESS", "REUSE_IN_FACILITY",
    "TREAT", "SUBSTITUTE", "EXTERNAL_EXCHANGE", "DISPOSE",
)


class ResourceValidationError(ValueError):
    """Raised when an engineering input is invalid or dimensionally ambiguous."""


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ResourceValidationError(f"{field} is required.")
    if len(result) > 240:
        raise ResourceValidationError(f"{field} must be 240 characters or fewer.")
    if any(ord(char) < 32 for char in result):
        raise ResourceValidationError(f"{field} contains unsupported control characters.")
    return result


def _number(value: Any, field: str, *, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResourceValidationError(f"{field} must be a finite number.") from exc
    if not isfinite(result):
        raise ResourceValidationError(f"{field} must be a finite number.")
    if minimum is not None and result < minimum:
        raise ResourceValidationError(f"{field} must be at least {minimum}.")
    return result


def _utc_timestamp(value: Any, field: str) -> str | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ResourceValidationError(f"{field} must be an ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ResourceValidationError(f"{field} must include a timezone offset.")
    return parsed.astimezone(timezone.utc).isoformat()


def validate_resource_passport(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a resource passport without inventing missing values."""
    if not isinstance(payload, Mapping):
        raise ResourceValidationError("Resource passport must be an object.")
    provenance = _text(payload.get("provenance"), "provenance").upper()
    if provenance not in PROVENANCE_VALUES:
        raise ResourceValidationError(f"provenance must be one of {', '.join(PROVENANCE_VALUES)}.")
    quantity = _number(payload.get("available_quantity"), "available_quantity", minimum=0)
    if quantity <= 0:
        raise ResourceValidationError("available_quantity must be greater than zero.")
    quality = payload.get("quality") or {}
    if not isinstance(quality, Mapping):
        raise ResourceValidationError("quality must be an object of numeric property measurements.")
    normalized_quality = {
        _text(key, "quality property"): _number(value, f"quality.{key}")
        for key, value in quality.items()
    }
    return {
        "resource_id": str(payload.get("resource_id") or uuid4()),
        "facility_id": _text(payload.get("facility_id"), "facility_id"),
        "name": _text(payload.get("name"), "name"),
        "resource_type": _text(payload.get("resource_type"), "resource_type"),
        "category": str(payload.get("category") or "OTHER").strip().upper(),
        "available_quantity": quantity,
        "unit": _text(payload.get("unit"), "unit"),
        "quality": normalized_quality,
        "temperature_c": (
            _number(payload["temperature_c"], "temperature_c")
            if payload.get("temperature_c") not in (None, "") else None
        ),
        "pressure_kpa": (
            _number(payload["pressure_kpa"], "pressure_kpa", minimum=0)
            if payload.get("pressure_kpa") not in (None, "") else None
        ),
        "availability_window": str(payload.get("availability_window") or "").strip(),
        "treatment_notes": str(payload.get("treatment_notes") or "").strip(),
        "safety_restrictions": str(payload.get("safety_restrictions") or "").strip(),
        "source_reference": str(payload.get("source_reference") or "").strip(),
        "measured_at": _utc_timestamp(payload.get("measured_at"), "measured_at"),
        "provenance": provenance,
        "created_at": str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "approval_status": str(payload.get("approval_status") or "DRAFT").upper(),
    }


def assess_resource_compatibility(
    supply: Mapping[str, Any],
    demand: Mapping[str, Any],
    *,
    treatment_plan: Mapping[str, Any] | None = None,
    laboratory_test_required: bool = False,
    engineering_review_required: bool = False,
) -> dict[str, Any]:
    """Compare declared resource properties against a buyer's explicit operating window.

    This is a screening calculation only. A treatment qualification is accepted as
    a recorded user assertion with an evidence reference, not independently verified.
    """
    reasons: list[str] = []
    try:
        supply_type = _text(supply.get("resource_type"), "supply.resource_type").casefold()
        demand_type = _text(demand.get("resource_type"), "demand.resource_type").casefold()
        supply_unit = _text(supply.get("unit"), "supply.unit").casefold()
        demand_unit = _text(demand.get("unit"), "demand.unit").casefold()
    except ResourceValidationError as exc:
        return {"status": "INSUFFICIENT_DATA", "reasons": [str(exc)], "qualification_is_user_asserted": False}

    if supply_type != demand_type or supply_unit != demand_unit:
        return {
            "status": "TECHNICALLY_INCOMPATIBLE",
            "reasons": ["Resource type or unit does not match; no implicit unit conversion is performed."],
            "qualification_is_user_asserted": False,
        }

    quality = supply.get("quality")
    limits = demand.get("quality_limits")
    if not isinstance(quality, Mapping) or not isinstance(limits, Mapping) or not limits:
        return {
            "status": "INSUFFICIENT_DATA",
            "reasons": ["Supply measurements and explicit buyer quality limits are required."],
            "qualification_is_user_asserted": False,
        }

    violations: list[str] = []
    for property_name, bounds in limits.items():
        if property_name not in quality and property_name not in supply:
            return {
                "status": "INSUFFICIENT_DATA",
                "reasons": [f"Supply measurement is missing required property: {property_name}."],
                "qualification_is_user_asserted": False,
            }
        if not isinstance(bounds, Mapping):
            return {
                "status": "INSUFFICIENT_DATA",
                "reasons": [f"Buyer limits for {property_name} must be an object."],
                "qualification_is_user_asserted": False,
            }
        raw_value = quality[property_name] if property_name in quality else supply[property_name]
        value = _number(raw_value, f"supply.{property_name}")
        lower = _number(bounds["min"], f"demand.quality_limits.{property_name}.min") if bounds.get("min") is not None else None
        upper = _number(bounds["max"], f"demand.quality_limits.{property_name}.max") if bounds.get("max") is not None else None
        if lower is None and upper is None:
            return {
                "status": "INSUFFICIENT_DATA",
                "reasons": [f"At least one numeric limit is required for {property_name}."],
                "qualification_is_user_asserted": False,
            }
        if lower is not None and value < lower:
            violations.append(f"{property_name}={value} is below minimum {lower}.")
        if upper is not None and value > upper:
            violations.append(f"{property_name}={value} is above maximum {upper}.")

    if violations:
        plan = treatment_plan or {}
        residual = plan.get("residual_quality") if isinstance(plan, Mapping) else None
        evidence = str(plan.get("qualification_evidence") or "").strip() if isinstance(plan, Mapping) else ""
        qualified_by = str(plan.get("qualified_by") or "").strip() if isinstance(plan, Mapping) else ""
        if isinstance(residual, Mapping) and evidence and qualified_by:
            residual_supply = dict(supply)
            residual_supply["quality"] = residual
            residual_assessment = assess_resource_compatibility(
                residual_supply, demand,
                laboratory_test_required=laboratory_test_required,
                engineering_review_required=engineering_review_required,
            )
            if residual_assessment["status"] == "TECHNICALLY_COMPATIBLE":
                return {
                    "status": "COMPATIBLE_SUBJECT_TO_TREATMENT",
                    "reasons": violations + ["Declared treatment residual quality meets the entered limits."],
                    "treatment": dict(plan),
                    "qualification_is_user_asserted": True,
                    "verification_warning": "Treatment qualification evidence and approver identity have not been independently verified.",
                }
        return {
            "status": "TECHNICALLY_INCOMPATIBLE",
            "reasons": violations + ["Treatment has not been qualified with residual-quality evidence."],
            "qualification_is_user_asserted": False,
        }

    if laboratory_test_required:
        status = "REQUIRES_LAB_TESTING"
        reasons.append("Laboratory testing is required before technical qualification.")
    elif engineering_review_required:
        status = "REQUIRES_ENGINEERING_REVIEW"
        reasons.append("Additional engineering review is required before technical qualification.")
    else:
        status = "TECHNICALLY_COMPATIBLE"
        reasons.append("Entered numeric quality values are within the entered buyer limits.")
    return {"status": status, "reasons": reasons, "qualification_is_user_asserted": False}


def calculate_resource_balance(
    input_quantity: float,
    output_quantity: float,
    *,
    unit: str,
    tolerance_percent: float = 1.0,
) -> dict[str, Any]:
    """Calculate a one-period, same-unit balance; does not infer leak root cause."""
    incoming = _number(input_quantity, "input_quantity", minimum=0)
    outgoing = _number(output_quantity, "output_quantity", minimum=0)
    tolerance = _number(tolerance_percent, "tolerance_percent", minimum=0)
    unit_label = _text(unit, "unit")
    if incoming <= 0:
        raise ResourceValidationError("input_quantity must be greater than zero.")
    difference = incoming - outgoing
    difference_percent = 100.0 * difference / incoming
    anomaly = abs(difference_percent) > tolerance
    return {
        "status": "ANOMALY_SUSPECTED" if anomaly else "WITHIN_TOLERANCE",
        "input_quantity": incoming,
        "output_quantity": outgoing,
        "unreconciled_quantity": difference,
        "difference_percent": difference_percent,
        "tolerance_percent": tolerance,
        "unit": unit_label,
        "interpretation": (
            "A discrepancy is suspected; investigate meters, inventory changes, timing and unmeasured streams. "
            "This is not proof of a confirmed leak or loss."
            if anomaly else "The entered balance difference is within the configured tolerance."
        ),
    }


def detect_resource_loss(
    input_quantity: float,
    accounted_quantity: float,
    *,
    unit: str,
    tolerance_percent: float = 1.0,
    evidence_provenance: str = "MANUAL",
) -> dict[str, Any]:
    result = calculate_resource_balance(
        input_quantity, accounted_quantity, unit=unit, tolerance_percent=tolerance_percent
    )
    provenance = _text(evidence_provenance, "evidence_provenance").upper()
    if provenance not in PROVENANCE_VALUES:
        raise ResourceValidationError("Unknown evidence provenance.")
    result.update({
        "finding_type": (
            "SUSPECTED_RESOURCE_LOSS" if result["unreconciled_quantity"] > 0
            else "UNRECONCILED_BALANCE" if result["status"] == "ANOMALY_SUSPECTED"
            else "NO_MATERIAL_ANOMALY"
        ),
        "evidence_provenance": provenance,
        "confirmation_status": "NOT_CONFIRMED",
    })
    return result


def optimize_resource_network(
    supplies: Sequence[Mapping[str, Any]],
    demands: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
    *,
    allow_shortage: bool = False,
    shortage_penalty_per_unit: float = 1_000_000.0,
) -> dict[str, Any]:
    """Solve a constrained transportation LP with independent qualification checks.

    Each demand must be fully satisfied unless allow_shortage=True. Supply limits,
    route capacities, resource type, units and quality constraints are enforced.
    """
    if not supplies or not demands:
        raise ResourceValidationError("At least one supply and one demand are required.")
    supply_by_id: dict[str, dict[str, Any]] = {}
    demand_by_id: dict[str, dict[str, Any]] = {}
    for item in supplies:
        sid = _text(item.get("resource_id") or item.get("id"), "supply id")
        if sid in supply_by_id:
            raise ResourceValidationError(f"Duplicate supply id: {sid}.")
        supply_by_id[sid] = dict(item, resource_id=sid)
        _number(item.get("available_quantity"), f"supply {sid} available_quantity", minimum=0)
        _text(item.get("unit"), f"supply {sid} unit")
    for item in demands:
        did = _text(item.get("demand_id") or item.get("id"), "demand id")
        if did in demand_by_id:
            raise ResourceValidationError(f"Duplicate demand id: {did}.")
        demand_by_id[did] = dict(item, demand_id=did)
        _number(item.get("required_quantity"), f"demand {did} required_quantity", minimum=0)
        if float(item["required_quantity"]) <= 0:
            raise ResourceValidationError(f"demand {did} required_quantity must be greater than zero.")
        _text(item.get("unit"), f"demand {did} unit")

    edges: list[dict[str, Any]] = []
    rejected_routes: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for raw in routes:
        sid = _text(raw.get("supply_id"), "route.supply_id")
        did = _text(raw.get("demand_id"), "route.demand_id")
        if sid not in supply_by_id or did not in demand_by_id:
            raise ResourceValidationError(f"Route references unknown supply or demand: {sid} -> {did}.")
        if (sid, did) in seen_pairs:
            raise ResourceValidationError(f"Duplicate route: {sid} -> {did}.")
        seen_pairs.add((sid, did))
        supply, demand = supply_by_id[sid], demand_by_id[did]
        compatibility = assess_resource_compatibility(
            supply, demand,
            treatment_plan=raw.get("treatment_plan"),
            laboratory_test_required=bool(raw.get("laboratory_test_required", False)),
            engineering_review_required=bool(raw.get("engineering_review_required", False)),
        )
        if compatibility["status"] != "TECHNICALLY_COMPATIBLE":
            rejected_routes.append({"supply_id": sid, "demand_id": did, **compatibility})
            continue
        cost = (
            _number(raw.get("unit_cost"), "route.unit_cost", minimum=0)
            + _number(raw.get("treatment_cost_per_unit", 0), "route.treatment_cost_per_unit", minimum=0)
            + _number(raw.get("transport_cost_per_unit", 0), "route.transport_cost_per_unit", minimum=0)
        )
        capacity = _number(raw.get("capacity", min(
            supply["available_quantity"], demand["required_quantity"]
        )), "route.capacity", minimum=0)
        if capacity <= 0:
            continue
        edges.append({
            "supply_id": sid, "demand_id": did, "unit_cost": cost,
            "capacity": capacity, "compatibility": compatibility["status"],
        })

    if not edges:
        return {
            "status": "INFEASIBLE",
            "reason": "No route passed the independent type, unit and quality screening gate.",
            "allocations": [], "rejected_routes": rejected_routes,
            "objective_cost": None, "unmet_demand": [
                {"demand_id": d["demand_id"], "quantity": d["required_quantity"], "unit": d["unit"]}
                for d in demand_by_id.values()
            ],
        }

    n_edges, n_demands = len(edges), len(demand_by_id)
    n_vars = n_edges + (n_demands if allow_shortage else 0)
    objective = [edge["unit_cost"] for edge in edges]
    if allow_shortage:
        penalty = _number(shortage_penalty_per_unit, "shortage_penalty_per_unit", minimum=0)
        objective += [penalty] * n_demands

    supply_ids = list(supply_by_id)
    demand_ids = list(demand_by_id)
    a_ub, b_ub = [], []
    for sid in supply_ids:
        row = [1.0 if edge["supply_id"] == sid else 0.0 for edge in edges] + ([0.0] * n_demands if allow_shortage else [])
        a_ub.append(row)
        b_ub.append(float(supply_by_id[sid]["available_quantity"]))

    a_eq, b_eq = [], []
    for index, did in enumerate(demand_ids):
        row = [1.0 if edge["demand_id"] == did else 0.0 for edge in edges]
        if allow_shortage:
            row += [1.0 if j == index else 0.0 for j in range(n_demands)]
        a_eq.append(row)
        b_eq.append(float(demand_by_id[did]["required_quantity"]))

    bounds = [(0, edge["capacity"]) for edge in edges]
    if allow_shortage:
        bounds += [(0, float(demand_by_id[did]["required_quantity"])) for did in demand_ids]
    solved = linprog(
        c=np.asarray(objective, dtype=float),
        A_ub=np.asarray(a_ub, dtype=float),
        b_ub=np.asarray(b_ub, dtype=float),
        A_eq=np.asarray(a_eq, dtype=float),
        b_eq=np.asarray(b_eq, dtype=float),
        bounds=bounds,
        method="highs",
    )
    if not solved.success:
        return {
            "status": "INFEASIBLE",
            "reason": str(solved.message),
            "solver": "scipy.optimize.linprog(method=highs)",
            "allocations": [], "rejected_routes": rejected_routes,
            "objective_cost": None, "unmet_demand": [
                {"demand_id": d["demand_id"], "quantity": d["required_quantity"], "unit": d["unit"]}
                for d in demand_by_id.values()
            ],
        }

    allocations = []
    for index, edge in enumerate(edges):
        quantity = float(solved.x[index])
        if quantity > 1e-8:
            allocations.append({**edge, "quantity": quantity, "unit": demand_by_id[edge["demand_id"]]["unit"]})
    unmet = []
    for index, did in enumerate(demand_ids):
        quantity = float(solved.x[n_edges + index]) if allow_shortage else 0.0
        if quantity > 1e-7:
            unmet.append({"demand_id": did, "quantity": quantity, "unit": demand_by_id[did]["unit"]})
    # Independent physical reconciliation, not just a solver success flag.
    allocated_supply = {sid: 0.0 for sid in supply_ids}
    allocated_demand = {did: 0.0 for did in demand_ids}
    for row in allocations:
        allocated_supply[row["supply_id"]] += row["quantity"]
        allocated_demand[row["demand_id"]] += row["quantity"]
    violations = []
    for sid, quantity in allocated_supply.items():
        if quantity > float(supply_by_id[sid]["available_quantity"]) + 1e-7:
            violations.append(f"Supply over-allocation: {sid}.")
    for did, quantity in allocated_demand.items():
        expected = float(demand_by_id[did]["required_quantity"])
        if quantity + (next((x["quantity"] for x in unmet if x["demand_id"] == did), 0.0)) < expected - 1e-7:
            violations.append(f"Demand reconciliation failed: {did}.")
        if not allow_shortage and quantity < expected - 1e-7:
            violations.append(f"Demand not fully met: {did}.")
    if violations:
        return {
            "status": "VALIDATION_FAILED", "reason": "; ".join(violations),
            "solver": "scipy.optimize.linprog(method=highs)",
            "allocations": allocations, "rejected_routes": rejected_routes,
            "objective_cost": None, "unmet_demand": unmet,
        }
    return {
        "status": "FEASIBLE_WITH_SHORTAGE" if unmet else "OPTIMAL",
        "solver": "scipy.optimize.linprog(method=highs)",
        "objective_cost": float(solved.fun),
        "allocations": allocations,
        "rejected_routes": rejected_routes,
        "unmet_demand": unmet,
        "binding_supply": [
            sid for sid, quantity in allocated_supply.items()
            if abs(quantity - float(supply_by_id[sid]["available_quantity"])) <= 1e-7
        ],
        "assumptions": [
            "Single-period, deterministic allocation.",
            "Entered unit costs are additive and expressed per allocated quantity.",
            "No implicit unit conversion, pipeline capacity, production schedule or permit approval is inferred.",
            "Compatibility is a screening gate, not a complete process engineering or safety certification.",
        ],
    }


def simulate_supplier_disruption(
    supplies: Sequence[Mapping[str, Any]],
    demands: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
    *,
    supplier_id: str,
    supply_reduction_fraction: float,
) -> dict[str, Any]:
    """Re-solve one-period allocation after an explicit supplier-capacity shock."""
    fraction = _number(supply_reduction_fraction, "supply_reduction_fraction", minimum=0)
    if fraction > 1:
        raise ResourceValidationError("supply_reduction_fraction must not exceed 1.")
    target = _text(supplier_id, "supplier_id")
    changed, found = [], False
    for source in supplies:
        item = dict(source)
        sid = str(item.get("resource_id") or item.get("id") or "")
        if sid == target:
            found = True
            original = _number(item.get("available_quantity"), "available_quantity", minimum=0)
            item["available_quantity"] = original * (1.0 - fraction)
        changed.append(item)
    if not found:
        raise ResourceValidationError(f"Unknown supplier id: {target}.")
    result = optimize_resource_network(changed, demands, routes, allow_shortage=True)
    return {
        "status": result["status"],
        "supplier_id": target,
        "supply_reduction_fraction": fraction,
        "remaining_supplier_quantity": next(
            float(x["available_quantity"]) for x in changed
            if str(x.get("resource_id") or x.get("id")) == target
        ),
        "allocation_result": result,
        "recovery_time": None,
        "recovery_time_note": "Not estimated: no validated restoration-time data was supplied.",
    }


def evaluate_safety_gate(
    *,
    critical_failure: bool,
    laboratory_required: bool,
    laboratory_passed: bool | None,
    engineering_approval_reference: str = "",
    safety_approval_reference: str = "",
    environmental_approval_reference: str = "",
) -> dict[str, Any]:
    """Fail-closed approval gate; evidence references are recorded, not verified."""
    blockers = []
    if critical_failure:
        blockers.append("Critical safety restriction or hazard failure is present.")
    if laboratory_required and laboratory_passed is not True:
        blockers.append("Required laboratory result has not passed.")
    if not str(engineering_approval_reference).strip():
        blockers.append("Qualified engineering approval reference is missing.")
    if not str(safety_approval_reference).strip():
        blockers.append("Safety approval reference is missing.")
    if not str(environmental_approval_reference).strip():
        blockers.append("Environmental approval reference is missing.")
    status = "REJECTED" if critical_failure else ("APPROVAL_PENDING" if blockers else "APPROVAL_EVIDENCE_RECORDED")
    return {
        "status": status,
        "blockers": blockers,
        "approval_references": {
            "engineering": str(engineering_approval_reference).strip(),
            "safety": str(safety_approval_reference).strip(),
            "environmental": str(environmental_approval_reference).strip(),
        },
        "independent_verification": "NOT_PERFORMED",
        "operational_authorization": False,
    }


def calculate_exchange_value(
    *,
    avoided_disposal_cost: float,
    supplier_sale_revenue: float,
    supplier_preparation_cost: float,
    supplier_testing_cost: float,
    supplier_handling_delivery_cost: float,
    avoided_alternative_purchase_cost: float,
    buyer_treatment_cost: float,
    buyer_transport_cost: float,
    buyer_testing_cost: float,
    buyer_additional_operating_cost: float,
    currency: str,
    evidence_status: str = "ESTIMATED",
) -> dict[str, Any]:
    """Calculate party economics and a transfer-neutral network benefit.

    Supplier sale revenue / buyer purchase payment is an internal transfer and is
    excluded from the network total. Avoided external costs and real resource
    preparation, treatment, logistics and operating costs remain in the boundary.
    """
    names = (
        "avoided_disposal_cost", "supplier_sale_revenue", "supplier_preparation_cost",
        "supplier_testing_cost", "supplier_handling_delivery_cost",
        "avoided_alternative_purchase_cost", "buyer_treatment_cost",
        "buyer_transport_cost", "buyer_testing_cost", "buyer_additional_operating_cost",
    )
    input_values = {
        "avoided_disposal_cost": avoided_disposal_cost,
        "supplier_sale_revenue": supplier_sale_revenue,
        "supplier_preparation_cost": supplier_preparation_cost,
        "supplier_testing_cost": supplier_testing_cost,
        "supplier_handling_delivery_cost": supplier_handling_delivery_cost,
        "avoided_alternative_purchase_cost": avoided_alternative_purchase_cost,
        "buyer_treatment_cost": buyer_treatment_cost,
        "buyer_transport_cost": buyer_transport_cost,
        "buyer_testing_cost": buyer_testing_cost,
        "buyer_additional_operating_cost": buyer_additional_operating_cost,
    }
    values = {name: _number(input_values[name], name, minimum=0) for name in names}
    currency_code = _text(currency, "currency").upper()
    if len(currency_code) != 3 or not currency_code.isalpha():
        raise ResourceValidationError("currency must be a three-letter currency code.")
    status = _text(evidence_status, "evidence_status").upper()
    if status not in {"FORECAST", "ESTIMATED", "MEASURED", "INDEPENDENTLY_VERIFIED"}:
        raise ResourceValidationError("Unsupported evidence_status.")
    supplier = (
        values["avoided_disposal_cost"] + values["supplier_sale_revenue"]
        - values["supplier_preparation_cost"] - values["supplier_testing_cost"]
        - values["supplier_handling_delivery_cost"]
    )
    buyer = (
        values["avoided_alternative_purchase_cost"] - values["buyer_treatment_cost"]
        - values["buyer_transport_cost"] - values["buyer_testing_cost"]
        - values["buyer_additional_operating_cost"]
    )
    network = (
        values["avoided_disposal_cost"] + values["avoided_alternative_purchase_cost"]
        - values["supplier_preparation_cost"] - values["supplier_testing_cost"]
        - values["supplier_handling_delivery_cost"] - values["buyer_treatment_cost"]
        - values["buyer_transport_cost"] - values["buyer_testing_cost"]
        - values["buyer_additional_operating_cost"]
    )
    # No software-only evidence status can establish independent verification.
    if status == "INDEPENDENTLY_VERIFIED":
        status = "MEASURED_PENDING_INDEPENDENT_EVIDENCE"
    return {
        "currency": currency_code,
        "supplier_benefit": supplier,
        "buyer_benefit": buyer,
        "network_benefit_transfer_neutral": network,
        "evidence_status": status,
        "independent_verification": "NOT_ESTABLISHED",
        "boundary_note": "Supplier sale revenue is a buyer payment transfer and is excluded from network benefit to avoid double-counting.",
        "inputs": values,
    }


def propagate_network_impact(
    edges: Sequence[Mapping[str, Any]],
    *,
    affected_node: str,
) -> dict[str, Any]:
    """Breadth-first downstream dependency traversal over user-supplied directed edges."""
    source = _text(affected_node, "affected_node")
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        start = _text(edge.get("from"), "edge.from")
        end = _text(edge.get("to"), "edge.to")
        adjacency.setdefault(start, set()).add(end)
    visited, queue = {source}, [source]
    order = []
    while queue:
        current = queue.pop(0)
        for nxt in sorted(adjacency.get(current, ())):
            if nxt not in visited:
                visited.add(nxt)
                order.append(nxt)
                queue.append(nxt)
    return {"source": source, "affected_nodes": order, "node_count": len(order), "causality_verified": False}


def forecast_resource_quality(
    observations: Sequence[Mapping[str, Any]],
    *,
    minimum_samples: int = 20,
) -> dict[str, Any]:
    """Exploratory linear-trend forecast with chronological holdout and uncertainty band."""
    if len(observations) < minimum_samples:
        return {
            "status": "INSUFFICIENT_DATA",
            "sample_count": len(observations),
            "minimum_samples": minimum_samples,
            "forecast": None,
            "reason": "Insufficient historical observations for the configured minimum sample count.",
        }
    values = np.asarray([_number(row.get("value"), "observation.value") for row in observations], dtype=float)
    timestamps = [_utc_timestamp(row.get("timestamp"), "observation.timestamp") for row in observations]
    if any(value is None for value in timestamps):
        raise ResourceValidationError("Every quality observation requires a timezone-aware timestamp.")
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise ResourceValidationError("Quality observations must have unique, ascending timestamps.")
    split = max(int(len(values) * 0.8), 10)
    parsed_times = [datetime.fromisoformat(value) for value in timestamps]
    start_time = parsed_times[0]
    x = np.asarray([(value - start_time).total_seconds() / 86400.0 for value in parsed_times], dtype=float)
    intervals = np.diff(x)
    if np.any(intervals <= 0):
        raise ResourceValidationError("Quality timestamps must advance in time.")
    coefficients = np.polyfit(x[:split], values[:split], 1)
    holdout_prediction = np.polyval(coefficients, x[split:])
    holdout_error = values[split:] - holdout_prediction
    mae = float(np.mean(np.abs(holdout_error)))
    fitted = np.polyval(coefficients, x[:split])
    residual_std = float(np.std(values[:split] - fitted, ddof=2)) if split > 2 else 0.0
    forecast_step_days = float(np.median(intervals))
    next_value = float(np.polyval(coefficients, x[-1] + forecast_step_days))
    band = 1.96 * residual_std
    return {
        "status": "EXPLORATORY_FORECAST_NOT_VALIDATED",
        "sample_count": len(values),
        "holdout_sample_count": len(holdout_error),
        "holdout_mae": mae,
        "forecast": next_value,
        "prediction_interval_approx_95": [next_value - band, next_value + band],
        "model": "Ordinary least-squares linear trend; one-step extrapolation.",
        "warnings": [
            "This is not a validated plant-quality model or a guarantee.",
            "The interval is an approximate residual band, not a calibrated prediction interval.",
            "Seasonality, process variables, outliers and model drift are not represented.",
        ],
    }


def calculate_supply_reliability(
    delivery_history: Sequence[Mapping[str, Any]],
    *,
    minimum_periods: int = 20,
) -> dict[str, Any]:
    """Report historical in-full-and-quality pass rate; does not forecast future reliability."""
    if len(delivery_history) < minimum_periods:
        return {
            "status": "INSUFFICIENT_DATA",
            "sample_count": len(delivery_history),
            "minimum_periods": minimum_periods,
            "historical_pass_rate": None,
        }
    passes = 0
    for index, row in enumerate(delivery_history):
        delivered = _number(row.get("delivered_quantity"), f"history[{index}].delivered_quantity", minimum=0)
        required = _number(row.get("required_quantity"), f"history[{index}].required_quantity", minimum=0)
        if required <= 0:
            raise ResourceValidationError("Historical required_quantity must be greater than zero.")
        if not isinstance(row.get("quality_pass"), bool):
            raise ResourceValidationError("Every history row requires an explicit quality_pass boolean.")
        passes += int(delivered >= required and row["quality_pass"])
    rate = passes / len(delivery_history)
    return {
        "status": "HISTORICAL_EMPIRICAL_RATE_NOT_FORECAST",
        "sample_count": len(delivery_history),
        "successful_periods": passes,
        "historical_pass_rate": rate,
        "standard_error": (rate * (1.0 - rate) / len(delivery_history)) ** 0.5,
        "future_reliability_probability": None,
    }


def rank_resource_cascade(opportunities: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Order opportunities by the prevention-first resource hierarchy."""
    rank = {name: position for position, name in enumerate(CASCADE_ORDER)}
    normalized = []
    for item in opportunities:
        action = _text(item.get("action"), "opportunity.action").upper()
        if action not in rank:
            raise ResourceValidationError(f"Unsupported cascade action: {action}.")
        normalized.append({**dict(item), "action": action, "_cascade_rank": rank[action]})
    normalized.sort(key=lambda item: (item["_cascade_rank"], str(item.get("opportunity_id") or "")))
    for item in normalized:
        item.pop("_cascade_rank", None)
    return normalized


def detect_resource_bottleneck(
    required_quantity: float,
    *,
    unit: str,
    capacity_constraints: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Identify the tightest declared capacity constraint for a single resource."""
    required = _number(required_quantity, "required_quantity", minimum=0)
    if required <= 0:
        raise ResourceValidationError("required_quantity must be greater than zero.")
    unit_label = _text(unit, "unit")
    if not capacity_constraints:
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": "At least one measured or configured capacity constraint is required.",
            "bottleneck": None,
        }
    normalized = []
    for index, item in enumerate(capacity_constraints):
        name = _text(item.get("constraint"), f"capacity_constraints[{index}].constraint")
        constraint_unit = _text(item.get("unit"), f"capacity_constraints[{index}].unit")
        if constraint_unit.casefold() != unit_label.casefold():
            raise ResourceValidationError(
                f"Capacity constraint {name} uses {constraint_unit}; expected {unit_label}. No implicit conversion is performed."
            )
        capacity = _number(item.get("capacity"), f"capacity_constraints[{index}].capacity", minimum=0)
        normalized.append({"constraint": name, "capacity": capacity, "unit": constraint_unit})
    limiting = min(normalized, key=lambda item: (item["capacity"], item["constraint"].casefold()))
    shortfall = max(0.0, required - limiting["capacity"])
    return {
        "status": "BOTTLENECK" if shortfall > 1e-9 else "NO_CAPACITY_SHORTFALL",
        "required_quantity": required,
        "unit": unit_label,
        "limiting_constraint": limiting,
        "shortfall_quantity": shortfall,
        "all_constraints": normalized,
        "interpretation": (
            "The limiting entered capacity is below the required quantity."
            if shortfall > 1e-9 else
            "All entered capacities meet the required quantity; unentered constraints remain unknown."
        ),
    }


def assess_infrastructure_route(route: Mapping[str, Any]) -> dict[str, Any]:
    """Screen an explicitly declared route; never infers a connection from proximity."""
    if not isinstance(route, Mapping):
        raise ResourceValidationError("Infrastructure route must be an object.")
    connection = route.get("connection_confirmed")
    if connection is False:
        return {
            "status": "BLOCKED_NO_CONFIRMED_CONNECTION",
            "reason": "The user indicates that a usable physical connection is unavailable.",
            "operational_authorization": False,
        }
    if connection is not True:
        return {
            "status": "INSUFFICIENT_DATA",
            "reason": "A physical connection must be explicitly confirmed with supporting evidence.",
            "operational_authorization": False,
        }
    distance = _number(route.get("distance_km"), "distance_km", minimum=0)
    capacity = _number(route.get("capacity"), "capacity", minimum=0)
    required = _number(route.get("required_quantity"), "required_quantity", minimum=0)
    unit = _text(route.get("unit"), "unit")
    capacity_unit = _text(route.get("capacity_unit") or unit, "capacity_unit")
    if unit.casefold() != capacity_unit.casefold():
        raise ResourceValidationError("Route capacity and required quantity must use the same unit.")
    if required <= 0:
        raise ResourceValidationError("required_quantity must be greater than zero.")
    if capacity < required:
        return {
            "status": "INFEASIBLE_CAPACITY",
            "distance_km": distance,
            "capacity": capacity,
            "required_quantity": required,
            "unit": unit,
            "operational_authorization": False,
        }
    missing = [
        label for label, value in (
            ("route_access_evidence", route.get("route_access_evidence")),
            ("permit_reference", route.get("permit_reference")),
            ("engineering_review_reference", route.get("engineering_review_reference")),
        ) if not str(value or "").strip()
    ]
    return {
        "status": "APPROVAL_PENDING" if missing else "PRELIMINARY_FEASIBILITY_ONLY",
        "distance_km": distance,
        "capacity": capacity,
        "required_quantity": required,
        "unit": unit,
        "transport_mode": str(route.get("transport_mode") or "").strip(),
        "missing_evidence": missing,
        "connection_confirmation_is_user_asserted": True,
        "independent_verification": "NOT_PERFORMED",
        "operational_authorization": False,
        "note": "This is a preliminary user-entered route screen, not a survey, hydraulic design, permit or construction approval.",
    }


def calculate_resource_intensity_change(
    baseline_usage: float,
    baseline_production: float,
    reporting_usage: float,
    reporting_production: float,
    *,
    usage_unit: str,
    production_unit: str,
) -> dict[str, Any]:
    """Compare usage intensity across periods without self-certifying savings."""
    base_usage = _number(baseline_usage, "baseline_usage", minimum=0)
    base_output = _number(baseline_production, "baseline_production", minimum=0)
    current_usage = _number(reporting_usage, "reporting_usage", minimum=0)
    current_output = _number(reporting_production, "reporting_production", minimum=0)
    if base_output <= 0 or current_output <= 0:
        raise ResourceValidationError("Both production quantities must be greater than zero.")
    if base_usage <= 0:
        raise ResourceValidationError("baseline_usage must be greater than zero for a comparable intensity.")
    usage_label = _text(usage_unit, "usage_unit")
    output_label = _text(production_unit, "production_unit")
    baseline_intensity = base_usage / base_output
    reporting_intensity = current_usage / current_output
    change_percent = 100.0 * (reporting_intensity - baseline_intensity) / baseline_intensity
    return {
        "status": (
            "LOWER_REPORTED_INTENSITY" if change_percent < 0 else
            "HIGHER_REPORTED_INTENSITY" if change_percent > 0 else
            "UNCHANGED_REPORTED_INTENSITY"
        ),
        "baseline_intensity": baseline_intensity,
        "reporting_intensity": reporting_intensity,
        "intensity_unit": f"{usage_label} per {output_label}",
        "change_percent": change_percent,
        "evidence_status": "COMPARISON_ONLY_NOT_INDEPENDENTLY_VERIFIED",
        "note": "Production-normalized intensity comparison only; operating conditions, quality, boundaries and causal attribution are not verified.",
    }


def validate_import_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate imported passport records while preserving input rows unchanged."""
    accepted, rejected = [], []
    for index, row in enumerate(rows):
        try:
            accepted.append(validate_resource_passport(row))
        except (ResourceValidationError, TypeError) as exc:
            rejected.append({"row_number": index + 1, "reason": str(exc), "source_row": dict(row)})
    return {
        "status": "VALID" if not rejected else ("INVALID" if not accepted else "PARTIALLY_VALID"),
        "accepted": accepted,
        "rejected": rejected,
        "source_rows_modified": False,
    }


__all__ = [
    "PROVENANCE_VALUES", "COMPATIBILITY_STATUSES", "CASCADE_ORDER",
    "ResourceValidationError", "validate_resource_passport",
    "assess_resource_compatibility", "calculate_resource_balance",
    "detect_resource_loss", "optimize_resource_network",
    "simulate_supplier_disruption", "evaluate_safety_gate",
    "calculate_exchange_value", "propagate_network_impact",
    "forecast_resource_quality", "calculate_supply_reliability",
    "rank_resource_cascade", "detect_resource_bottleneck",
    "assess_infrastructure_route", "calculate_resource_intensity_change",
    "validate_import_rows",
]
