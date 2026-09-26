"""Shoir-IE adoption engine.

Shared adoption primitives that sit above the existing Industrial Workbook,
Digital Thread, Copilot, Universal Visualization and enterprise services.

The goal is a productivity layer, not another module catalog:
workbook -> query -> formula -> pivot -> analyze -> automation -> explain ->
decision -> implementation -> outcome.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


FORMULA_LIBRARY: dict[str, dict[str, str]] = {
    "OEE": {
        "signature": "OEE(Availability, Performance, Quality)",
        "purpose": "Overall equipment effectiveness as the product of the three ratios.",
        "example": "=OEE(0.92,0.95,0.99)",
        "notes": "Inputs may be decimals or percentages; percentage-like values above 1 are normalized to ratios.",
    },
    "TAKTTIME": {
        "signature": "TAKTTIME(AvailableTime, Demand)",
        "purpose": "Required production pace in the same time unit as AvailableTime.",
        "example": "=TAKTTIME(480,120)",
        "notes": "Keep time and demand units consistent.",
    },
    "LITTLELAW": {
        "signature": "LITTLELAW(ArrivalRate, TimeInSystem)",
        "purpose": "Average WIP from Little's Law, L = lambda × W.",
        "example": "=LITTLELAW(12,0.5)",
        "notes": "TimeInSystem must use the inverse time unit of ArrivalRate.",
    },
    "CPK": {
        "signature": "CPK(Measurements, LSL, USL)",
        "purpose": "Process capability index using sample standard deviation.",
        "example": "=CPK(A2:A101,9.5,10.5)",
        "notes": "A measurement range is accepted by the workbook formula engine.",
    },
    "PPK": {
        "signature": "PPK(Measurements, LSL, USL)",
        "purpose": "Overall performance index using sample standard deviation.",
        "example": "=PPK(A2:A101,9.5,10.5)",
        "notes": "This generic implementation uses the overall sample standard deviation.",
    },
    "EOQ": {
        "signature": "EOQ(AnnualDemand, OrderingCost, HoldingCost)",
        "purpose": "Economic order quantity under the classic deterministic model.",
        "example": "=EOQ(12000,50,2)",
        "notes": "All three inputs must use compatible annualized units.",
    },
    "SAFETYSTOCK": {
        "signature": "SAFETYSTOCK(Z, DemandStd, LeadTime)",
        "purpose": "Safety stock using z × sigma_demand × sqrt(lead time).",
        "example": "=SAFETYSTOCK(1.65,120,5)",
        "notes": "Use the lead-time unit expected by the demand standard deviation convention.",
    },
    "NPV": {
        "signature": "NPV(Rate, Cashflows)",
        "purpose": "Net present value of cash flows from period 1 onward.",
        "example": "=NPV(0.1,F2:F6)",
        "notes": "An initial period-0 investment should be added separately, matching standard spreadsheet NPV conventions.",
    },
    "CO2E": {
        "signature": "CO2E(Activity, EmissionFactor)",
        "purpose": "Activity times an emission factor.",
        "example": "=CO2E(1000,0.42)",
        "notes": "The result inherits the combined units of the two inputs.",
    },
    "CONVERT": {
        "signature": "CONVERT(Value, FromUnit, ToUnit)",
        "purpose": "Explicit engineering-unit conversion using the workbook unit registry.",
        "example": '=CONVERT(60,"min","h")',
        "notes": "Incompatible dimensions are rejected.",
    },
    "MTBF": {
        "signature": "MTBF(Uptime, Failures)",
        "purpose": "Mean time between failures under the supplied uptime/failure convention.",
        "example": "=MTBF(720,3)",
        "notes": "Failures must be greater than zero.",
    },
    "MTTR": {
        "signature": "MTTR(Downtime, Failures)",
        "purpose": "Mean time to repair under the supplied downtime/failure convention.",
        "example": "=MTTR(12,3)",
        "notes": "Failures must be greater than zero.",
    },
    "UTILIZATION": {
        "signature": "UTILIZATION(Used, Available)",
        "purpose": "Resource utilization ratio.",
        "example": "=UTILIZATION(144,160)",
        "notes": "Available must be greater than zero.",
    },
    "FPY": {
        "signature": "FPY(GoodUnits, TotalUnits)",
        "purpose": "First-pass yield ratio.",
        "example": "=FPY(950,1000)",
        "notes": "TotalUnits must be greater than zero.",
    },
    "DPMO": {
        "signature": "DPMO(Defects, Units, OpportunitiesPerUnit)",
        "purpose": "Defects per million opportunities.",
        "example": "=DPMO(12,1000,4)",
        "notes": "Units and opportunities per unit must be greater than zero.",
    },
    "PERCENTCHANGE": {
        "signature": "PERCENTCHANGE(Old, New)",
        "purpose": "Relative change from Old to New.",
        "example": "=PERCENTCHANGE(100,108)",
        "notes": "Old must be non-zero.",
    },
    "CAPACITY": {
        "signature": "CAPACITY(AvailableTime, Rate)",
        "purpose": "Capacity from available time multiplied by rate.",
        "example": "=CAPACITY(480,2.5)",
        "notes": "Inputs retain their supplied engineering units.",
    },
    "YIELD": {
        "signature": "YIELD(Good, Total)",
        "purpose": "Good-output yield ratio.",
        "example": "=YIELD(980,1000)",
        "notes": "Total must be greater than zero.",
    },
}


def _numeric(values: Any) -> list[float]:
    if isinstance(values, (list, tuple, np.ndarray, pd.Series)):
        out: list[float] = []
        for item in list(values):
            out.extend(_numeric(item))
        return out
    if isinstance(values, (bool, np.bool_)):
        return []
    try:
        value = float(values)
    except (TypeError, ValueError):
        return []
    return [value] if math.isfinite(value) else []


def _ratio(value: Any) -> float:
    number = float(value)
    return number / 100.0 if abs(number) > 1.0 else number


def evaluate_engineering_function(name: str, args: Sequence[Any]) -> Any:
    """Evaluate a named industrial function with explicit argument checks."""
    key = str(name).strip().upper()
    a = list(args)

    if key == "OEE":
        if len(a) != 3:
            raise ValueError("OEE requires Availability, Performance and Quality.")
        return _ratio(a[0]) * _ratio(a[1]) * _ratio(a[2])

    if key == "TAKTTIME":
        if len(a) != 2:
            raise ValueError("TAKTTIME requires AvailableTime and Demand.")
        demand = float(a[1])
        if demand == 0:
            raise ZeroDivisionError("Demand cannot be zero for TAKTTIME.")
        return float(a[0]) / demand

    if key == "LITTLELAW":
        if len(a) != 2:
            raise ValueError("LITTLELAW requires ArrivalRate and TimeInSystem.")
        return float(a[0]) * float(a[1])

    if key in {"CPK", "PPK"}:
        if len(a) != 3:
            raise ValueError(f"{key} requires Measurements, LSL and USL.")
        values = _numeric(a[0])
        if len(values) < 2:
            raise ValueError(f"{key} requires at least two numeric measurements.")
        lsl, usl = float(a[1]), float(a[2])
        if usl <= lsl:
            raise ValueError("USL must be greater than LSL.")
        sigma = float(np.std(np.asarray(values, dtype=float), ddof=1))
        if sigma <= 0:
            raise ValueError(f"{key} cannot be calculated when measurement variation is zero.")
        mean = float(np.mean(values))
        return min((usl - mean) / (3 * sigma), (mean - lsl) / (3 * sigma))

    if key == "EOQ":
        if len(a) != 3:
            raise ValueError("EOQ requires AnnualDemand, OrderingCost and HoldingCost.")
        demand, ordering, holding = map(float, a)
        if demand < 0 or ordering < 0 or holding <= 0:
            raise ValueError("EOQ requires non-negative demand/order cost and positive holding cost.")
        return math.sqrt(2.0 * demand * ordering / holding)

    if key == "SAFETYSTOCK":
        if len(a) != 3:
            raise ValueError("SAFETYSTOCK requires Z, DemandStd and LeadTime.")
        z, sigma, lead = map(float, a)
        if sigma < 0 or lead < 0:
            raise ValueError("DemandStd and LeadTime cannot be negative.")
        return z * sigma * math.sqrt(lead)

    if key == "NPV":
        if len(a) != 2:
            raise ValueError("NPV requires Rate and Cashflows.")
        rate = float(a[0])
        cashflows = _numeric(a[1])
        if rate <= -1:
            raise ValueError("NPV discount rate must be greater than -100%.")
        return float(sum(cf / ((1.0 + rate) ** period) for period, cf in enumerate(cashflows, start=1)))

    if key == "CO2E":
        if len(a) != 2:
            raise ValueError("CO2E requires Activity and EmissionFactor.")
        return float(a[0]) * float(a[1])

    if key == "MTBF":
        if len(a) != 2:
            raise ValueError("MTBF requires Uptime and Failures.")
        failures=float(a[1])
        if failures <= 0:
            raise ValueError("Failures must be greater than zero.")
        return float(a[0]) / failures

    if key == "MTTR":
        if len(a) != 2:
            raise ValueError("MTTR requires Downtime and Failures.")
        failures=float(a[1])
        if failures <= 0:
            raise ValueError("Failures must be greater than zero.")
        return float(a[0]) / failures

    if key == "UTILIZATION":
        if len(a) != 2:
            raise ValueError("UTILIZATION requires Used and Available.")
        available=float(a[1])
        if available <= 0:
            raise ValueError("Available must be greater than zero.")
        return float(a[0]) / available

    if key in {"FPY","YIELD"}:
        if len(a) != 2:
            raise ValueError(f"{key} requires Good and Total.")
        total=float(a[1])
        if total <= 0:
            raise ValueError("Total must be greater than zero.")
        return float(a[0]) / total

    if key == "DPMO":
        if len(a) != 3:
            raise ValueError("DPMO requires Defects, Units and OpportunitiesPerUnit.")
        defects,units,opps=map(float,a)
        if units <= 0 or opps <= 0:
            raise ValueError("Units and OpportunitiesPerUnit must be greater than zero.")
        return defects / (units * opps) * 1_000_000.0

    if key == "PERCENTCHANGE":
        if len(a) != 2:
            raise ValueError("PERCENTCHANGE requires Old and New.")
        old=float(a[0])
        if old == 0:
            raise ValueError("Old value must be non-zero.")
        return (float(a[1]) - old) / old

    if key == "CAPACITY":
        if len(a) != 2:
            raise ValueError("CAPACITY requires AvailableTime and Rate.")
        return float(a[0]) * float(a[1])

    if key == "CONVERT":
        if len(a) != 3:
            raise ValueError("CONVERT requires Value, FromUnit and ToUnit.")
        from shoir_industrial_workbook import convert_units
        return convert_units(float(a[0]), str(a[1]), str(a[2]))

    raise KeyError(f"Unknown engineering function: {name}")


def formula_library_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"Function": name, **spec} for name, spec in FORMULA_LIBRARY.items()
    ])


def industrial_pivot(
    df: pd.DataFrame,
    index: str | Sequence[str],
    columns: str | Sequence[str] | None,
    values: str | Sequence[str],
    aggfunc: str = "sum",
    fill_value: float | None = None,
) -> pd.DataFrame:
    """Safe PivotTable-equivalent for industrial workbooks."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Pivot input must be a pandas DataFrame.")
    work = df.copy(deep=True)
    index_cols = [str(index)] if isinstance(index, str) else [str(x) for x in index]
    col_cols = None if columns in (None, "", []) else ([str(columns)] if isinstance(columns, str) else [str(x) for x in columns])
    value_cols = [str(values)] if isinstance(values, str) else [str(x) for x in values]
    missing = [c for c in [*index_cols, *(col_cols or []), *value_cols] if c not in work.columns]
    if missing:
        raise KeyError(f"Pivot columns not found: {sorted(set(missing))}")
    funcs = {"sum", "mean", "median", "min", "max", "count", "std"}
    agg = str(aggfunc).lower().strip()
    if agg not in funcs:
        raise ValueError(f"Unsupported pivot aggregation: {aggfunc}. Choose from {sorted(funcs)}.")
    result = pd.pivot_table(
        work,
        index=index_cols,
        columns=col_cols,
        values=value_cols,
        aggfunc=agg,
        fill_value=fill_value,
        dropna=False,
    ).reset_index()
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = [
            " · ".join(str(part) for part in col if str(part) not in {"", "None"})
            if isinstance(col, tuple) else str(col)
            for col in result.columns.to_flat_index()
        ]
    return result.reset_index(drop=True)


