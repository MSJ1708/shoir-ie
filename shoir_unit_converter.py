"""Deterministic engineering unit and explicitly sourced currency conversion.

This module never fetches or guesses exchange rates. Currency conversion requires
the caller to provide a positive target-per-source rate, its date, and a source.
"""

from __future__ import annotations

import math
import re
from typing import Any

# Each unit maps to (dimension, factor_to_base, additive_offset_to_base).
# For all physical dimensions except temperature: base = value * factor + offset.
_UNIT_DEFINITIONS: dict[str, tuple[str, float, float]] = {
    # Length; base = metre
    "m": ("Length", 1.0, 0.0),
    "km": ("Length", 1000.0, 0.0),
    "cm": ("Length", 0.01, 0.0),
    "mm": ("Length", 0.001, 0.0),
    "in": ("Length", 0.0254, 0.0),
    "ft": ("Length", 0.3048, 0.0),
    "yd": ("Length", 0.9144, 0.0),
    "mi": ("Length", 1609.344, 0.0),
    # Mass; base = kilogram
    "kg": ("Mass", 1.0, 0.0),
    "g": ("Mass", 0.001, 0.0),
    "mg": ("Mass", 0.000001, 0.0),
    "t": ("Mass", 1000.0, 0.0),
    "lb": ("Mass", 0.45359237, 0.0),
    "oz": ("Mass", 0.028349523125, 0.0),
    # Time; base = second
    "s": ("Time", 1.0, 0.0),
    "min": ("Time", 60.0, 0.0),
    "h": ("Time", 3600.0, 0.0),
    "day": ("Time", 86400.0, 0.0),
    # Temperature; base = kelvin
    "°C": ("Temperature", 1.0, 273.15),
    "°F": ("Temperature", 5.0 / 9.0, 273.15 - 32.0 * 5.0 / 9.0),
    "K": ("Temperature", 1.0, 0.0),
    # Pressure; base = pascal
    "Pa": ("Pressure", 1.0, 0.0),
    "kPa": ("Pressure", 1000.0, 0.0),
    "MPa": ("Pressure", 1_000_000.0, 0.0),
    "bar": ("Pressure", 100_000.0, 0.0),
    "psi": ("Pressure", 6894.757293168, 0.0),
    # Volume; base = cubic metre
    "m³": ("Volume", 1.0, 0.0),
    "L": ("Volume", 0.001, 0.0),
    "mL": ("Volume", 0.000001, 0.0),
    "US gal": ("Volume", 0.003785411784, 0.0),
    # Speed; base = metres per second
    "m/s": ("Speed", 1.0, 0.0),
    "km/h": ("Speed", 1.0 / 3.6, 0.0),
    "mph": ("Speed", 0.44704, 0.0),
    # Energy; base = joule
    "J": ("Energy", 1.0, 0.0),
    "kJ": ("Energy", 1000.0, 0.0),
    "MJ": ("Energy", 1_000_000.0, 0.0),
    "Wh": ("Energy", 3600.0, 0.0),
    "kWh": ("Energy", 3_600_000.0, 0.0),
    # Power; base = watt
    "W": ("Power", 1.0, 0.0),
    "kW": ("Power", 1000.0, 0.0),
    "MW": ("Power", 1_000_000.0, 0.0),
    # Dimensionless ratio; base = fraction
    "fraction": ("Ratio", 1.0, 0.0),
    "%": ("Ratio", 0.01, 0.0),
}

UNIT_OPTIONS: dict[str, tuple[str, ...]] = {
    dimension: tuple(unit for unit, definition in _UNIT_DEFINITIONS.items() if definition[0] == dimension)
    for dimension in dict.fromkeys(definition[0] for definition in _UNIT_DEFINITIONS.values())
}


def _finite_number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a valid number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite; NaN and infinity are not supported.")
    return result


