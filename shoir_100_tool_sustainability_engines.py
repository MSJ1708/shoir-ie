"""Bounded measured-resource and ROI arithmetic for Shoir-IE targets T077/T079/T083."""
from __future__ import annotations

from datetime import date
import math
from typing import Any

import pandas as pd


def _txt(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _number(value: Any, label: str, *, minimum: float = 0, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    if positive and number <= 0:
        raise ValueError(f"{label} must be greater than zero.")
    if number < minimum:
        raise ValueError(f"{label} must be at least {minimum}.")
    return number


def _date(value: Any, label: str, *, required: bool = True) -> str | None:
    raw = _txt(value)
    if not raw and not required:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD format.") from exc
    if parsed.isoformat() != raw:
        raise ValueError(f"{label} must use YYYY-MM-DD format.")
    return raw


def _resource_frame(value: Any, label: str, required: set[str]) -> pd.DataFrame:
    frame = value.copy(deep=True) if isinstance(value, pd.DataFrame) else pd.DataFrame(list(value))
    if frame.empty:
        raise ValueError(f"{label} requires at least one row.")
    if frame.columns.has_duplicates:
        raise ValueError(f"{label} must have unique columns.")
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label} is missing columns: " + ", ".join(missing) + ".")
    if len(frame) > 1000:
        raise ValueError(f"{label} is limited to 1000 rows.")
    return frame


def analyze_energy_intensity(
    rows: Any,
    baseline_period: str,
    *,
    tariff_per_kwh: float | None = None,
    emission_factor_kg_per_kwh: float | None = None,
    factor_source: str = "",
    factor_date: str = "",
) -> dict[str, Any]:
    """Compare measured energy intensity with a user-chosen measured baseline."""
    frame = _resource_frame(rows, "Energy dataset", {"period", "production_units", "energy_kwh"})
    baseline_period = _txt(baseline_period)
    if not baseline_period:
        raise ValueError("Select a baseline period.")
    periods = [_txt(v) for v in frame["period"]]
    if any(not p for p in periods):
        raise ValueError("Every energy row requires a period label.")
    if len({p.casefold() for p in periods}) != len(periods):
        raise ValueError("Energy period labels must be unique.")
    output = []
    for ix, raw in enumerate(frame.to_dict(orient="records"), start=1):
        production = _number(raw.get("production_units"), f"Energy row {ix} production_units", positive=True)
        energy = _number(raw.get("energy_kwh"), f"Energy row {ix} energy_kwh")
        output.append({"period": _txt(raw.get("period")), "production_units": production, "energy_kwh": energy,
                       "energy_kwh_per_unit": energy / production})
    result = pd.DataFrame(output)
    baseline_rows = result.loc[result["period"] == baseline_period]
    if baseline_rows.empty:
        raise ValueError(f"Baseline period '{baseline_period}' was not found.")
    baseline_intensity = float(baseline_rows.iloc[0]["energy_kwh_per_unit"])
    result["baseline_kwh_per_unit"] = baseline_intensity
    result["normalized_baseline_energy_kwh"] = baseline_intensity * result["production_units"]
    result["estimated_energy_difference_kwh"] = result["normalized_baseline_energy_kwh"] - result["energy_kwh"]
    if baseline_intensity > 0:
        result["intensity_change_percent_vs_baseline"] = (
            baseline_intensity - result["energy_kwh_per_unit"]
        ) / baseline_intensity * 100.0
    else:
        result["intensity_change_percent_vs_baseline"] = None
    tariff = None if tariff_per_kwh is None else _number(tariff_per_kwh, "Tariff per kWh")
    if tariff is not None:
        result["estimated_energy_cost"] = result["energy_kwh"] * tariff
        result["estimated_cost_difference_vs_normalized_baseline"] = result["estimated_energy_difference_kwh"] * tariff
    factor = None if emission_factor_kg_per_kwh is None else _number(emission_factor_kg_per_kwh, "Emission factor per kWh")
    factor_source = _txt(factor_source)
    factor_date_value = _date(factor_date, "Emission factor date", required=False)
    if factor is not None:
        if not factor_source or not factor_date_value:
            raise ValueError("An emission factor requires a source and YYYY-MM-DD factor date.")
        result["estimated_emissions_kg_co2e"] = result["energy_kwh"] * factor
    elif factor_source or factor_date_value:
        raise ValueError("Provide both an emission factor value, source and date, or leave all factor fields blank.")
    warnings = [
        "Energy differences are normalized to the selected measured baseline and supplied production units; they are not independently verified savings.",
        "The tool compares consumption intensity; it does not optimize controls or connect to live equipment.",
    ]
    if factor is not None:
        warnings.append("Emissions depend entirely on the user-supplied factor and stated boundary; this is not an audited disclosure.")
    return {
        "tool_id": "T077",
        "status": "CALCULATED",
        "method": "Measured energy intensity and normalized baseline comparison",
        "formula": "Energy intensity = kWh / production units; normalized baseline energy = baseline intensity × current production",
        "assumptions": [
            "All rows use compatible kWh and production-unit definitions and comparable periods.",
            "The selected baseline is an appropriate comparison period; mix, weather, shift and production changes are not adjusted automatically.",
        ],
        "warnings": warnings,
        "metrics": {
            "period_count": int(len(result)),
            "baseline_period": baseline_period,
            "baseline_kwh_per_unit": baseline_intensity,
            "total_measured_energy_kwh": float(result["energy_kwh"].sum()),
            "total_normalized_baseline_energy_kwh": float(result["normalized_baseline_energy_kwh"].sum()),
            "estimated_energy_difference_kwh": float(result["estimated_energy_difference_kwh"].sum()),
        },
        "period_comparison": result,
        "provenance": {"source": "USER_ENTERED_MEASUREMENTS", "baseline_period": baseline_period,
                       "factor_source": factor_source or None, "factor_date": factor_date_value},
    }


def analyze_water_waste_efficiency(rows: Any) -> dict[str, Any]:
    """Trend normalized water/waste values; label input-minus-wastewater as an apparent difference only."""
    required = {"period", "production_units", "water_input_m3", "wastewater_m3", "waste_generated_kg", "waste_recycled_kg"}
    frame = _resource_frame(rows, "Water/waste dataset", required)
    periods = [_txt(v) for v in frame["period"]]
    if any(not p for p in periods) or len({p.casefold() for p in periods}) != len(periods):
        raise ValueError("Water/waste period labels must be non-empty and unique.")
    out = []
    for ix, raw in enumerate(frame.to_dict(orient="records"), start=1):
        production = _number(raw.get("production_units"), f"Water/waste row {ix} production_units", positive=True)
        water = _number(raw.get("water_input_m3"), f"Water/waste row {ix} water_input_m3")
        wastewater = _number(raw.get("wastewater_m3"), f"Water/waste row {ix} wastewater_m3")
        generated = _number(raw.get("waste_generated_kg"), f"Water/waste row {ix} waste_generated_kg")
        recycled = _number(raw.get("waste_recycled_kg"), f"Water/waste row {ix} waste_recycled_kg")
        if recycled > generated:
            raise ValueError(f"Water/waste row {ix}: waste_recycled_kg cannot exceed waste_generated_kg.")
        out.append({
            "period": _txt(raw.get("period")), "production_units": production,
            "water_input_m3": water, "wastewater_m3": wastewater,
            "apparent_water_input_minus_wastewater_m3": water - wastewater,
            "water_m3_per_unit": water / production,
            "waste_generated_kg": generated, "waste_recycled_kg": recycled,
            "waste_kg_per_unit": generated / production,
            "waste_recycling_percent": recycled / generated * 100.0 if generated > 0 else None,
        })
    result = pd.DataFrame(out)
    return {
        "tool_id": "T079",
        "status": "CALCULATED",
        "method": "Period-level water and waste normalization",
        "formula": "Water intensity = water input / production; waste intensity = generated waste / production; recycling rate = recycled waste / generated waste",
        "assumptions": [
            "Production and resource quantities are comparable within each period and use stated units.",
            "Input water minus wastewater is only an apparent difference; it is not a closed mass balance unless other in/out flows are accounted for.",
        ],
        "warnings": [
            "The apparent water difference is not a leak/loss calculation without a complete process boundary and all streams.",
            "Resource totals and recycling rates are user-entered and not independently audited.",
        ],
        "metrics": {
            "period_count": int(len(result)),
            "total_water_input_m3": float(result["water_input_m3"].sum()),
            "total_wastewater_m3": float(result["wastewater_m3"].sum()),
            "total_waste_generated_kg": float(result["waste_generated_kg"].sum()),
            "total_waste_recycled_kg": float(result["waste_recycled_kg"].sum()),
            "total_recycling_rate_percent": (
                float(result["waste_recycled_kg"].sum() / result["waste_generated_kg"].sum() * 100.0)
                if result["waste_generated_kg"].sum() > 0 else None
            ),
        },
        "period_comparison": result,
    }


def calculate_roi_evidence(
    *,
    baseline_cost: float,
    post_intervention_cost: float,
    implementation_cost: float,
    currency: str,
    measurement_start: str,
    measurement_end: str,
    baseline_evidence_reference: str,
    post_evidence_reference: str,
    implementation_cost_reference: str,
    verifier_name: str = "",
    evidence_reviewed: bool = False,
) -> dict[str, Any]:
    """Calculate conditional benefit/ROI while refusing to claim verified savings."""
    baseline = _number(baseline_cost, "Baseline cost")
    post = _number(post_intervention_cost, "Post-intervention cost")
    implementation = _number(implementation_cost, "Implementation cost")
    currency = _txt(currency).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("Currency must be a three-letter code such as SAR, USD or EUR.")
    start = _date(measurement_start, "Measurement start")
    end = _date(measurement_end, "Measurement end")
    if date.fromisoformat(end) < date.fromisoformat(start):
        raise ValueError("Measurement end date cannot be earlier than start date.")
    base_ref = _txt(baseline_evidence_reference)
    post_ref = _txt(post_evidence_reference)
    cost_ref = _txt(implementation_cost_reference)
    verifier = _txt(verifier_name)
    gross_change = baseline - post
    net = gross_change - implementation
    all_refs = bool(base_ref and post_ref and cost_ref)
    reviewed_fields = all_refs and bool(verifier) and bool(evidence_reviewed)
    evidence_state = "USER_MARKED_REVIEWED_NOT_INDEPENDENTLY_VERIFIED" if reviewed_fields else "ESTIMATE_ONLY"
    warnings = [
        "All monetary values and evidence references are user-entered; the tool does not verify source records or causal attribution.",
        "A calculated positive net benefit is not a verified or guaranteed saving and must not be used as a marketing claim without independent evidence.",
    ]
    if not all_refs:
        warnings.append("Evidence references are incomplete; baseline, post-intervention and implementation-cost records should be linked.")
    if evidence_reviewed and not verifier:
        warnings.append("A reviewer name is required before the evidence state can be marked as user-reviewed.")
    if implementation == 0:
        roi = None
        warnings.append("ROI percentage is undefined when implementation cost is zero; net benefit is still shown separately.")
    else:
        roi = net / implementation * 100.0
    return {
        "tool_id": "T083",
        "status": "CALCULATED",
        "method": "Baseline/post-intervention cost reconciliation with implementation-cost adjustment",
        "formulas": {
            "gross cost change": "baseline cost − post-intervention cost",
            "net benefit": "baseline cost − post-intervention cost − implementation cost",
            "ROI": "net benefit / implementation cost × 100% (only when implementation cost > 0)",
        },
        "assumptions": [
            "Baseline and post-intervention values cover a comparable measurement window and scope.",
            "Cost units, currency, boundaries and accounting treatment are consistent across the comparison.",
            "User-reviewed evidence is still not an independent audit or proof of causality.",
        ],
        "warnings": warnings,
        "metrics": {
            "currency": currency,
            "measurement_start": start,
            "measurement_end": end,
            "baseline_cost": baseline,
            "post_intervention_cost": post,
            "implementation_cost": implementation,
            "gross_cost_change": gross_change,
            "net_benefit_after_implementation_cost": net,
            "roi_percent": roi,
            "evidence_state": evidence_state,
            "evidence_references_complete": all_refs,
            "positive_net_benefit": bool(net > 0),
            "verified_savings": False,
        },
        "evidence_ledger": {
            "baseline_reference": base_ref,
            "post_intervention_reference": post_ref,
            "implementation_cost_reference": cost_ref,
            "reviewer_name": verifier,
            "user_marked_reviewed": bool(evidence_reviewed),
        },
    }
