"""Independent golden tests for Shoir-IE unit and currency conversion."""

import math

import pytest

from shoir_unit_converter import convert_currency, convert_units


def test_length_conversion_matches_exact_factor():
    result = convert_units(2.5, "km", "m")
    assert result["status"] == "COMPLETED"
    assert result["dimension"] == "Length"
    assert result["output_value"] == 2500.0
    assert "base unit" in result["method"]


def test_mass_conversion_matches_known_pound_factor():
    result = convert_units(1, "kg", "lb")
    assert result["output_value"] == pytest.approx(2.2046226218, abs=1e-9)


@pytest.mark.parametrize(
    ("value", "source", "target", "expected"),
    [(0, "°C", "°F", 32.0), (100, "°C", "°F", 212.0), (273.15, "K", "°C", 0.0)],
)
def test_temperature_conversion_uses_affine_transform(value, source, target, expected):
    assert convert_units(value, source, target)["output_value"] == pytest.approx(expected, abs=1e-9)


def test_ratio_conversion_percent_to_fraction():
    assert convert_units(62.5, "%", "fraction")["output_value"] == pytest.approx(0.625)


@pytest.mark.parametrize(
    ("value", "source", "target"),
    [
        (1, "km", "kg"),
        (1, "made-up", "m"),
        (1, "m", "made-up"),
        (float("nan"), "m", "km"),
        (float("inf"), "m", "km"),
    ],
)
def test_unit_conversion_rejects_invalid_or_incompatible_inputs(value, source, target):
    with pytest.raises(ValueError):
        convert_units(value, source, target)


def test_currency_conversion_records_user_rate_date_and_source():
    result = convert_currency(
        100, "USD", "SAR", 3.75, "2026-10-23", "Approved finance rate sheet v4"
    )
    assert result["output_value"] == 375.0
    assert result["rate"] == 3.75
    assert result["rate_date"] == "2026-10-23"
    assert result["rate_source"] == "Approved finance rate sheet v4"
    assert "Not a live quote" in result["warnings"][0]


def test_same_currency_does_not_require_an_exchange_rate():
    result = convert_currency(19.25, "sar", "SAR", None)
    assert result["output_value"] == 19.25
    assert result["rate"] == 1.0
    assert result["rate_date"] is None


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ((100, "USD", "SAR", None, "2026-10-23", "source"), "rate is required"),
        ((100, "USD", "SAR", 0, "2026-10-23", "source"), "greater than zero"),
        ((100, "USD", "SAR", -1, "2026-10-23", "source"), "greater than zero"),
        ((100, "USD", "SAR", float("nan"), "2026-10-23", "source"), "finite"),
        ((100, "US", "SAR", 3.75, "2026-10-23", "source"), "three-letter"),
        ((100, "USD", "SAR", 3.75, "not-a-date", "source"), "YYYY-MM-DD"),
        ((100, "USD", "SAR", 3.75, "2026-02-30", "source"), "calendar date"),
        ((100, "USD", "SAR", 3.75, "2026-10-23", ""), "source"),
    ],
)
def test_currency_conversion_rejects_missing_invalid_or_untraceable_rate(args, message):
    with pytest.raises(ValueError, match=message):
        convert_currency(*args)


def test_currency_conversion_rejects_nonfinite_result():
    with pytest.raises(ValueError, match="non-finite"):
        convert_currency(1e308, "USD", "SAR", 1e308, "2026-10-23", "source")
