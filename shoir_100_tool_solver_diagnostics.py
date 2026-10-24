"""Bounded linear-program solver diagnostics for Shoir-IE target T062.

This target runs a continuous LP via SciPy/HiGHS and reports solver states and
constraint residuals. It does not claim a mixed-integer solution, IIS, or a
conflict explanation unsupported by the installed solver result.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import linprog


def solve_and_diagnose_linear_program(
    variables: pd.DataFrame,
    constraints: pd.DataFrame,
    *,
    objective_sense: str = "maximize",
) -> dict[str, Any]:
    if not isinstance(variables, pd.DataFrame) or variables.empty:
        raise ValueError("At least one decision variable is required.")
    if variables.columns.has_duplicates:
        raise ValueError("Variable table must have unique column names.")
    var_fields = {"variable", "objective_coefficient", "lower_bound", "upper_bound"}
    missing = sorted(var_fields - set(variables.columns))
    if missing:
        raise ValueError("Variable table is missing columns: " + ", ".join(missing))
    sense = str(objective_sense or "").strip().lower()
    if sense not in {"minimize", "maximize"}:
        raise ValueError("Objective sense must be minimize or maximize.")
    names = [str(v).strip() for v in variables["variable"]]
    if any(not n for n in names) or len({n.casefold() for n in names}) != len(names):
        raise ValueError("Variable names must be non-empty and unique.")
    if not all(name.replace("_", "").isalnum() for name in names):
        raise ValueError("Variable names may contain only letters, digits and underscores.")

    objective, bounds = [], []
    for i, raw in enumerate(variables.to_dict(orient="records"), start=1):
        try:
            coeff = float(raw["objective_coefficient"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Variable row {i} objective coefficient must be numeric.") from exc
        if not math.isfinite(coeff):
            raise ValueError(f"Variable row {i} objective coefficient must be finite.")
        objective.append(coeff)
        parsed_bounds = []
        for field in ("lower_bound", "upper_bound"):
            value = raw.get(field)
            if value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == "":
                parsed_bounds.append(None)
            else:
                try:
                    number = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Variable row {i} {field} must be numeric or blank.") from exc
                if not math.isfinite(number):
                    raise ValueError(f"Variable row {i} {field} must be finite or blank.") from None
                parsed_bounds.append(number)
        lower, upper = parsed_bounds
        if lower is not None and upper is not None and lower > upper:
            raise ValueError(f"Variable row {i} lower_bound cannot exceed upper_bound.")
        bounds.append((lower, upper))

    if not isinstance(constraints, pd.DataFrame):
        constraints = pd.DataFrame(list(constraints))
    if constraints.columns.has_duplicates:
        raise ValueError("Constraint table must have unique column names.")
    required = {"constraint_id", "sense", "rhs", *names}
    missing = sorted(required - set(constraints.columns))
    if missing and not constraints.empty:
        raise ValueError("Constraint table is missing columns: " + ", ".join(missing))
    if len(constraints) > 1000:
        raise ValueError("Linear-program diagnostics are limited to 1000 constraints.")
    if constraints.empty and not set(["constraint_id", "sense", "rhs", *names]).issubset(set(constraints.columns)):
        # Empty UI table still needs all editable column names.
        constraints = pd.DataFrame(columns=["constraint_id", "sense", "rhs", *names])

    c = np.asarray(objective, dtype=float)
    solver_c = -c if sense == "maximize" else c
    a_ub, b_ub, ids_ub = [], [], []
    a_eq, b_eq, ids_eq = [], [], []
    original_rows = []
    seen_ids = set()
    for i, raw in enumerate(constraints.to_dict(orient="records"), start=1):
        cid = str(raw.get("constraint_id", "") or "").strip()
        if not cid:
            raise ValueError(f"Constraint row {i} requires a constraint_id.")
        if cid.casefold() in seen_ids:
            raise ValueError(f"Duplicate constraint ID '{cid}'.")
        seen_ids.add(cid.casefold())
        constraint_sense = str(raw.get("sense", "") or "").strip()
        if constraint_sense not in {"<=", ">=", "="}:
            raise ValueError(f"Constraint row {i} sense must be <=, >= or =.")
        try:
            rhs = float(raw.get("rhs"))
            coefficients = np.asarray([float(raw.get(name)) for name in names], dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Constraint row {i} coefficients and RHS must be numeric and complete.") from exc
        if not math.isfinite(rhs) or not np.isfinite(coefficients).all():
            raise ValueError(f"Constraint row {i} coefficients and RHS must be finite.")
        lhs = coefficients.tolist()
        original_rows.append({"constraint_id": cid, "sense": constraint_sense, "rhs": rhs, **dict(zip(names, lhs))})
        if constraint_sense == "<=":
            a_ub.append(coefficients); b_ub.append(rhs); ids_ub.append(cid)
        elif constraint_sense == ">=":
            a_ub.append(-coefficients); b_ub.append(-rhs); ids_ub.append(cid)
        else:
            a_eq.append(coefficients); b_eq.append(rhs); ids_eq.append(cid)

    result = linprog(
        solver_c,
        A_ub=np.asarray(a_ub, dtype=float) if a_ub else None,
        b_ub=np.asarray(b_ub, dtype=float) if b_ub else None,
        A_eq=np.asarray(a_eq, dtype=float) if a_eq else None,
        b_eq=np.asarray(b_eq, dtype=float) if b_eq else None,
        bounds=bounds,
        method="highs",
    )
    status_map = {
        0: "OPTIMAL",
        1: "LIMIT_REACHED",
        2: "INFEASIBLE",
        3: "UNBOUNDED",
        4: "SOLVER_ERROR",
    }
    status = status_map.get(int(result.status), "UNKNOWN_SOLVER_STATUS")
    message = str(result.message or "").strip()
    if status != "OPTIMAL" or result.x is None or not np.isfinite(result.x).all():
        warnings = []
        if status == "INFEASIBLE":
            warnings.append("The supplied constraints and bounds are infeasible. No irreducible infeasible set (IIS) is fabricated by this helper.")
        elif status == "UNBOUNDED":
            warnings.append("The objective is unbounded under the supplied constraints/bounds. Add valid limits if appropriate.")
        elif status == "LIMIT_REACHED":
            warnings.append("The solver reached a limit; no optimal value is claimed.")
        else:
            warnings.append("The solver did not return an optimal solution; inspect the status/message and simplify or validate the model.")
        return {
            "tool_id": "T062",
            "status": status,
            "method": "Continuous linear programming via SciPy linprog / HiGHS",
            "solver_name": "HiGHS (through SciPy linprog)",
            "solver_status_code": int(result.status),
            "solver_message": message,
            "objective_sense": sense,
            "objective_value": None,
            "variables": pd.DataFrame(columns=["variable", "value"]),
            "constraint_diagnostics": pd.DataFrame(columns=["constraint_id", "lhs", "sense", "rhs", "slack_or_residual", "status"]),
            "warnings": warnings,
            "assumptions": [
                "Variables are continuous; integer/binary restrictions are not supported by this target.",
                "No IIS or infeasibility explanation is emitted unless a solver specifically returns supported diagnostic data.",
            ],
            "metrics": {"variable_count": int(len(names)), "constraint_count": int(len(constraints)), "optimal": False},
        }

    x = np.asarray(result.x, dtype=float)
    objective_value = float(c @ x)
    variable_table = pd.DataFrame({"variable": names, "value": x, "objective_coefficient": c})
    diagnostic_rows = []
    for raw in original_rows:
        lhs_value = sum(float(raw[name]) * float(x[ix]) for ix, name in enumerate(names))
        rhs = float(raw["rhs"])
        sense_value = str(raw["sense"])
        if sense_value == "<=":
            slack = rhs - lhs_value
            state = "SATISFIED" if slack >= -1e-7 else "VIOLATED"
        elif sense_value == ">=":
            slack = lhs_value - rhs
            state = "SATISFIED" if slack >= -1e-7 else "VIOLATED"
        else:
            slack = lhs_value - rhs
            state = "SATISFIED" if abs(slack) <= 1e-7 else "VIOLATED"
        diagnostic_rows.append({"constraint_id": raw["constraint_id"], "lhs": lhs_value, "sense": sense_value,
                                "rhs": rhs, "slack_or_residual": slack, "status": state})
    diagnostics = pd.DataFrame(diagnostic_rows)
    bound_rows = []
    for name, value, (lower, upper) in zip(names, x, bounds):
        lower_slack = None if lower is None else float(value - lower)
        upper_slack = None if upper is None else float(upper - value)
        bound_rows.append({"variable": name, "value": float(value), "lower_bound": lower,
                           "upper_bound": upper, "lower_bound_slack": lower_slack, "upper_bound_slack": upper_slack})
    return {
        "tool_id": "T062",
        "status": "OPTIMAL",
        "method": "Continuous linear programming via SciPy linprog / HiGHS",
        "solver_name": "HiGHS (through SciPy linprog)",
        "solver_status_code": int(result.status),
        "solver_message": message,
        "objective_sense": sense,
        "objective_value": objective_value,
        "variables": variable_table,
        "constraint_diagnostics": diagnostics,
        "bound_diagnostics": pd.DataFrame(bound_rows),
        "warnings": [
            "Optimality applies only to the supplied continuous linear model. Integer, nonlinear, scheduling and hidden constraints are not included.",
            "Constraint residuals are recomputed from returned variables. No IIS or unsupported conflict diagnosis is fabricated.",
        ],
        "assumptions": [
            "All coefficients are finite and use internally consistent units.",
            "Bounds are interpreted as continuous variable bounds; blank values indicate no bound on that side.",
        ],
        "metrics": {
            "variable_count": int(len(names)),
            "constraint_count": int(len(constraints)),
            "objective_value": objective_value,
            "constraints_satisfied": bool((diagnostics["status"] == "SATISFIED").all()) if not diagnostics.empty else True,
            "optimal": True,
        },
    }
