"""A narrowly scoped implementation of the Revised NIOSH Lifting Equation (RNLE).

This function supports one two-handed lifting task only. It is a screening aid,
not a certified ergonomic assessment or an automated determination that a task
is safe. Method constants and lookup tables are attributed to the NIOSH
Applications Manual, DHHS (NIOSH) Publication 94-110, revised September 2021.
"""
from __future__ import annotations

import math
from typing import Any

NIOSH_RNLE_SOURCE = (
    "https://www.cdc.gov/niosh/docs/94-110/"
)
NIOSH_RNLE_METHOD_VERSION = (
    "Revised NIOSH Lifting Equation (RNLE), Applications Manual 94-110, revised 2021"
)

# NIOSH Table 5 and Table 7 express the vertical boundary as 30 inches.
NIOSH_VERTICAL_CATEGORY_BOUNDARY_CM = 76.2

# Table 5: FM rows indexed by frequency. Columns are grouped by duration:
# <=1h, >1 to <=2h, >2 to <=8h; each duration has V<30 in and V>=30 in.
# The vertical boundary is 30 inches (76.2 cm), as footnoted in NIOSH 94-110 (2021).
_FREQUENCY_ROWS: tuple[tuple[float, tuple[float, float, float, float, float, float]], ...] = (
    (0.2, (1.00, 1.00, 0.95, 0.95, 0.85, 0.85)),
    (0.5, (0.97, 0.97, 0.92, 0.92, 0.81, 0.81)),
    (1.0, (0.94, 0.94, 0.88, 0.88, 0.75, 0.75)),
    (2.0, (0.91, 0.91, 0.84, 0.84, 0.65, 0.65)),
    (3.0, (0.88, 0.88, 0.79, 0.79, 0.55, 0.55)),
    (4.0, (0.84, 0.84, 0.72, 0.72, 0.45, 0.45)),
    (5.0, (0.80, 0.80, 0.60, 0.60, 0.35, 0.35)),
    (6.0, (0.75, 0.75, 0.50, 0.50, 0.27, 0.27)),
    (7.0, (0.70, 0.70, 0.42, 0.42, 0.22, 0.22)),
    (8.0, (0.60, 0.60, 0.35, 0.35, 0.18, 0.18)),
    (9.0, (0.52, 0.52, 0.30, 0.30, 0.00, 0.15)),
    (10.0, (0.45, 0.45, 0.26, 0.26, 0.00, 0.13)),
    (11.0, (0.41, 0.41, 0.00, 0.23, 0.00, 0.00)),
    (12.0, (0.37, 0.37, 0.00, 0.21, 0.00, 0.00)),
    (13.0, (0.00, 0.34, 0.00, 0.00, 0.00, 0.00)),
    (14.0, (0.00, 0.31, 0.00, 0.00, 0.00, 0.00)),
    (15.0, (0.00, 0.28, 0.00, 0.00, 0.00, 0.00)),
)


def _finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number.")
    return number


def _duration_column(duration_hours: float) -> int:
    if not 0 < duration_hours <= 8:
        raise ValueError("Continuous lifting duration must be greater than 0 and no more than 8 hours.")
    if duration_hours <= 1:
        return 0
    if duration_hours <= 2:
        return 2
    return 4


