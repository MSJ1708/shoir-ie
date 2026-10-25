"""Hand-checkable continuous LP and solver-status fixtures for T062."""
import pandas as pd
import pytest

from shoir_100_tool_solver_diagnostics import solve_and_diagnose_linear_program


def variables():
    return pd.DataFrame([
        {"variable":"x","objective_coefficient":3.0,"lower_bound":0.0,"upper_bound":None},
        {"variable":"y","objective_coefficient":2.0,"lower_bound":0.0,"upper_bound":None},
    ])


def test_feasible_lp_matches_hand_solution_and_recomputes_slacks():
    cons=pd.DataFrame([
        {"constraint_id":"C1","sense":"<=","rhs":4.0,"x":1.0,"y":1.0},
        {"constraint_id":"C2","sense":"<=","rhs":2.0,"x":1.0,"y":0.0},
        {"constraint_id":"C3","sense":"<=","rhs":3.0,"x":0.0,"y":1.0},
    ])
    result=solve_and_diagnose_linear_program(variables(),cons,objective_sense="maximize")
    assert result["status"]=="OPTIMAL"
    values=result["variables"].set_index("variable")["value"]
    assert values["x"]==pytest.approx(2)
    assert values["y"]==pytest.approx(2)
    assert result["objective_value"]==pytest.approx(10)
    assert result["metrics"]["constraints_satisfied"] is True
    assert set(result["constraint_diagnostics"]["status"])=={"SATISFIED"}


def test_infeasible_and_unbounded_states_are_not_falsely_reported_as_optimal():
    infeasible=pd.DataFrame([
        {"constraint_id":"lower","sense":">=","rhs":2.0,"x":1.0,"y":0.0},
        {"constraint_id":"upper","sense":"<=","rhs":1.0,"x":1.0,"y":0.0},
    ])
    result=solve_and_diagnose_linear_program(variables(),infeasible)
    assert result["status"]=="INFEASIBLE"
    assert result["objective_value"] is None
    assert result["metrics"]["optimal"] is False

    unbounded_vars=pd.DataFrame([{"variable":"x","objective_coefficient":1.0,"lower_bound":0.0,"upper_bound":None}])
    unbounded_cons=pd.DataFrame(columns=["constraint_id","sense","rhs","x"])
    unbounded=solve_and_diagnose_linear_program(unbounded_vars,unbounded_cons,objective_sense="maximize")
    assert unbounded["status"]=="UNBOUNDED"
    assert unbounded["objective_value"] is None


def test_solver_diagnostics_reject_invalid_names_senses_and_bounds():
    with pytest.raises(ValueError,match="cannot exceed"):
        solve_and_diagnose_linear_program(pd.DataFrame([{"variable":"x","objective_coefficient":1,"lower_bound":5,"upper_bound":2}]),
                                          pd.DataFrame(columns=["constraint_id","sense","rhs","x"]))
    with pytest.raises(ValueError,match="sense must be"):
        solve_and_diagnose_linear_program(variables(),pd.DataFrame([{"constraint_id":"C1","sense":"~=","rhs":1,"x":1,"y":1}]))
    with pytest.raises(ValueError,match="unique"):
        solve_and_diagnose_linear_program(pd.DataFrame([{"variable":"x","objective_coefficient":1,"lower_bound":0,"upper_bound":None},{"variable":"X","objective_coefficient":2,"lower_bound":0,"upper_bound":None}]),
                                          pd.DataFrame(columns=["constraint_id","sense","rhs","x","X"]))
