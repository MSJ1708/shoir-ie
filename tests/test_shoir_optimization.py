import numpy as np
import pandas as pd

from shoir_optimization import (
    solve_linear_program,
    solve_quadratic_program,
    solve_robust_linear_program,
    solve_stochastic_linear_program,
    pareto_weight_sweep,
)


def test_lp_and_quadratic_solve():
    lp = solve_linear_program([1, 2], A_ub=[[-1, -1]], b_ub=[-4], bounds=[(0,None),(0,None)])
    assert lp["success"]
    assert np.isclose(lp["objective"], 4.0, atol=1e-6)

    qp = solve_quadratic_program([1, 2], [[1,0],[0,1]], A_ub=[[-1,-1]], b_ub=[-4], bounds=[(0,None),(0,None)])
    assert qp["success"]
    assert np.isfinite(qp["objective"])


def test_robust_stochastic_and_pareto():
    scenarios = [[1,2],[2,1],[1.5,1.5]]
    robust = solve_robust_linear_program(scenarios, A_ub=[[-1,-1]], b_ub=[-1], bounds=[(0,None),(0,None)])
    assert robust["success"]
    stochastic = solve_stochastic_linear_program(scenarios, probabilities=[0.5,0.3,0.2], risk_aversion=0.5, bounds=[(0,None),(0,None)])
    assert stochastic["success"]

    df = pd.DataFrame({"Scenario":["A","B","C"],"Cost":[10,8,9],"Carbon":[5,7,4],"Service":[95,96,94]})
    out = pareto_weight_sweep(df, ["Cost","Carbon"], weights=[0.5,0.5], minimize=[True,True])
    assert "Pareto Candidate" in out.columns
    assert out["Pareto Candidate"].any()