def convert_units(value: float, from_unit: str, to_unit: str) -> dict[str, Any]:
    """Convert compatible physical units and return formula/provenance metadata."""
    source = str(from_unit or "").strip()
    target = str(to_unit or "").strip()
    if source not in _UNIT_DEFINITIONS:
        raise ValueError(f"Unsupported source unit: {source or '(empty)'}.")
    if target not in _UNIT_DEFINITIONS:
        raise ValueError(f"Unsupported target unit: {target or '(empty)'}.")
    source_dimension, source_factor, source_offset = _UNIT_DEFINITIONS[source]
    target_dimension, target_factor, target_offset = _UNIT_DEFINITIONS[target]
    if source_dimension != target_dimension:
        raise ValueError(
            f"Incompatible dimensions: {source} is {source_dimension}, while "
            f"{target} is {target_dimension}. Choose units from the same dimension."
        )
    numeric = _finite_number(value, "Value")
    base_value = numeric * source_factor + source_offset
    converted = (base_value - target_offset) / target_factor
    if not math.isfinite(converted):
        raise ValueError("The conversion produced a non-finite result.")
    return {
        "status": "COMPLETED",
        "input_value": numeric,
        "output_value": round(converted, 10),
        "from_unit": source,
        "to_unit": target,
        "dimension": source_dimension,
        "method": "Convert source value to the dimension's base unit, then to the target unit.",
        "formula": f"base = value × {source_factor!r} + {source_offset!r}; target = (base − {target_offset!r}) / {target_factor!r}",
        "rounding": "Output rounded to 10 decimal places for display; source value is preserved.",
        "provenance": "Deterministic built-in SI/conventional conversion definitions; no external data.",
        "warnings": [],
    }


def convert_currency(
    amount: float,
    from_currency: str,
    to_currency: str,
    target_per_source_rate: float | None,
    rate_date: str = "",
    rate_source: str = "",
) -> dict[str, Any]:
    """Convert currency only using a caller-provided, dated, attributable rate.

    The rate definition is: 1 unit of source currency = rate units of target
    currency. This function performs arithmetic only; it does not validate the
    market accuracy of the supplied rate.
    """
    source = str(from_currency or "").strip().upper()
    target = str(to_currency or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", source):
        raise ValueError("Source currency must be a three-letter ISO-style code.")
    if not re.fullmatch(r"[A-Z]{3}", target):
        raise ValueError("Target currency must be a three-letter ISO-style code.")
    numeric_amount = _finite_number(amount, "Amount")
    if source == target:
        return {
            "status": "COMPLETED",
            "input_value": numeric_amount,
            "output_value": round(numeric_amount, 10),
            "from_currency": source,
            "to_currency": target,
            "rate": 1.0,
            "rate_date": None,
            "rate_source": "Not required: source and target currencies are identical.",
            "formula": "target_amount = source_amount",
            "provenance": "Identity conversion; no exchange rate was used.",
            "warnings": [],
        }
    if target_per_source_rate is None:
        raise ValueError("A user-supplied exchange rate is required for different currencies.")
    rate = _finite_number(target_per_source_rate, "Exchange rate")
    if rate <= 0:
        raise ValueError("Exchange rate must be greater than zero.")
    date_value = str(rate_date or "").strip()
    source_value = str(rate_source or "").strip()
    if not date_value:
        raise ValueError("Enter the date the exchange rate applies to.")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
        raise ValueError("Rate date must use YYYY-MM-DD format.")
    from datetime import date
    try:
        date.fromisoformat(date_value)
    except ValueError as exc:
        raise ValueError("Rate date is not a valid calendar date.") from exc
    if not source_value:
        raise ValueError("Enter the exchange-rate source (for example, your approved finance feed or a source URL/name).")
    converted = numeric_amount * rate
    if not math.isfinite(converted):
        raise ValueError("The conversion produced a non-finite result.")
    return {
        "status": "COMPLETED",
        "input_value": numeric_amount,
        "output_value": round(converted, 10),
        "from_currency": source,
        "to_currency": target,
        "rate": rate,
        "rate_date": date_value,
        "rate_source": source_value,
        "formula": f"target_amount = source_amount × target_per_source_rate = {numeric_amount!r} × {rate!r}",
        "provenance": "User-supplied exchange rate; source/date are recorded, but market accuracy is not independently verified.",
        "warnings": ["Not a live quote. Confirm rate, fees, and accounting policy with your approved source."],
    }