def _frequency_multiplier(
    frequency_lifts_per_minute: float,
    duration_hours: float,
    vertical_origin_cm: float,
) -> tuple[float, float, list[str]]:
    """Return interpolated FM, table frequency, and transparent guidance notes."""
    if frequency_lifts_per_minute <= 0:
        raise ValueError("Lifting frequency must be greater than zero lifts/minute.")
    if frequency_lifts_per_minute > 15:
        raise ValueError(
            "The NIOSH frequency table gives a zero multiplier above 15 lifts/minute; "
            "this single-task calculator cannot return a positive recommended weight limit."
        )

    notes: list[str] = []
    table_frequency = max(0.2, frequency_lifts_per_minute)
    if frequency_lifts_per_minute < 0.2:
        notes.append(
            "NIOSH Table 5 uses 0.2 lifts/minute when observed frequency is lower than 0.2."
        )
    if frequency_lifts_per_minute < 0.1:
        notes.append(
            "For very infrequent lifting (<0.1 lifts/minute), confirm the recovery-period and "
            "duration treatment with the NIOSH manual or a qualified ergonomist."
        )

    column = _duration_column(duration_hours)
    # Table 5 boundary is V < 30 in versus V >= 30 in (30 in = 76.2 cm),
    # evaluated at the origin, not at a 75 cm rounded boundary.
    column += 0 if vertical_origin_cm < NIOSH_VERTICAL_CATEGORY_BOUNDARY_CM else 1

    if table_frequency > 15:
        fm = 0.0
    else:
        fm = 0.0
        for row_index, (rate, values) in enumerate(_FREQUENCY_ROWS):
            if math.isclose(table_frequency, rate, rel_tol=0.0, abs_tol=1e-12):
                fm = values[column]
                break
            if table_frequency < rate:
                lower_rate, lower_values = _FREQUENCY_ROWS[row_index - 1]
                upper_rate, upper_values = rate, values
                fraction = (table_frequency - lower_rate) / (upper_rate - lower_rate)
                fm = lower_values[column] + fraction * (upper_values[column] - lower_values[column])
                break
        else:
            fm = 0.0

    if not math.isfinite(fm) or fm <= 0:
        raise ValueError(
            "The applicable NIOSH frequency-table multiplier is zero for these inputs. "
            "No positive recommended weight limit is produced; obtain a qualified assessment."
        )
    return float(fm), float(table_frequency), notes


def _horizontal_multiplier(horizontal_cm: float, endpoint: str) -> float:
    if not 0 <= horizontal_cm <= 63:
        raise ValueError(
            f"{endpoint} horizontal hand distance must be between 0 and 63 cm for RNLE applicability."
        )
    return 1.0 if horizontal_cm <= 25 else 25.0 / horizontal_cm


def _vertical_multiplier(vertical_cm: float, endpoint: str) -> float:
    if not 0 <= vertical_cm <= 175:
        raise ValueError(f"{endpoint} vertical hand height must be between 0 and 175 cm.")
    return 1.0 - 0.003 * abs(vertical_cm - 75.0)


def _asymmetric_multiplier(angle_degrees: float, endpoint: str) -> float:
    if not 0 <= angle_degrees <= 135:
        raise ValueError(f"{endpoint} asymmetry angle must be between 0 and 135 degrees.")
    return 1.0 - 0.0032 * angle_degrees


def _coupling_multiplier(coupling_quality: str, vertical_cm: float) -> float:
    quality = str(coupling_quality or "").strip().casefold()
    if quality not in {"good", "fair", "poor"}:
        raise ValueError("Coupling quality must be Good, Fair, or Poor.")
    if quality == "good":
        return 1.0
    if quality == "fair":
        return 0.95 if vertical_cm < NIOSH_VERTICAL_CATEGORY_BOUNDARY_CM else 1.0
    return 0.90


