"""Golden and boundary tests for standard time, work sampling, and takt/capacity."""

import math

import pytest

from shoir_ie_basic_calculators import (
    calculate_standard_time,
    calculate_takt_capacity,
    calculate_work_sampling,
)


def test_standard_time_uses_explicit_rating_and_allowance_convention():
    # Mean observed=10 min; normal=10*1.10=11; standard=11/(1-.15)
    result = calculate_standard_time([9, 10, 11], "min", 110, 15)
    assert result["mean_observed_time"] == pytest.approx(10)
    assert result["normal_time"] == pytest.approx(11)
    assert result["standard_time"] == pytest.approx(11 / 0.85)
    assert result["time_unit"] == "min"
    assert "fraction of standard time" in result["assumptions"][2]


def test_standard_time_single_observation_discloses_variability_limit():
    result = calculate_standard_time([4.0], "s", 100, 0)
    assert result["standard_time"] == 4
    assert result["sample_standard_deviation"] == 0
    assert result["warnings"]


@pytest.mark.parametrize(
    ("observations", "unit", "rating", "allowance"),
    [
        ([], "min", 100, 15),
        ([1, 0], "min", 100, 15),
        ([1, -1], "min", 100, 15),
        ([1, float("nan")], "min", 100, 15),
        ([1], "unknown", 100, 15),
        ([1], "min", 0, 15),
        ([1], "min", 201, 15),
        ([1], "min", 100, 100),
        ([1], "min", 100, -1),
    ],
)
def test_standard_time_rejects_invalid_observations_and_parameters(observations, unit, rating, allowance):
    with pytest.raises(ValueError):
        calculate_standard_time(observations, unit, rating, allowance)


def test_work_sampling_wilson_interval_and_required_sample_size():
    result = calculate_work_sampling(40, 100, confidence_percent=95, target_margin_percent=5)
    assert result["activity_proportion"] == pytest.approx(0.4)
    assert result["wilson_interval_lower_percent"] < 40
    assert result["wilson_interval_upper_percent"] > 40
    assert result["conservative_required_sample_size"] == 385
    assert result["additional_observations_suggested"] == 285
    assert result["warnings"]


def test_work_sampling_boundary_counts_are_bounded_and_warned():
    result = calculate_work_sampling(0, 100, 95, 5)
    assert result["activity_percent"] == 0
    assert 0 <= result["wilson_interval_lower_percent"] <= result["wilson_interval_upper_percent"]
    assert any("does not prove" in warning for warning in result["warnings"])


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ((-1, 10, 95, 5), "between zero"),
        ((11, 10, 95, 5), "between zero"),
        ((1, 0, 95, 5), "greater than zero"),
        ((1.5, 10, 95, 5), "integers"),
        ((1, 10, 50, 5), "greater than 50%"),
        ((1, 10, 95, 0), "greater than 0%"),
        ((1, 10, float("nan"), 5), "finite"),
    ],
)
def test_work_sampling_rejects_invalid_counts_and_parameters(args, message):
    with pytest.raises(ValueError, match=message):
        calculate_work_sampling(*args)


def test_takt_and_capacity_convert_mixed_time_units():
    result = calculate_takt_capacity(
        demand_units=480,
        demand_period="one shift",
        available_time=8,
        available_time_unit="h",
        planned_unavailable_time=30,
        unavailable_time_unit="min",
        cycle_time=0.9,
        cycle_time_unit="min",
        takt_output_unit="min",
    )
    assert result["net_available_time_seconds"] == 7.5 * 3600
    assert result["takt_time"] == pytest.approx(0.9375)
    assert result["capacity_units_per_period"] == pytest.approx(500)
    assert result["capacity_margin_units"] == pytest.approx(20)
    assert result["capacity_feasible"] is True


def test_takt_without_cycle_time_does_not_claim_capacity_feasibility():
    result = calculate_takt_capacity(400, "shift", 480, "min", 30, "min")
    assert result["takt_time"] == pytest.approx(1.125)
    assert result["capacity_units_per_period"] is None
    assert result["capacity_feasible"] is None
    assert result["warnings"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"demand_units": 0}, "Demand must be greater"),
        ({"available_time": 0}, "Available time must be greater"),
        ({"planned_unavailable_time": 480}, "must be less than available time"),
        ({"planned_unavailable_time": -1}, "cannot be negative"),
        ({"available_time_unit": "kg"}, "supported time units"),
        ({"cycle_time": 0}, "Cycle time must be greater"),
        ({"cycle_time_unit": "units"}, "supported time units"),
        ({"demand_period": ""}, "Specify the period"),
    ],
)
def test_takt_rejects_invalid_units_durations_and_demand(kwargs, message):
    inputs = {
        "demand_units": 100,
        "demand_period": "one shift",
        "available_time": 480,
        "available_time_unit": "min",
        "planned_unavailable_time": 30,
        "unavailable_time_unit": "min",
        "cycle_time": 1,
        "cycle_time_unit": "min",
        "takt_output_unit": "min",
    }
    inputs.update(kwargs)
    with pytest.raises(ValueError, match=message):
        calculate_takt_capacity(**inputs)


def test_takt_flags_insufficient_theoretical_capacity():
    result = calculate_takt_capacity(
        500, "one shift", 8, "h", 30, "min", 1.0, "min", "min"
    )
    assert result["capacity_units_per_period"] == pytest.approx(450)
    assert result["capacity_feasible"] is False
    assert result["capacity_margin_units"] == pytest.approx(-50)
