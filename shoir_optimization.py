"""Reusable optimization engines for Shoir-IE.

Includes LP, quadratic/nonlinear, robust LP, stochastic LP and Pareto helpers.
The existing production MILP network solver remains untouched and can continue
to use PuLP; these engines fill the adjacent optimization method gaps.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, linprog, minimize


def solve_linear_program(
    c: Sequence[float],
    *,
    A_ub: Sequence[Sequence[float]] | None = None,
    b_ub: Sequence[float] | None = None,
    A_eq: Sequence[Sequence[float]] | None = None,
    b_eq: Sequence[float] | None = None,
    bounds: Sequence[tuple[float | None, float | None]] | None = None,
) -> dict[str, Any]:
    c_arr = np.asarray(c, dtype=float)
    if c_arr.ndim != 1 or c_arr.size == 0:
        raise ValueError("Objective coefficients must be a non-empty vector.")
    result = linprog(
        c_arr,
        A_ub=np.asarray(A_ub, dtype=float) if A_ub is not None else None,
        b_ub=np.asarray(b_ub, dtype=float) if b_ub is not None else None,
        A_eq=np.asarray(A_eq, dtype=float) if A_eq is not None else None,
        b_eq=np.asarray(b_eq, dtype=float) if b_eq is not None else None,
        bounds=list(bounds) if bounds is not None else [(0, None)] * len(c_arr),
        method="highs",
    )
    return {
        "status": "Optimal" if bool(result.success) else str(result.message),
        "success": bool(result.success),
        "objective": float(result.fun) if result.success else float("nan"),
        "variables": np.asarray(result.x, dtype=float) if result.success else np.full(len(c_arr), np.nan),
        "message": str(result.message),
        "iterations": int(getattr(result, "nit", 0) or 0),
    }


def solve_quadratic_program(
    linear: Sequence[float],
    quadratic: Sequence[Sequence[float]],
    *,
    A_ub: Sequence[Sequence[float]] | None = None,
    b_ub: Sequence[float] | None = None,
    A_eq: Sequence[Sequence[float]] | None = None,
    b_eq: Sequence[float] | None = None,
    bounds: Sequence[tuple[float | None, float | None]] | None = None,
    x0: Sequence[float] | None = None,
) -> dict[str, Any]:
    c = np.asarray(linear, dtype=float)
    Q = np.asarray(quadratic, dtype=float)
    if Q.shape != (len(c), len(c)):
        raise ValueError("Quadratic matrix shape must match the objective vector.")
    if bounds is None:
        bounds = [(0.0, None)] * len(c)
    x_init = np.asarray(x0 if x0 is not None else [max(0.0, float((lo or 0.0))) for lo, _ in bounds], dtype=float)
    if len(x_init) != len(c):
        x_init = np.zeros(len(c))
    constraints = []
    if A_ub is not None and b_ub is not None:
        constraints.append(LinearConstraint(np.asarray(A_ub,float), -np.inf, np.asarray(b_ub,float)))
    if A_eq is not None and b_eq is not None:
        beq=np.asarray(b_eq,float)
        constraints.append(LinearConstraint(np.asarray(A_eq,float), beq, beq))
    def objective(x: np.ndarray) -> float:
        return float(c @ x + 0.5 * x @ Q @ x)
    result = minimize(objective, x_init, method="SLSQP", bounds=Bounds(
        np.asarray([(-np.inf if lo is None else lo) for lo,_ in bounds],float),
        np.asarray([(np.inf if hi is None else hi) for _,hi in bounds],float),
    ), constraints=constraints, options={"maxiter":2000,"ftol":1e-9})
    return {
        "status": "Optimal" if bool(result.success) else str(result.message),
        "success": bool(result.success),
        "objective": float(result.fun),
        "variables": np.asarray(result.x, dtype=float),
        "message": str(result.message),
        "iterations": int(getattr(result,"nit",0) or 0),
    }


def solve_robust_linear_program(
    scenario_objectives: Sequence[Sequence[float]],
    *,
    A_ub: Sequence[Sequence[float]] | None = None,
    b_ub: Sequence[float] | None = None,
    A_eq: Sequence[Sequence[float]] | None = None,
    b_eq: Sequence[float] | None = None,
    bounds: Sequence[tuple[float | None, float | None]] | None = None,
) -> dict[str, Any]:
    scenarios = np.asarray(scenario_objectives, dtype=float)
    if scenarios.ndim != 2 or scenarios.shape[0] < 2:
        raise ValueError("Robust optimization requires at least two scenario objective vectors.")
    n = scenarios.shape[1]
    # Add t as the last variable and enforce c_s*x <= t for every scenario.
    robust_A = []
    robust_b = []
    for c in scenarios:
        row = np.r_[c, -1.0]
        robust_A.append(row)
        robust_b.append(0.0)
    if A_ub is not None and b_ub is not None:
        for row,b in zip(np.asarray(A_ub,float),np.asarray(b_ub,float)):
            robust_A.append(np.r_[row,0.0]); robust_b.append(float(b))
    robust_bounds = list(bounds) if bounds is not None else [(0.0,None)]*n
    robust_bounds.append((None,None))
    c_t = np.r_[np.zeros(n), 1.0]
    result = linprog(c_t,A_ub=np.asarray(robust_A,float),b_ub=np.asarray(robust_b,float),A_eq=np.c_[np.asarray(A_eq,float),np.zeros(len(A_eq))] if A_eq is not None else None,b_eq=b_eq,bounds=robust_bounds,method="highs")
    return {
        "status":"Optimal" if bool(result.success) else str(result.message),
        "success":bool(result.success),
        "worst_case_objective":float(result.x[-1]) if result.success else float("nan"),
        "objective":float(result.fun) if result.success else float("nan"),
        "variables":np.asarray(result.x[:-1],float) if result.success else np.full(n,np.nan),
        "scenario_objectives":scenarios,
        "message":str(result.message),
    }


def solve_stochastic_linear_program(
    scenario_objectives: Sequence[Sequence[float]],
    probabilities: Sequence[float] | None = None,
    risk_aversion: float = 0.0,
    *,
    A_ub: Sequence[Sequence[float]] | None = None,
    b_ub: Sequence[float] | None = None,
    A_eq: Sequence[Sequence[float]] | None = None,
    b_eq: Sequence[float] | None = None,
    bounds: Sequence[tuple[float | None, float | None]] | None = None,
) -> dict[str, Any]:
    """Sample-average stochastic objective with a risk penalty proxy."""
    scenarios=np.asarray(scenario_objectives,dtype=float)
    if scenarios.ndim != 2 or scenarios.shape[0] < 2: raise ValueError("Need at least two stochastic scenarios.")
    probs=np.asarray(probabilities if probabilities is not None else np.full(scenarios.shape[0],1.0/scenarios.shape[0]),dtype=float)
    if len(probs)!=len(scenarios) or probs.sum()<=0: raise ValueError("Scenario probabilities are invalid.")
    probs=probs/probs.sum()
    expected=np.sum(scenarios*probs[:,None],axis=0)
    sd=np.sqrt(np.sum(((scenarios-expected)**2)*probs[:,None],axis=0))
    effective=expected+float(max(0.0,risk_aversion))*sd
    result=solve_linear_program(effective,A_ub=A_ub,b_ub=b_ub,A_eq=A_eq,b_eq=b_eq,bounds=bounds)
    result.update({"expected_coefficients":expected,"scenario_std":sd,"risk_aversion":float(risk_aversion),"probabilities":probs})
    return result


def pareto_weight_sweep(
    objectives: pd.DataFrame,
    objective_columns: Sequence[str],
    *,
    weights: Sequence[float] | None = None,
    minimize: Sequence[bool] | None = None,
) -> pd.DataFrame:
    cols=[str(c) for c in objective_columns]
    if not cols or not set(cols).issubset(objectives.columns): raise ValueError("Objective columns not found.")
    d=objectives.copy()
    mins=list(minimize if minimize is not None else [True]*len(cols))
    if len(mins)!=len(cols): raise ValueError("minimize must match objective count.")
    normalized={}
    for c,mn in zip(cols,mins):
        x=pd.to_numeric(d[c],errors="coerce")
        lo,hi=x.min(),x.max()
        norm=(x-lo)/(hi-lo) if hi>lo else pd.Series(np.zeros(len(x)),index=x.index)
        normalized[c]=(norm if mn else 1-norm).fillna(1.0)
    if weights is None: weights=[1.0/len(cols)]*len(cols)
    w=np.asarray(weights,float)
    if len(w)!=len(cols) or w.sum()<=0: raise ValueError("weights must match objectives and sum positive.")
    w=w/w.sum()
    d["Composite Score"]=sum(float(wi)*normalized[c] for wi,c in zip(w,cols))
    d["Pareto Candidate"]=True
    values=d[cols].to_numpy(dtype=float)
    for i in range(len(d)):
        for j in range(len(d)):
            if i==j: continue
            better=True; strict=False
            for k in range(len(cols)):
                if mins[k]:
                    if values[j,k] > values[i,k]: better=False; break
                    if values[j,k] < values[i,k]: strict=True
                else:
                    if values[j,k] < values[i,k]: better=False; break
                    if values[j,k] > values[i,k]: strict=True
            if better and strict:
                d.loc[d.index[i],"Pareto Candidate"]=False
                break
    return d.sort_values(["Pareto Candidate","Composite Score"],ascending=[False,True]).reset_index(drop=True)
