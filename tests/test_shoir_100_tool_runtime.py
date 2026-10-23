import csv
import io
import math

import pytest

pd = pytest.importorskip("pandas")

from shoir_100_tool_runtime import (
    carbon_emissions,
    clean_dataframe,
    convert_unit,
    engineering_economics,
    generate_synthetic_industrial_data,
    inventory_policy,
    monte_carlo_triangular,
    mtbf_mttr,
    oee,
    process_capability,
    profile_dataframe,
    read_dataset_bytes,
    result_to_csv_bytes,
    takt_capacity,
    time_study,
    work_sampling,
)


def test_time_study_golden_case():
    result = time_study([10, 12, 11], rating_percent=110, allowance_percent=15, unit="s")
    assert result["metrics"]["mean_observed_time"] == pytest.approx(11)
    assert result["metrics"]["normal_time"] == pytest.approx(12.1)
    assert result["metrics"]["standard_time"] == pytest.approx(12.1 / 0.85)


def test_work_sampling_confidence_interval_fixture():
    result = work_sampling(30, 100, 1.96)
    assert result["metrics"]["proportion"] == pytest.approx(0.3)
    assert result["metrics"]["ci_low"] == pytest.approx(0.210183, abs=1e-5)
    assert result["metrics"]["ci_high"] == pytest.approx(0.389817, abs=1e-5)


def test_takt_capacity_golden_case():
    result = takt_capacity(480, 120, "min")
    assert result["metrics"]["takt_time"] == pytest.approx(4)
    assert result["metrics"]["theoretical_capacity"] == pytest.approx(120)


def test_oee_golden_case_and_loss_consistency():
    result = oee(480, 60, 0.5, 600, 570, "min")
    m = result["metrics"]
    assert m["availability"] == pytest.approx(0.875)
    assert m["performance"] == pytest.approx(300 / 420)
    assert m["quality"] == pytest.approx(0.95)
    assert m["oee"] == pytest.approx(0.59375)
    assert [item["value"] for item in result["chart"]][-1] == pytest.approx(100 * m["oee"])


def test_process_capability_golden_case():
    result = process_capability([9, 10, 11], 8, 12)
    assert result["metrics"]["mean"] == pytest.approx(10)
    assert result["metrics"]["sample_std"] == pytest.approx(1)
    assert result["metrics"]["cp"] == pytest.approx(2 / 3)
    assert result["metrics"]["cpk"] == pytest.approx(2 / 3)
    assert result["metrics"]["pp"] == pytest.approx(result["metrics"]["cp"])


def test_mtbf_mttr_golden_case_and_zero_failures():
    result = mtbf_mttr(100, 10, 3)
    assert result["metrics"]["uptime_hours"] == pytest.approx(90)
    assert result["metrics"]["mtbf_hours"] == pytest.approx(30)
    assert result["metrics"]["mttr_hours"] == pytest.approx(10 / 3)
    zero = mtbf_mttr(100, 10, 0)
    assert zero["metrics"]["mtbf_hours"] is None
    assert zero["warnings"]


def test_inventory_policy_golden_case():
    result = inventory_policy(10000, 50, 2, 40, 5, daily_demand_std=0, service_z=1.65, working_days=250)
    assert result["metrics"]["eoq_units"] == pytest.approx(math.sqrt(500000))
    assert result["metrics"]["reorder_point_units"] == pytest.approx(200)
    assert result["metrics"]["safety_stock_units"] == pytest.approx(0)


def test_monte_carlo_is_reproducible_and_bounded():
    a = monte_carlo_triangular(0, 10, 20, iterations=1000, seed=13)
    b = monte_carlo_triangular(0, 10, 20, iterations=1000, seed=13)
    assert a["metrics"] == b["metrics"]
    assert 0 <= a["metrics"]["p05"] <= a["metrics"]["p50"] <= a["metrics"]["p95"] <= 20
    assert a["metrics"]["iterations"] == 1000


