from __future__ import annotations

import math

import pytest

from shoir_tier_capabilities import tier_allows

from shoir_100_tool_hub import (
    CALCULATOR_IDS,
    calculate_carbon_emissions,
    binomial_acceptance_probability,
    calculate_acceptance_sampling_plan,
    calculate_quality_cost,
    calculate_portfolio_scores,
    calculate_two_group_sample_size,
    calculate_economics,
    calculate_inventory_policy,
    calculate_mtbf_mttr,
    calculate_oee,
    calculate_process_capability,
    calculate_takt_capacity,
    calculate_time_study,
    calculate_work_sampling,
    load_tool_registry,
    parse_numeric_values,
)


def test_registry_has_100_stable_unique_ids_and_valid_statuses():
    rows = load_tool_registry()
    assert len(rows) == 100
    assert {row["tool_id"] for row in rows} == {f"T{i:03d}" for i in range(1, 101)}
    assert len({row["canonical_name"] for row in rows}) == 100
    assert all(row["implementation_status"] for row in rows)
    assert set(CALCULATOR_IDS).issubset({row["tool_id"] for row in rows})


def test_parse_numeric_values_rejects_bad_and_non_finite_data():
    assert parse_numeric_values("1, 2.5\n3;4") == [1.0, 2.5, 3.0, 4.0]
    with pytest.raises(ValueError, match="non-numeric"):
        parse_numeric_values("1, no, 3")
    with pytest.raises(ValueError, match="NaN or infinity"):
        parse_numeric_values("1, nan")
    with pytest.raises(ValueError, match="at least one"):
        parse_numeric_values(" , ; \n")


def test_calculate_time_study_golden_case():
    result = calculate_time_study([10, 11, 9, 10.5, 10], 110, 15)
    assert result["observed_mean"] == pytest.approx(10.1)
    assert result["normal_time"] == pytest.approx(11.11)
    assert result["standard_time"] == pytest.approx(13.0705882353)
    assert result["unit"] == "same time unit as observations"
    with pytest.raises(ValueError, match="below 100"):
        calculate_time_study([10, 11], 100, 100)


def test_calculate_work_sampling_golden_case():
    result = calculate_work_sampling(15, 50)
    assert result["proportion"] == pytest.approx(0.3)
    assert result["wilson_lower"] == pytest.approx(0.191, abs=0.002)
    assert result["wilson_upper"] == pytest.approx(0.438, abs=0.002)
    assert result["warnings"] == []
    assert calculate_work_sampling(2, 10)["warnings"]


def test_calculate_takt_capacity_golden_case_and_invalid_denominators():
    result = calculate_takt_capacity(420, 210, 1.8)
    assert result["takt_time"] == pytest.approx(2)
    assert result["theoretical_capacity"] == pytest.approx(233.3333333333)
    assert result["capacity_minus_demand"] == pytest.approx(23.3333333333)
    with pytest.raises(ValueError, match="Demand"):
        calculate_takt_capacity(420, 0, 1.8)
    with pytest.raises(ValueError, match="Cycle time"):
        calculate_takt_capacity(420, 210, 0)


def test_calculate_oee_golden_case():
    result = calculate_oee(90, 85, 98)
    assert result["oee_percent"] == pytest.approx(74.97)
    assert result["formula"].startswith("OEE")
    with pytest.raises(ValueError, match="must not exceed 100"):
        calculate_oee(101, 90, 98)


def test_calculate_process_capability_golden_case_separates_overall_and_within_sigma():
    values = [9.98, 10.00, 10.02, 10.01, 9.99]
    result = calculate_process_capability(values, 9.95, 10.05)
    assert result["Pp"] == pytest.approx(1.0540925534)
    assert result["Ppk"] == pytest.approx(1.0540925534)
    assert "Cp" not in result and "Cpk" not in result
    with_sigma = calculate_process_capability(values, 9.95, 10.05, 0.01)
    assert with_sigma["Cp"] == pytest.approx(1.6666666667)
    assert with_sigma["Cpk"] == pytest.approx(1.6666666667)
    with pytest.raises(ValueError, match="less than"):
        calculate_process_capability(values, 10.1, 10.0)


def test_calculate_mtbf_mttr_golden_case():
    result = calculate_mtbf_mttr(500, [2, 1.5, 3])
    assert result["failure_count"] == 3
    assert result["mtbf_hours"] == pytest.approx(500 / 3)
    assert result["mttr_hours"] == pytest.approx(6.5 / 3)
    with pytest.raises(ValueError, match="at least one"):
        calculate_mtbf_mttr(500, [])


def test_calculate_inventory_policy_golden_case():
    result = calculate_inventory_policy(10000, 75, 3.5, 32, 6, 80)
    assert result["eoq_units"] == pytest.approx(654.6536707)
    assert result["reorder_point_units"] == pytest.approx(272)
    assert result["lead_time_demand_units"] == pytest.approx(192)
    with pytest.raises(ValueError, match="Holding cost"):
        calculate_inventory_policy(10000, 75, 0, 32, 6, 80)


def test_calculate_carbon_emissions_requires_factor_provenance():
    result = calculate_carbon_emissions(5000, 0.42, "Example factor source", "2026-10-23")
    assert result["emissions_kg_co2e"] == pytest.approx(2100)
    assert result["emissions_t_co2e"] == pytest.approx(2.1)
    with pytest.raises(ValueError, match="source"):
        calculate_carbon_emissions(5000, 0.42, "", "2026-10-23")
    with pytest.raises(ValueError, match="date"):
        calculate_carbon_emissions(5000, 0.42, "Example source", "")


