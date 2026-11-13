"""Industrial Resource Intelligence: deterministic engineering foundation.

This module deliberately contains no live plant connector, supplier marketplace,
regulatory certification, or AI-authoritative decision. Inputs are caller supplied
and must retain their declared provenance. The calculations are deterministic and
return explicit incomplete/infeasible states rather than inventing data.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from math import isfinite
from typing import Any, Mapping, Sequence
from uuid import uuid4

import numpy as np
from scipy.optimize import linprog

PROVENANCE_VALUES = ("LIVE", "IMPORTED", "MANUAL", "SYNTHETIC", "SIMULATED", "MOCK", "STALE")
USER_INPUT_PROVENANCE_VALUES = ("IMPORTED", "MANUAL", "SYNTHETIC", "SIMULATED", "MOCK", "STALE")
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
    missing_type = value.__class__.__name__ if value is not None else ""
    if value is None or missing_type in {"NAType", "NaTType"}:
        result = ""
    elif isinstance(value, (float, np.floating)) and not isfinite(float(value)):
        result = ""
    else:
        result = str(value).strip()
    if not result:
        raise ResourceValidationError(f"{field} is required.")
    if len(result) > 240:
        raise ResourceValidationError(f"{field} must be 240 characters or fewer.")
    if any(ord(char) < 32 for char in result):
        raise ResourceValidationError(f"{field} contains unsupported control characters.")
    return result


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if value.__class__.__name__ in {"NAType", "NaTType"}:
        return True
    return isinstance(value, (float, np.floating)) and bool(np.isnan(value))


def _optional_text(value: Any) -> str:
    return "" if _is_missing(value) else str(value).strip()


def _number(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise ResourceValidationError(f"{field} must be a numeric measurement, not a boolean.")
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
    if _is_missing(value) or value == "":
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
    if provenance == "LIVE":
        raise ResourceValidationError("LIVE provenance is reserved for a separately verified connector. Manual and imported records cannot claim LIVE.")
    quantity = _number(payload.get("available_quantity"), "available_quantity", minimum=0)
    if quantity <= 0:
        raise ResourceValidationError("available_quantity must be greater than zero.")
    quality_value = payload.get("quality")
    if _is_missing(quality_value):
        quality = {}
    elif not isinstance(quality_value, Mapping):
        raise ResourceValidationError("quality must be an object of numeric property measurements.")
    else:
        quality = quality_value
    certificate_valid_until = _optional_text(payload.get("certificate_valid_until"))
    if certificate_valid_until:
        try:
            certificate_valid_until = date.fromisoformat(certificate_valid_until).isoformat()
        except ValueError as exc:
            raise ResourceValidationError("certificate_valid_until must be a valid YYYY-MM-DD date.") from exc
    approval_status = (_optional_text(payload.get("approval_status")) or "DRAFT").upper()
    if approval_status not in {"DRAFT", "PENDING", "APPROVED", "REJECTED"}:
        raise ResourceValidationError("approval_status must be DRAFT, PENDING, APPROVED or REJECTED.")
    normalized_quality = {
        _text(key, "quality property"): _number(value, f"quality.{key}")
        for key, value in quality.items()
    }
    return {
        "resource_id": _optional_text(payload.get("resource_id")) or str(uuid4()),
        "facility_id": _text(payload.get("facility_id"), "facility_id"),
        "name": _text(payload.get("name"), "name"),
        "resource_type": _text(payload.get("resource_type"), "resource_type"),
        "category": (_optional_text(payload.get("category")) or "OTHER").upper(),
        "available_quantity": quantity,
        "unit": _text(payload.get("unit"), "unit"),
        "quality": normalized_quality,
        "temperature_c": (
            _number(payload["temperature_c"], "temperature_c")
            if not _is_missing(payload.get("temperature_c")) and payload.get("temperature_c") != "" else None
        ),
        "pressure_kpa": (
            _number(payload["pressure_kpa"], "pressure_kpa", minimum=0)
            if not _is_missing(payload.get("pressure_kpa")) and payload.get("pressure_kpa") != "" else None
        ),
        "owner": _optional_text(payload.get("owner")),
        "description_en": _optional_text(payload.get("description_en")),
        "description_ar": _optional_text(payload.get("description_ar")),
        "source_process": _optional_text(payload.get("source_process")),
        "source_equipment": _optional_text(payload.get("source_equipment")),
        "availability_window": _optional_text(payload.get("availability_window")),
        "seasonal_variation": _optional_text(payload.get("seasonal_variation")),
        "storage_requirements": _optional_text(payload.get("storage_requirements")),
        "transport_requirements": _optional_text(payload.get("transport_requirements")),
        "treatment_notes": _optional_text(payload.get("treatment_notes")),
        "safety_restrictions": _optional_text(payload.get("safety_restrictions")),
        "source_reference": _optional_text(payload.get("source_reference")),
        "laboratory_evidence_reference": _optional_text(payload.get("laboratory_evidence_reference")),
        "certificate_reference": _optional_text(payload.get("certificate_reference")),
        "certificate_valid_until": certificate_valid_until,
        "measured_at": _utc_timestamp(payload.get("measured_at"), "measured_at"),
        "provenance": provenance,
        "created_at": _optional_text(payload.get("created_at")) or datetime.now(timezone.utc).isoformat(),
        "approval_status": approval_status,
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


def append_resource_passport_revision(
    history: Sequence[Mapping[str, Any]],
    passport: Mapping[str, Any],
    *,
    actor: str,
) -> list[dict[str, Any]]:
    """Append a hash-checkable resource passport revision to workspace history.

    This is an integrity-check helper, not an immutable ledger: workspace owners
    can edit/delete their saved workspace, and no external timestamp authority
    or independent custodian is involved.
    """
    if not isinstance(passport, Mapping):
        raise ResourceValidationError("Passport revision must be an object.")
    resource_id = _text(passport.get("resource_id"), "passport.resource_id")
    actor_name = _text(actor, "actor")
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes, bytearray)):
        raise ResourceValidationError("Passport history must be a sequence.")
    prior = [
        dict(item) for item in history
        if isinstance(item, Mapping) and str(item.get("resource_id") or "") == resource_id
    ]
    try:
        prior.sort(key=lambda item: int(item.get("revision_no", 0)))
    except (TypeError, ValueError) as exc:
        raise ResourceValidationError("Existing passport revision history has an invalid revision number.") from exc
    if prior and verify_resource_passport_history(prior)["status"] != "VALID_HASH_CHAINS":
        raise ResourceValidationError("Existing passport revision history failed its integrity check; refusing to append.")
    revision_no = len(prior) + 1
    previous_hash = prior[-1].get("revision_sha256") if prior else None
    snapshot = dict(passport)
    canonical_snapshot = json.dumps(
        snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    content_hash = hashlib.sha256(canonical_snapshot.encode("utf-8")).hexdigest()
    event = {
        "resource_id": resource_id,
        "revision_no": revision_no,
        "previous_revision_sha256": previous_hash,
        "content_sha256": content_hash,
        "recorded_by": actor_name,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "passport_snapshot": snapshot,
    }
    canonical_event = json.dumps(
        event, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    event["revision_sha256"] = hashlib.sha256(canonical_event.encode("utf-8")).hexdigest()
    result = [dict(item) for item in history]
    result.append(event)
    return result


def verify_resource_passport_history(
    history: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Recompute per-resource revision hashes and continuity from saved workspace rows."""
    if not isinstance(history, Sequence) or isinstance(history, (str, bytes, bytearray)):
        raise ResourceValidationError("Passport history must be a sequence.")
    grouped: dict[str, list[dict[str, Any]]] = {}
    malformed = []
    for index, item in enumerate(history):
        if not isinstance(item, Mapping):
            malformed.append(f"History item {index + 1} is not an object.")
            continue
        resource_id = str(item.get("resource_id") or "").strip()
        if not resource_id:
            malformed.append(f"History item {index + 1} has no resource_id.")
            continue
        grouped.setdefault(resource_id, []).append(dict(item))

    reports = []
    for resource_id, revisions in grouped.items():
        issues = []
        def _revision_sort_key(item: Mapping[str, Any]) -> tuple[int, str]:
            try:
                revision_value = int(item.get("revision_no", 0))
            except (TypeError, ValueError):
                revision_value = 2**31 - 1
            return revision_value, str(item.get("recorded_at") or "")
        revisions.sort(key=_revision_sort_key)
        expected_parent = None
        for expected_revision_no, event in enumerate(revisions, start=1):
            try:
                actual_revision_no = int(event.get("revision_no"))
            except (TypeError, ValueError):
                actual_revision_no = None
            if actual_revision_no != expected_revision_no:
                issues.append(f"Expected revision {expected_revision_no}, found {event.get('revision_no')}.")
            if event.get("previous_revision_sha256") != expected_parent:
                issues.append(f"Revision {expected_revision_no} parent hash does not match.")
            snapshot = event.get("passport_snapshot")
            if not isinstance(snapshot, Mapping):
                issues.append(f"Revision {expected_revision_no} has no passport snapshot.")
                expected_parent = event.get("revision_sha256")
                continue
            if str(snapshot.get("resource_id") or "") != resource_id:
                issues.append(f"Revision {expected_revision_no} snapshot resource_id does not match its event.")
            canonical_snapshot = json.dumps(
                dict(snapshot), sort_keys=True, ensure_ascii=False,
                separators=(",", ":"), default=str
            )
            content_hash = hashlib.sha256(canonical_snapshot.encode("utf-8")).hexdigest()
            if content_hash != event.get("content_sha256"):
                issues.append(f"Revision {expected_revision_no} content hash does not match.")
            event_without_hash = {
                key: value for key, value in event.items() if key != "revision_sha256"
            }
            canonical_event = json.dumps(
                event_without_hash, sort_keys=True, ensure_ascii=False,
                separators=(",", ":"), default=str
            )
            revision_hash = hashlib.sha256(canonical_event.encode("utf-8")).hexdigest()
            if revision_hash != event.get("revision_sha256"):
                issues.append(f"Revision {expected_revision_no} event hash does not match.")
            expected_parent = event.get("revision_sha256")
        reports.append({
            "resource_id": resource_id,
            "revision_count": len(revisions),
            "status": "VALID_HASH_CHAIN" if not issues else "INTEGRITY_CHECK_FAILED",
            "issues": issues,
        })
    invalid_resources = [row["resource_id"] for row in reports if row["status"] != "VALID_HASH_CHAIN"]
    overall = "VALID_HASH_CHAINS" if not malformed and not invalid_resources else "INTEGRITY_CHECK_FAILED"
    return {
        "status": overall,
        "resource_count": len(reports),
        "revision_count": len(history),
        "invalid_resource_ids": invalid_resources,
        "malformed_items": malformed,
        "resources": reports,
        "trust_boundary": "Hash integrity can be recomputed from the current workspace; this does not prevent an authorized editor from rewriting the complete history or establish an independent timestamp/custody authority.",
    }


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
    if provenance not in USER_INPUT_PROVENANCE_VALUES:
        raise ResourceValidationError("Evidence provenance must be imported, manual, synthetic, simulated, mock or stale. LIVE requires a verified connector.")
    result.update({
        "finding_type": (
            "SUSPECTED_RESOURCE_LOSS"
            if result["status"] == "ANOMALY_SUSPECTED" and result["unreconciled_quantity"] > 0
            else "UNRECONCILED_BALANCE"
            if result["status"] == "ANOMALY_SUSPECTED"
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
    shortage_penalty_per_unit: float | None = None,
) -> dict[str, Any]:
    """Solve a constrained transportation LP with independent qualification checks.

    Each demand must be fully satisfied unless allow_shortage=True. Supply limits,
    route capacities, resource type, units and quality constraints are enforced.
    """
    if not supplies or not demands:
        raise ResourceValidationError("At least one supply and one demand are required.")
    if not isinstance(allow_shortage, bool):
        raise ResourceValidationError("allow_shortage must be a boolean.")
    if allow_shortage:
        shortage_penalty_per_unit = _number(
            shortage_penalty_per_unit, "shortage_penalty_per_unit", minimum=0
        )
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
            + _number(raw.get("treatment_cost_per_unit"), "route.treatment_cost_per_unit", minimum=0)
            + _number(raw.get("transport_cost_per_unit"), "route.transport_cost_per_unit", minimum=0)
        )
        capacity = _number(raw.get("capacity"), "route.capacity", minimum=0)
        if capacity <= 0:
            continue
        edges.append({
            "supply_id": sid, "demand_id": did, "unit_cost": cost,
            "capacity": capacity, "compatibility": compatibility["status"],
        })

    if not edges:
        unmet_demand = [
            {"demand_id": d["demand_id"], "quantity": d["required_quantity"], "unit": d["unit"]}
            for d in demand_by_id.values()
        ]
        if allow_shortage:
            penalty = _number(shortage_penalty_per_unit, "shortage_penalty_per_unit", minimum=0)
            return {
                "status": "FEASIBLE_WITH_SHORTAGE",
                "reason": "No route passed engineering screening or no positive supply capacity remained; demand is recorded as unmet rather than inventing an allocation.",
                "solver": "CLOSED_FORM_NO_FEASIBLE_ROUTE",
                "allocations": [], "rejected_routes": rejected_routes,
                "objective_cost": penalty * sum(float(d["required_quantity"]) for d in demand_by_id.values()),
                "unmet_demand": unmet_demand,
                "assumptions": ["No eligible supply route was available.", "No resource was allocated.", "Shortage penalty is a configured scenario cost, not a measured financial loss."],
            }
        return {
            "status": "INFEASIBLE",
            "reason": "No route passed the independent type, unit and quality screening gate.",
            "allocations": [], "rejected_routes": rejected_routes,
            "objective_cost": None, "unmet_demand": unmet_demand,
        }

    n_edges, n_demands = len(edges), len(demand_by_id)
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


def optimize_period_aligned_resource_network(
    supplies: Sequence[Mapping[str, Any]],
    demands: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
    *,
    allow_shortage: bool = False,
    shortage_penalty_per_unit: float | None = None,
) -> dict[str, Any]:
    """Optimize allocations inside explicit matching time buckets.

    No allocation crosses a period boundary. Inventory carryover, storage,
    production scheduling and maintenance calendars are not inferred; callers
    must represent each period's available supply and demand explicitly.
    """
    if not demands:
        raise ResourceValidationError("At least one time-bucketed demand is required.")
    if not supplies and not allow_shortage:
        raise ResourceValidationError("At least one time-bucketed supply is required unless shortage reporting is enabled.")
    if not isinstance(allow_shortage, bool):
        raise ResourceValidationError("allow_shortage must be a boolean.")
    if allow_shortage:
        shortage_penalty_per_unit = _number(
            shortage_penalty_per_unit, "shortage_penalty_per_unit", minimum=0
        )
    try:
        supply_rows = [dict(row) for row in supplies]
        demand_rows = [dict(row) for row in demands]
        route_rows = [dict(row) for row in routes]
    except (TypeError, ValueError) as exc:
        raise ResourceValidationError("Supplies, demands and routes must contain object records.") from exc
    for index, row in enumerate(supply_rows):
        row["period_id"] = _text(row.get("period_id"), f"supplies[{index}].period_id")
    for index, row in enumerate(demand_rows):
        row["period_id"] = _text(row.get("period_id"), f"demands[{index}].period_id")
    for index, row in enumerate(route_rows):
        row["period_id"] = _text(row.get("period_id"), f"routes[{index}].period_id")

    supply_periods = {row["period_id"] for row in supply_rows}
    demand_periods = {row["period_id"] for row in demand_rows}
    periods = sorted(demand_periods)
    unexpected_route_periods = sorted(
        {row["period_id"] for row in route_rows} - demand_periods
    )
    period_results = []
    all_allocations = []
    total_cost = 0.0
    total_unmet = 0.0
    for period_id in periods:
        period_demands = [
            {key: value for key, value in row.items() if key != "period_id"}
            for row in demand_rows if row["period_id"] == period_id
        ]
        period_supplies = [
            {key: value for key, value in row.items() if key != "period_id"}
            for row in supply_rows if row["period_id"] == period_id
        ]
        period_routes = [
            {key: value for key, value in row.items() if key != "period_id"}
            for row in route_rows if row["period_id"] == period_id
        ]
        if not period_supplies:
            rejected_for_period = [
                {
                    "supply_id": _optional_text(route.get("supply_id")),
                    "demand_id": _optional_text(route.get("demand_id")),
                    "status": "REJECTED_NO_SAME_PERIOD_SUPPLY",
                    "reason": "Route period has no declared same-period supply. Cross-period carryover is not modeled.",
                }
                for route in period_routes
            ]
            period_result = {
                "status": "FEASIBLE_WITH_SHORTAGE" if allow_shortage else "INFEASIBLE",
                "reason": "No supply was declared for this demand period; no carryover or external replenishment is assumed.",
                "allocations": [],
                "rejected_routes": rejected_for_period,
                "objective_cost": (
                    _number(shortage_penalty_per_unit, "shortage_penalty_per_unit", minimum=0)
                    * sum(_number(item.get("required_quantity"), "required_quantity", minimum=0) for item in period_demands)
                    if allow_shortage else None
                ),
                "unmet_demand": [
                    {"demand_id": _text(item.get("demand_id") or item.get("id"), "demand id"),
                     "quantity": _number(item.get("required_quantity"), "required_quantity", minimum=0),
                     "unit": _text(item.get("unit"), "demand.unit")}
                    for item in period_demands
                ],
            }
        else:
            period_result = optimize_resource_network(
                period_supplies,
                period_demands,
                period_routes,
                allow_shortage=allow_shortage,
                shortage_penalty_per_unit=shortage_penalty_per_unit,
            )
        period_result["period_id"] = period_id
        period_results.append(period_result)
        for allocation in period_result.get("allocations", []):
            all_allocations.append({**allocation, "period_id": period_id})
        if period_result.get("objective_cost") is not None:
            total_cost += float(period_result["objective_cost"])
        total_unmet += sum(float(item["quantity"]) for item in period_result.get("unmet_demand", []))

    unexpected_supply_periods = sorted(supply_periods - demand_periods)
    period_states = [item["status"] for item in period_results]
    if any(status in {"INFEASIBLE", "VALIDATION_FAILED"} for status in period_states):
        status = "INFEASIBLE" if "INFEASIBLE" in period_states else "VALIDATION_FAILED"
    elif any(status == "FEASIBLE_WITH_SHORTAGE" for status in period_states):
        status = "FEASIBLE_WITH_SHORTAGE"
    else:
        status = "OPTIMAL_BY_PERIOD"
    return {
        "status": status,
        "period_count": len(periods),
        "periods": period_results,
        "allocations": all_allocations,
        "objective_cost": total_cost if status in {"OPTIMAL_BY_PERIOD", "FEASIBLE_WITH_SHORTAGE"} else None,
        "unmet_demand_total": total_unmet,
        "unused_supply_periods": unexpected_supply_periods,
        "rejected_routes_outside_demand_periods": [
            {
                "period_id": route["period_id"],
                "supply_id": _optional_text(route.get("supply_id")),
                "demand_id": _optional_text(route.get("demand_id")),
                "status": "REJECTED_ROUTE_PERIOD_WITHOUT_DEMAND",
            }
            for route in route_rows if route["period_id"] in unexpected_route_periods
        ],
        "unexpected_route_periods": unexpected_route_periods,
        "period_alignment": "STRICT_NO_CROSS_PERIOD_ALLOCATION",
        "storage_or_carryover": "NOT_MODELED",
        "production_and_maintenance_schedules": "NOT_CONNECTED; caller must encode per-period availability and demand.",
        "limitations": [
            "No storage or inventory carryover between periods.",
            "No automatic production schedule, maintenance calendar or operating-hour interpretation.",
            "Every period is optimized independently; the model cannot transfer surplus across periods.",
        ],
    }


def simulate_resource_network_scenario(
    supplies: Sequence[Mapping[str, Any]],
    demands: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
    shocks: Sequence[Mapping[str, Any]],
    *,
    scenario_id: str,
    scenario_name: str,
    shortage_penalty_per_unit: float,
) -> dict[str, Any]:
    """Apply multiple explicit resource-network shocks and re-optimize.

    Supported shocks:
    SUPPLIER_SHUTDOWN, SUPPLY_REDUCTION, SUPPLY_QUALITY_OVERRIDE,
    DEMAND_MULTIPLIER, ROUTE_UNAVAILABLE, ROUTE_CAPACITY_MULTIPLIER,
    ROUTE_RESOURCE_COST_MULTIPLIER, ROUTE_TRANSPORT_COST_MULTIPLIER,
    ROUTE_TREATMENT_COST_MULTIPLIER.

    This is a deterministic one-period what-if solver, not a time-stepped
    discrete-event simulator or validated probability model.
    """
    scenario_key = _text(scenario_id, "scenario_id")
    scenario_label = _text(scenario_name, "scenario_name")
    if not supplies or not demands:
        raise ResourceValidationError("Scenario requires at least one supply and one demand record.")
    if not isinstance(shocks, Sequence) or isinstance(shocks, (str, bytes, bytearray)):
        raise ResourceValidationError("shocks must be a sequence of objects.")
    changed_supplies = [dict(item) for item in supplies]
    changed_demands = [dict(item) for item in demands]
    changed_routes = [dict(item) for item in routes]
    applied = []
    supported = {
        "SUPPLIER_SHUTDOWN",
        "SUPPLY_REDUCTION",
        "SUPPLY_QUALITY_OVERRIDE",
        "DEMAND_MULTIPLIER",
        "ROUTE_UNAVAILABLE",
        "ROUTE_CAPACITY_MULTIPLIER",
        "ROUTE_RESOURCE_COST_MULTIPLIER",
        "ROUTE_TRANSPORT_COST_MULTIPLIER",
        "ROUTE_TREATMENT_COST_MULTIPLIER",
    }

    def _find_supply(target: str) -> dict[str, Any]:
        matches = [
            item for item in changed_supplies
            if str(item.get("resource_id") or item.get("id") or "") == target
        ]
        if len(matches) != 1:
            raise ResourceValidationError(f"Supply target {target} must match exactly one supply record.")
        return matches[0]

    def _find_demand(target: str) -> dict[str, Any]:
        matches = [
            item for item in changed_demands
            if str(item.get("demand_id") or item.get("id") or "") == target
        ]
        if len(matches) != 1:
            raise ResourceValidationError(f"Demand target {target} must match exactly one demand record.")
        return matches[0]

    def _find_route(shock: Mapping[str, Any]) -> dict[str, Any]:
        route_id = _optional_text(shock.get("route_id"))
        if route_id:
            matches = [item for item in changed_routes if str(item.get("route_id") or "") == route_id]
        else:
            supply_id = _text(shock.get("supply_id"), "shock.supply_id")
            demand_id = _text(shock.get("demand_id"), "shock.demand_id")
            matches = [
                item for item in changed_routes
                if str(item.get("supply_id") or "") == supply_id
                and str(item.get("demand_id") or "") == demand_id
            ]
        if len(matches) != 1:
            raise ResourceValidationError("Route shock must match exactly one declared route.")
        return matches[0]

    for index, raw in enumerate(shocks):
        if not isinstance(raw, Mapping):
            raise ResourceValidationError(f"Shock {index + 1} must be an object.")
        kind = _text(raw.get("type"), f"shocks[{index}].type").upper()
        if kind not in supported:
            raise ResourceValidationError(f"Unsupported resource-network shock type: {kind}.")
        if kind == "SUPPLIER_SHUTDOWN":
            target = _text(raw.get("supply_id"), "shock.supply_id")
            item = _find_supply(target)
            item["available_quantity"] = 0.0
            applied.append({"type": kind, "supply_id": target})
        elif kind == "SUPPLY_REDUCTION":
            target = _text(raw.get("supply_id"), "shock.supply_id")
            fraction = _number(raw.get("fraction"), "shock.fraction", minimum=0)
            if fraction > 1:
                raise ResourceValidationError("Supply reduction fraction must not exceed 1.")
            item = _find_supply(target)
            original = _number(item.get("available_quantity"), "supply.available_quantity", minimum=0)
            item["available_quantity"] = original * (1.0 - fraction)
            applied.append({"type": kind, "supply_id": target, "fraction": fraction})
        elif kind == "SUPPLY_QUALITY_OVERRIDE":
            target = _text(raw.get("supply_id"), "shock.supply_id")
            quality = raw.get("quality")
            if not isinstance(quality, Mapping) or not quality:
                raise ResourceValidationError("Supply quality override requires a non-empty quality object.")
            item = _find_supply(target)
            item["quality"] = dict(quality)
            applied.append({"type": kind, "supply_id": target, "quality_override": dict(quality)})
        elif kind == "DEMAND_MULTIPLIER":
            target = _text(raw.get("demand_id"), "shock.demand_id")
            multiplier = _number(raw.get("multiplier"), "shock.multiplier", minimum=0)
            if multiplier <= 0:
                raise ResourceValidationError("Demand multiplier must be greater than zero.")
            item = _find_demand(target)
            original = _number(item.get("required_quantity"), "demand.required_quantity", minimum=0)
            if original <= 0:
                raise ResourceValidationError("Demand required_quantity must be greater than zero.")
            item["required_quantity"] = original * multiplier
            applied.append({"type": kind, "demand_id": target, "multiplier": multiplier})
        else:
            route = _find_route(raw)
            if kind == "ROUTE_UNAVAILABLE":
                changed_routes.remove(route)
                applied.append({
                    "type": kind,
                    "supply_id": _optional_text(route.get("supply_id")),
                    "demand_id": _optional_text(route.get("demand_id")),
                })
            else:
                field, label = {
                    "ROUTE_CAPACITY_MULTIPLIER": ("capacity", "capacity"),
                    "ROUTE_RESOURCE_COST_MULTIPLIER": ("unit_cost", "unit_cost"),
                    "ROUTE_TRANSPORT_COST_MULTIPLIER": ("transport_cost_per_unit", "transport_cost_per_unit"),
                    "ROUTE_TREATMENT_COST_MULTIPLIER": ("treatment_cost_per_unit", "treatment_cost_per_unit"),
                }[kind]
                multiplier = _number(raw.get("multiplier"), "shock.multiplier", minimum=0)
                original = _number(route.get(field), f"route.{label}", minimum=0)
                route[field] = original * multiplier
                applied.append({
                    "type": kind,
                    "supply_id": _optional_text(route.get("supply_id")),
                    "demand_id": _optional_text(route.get("demand_id")),
                    "multiplier": multiplier,
                })

    baseline_result = optimize_resource_network(
        supplies, demands, routes,
        allow_shortage=True,
        shortage_penalty_per_unit=shortage_penalty_per_unit,
    )
    stressed_result = optimize_resource_network(
        changed_supplies, changed_demands, changed_routes,
        allow_shortage=True,
        shortage_penalty_per_unit=shortage_penalty_per_unit,
    )
    baseline_unmet = sum(float(item["quantity"]) for item in baseline_result.get("unmet_demand", []))
    stressed_unmet = sum(float(item["quantity"]) for item in stressed_result.get("unmet_demand", []))
    baseline_cost = baseline_result.get("objective_cost")
    stressed_cost = stressed_result.get("objective_cost")
    return {
        "scenario_id": scenario_key,
        "scenario_name": scenario_label,
        "status": stressed_result["status"],
        "shocks_applied": applied,
        "baseline": baseline_result,
        "stressed": stressed_result,
        "baseline_unmet_quantity": baseline_unmet,
        "stressed_unmet_quantity": stressed_unmet,
        "change_in_unmet_quantity": stressed_unmet - baseline_unmet,
        "baseline_objective_cost": baseline_cost,
        "stressed_objective_cost": stressed_cost,
        "change_in_objective_cost": (
            float(stressed_cost) - float(baseline_cost)
            if stressed_cost is not None and baseline_cost is not None else None
        ),
        "recovery_time": None,
        "recovery_time_note": "Not estimated: no validated restoration-time distribution or recovery plan was supplied.",
        "probability": None,
        "probability_note": "No probability is estimated. The shocks are deterministic user-defined scenarios.",
        "limitations": [
            "One-period deterministic resource allocation only.",
            "No maintenance calendar, storage depletion, production rescheduling or time-stepped outage duration is modeled.",
            "No supplier, price or disruption probability is inferred.",
            "A shortage penalty is a scenario input, not a measured financial loss.",
        ],
    }


def simulate_supplier_disruption(
    supplies: Sequence[Mapping[str, Any]],
    demands: Sequence[Mapping[str, Any]],
    routes: Sequence[Mapping[str, Any]],
    *,
    supplier_id: str,
    supply_reduction_fraction: float,
    shortage_penalty_per_unit: float,
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
    result = optimize_resource_network(
        changed, demands, routes, allow_shortage=True,
        shortage_penalty_per_unit=shortage_penalty_per_unit,
    )
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
    if not isinstance(critical_failure, bool):
        raise ResourceValidationError("critical_failure must be a boolean.")
    if not isinstance(laboratory_required, bool):
        raise ResourceValidationError("laboratory_required must be a boolean.")
    if laboratory_passed is not None and not isinstance(laboratory_passed, bool):
        raise ResourceValidationError("laboratory_passed must be a boolean or None.")
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


def assess_resource_substitution(
    candidate_resource: Mapping[str, Any],
    buyer_requirement: Mapping[str, Any],
    *,
    product_quality_status: str = "NOT_ASSESSED",
    equipment_compatibility_status: str = "NOT_ASSESSED",
    laboratory_evidence_reference: str = "",
    engineering_review_reference: str = "",
    safety_review_reference: str = "",
    environmental_review_reference: str = "",
) -> dict[str, Any]:
    """Screen a substitute candidate without authorizing process substitution."""
    compatibility = assess_resource_compatibility(candidate_resource, buyer_requirement)
    allowed = {"NOT_ASSESSED", "TEST_REQUIRED", "PASS", "FAIL"}
    product_status = _text(product_quality_status, "product_quality_status").upper()
    equipment_status = _text(equipment_compatibility_status, "equipment_compatibility_status").upper()
    if product_status not in allowed or equipment_status not in allowed:
        raise ResourceValidationError("Substitution test status must be NOT_ASSESSED, TEST_REQUIRED, PASS or FAIL.")
    references = {
        "laboratory": _optional_text(laboratory_evidence_reference),
        "engineering": _optional_text(engineering_review_reference),
        "safety": _optional_text(safety_review_reference),
        "environmental": _optional_text(environmental_review_reference),
    }
    blockers = []
    if compatibility["status"] == "TECHNICALLY_INCOMPATIBLE":
        blockers.append("Resource type, unit or entered quality is incompatible.")
    elif compatibility["status"] == "INSUFFICIENT_DATA":
        blockers.append("Essential compatibility measurements or operating limits are missing.")
    elif compatibility["status"] != "TECHNICALLY_COMPATIBLE":
        blockers.append("Base resource compatibility remains conditional or requires further review.")
    for label, status in (
        ("product quality", product_status),
        ("equipment compatibility", equipment_status),
    ):
        if status == "FAIL":
            blockers.append(f"{label.title()} check failed.")
        elif status in {"NOT_ASSESSED", "TEST_REQUIRED"}:
            blockers.append(f"{label.title()} check is not qualified.")
    for key in ("laboratory", "engineering", "safety", "environmental"):
        if not references[key]:
            blockers.append(f"{key.title()} evidence reference is missing.")
    if compatibility["status"] == "TECHNICALLY_INCOMPATIBLE" or "FAIL" in {product_status, equipment_status}:
        status = "REJECTED"
    elif compatibility["status"] == "INSUFFICIENT_DATA":
        status = "INSUFFICIENT_DATA"
    elif blockers:
        status = "CANDIDATE_REQUIRES_QUALIFICATION"
    else:
        status = "QUALIFICATION_REFERENCES_RECORDED_PENDING_INDEPENDENT_REVIEW"
    return {
        "status": status,
        "candidate_resource_id": _optional_text(candidate_resource.get("resource_id")),
        "candidate_resource_name": _optional_text(candidate_resource.get("name")),
        "compatibility": compatibility,
        "product_quality_status": product_status,
        "equipment_compatibility_status": equipment_status,
        "evidence_references": references,
        "blockers": blockers,
        "independent_verification": "NOT_PERFORMED",
        "operational_authorization": False,
        "substitution_authorized": False,
        "note": "A substitute candidate is not approved for production use. Product quality, equipment, laboratory, engineering, safety and environmental qualification remain the responsibility of authorized reviewers.",
    }


def rank_resource_improvement_projects(
    projects: Sequence[Mapping[str, Any]],
    *,
    weights: Mapping[str, Any],
) -> dict[str, Any]:
    """Rank projects using explicit 1–5 engineering scores and transparent weights."""
    score_dimensions = (
        "feasibility", "resource_impact", "reliability", "data_confidence",
        "risk", "implementation_difficulty",
    )
    if not projects:
        return {"status": "INSUFFICIENT_DATA", "ranked_projects": [], "reason": "No project records were supplied."}
    if not isinstance(weights, Mapping):
        raise ResourceValidationError("Project scoring weights must be an object.")
    unknown_weights = sorted(set(weights) - set(score_dimensions))
    if unknown_weights:
        raise ResourceValidationError(f"Unknown project scoring weight(s): {', '.join(str(x) for x in unknown_weights)}.")
    normalized_weights = {
        key: _number(weights.get(key), f"weights.{key}", minimum=0)
        for key in score_dimensions
    }
    weight_total = sum(normalized_weights.values())
    if weight_total <= 0:
        raise ResourceValidationError("At least one project scoring weight must be positive.")
    normalized_weights = {key: value / weight_total for key, value in normalized_weights.items()}
    ranked = []
    seen_ids: set[str] = set()
    for index, project in enumerate(projects):
        if not isinstance(project, Mapping):
            raise ResourceValidationError(f"Project {index + 1} must be an object.")
        project_id = _text(project.get("project_id"), f"projects[{index}].project_id")
        if project_id in seen_ids:
            raise ResourceValidationError(f"Duplicate project_id: {project_id}.")
        seen_ids.add(project_id)
        name = _text(project.get("name"), f"projects[{index}].name")
        scores = {
            key: _number(project.get(f"{key}_score"), f"projects[{index}].{key}_score", minimum=1)
            for key in score_dimensions
        }
        for key, value in scores.items():
            if value > 5:
                raise ResourceValidationError(f"projects[{index}].{key}_score must not exceed 5.")
        capex = _number(project.get("capex"), f"projects[{index}].capex", minimum=0)
        annual_gross_benefit = _number(
            project.get("annual_gross_benefit"),
            f"projects[{index}].annual_gross_benefit",
            minimum=0,
        )
        annual_opex = _number(project.get("annual_opex"), f"projects[{index}].annual_opex", minimum=0)
        annual_net_benefit = annual_gross_benefit - annual_opex
        payback = capex / annual_net_benefit if annual_net_benefit > 0 else None
        currency = _text(project.get("currency"), f"projects[{index}].currency").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ResourceValidationError(f"projects[{index}].currency must be a three-letter currency code.")
        safety_status = _text(project.get("safety_status"), f"projects[{index}].safety_status").upper()
        if safety_status not in {"REJECTED", "APPROVAL_PENDING", "APPROVAL_EVIDENCE_RECORDED"}:
            raise ResourceValidationError(f"projects[{index}].safety_status is not a recognized safety gate status.")
        if safety_status == "REJECTED":
            lifecycle = "BLOCKED_SAFETY"
        elif safety_status == "APPROVAL_EVIDENCE_RECORDED":
            lifecycle = "APPROVAL_REFERENCES_RECORDED_NOT_INDEPENDENTLY_VERIFIED"
        else:
            lifecycle = "APPROVAL_PENDING"
        normalized_score = (
            normalized_weights["feasibility"] * scores["feasibility"]
            + normalized_weights["resource_impact"] * scores["resource_impact"]
            + normalized_weights["reliability"] * scores["reliability"]
            + normalized_weights["data_confidence"] * scores["data_confidence"]
            + normalized_weights["risk"] * (6 - scores["risk"])
            + normalized_weights["implementation_difficulty"] * (6 - scores["implementation_difficulty"])
        ) * 20.0
        ranked.append({
            "project_id": project_id,
            "name": name,
            "scores": scores,
            "priority_score_0_100": normalized_score,
            "capex": capex,
            "annual_gross_benefit": annual_gross_benefit,
            "annual_opex": annual_opex,
            "annual_net_benefit": annual_net_benefit,
            "simple_payback_years": payback,
            "currency": currency,
            "safety_status": safety_status,
            "project_status": lifecycle,
            "evidence_reference": _optional_text(project.get("evidence_reference")),
            "priority_is_financial_roi": False,
        })
    ranked.sort(key=lambda item: (
        item["project_status"] == "BLOCKED_SAFETY",
        -item["priority_score_0_100"],
        item["project_id"],
    ))
    for index, item in enumerate(ranked, start=1):
        item["priority_rank"] = index
    return {
        "status": "RANKED_WITH_SAFETY_BLOCKS" if any(x["project_status"] == "BLOCKED_SAFETY" for x in ranked) else "RANKED",
        "ranked_projects": ranked,
        "weights": normalized_weights,
        "scoring_method": "Weighted 1–5 engineering rubric normalized to 0–100; higher risk and implementation difficulty reduce score.",
        "limitations": [
            "Priority score is not ROI, NPV, IRR or a recommendation to approve investment.",
            "Payback is a simple arithmetic ratio using entered annual gross benefit less entered annual operating cost; it excludes tax, discounting, ramp-up and uncertainty.",
            "Safety-rejected projects are flagged and must not proceed regardless of ranking.",
            "Entered score evidence and approval references have not been independently verified.",
        ],
    }


def calculate_environmental_impact(
    *,
    reporting_period: str,
    facility_boundary: str,
    geography: str,
    avoided_freshwater_m3: float,
    avoided_wastewater_m3: float,
    avoided_electricity_kwh: float,
    avoided_fuel_kwh: float,
    diverted_waste_kg: float,
    added_treatment_electricity_kwh: float,
    added_transport_tonne_km: float,
    added_chemical_kg: float,
    added_residual_waste_kg: float,
    factors: Mapping[str, Any],
    evidence_status: str = "ESTIMATED",
) -> dict[str, Any]:
    """Calculate bounded, factor-based indicative CO2e effects and physical outcomes.

    Factor values and references must be supplied by the caller. This function
    does not retrieve, endorse or independently validate environmental factors.
    """
    period = _text(reporting_period, "reporting_period")
    boundary = _text(facility_boundary, "facility_boundary")
    region = _text(geography, "geography")
    if not isinstance(factors, Mapping):
        raise ResourceValidationError("Environmental factors must be an object.")
    required_factor_names = {
        "freshwater", "wastewater", "electricity", "fuel",
        "waste_diversion", "transport", "chemical", "residual_waste",
    }
    unknown_factors = sorted(set(factors) - required_factor_names)
    if unknown_factors:
        raise ResourceValidationError(f"Unknown environmental factor(s): {', '.join(str(x) for x in unknown_factors)}.")
    factor_units = {
        "freshwater": "kgCO2e/m3",
        "wastewater": "kgCO2e/m3",
        "electricity": "kgCO2e/kWh",
        "fuel": "kgCO2e/kWh",
        "waste_diversion": "kgCO2e/kg",
        "transport": "kgCO2e/tonne-km",
        "chemical": "kgCO2e/kg",
        "residual_waste": "kgCO2e/kg",
    }
    normalized_factors = {}
    for name, expected_unit in factor_units.items():
        item = factors.get(name)
        if not isinstance(item, Mapping):
            raise ResourceValidationError(f"Environmental factor {name} is required.")
        value = _number(item.get("value"), f"factors.{name}.value", minimum=0)
        unit = _text(item.get("unit"), f"factors.{name}.unit")
        if unit.casefold() != expected_unit.casefold():
            raise ResourceValidationError(f"Factor {name} must use {expected_unit}.")
        source = _text(item.get("source_reference"), f"factors.{name}.source_reference")
        version = _text(item.get("version"), f"factors.{name}.version")
        normalized_factors[name] = {
            "value": value,
            "unit": unit,
            "source_reference": source,
            "version": version,
        }
    quantities = {
        "avoided_freshwater_m3": _number(avoided_freshwater_m3, "avoided_freshwater_m3", minimum=0),
        "avoided_wastewater_m3": _number(avoided_wastewater_m3, "avoided_wastewater_m3", minimum=0),
        "avoided_electricity_kwh": _number(avoided_electricity_kwh, "avoided_electricity_kwh", minimum=0),
        "avoided_fuel_kwh": _number(avoided_fuel_kwh, "avoided_fuel_kwh", minimum=0),
        "diverted_waste_kg": _number(diverted_waste_kg, "diverted_waste_kg", minimum=0),
        "added_treatment_electricity_kwh": _number(added_treatment_electricity_kwh, "added_treatment_electricity_kwh", minimum=0),
        "added_transport_tonne_km": _number(added_transport_tonne_km, "added_transport_tonne_km", minimum=0),
        "added_chemical_kg": _number(added_chemical_kg, "added_chemical_kg", minimum=0),
        "added_residual_waste_kg": _number(added_residual_waste_kg, "added_residual_waste_kg", minimum=0),
    }
    avoided_components = {
        "freshwater": quantities["avoided_freshwater_m3"] * normalized_factors["freshwater"]["value"],
        "wastewater": quantities["avoided_wastewater_m3"] * normalized_factors["wastewater"]["value"],
        "electricity": quantities["avoided_electricity_kwh"] * normalized_factors["electricity"]["value"],
        "fuel": quantities["avoided_fuel_kwh"] * normalized_factors["fuel"]["value"],
        "waste_diversion": quantities["diverted_waste_kg"] * normalized_factors["waste_diversion"]["value"],
    }
    burden_components = {
        "treatment_electricity": quantities["added_treatment_electricity_kwh"] * normalized_factors["electricity"]["value"],
        "transport": quantities["added_transport_tonne_km"] * normalized_factors["transport"]["value"],
        "additional_chemicals": quantities["added_chemical_kg"] * normalized_factors["chemical"]["value"],
        "residual_waste": quantities["added_residual_waste_kg"] * normalized_factors["residual_waste"]["value"],
    }
    gross_avoided = sum(avoided_components.values())
    additional_burden = sum(burden_components.values())
    net_avoided = gross_avoided - additional_burden
    status = _text(evidence_status, "evidence_status").upper()
    if status not in {"FORECAST", "ESTIMATED", "MEASURED", "INDEPENDENTLY_VERIFIED"}:
        raise ResourceValidationError("Unsupported environmental evidence status.")
    if status == "INDEPENDENTLY_VERIFIED":
        status = "MEASURED_PENDING_INDEPENDENT_EVIDENCE"
    return {
        "status": "NET_ENVIRONMENTAL_BENEFIT_ESTIMATED" if net_avoided > 0 else (
            "NET_ENVIRONMENTAL_BURDEN_ESTIMATED" if net_avoided < 0 else "NO_NET_CO2E_CHANGE_ESTIMATED"
        ),
        "reporting_period": period,
        "facility_boundary": boundary,
        "geography": region,
        "physical_resource_outcomes": {
            "avoided_freshwater_m3": quantities["avoided_freshwater_m3"],
            "avoided_wastewater_m3": quantities["avoided_wastewater_m3"],
            "avoided_electricity_kwh": quantities["avoided_electricity_kwh"],
            "avoided_fuel_kwh": quantities["avoided_fuel_kwh"],
            "diverted_waste_kg": quantities["diverted_waste_kg"],
            "added_treatment_electricity_kwh": quantities["added_treatment_electricity_kwh"],
            "added_transport_tonne_km": quantities["added_transport_tonne_km"],
            "added_chemical_kg": quantities["added_chemical_kg"],
            "added_residual_waste_kg": quantities["added_residual_waste_kg"],
        },
        "avoided_emissions_kgco2e_by_component": avoided_components,
        "additional_burden_kgco2e_by_component": burden_components,
        "gross_avoided_emissions_kgco2e": gross_avoided,
        "additional_burden_kgco2e": additional_burden,
        "net_avoided_emissions_kgco2e": net_avoided,
        "evidence_status": status,
        "factor_registry": normalized_factors,
        "independent_verification": "NOT_ESTABLISHED",
        "limitations": [
            "All emission factors and physical quantities are caller-supplied and have not been independently validated.",
            "The caller must ensure that factor boundaries, geography, reporting period and allocation methods are compatible.",
            "No lifecycle, indirect, rebound or omitted burdens are included unless explicitly represented in the inputs.",
            "Do not add the same electricity or fuel benefit to multiple components; double counting is not automatically detected.",
            "A positive net value is an estimate, not a verified environmental claim or certification.",
        ],
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
    minimum_samples = int(minimum_samples)
    if minimum_samples < 12:
        raise ResourceValidationError("minimum_samples must be at least 12 to retain training and holdout observations.")
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
    minimum_periods = int(minimum_periods)
    if minimum_periods < 1:
        raise ResourceValidationError("minimum_periods must be at least 1.")
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


def optimize_single_contaminant_water_reuse(
    sources: Sequence[Mapping[str, Any]],
    sinks: Sequence[Mapping[str, Any]],
    connections: Sequence[Mapping[str, Any]],
    *,
    contaminant: str,
    concentration_unit: str,
    flow_unit: str,
) -> dict[str, Any]:
    """Maximize preliminary water reuse with one blended-contaminant limit.

    Every physical source-to-sink connection must be explicitly entered and
    marked as user-confirmed with an evidence reference. The model covers one
    contaminant only and does not model treatment, pathogens, chemistry or permits.
    """
    contaminant_name = _text(contaminant, "contaminant")
    concentration_label = _text(concentration_unit, "concentration_unit")
    flow_label = _text(flow_unit, "flow_unit")
    if not sources or not sinks:
        raise ResourceValidationError("At least one water source and one demand sink are required.")
    source_map: dict[str, dict[str, Any]] = {}
    sink_map: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(sources):
        source_id = _text(source.get("source_id"), f"sources[{index}].source_id")
        if source_id in source_map:
            raise ResourceValidationError(f"Duplicate source_id: {source_id}.")
        source_unit = _text(source.get("flow_unit"), f"sources[{index}].flow_unit")
        quality_unit = _text(source.get("concentration_unit"), f"sources[{index}].concentration_unit")
        if source_unit.casefold() != flow_label.casefold():
            raise ResourceValidationError(f"Source {source_id} flow unit does not match {flow_label}.")
        if quality_unit.casefold() != concentration_label.casefold():
            raise ResourceValidationError(f"Source {source_id} concentration unit does not match {concentration_label}.")
        source_map[source_id] = {
            "source_id": source_id,
            "available_flow": _number(source.get("available_flow"), f"sources[{index}].available_flow", minimum=0),
            "concentration": _number(source.get("concentration"), f"sources[{index}].concentration", minimum=0),
        }
    for index, sink in enumerate(sinks):
        sink_id = _text(sink.get("sink_id"), f"sinks[{index}].sink_id")
        if sink_id in sink_map:
            raise ResourceValidationError(f"Duplicate sink_id: {sink_id}.")
        sink_unit = _text(sink.get("flow_unit"), f"sinks[{index}].flow_unit")
        quality_unit = _text(sink.get("concentration_unit"), f"sinks[{index}].concentration_unit")
        if sink_unit.casefold() != flow_label.casefold():
            raise ResourceValidationError(f"Sink {sink_id} flow unit does not match {flow_label}.")
        if quality_unit.casefold() != concentration_label.casefold():
            raise ResourceValidationError(f"Sink {sink_id} concentration unit does not match {concentration_label}.")
        demand = _number(sink.get("required_flow"), f"sinks[{index}].required_flow", minimum=0)
        maximum = _number(sink.get("maximum_concentration"), f"sinks[{index}].maximum_concentration", minimum=0)
        sink_map[sink_id] = {
            "sink_id": sink_id,
            "required_flow": demand,
            "maximum_concentration": maximum,
        }

    eligible_connections: list[dict[str, Any]] = []
    rejected_connections: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for index, connection in enumerate(connections):
        source_id = _text(connection.get("source_id"), f"connections[{index}].source_id")
        sink_id = _text(connection.get("sink_id"), f"connections[{index}].sink_id")
        if source_id not in source_map or sink_id not in sink_map:
            raise ResourceValidationError(f"Connection references unknown source or sink: {source_id} -> {sink_id}.")
        if (source_id, sink_id) in seen:
            raise ResourceValidationError(f"Duplicate water reuse connection: {source_id} -> {sink_id}.")
        seen.add((source_id, sink_id))
        evidence = _optional_text(connection.get("connection_evidence_reference"))
        if connection.get("connection_confirmed") is not True or not evidence:
            rejected_connections.append({
                "source_id": source_id,
                "sink_id": sink_id,
                "reason": "A user-confirmed physical connection and evidence reference are required.",
            })
            continue
        capacity = _number(
            connection.get("capacity", min(
                source_map[source_id]["available_flow"], sink_map[sink_id]["required_flow"]
            )),
            f"connections[{index}].capacity",
            minimum=0,
        )
        if capacity <= 0:
            continue
        eligible_connections.append({
            "source_id": source_id,
            "sink_id": sink_id,
            "capacity": min(
                capacity,
                source_map[source_id]["available_flow"],
                sink_map[sink_id]["required_flow"],
            ),
            "connection_evidence_reference": evidence,
        })

    if not eligible_connections:
        return {
            "status": "NO_CONFIRMED_REUSE_CONNECTION",
            "contaminant": contaminant_name,
            "allocations": [],
            "total_reuse_flow": 0.0,
            "rejected_connections": rejected_connections,
            "operational_authorization": False,
        }

    n_edges = len(eligible_connections)
    objective = -np.ones(n_edges, dtype=float)
    a_ub: list[list[float]] = []
    b_ub: list[float] = []
    source_ids = list(source_map)
    sink_ids = list(sink_map)
    for source_id in source_ids:
        a_ub.append([1.0 if edge["source_id"] == source_id else 0.0 for edge in eligible_connections])
        b_ub.append(source_map[source_id]["available_flow"])
    for sink_id in sink_ids:
        a_ub.append([1.0 if edge["sink_id"] == sink_id else 0.0 for edge in eligible_connections])
        b_ub.append(sink_map[sink_id]["required_flow"])
        a_ub.append([
            source_map[edge["source_id"]]["concentration"] - sink_map[sink_id]["maximum_concentration"]
            if edge["sink_id"] == sink_id else 0.0
            for edge in eligible_connections
        ])
        b_ub.append(0.0)

    solved = linprog(
        c=objective,
        A_ub=np.asarray(a_ub, dtype=float),
        b_ub=np.asarray(b_ub, dtype=float),
        bounds=[(0, edge["capacity"]) for edge in eligible_connections],
        method="highs",
    )
    if not solved.success:
        return {
            "status": "OPTIMIZATION_FAILED",
            "solver_message": str(solved.message),
            "allocations": [],
            "total_reuse_flow": 0.0,
            "rejected_connections": rejected_connections,
            "operational_authorization": False,
        }

    allocations: list[dict[str, Any]] = []
    sink_flow: dict[str, float] = {sink_id: 0.0 for sink_id in sink_ids}
    sink_contaminant_load: dict[str, float] = {sink_id: 0.0 for sink_id in sink_ids}
    source_flow: dict[str, float] = {source_id: 0.0 for source_id in source_ids}
    for index, edge in enumerate(eligible_connections):
        flow = float(solved.x[index])
        if flow <= 1e-8:
            continue
        concentration = source_map[edge["source_id"]]["concentration"]
        sink_id = edge["sink_id"]
        source_flow[edge["source_id"]] += flow
        sink_flow[sink_id] += flow
        sink_contaminant_load[sink_id] += flow * concentration
        allocations.append({
            **edge,
            "allocated_flow": flow,
            "source_concentration": concentration,
        })

    sink_quality: list[dict[str, Any]] = []
    quality_violations = []
    flow_violations = []
    for sink_id, flow in sink_flow.items():
        if flow > sink_map[sink_id]["required_flow"] + 1e-7:
            flow_violations.append(f"Sink demand exceeded: {sink_id}.")
        if flow <= 1e-8:
            continue
        blended = sink_contaminant_load[sink_id] / flow
        maximum = sink_map[sink_id]["maximum_concentration"]
        if blended > maximum + 1e-7:
            quality_violations.append(sink_id)
        sink_quality.append({
            "sink_id": sink_id,
            "allocated_flow": flow,
            "blended_concentration": blended,
            "maximum_concentration": maximum,
            "concentration_unit": concentration_label,
        })
    for source_id, flow in source_flow.items():
        if flow > source_map[source_id]["available_flow"] + 1e-7:
            flow_violations.append(f"Source supply exceeded: {source_id}.")
    for index, edge in enumerate(eligible_connections):
        if float(solved.x[index]) > edge["capacity"] + 1e-7:
            flow_violations.append(f"Connection capacity exceeded: {edge['source_id']} -> {edge['sink_id']}.")
    total_flow = float(sum(sink_flow.values()))
    if quality_violations or flow_violations:
        status = "VALIDATION_FAILED"
    elif total_flow <= 1e-8:
        status = "NO_QUALIFIED_REUSE"
    else:
        status = "PRELIMINARY_SINGLE_CONTAMINANT_REUSE_ALLOCATION"
    return {
        "status": status,
        "contaminant": contaminant_name,
        "concentration_unit": concentration_label,
        "flow_unit": flow_label,
        "total_reuse_flow": total_flow,
        "allocations": allocations,
        "source_flow_totals": source_flow,
        "sink_quality_checks": sink_quality,
        "rejected_connections": rejected_connections,
        "solver": "scipy.optimize.linprog(method=highs)",
        "quality_violations": quality_violations,
        "flow_violations": flow_violations,
        "physical_connection_confirmation_is_user_asserted": True,
        "operational_authorization": False,
        "limitations": [
            "One dissolved contaminant and perfect mixing only.",
            "No treatment unit, secondary waste, microbial, chemical interaction or process-specific requirement is modeled.",
            "Connection evidence is user-entered and not independently checked.",
            "This is not a multi-contaminant water-pinch study or authorization to reuse water.",
        ],
    }


def calculate_energy_balance(
    energy_input_kwh: float,
    useful_energy_output_kwh: float,
    waste_heat_output_kwh: float,
    other_energy_output_kwh: float = 0.0,
    *,
    tolerance_percent: float = 1.0,
) -> dict[str, Any]:
    """Reconcile same-boundary energy terms without treating residual as confirmed loss."""
    energy_in = _number(energy_input_kwh, "energy_input_kwh", minimum=0)
    useful = _number(useful_energy_output_kwh, "useful_energy_output_kwh", minimum=0)
    waste_heat = _number(waste_heat_output_kwh, "waste_heat_output_kwh", minimum=0)
    other = _number(other_energy_output_kwh, "other_energy_output_kwh", minimum=0)
    tolerance = _number(tolerance_percent, "tolerance_percent", minimum=0)
    if energy_in <= 0:
        raise ResourceValidationError("energy_input_kwh must be greater than zero.")
    accounted = useful + waste_heat + other
    residual = energy_in - accounted
    residual_percent = 100.0 * residual / energy_in
    anomaly = abs(residual_percent) > tolerance
    return {
        "status": "ANOMALY_SUSPECTED" if anomaly else "WITHIN_TOLERANCE",
        "energy_input_kwh": energy_in,
        "useful_energy_output_kwh": useful,
        "waste_heat_output_kwh": waste_heat,
        "other_energy_output_kwh": other,
        "accounted_output_kwh": accounted,
        "unreconciled_energy_kwh": residual,
        "unreconciled_percent": residual_percent,
        "useful_energy_ratio_percent": 100.0 * useful / energy_in,
        "waste_heat_ratio_percent": 100.0 * waste_heat / energy_in,
        "tolerance_percent": tolerance,
        "interpretation": (
            "The entered energy terms do not close within tolerance. Check boundary, time basis, meter uncertainty and omitted streams; this is not proof of a specific energy loss."
            if anomaly else
            "The entered energy terms close within the configured tolerance; this does not independently verify the measurements or system boundary."
        ),
    }


def screen_waste_heat_recovery(
    source_temperature_c: float,
    sink_temperature_c: float,
    available_heat_rate_kw: float,
    *,
    minimum_approach_temperature_c: float,
    annual_operating_hours: float | None = None,
    energy_value_per_kwh: float | None = None,
) -> dict[str, Any]:
    """Run a temperature-approach screen; no exchanger performance is presumed."""
    source_temp = _number(source_temperature_c, "source_temperature_c")
    sink_temp = _number(sink_temperature_c, "sink_temperature_c")
    heat_rate = _number(available_heat_rate_kw, "available_heat_rate_kw", minimum=0)
    approach = _number(minimum_approach_temperature_c, "minimum_approach_temperature_c", minimum=0)
    if heat_rate <= 0:
        raise ResourceValidationError("available_heat_rate_kw must be greater than zero.")
    margin = source_temp - sink_temp - approach
    annual_energy = None
    indicative_value = None
    operating_hours = None
    rate_value = None
    if annual_operating_hours is not None:
        operating_hours = _number(annual_operating_hours, "annual_operating_hours", minimum=0)
        if operating_hours > 8760:
            raise ResourceValidationError("annual_operating_hours must not exceed 8760.")
        annual_energy = heat_rate * operating_hours
    if energy_value_per_kwh is not None:
        rate_value = _number(energy_value_per_kwh, "energy_value_per_kwh", minimum=0)
        if annual_energy is not None:
            indicative_value = annual_energy * rate_value
    passed = margin > 0
    return {
        "status": "TEMPERATURE_APPROACH_PASSED_REQUIRES_HX_DESIGN" if passed else "INFEASIBLE_TEMPERATURE_APPROACH",
        "source_temperature_c": source_temp,
        "sink_temperature_c": sink_temp,
        "minimum_approach_temperature_c": approach,
        "temperature_margin_c": margin,
        "entered_heat_source_rate_kw": heat_rate,
        "screened_annual_thermal_energy_kwh": annual_energy,
        "energy_value_per_kwh": rate_value,
        "indicative_thermal_energy_value": indicative_value,
        "verified_recovered_energy_kwh": None,
        "verified_savings": None,
        "independent_verification": "NOT_PERFORMED",
        "note": "Temperature feasibility screen only. Actual heat duty, exchanger effectiveness, fouling, pressure drop, utility integration, CAPEX/OPEX and safety require separate engineering design and validation.",
    }


def monitor_resource_intensity_persistence(
    baseline_usage: float,
    baseline_production: float,
    observations: Sequence[Mapping[str, Any]],
    *,
    usage_unit: str,
    production_unit: str,
    degradation_threshold_percent: float = 5.0,
    required_consecutive_periods: int = 2,
) -> dict[str, Any]:
    """Monitor normalized usage against a declared baseline over dated periods.

    The monitor flags deviations only; it does not establish cause or verified
    savings, and does not adjust for operating conditions beyond production volume.
    """
    base_usage = _number(baseline_usage, "baseline_usage", minimum=0)
    base_output = _number(baseline_production, "baseline_production", minimum=0)
    if base_usage <= 0 or base_output <= 0:
        raise ResourceValidationError("Baseline usage and production must both be greater than zero.")
    threshold = _number(degradation_threshold_percent, "degradation_threshold_percent", minimum=0)
    required = int(required_consecutive_periods)
    if required < 1:
        raise ResourceValidationError("required_consecutive_periods must be at least 1.")
    if len(observations) < required:
        return {
            "status": "INSUFFICIENT_DATA",
            "sample_count": len(observations),
            "required_consecutive_periods": required,
            "baseline_intensity": base_usage / base_output,
            "periods": [],
        }
    usage_label = _text(usage_unit, "usage_unit")
    output_label = _text(production_unit, "production_unit")
    baseline_intensity = base_usage / base_output
    periods: list[dict[str, Any]] = []
    timestamps: list[str] = []
    for index, row in enumerate(observations):
        timestamp = _utc_timestamp(row.get("timestamp"), f"observations[{index}].timestamp")
        if timestamp is None:
            raise ResourceValidationError("Every monitoring observation requires a timezone-aware timestamp.")
        timestamps.append(timestamp)
        usage = _number(row.get("usage"), f"observations[{index}].usage", minimum=0)
        production = _number(row.get("production"), f"observations[{index}].production", minimum=0)
        if production <= 0:
            raise ResourceValidationError("Every monitoring period requires positive production.")
        intensity = usage / production
        change = 100.0 * (intensity - baseline_intensity) / baseline_intensity
        state = (
            "DEGRADATION_SUSPECTED" if change > threshold else
            "LOWER_INTENSITY_OBSERVED" if change < -threshold else
            "WITHIN_BASELINE_BAND"
        )
        periods.append({
            "timestamp": timestamp,
            "usage": usage,
            "production": production,
            "intensity": intensity,
            "intensity_unit": f"{usage_label} per {output_label}",
            "change_from_baseline_percent": change,
            "status": state,
        })
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise ResourceValidationError("Monitoring observations must have unique, ascending timestamps.")
    trailing_degradation = 0
    for period in reversed(periods):
        if period["status"] == "DEGRADATION_SUSPECTED":
            trailing_degradation += 1
        else:
            break
    alert = trailing_degradation >= required
    latest_status = periods[-1]["status"]
    status = "PERSISTENCE_ALERT" if alert else latest_status
    return {
        "status": status,
        "sample_count": len(periods),
        "baseline_intensity": baseline_intensity,
        "intensity_unit": f"{usage_label} per {output_label}",
        "degradation_threshold_percent": threshold,
        "required_consecutive_periods": required,
        "trailing_degradation_periods": trailing_degradation,
        "persistence_alert": alert,
        "periods": periods,
        "verified_savings": None,
        "causality_verified": False,
        "limitations": [
            "Production-volume normalization only; operating hours, product mix, quality and ambient/process conditions are not adjusted.",
            "A degradation alert identifies a deviation from the entered baseline, not its cause.",
            "Observed lower intensity is not independently verified savings.",
        ],
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


def validate_exchange_agreement(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create a structured exchange draft; it is not a signed contract or release."""
    if not isinstance(payload, Mapping):
        raise ResourceValidationError("Exchange agreement must be an object.")
    supplier = _text(payload.get("supplier"), "supplier")
    buyer = _text(payload.get("buyer"), "buyer")
    resource_id = _text(payload.get("resource_id"), "resource_id")
    resource_name = _text(payload.get("resource_name"), "resource_name")
    unit = _text(payload.get("unit"), "unit")
    quantity = _number(payload.get("agreed_quantity"), "agreed_quantity", minimum=0)
    if quantity <= 0:
        raise ResourceValidationError("agreed_quantity must be greater than zero.")
    tolerance = _number(payload.get("quantity_tolerance_percent"), "quantity_tolerance_percent", minimum=0)
    if tolerance > 100:
        raise ResourceValidationError("quantity_tolerance_percent must not exceed 100.")
    schedule = _text(payload.get("delivery_schedule"), "delivery_schedule")
    quality_limits = payload.get("quality_limits")
    if not isinstance(quality_limits, Mapping) or not quality_limits:
        raise ResourceValidationError("At least one explicit quality limit is required.")
    normalized_limits: dict[str, dict[str, float | None]] = {}
    for name, bounds in quality_limits.items():
        property_name = _text(name, "quality property")
        if not isinstance(bounds, Mapping):
            raise ResourceValidationError(f"Quality bounds for {property_name} must be an object.")
        lower = _number(bounds["min"], f"{property_name}.min") if bounds.get("min") is not None else None
        upper = _number(bounds["max"], f"{property_name}.max") if bounds.get("max") is not None else None
        if lower is None and upper is None:
            raise ResourceValidationError(f"Quality property {property_name} needs a minimum or maximum.")
        if lower is not None and upper is not None and lower > upper:
            raise ResourceValidationError(f"Quality minimum exceeds maximum for {property_name}.")
        normalized_limits[property_name] = {"min": lower, "max": upper}
    certificate_required = payload.get("certificate_required", False)
    if not isinstance(certificate_required, bool):
        raise ResourceValidationError("certificate_required must be a boolean.")
    approval_payload = payload.get("approval_references")
    if _is_missing(approval_payload):
        approval_payload = {}
    if not isinstance(approval_payload, Mapping):
        raise ResourceValidationError("approval_references must be an object.")
    approval_references = {
        key: _optional_text(approval_payload.get(key))
        for key in ("engineering", "safety", "environmental", "commercial")
    }
    missing_approvals = [key for key, value in approval_references.items() if not value]
    return {
        "agreement_id": _optional_text(payload.get("agreement_id")) or str(uuid4()),
        "supplier": supplier,
        "buyer": buyer,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "agreed_quantity": quantity,
        "unit": unit,
        "quantity_tolerance_percent": tolerance,
        "quality_limits": normalized_limits,
        "delivery_schedule": schedule,
        "certificate_required": certificate_required,
        "treatment_responsibility": _optional_text(payload.get("treatment_responsibility")),
        "testing_requirements": _optional_text(payload.get("testing_requirements")),
        "shortage_response": _optional_text(payload.get("shortage_response")),
        "rejection_procedure": _optional_text(payload.get("rejection_procedure")),
        "approval_references": approval_references,
        "missing_approval_references": missing_approvals,
        "status": "APPROVAL_PENDING" if missing_approvals else "APPROVAL_REFERENCES_RECORDED_NOT_SIGNED",
        "contract_status": "DRAFT_NOT_A_SIGNED_CONTRACT",
        "created_at": _optional_text(payload.get("created_at")) or datetime.now(timezone.utc).isoformat(),
        "contractual_effect": "NOT_CALCULATED",
        "operational_authorization": False,
    }


def assess_exchange_delivery(
    agreement: Mapping[str, Any],
    delivery: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare a delivery with entered agreement terms; require human acceptance."""
    if not isinstance(agreement, Mapping) or not isinstance(delivery, Mapping):
        raise ResourceValidationError("Agreement and delivery must both be objects.")
    agreement_id = _text(agreement.get("agreement_id"), "agreement_id")
    delivery_date_text = _text(delivery.get("delivery_date"), "delivery_date")
    try:
        delivery_day = date.fromisoformat(delivery_date_text)
    except ValueError as exc:
        raise ResourceValidationError("delivery_date must be a valid YYYY-MM-DD date.") from exc
    expected = _number(agreement.get("agreed_quantity"), "agreed_quantity", minimum=0)
    delivered = _number(delivery.get("delivered_quantity"), "delivered_quantity", minimum=0)
    tolerance = _number(agreement.get("quantity_tolerance_percent"), "quantity_tolerance_percent", minimum=0)
    if expected <= 0 or tolerance > 100:
        raise ResourceValidationError("Agreement quantity or tolerance is invalid.")
    certificate_required = agreement.get("certificate_required", False)
    if not isinstance(certificate_required, bool):
        raise ResourceValidationError("Agreement certificate_required must be a boolean.")
    quality_terms = agreement.get("quality_limits")
    if not isinstance(quality_terms, Mapping) or not quality_terms:
        raise ResourceValidationError("Agreement quality_limits must be a non-empty object.")
    for property_name, bounds in quality_terms.items():
        if not isinstance(bounds, Mapping):
            raise ResourceValidationError(f"Agreement quality bounds for {property_name} must be an object.")
        lower = _number(bounds["min"], f"{property_name}.min") if bounds.get("min") is not None else None
        upper = _number(bounds["max"], f"{property_name}.max") if bounds.get("max") is not None else None
        if lower is None and upper is None:
            raise ResourceValidationError(f"Agreement quality limits for {property_name} are empty.")
        if lower is not None and upper is not None and lower > upper:
            raise ResourceValidationError(f"Agreement quality minimum exceeds maximum for {property_name}.")
    unit = _text(agreement.get("unit"), "agreement.unit")
    tolerance_quantity = expected * tolerance / 100.0
    deviations: list[str] = []
    if delivered < expected - tolerance_quantity:
        deviations.append("SHORTAGE")
    elif delivered > expected + tolerance_quantity:
        deviations.append("EXCESS_QUANTITY")

    measured_quality = delivery.get("quality")
    missing_quality: list[str] = []
    quality_failures: list[str] = []
    limits = quality_terms
    if not isinstance(measured_quality, Mapping):
        missing_quality.extend(str(key) for key in limits)
    else:
        for property_name, bounds in limits.items():
            if property_name not in measured_quality:
                missing_quality.append(str(property_name))
                continue
            value = _number(measured_quality[property_name], f"delivery.quality.{property_name}")
            lower = bounds.get("min") if isinstance(bounds, Mapping) else None
            upper = bounds.get("max") if isinstance(bounds, Mapping) else None
            if lower is not None and value < float(lower):
                quality_failures.append(f"{property_name}={value} below {lower}")
            if upper is not None and value > float(upper):
                quality_failures.append(f"{property_name}={value} above {upper}")
    if missing_quality:
        deviations.append("QUALITY_DATA_MISSING")
    if quality_failures:
        deviations.append("QUALITY_OUT_OF_SPECIFICATION")

    certificate_reference = _optional_text(delivery.get("certificate_reference"))
    certificate_valid_until = _optional_text(delivery.get("certificate_valid_until"))
    if certificate_required:
        if not certificate_reference or not certificate_valid_until:
            deviations.append("CERTIFICATE_MISSING")
        else:
            try:
                expiry_day = date.fromisoformat(certificate_valid_until)
            except ValueError as exc:
                raise ResourceValidationError("certificate_valid_until must be a valid YYYY-MM-DD date.") from exc
            if expiry_day < delivery_day:
                deviations.append("CERTIFICATE_EXPIRED")
    evidence_reference = _optional_text(delivery.get("delivery_evidence_reference"))
    if not evidence_reference:
        deviations.append("DELIVERY_EVIDENCE_MISSING")

    blocking = {
        "QUALITY_DATA_MISSING", "QUALITY_OUT_OF_SPECIFICATION",
        "CERTIFICATE_MISSING", "CERTIFICATE_EXPIRED",
    }
    if any(item in blocking for item in deviations):
        status = "REJECTED_PENDING_REVIEW"
    elif "DELIVERY_EVIDENCE_MISSING" in deviations:
        status = "EVIDENCE_INCOMPLETE"
    elif "SHORTAGE" in deviations:
        status = "SHORTAGE_REVIEW"
    elif "EXCESS_QUANTITY" in deviations:
        status = "EXCESS_REVIEW"
    else:
        status = "WITHIN_ENTERED_TOLERANCES_PENDING_HUMAN_ACCEPTANCE"
    return {
        "delivery_id": _optional_text(delivery.get("delivery_id")) or str(uuid4()),
        "agreement_id": agreement_id,
        "delivery_date": delivery_day.isoformat(),
        "expected_quantity": expected,
        "delivered_quantity": delivered,
        "unit": unit,
        "quantity_tolerance": tolerance_quantity,
        "quantity_variance": delivered - expected,
        "quality_failures": quality_failures,
        "missing_quality_properties": missing_quality,
        "deviations": deviations,
        "status": status,
        "certificate_reference": certificate_reference,
        "certificate_valid_until": certificate_valid_until,
        "delivery_evidence_reference": evidence_reference,
        "human_acceptance_required": True,
        "contractual_effect": "NOT_CALCULATED",
        "operational_authorization": False,
        "independent_verification": "NOT_PERFORMED",
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
    "PROVENANCE_VALUES", "USER_INPUT_PROVENANCE_VALUES", "COMPATIBILITY_STATUSES", "CASCADE_ORDER",
    "ResourceValidationError", "validate_resource_passport",
    "append_resource_passport_revision", "verify_resource_passport_history",
    "assess_resource_compatibility", "calculate_resource_balance",
    "detect_resource_loss", "optimize_resource_network", "optimize_period_aligned_resource_network",
    "simulate_supplier_disruption", "simulate_resource_network_scenario", "evaluate_safety_gate",
    "calculate_exchange_value", "propagate_network_impact",
    "forecast_resource_quality", "calculate_supply_reliability",
    "rank_resource_cascade", "detect_resource_bottleneck",
    "assess_infrastructure_route", "calculate_resource_intensity_change",
    "monitor_resource_intensity_persistence",
    "calculate_energy_balance", "screen_waste_heat_recovery",
    "optimize_single_contaminant_water_reuse",
    "validate_exchange_agreement", "assess_exchange_delivery",
    "assess_resource_substitution", "rank_resource_improvement_projects",
    "calculate_environmental_impact",
    "validate_import_rows",
]