def test_carbon_estimate_and_factor_provenance_warning():
    result = carbon_emissions(1000, 0.5, activity_unit="kWh", emission_unit="kg CO2e")
    assert result["metrics"]["estimated_emissions"] == pytest.approx(500)
    assert result["warnings"]


def test_npv_irr_and_discounted_payback_golden_case():
    result = engineering_economics([-100, 60, 60], 10)
    assert result["metrics"]["npv"] == pytest.approx(-100 + 60 / 1.1 + 60 / 1.1**2)
    assert result["metrics"]["irr_percent"] == pytest.approx(13.066238, abs=1e-4)
    assert result["metrics"]["discounted_payback_period"] == pytest.approx(1.9166667, abs=0.01)


def test_unit_converter_rejects_incompatible_units():
    result = convert_unit(5, "ft", "m")
    assert result["metrics"]["output_value"] == pytest.approx(1.524)
    with pytest.raises(ValueError):
        convert_unit(1, "kg", "min")


def test_synthetic_data_reproducible_and_labeled():
    a = generate_synthetic_industrial_data(10, 42)
    b = generate_synthetic_industrial_data(10, 42)
    assert a["records"] == b["records"]
    assert a["status"] == "SYNTHETIC"
    assert len(a["records"]) == 10
    assert a["source_fingerprint"] == b["source_fingerprint"]


def test_profile_and_reversible_cleaning_do_not_mutate_source():
    source = pd.DataFrame({"x": [1, 1, None, 4], "area": ["A", "A", "B", "C"]})
    original = source.copy(deep=True)
    profile = profile_dataframe(source)
    assert profile["metrics"]["row_count"] == 4
    assert profile["metrics"]["duplicate_rows"] == 1
    assert profile["metrics"]["missing_cells"] == 1
    candidate, audit = clean_dataframe(source, drop_duplicates=True, missing_strategy="fill_median")
    assert len(candidate) == 3
    assert audit["removed_duplicate_rows"] == 1
    assert audit["imputed_numeric_cells"] == 1
    pd.testing.assert_frame_equal(source, original)


def test_csv_export_is_reopenable_and_contains_method_and_fingerprint():
    result = takt_capacity(480, 120)
    payload = result_to_csv_bytes(result).decode("utf-8-sig")
    parsed = list(csv.DictReader(io.StringIO(payload)))
    assert parsed
    assert parsed[0]["tool_id"] == "T023"
    assert parsed[0]["metric"] == "available_time"
    assert parsed[0]["method"]
    assert parsed[0]["source_fingerprint"] == result["source_fingerprint"]


@pytest.mark.parametrize("args", [
    ([0, 0], 100, 10, "s"),
    ([1, 2], 100, 100, "s"),
])
def test_time_study_rejects_invalid_inputs(args):
    with pytest.raises(ValueError):
        time_study(*args)


def test_oee_rejects_zero_denominators_and_impossible_counts():
    with pytest.raises(ValueError):
        oee(480, 480, 0.5, 600, 570)
    with pytest.raises(ValueError):
        oee(480, 60, 0.5, 10, 11)


def test_capability_rejects_invalid_specs_and_constant_data():
    with pytest.raises(ValueError):
        process_capability([1, 1, 1], 0, 2)
    with pytest.raises(ValueError):
        process_capability([1, 2], 3, 2)


def test_inventory_and_simulation_reject_invalid_ranges():
    with pytest.raises(ValueError):
        inventory_policy(100, 0, 1, 2, 3)
    with pytest.raises(ValueError):
        monte_carlo_triangular(10, 5, 20, 1000, 7)


def test_bad_dataset_upload_is_rejected_and_csv_parses():
    parsed = read_dataset_bytes("sample.csv", b"station,count\nA,2\nB,3\n")
    assert parsed.shape == (2, 2)
    with pytest.raises(ValueError):
        read_dataset_bytes("sample.txt", b"x")
    with pytest.raises(ValueError):
        read_dataset_bytes("corrupt.xlsx", b"not a real workbook")