def calculate_rnle_lifting_index(
    *,
    load_kg: float,
    horizontal_origin_cm: float,
    horizontal_destination_cm: float,
    vertical_origin_cm: float,
    vertical_destination_cm: float,
    asymmetry_origin_degrees: float,
    asymmetry_destination_degrees: float,
    frequency_lifts_per_minute: float,
    duration_hours: float,
    coupling_quality: str,
    applicability_confirmed: bool,
) -> dict[str, Any]:
    """Calculate origin/destination RWL and the single-task RNLE lifting index.

    FM is linearly interpolated as NIOSH directs when frequency falls between
    frequency-table rows. CM is calculated from coupling quality and endpoint
    vertical location. The task RWL is the lower endpoint RWL; LI = load/RWL.

    The function intentionally does not claim to cover multiple distinct tasks,
    one-handed/seated/kneeling lifts, carrying, unstable loads, or other tasks
    outside RNLE applicability.
    """
    if applicability_confirmed is not True:
        raise ValueError(
            "Confirm the task matches the supported single, two-handed standing-lift RNLE scope before calculating."
        )

    load = _finite_number("Load weight", load_kg)
    h_origin = _finite_number("Origin horizontal distance", horizontal_origin_cm)
    h_destination = _finite_number("Destination horizontal distance", horizontal_destination_cm)
    v_origin = _finite_number("Origin vertical height", vertical_origin_cm)
    v_destination = _finite_number("Destination vertical height", vertical_destination_cm)
    a_origin = _finite_number("Origin asymmetry angle", asymmetry_origin_degrees)
    a_destination = _finite_number("Destination asymmetry angle", asymmetry_destination_degrees)
    frequency = _finite_number("Lifting frequency", frequency_lifts_per_minute)
    duration = _finite_number("Lifting duration", duration_hours)

    if load <= 0:
        raise ValueError("Load weight must be greater than zero kg.")
    if not 0 <= v_origin <= 175 or not 0 <= v_destination <= 175:
        raise ValueError("Origin and destination vertical heights must each be between 0 and 175 cm.")

    travel_cm = abs(v_destination - v_origin)
    if travel_cm > 175:
        raise ValueError("Vertical travel distance cannot exceed 175 cm for this RNLE screening.")

    # NIOSH sets distances under 25 cm to 25 cm for the distance multiplier.
    distance_used_cm = max(25.0, travel_cm)
    dm = min(1.0, 0.82 + 4.5 / distance_used_cm)
    fm, table_frequency, warnings = _frequency_multiplier(frequency, duration, v_origin)

    endpoint_inputs = (
        ("origin", h_origin, v_origin, a_origin),
        ("destination", h_destination, v_destination, a_destination),
    )
    endpoint_results: dict[str, dict[str, float]] = {}
    for endpoint, horizontal_cm, vertical_cm, angle_degrees in endpoint_inputs:
        hm = _horizontal_multiplier(horizontal_cm, endpoint)
        vm = _vertical_multiplier(vertical_cm, endpoint)
        am = _asymmetric_multiplier(angle_degrees, endpoint)
        cm = _coupling_multiplier(coupling_quality, vertical_cm)
        rwl = 23.0 * hm * vm * dm * am * fm * cm
        if not math.isfinite(rwl) or rwl <= 0:
            raise ValueError(f"RNLE produced a non-positive recommended weight limit at the {endpoint}.")
        endpoint_results[endpoint] = {
            "horizontal_multiplier": hm,
            "vertical_multiplier": vm,
            "distance_multiplier": dm,
            "asymmetric_multiplier": am,
            "frequency_multiplier": fm,
            "coupling_multiplier": cm,
            "recommended_weight_limit_kg": rwl,
        }

    limiting_endpoint = min(
        endpoint_results,
        key=lambda name: endpoint_results[name]["recommended_weight_limit_kg"],
    )
    rwl_task = endpoint_results[limiting_endpoint]["recommended_weight_limit_kg"]
    lifting_index = load / rwl_task
    if lifting_index > 1:
        interpretation = (
            "The entered load exceeds the computed single-task recommended weight limit. "
            "Review task redesign options with a qualified ergonomics professional."
        )
    else:
        interpretation = (
            "The entered load is at or below the computed single-task recommended weight limit. "
            "This does not establish that the task is risk-free or suitable for every worker."
        )

    warnings.extend(
        [
            "Single-task RNLE screening only; multiple-task index analysis is not implemented here.",
            "Requires accurate field measurements and correct coupling/duration classification.",
            "Not a medical determination, site safety certification, or substitute for qualified ergonomic review.",
        ]
    )
    return {
        "status": "CALCULATED_SCREENING",
        "method": NIOSH_RNLE_METHOD_VERSION,
        "source": NIOSH_RNLE_SOURCE,
        "formula": "RWL = 23 kg × HM × VM × DM × AM × FM × CM; LI = load / lower endpoint RWL.",
        "actual_load_kg": load,
        "vertical_travel_cm": travel_cm,
        "distance_used_for_DM_cm": distance_used_cm,
        "frequency_observed_lifts_per_minute": frequency,
        "frequency_used_for_table_lifts_per_minute": table_frequency,
        "duration_hours": duration,
        "coupling_quality": str(coupling_quality).strip().title(),
        "frequency_multiplier": fm,
        "endpoint_results": endpoint_results,
        "limiting_endpoint": limiting_endpoint,
        "recommended_weight_limit_kg": rwl_task,
        "lifting_index": lifting_index,
        "interpretation": interpretation,
        "warnings": warnings,
        "data_provenance": "USER_ENTERED_UNVERIFIED",
        "limitations": [
            "Only one distinct two-handed standing lifting task is supported.",
            "RNLE does not cover every lifting situation; review the official manual's applicability conditions.",
            "Outputs are screening estimates; a value alone cannot identify whether a task is hazardous.",
        ],
    }


__all__ = [
    "NIOSH_RNLE_SOURCE",
    "NIOSH_RNLE_METHOD_VERSION",
    "NIOSH_VERTICAL_CATEGORY_BOUNDARY_CM",
    "calculate_rnle_lifting_index",
]
