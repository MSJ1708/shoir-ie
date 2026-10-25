"""Golden and boundary fixtures for the single-task NIOSH RNLE screening engine."""
from __future__ import annotations

import pytest

from shoir_ergonomics import calculate_rnle_lifting_index


def _ideal_inputs(**overrides):
    inputs = {
        "load_kg": 23.0,
        "horizontal_origin_cm": 25.0,
        "horizontal_destination_cm": 25.0,
        "vertical_origin_cm": 75.0,
        "vertical_destination_cm": 75.0,
        "asymmetry_origin_degrees": 0.0,
        "asymmetry_destination_degrees": 0.0,
        "frequency_lifts_per_minute": 0.2,
        "duration_hours": 1.0,
        "coupling_quality": "Good",
        "applicability_confirmed": True,
    }
    inputs.update(overrides)
    return inputs


def test_rnle_ideal_single_task_reproduces_23kg_load_constant_fixture():
    result = calculate_rnle_lifting_index(**_ideal_inputs())

    assert result["status"] == "CALCULATED_SCREENING"
    assert result["recommended_weight_limit_kg"] == pytest.approx(23.0)
    assert result["lifting_index"] == pytest.approx(1.0)
    assert result["limiting_endpoint"] in {"origin", "destination"}
    assert result["endpoint_results"]["origin"]["frequency_multiplier"] == pytest.approx(1.0)
    assert result["endpoint_results"]["destination"]["coupling_multiplier"] == pytest.approx(1.0)
    assert result["distance_used_for_DM_cm"] == pytest.approx(25.0)
    assert result["data_provenance"] == "USER_ENTERED_UNVERIFIED"
    assert any("not a medical determination" in warning for warning in result["warnings"])


def test_rnle_interpolates_frequency_and_uses_lower_endpoint_weight_limit():
    result = calculate_rnle_lifting_index(
        **_ideal_inputs(
            load_kg=15,
            horizontal_destination_cm=50,
            vertical_destination_cm=100,
            asymmetry_destination_degrees=30,
            frequency_lifts_per_minute=2.5,
        )
    )

    # NIOSH Table 5 FM at 2.5 lifts/min for <=1 h is halfway between
    # 2/min (0.91) and 3/min (0.88), i.e. 0.895.
    assert result["frequency_multiplier"] == pytest.approx(0.895)
    assert result["endpoint_results"]["origin"]["recommended_weight_limit_kg"] == pytest.approx(20.585)
    expected_destination = 23 * 0.5 * 0.925 * 1.0 * 0.904 * 0.895 * 1.0
    assert result["endpoint_results"]["destination"]["recommended_weight_limit_kg"] == pytest.approx(expected_destination)
    assert result["limiting_endpoint"] == "destination"
    assert result["recommended_weight_limit_kg"] == pytest.approx(expected_destination)
    assert result["lifting_index"] == pytest.approx(15 / expected_destination)
    assert result["lifting_index"] > 1


def test_rnle_coupling_multiplier_uses_each_endpoint_vertical_height():
    result = calculate_rnle_lifting_index(
        **_ideal_inputs(
            load_kg=10,
            vertical_origin_cm=60,
            vertical_destination_cm=90,
            coupling_quality="Fair",
            frequency_lifts_per_minute=1,
        )
    )

    assert result["endpoint_results"]["origin"]["coupling_multiplier"] == pytest.approx(0.95)
    assert result["endpoint_results"]["destination"]["coupling_multiplier"] == pytest.approx(1.0)
    assert result["frequency_multiplier"] == pytest.approx(0.94)


def test_rnle_uses_minimum_table_frequency_when_observed_frequency_is_below_point_two():
    result = calculate_rnle_lifting_index(
        **_ideal_inputs(frequency_lifts_per_minute=0.1, duration_hours=2)
    )
    assert result["frequency_used_for_table_lifts_per_minute"] == pytest.approx(0.2)
    assert result["frequency_multiplier"] == pytest.approx(0.95)
    assert any("uses 0.2 lifts/minute" in warning for warning in result["warnings"])
    assert any("recovery-period" in warning for warning in result["warnings"])


def test_rnle_requires_confirmed_applicability_and_rejects_invalid_boundaries():
    with pytest.raises(ValueError, match="Confirm the task"):
        calculate_rnle_lifting_index(**_ideal_inputs(applicability_confirmed=False))
    with pytest.raises(ValueError, match="greater than zero kg"):
        calculate_rnle_lifting_index(**_ideal_inputs(load_kg=0))
    with pytest.raises(ValueError, match="horizontal hand distance"):
        calculate_rnle_lifting_index(**_ideal_inputs(horizontal_origin_cm=63.1))
    with pytest.raises(ValueError, match="vertical heights"):
        calculate_rnle_lifting_index(**_ideal_inputs(vertical_destination_cm=176))
    with pytest.raises(ValueError, match="asymmetry angle"):
        calculate_rnle_lifting_index(**_ideal_inputs(asymmetry_destination_degrees=136))
    with pytest.raises(ValueError, match="duration"):
        calculate_rnle_lifting_index(**_ideal_inputs(duration_hours=8.1))
    with pytest.raises(ValueError, match="above 15 lifts/minute"):
        calculate_rnle_lifting_index(**_ideal_inputs(frequency_lifts_per_minute=15.1))


def test_rnle_rejects_zero_frequency_multiplier_instead_of_returning_fake_success():
    with pytest.raises(ValueError, match="frequency-table multiplier is zero"):
        calculate_rnle_lifting_index(
            **_ideal_inputs(
                vertical_origin_cm=20,
                frequency_lifts_per_minute=13,
                duration_hours=1,
            )
        )

def test_rnle_uses_exact_30_inch_vertical_cutoff_for_frequency_and_coupling_tables():
    # NIOSH Table 5/7 use a 30-inch boundary (76.2 cm), not 75 cm.
    with pytest.raises(ValueError, match="frequency-table multiplier is zero"):
        calculate_rnle_lifting_index(
            **_ideal_inputs(
                vertical_origin_cm=76.1,
                vertical_destination_cm=76.1,
                frequency_lifts_per_minute=11,
                duration_hours=2,
                coupling_quality="Fair",
            )
        )

    result = calculate_rnle_lifting_index(
        **_ideal_inputs(
            vertical_origin_cm=76.2,
            vertical_destination_cm=76.2,
            frequency_lifts_per_minute=11,
            duration_hours=2,
            coupling_quality="Fair",
        )
    )
    assert result["frequency_multiplier"] == pytest.approx(0.23)
    assert result["endpoint_results"]["origin"]["coupling_multiplier"] == pytest.approx(1.0)
    assert result["endpoint_results"]["destination"]["coupling_multiplier"] == pytest.approx(1.0)