_SCRIPT_CALL_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*\(.*\)\s*$")
_SCRIPT_ALLOWED = {
    "load", "select", "rename", "drop_duplicates", "fill", "sort", "filter",
    "add_column", "groupby", "pivot", "formula", "analyze", "validate",
}


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception as exc:
        raise ValueError("Shoir Script accepts literal arguments only; executable Python is not permitted.") from exc


def compile_shoir_script(script: str) -> list[dict[str, Any]]:
    """Compile a small deterministic automation DSL without eval/exec."""
    commands: list[dict[str, Any]] = []
    for raw_line in str(script or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not _SCRIPT_CALL_RE.fullmatch(line):
            raise ValueError(f"Invalid Shoir Script statement: {line}")
        tree = ast.parse(line, mode="eval")
        call = tree.body
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            raise ValueError("Only named Shoir Script function calls are allowed.")
        name = call.func.id
        if name not in _SCRIPT_ALLOWED:
            raise ValueError(f"Unsupported Shoir Script command: {name}")
        if any(not isinstance(keyword.value, (ast.Constant, ast.List, ast.Tuple, ast.Dict)) for keyword in call.keywords):
            raise ValueError(f"Command {name} only accepts literal keyword values.")
        args = [_literal(arg) for arg in call.args]
        kwargs = {kw.arg: _literal(kw.value) for kw in call.keywords if kw.arg is not None}
        commands.append({"command": name, "args": args, "kwargs": kwargs})
    return commands


def run_shoir_script(
    script: str,
    workbook: Mapping[str, pd.DataFrame],
    active_sheet: str | None = None,
    formulas: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Execute compiled Shoir Script commands against a workbook safely."""
    from shoir_industrial_workbook import apply_query_pipeline, evaluate_workbook_formulas

    compiled = compile_shoir_script(script)
    state = {str(k): v.copy(deep=True) for k, v in workbook.items()}
    formula_map: dict[str, dict[str, str]] = {
        str(k): dict(v) for k, v in (formulas or {}).items()
    }
    sheet = str(active_sheet or next(iter(state), "Sheet1"))
    outputs: list[dict[str, Any]] = []

    for item in compiled:
        name, args, kwargs = item["command"], item["args"], item["kwargs"]
        if name == "load":
            target = str(args[0] if args else kwargs.get("sheet", sheet))
            if target not in state:
                raise KeyError(f"Unknown worksheet: {target}")
            sheet = target
            outputs.append({"command": name, "sheet": sheet, "status": "Loaded"})
            continue

        if sheet not in state:
            raise KeyError(f"Unknown worksheet: {sheet}")

        if name == "analyze":
            from shoir_industrial_workbook import instant_analyze
            analysis = instant_analyze(state[sheet])
            outputs.append({"command": name, "sheet": sheet, "status": "Completed", "result": analysis})
            continue

        if name == "validate":
            from shoir_industrial_workbook import validate_workbook
            validation = validate_workbook(state)
            outputs.append({"command": name, "status": "Completed", "result": validation})
            continue

        if name == "formula":
            cell = str(kwargs.get("cell", args[0] if args else ""))
            expression = str(kwargs.get("expression", args[1] if len(args) > 1 else ""))
            if not cell or not expression:
                raise ValueError("formula requires cell and expression.")
            formula_map.setdefault(sheet, {})[cell.upper()] = expression
            state, audit = evaluate_workbook_formulas(state, formula_map)
            outputs.append({"command": name, "sheet": sheet, "cell": cell.upper(), "status": "Completed", "audit": audit})
            continue

        step = {"type": {
            "select": "select",
            "rename": "rename",
            "drop_duplicates": "drop_duplicates",
            "fill": "fill_missing",
            "sort": "sort",
            "filter": "filter",
            "add_column": "add_formula",
            "groupby": "groupby",
            "pivot": "pivot",
        }[name]}
        if args:
            positional_maps = {
                "select": ["columns"], "rename": ["source", "target"], "drop_duplicates": ["columns"],
                "fill": ["column", "value"], "sort": ["column"], "filter": ["column", "op", "value"],
                "add_column": ["target", "expression"], "groupby": ["columns", "value_column", "aggregation"],
                "pivot": ["index", "columns", "values", "aggregation"],
            }
            for key, value in zip(positional_maps[name], args):
                step[key] = value
        step.update(kwargs)

        if name == "pivot":
            state[sheet] = industrial_pivot(
                state[sheet],
                index=step.get("index", []),
                columns=step.get("columns"),
                values=step.get("values"),
                aggfunc=step.get("aggregation", "sum"),
                fill_value=step.get("fill_value"),
            )
        else:
            state[sheet] = apply_query_pipeline(state[sheet], [step])
        outputs.append({"command": name, "sheet": sheet, "status": "Completed", "shape": state[sheet].shape})

    return {
        "workbook": state,
        "formulas": formula_map,
        "outputs": outputs,
        "script_hash": hashlib.sha256(str(script).encode("utf-8")).hexdigest(),
    }


def extract_formula_dependencies(formula: str, sheet: str) -> list[dict[str, str]]:
    raw = str(formula or "").strip()
    dependencies: list[dict[str, str]] = []
    for match in re.finditer(r"'([^']+)'!\$?([A-Za-z]{1,3})\$?(\d+)|([A-Za-z_][A-Za-z0-9_]*)!\$?([A-Za-z]{1,3})\$?(\d+)|(?<![A-Za-z0-9_])\$?([A-Za-z]{1,3})\$?(\d+)", raw):
        target_sheet = match.group(1) or match.group(4) or sheet
        column = match.group(2) or match.group(5) or match.group(7)
        row = match.group(3) or match.group(6) or match.group(8)
        dependencies.append({
            "Sheet": str(target_sheet),
            "Cell": f"{column.upper()}{row}",
            "Reference": f"{target_sheet}!{column.upper()}{row}",
        })
    return dependencies


def build_dependency_graph(
    workbook: Mapping[str, pd.DataFrame],
    formulas: Mapping[str, Mapping[str, str]],
    semantic_map: Mapping[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for sheet, df in workbook.items():
        nodes.append({"ID": f"sheet:{sheet}", "Type": "Sheet", "Label": str(sheet), "Status": "Observed"})
        for col in df.columns:
            nodes.append({
                "ID": f"field:{sheet}:{col}",
                "Type": "Field",
                "Label": f"{sheet}.{col}",
                "Status": "Observed",
            })
            edges.append({
                "Source": f"sheet:{sheet}",
                "Target": f"field:{sheet}:{col}",
                "Relation": "contains",
            })

    for sheet, sheet_formulas in formulas.items():
        for cell, formula in sheet_formulas.items():
            source = f"cell:{sheet}:{str(cell).upper()}"
            nodes.append({"ID": source, "Type": "Formula", "Label": f"{sheet}!{str(cell).upper()}", "Status": "Calculated"})
            for dep in extract_formula_dependencies(str(formula), str(sheet)):
                target = f"cell:{dep['Sheet']}!{dep['Cell']}"
                edges.append({"Source": source, "Target": target, "Relation": "depends on"})

    for sheet, mapping in (semantic_map or {}).items():
        if not isinstance(mapping, Mapping):
            continue
        for column, role in mapping.items():
            edges.append({
                "Source": f"field:{sheet}:{column}",
                "Target": f"semantic:{role}",
                "Relation": "maps to",
            })
            nodes.append({"ID": f"semantic:{role}", "Type": "Semantic", "Label": str(role), "Status": "Mapped"})

    node_df = pd.DataFrame(nodes).drop_duplicates("ID").reset_index(drop=True)
    edge_df = pd.DataFrame(edges).drop_duplicates().reset_index(drop=True)
    return node_df, edge_df


def explain_number(
    workbook: Mapping[str, pd.DataFrame],
    formulas: Mapping[str, Mapping[str, str]],
    sheet: str,
    cell: str,
    semantic_map: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    cell_ref = str(cell).upper()
    if sheet not in workbook:
        raise KeyError(f"Unknown worksheet: {sheet}")
    from shoir_industrial_workbook import _cell_parts, infer_units
    col_index, row_index = _cell_parts(cell_ref)
    df = workbook[sheet]
    if row_index >= len(df) or col_index >= len(df.columns):
        raise ValueError(f"Cell {sheet}!{cell_ref} is outside the current worksheet.")
    column_name = str(df.columns[col_index])
    formula = str(formulas.get(sheet, {}).get(cell_ref, "") or "")
    dependencies = extract_formula_dependencies(formula, sheet) if formula else []
    role = None
    if isinstance(semantic_map, Mapping):
        role = semantic_map.get(sheet, {}).get(column_name) if isinstance(semantic_map.get(sheet, {}), Mapping) else None
    value = df.iloc[row_index, col_index]
    return {
        "Sheet": sheet,
        "Cell": cell_ref,
        "Value": None if pd.isna(value) else value,
        "Column": column_name,
        "Formula": formula or "Direct cell value",
        "Dependencies": dependencies,
        "Unit Hints": infer_units(column_name),
        "Semantic Role": role or "Unmapped",
        "Explanation": (
            f"{sheet}!{cell_ref} is calculated from {len(dependencies)} reference(s)."
            if formula else
            f"{sheet}!{cell_ref} is a direct value from the {column_name} field."
        ),
    }


def runtime_capability_report() -> pd.DataFrame:
    capabilities = []
    for label, package, mode in [
        ("Pandas", "pandas", "Baseline vectorized runtime"),
        ("PyArrow", "pyarrow", "Columnar interchange / Arrow-backed paths"),
        ("Polars", "polars", "Optional high-performance dataframe runtime"),
        ("DuckDB", "duckdb", "Optional analytical SQL runtime"),
    ]:
        try:
            __import__(package)
            installed = True
        except Exception:
            installed = False
        capabilities.append({"Runtime": label, "Installed": installed, "Role": mode})
    return pd.DataFrame(capabilities)


def choose_runtime(rows: int, columns: int) -> dict[str, Any]:
    cells = max(0, int(rows)) * max(0, int(columns))
    capability = runtime_capability_report()
    available = set(capability.loc[capability["Installed"], "Runtime"].astype(str))
    if cells <= 250_000:
        selected = "Pandas / interactive"
    elif "DuckDB" in available:
        selected = "DuckDB analytical path"
    elif "Polars" in available:
        selected = "Polars vectorized path"
    elif "PyArrow" in available:
        selected = "PyArrow columnar path"
    else:
        selected = "Pandas chunked/vectorized path"
    return {
        "rows": int(rows), "columns": int(columns), "cells": cells,
        "selected_runtime": selected,
        "available_runtimes": sorted(available),
        "reason": "Runtime selection is capability-based; it never pretends an optional engine is available when it is not installed.",
    }


def product_home_snapshot(username: str, workspace: str = "default", db_path: str = "enterprise_full_workspace.db") -> dict[str, Any]:
    """Collect adoption metrics without exposing credentials or secret values."""
    counts = {"workbooks": 0, "decisions": 0, "studies": 0, "templates": 0}
    with sqlite3.connect(db_path, timeout=10) as conn:
        queries = [
            ("workbooks", "SELECT COUNT(*) FROM industrial_workbooks WHERE workspace=?"),
            ("templates", "SELECT COUNT(*) FROM industrial_workbook_templates WHERE workspace=?"),
            ("decisions", "SELECT COUNT(*) FROM experience_decisions WHERE owner=?"),
            ("studies", "SELECT COUNT(*) FROM experience_projects WHERE owner=?"),
        ]
        for key, query in queries:
            try:
                param = workspace if key in {"workbooks", "templates"} else username
                counts[key] = int(conn.execute(query, (param,)).fetchone()[0])
            except sqlite3.Error:
                counts[key] = 0

    return {
        "generated_at": _now(),
        "actor": str(username),
        "workspace": str(workspace),
        **counts,
    }


def action_center_snapshot(
    username: str,
    session_state: Mapping[str, Any],
    db_path: str = "enterprise_full_workspace.db",
) -> pd.DataFrame:
    """Return actionable items for the user, derived from current evidence."""
    rows: list[dict[str, str]] = []
    readiness = session_state.get("unified_readiness_score")
    if readiness is not None:
        try:
            if float(readiness) < 100:
                rows.append({"Priority": "Review", "Type": "Data", "Item": f"Data readiness is {float(readiness):.1f}%; review failed checks before decision use.", "Source": "Unified Study Center"})
        except (TypeError, ValueError):
            pass

    audit = session_state.get("industrial_workbook_formula_audit_df")
    if isinstance(audit, pd.DataFrame) and not audit.empty and "Status" in audit.columns:
        errors = int(audit["Status"].astype(str).eq("Error").sum())
        if errors:
            rows.append({"Priority": "Review", "Type": "Formula", "Item": f"{errors} workbook formula error(s) require review.", "Source": "Industrial Workbook"})

    jobs = session_state.get("enterprise_job_history_df")
    if isinstance(jobs, pd.DataFrame) and not jobs.empty:
        pending = jobs[jobs.astype(str).apply(lambda s: s.str.contains("pending|running|attention", case=False, regex=True)).any(axis=1)]
        if not pending.empty:
            rows.append({"Priority": "Action", "Type": "Job", "Item": f"{len(pending):,} job record(s) need attention.", "Source": "Jobs System"})

    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            decisions = conn.execute(
                "SELECT decision_id,title,status FROM experience_decisions WHERE owner=? AND status IN ('Draft','Review','Proposed','Validated') ORDER BY updated_at DESC LIMIT 20",
                (username,),
            ).fetchall()
        for decision_id, title, status in decisions:
            rows.append({"Priority": "Action", "Type": "Decision", "Item": f"{title} · {status}", "Source": f"Decision {decision_id}"})
    except sqlite3.Error:
        pass

    return pd.DataFrame(rows, columns=["Priority", "Type", "Item", "Source"])


ACADEMY_COURSES = [
    ("Industrial Engineering Essentials", "Takt, capacity, OEE, flow and engineering economics in one workbook."),
    ("Quality Analytics", "SPC, capability, Pareto, variation and evidence-ready quality decisions."),
    ("Operations Research", "LP/MILP, robust optimization, scenarios and decision governance."),
    ("Simulation & Uncertainty", "DOE, Monte Carlo, replication, confidence intervals and sensitivity."),
    ("Industrial Data Engineering", "Excel interoperability, validation, query pipelines, semantic mapping and lineage."),
    ("Decision Governance", "Assumptions, approvals, implementation and verified outcomes."),
]


def render_adoption_center(username: str, tier: str, initial_tab: str = "Home") -> None:
    """Render the productivity layer as a single application surface."""
    import streamlit as st
    from shoir_industrial_workbook import (
        _workspace, _serialize_workbook, instant_analyze, infer_semantic_roles,
        list_templates, list_workbook_extensions, _starter_templates,
    )

    tabs = ["Home", "Quick Analyze", "Industrial Pivot", "Automate", "Trust & Explain", "Learn & Extend"]
    initial = tabs.index(initial_tab) if initial_tab in tabs else 0
    st.markdown(
        "<div class='iw-hero'><div class='iw-chip'>SHOIR-IE PRODUCTIVITY LAYER</div>"
        "<div class='iw-chip'>EXCEL-FRIENDLY</div><div class='iw-chip'>EVIDENCE-FIRST</div>"
        "<div class='iw-title'>Industrial Home</div>"
        "<div class='iw-copy'>One workspace for data, formulas, pivots, automation, explanation and governed decisions.</div></div>",
        unsafe_allow_html=True,
    )
    data = st.session_state.get("industrial_workbook_current_df")
    if not isinstance(data, pd.DataFrame) or data.empty:
        data = st.session_state.get("unified_data")
    if not isinstance(data, pd.DataFrame) or data.empty:
        data = _starter_templates()["OEE Starter"]["data"].copy(deep=True)

    product = product_home_snapshot(username, _workspace())
    top = st.columns(5)
    top[0].metric("Workbooks", f"{product['workbooks']:,}")
    top[1].metric("Studies", f"{product['studies']:,}")
    top[2].metric("Decisions", f"{product['decisions']:,}")
    top[3].metric("Templates", f"{product['templates'] + len(_starter_templates()):,}")
    top[4].metric("Current table", f"{len(data):,} × {len(data.columns):,}")

    if st.button("Open Industrial Workbook", type="primary", use_container_width=True, key="adoption_open_workbook"):
        st.session_state["force_workbook_module"] = True
        st.rerun()

    with st.expander("Commandable workflow", expanded=True):
        st.markdown("**Import → Validate → Analyze → Visualize → Simulate → Optimize → Decide → Implement → Learn**")
        st.caption("Existing domain engines remain the calculation authorities; this layer routes work between them.")

    with st.container(border=True):
        st.markdown("### Quick actions")
        q1, q2, q3 = st.columns(3)
        if q1.button("⚡ Quick Analyze", use_container_width=True, key="adoption_quick_action"):
            st.session_state["adoption_tab_request"] = "Quick Analyze"
            st.rerun()
        if q2.button("📊 Industrial Pivot", use_container_width=True, key="adoption_pivot_action"):
            st.session_state["adoption_tab_request"] = "Industrial Pivot"
            st.rerun()
        if q3.button("🤖 Automate", use_container_width=True, key="adoption_automate_action"):
            st.session_state["adoption_tab_request"] = "Automate"
            st.rerun()

    current_initial = st.session_state.pop("adoption_tab_request", initial)
    tabs_widget = st.tabs(tabs)
    with tabs_widget[tabs.index(current_initial) if current_initial in tabs else initial]:
        pass

    # Streamlit tabs do not expose a programmatic selected tab API; the
    # widgets below are rendered in their own expanders so commands remain
    # accessible without fragile state manipulation.
    home_tab, analyze_tab, pivot_tab, automation_tab, trust_tab, learn_tab = tabs_widget

    with home_tab:
        st.markdown("### Recent work")
        st.info("Use Open Industrial Workbook to continue an editable multi-sheet session. The same workbook can feed module-specific engines.")
        try:
            saved = list_workbook_extensions()
            st.caption(f"Developer extensions available: {len(saved):,}")
        except Exception:
            pass

    with analyze_tab:
        st.markdown("### Quick Analyze")
        upload = st.file_uploader("Drop Excel or CSV", type=["xlsx", "csv"], key="adoption_quick_upload")
        source = data
        if upload is not None:
            try:
                raw = upload.getvalue()
                if upload.name.lower().endswith(".xlsx"):
                    from shoir_upgrade import read_uploaded_workbook
                    book = read_uploaded_workbook(raw, upload.name)
                    choice = st.selectbox("Sheet", list(book), key="adoption_analyze_sheet")
                    source = book[choice]
                else:
                    source = pd.read_csv(io.BytesIO(raw))
                st.session_state["adoption_quick_analyze_source"] = source
            except Exception as exc:
                st.error(f"Import failed safely: {type(exc).__name__}: {exc}")
        source = st.session_state.get("adoption_quick_analyze_source", source)
        analysis = instant_analyze(source)
        st.dataframe(analysis["profile"], use_container_width=True, hide_index=True)
        for item in analysis["recommendations"]:
            st.write("✓ " + item)
        if analysis.get("figure") is not None:
            st.plotly_chart(analysis["figure"], use_container_width=True, config={"displayModeBar": False})
        runtime = choose_runtime(len(source), len(source.columns))
        st.caption(f"Runtime path: **{runtime['selected_runtime']}**")

    with pivot_tab:
        st.markdown("### Industrial Pivot")
        cols = list(map(str, data.columns))
        if cols:
            idx = st.multiselect("Rows", cols, default=[cols[0]], key="adoption_pivot_index")
            col = st.selectbox("Columns", ["(none)"] + cols, key="adoption_pivot_columns")
            vals = st.selectbox("Values", cols, key="adoption_pivot_values")
            agg = st.selectbox("Aggregation", ["sum", "mean", "median", "min", "max", "count"], key="adoption_pivot_agg")
            if st.button("Build Pivot", type="primary", use_container_width=True, key="adoption_pivot_run"):
                try:
                    result = industrial_pivot(data, idx or [cols[0]], None if col == "(none)" else col, vals, agg)
                    st.session_state["adoption_pivot_result"] = result
                except Exception as exc:
                    st.error(f"Pivot failed safely: {type(exc).__name__}: {exc}")
        pivot_result = st.session_state.get("adoption_pivot_result", pd.DataFrame())
        if isinstance(pivot_result, pd.DataFrame) and not pivot_result.empty:
            st.dataframe(pivot_result, use_container_width=True, hide_index=True)
            numeric = [c for c in pivot_result.columns if pd.api.types.is_numeric_dtype(pivot_result[c])]
            categorical = [c for c in pivot_result.columns if c not in numeric]
            if numeric:
                import plotly.express as px
                fig = px.bar(pivot_result, x=categorical[0] if categorical else pivot_result.index, y=numeric[0], title="Industrial Pivot result")
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with automation_tab:
        st.markdown("### Shoir Script")
        st.caption("Deterministic automation; no Python execution is accepted from the script surface.")
        script = st.text_area(
            "Automation",
            value='load("Sheet1")\\nadd_column("Extended Cost","Quantity * Unit Cost")\\nanalyze()',
            height=150,
            key="adoption_script",
        )
        if st.button("▶ Run automation", type="primary", use_container_width=True, key="adoption_script_run"):
            try:
                from shoir_industrial_workbook import WORKBOOK_STATE_KEY, FORMULA_STATE_KEY
                wb = st.session_state.get(WORKBOOK_STATE_KEY, {"Sheet1": data})
                result = run_shoir_script(
                    script,
                    wb,
                    active_sheet=st.session_state.get("industrial_workbook_active_sheet", next(iter(wb), "Sheet1")),
                    formulas=st.session_state.get(FORMULA_STATE_KEY, {}),
                )
                st.session_state[WORKBOOK_STATE_KEY] = result["workbook"]
                st.session_state[FORMULA_STATE_KEY] = result["formulas"]
                st.session_state["adoption_script_outputs"] = result["outputs"]
                st.success(f"Automation completed · {len(result['outputs']):,} command(s).")
            except Exception as exc:
                st.error(f"Automation stopped safely: {type(exc).__name__}: {exc}")
        if st.session_state.get("adoption_script_outputs"):
            st.dataframe(pd.json_normalize(st.session_state["adoption_script_outputs"]), use_container_width=True, hide_index=True)

    with trust_tab:
        st.markdown("### Trust & Explain")
        workbook = st.session_state.get("industrial_workbook", {"Sheet1": data})
        formulas = st.session_state.get("industrial_workbook_formulas", {})
        semantic = st.session_state.get("industrial_workbook_semantic_map", {})
        node_df, edge_df = build_dependency_graph(workbook, formulas, semantic)
        st.markdown("#### Dependency graph")
        st.dataframe(edge_df.head(500), use_container_width=True, hide_index=True)
        st.caption(f"{len(node_df):,} dependency nodes · {len(edge_df):,} relationships")
        st.markdown("#### Explain this number")
        sheet = st.selectbox("Sheet", list(workbook), key="adoption_explain_sheet")
        cell = st.text_input("Cell", value="A1", key="adoption_explain_cell")
        if st.button("Explain", key="adoption_explain_run"):
            try:
                explanation = explain_number(workbook, formulas, sheet, cell, semantic)
                st.json(explanation)
            except Exception as exc:
                st.warning(f"Number explanation unavailable: {type(exc).__name__}: {exc}")
        st.markdown("#### Action center")
        actions = action_center_snapshot(username, st.session_state)
        if actions.empty:
            st.success("No outstanding action is visible from the current workspace state.")
        else:
            st.dataframe(actions, use_container_width=True, hide_index=True)
        st.markdown("#### Runtime")
        st.dataframe(runtime_capability_report(), use_container_width=True, hide_index=True)

    with learn_tab:
        st.markdown("### Industrial Academy")
        st.dataframe(pd.DataFrame(ACADEMY_COURSES, columns=["Course", "Outcome"]), use_container_width=True, hide_index=True)
        st.markdown("### Formula library")
        st.dataframe(formula_library_frame(), use_container_width=True, hide_index=True)
        st.markdown("### Template ecosystem")
        st.dataframe(list_templates(), use_container_width=True, hide_index=True)
        st.caption("Community and public marketplace publication should be enabled through explicit workspace publication controls; the local library remains workspace-scoped.")
