"""Shoir-IE Industrial Workbook.

A first-class, Excel-like productivity layer that sits above the existing
engineering engines. It provides editable sheets, a safe engineering formula
engine, reusable query pipelines, instant analysis, template packs, semantic
mapping into the Digital Thread, deterministic Copilot edits, and a small
extension SDK.

This module deliberately does not claim to be a Microsoft Excel replacement.
It is an interoperable industrial workbook surface that can hand work into
Shoir-IE's existing Digital Thread, Copilot, Visualization, persistence,
optimization, forecasting and reporting layers.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import io
import json
import math
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd
import plotly.express as px

DB_PATH = "enterprise_full_workspace.db"
WORKBOOK_STATE_KEY = "industrial_workbook"
FORMULA_STATE_KEY = "industrial_workbook_formulas"

CANONICAL_TYPES = [
    "Dataset", "Asset", "Process", "Product", "Material", "Order", "Workforce",
    "Quality", "Maintenance", "Energy", "Cost", "Scenario", "KPI", "Model",
    "Experiment", "Decision", "Outcome",
]

UNIT_DEFS: dict[str, tuple[str, float]] = {
    "m": ("length", 1.0), "meter": ("length", 1.0), "meters": ("length", 1.0),
    "cm": ("length", 0.01), "mm": ("length", 0.001), "km": ("length", 1000.0),
    "in": ("length", 0.0254), "ft": ("length", 0.3048),
    "kg": ("mass", 1.0), "g": ("mass", 0.001), "mg": ("mass", 0.000001),
    "t": ("mass", 1000.0), "lb": ("mass", 0.45359237),
    "s": ("time", 1.0), "sec": ("time", 1.0), "min": ("time", 60.0),
    "h": ("time", 3600.0), "hr": ("time", 3600.0), "day": ("time", 86400.0),
    "pa": ("pressure", 1.0), "kpa": ("pressure", 1000.0),
    "mpa": ("pressure", 1_000_000.0), "bar": ("pressure", 100_000.0),
    "psi": ("pressure", 6894.757293168),
    "j": ("energy", 1.0), "kj": ("energy", 1000.0),
    "mj": ("energy", 1_000_000.0), "wh": ("energy", 3600.0),
    "kwh": ("energy", 3_600_000.0), "mwh": ("energy", 3_600_000_000.0),
    "btu": ("energy", 1055.05585262),
    "w": ("power", 1.0), "kw": ("power", 1000.0), "mw": ("power", 1_000_000.0),
}
UNIT_ALIASES = {"°c": "c", "degc": "c", "celsius": "c", "°f": "f", "degf": "f",
                "fahrenheit": "f", "°k": "k", "kelvin": "k"}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _workspace() -> str:
    try:
        import streamlit as st
        return str(st.session_state.get("shoir_workspace_name") or st.session_state.get("workspace")
                   or st.session_state.get("active_workspace_name") or "default")
    except Exception:
        return "default"

def _actor() -> str:
    try:
        import streamlit as st
        return str(st.session_state.get("current_user") or "unknown")
    except Exception:
        return "unknown"

def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(value)).strip("_").lower() or "workbook"

def _excel_col(index_zero_based: int) -> str:
    n = int(index_zero_based) + 1
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result

def _excel_index(column: str) -> int:
    value = 0
    for ch in str(column).upper().strip():
        if not "A" <= ch <= "Z":
            raise ValueError(f"Invalid Excel column: {column}")
        value = value * 26 + (ord(ch) - 64)
    return value - 1

def _cell_parts(ref: str) -> tuple[int, int]:
    match = re.fullmatch(r"\$?([A-Za-z]{1,3})\$?(\d+)", str(ref).strip())
    if not match:
        raise ValueError(f"Invalid cell reference: {ref}")
    return _excel_index(match.group(1)), int(match.group(2)) - 1

def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    from_u = UNIT_ALIASES.get(str(from_unit).strip().lower(), str(from_unit).strip().lower())
    to_u = UNIT_ALIASES.get(str(to_unit).strip().lower(), str(to_unit).strip().lower())
    if from_u == to_u:
        return float(value)
    if {from_u, to_u} <= {"c", "f", "k"}:
        x = float(value)
        k = x + 273.15 if from_u == "c" else (x - 32.0) * 5.0 / 9.0 + 273.15 if from_u == "f" else x
        return k - 273.15 if to_u == "c" else (k - 273.15) * 9.0 / 5.0 + 32.0 if to_u == "f" else k
    if from_u not in UNIT_DEFS or to_u not in UNIT_DEFS:
        raise ValueError(f"Unsupported unit conversion: {from_unit} → {to_unit}")
    from_dim, from_factor = UNIT_DEFS[from_u]
    to_dim, to_factor = UNIT_DEFS[to_u]
    if from_dim != to_dim:
        raise ValueError(f"Incompatible unit dimensions: {from_unit} and {to_unit}")
    return float(value) * from_factor / to_factor

def infer_units(column: str) -> list[str]:
    name = str(column).lower().replace("_", " ")
    if any(x in name for x in ("kwh", "energy")): return ["kWh", "MWh", "J", "MJ"]
    if any(x in name for x in ("power", "kw", "mw")): return ["kW", "MW", "W"]
    if any(x in name for x in ("pressure", "psi", "bar", "mpa")): return ["bar", "kPa", "MPa", "psi", "Pa"]
    if any(x in name for x in ("temperature", "temp")): return ["°C", "°F", "K"]
    if any(x in name for x in ("distance", "length", "travel", "height", "width")): return ["m", "cm", "mm", "ft", "in", "km"]
    if any(x in name for x in ("weight", "mass", "load")): return ["kg", "g", "t", "lb"]
    if any(x in name for x in ("time", "duration", "cycle", "lead")): return ["min", "h", "s", "day"]
    return []

def _flatten(values: Any) -> list[Any]:
    if isinstance(values, (list, tuple, np.ndarray, pd.Series)):
        out: list[Any] = []
        for item in list(values): out.extend(_flatten(item))
        return out
    return [values]

def _numeric(values: Any) -> list[float]:
    result = []
    for item in _flatten(values):
        if isinstance(item, (bool, np.bool_)): continue
        try: number = float(item)
        except (TypeError, ValueError): continue
        if math.isfinite(number): result.append(number)
    return result

def _excel_aggregate(name: str, values: Any) -> float:
    nums = _numeric(values)
    if name == "SUM": return float(sum(nums))
    if name == "AVERAGE": return float(sum(nums) / len(nums)) if nums else math.nan
    if name == "MIN": return float(min(nums)) if nums else math.nan
    if name == "MAX": return float(max(nums)) if nums else math.nan
    if name == "COUNT": return float(len(nums))
    if name == "COUNTA": return float(sum(x not in (None, "") for x in _flatten(values)))
    raise ValueError(name)

_ALLOWED_FUNCS = {"ABS","AVERAGE","COUNT","COUNTA","IF","IFERROR","MAX","MIN",
                  "MOD","NOT","OR","AND","POWER","ROUND","SQRT","SUM",
                  "OEE","TAKTTIME","LITTLELAW","CPK","PPK","EOQ","SAFETYSTOCK","NPV","CO2E","CONVERT"}

class SafeFormulaEngine:
    def __init__(
        self,
        workbook: Mapping[str, pd.DataFrame],
        formulas: Mapping[str, Mapping[str, str]] | None = None,
        variables: Mapping[str, Any] | None = None,
    ):
        self.workbook = workbook
        self.formulas = formulas or {}
        self.variables = {
            str(k).strip(): (
                v.get("value") if isinstance(v, Mapping) and "value" in v else v
            )
            for k, v in (variables or {}).items()
            if str(k).strip()
        }
        self._stack: set[tuple[str, str]] = set()
        self._current_sheet = ""

    def evaluate(self, expression: str, sheet: str) -> Any:
        raw = str(expression or "").strip()
        if not raw: return ""
        if raw.startswith("="): raw = raw[1:].strip()
        raw = raw.replace("^", "**").replace("<>", "!=").replace(";", ",")
        tree = ast.parse(self._replace_refs(raw), mode="eval")
        return self._eval_node(tree.body, sheet)

    def _replace_refs(self, expression: str) -> str:
        placeholders: dict[str, str] = {}
        counter = 0
        def save(token: str) -> str:
            nonlocal counter
            key = f"__REF_{counter}__"; counter += 1; placeholders[key] = token; return key
        def cross(match: re.Match[str]) -> str:
            sheet_name = match.group(1)
            start = f"{match.group(2)}{match.group(3)}"
            end = f"{match.group(4)}{match.group(5)}" if match.group(4) else None
            ref = start if not end else start + ":" + end
            call = f"_RANGE({sheet_name!r},{ref!r})" if end else f"_CELL({sheet_name!r},{start!r})"
            return save(call)
        expression = re.sub(r"'([^']+)'!\$?([A-Za-z]{1,3})\$?(\d+)(?::\$?([A-Za-z]{1,3})\$?(\d+))?", cross, expression)
        def cross_unquoted(match: re.Match[str]) -> str:
            sheet_name = match.group(1)
            start = f"{match.group(2)}{match.group(3)}"
            end = f"{match.group(4)}{match.group(5)}" if match.group(4) else None
            ref = start if not end else start + ":" + end
            call = f"_RANGE({sheet_name!r},{ref!r})" if end else f"_CELL({sheet_name!r},{start!r})"
            return save(call)
        expression = re.sub(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)!\$?([A-Za-z]{1,3})\$?(\d+)(?::\$?([A-Za-z]{1,3})\$?(\d+))?", cross_unquoted, expression)
        expression = re.sub(r"(?<![A-Za-z_])\$?([A-Za-z]{1,3})\$?(\d+):\$?([A-Za-z]{1,3})\$?(\d+)",
                             lambda m: save(f"_RANGE(None,{(m.group(1)+m.group(2)+':'+m.group(3)+m.group(4))!r})"), expression)
        expression = re.sub(r"(?<![A-Za-z0-9_])\$?([A-Za-z]{1,3})\$?(\d+)",
                             lambda m: save(f"_CELL(None,{(m.group(1)+m.group(2))!r})"), expression)
        for token, replacement in placeholders.items(): expression = expression.replace(token, replacement)
        return expression

    def _cell(self, sheet: str | None, ref: str) -> Any:
        target = str(sheet or self._current_sheet)
        key = (target, ref.upper())
        if key in self._stack: raise ValueError(f"Circular formula reference detected at {target}!{ref}")
        if target not in self.workbook: raise KeyError(f"Unknown worksheet: {target}")
        df = self.workbook[target]
        col, row = _cell_parts(ref)
        if not (0 <= row < len(df) and 0 <= col < len(df.columns)): return 0
        formula = str(self.formulas.get(target, {}).get(ref.upper(), "") or "").strip()
        if formula.startswith("="):
            self._stack.add(key)
            try:
                self._current_sheet = target
                return self.evaluate(formula, target)
            finally:
                self._stack.discard(key)
        value = df.iloc[row, col]
        return 0 if pd.isna(value) else value

    def _range(self, sheet: str | None, ref_range: str) -> list[Any]:
        target = str(sheet or self._current_sheet)
        start, end = str(ref_range).split(":", 1) if ":" in str(ref_range) else (str(ref_range), str(ref_range))
        c1, r1 = _cell_parts(start); c2, r2 = _cell_parts(end)
        df = self.workbook.get(target)
        if df is None: raise KeyError(f"Unknown worksheet: {target}")
        return [self._cell(target, f"{_excel_col(col)}{row + 1}")
                for row in range(min(r1, r2), max(r1, r2)+1)
                for col in range(min(c1, c2), max(c1, c2)+1)
                if 0 <= row < len(df) and 0 <= col < len(df.columns)]

    def _eval_node(self, node: ast.AST, sheet: str) -> Any:
        self._current_sheet = sheet
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.Num): return node.n
        if isinstance(node, ast.List): return [self._eval_node(x, sheet) for x in node.elts]
        if isinstance(node, ast.Tuple): return tuple(self._eval_node(x, sheet) for x in node.elts)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
            value = self._eval_node(node.operand, sheet)
            return +value if isinstance(node.op, ast.UAdd) else -value if isinstance(node.op, ast.USub) else not bool(value)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)):
            left, right = self._eval_node(node.left, sheet), self._eval_node(node.right, sheet)
            return {ast.Add: lambda:left+right, ast.Sub:lambda:left-right, ast.Mult:lambda:left*right,
                    ast.Div:lambda:left/right, ast.Mod:lambda:left%right, ast.Pow:lambda:left**right}[type(node.op)]()
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            if isinstance(node.op, ast.And):
                value = True
                for child in node.values:
                    value = self._eval_node(child, sheet)
                    if not bool(value): return value
                return value
            for child in node.values:
                value = self._eval_node(child, sheet)
                if bool(value): return value
            return False
        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, sheet)
            for op, comp in zip(node.ops, node.comparators):
                right = self._eval_node(comp, sheet)
                if isinstance(op, ast.Eq): passed = left == right
                elif isinstance(op, ast.NotEq): passed = left != right
                elif isinstance(op, ast.Lt): passed = left < right
                elif isinstance(op, ast.LtE): passed = left <= right
                elif isinstance(op, ast.Gt): passed = left > right
                elif isinstance(op, ast.GtE): passed = left >= right
                elif isinstance(op, ast.In): passed = left in right
                elif isinstance(op, ast.NotIn): passed = left not in right
                else: raise ValueError(f"Unsupported comparison operator: {type(op).__name__}")
                if not passed: return False
                left = right
            return True
        if isinstance(node, ast.Name):
            if node.id.upper() == "PI": return math.pi
            if node.id in self.variables:
                return self.variables[node.id]
            if node.id.upper() in {str(k).upper() for k in self.variables}:
                target = next(k for k in self.variables if k.upper() == node.id.upper())
                return self.variables[target]
            raise ValueError(f"Unknown name in formula: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name): raise ValueError("Only named functions are allowed.")
            name = node.func.id.upper()
            if name == "_CELL":
                s = self._eval_node(node.args[0], sheet); ref = str(self._eval_node(node.args[1], sheet))
                return self._cell(None if s is None or s == "None" else str(s), ref)
            if name == "_RANGE":
                s = self._eval_node(node.args[0], sheet); ref = str(self._eval_node(node.args[1], sheet))
                return self._range(None if s is None or s == "None" else str(s), ref)
            if name not in _ALLOWED_FUNCS: raise ValueError(f"Function is not allowed: {name}")
            if name == "IF":
                if len(node.args) < 2: raise ValueError("IF requires a condition and true value.")
                condition = self._eval_node(node.args[0], sheet)
                return self._eval_node(node.args[1] if bool(condition) else (node.args[2] if len(node.args)>2 else ast.Constant(value=False)), sheet)
            if name == "IFERROR":
                if len(node.args) < 2: raise ValueError("IFERROR requires a value and fallback.")
                try: return self._eval_node(node.args[0], sheet)
                except Exception: return self._eval_node(node.args[1], sheet)
            args = [self._eval_node(x, sheet) for x in node.args]
            if name in {"SUM","AVERAGE","MIN","MAX","COUNT","COUNTA"}: return _excel_aggregate(name, args)
            if name == "ABS": return abs(float(args[0]))
            if name == "SQRT": return math.sqrt(float(args[0]))
            if name == "POWER": return float(args[0]) ** float(args[1])
            if name == "ROUND": return round(float(args[0]), int(args[1]) if len(args)>1 else 0)
            if name == "MOD": return float(args[0]) % float(args[1])
            if name == "NOT": return not bool(args[0])
            if name == "AND": return all(bool(x) for x in args)
            if name == "OR": return any(bool(x) for x in args)
            if name in {"OEE","TAKTTIME","LITTLELAW","CPK","PPK","EOQ","SAFETYSTOCK","NPV","CO2E","CONVERT"}:
                from shoir_adoption_engine import evaluate_engineering_function
                return evaluate_engineering_function(name, args)
        raise ValueError(f"Unsupported formula expression: {ast.dump(node, include_attributes=False)}")

def evaluate_workbook_formulas(
    workbook: Mapping[str,pd.DataFrame],
    formulas: Mapping[str,Mapping[str,str]],
    variables: Mapping[str,Any] | None = None,
) -> tuple[dict[str,pd.DataFrame],pd.DataFrame]:
    result = {sheet: frame.copy(deep=True) for sheet,frame in workbook.items()}
    engine = SafeFormulaEngine(result, formulas, variables=variables)
    audit = []
    for sheet, sheet_formulas in formulas.items():
        if sheet not in result: continue
        for ref, formula in sheet_formulas.items():
            try:
                col, row = _cell_parts(ref)
                if row >= len(result[sheet]) or col >= len(result[sheet].columns):
                    audit.append({"Sheet":sheet,"Cell":ref,"Formula":formula,"Status":"Error","Detail":"Cell is outside the current sheet range."})
                    continue
                engine._current_sheet = sheet
                value = engine.evaluate(formula, sheet)
                result[sheet].iat[row,col] = value
                audit.append({"Sheet":sheet,"Cell":ref,"Formula":formula,"Status":"Calculated","Detail":str(value)})
            except Exception as exc:
                audit.append({"Sheet":sheet,"Cell":ref,"Formula":formula,"Status":"Error","Detail":f"{type(exc).__name__}: {exc}"})
    return result, pd.DataFrame(audit)

def infer_semantic_roles(df: pd.DataFrame) -> pd.DataFrame:
    try:
        from shoir_digital_thread import CANONICAL_FIELD_ALIASES
    except Exception:
        CANONICAL_FIELD_ALIASES = {
            "Asset":("asset","machine","equipment"),"Process":("process","operation"),
            "Product":("product","sku","part"),"Material":("material","component"),
            "Order":("order","work_order"),"Workforce":("operator","employee","worker"),
            "Quality":("quality","defect","scrap"),"Maintenance":("maintenance","failure","downtime"),
            "Energy":("energy","kwh","power"),"Cost":("cost","price","opex","capex"),
            "Scenario":("scenario","variant","alternative"),"Decision":("decision","recommendation"),
            "Outcome":("outcome","actual","result"),
        }
    rows=[]
    for column in df.columns:
        name=str(column).lower().replace("_"," ").replace("-"," ")
        candidates=[]
        for canonical,aliases in CANONICAL_FIELD_ALIASES.items():
            score=sum(2 if str(alias).replace("_"," ").lower()==name else 1 for alias in aliases if str(alias).replace("_"," ").lower() in name)
            if score: candidates.append((score,canonical))
        candidates.sort(key=lambda x:(-x[0],x[1]))
        rows.append({"Column":str(column),"Suggested Role":candidates[0][1] if candidates else "Dataset",
                     "Confidence":min(1.0,candidates[0][0]/2.0) if candidates else 0.25,
                     "Unit Hints":", ".join(infer_units(str(column)))})
    return pd.DataFrame(rows)

def semantic_relationships(mapping_df: pd.DataFrame, sheet: str) -> pd.DataFrame:
    if mapping_df.empty: return pd.DataFrame(columns=["Source","Source Type","Relation","Target","Target Type"])
    return pd.DataFrame([{"Source":f"{sheet}.{row['Column']}","Source Type":"Dataset","Relation":"semantic column",
                          "Target":str(row["Suggested Role"]),"Target Type":str(row["Suggested Role"])}
                         for row in mapping_df.to_dict("records") if str(row.get("Suggested Role","")) in CANONICAL_TYPES])

def validate_workbook(workbook: Mapping[str,pd.DataFrame]) -> dict[str,Any]:
    sheets=[]; total_rows=total_cells=missing_cells=duplicate_columns=duplicate_rows=0
    for name,df in workbook.items():
        if not isinstance(df,pd.DataFrame):
            sheets.append({"Sheet":name,"Status":"Error","Rows":0,"Columns":0,"Missing":0,"Duplicates":0}); continue
        missing=int(df.isna().sum().sum()); dup_rows=int(df.duplicated().sum()) if len(df) else 0
        dup_cols=int(df.columns.duplicated().sum()); total_rows+=len(df); total_cells+=int(df.size)
        missing_cells+=missing; duplicate_columns+=dup_cols; duplicate_rows+=dup_rows
        sheets.append({"Sheet":str(name),"Status":"Ready" if len(df) else "Empty","Rows":int(len(df)),
                       "Columns":int(len(df.columns)),"Missing":missing,"Duplicates":dup_rows})
    health=max(0.0,min(100.0,100.0-100.0*missing_cells/max(1,total_cells)-10.0*duplicate_columns-5.0*duplicate_rows/max(1,total_rows)))
    return {"sheets":len(workbook),"rows":total_rows,"cells":total_cells,"missing_cells":missing_cells,
            "duplicate_rows":duplicate_rows,"duplicate_columns":duplicate_columns,"health":round(health,1),
            "sheet_summary":pd.DataFrame(sheets)}

def instant_analyze(df: pd.DataFrame) -> dict[str,Any]:
    if not isinstance(df,pd.DataFrame) or df.empty: return {"profile":pd.DataFrame(),"recommendations":["Load a table first."],"figure":None}
    numeric=[str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    categorical=[str(c) for c in df.columns if not pd.api.types.is_numeric_dtype(df[c])]
    profile=[]
    for col in df.columns:
        s=df[col]; profile.append({"Column":str(col),"Type":str(s.dtype),"Non-null":int(s.notna().sum()),
                                   "Missing %":round(float(s.isna().mean()*100),2),"Unique":int(s.nunique(dropna=True)),
                                   "Sample":str(s.dropna().iloc[0])[:80] if s.notna().any() else ""})
    recommendations=[]; figure=None
    if numeric:
        metric=numeric[0]
        if categorical:
            category=categorical[0]; recommendations.append(f"Compare {metric} by {category}.")
            work=df[[category,metric]].dropna().copy()
            if not work.empty:
                grouped=work.groupby(category,as_index=False)[metric].mean().sort_values(metric,ascending=False).head(25)
                figure=px.bar(grouped,x=category,y=metric,title=f"Instant Analyze · {metric} by {category}")
        else:
            recommendations.append(f"Inspect the distribution of {metric}.")
            figure=px.histogram(df,x=metric,nbins=30,title=f"Instant Analyze · {metric}")
        if len(numeric)>=2: recommendations.append(f"Check the relationship between {numeric[0]} and {numeric[1]}.")
        recommendations.append("Run validation before using the table as decision evidence.")
    else:
        recommendations.append("Profile categorical structure and map columns into the Digital Thread.")
    return {"profile":pd.DataFrame(profile),"recommendations":recommendations[:5],"figure":figure}

def apply_query_pipeline(df:pd.DataFrame, steps:Sequence[Mapping[str,Any]])->pd.DataFrame:
    work=df.copy(deep=True)
    for step in steps:
        kind=str(step.get("type","")).strip()
        if kind=="select":
            cols=[c for c in step.get("columns",[]) if c in work.columns]; work=work[cols].copy()
        elif kind=="rename":
            source,target=str(step.get("source","")),str(step.get("target",""))
            if source not in work.columns: raise KeyError(f"Column not found: {source}")
            if not target: raise ValueError("A target column name is required.")
            work=work.rename(columns={source:target})
        elif kind=="drop_duplicates":
            subset=[c for c in step.get("columns",[]) if c in work.columns] or None
            work=work.drop_duplicates(subset=subset).reset_index(drop=True)
        elif kind=="fill_missing":
            col=str(step.get("column","")); 
            if col not in work.columns: raise KeyError(f"Column not found: {col}")
            value=step.get("value",""); work[col]=work[col].fillna(value)
        elif kind=="cast_numeric":
            col=str(step.get("column","")); 
            if col not in work.columns: raise KeyError(f"Column not found: {col}")
            work[col]=pd.to_numeric(work[col],errors="coerce")
        elif kind=="sort":
            col=str(step.get("column",""))
            if col not in work.columns: raise KeyError(f"Column not found: {col}")
            work=work.sort_values(col,ascending=not bool(step.get("descending",False)),kind="stable").reset_index(drop=True)
        elif kind=="filter":
            col,op=str(step.get("column","")),str(step.get("op","==")); raw=step.get("value","")
            if col not in work.columns: raise KeyError(f"Column not found: {col}")
            s_num=pd.to_numeric(work[col],errors="coerce")
            try: rhs=float(raw); left=s_num
            except (TypeError,ValueError): rhs=str(raw); left=work[col].astype("string")
            mask={"==":left==rhs,"!=":left!=rhs,">":left>rhs,">=":left>=rhs,"<":left<rhs,"<=":left<=rhs,
                  "contains":left.astype("string").str.contains(str(rhs),case=False,na=False)}.get(op)
            if mask is None: raise ValueError(f"Unsupported filter operator: {op}")
            work=work.loc[mask].copy()
        elif kind=="groupby":
            groups=[c for c in step.get("columns",[]) if c in work.columns]; value_col=str(step.get("value_column",""))
            agg=str(step.get("aggregation","sum")).lower()
            if not groups or value_col not in work.columns: raise ValueError("Group By requires grouping columns and a value column.")
            metric=pd.to_numeric(work[value_col],errors="coerce")
            grouped=work.assign(__value=metric).groupby(groups,dropna=False)["__value"]
            out={"mean":grouped.mean(),"count":grouped.size(),"min":grouped.min(),"max":grouped.max(),"median":grouped.median(),"std":grouped.std(ddof=1)}.get(agg,grouped.sum())
            work=out.reset_index(name=f"{agg.title()} {value_col}")
        elif kind=="pivot":
            from shoir_adoption_engine import industrial_pivot
            work=industrial_pivot(
                work,
                index=step.get("index", step.get("rows", [])),
                columns=step.get("columns") or None,
                values=step.get("values", step.get("value_column", "")),
                aggfunc=step.get("aggregation", "sum"),
                fill_value=step.get("fill_value"),
            )
        elif kind=="add_formula":
            target,expression=str(step.get("target","")),str(step.get("expression",""))
            if not target or not expression: raise ValueError("Add Formula requires a target and expression.")
            work[target]=[_evaluate_row_expression(expression,row) for row in work.to_dict("records")]
        else:
            raise ValueError(f"Unknown query step: {kind}")
    return work

def _evaluate_row_expression(expression:str,row:Mapping[str,Any])->Any:
    expr=str(expression).strip(); expr=expr[1:].strip() if expr.startswith("=") else expr
    expr=expr.replace("^","**").replace("<>","!="); tree=ast.parse(expr,mode="eval")
    def walk(node:ast.AST)->Any:
        if isinstance(node,ast.Constant): return node.value
        if isinstance(node,ast.Name):
            if node.id in row: return row[node.id]
            if node.id.upper()=="PI": return math.pi
            raise ValueError(f"Unknown column in expression: {node.id}")
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub,ast.Not)):
            value=walk(node.operand); return +value if isinstance(node.op,ast.UAdd) else -value if isinstance(node.op,ast.USub) else not bool(value)
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Mod,ast.Pow)):
            a,b=walk(node.left),walk(node.right)
            return {ast.Add:lambda:a+b,ast.Sub:lambda:a-b,ast.Mult:lambda:a*b,ast.Div:lambda:a/b,ast.Mod:lambda:a%b,ast.Pow:lambda:a**b}[type(node.op)]()
        if isinstance(node,ast.Compare):
            a=walk(node.left)
            for op,comp in zip(node.ops,node.comparators):
                b=walk(comp)
                if isinstance(op, ast.Eq): ok = a == b
                elif isinstance(op, ast.NotEq): ok = a != b
                elif isinstance(op, ast.Lt): ok = a < b
                elif isinstance(op, ast.LtE): ok = a <= b
                elif isinstance(op, ast.Gt): ok = a > b
                elif isinstance(op, ast.GtE): ok = a >= b
                else: raise ValueError("Unsupported comparison")
                if not ok: return False
                a=b
            return True
        if isinstance(node,ast.BoolOp) and isinstance(node.op,(ast.And,ast.Or)):
            vals=[walk(x) for x in node.values]; return all(vals) if isinstance(node.op,ast.And) else any(vals)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
            name=node.func.id.upper(); args=[walk(x) for x in node.args]
            if name=="ABS": return abs(float(args[0]))
            if name=="SQRT": return math.sqrt(float(args[0]))
            if name=="POWER": return float(args[0])**float(args[1])
            if name=="ROUND": return round(float(args[0]),int(args[1]) if len(args)>1 else 0)
            if name=="MIN": return min(_numeric(args)) if _numeric(args) else math.nan
            if name=="MAX": return max(_numeric(args)) if _numeric(args) else math.nan
            if name=="SUM": return sum(_numeric(args))
            if name=="AVERAGE":
                nums=_numeric(args); return sum(nums)/len(nums) if nums else math.nan
            if name=="IF": return args[1] if bool(args[0]) else (args[2] if len(args)>2 else False)
            raise ValueError(f"Unsupported function: {name}")
        raise ValueError(f"Unsupported expression node: {ast.dump(node,include_attributes=False)}")
    return walk(tree.body)

@dataclass(frozen=True)
class WorkbookExtension:
    name:str; version:str; category:str; description:str
    transform:Callable[[pd.DataFrame],pd.DataFrame]|None=None

_EXTENSION_REGISTRY:dict[str,WorkbookExtension]={}

def register_workbook_extension(extension:WorkbookExtension)->None:
    if not extension.name.strip(): raise ValueError("Extension name is required.")
    _EXTENSION_REGISTRY[extension.name]=extension
    # Reuse Shoir-IE's existing plugin registry rather than creating a second
    # extension catalog. The adapter remains metadata-only unless a transform
    # function is explicitly installed.
    try:
        from plugin_registry import PluginSpec, register_plugin
        register_plugin(
            PluginSpec(
                name="Workbook Extension · " + extension.name,
                category="Workbook",
                version=extension.version,
                description=extension.description,
            ),
            handler=(lambda df, _name=extension.name: run_workbook_extension(_name, df))
                if extension.transform is not None else None,
        )
    except Exception:
        pass

def list_workbook_extensions()->list[WorkbookExtension]:
    return list(_EXTENSION_REGISTRY.values())

def run_workbook_extension(name:str,df:pd.DataFrame)->pd.DataFrame:
    ext=_EXTENSION_REGISTRY.get(name)
    if ext is None: raise KeyError(f"Unknown workbook extension: {name}")
    if ext.transform is None: raise RuntimeError(f"Extension '{name}' is metadata-only until a transform is installed.")
    result=ext.transform(df.copy(deep=True))
    if not isinstance(result,pd.DataFrame): raise TypeError("Workbook extension must return a pandas DataFrame.")
    return result

def _starter_templates()->dict[str,dict[str,Any]]:
    return {
        "OEE Starter":{"category":"Operations","description":"Availability, performance and quality inputs for an OEE study.",
                       "data":pd.DataFrame({"Asset":["Line-01","Line-02","Line-03"],"Availability":[0.92,0.88,0.95],"Performance":[0.90,0.84,0.93],"Quality":[0.98,0.97,0.99]})},
        "Quality Pareto":{"category":"Quality","description":"Defect categories and counts ready for Pareto analysis.",
                          "data":pd.DataFrame({"Defect":["Scratch","Void","Crack","Dimension","Other"],"Count":[42,27,18,12,7]})},
        "Inventory Reorder":{"category":"Inventory","description":"SKU demand, lead time and reorder-point inputs.",
                             "data":pd.DataFrame({"SKU":["SKU-001","SKU-002","SKU-003"],"DailyDemand":[120,80,55],"LeadTimeDays":[5,8,4],"SafetyStock":[150,120,75]})},
        "Capacity Plan":{"category":"Planning","description":"Demand, capacity and utilization inputs for a finite-capacity study.",
                          "data":pd.DataFrame({"Workcenter":["WC-01","WC-02","WC-03"],"AvailableHours":[160,180,150],"RequiredHours":[144,171,132],"Utilization":[0.90,0.95,0.88]})},
        "Maintenance Risk":{"category":"Maintenance","description":"Asset telemetry columns suitable for existing predictive maintenance workflows.",
                            "data":pd.DataFrame({"Asset":["CNC-01","Press-02","Pump-04"],"Temperature":[62,71,58],"Vibration":[1.2,2.5,1.0],"RuntimeHours":[7200,9600,4800]})},
        "DOE Results":{"category":"Research","description":"A compact experiment-results table ready for statistical analysis.",
                       "data":pd.DataFrame({"Run":[1,2,3,4,5,6],"Factor_A":[0,0,0,1,1,1],"Factor_B":[0,1,1,0,0,1],"Response":[41,45,44,52,50,55]})},
    }

def ensure_workbook_db(path:str=DB_PATH)->None:
    with sqlite3.connect(path,timeout=30) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS industrial_workbooks(
            workbook_id TEXT PRIMARY KEY,workspace TEXT NOT NULL,owner TEXT NOT NULL,name TEXT NOT NULL,
            payload_b64 TEXT NOT NULL,formulas_json TEXT NOT NULL,semantic_map_json TEXT,variables_json TEXT NOT NULL DEFAULT '{}',
            sha256 TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
        try:
            conn.execute("ALTER TABLE industrial_workbooks ADD COLUMN variables_json TEXT NOT NULL DEFAULT '{}' ")
        except sqlite3.OperationalError:
            pass
        conn.execute("""CREATE TABLE IF NOT EXISTS industrial_workbook_versions(
            version_id TEXT PRIMARY KEY,workbook_id TEXT NOT NULL,workspace TEXT NOT NULL,owner TEXT NOT NULL,
            version_number INTEGER NOT NULL,label TEXT,payload_b64 TEXT NOT NULL,formulas_json TEXT NOT NULL,
            semantic_map_json TEXT,variables_json TEXT NOT NULL DEFAULT '{}',sha256 TEXT NOT NULL,created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS industrial_workbook_comments(
            comment_id TEXT PRIMARY KEY,workbook_id TEXT NOT NULL,workspace TEXT NOT NULL,owner TEXT NOT NULL,
            sheet TEXT NOT NULL,cell TEXT NOT NULL,comment TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS industrial_workbook_templates(
            template_id TEXT PRIMARY KEY,workspace TEXT NOT NULL,owner TEXT NOT NULL,name TEXT NOT NULL,
            category TEXT NOT NULL,description TEXT,payload_b64 TEXT NOT NULL,builtin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS industrial_workbook_queries(
            pipeline_id TEXT PRIMARY KEY,workspace TEXT NOT NULL,owner TEXT NOT NULL,name TEXT NOT NULL,
            source_sheet TEXT NOT NULL,steps_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS industrial_workbook_audit(
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,workbook_id TEXT,workspace TEXT,owner TEXT,
            action TEXT,details TEXT,created_at TEXT)""")
        conn.commit()

def _serialize_workbook(workbook:Mapping[str,pd.DataFrame])->bytes:
    payload=io.BytesIO()
    with pd.ExcelWriter(payload,engine="xlsxwriter") as writer:
        used=set()
        for raw_sheet,df in workbook.items():
            sheet=re.sub(r"[:\\\\/?*\\[\\]]+","",str(raw_sheet)).strip()[:31] or "Sheet1"
            base=sheet; idx=2
            while sheet in used:
                suffix=f" ({idx})"; sheet=(base[:31-len(suffix)]+suffix)[:31]; idx+=1
            used.add(sheet)
            df.copy(deep=True).to_excel(writer,index=False,sheet_name=sheet)
    return payload.getvalue()

def _deserialize_workbook(payload:bytes)->dict[str,pd.DataFrame]:
    book=pd.ExcelFile(io.BytesIO(payload))
    return {sheet:pd.read_excel(io.BytesIO(payload),sheet_name=sheet) for sheet in book.sheet_names}

def save_workbook(workbook:Mapping[str,pd.DataFrame],formulas:Mapping[str,Mapping[str,str]]|None=None,
                  semantic_map:Mapping[str,Any]|None=None,name:str="Industrial Workbook",workbook_id:str|None=None,
                  path:str=DB_PATH,variables:Mapping[str,Any]|None=None,version_label:str="Autosave")->str:
    ensure_workbook_db(path); formulas=formulas or {}; variables=variables or {}; payload=_serialize_workbook(workbook)
    digest=hashlib.sha256(payload).hexdigest(); wid=str(workbook_id or ("WB-"+uuid.uuid4().hex[:12].upper())); now=_now()
    workspace,owner=_workspace(),_actor()
    with sqlite3.connect(path,timeout=30) as conn:
        existing=conn.execute("SELECT sha256 FROM industrial_workbooks WHERE workbook_id=? AND workspace=?",(wid,workspace)).fetchone()
        conn.execute("""INSERT INTO industrial_workbooks(workbook_id,workspace,owner,name,payload_b64,formulas_json,
                        semantic_map_json,variables_json,sha256,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(workbook_id) DO UPDATE SET workspace=excluded.workspace,owner=excluded.owner,
                        name=excluded.name,payload_b64=excluded.payload_b64,formulas_json=excluded.formulas_json,
                        semantic_map_json=excluded.semantic_map_json,variables_json=excluded.variables_json,
                        sha256=excluded.sha256,updated_at=excluded.updated_at""",
                     (wid,workspace,owner,str(name)[:160],base64.b64encode(payload).decode("ascii"),
                      json.dumps({str(k):dict(v) for k,v in formulas.items()},default=str),
                      json.dumps(dict(semantic_map or {}),default=str),
                      json.dumps(dict(variables),default=str),digest,now,now))
        # Version history is content-addressed: repeated Streamlit reruns do not
        # create duplicate versions when the workbook payload and formulas are unchanged.
        if not existing or str(existing[0]) != digest:
            next_no=int(conn.execute("SELECT COALESCE(MAX(version_number),0)+1 FROM industrial_workbook_versions WHERE workbook_id=? AND workspace=?",(wid,workspace)).fetchone()[0])
            vid="VER-"+uuid.uuid4().hex[:12].upper()
            conn.execute("""INSERT INTO industrial_workbook_versions(
                version_id,workbook_id,workspace,owner,version_number,label,payload_b64,formulas_json,
                semantic_map_json,variables_json,sha256,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (vid,wid,workspace,owner,next_no,str(version_label or "Autosave")[:120],
                 base64.b64encode(payload).decode("ascii"),
                 json.dumps({str(k):dict(v) for k,v in formulas.items()},default=str),
                 json.dumps(dict(semantic_map or {}),default=str),json.dumps(dict(variables),default=str),
                 digest,now))
        conn.execute("INSERT INTO industrial_workbook_audit(workbook_id,workspace,owner,action,details,created_at) VALUES(?,?,?,?,?,?)",
                     (wid,workspace,owner,"save",f"{name} | {len(workbook)} sheet(s) | {len(payload):,} bytes | sha256={digest}",now))
        conn.commit()
    return wid

def load_workbook(workbook_id:str,path:str=DB_PATH)->tuple[dict[str,pd.DataFrame],dict[str,dict[str,str]],dict[str,Any]]:
    """Load a workbook using the original three-value API; variables are a separate metadata channel."""
    ensure_workbook_db(path)
    with sqlite3.connect(path,timeout=30) as conn:
        row=conn.execute(
            "SELECT payload_b64,formulas_json,semantic_map_json FROM industrial_workbooks WHERE workbook_id=? AND workspace=?",
            (workbook_id,_workspace()),
        ).fetchone()
    if not row: raise KeyError("Workbook not found in the current workspace.")
    return (_deserialize_workbook(base64.b64decode(row[0])),json.loads(row[1] or "{}"),json.loads(row[2] or "{}"))

def load_workbook_variables(workbook_id:str,path:str=DB_PATH)->dict[str,Any]:
    """Load named engineering variables without breaking the original load_workbook contract."""
    ensure_workbook_db(path)
    with sqlite3.connect(path,timeout=30) as conn:
        row=conn.execute(
            "SELECT COALESCE(variables_json,'{}') FROM industrial_workbooks WHERE workbook_id=? AND workspace=?",
            (workbook_id,_workspace()),
        ).fetchone()
    if not row: raise KeyError("Workbook not found in the current workspace.")
    return json.loads(row[0] or "{}")


def list_workbook_versions(workbook_id:str,path:str=DB_PATH)->pd.DataFrame:
    ensure_workbook_db(path)
    with sqlite3.connect(path,timeout=30) as conn:
        return pd.read_sql(
            """SELECT version_id AS ID, version_number AS Version, label AS Label,
                      sha256 AS SHA256, created_at AS Created
               FROM industrial_workbook_versions
               WHERE workbook_id=? AND workspace=?
               ORDER BY version_number DESC""",
            conn,params=(workbook_id,_workspace())
        )

def load_workbook_version(version_id:str,path:str=DB_PATH)->tuple[dict[str,pd.DataFrame],dict[str,dict[str,str]],dict[str,Any],dict[str,Any]]:
    ensure_workbook_db(path)
    with sqlite3.connect(path,timeout=30) as conn:
        row=conn.execute(
            """SELECT payload_b64,formulas_json,semantic_map_json,variables_json
               FROM industrial_workbook_versions WHERE version_id=? AND workspace=?""",
            (version_id,_workspace())
        ).fetchone()
    if not row: raise KeyError("Workbook version not found in the current workspace.")
    return (_deserialize_workbook(base64.b64decode(row[0])),json.loads(row[1] or "{}"),
            json.loads(row[2] or "{}"),json.loads(row[3] or "{}"))

def save_workbook_comment(workbook_id:str,sheet:str,cell:str,comment:str,path:str=DB_PATH)->str:
    ensure_workbook_db(path)
    comment_text=str(comment or "").strip()
    if not comment_text: raise ValueError("Comment text is required.")
    _cell_parts(cell)
    cid="CMT-"+uuid.uuid4().hex[:10].upper()
    with sqlite3.connect(path,timeout=30) as conn:
        conn.execute(
            """INSERT INTO industrial_workbook_comments(
               comment_id,workbook_id,workspace,owner,sheet,cell,comment,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (cid,workbook_id,_workspace(),_actor(),str(sheet)[:160],str(cell).upper(),comment_text[:2000],_now(),_now())
        )
        conn.commit()
    return cid

def list_workbook_comments(workbook_id:str,path:str=DB_PATH)->pd.DataFrame:
    ensure_workbook_db(path)
    with sqlite3.connect(path,timeout=30) as conn:
        return pd.read_sql(
            """SELECT comment_id AS ID,sheet AS Sheet,cell AS Cell,comment AS Comment,
                      owner AS Author,created_at AS Created
               FROM industrial_workbook_comments
               WHERE workbook_id=? AND workspace=? ORDER BY created_at DESC""",
            conn,params=(workbook_id,_workspace())
        )


def list_saved_workbooks(path:str=DB_PATH)->pd.DataFrame:
    ensure_workbook_db(path)
    with sqlite3.connect(path,timeout=30) as conn:
        return pd.read_sql("SELECT workbook_id AS ID,name AS Name,owner AS Owner,updated_at AS Updated,sha256 AS SHA256 FROM industrial_workbooks WHERE workspace=? ORDER BY updated_at DESC",
                           conn,params=(_workspace(),))

def save_template(name:str,category:str,description:str,workbook:Mapping[str,pd.DataFrame],path:str=DB_PATH)->str:
    ensure_workbook_db(path); payload=_serialize_workbook(workbook); tid="TPL-"+uuid.uuid4().hex[:10].upper()
    with sqlite3.connect(path,timeout=30) as conn:
        conn.execute("INSERT INTO industrial_workbook_templates(template_id,workspace,owner,name,category,description,payload_b64,builtin,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (tid,_workspace(),_actor(),str(name)[:160],str(category)[:80],str(description)[:500],
                      base64.b64encode(payload).decode("ascii"),0,_now(),_now())); conn.commit()
    return tid

def list_templates(path:str=DB_PATH)->pd.DataFrame:
    ensure_workbook_db(path)
    built=[{"ID":"builtin:"+_slug(n),"Name":n,"Category":d["category"],"Description":d["description"],"Source":"Shoir-IE built-in"} for n,d in _starter_templates().items()]
    with sqlite3.connect(path,timeout=30) as conn:
        try:
            custom=pd.read_sql("SELECT template_id AS ID,name AS Name,category AS Category,description AS Description,'Workspace library' AS Source FROM industrial_workbook_templates WHERE workspace=? ORDER BY updated_at DESC",
                               conn,params=(_workspace(),))
        except Exception: custom=pd.DataFrame()
    frames=[pd.DataFrame(built)]; 
    if not custom.empty: frames.append(custom)
    return pd.concat(frames,ignore_index=True)

def load_template(template_id:str,path:str=DB_PATH)->tuple[str,dict[str,pd.DataFrame]]:
    if str(template_id).startswith("builtin:"):
        target=str(template_id).split(":",1)[1]
        for name,data in _starter_templates().items():
            if _slug(name)==target: return name,{"Sheet1":data["data"].copy(deep=True)}
        raise KeyError("Built-in template not found.")
    ensure_workbook_db(path)
    with sqlite3.connect(path,timeout=30) as conn:
        row=conn.execute("SELECT name,payload_b64 FROM industrial_workbook_templates WHERE template_id=? AND workspace=?",(template_id,_workspace())).fetchone()
    if not row: raise KeyError("Template not found.")
    return str(row[0]),_deserialize_workbook(base64.b64decode(row[1]))

def save_query_pipeline(name:str,source_sheet:str,steps:Sequence[Mapping[str,Any]],path:str=DB_PATH)->str:
    ensure_workbook_db(path); pid="Q-"+uuid.uuid4().hex[:10].upper()
    with sqlite3.connect(path,timeout=30) as conn:
        conn.execute("INSERT INTO industrial_workbook_queries(pipeline_id,workspace,owner,name,source_sheet,steps_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                     (pid,_workspace(),_actor(),str(name)[:160],str(source_sheet)[:160],json.dumps(list(steps),default=str),_now(),_now())); conn.commit()
    return pid

def list_query_pipelines(path:str=DB_PATH)->pd.DataFrame:
    ensure_workbook_db(path)
    with sqlite3.connect(path,timeout=30) as conn:
        return pd.read_sql("SELECT pipeline_id AS ID,name AS Name,source_sheet AS Source,updated_at AS Updated FROM industrial_workbook_queries WHERE workspace=? ORDER BY updated_at DESC",
                           conn,params=(_workspace(),))

def stream_profile_csv(raw: bytes, chunksize: int = 50_000) -> dict[str, Any]:
    """Profile a CSV in chunks without materializing the whole table."""
    if not raw: raise ValueError("The CSV payload is empty.")
    total_rows=total_missing=0; columns=[]; numeric_min={}; numeric_max={}
    for chunk in pd.read_csv(io.BytesIO(raw), chunksize=max(1,int(chunksize))):
        if not columns: columns=[str(x) for x in chunk.columns]
        total_rows += int(len(chunk)); total_missing += int(chunk.isna().sum().sum())
        for col in chunk.select_dtypes(include=np.number).columns:
            vals=pd.to_numeric(chunk[col],errors="coerce").dropna()
            if vals.empty: continue
            name=str(col); numeric_min[name]=min(numeric_min.get(name,float(vals.min())),float(vals.min()))
            numeric_max[name]=max(numeric_max.get(name,float(vals.max())),float(vals.max()))
    return {"mode":"streaming","rows":total_rows,"columns":len(columns),"missing_cells":total_missing,
            "columns_sample":columns[:80],"numeric_min":numeric_min,"numeric_max":numeric_max}

def stream_query_csv(raw: bytes, steps: Sequence[Mapping[str, Any]], chunksize: int = 50_000) -> pd.DataFrame:
    """Apply safe query steps chunk-by-chunk and concatenate results."""
    outputs=[apply_query_pipeline(chunk,steps) for chunk in pd.read_csv(io.BytesIO(raw),chunksize=max(1,int(chunksize)))]
    return pd.concat(outputs,ignore_index=True) if outputs else pd.DataFrame()

def instant_runtime_profile(df:pd.DataFrame)->dict[str,Any]:
    cells=int(df.size)
    mode="interactive" if cells<=250_000 else "vectorized" if cells<=2_000_000 else "large-table"
    return {"mode":mode,"rows":int(len(df)),"columns":int(len(df.columns)),"cells":cells,
            "memory_mb":round(float(df.memory_usage(deep=True).sum())/(1024*1024),2),
            "execution_note":"Use vectorized pandas operations and query pipelines for large tables; keep cell-level formula editing for interactive workbooks."}

def _copilot_edit(prompt:str,workbook:dict[str,pd.DataFrame],sheet:str)->tuple[dict[str,pd.DataFrame],str]:
    text=str(prompt or "").strip()
    if not text: raise ValueError("Describe the workbook edit.")
    df=workbook[sheet].copy(deep=True)
    patterns=[
        (r"rename\s+(?:column\s+)?['\"]?([^'\"]+?)['\"]?\s+(?:to|as)\s+['\"]?([^'\"]+)['\"]?$","rename"),
        (r"(?:drop|delete|remove)\s+(?:column\s+)?['\"]?([^'\"]+?)['\"]?$","drop"),
        (r"sort\s+by\s+['\"]?([^'\"]+?)['\"]?(?:\s+(ascending|descending))?$","sort"),
        (r"fill\s+missing\s+(?:in\s+)?['\"]?([^'\"]+?)['\"]?\s+with\s+(.+)$","fill"),
        (r"filter\s+['\"]?([^'\"]+?)['\"]?\s*(==|!=|>=|<=|>|<|contains)\s*(.+)$","filter"),
        (r"add\s+(?:a\s+)?column\s+['\"]?([^'\"]+?)['\"]?\s*(?:=|with)\s*(.+)$","add"),
    ]
    for pattern,kind in patterns:
        m=re.search(pattern,text,re.I)
        if not m: continue
        if kind=="rename" and m.group(1).strip() in df.columns:
            src,dst=m.group(1).strip(),m.group(2).strip(); workbook[sheet]=df.rename(columns={src:dst}); return workbook,f"Renamed column {src} → {dst}."
        if kind=="drop" and m.group(1).strip() in df.columns:
            col=m.group(1).strip(); workbook[sheet]=df.drop(columns=[col]); return workbook,f"Removed column {col}."
        if kind=="sort" and m.group(1).strip() in df.columns:
            col=m.group(1).strip(); desc=str(m.group(2) or "").lower()=="descending"; workbook[sheet]=df.sort_values(col,ascending=not desc,kind="stable").reset_index(drop=True); return workbook,f"Sorted {col} {'descending' if desc else 'ascending'}."
        if kind=="fill" and m.group(1).strip() in df.columns:
            col=m.group(1).strip(); raw=m.group(2).strip().strip("'\"")
            try: value=float(raw) if any(ch in raw for ch in ".0123456789") and re.fullmatch(r"-?\d+(?:\.\d+)?",raw) else raw
            except Exception: value=raw
            df[col]=df[col].fillna(value); workbook[sheet]=df; return workbook,f"Filled missing values in {col}."
        if kind=="filter" and m.group(1).strip() in df.columns:
            result=apply_query_pipeline(df,[{"type":"filter","column":m.group(1).strip(),"op":m.group(2),"value":m.group(3).strip().strip("'\"")}])
            workbook[sheet]=result; return workbook,f"Filtered {m.group(1).strip()} using {m.group(2)}."
        if kind=="add":
            target,expr=m.group(1).strip(),m.group(2).strip()
            workbook[sheet]=apply_query_pipeline(df,[{"type":"add_formula","target":target,"expression":expr}]); return workbook,f"Added column {target} from a safe row expression."
    raise ValueError("Supported direct edits: rename, remove, sort, fill missing, filter, or add a formula column.")

def render_industrial_workbook(tier:str="Starter",username:str="unknown")->None:
    import streamlit as st
    ensure_workbook_db()
    st.session_state.setdefault(WORKBOOK_STATE_KEY,{"Sheet1":pd.DataFrame({"Item":["A","B","C","D"],"Quantity":[10,14,8,16],"Unit Cost":[12.5,9.5,14.0,11.0],"Total Cost":[125.0,133.0,112.0,176.0]})})
    st.session_state.setdefault(FORMULA_STATE_KEY,{"Sheet1":{}})
    st.session_state.setdefault("industrial_workbook_id",None)
    st.session_state.setdefault("industrial_workbook_undo",[])
    st.session_state.setdefault("industrial_workbook_redo",[])
    st.session_state.setdefault("industrial_workbook_query_steps",[])
    st.session_state.setdefault("industrial_workbook_semantic_map",{})
    st.session_state.setdefault("industrial_workbook_variables",{})
    st.session_state.setdefault("industrial_workbook_query_result_df",pd.DataFrame())
    st.session_state.setdefault("industrial_workbook_analysis_df",pd.DataFrame())
    st.session_state.setdefault("industrial_workbook_formula_audit_df",pd.DataFrame())
    wb:dict[str,pd.DataFrame]=st.session_state[WORKBOOK_STATE_KEY]
    formulas:dict[str,dict[str,str]]=st.session_state[FORMULA_STATE_KEY]
    variables:dict[str,Any]=st.session_state["industrial_workbook_variables"]
    st.markdown("""<style>
    .iw-hero{padding:26px 28px;border-radius:22px;background:linear-gradient(135deg,#081526,#1d3c7a 52%,#0f766e);color:#fff;box-shadow:0 18px 50px rgba(15,23,42,.14);margin-bottom:14px}
    .iw-title{font-size:30px;font-weight:900;line-height:1.08}.iw-copy{font-size:13px;color:#dbeafe;margin-top:6px}.iw-chip{display:inline-block;padding:5px 9px;margin:6px 6px 0 0;border-radius:999px;background:rgba(255,255,255,.09);border:1px solid rgba(255,255,255,.12);font-size:11px}
    @media (max-width:800px){.iw-title{font-size:23px}.block-container{padding-left:1rem;padding-right:1rem}.iw-copy{font-size:12px}}
    </style><div class="iw-hero"><div class="iw-chip">INDUSTRIAL WORKBOOK</div><div class="iw-chip">EXCEL INTEROPERABLE</div><div class="iw-chip">DIGITAL THREAD AWARE</div><div class="iw-title">Work the way engineers already work.</div><div class="iw-copy">Editable sheets → formulas → data preparation → instant analysis → engineering workflows → governed evidence.</div></div>""",unsafe_allow_html=True)

    current_sheet=st.selectbox("Sheet",list(wb.keys()),key="industrial_workbook_sheet")
    c1,c2,c3,c4,c5,c6=st.columns(6)
    uploaded=c1.file_uploader("Import .xlsx / .csv",type=["xlsx","csv"],key="industrial_workbook_upload")
    if c2.button("➕ Sheet",use_container_width=True):
        name=f"Sheet{len(wb)+1}"; wb[name]=pd.DataFrame({"Value":[None]}); formulas[name]={}; st.rerun()
    if c3.button("↶ Undo",disabled=not st.session_state["industrial_workbook_undo"],use_container_width=True):
        snap=st.session_state["industrial_workbook_undo"].pop(); st.session_state["industrial_workbook_redo"].append({k:v.copy(deep=True) for k,v in wb.items()})
        wb.clear(); wb.update({k:v.copy(deep=True) for k,v in snap.items()}); st.rerun()
    if c4.button("↷ Redo",disabled=not st.session_state["industrial_workbook_redo"],use_container_width=True):
        snap=st.session_state["industrial_workbook_redo"].pop(); st.session_state["industrial_workbook_undo"].append({k:v.copy(deep=True) for k,v in wb.items()})
        wb.clear(); wb.update({k:v.copy(deep=True) for k,v in snap.items()}); st.rerun()
    if c5.button("💾 Save",type="primary",use_container_width=True):
        try:
            wid=save_workbook(wb,formulas,st.session_state.get("industrial_workbook_semantic_map",{}),f"Shoir-IE Workbook · {current_sheet}",st.session_state.get("industrial_workbook_id"),variables=variables)
            st.session_state["industrial_workbook_id"]=wid; st.success(f"Saved workbook {wid}.")
        except Exception as exc: st.error(f"Workbook save failed safely: {exc}")
    saved=list_saved_workbooks()
    if c6.button("📂 Load saved",use_container_width=True): st.session_state["industrial_workbook_show_saved"]=True

    if uploaded is not None:
        try:
            upload_sig = hashlib.sha256(uploaded.getvalue()).hexdigest()
            if upload_sig != st.session_state.get("industrial_workbook_last_upload_signature"):
                from shoir_upgrade import read_uploaded_workbook
                loaded=read_uploaded_workbook(uploaded.getvalue(),uploaded.name)
                st.session_state["industrial_workbook_undo"].append({k: v.copy(deep=True) for k,v in wb.items()})
                st.session_state["industrial_workbook_undo"]=st.session_state["industrial_workbook_undo"][-20:]
                wb.clear(); wb.update({k: v.copy(deep=True) for k,v in loaded.items()})
                st.session_state[FORMULA_STATE_KEY]={k:{} for k in wb}
                st.session_state["industrial_workbook_redo"].clear()
                st.session_state["industrial_workbook_last_upload_signature"]=upload_sig
                st.success(f"Imported {len(loaded)} sheet(s) from {uploaded.name}.")
                st.rerun()
        except Exception as exc: st.error(f"Excel import failed safely: {exc}")

    if st.session_state.pop("industrial_workbook_show_saved",False):
        st.markdown("### Saved workbooks in this workspace")
        if saved.empty: st.info("No saved workbooks yet.")
        else:
            labels=saved["ID"].tolist(); choice=st.selectbox("Saved workbook",labels,format_func=lambda x:saved.loc[saved["ID"].eq(x),"Name"].iloc[0],key="industrial_workbook_saved_choice")
            if st.button("Open saved workbook",type="primary",key="industrial_workbook_open_saved"):
                try:
                    loaded_wb,loaded_formulas,semantic=load_workbook(choice); loaded_variables=load_workbook_variables(choice); st.session_state[WORKBOOK_STATE_KEY]=loaded_wb; st.session_state[FORMULA_STATE_KEY]=loaded_formulas
                    st.session_state["industrial_workbook_semantic_map"]=semantic; st.session_state["industrial_workbook_variables"]=loaded_variables; st.session_state["industrial_workbook_id"]=choice; st.success("Workbook loaded."); st.rerun()
                except Exception as exc: st.error(f"Workbook load failed safely: {exc}")

    wb=st.session_state[WORKBOOK_STATE_KEY]; formulas=st.session_state[FORMULA_STATE_KEY]
    current_sheet=st.selectbox("Active sheet",list(wb.keys()),index=min(list(wb.keys()).index(current_sheet),len(wb)-1),key="industrial_workbook_active_sheet")
    current=wb[current_sheet]
    tabs=st.tabs(["📊 Workbook","⚡ Instant Analyze","🔧 Query Studio","🧰 Templates","🧬 Semantic Thread","🤖 Copilot Edit","🎓 Learn & Extend"])

    with tabs[0]:
        st.caption(f"{current_sheet} · {len(current):,} rows × {len(current.columns):,} columns")
        edited=st.data_editor(current,num_rows="dynamic",use_container_width=True,hide_index=True,key=f"industrial_workbook_editor_{_slug(current_sheet)}")
        if not edited.equals(current):
            st.session_state["industrial_workbook_undo"].append({k:v.copy(deep=True) for k,v in wb.items()}); st.session_state["industrial_workbook_redo"].clear(); wb[current_sheet]=edited.copy(deep=True)
        f1,f2,f3=st.columns([1,4,1]); formula_cell=f1.text_input("Cell",value="E2",key="industrial_workbook_formula_cell")
        formula_value=f2.text_input("Formula",placeholder="=B2*C2  |  =SUM(D2:D5)  |  ='Sheet 2'!A2",key="industrial_workbook_formula_value")
        if f3.button("Apply formula",type="primary",key="industrial_workbook_apply_formula"):
            try:
                _cell_parts(formula_cell); formulas.setdefault(current_sheet,{})[formula_cell.upper()]=formula_value
                recalculated,audit=evaluate_workbook_formulas(wb,formulas,variables=variables); st.session_state[WORKBOOK_STATE_KEY]=recalculated; wb=recalculated
                st.session_state["industrial_workbook_formula_audit_df"]=audit; st.success(f"Formula applied to {current_sheet}!{formula_cell.upper()}.")
            except Exception as exc: st.error(f"Formula error safely contained: {type(exc).__name__}: {exc}")
        if formulas.get(current_sheet):
            with st.expander("Formula register"):
                st.dataframe(pd.DataFrame([{"Cell":c,"Formula":v} for c,v in formulas[current_sheet].items()]),use_container_width=True,hide_index=True)
        u1,u2,u3,u4=st.columns(4); value=u1.number_input("Convert value",value=1.0,key="iw_unit_value"); fr=u2.text_input("From unit",value="min",key="iw_unit_from"); to=u3.text_input("To unit",value="h",key="iw_unit_to")
        if u4.button("Convert",key="iw_convert_unit"):
            try: st.metric("Converted",f"{convert_units(value,fr,to):,.6g} {to}")
            except Exception as exc: st.warning(f"Unit conversion not available: {exc}")
        if not st.session_state["industrial_workbook_formula_audit_df"].empty: st.dataframe(st.session_state["industrial_workbook_formula_audit_df"],use_container_width=True,hide_index=True)
        st.markdown("#### Named engineering variables")
        variable_editor=st.data_editor(
            pd.DataFrame(
                [{"Name":k,"Value":v.get("value",v) if isinstance(v,dict) else v,
                  "Unit":v.get("unit","") if isinstance(v,dict) else "",
                  "Description":v.get("description","") if isinstance(v,dict) else ""}
                 for k,v in variables.items()]
            ),
            num_rows="dynamic",use_container_width=True,hide_index=True,key="iw_variables_editor",
        )
        if st.button("💾 Save named variables",key="iw_variables_save"):
            variables={}
            for rec in variable_editor.fillna("").to_dict("records"):
                name=str(rec.get("Name","")).strip()
                if not name: continue
                variables[name]={"value":rec.get("Value"),"unit":str(rec.get("Unit","")),"description":str(rec.get("Description",""))[:300]}
            st.session_state["industrial_workbook_variables"]=variables
            st.success(f"Saved {len(variables):,} named variable(s). Use them directly in formulas, e.g. =AnnualDemand*HoldingCost.")

    with tabs[1]:
        profile=instant_analyze(current); health=validate_workbook({current_sheet:current}); runtime=instant_runtime_profile(current)
        a1,a2,a3,a4=st.columns(4); a1.metric("Rows",f"{len(current):,}"); a2.metric("Columns",f"{len(current.columns):,}"); a3.metric("Data health",f"{health['health']:.1f}%"); a4.metric("Execution mode",runtime["mode"])
        st.dataframe(profile["profile"],use_container_width=True,hide_index=True); st.markdown("#### What to analyze next")
        for item in profile["recommendations"]: st.write("✓ "+item)
        if profile["figure"] is not None: st.plotly_chart(profile["figure"],use_container_width=True,config={"displayModeBar":False})
        st.session_state["industrial_workbook_analysis_df"]=profile["profile"]

    with tabs[2]:
        st.markdown("### Power Query-style pipeline"); st.caption("Build a repeatable sequence: select → rename → filter → clean → calculate → group → sort.")
        cols=list(map(str,current.columns)); step_type=st.selectbox("Add step",["select","rename","filter","fill_missing","cast_numeric","drop_duplicates","sort","add_formula","groupby","pivot"],key="iw_query_type"); params:dict[str,Any]={}
        if step_type=="select": params["columns"]=st.multiselect("Columns",cols,default=cols,key="iw_query_select")
        elif step_type=="rename":
            q1,q2=st.columns(2); params["source"]=q1.selectbox("Source",cols,key="iw_query_rename_source"); params["target"]=q2.text_input("Target",key="iw_query_rename_target")
        elif step_type=="filter":
            q1,q2,q3=st.columns(3); params["column"]=q1.selectbox("Column",cols,key="iw_query_filter_col"); params["op"]=q2.selectbox("Operator",["==","!=",">=", "<=",">","<","contains"],key="iw_query_filter_op"); params["value"]=q3.text_input("Value",key="iw_query_filter_value")
        elif step_type in {"fill_missing","cast_numeric","sort"}:
            params["column"]=st.selectbox("Column",cols,key=f"iw_query_{step_type}_col")
            if step_type=="fill_missing": params["value"]=st.text_input("Fill with",value="0",key="iw_query_fill")
            if step_type=="sort": params["descending"]=st.checkbox("Descending",key="iw_query_desc")
        elif step_type=="drop_duplicates": params["columns"]=st.multiselect("Duplicate key columns (blank = all)",cols,key="iw_query_dupes")
        elif step_type=="add_formula":
            q1,q2=st.columns(2); params["target"]=q1.text_input("New column",key="iw_query_formula_target"); params["expression"]=q2.text_input("Expression",placeholder="Quantity * UnitCost",key="iw_query_formula_expr")
        elif step_type=="groupby":
            q1,q2,q3=st.columns(3); params["columns"]=q1.multiselect("Group columns",cols,key="iw_query_group_cols"); params["value_column"]=q2.selectbox("Value",cols,key="iw_query_group_value"); params["aggregation"]=q3.selectbox("Aggregation",["sum","mean","median","count","min","max","std"],key="iw_query_group_agg")
        elif step_type=="pivot":
            q1,q2,q3=st.columns(3)
            params["index"]=q1.multiselect("Pivot rows",cols,default=cols[:1],key="iw_query_pivot_index")
            pivot_cols=q2.selectbox("Pivot columns",["(none)"]+cols,key="iw_query_pivot_columns")
            params["columns"]=None if pivot_cols=="(none)" else pivot_cols
            params["values"]=q3.selectbox("Pivot values",cols,key="iw_query_pivot_values")
            params["aggregation"]=st.selectbox("Pivot aggregation",["sum","mean","median","count","min","max","std"],key="iw_query_pivot_agg")
        b1,b2,b3=st.columns(3)
        if b1.button("➕ Add step",type="primary",key="iw_query_add_step"):
            try: apply_query_pipeline(current,[params|{"type":step_type}]); st.session_state["industrial_workbook_query_steps"].append(params|{"type":step_type}); st.success("Step added.")
            except Exception as exc: st.error(f"Step rejected: {exc}")
        if b2.button("▶ Run pipeline",key="iw_query_run"):
            try:
                result=apply_query_pipeline(current,st.session_state["industrial_workbook_query_steps"]); st.session_state["industrial_workbook_query_result_df"]=result; st.success(f"Pipeline produced {len(result):,} row(s) × {len(result.columns):,} column(s).")
            except Exception as exc: st.error(f"Pipeline execution failed safely: {exc}")
        if b3.button("🧹 Clear steps",key="iw_query_clear"): st.session_state["industrial_workbook_query_steps"]=[]; st.session_state["industrial_workbook_query_result_df"]=pd.DataFrame()
        if st.session_state["industrial_workbook_query_steps"]: st.dataframe(pd.DataFrame(st.session_state["industrial_workbook_query_steps"]),use_container_width=True,hide_index=True)
        result=st.session_state["industrial_workbook_query_result_df"]
        if not result.empty:
            st.dataframe(result,use_container_width=True,hide_index=True); nums=[c for c in result.columns if pd.api.types.is_numeric_dtype(result[c])]
            if nums: st.plotly_chart(px.histogram(result,x=nums[0],title=f"Query Result · {nums[0]}"),use_container_width=True,config={"displayModeBar":False})
            if st.button("💾 Save pipeline",key="iw_query_save"):
                try: pid=save_query_pipeline("Industrial Query Pipeline",current_sheet,st.session_state["industrial_workbook_query_steps"]); st.success(f"Saved pipeline {pid}.")
                except Exception as exc: st.error(f"Pipeline save failed: {exc}")

    with tabs[3]:
        st.markdown("### Template Marketplace"); templates=list_templates()
        if not templates.empty:
            choice=st.selectbox("Template",templates["ID"].tolist(),format_func=lambda x:templates.loc[templates["ID"].eq(x),"Name"].iloc[0],key="iw_template_choice"); chosen=templates.loc[templates["ID"].eq(choice)].iloc[0]
            st.caption(f"{chosen['Category']} · {chosen['Description']}")
            if st.button("Use template in current workbook",type="primary",key="iw_template_use"):
                try:
                    name,template_wb=load_template(choice); st.session_state["industrial_workbook_undo"].append({k:v.copy(deep=True) for k,v in wb.items()})
                    st.session_state[WORKBOOK_STATE_KEY]=template_wb; st.session_state[FORMULA_STATE_KEY]={k:{} for k in template_wb}; st.success(f"Loaded {name}."); st.rerun()
                except Exception as exc: st.error(f"Template load failed: {exc}")
        st.markdown("#### Publish a reusable workspace template"); p1,p2=st.columns(2); template_name=p1.text_input("Template name",key="iw_template_name"); template_category=p2.text_input("Category",value="Engineering",key="iw_template_category")
        desc=st.text_input("Description",key="iw_template_desc")
        if st.button("Publish to workspace library",key="iw_template_publish"):
            try:
                if not template_name.strip(): raise ValueError("Template name is required.")
                tid=save_template(template_name,template_category,desc,wb); st.success(f"Template {tid} published to this workspace's library.")
            except Exception as exc: st.error(f"Template publication failed: {exc}")
        st.info("The workspace library is persistent per configured Shoir-IE workspace. A shared/public marketplace requires the durable backend and explicit publication controls.")

    with tabs[4]:
        st.markdown("### Industrial Semantic / Ontology Layer")
        st.caption("This reuses the Digital Thread vocabulary; it does not create a second ontology.")
        inferred=infer_semantic_roles(current)
        st.dataframe(inferred,use_container_width=True,hide_index=True)
        overrides=st.session_state.get("industrial_workbook_semantic_map",{}).get(current_sheet,{})
        selected_roles={}
        for col in current.columns:
            suggested=str(inferred.loc[inferred["Column"].eq(str(col)),"Suggested Role"].iloc[0])
            default=overrides.get(str(col),suggested)
            selected_roles[str(col)]=st.selectbox(
                str(col),CANONICAL_TYPES,
                index=CANONICAL_TYPES.index(default) if default in CANONICAL_TYPES else 0,
                key=f"iw_sem_{_slug(current_sheet)}_{_slug(str(col))}",
            )
        if st.button("💾 Apply semantic mapping",key="iw_semantic_apply"):
            st.session_state["industrial_workbook_semantic_map"][current_sheet]=selected_roles
            st.session_state["industrial_workbook_semantic_map_df"]=pd.DataFrame([
                {"Sheet":current_sheet,"Column":col,"Role":role} for col,role in selected_roles.items()
            ])
            try:
                st.session_state["industrial_workbook_current_df"]=current.copy(deep=True)
                from shoir_digital_thread import sync_workspace_to_thread
                sync_workspace_to_thread(username,active_module="Industrial Workbook")
                st.success("Semantic mapping saved and sent through the existing Digital Thread synchronization path.")
            except Exception as exc:
                st.warning(f"Semantic mapping saved locally; Digital Thread synchronization needs attention: {exc}")
        semantic_df=st.session_state.get("industrial_workbook_semantic_map_df",pd.DataFrame())
        if isinstance(semantic_df,pd.DataFrame) and not semantic_df.empty:
            st.dataframe(semantic_df,use_container_width=True,hide_index=True)
            rel=semantic_relationships(semantic_df.rename(columns={"Role":"Suggested Role"}),current_sheet)
            if not rel.empty:
                st.markdown("#### Traceability relationships")
                st.dataframe(rel,use_container_width=True,hide_index=True)

    with tabs[5]:
        st.markdown("### Copilot direct editing")
        st.caption("Edits are deterministic and transparent. The governed Copilot remains responsible for planning and approval-gated actions.")
        prompt=st.text_input("Tell the workbook what to change",placeholder="Add column Total = Quantity * UnitCost",key="iw_copilot_edit_prompt")
        if st.button("✨ Apply safe edit",type="primary",key="iw_copilot_apply"):
            try:
                prior={k:v.copy(deep=True) for k,v in wb.items()}
                updated,message=_copilot_edit(prompt,wb,current_sheet)
                st.session_state["industrial_workbook_undo"].append(prior)
                st.session_state["industrial_workbook_undo"]=st.session_state["industrial_workbook_undo"][-20:]
                st.session_state["industrial_workbook_redo"].clear()
                st.session_state[WORKBOOK_STATE_KEY]=updated
                st.success(message)
                st.rerun()
            except Exception as exc:
                st.error(f"Copilot edit was not applied: {exc}")
        st.caption("Examples: rename column Unit Cost to UnitCost · sort by Total Cost descending · fill missing Quantity with 0 · filter Quantity > 10 · add column ExtendedCost = Quantity * Unit Cost.")
        st.info("Multi-step analytical requests continue through the existing governed Advanced Engineering Copilot and its approval gates.")

    with tabs[6]:
        st.markdown("### Learn & Extend")
        st.dataframe(pd.DataFrame([
            {"Topic":"Workbook basics","What to do":"Import, edit, save, and export an engineering workbook."},
            {"Topic":"Formula engine","What to do":"Use =B2*C2, =SUM(D2:D10), =IF(B2>0,1,0), and cross-sheet references."},
            {"Topic":"Units","What to do":"Convert common engineering units with explicit from/to units before mixing measurements."},
            {"Topic":"Query Studio","What to do":"Build a repeatable data-preparation and aggregation pipeline."},
            {"Topic":"Semantic mapping","What to do":"Map columns into the same canonical vocabulary used by the Digital Thread."},
            {"Topic":"Templates","What to do":"Start from a reusable engineering pattern and publish it to the workspace library."},
            {"Topic":"Extensions","What to do":"Register a WorkbookExtension through the existing Shoir-IE plugin registry."},
            {"Topic":"Industrial formulas","What to do":"Use OEE, TAKTTIME, LITTLELAW, CPK, PPK, EOQ, SAFETYSTOCK, NPV, CO2E and CONVERT from the shared engineering formula library."},
            {"Topic":"Industrial Pivot","What to do":"Summarize plant, line, machine, product or order measures using multi-dimensional pivot views."},
            {"Topic":"Shoir Script","What to do":"Run deterministic workbook automations through the shared Shoir Script engine; executable Python is rejected."},
            {"Topic":"Trust & Explain","What to do":"Use the dependency graph and Explain This Number surface to trace formulas and semantic links."},
        ]),use_container_width=True,hide_index=True)
        st.markdown("### Formula reference")
        st.dataframe(pd.DataFrame([
            {"Function":"SUM","Example":"=SUM(D2:D10)","Purpose":"Total"},
            {"Function":"AVERAGE","Example":"=AVERAGE(B2:B10)","Purpose":"Mean"},
            {"Function":"IF","Example":'=IF(B2>10,"High","Low")',"Purpose":"Conditional logic"},
            {"Function":"ROUND","Example":"=ROUND(B2,2)","Purpose":"Rounding"},
            {"Function":"ABS","Example":"=ABS(B2)","Purpose":"Absolute value"},
            {"Function":"SQRT","Example":"=SQRT(B2)","Purpose":"Square root"},
            {"Function":"POWER","Example":"=POWER(B2,2)","Purpose":"Exponentiation"},
        ]),use_container_width=True,hide_index=True)
        try:
            from shoir_adoption_engine import formula_library_frame
            st.markdown("### Shared industrial formula library")
            st.dataframe(formula_library_frame(),use_container_width=True,hide_index=True)
        except Exception as exc:
            st.caption(f"Engineering formula library metadata unavailable: {exc}")
        st.markdown("### Automation")
        st.caption("For multi-step workflows use the shared Shoir Script surface from Industrial Home; this workbook stays the editable artifact.")
        st.code('load("Sheet1")\nadd_column("Extended Cost","Quantity * Unit Cost")\nanalyze()', language="text")
        exts=list_workbook_extensions()
        st.markdown("### Developer extension SDK")
        st.dataframe(pd.DataFrame([
            {"Name":x.name,"Version":x.version,"Category":x.category,"Description":x.description,"Executable":bool(x.transform)}
            for x in exts
        ]) if exts else pd.DataFrame([{"Name":"No extensions installed","Executable":False}]),
        use_container_width=True,hide_index=True)
        st.markdown("### Excel interoperability & product shell")
        st.write("Import/export uses the existing Shoir-IE Excel pipeline. The responsive workbook UI is browser-first, and the companion Office add-in scaffold in excel_addin/ can connect to a configured Shoir-IE API host.")
        st.caption("Large-data mode is explicit: interactive cell editing remains in-memory, while vectorized and chunked CSV primitives provide a path for larger datasets without changing the workbook contract.")

    st.session_state["industrial_workbook_current_df"]=wb[current_sheet].copy(deep=True)
    st.session_state["industrial_workbook_query_result_df"]=st.session_state.get("industrial_workbook_query_result_df",pd.DataFrame())
    if st.session_state.get("industrial_workbook_id"):
        with st.expander("🕘 Version history & comments", expanded=False):
            try:
                versions=list_workbook_versions(st.session_state["industrial_workbook_id"])
                if versions.empty:
                    st.info("No saved versions yet.")
                else:
                    st.dataframe(versions,use_container_width=True,hide_index=True)
                    version_choice=st.selectbox(
                        "Version to restore",
                        versions["ID"].tolist(),
                        format_func=lambda x: str(versions.loc[versions["ID"].eq(x),"Version"].iloc[0]) + " · " + str(versions.loc[versions["ID"].eq(x),"Label"].iloc[0]),
                        key="iw_version_choice",
                    )
                    if st.button("↩ Restore selected version", key="iw_restore_version"):
                        loaded_wb,loaded_formulas,loaded_semantic,loaded_variables=load_workbook_version(version_choice)
                        st.session_state[WORKBOOK_STATE_KEY]=loaded_wb
                        st.session_state[FORMULA_STATE_KEY]=loaded_formulas
                        st.session_state["industrial_workbook_semantic_map"]=loaded_semantic
                        st.session_state["industrial_workbook_variables"]=loaded_variables
                        st.success("Version restored into the editable workbook state.")
                        st.rerun()
            except Exception as exc:
                st.warning(f"Version history unavailable: {type(exc).__name__}: {exc}")
            comments=list_workbook_comments(st.session_state["industrial_workbook_id"])
            st.markdown("#### Cell comments")
            if comments.empty:
                st.caption("No comments yet.")
            else:
                st.dataframe(comments,use_container_width=True,hide_index=True)
            cc1,cc2=st.columns([1,3]); comment_cell=cc1.text_input("Cell",value="A1",key="iw_comment_cell"); comment_text=cc2.text_input("Comment",key="iw_comment_text")
            if st.button("💬 Add comment",key="iw_comment_add"):
                try:
                    save_workbook_comment(st.session_state["industrial_workbook_id"],current_sheet,comment_cell,comment_text)
                    st.success("Comment saved to this workbook version history.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Comment could not be saved: {type(exc).__name__}: {exc}")

    try:
        export_payload=_serialize_workbook(wb)
        st.download_button("⬇️ Export current workbook (.xlsx)",data=export_payload,
                           file_name=f"{_slug('Shoir-IE-' + current_sheet)}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True,key="industrial_workbook_export_xlsx")
    except Exception as exc:
        st.warning(f"Workbook export is temporarily unavailable: {exc}")
    try:
        fingerprint_payload=json.dumps({
            "sheets":{str(k):hashlib.sha256(v.to_csv(index=False).encode("utf-8")).hexdigest() for k,v in wb.items()},
            "formulas":formulas,"semantic":st.session_state.get("industrial_workbook_semantic_map",{}),
            "variables":variables
        },sort_keys=True,default=str).encode("utf-8")
        fingerprint=hashlib.sha256(fingerprint_payload).hexdigest()
        if fingerprint != st.session_state.get("industrial_workbook_last_autosave_fingerprint"):
            wid=save_workbook(wb,formulas,st.session_state.get("industrial_workbook_semantic_map",{}),
                              f"Shoir-IE Workbook · {current_sheet}",st.session_state.get("industrial_workbook_id"),
                              variables=variables)
            st.session_state["industrial_workbook_id"]=wid
            st.session_state["industrial_workbook_last_autosave_fingerprint"]=fingerprint
    except Exception:
        pass
