import numpy as np
import pandas as pd

from shoir_experiment_engine import (
    full_factorial_design,
    factorial_effects,
    bootstrap_statistic,
    bootstrap_group_effect,
    monte_carlo_uncertainty,
    replication_summary,
    sensitivity_table,
)


def test_full_factorial_design_and_effects():
    design = full_factorial_design({"A": [-1, 1], "B": [0, 10]})
    assert len(design) == 4
    design["Response"] = 10 + 2 * design["A"] + 0.5 * design["B"]
    effects, summary = factorial_effects(design, "Response", ["A", "B"], bootstrap=100, seed=7)
    assert set(["A", "B"]).issubset(set(effects["Term"]))
    assert summary["n"] == 4
    assert np.isfinite(effects["Effect"]).all()


def test_bootstrap_and_group_effect_are_reproducible():
    values = [1, 2, 3, 4, 5, 6]
    a, draws_a = bootstrap_statistic(values, replicates=300, seed=11)
    b, draws_b = bootstrap_statistic(values, replicates=300, seed=11)
    assert a["Estimate"] == b["Estimate"]
    assert draws_a.equals(draws_b)

    df = pd.DataFrame({"Group":["A"]*5 + ["B"]*5, "Y":[1,2,3,4,5,6,7,8,9,10]})
    summary, dist = bootstrap_group_effect(df, "Group", "Y", "A", "B", replicates=200, seed=3)
    assert summary["Cohen d"] < 0
    assert len(dist) == 200


def test_monte_carlo_replication_and_sensitivity():
    specs = {
        "Demand": {"mean":100, "std":5, "weight":1, "distribution":"Normal"},
        "Capacity": {"mean":110, "std":4, "weight":-1, "distribution":"Uniform"},
    }
    s1, d1 = monte_carlo_uncertainty(specs, runs=500, seed=5)
    s2, d2 = monte_carlo_uncertainty(specs, runs=500, seed=5)
    assert s1 == s2
    assert d1.equals(d2)

    rep = pd.DataFrame({
        "Scenario":["A"]*4+["B"]*4,
        "Replication":[1,2,3,4]*2,
        "Response":[10,11,9,10,20,19,21,20],
        "Driver":[1,2,3,4,5,6,7,8],
    })
    summary = replication_summary(rep, "Response", scenario_col="Scenario", replication_col="Replication")
    assert set(summary["Scenario"]) == {"A","B"}
    sens = sensitivity_table(rep, "Response", ["Driver"])
    assert not sens.empty