def test_calculate_economics_golden_case_and_irr_root():
    cash_flows = [80000, 90000, 100000, 110000]
    result = calculate_economics(250000, cash_flows, 10)
    expected_npv = -250000 + sum(cf / (1.1 ** year) for year, cf in enumerate(cash_flows, start=1))
    assert result["npv"] == pytest.approx(expected_npv, abs=0.01)
    assert result["npv"] == pytest.approx(47370.41, abs=0.02)
    assert result["simple_payback_years"] == pytest.approx(2.8)
    assert result["irr_percent"] is not None
    irr = result["irr_percent"] / 100
    independent_irr_npv = -250000 + sum(cf / ((1 + irr) ** year) for year, cf in enumerate(cash_flows, start=1))
    assert independent_irr_npv == pytest.approx(0, abs=0.01)
    with pytest.raises(ValueError, match="nonnegative"):
        calculate_economics(100, [200, -10], 5)



def test_100_tool_tier_truth_table_covers_all_six_packages_independently():
    rows = load_tool_registry()
    ordinary = {
        "Starter": 0,
        "Mid-Tier Pro": 1,
        "Professional": 2,
        "Enterprise": 3,
        "Enterprise Plus": 4,
    }
    packages = ["Starter", "Mid-Tier Pro", "Professional", "Enterprise", "Enterprise Plus", "Research Pack"]

    def expected_allow(current, required):
        if required == "Research Pack":
            return current == "Research Pack"
        if current == "Research Pack":
            return required in ordinary and ordinary[required] <= ordinary["Enterprise"]
        return required in ordinary and ordinary[current] >= ordinary[required]

    assert len(rows) == 100
    for row in rows:
        required = row["target_minimum_tier"]
        assert required in set(ordinary) | {"Research Pack"}
        for current in packages:
            assert tier_allows(current, required) is expected_allow(current, required), (
                row["tool_id"], row["canonical_name"], current, required
            )

    # Explicitly preserve the add-on boundary in both directions.
    assert not tier_allows("Research Pack", "Enterprise Plus")
    assert not tier_allows("Enterprise Plus", "Research Pack")
    assert tier_allows("Research Pack", "Enterprise")



def test_binomial_acceptance_probability_golden_cases():
    assert binomial_acceptance_probability(5, 0, 0.1) == pytest.approx(0.9**5)
    assert binomial_acceptance_probability(5, 1, 0.1) == pytest.approx(0.91854)
    assert binomial_acceptance_probability(10, 10, 0.25) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="between zero and sample size"):
        binomial_acceptance_probability(5, 6, 0.1)


def test_acceptance_sampling_plan_meets_both_risk_constraints():
    result = calculate_acceptance_sampling_plan(1.0, 10.0, 5.0, 10.0, 500)
    assert 1 <= result["sample_size"] <= 500
    assert 0 <= result["acceptance_number"] < result["sample_size"]
    assert result["producer_risk_actual_percent"] <= 5.0 + 1e-8
    assert result["consumer_risk_actual_percent"] <= 10.0 + 1e-8
    assert result["rejection_number"] == result["acceptance_number"] + 1
    with pytest.raises(ValueError, match="AQL must be below LTPD"):
        calculate_acceptance_sampling_plan(10.0, 1.0)
    with pytest.raises(ValueError, match="No single-sampling plan"):
        calculate_acceptance_sampling_plan(1.0, 2.0, 0.1, 0.1, 1)


def test_quality_cost_reconciles_explicit_nonoverlapping_categories():
    result = calculate_quality_cost(1000, 50, 20, 30, 10, 5, 200)
    assert result["scrap_cost"] == pytest.approx(200)
    assert result["rework_cost"] == pytest.approx(150)
    assert result["internal_failure_cost"] == pytest.approx(350)
    assert result["cost_of_poor_quality_included_costs"] == pytest.approx(550)
    assert result["copq_per_unit_produced"] == pytest.approx(0.55)
    assert result["defect_rate_percent"] == pytest.approx(5.0)
    with pytest.raises(ValueError, match="non-overlapping"):
        calculate_quality_cost(1000, 50, 30, 30, 10, 5, 200)
    with pytest.raises(ValueError, match="cannot exceed"):
        calculate_quality_cost(10, 11, 1, 0, 2, 1, 0)


def test_portfolio_score_uses_normalized_visible_weights():
    result = calculate_portfolio_scores(
        {
            "Automation": {"Safety": 90, "Cost": 60},
            "Training": {"Safety": 70, "Cost": 90},
        },
        {"Safety": 70, "Cost": 30},
    )
    ranking = result["ranking"].set_index("Project")
    assert ranking.loc["Automation", "Weighted score (0-100)"] == pytest.approx(81.0)
    assert ranking.loc["Training", "Weighted score (0-100)"] == pytest.approx(76.0)
    assert ranking.loc["Automation", "Rank"] == 1
    assert sum(result["normalized_weights_percent"].values()) == pytest.approx(100)
    with pytest.raises(ValueError, match="missing scores"):
        calculate_portfolio_scores({"Automation": {"Safety": 50}}, {"Safety": 50, "Cost": 50})


def test_two_group_sample_size_normal_approximation_golden_case():
    result = calculate_two_group_sample_size(0.5, 0.05, 0.80)
    assert result["sample_size_per_group_approx"] == 63
    assert result["total_sample_size_approx"] == 126
    with pytest.raises(ValueError, match="effect size"):
        calculate_two_group_sample_size(0, 0.05, 0.8)
