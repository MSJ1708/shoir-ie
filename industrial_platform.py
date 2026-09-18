"""Integrated industrial engineering platform services for Shoir-IE.

The services in this file are deterministic, testable building blocks for the
Streamlit UI. They avoid fabricating operational facts and return explicit
validation/error information when inputs are incomplete.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import sqlite3
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from heapq import heappush, heappop
from typing import Any, Iterable, Optional, Sequence

import numpy as np
import pandas as pd

try:
    from scipy import stats
except Exception:  # pragma: no cover
    stats = None

try:
    import plotly.express as px
    import plotly.graph_objects as go
except Exception:  # pragma: no cover
    px = go = None

TIERS = ["Starter", "Mid-Tier Pro", "Enterprise", "Enterprise Plus", "Research Pack"]

NEW_ENTERPRISE_PLUS_MODULES = [
    "Industrial Digital Thread",
    "Advanced Planning & Scheduling (APS)",
    "Manufacturing Execution System (MES)",
    "Quality Engineering & Reliability",
    "Industrial Simulation Lab",
    "3D Factory Designer",
    "Industrial Connectivity Hub",
    "Multi-Objective & Robust Optimization",
    "Capital & Workforce Engineering",
    "Industrial Sustainability & LCA",
    "Enterprise Security & Governance", "Advanced Industrial AI & Digital Twin Lab",
]

def safe_float(value, default=0.0):
    try:
        x = float(value)
        return x if np.isfinite(x) else default
    except Exception:
        return default

def validate_table(df: pd.DataFrame, numeric_ranges: Optional[dict[str, tuple[float, float]]] = None) -> dict[str, Any]:
    if df is None or not isinstance(df, pd.DataFrame):
        return {"valid": False, "score": 0, "issues": ["No valid table supplied."]}
    issues = []
    rows, cols = df.shape
    if rows == 0:
        issues.append("The table is empty.")
    duplicate_rows = int(df.duplicated().sum())
    if duplicate_rows:
        issues.append(f"{duplicate_rows} duplicate rows.")
    missing = int(df.isna().sum().sum())
    if missing:
        issues.append(f"{missing} missing cells.")
    constant_cols = [c for c in df.columns if df[c].nunique(dropna=True) <= 1]
    if constant_cols:
        issues.append(f"Constant columns: {', '.join(map(str, constant_cols[:6]))}.")
    if numeric_ranges:
        for col, (lo, hi) in numeric_ranges.items():
            if col in df.columns:
                vals = pd.to_numeric(df[col], errors="coerce")
                bad = int(((vals < lo) | (vals > hi)).fillna(False).sum())
                if bad:
                    issues.append(f"{bad} values outside {lo:g}–{hi:g} in {col}.")
    score = 100.0
    score -= min(35, duplicate_rows / max(rows, 1) * 100)
    score -= min(35, missing / max(rows * max(cols, 1), 1) * 100)
    score -= min(20, len(constant_cols) * 3)
    score = max(0.0, round(score, 1))
    return {
        "valid": rows > 0 and score >= 60,
        "score": score,
        "rows": rows,
        "columns": cols,
        "duplicates": duplicate_rows,
        "missing_cells": missing,
        "constant_columns": constant_cols,
        "issues": issues,
    }

def industrial_data_snapshot(session_state: dict) -> dict[str, pd.DataFrame]:
    mapping = {
        "Customers": session_state.get("customers_list", []),
        "Warehouses": session_state.get("warehouses_list", []),
        "Fleet": session_state.get("fleet_list", []),
        "Inventory": session_state.get("inventory_playback", session_state.get("inventory_list", [])),
        "Machines": session_state.get("workspace_users", []),
    }
    result = {}
    for name, value in mapping.items():
        if isinstance(value, pd.DataFrame):
            result[name] = value.copy(deep=True)
        elif isinstance(value, list):
            result[name] = pd.DataFrame(value)
        elif value is not None:
            result[name] = pd.DataFrame(value)
    return {k: v for k, v in result.items() if not v.empty}

def calculate_takt_time(available_minutes: float, demand_units: float) -> float:
    if demand_units <= 0:
        raise ValueError("Demand must be greater than zero.")
    if available_minutes <= 0:
        raise ValueError("Available production time must be greater than zero.")
    return available_minutes / demand_units

def calculate_line_balance(tasks: pd.DataFrame, stations: int, available_minutes: float) -> dict[str, Any]:
    required = {"Task", "Time"}
    if not required.issubset(tasks.columns):
        raise ValueError("Tasks table must contain Task and Time columns.")
    if stations < 1:
        raise ValueError("Stations must be at least 1.")
    work = tasks.copy()
    work["Time"] = pd.to_numeric(work["Time"], errors="coerce")
    work = work.dropna(subset=["Time"])
    total = float(work["Time"].sum())
    takt = safe_float(available_minutes) / max(stations, 1)
    ranked = work.sort_values("Time", ascending=False)
    loads = [0.0] * stations
    assignment = []
    for row in ranked.itertuples(index=False):
        i = int(np.argmin(loads))
        loads[i] += float(row.Time)
        assignment.append({"Task": getattr(row, "Task"), "Station": i + 1, "Time": float(row.Time)})
    max_load = max(loads) if loads else 0
    efficiency = (total / (stations * max_load) * 100) if max_load else 0
    return {
        "takt_time": takt,
        "station_loads": pd.DataFrame({"Station": range(1, stations + 1), "Load": loads}),
        "assignments": pd.DataFrame(assignment),
        "line_efficiency_pct": round(efficiency, 2),
        "total_work": total,
    }

@dataclass
class ScheduleJob:
    job: str
    machine: str
    duration: float
    due_date: str
    priority: int = 0
    release_date: str = ""

def finite_schedule(jobs: pd.DataFrame, machines: pd.DataFrame, horizon_hours: float = 168.0) -> tuple[pd.DataFrame, dict[str, Any]]:
    req_jobs = {"Job", "Machine", "Duration", "Due Date"}
    req_machines = {"Machine", "Available Hours"}
    if not req_jobs.issubset(jobs.columns):
        raise ValueError(f"Jobs table needs: {sorted(req_jobs)}")
    if not req_machines.issubset(machines.columns):
        raise ValueError(f"Machines table needs: {sorted(req_machines)}")
    m_caps = {str(r["Machine"]): safe_float(r["Available Hours"]) for _, r in machines.iterrows()}
    work = jobs.copy()
    work["Duration"] = pd.to_numeric(work["Duration"], errors="coerce")
    work["Due Date"] = pd.to_datetime(work["Due Date"], errors="coerce")
    work = work.dropna(subset=["Duration", "Due Date"])
    if "Priority" not in work.columns:
        work["Priority"] = 0
    work["Priority"] = pd.to_numeric(work["Priority"], errors="coerce").fillna(0)
    work = work.sort_values(["Due Date", "Priority"], ascending=[True, False])
    clocks = {m: pd.Timestamp("2000-01-01") for m in m_caps}
    rows = []
    late = 0
    for _, r in work.iterrows():
        machine = str(r["Machine"])
        if machine not in m_caps:
            continue
        dur = float(r["Duration"])
        used = sum(safe_float(x["Duration"]) for x in rows if x["Machine"] == machine)
        if used + dur > m_caps[machine] or used + dur > horizon_hours:
            rows.append({
                "Job": r["Job"], "Machine": machine, "Duration": dur,
                "Start": pd.NaT, "Finish": pd.NaT, "Due Date": r["Due Date"],
                "Status": "Capacity exceeded"
            })
            late += 1
            continue
        start = clocks[machine]
        finish = start + pd.Timedelta(hours=dur)
        due = r["Due Date"]
        status = "On time" if finish <= due else "Late"
        if status == "Late":
            late += 1
        rows.append({
            "Job": r["Job"], "Machine": machine, "Duration": dur,
            "Start": start, "Finish": finish, "Due Date": due, "Status": status
        })
        clocks[machine] = finish
    out = pd.DataFrame(rows)
    return out, {"scheduled_jobs": len(out), "late_or_capacity_exceptions": late, "feasible": late == 0}

def mes_work_order_table(orders: pd.DataFrame) -> dict[str, Any]:
    if orders is None or orders.empty:
        return {"orders": pd.DataFrame(), "summary": pd.DataFrame()}
    out = orders.copy()
    for c in ["Quantity", "Produced", "Scrap"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    if "Quantity" in out.columns and "Produced" in out.columns:
        out["Remaining"] = (out["Quantity"] - out["Produced"]).clip(lower=0)
    if "Quantity" in out.columns and "Scrap" in out.columns:
        out["Yield_pct"] = np.where(out["Quantity"] > 0, ((out["Quantity"] - out["Scrap"]) / out["Quantity"]) * 100, 0)
    group_col = "Status" if "Status" in out.columns else None
    if group_col:
        summary = out.groupby(group_col, dropna=False).size().reset_index(name="Orders")
    else:
        summary = pd.DataFrame({"Orders": [len(out)]})
    return {"orders": out, "summary": summary}

def spc_limits(values: Sequence[float], sigma: float = 3.0) -> dict[str, Any]:
    x = np.asarray(pd.to_numeric(pd.Series(values), errors="coerce").dropna(), dtype=float)
    if x.size < 2:
        raise ValueError("At least two numeric observations are required.")
    mean = float(x.mean())
    sd = float(x.std(ddof=1))
    return {
        "mean": mean, "std": sd,
        "ucl": mean + sigma * sd,
        "lcl": mean - sigma * sd,
        "values": x,
        "out_of_control": x[(x > mean + sigma * sd) | (x < mean - sigma * sd)],
    }

def process_capability(values: Sequence[float], usl: float, lsl: float, target: Optional[float] = None) -> dict[str, float]:
    x = np.asarray(pd.to_numeric(pd.Series(values), errors="coerce").dropna(), dtype=float)
    if x.size < 2 or usl <= lsl:
        raise ValueError("Need at least two observations and USL > LSL.")
    mean = float(x.mean()); sd = float(x.std(ddof=1))
    cp = (usl - lsl) / (6 * sd) if sd else float("inf")
    cpk = min((usl - mean) / (3 * sd), (mean - lsl) / (3 * sd)) if sd else float("inf")
    cpm = None
    if target is not None and sd:
        cpm = (usl - lsl) / (6 * math.sqrt(sd**2 + (mean - target)**2))
    return {"mean": mean, "std": sd, "Cp": cp, "Cpk": cpk, "Cpm": cpm}

def pareto_frontier(points: pd.DataFrame, minimize: Sequence[str], maximize: Sequence[str] = ()) -> pd.DataFrame:
    if points.empty:
        return points.copy()
    arr = points.copy()
    score = []
    for i, row_i in arr.iterrows():
        dominated = False
        for j, row_j in arr.iterrows():
            if i == j:
                continue
            no_worse = True; strictly_better = False
            for c in minimize:
                a, b = safe_float(row_j[c]), safe_float(row_i[c])
                no_worse &= a <= b
                strictly_better |= a < b
            for c in maximize:
                a, b = safe_float(row_j[c]), safe_float(row_i[c])
                no_worse &= a >= b
                strictly_better |= a > b
            if no_worse and strictly_better:
                dominated = True; break
        score.append(not dominated)
    arr["Pareto Optimal"] = score
    return arr

def weighted_objective(points: pd.DataFrame, objective_weights: dict[str, float], minimize: bool = True) -> pd.DataFrame:
    if points.empty:
        return points.copy()
    out = points.copy()
    total = max(sum(abs(safe_float(v)) for v in objective_weights.values()), 1e-12)
    result = np.zeros(len(out))
    for col, weight in objective_weights.items():
        if col not in out.columns: continue
        series = pd.to_numeric(out[col], errors="coerce")
        lo, hi = float(series.min()), float(series.max())
        norm = np.zeros(len(out)) if hi == lo else (series - lo) / (hi - lo)
        result += norm.fillna(0).to_numpy() * float(weight)
    out["Weighted Objective"] = result / total
    return out.sort_values("Weighted Objective", ascending=minimize).reset_index(drop=True)

def robust_scenario_bounds(base: dict[str, float], relative_uncertainty: dict[str, float], samples: int = 1000, seed: int = 42) -> pd.DataFrame:
    if samples < 10:
        raise ValueError("Use at least 10 scenarios.")
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(samples):
        row = {"Scenario": i + 1}
        for key, value in base.items():
            pct = abs(safe_float(relative_uncertainty.get(key, 0)))
            row[key] = safe_float(value) * (1 + rng.uniform(-pct, pct))
        rows.append(row)
    return pd.DataFrame(rows)

def discrete_event_simulation(arrivals: Sequence[float], service_times: Sequence[float], servers: int = 1) -> dict[str, Any]:
    if servers < 1:
        raise ValueError("Servers must be at least 1.")
    n = min(len(arrivals), len(service_times))
    if n == 0:
        return {"events": pd.DataFrame(), "summary": {"throughput": 0, "avg_wait": 0}}
    available = [0.0] * servers
    events = []
    for i in range(n):
        arrival = safe_float(arrivals[i]); service = max(0.0, safe_float(service_times[i]))
        k = int(np.argmin(available))
        start = max(arrival, available[k])
        finish = start + service
        wait = start - arrival
        available[k] = finish
        events.append({"Entity": i + 1, "Server": k + 1, "Arrival": arrival, "Start": start, "Finish": finish, "Wait": wait, "Service": service})
    ev = pd.DataFrame(events)
    makespan = float(ev["Finish"].max()) if not ev.empty else 0
    return {"events": ev, "summary": {"throughput": len(ev) / makespan if makespan else 0, "avg_wait": float(ev["Wait"].mean()), "utilization": float(ev["Service"].sum() / max(makespan * servers, 1e-9))}}

def system_dynamics_projection(initial_inventory: float, demand: float, replenishment: float, periods: int = 12) -> pd.DataFrame:
    inventory = safe_float(initial_inventory)
    rows=[]
    for p in range(1, periods+1):
        inventory += safe_float(replenishment) - safe_float(demand)
        rows.append({"Period":p,"Inventory":inventory,"Demand":safe_float(demand),"Replenishment":safe_float(replenishment)})
    return pd.DataFrame(rows)

def n_sim_agent_model(population: int, arrival_rate: float, service_rate: float, periods: int = 24, seed: int = 42) -> pd.DataFrame:
    rng=np.random.default_rng(seed); active=0; rows=[]
    for p in range(periods):
        arrivals=int(rng.poisson(max(arrival_rate,0)))
        departures=min(active,int(rng.poisson(max(service_rate,0))))
        active=max(0,active+arrivals-departures)
        rows.append({"Period":p+1,"Arrivals":arrivals,"Departures":departures,"Active":active,"Capacity":population})
    return pd.DataFrame(rows)

def nci_ergonomics(lift_weight: float, horizontal: float, vertical: float, distance: float, asymmetry_deg: float, frequency: float, duration_hours: float, coupling: float = 1.0) -> dict[str, float]:
    # NIOSH Revised Lifting Equation factors (metric approximation).
    LC = 23.0
    HM = min(1.0, 25.0 / max(horizontal, 25.0))
    VM = max(0.0, 1 - 0.003 * abs(vertical - 75))
    DM = min(1.0, 0.82 + 4.5 / max(distance, 100.0))
    AM = max(0.0, 1 - 0.0032 * asymmetry_deg)
    FM = max(0.2, min(1.0, 0.95 - 0.15 * max(0, frequency - 0.2)))
    CM = max(0.7, min(1.0, coupling))
    RWL = LC * HM * VM * DM * AM * FM * CM
    LI = safe_float(lift_weight) / max(RWL, 1e-9)
    return {"RWL_kg": RWL, "Lifting_Index": LI}

def economics(cash_flows: Sequence[float], discount_rate: float = 0.1) -> dict[str, float]:
    if not cash_flows:
        raise ValueError("Provide cash flows beginning with the initial investment.")
    rate = safe_float(discount_rate)
    npv = sum(safe_float(cf) / ((1 + rate) ** i) for i, cf in enumerate(cash_flows))
    irr = None
    # Bisection IRR over a broad range when a sign change exists.
    lo, hi = -0.99, 10.0
    f_lo = sum(safe_float(cf) / ((1 + lo) ** i) for i, cf in enumerate(cash_flows))
    f_hi = sum(safe_float(cf) / ((1 + hi) ** i) for i, cf in enumerate(cash_flows))
    if f_lo * f_hi < 0:
        for _ in range(100):
            mid=(lo+hi)/2
            f_mid=sum(safe_float(cf)/((1+mid)**i) for i,cf in enumerate(cash_flows))
            if abs(f_mid)<1e-8: break
            if f_lo*f_mid<=0: hi=mid; f_hi=f_mid
            else: lo=mid; f_lo=f_mid
        irr=mid
    cumulative=0; payback=None
    for i,cf in enumerate(cash_flows):
        prev=cumulative; cumulative+=safe_float(cf)
        if cumulative>=0 and i>0:
            payback=(i-1)+(-prev/max(safe_float(cf),1e-9)); break
    return {"NPV":npv,"IRR":irr,"Payback_Period":payback}

def lca_inventory(factors: pd.DataFrame) -> pd.DataFrame:
    required={"Activity","Quantity","Unit","Factor_kgCO2e_per_unit"}
    if not required.issubset(factors.columns):
        raise ValueError(f"LCA table must contain {sorted(required)}")
    out=factors.copy()
    out["Quantity"]=pd.to_numeric(out["Quantity"],errors="coerce").fillna(0)
    out["Factor_kgCO2e_per_unit"]=pd.to_numeric(out["Factor_kgCO2e_per_unit"],errors="coerce").fillna(0)
    out["CO2e_kg"]=out["Quantity"]*out["Factor_kgCO2e_per_unit"]
    return out

def model_hash(payload: Any) -> str:
    raw=json.dumps(payload,sort_keys=True,default=str,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()

def ensure_model_registry(db_path="enterprise_full_workspace.db"):
    with sqlite3.connect(db_path) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS model_registry(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, model_name TEXT, version TEXT,
            model_type TEXT, payload_json TEXT, dataset_hash TEXT, created_at TEXT, approved INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS experiment_runs(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, experiment_name TEXT,
            scenario_json TEXT, result_json TEXT, created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS security_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, event TEXT, severity TEXT, created_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS industrial_entities(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, entity_type TEXT,
            entity_key TEXT, payload_json TEXT, updated_at TEXT,
            UNIQUE(username,entity_type,entity_key))""")
        c.commit()

def registry_add(username: str, name: str, version: str, model_type: str, payload: Any, dataset_hash: str = "", db_path="enterprise_full_workspace.db"):
    ensure_model_registry(db_path)
    with sqlite3.connect(db_path) as c:
        c.execute("INSERT INTO model_registry(username,model_name,version,model_type,payload_json,dataset_hash,created_at) VALUES(?,?,?,?,?,?,?)",(username,name,version,model_type,json.dumps(payload,default=str),dataset_hash,datetime.utcnow().isoformat()))
        c.commit()

def registry_list(username: str, db_path="enterprise_full_workspace.db") -> pd.DataFrame:
    ensure_model_registry(db_path)
    with sqlite3.connect(db_path) as c:
        return pd.read_sql("SELECT * FROM model_registry WHERE username=? ORDER BY id DESC", c, params=(username,))

def experiment_save(username: str, name: str, scenario: Any, result: Any, db_path="enterprise_full_workspace.db"):
    ensure_model_registry(db_path)
    with sqlite3.connect(db_path) as c:
        c.execute("INSERT INTO experiment_runs(username,experiment_name,scenario_json,result_json,created_at) VALUES(?,?,?,?,?)",(username,name,json.dumps(scenario,default=str),json.dumps(result,default=str),datetime.utcnow().isoformat()))
        c.commit()

def governance_hash(event: dict[str, Any], previous_hash: str = "") -> str:
    payload={"previous_hash":previous_hash,"event":event}
    return model_hash(payload)

def build_excel_export(title: str, sheets: dict[str,pd.DataFrame], figures: Optional[list] = None) -> bytes:
    import xlsxwriter
    buf=io.BytesIO()
    with pd.ExcelWriter(buf,engine="xlsxwriter") as writer:
        wb=writer.book
        title_fmt=wb.add_format({"bold":True,"font_size":18,"font_color":"17365D"})
        header_fmt=wb.add_format({"bold":True,"bg_color":"17365D","font_color":"FFFFFF","border":1})
        for name,df in sheets.items():
            safe=re.sub(r"[^A-Za-z0-9 _-]","",str(name))[:31] or "Sheet"
            if safe in writer.sheets: safe=(safe[:27]+"_"+str(len(writer.sheets)+1))[:31]
            df.to_excel(writer,index=False,sheet_name=safe,startrow=2)
            ws=writer.sheets[safe]
            ws.write(0,0,title,title_fmt); ws.freeze_panes(3,0)
            if len(df.columns):
                for j,col in enumerate(df.columns): ws.write(2,j,str(col),header_fmt)
                ws.autofilter(2,0,max(2,len(df)+2),len(df.columns)-1)
            for j,col in enumerate(df.columns):
                vals=df[col].astype(str) if not df.empty else pd.Series(dtype=str)
                width=min(48,max(10,len(str(col))+2,int(vals.map(len).max()+2) if len(vals) else 10))
                ws.set_column(j,j,width)
            nums=[j for j,col in enumerate(df.columns) if pd.api.types.is_numeric_dtype(df[col])]
            if nums and len(df):
                ch=wb.add_chart({"type":"column"})
                for j in nums[:6]:
                    ch.add_series({"name":[safe,2,j],"categories":[safe,3,0,2+len(df),0],"values":[safe,3,j,2+len(df),j]})
                ch.set_title({"name":f"{safe} — Metrics"}); ch.set_legend({"position":"bottom"})
                ws.insert_chart(2,len(df.columns)+2,ch,{"x_scale":1.2,"y_scale":1.0})
        if figures:
            for idx,fig in enumerate(figures,1):
                try:
                    ws=wb.add_worksheet(f"Chart {idx}"[:31])
                    png=fig.to_image(format="png",width=1200,height=650,scale=1)
                    ws.insert_image("A1","chart.png",{"image_data":io.BytesIO(png)})
                except Exception:
                    pass
    return buf.getvalue()

def module_report_bytes(title: str, df: pd.DataFrame, figure=None) -> bytes:
    sheets={"Results":df if isinstance(df,pd.DataFrame) else pd.DataFrame(df)}
    return build_excel_export(title,sheets,[figure] if figure is not None else [])

def data_quality_frame(df: pd.DataFrame) -> pd.DataFrame:
    report=validate_table(df)
    return pd.DataFrame([{
        "Metric":"Rows","Value":report["rows"]},
        {"Metric":"Columns","Value":report["columns"]},
        {"Metric":"Missing cells","Value":report["missing_cells"]},
        {"Metric":"Duplicate rows","Value":report["duplicates"]},
        {"Metric":"Data quality score","Value":report["score"]},
    ])


def ml_demand_forecast(history: pd.DataFrame, target: str, feature_columns: Sequence[str], horizon: int = 12, model_type: str = "Random Forest") -> dict[str, Any]:
    """Train a reproducible SKU/demand model from historical rows and return diagnostics.
    The caller supplies external variables such as promotion, weather and macro indicators.
    """
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    if target not in history.columns or not feature_columns:
        raise ValueError("Provide a target column and at least one feature column.")
    work = history[list(feature_columns) + [target]].copy()
    work = work.apply(pd.to_numeric, errors="coerce").dropna()
    if len(work) < max(12, len(feature_columns) + 3):
        raise ValueError("Not enough complete historical rows for a stable forecast model.")
    X = work[list(feature_columns)]; y = work[target]
    split = max(len(work) - max(3, min(horizon, len(work)//4)), len(feature_columns) + 2)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]
    if model_type == "Gradient Boosting":
        model = GradientBoostingRegressor(random_state=42)
    else:
        model = RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    pred = model.predict(X_test) if len(X_test) else np.array([])
    diagnostics = {
        "MAE": float(mean_absolute_error(y_test, pred)) if len(pred) else None,
        "R2": float(r2_score(y_test, pred)) if len(pred) > 1 else None,
        "Training Rows": int(len(X_train)),
        "Validation Rows": int(len(X_test)),
        "Model": model_type,
    }
    future_X = X.tail(min(horizon, len(X))).copy()
    forecast = pd.DataFrame({"Period": range(1, len(future_X)+1), "Forecast": model.predict(future_X)})
    importance = pd.DataFrame({"Feature": list(feature_columns), "Importance": model.feature_importances_}).sort_values("Importance", ascending=False)
    return {"forecast": forecast, "feature_importance": importance, "diagnostics": diagnostics, "model": model}

def predictive_maintenance_rul(history: pd.DataFrame, target: str, feature_columns: Sequence[str]) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    if target not in history.columns or not feature_columns:
        raise ValueError("Provide an RUL target and telemetry feature columns.")
    work = history[list(feature_columns) + [target]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(work) < max(20, len(feature_columns) + 5):
        raise ValueError("At least 20 complete telemetry/RUL rows are required.")
    X=work[list(feature_columns)]; y=work[target]
    split=max(len(work)-max(5,len(work)//5),len(feature_columns)+2)
    model=RandomForestRegressor(n_estimators=250,random_state=42,n_jobs=-1)
    model.fit(X.iloc[:split],y.iloc[:split])
    pred=model.predict(X.iloc[split:])
    latest=model.predict(X.tail(1))[0]
    return {
        "predicted_rul": float(max(0,latest)),
        "MAE": float(mean_absolute_error(y.iloc[split:],pred)),
        "R2": float(r2_score(y.iloc[split:],pred)) if len(pred)>1 else None,
        "feature_importance": pd.DataFrame({"Feature":list(feature_columns),"Importance":model.feature_importances_}).sort_values("Importance",ascending=False),
        "predictions": pd.DataFrame({"Actual RUL":y.iloc[split:].to_numpy(),"Predicted RUL":pred}),
        "model":model,
    }

def scenario_delta(baseline: pd.DataFrame, scenario: pd.DataFrame, keys: Sequence[str]) -> pd.DataFrame:
    if not keys:
        raise ValueError("Provide at least one scenario key.")
    a=baseline.copy(); b=scenario.copy()
    merged=a.merge(b,on=list(keys),how="outer",suffixes=(" Baseline"," Scenario"))
    for col in list(a.columns):
        if col in keys or col not in b.columns: continue
        base_col=f"{col} Baseline"; scen_col=f"{col} Scenario"
        merged[f"{col} Delta"]=pd.to_numeric(merged[scen_col],errors="coerce")-pd.to_numeric(merged[base_col],errors="coerce")
    return merged

def currency_convert(amount: float, rate_to_base: float) -> float:
    if rate_to_base <= 0:
        raise ValueError("Currency conversion rate must be greater than zero.")
    return float(amount) * float(rate_to_base)

def rbac_can_edit(role: str, resource: str, action: str) -> bool:
    permissions={
        "Viewer":{"read"},
        "Planner":{"read","write_scenario","run_model"},
        "Engineer":{"read","write_scenario","run_model","edit_model"},
        "Manager":{"read","write_scenario","run_model","approve"},
        "Admin":{"read","write_scenario","run_model","edit_model","approve","admin"},
    }
    return action in permissions.get(str(role),set())

def connector_healthcheck(config: dict[str, Any]) -> dict[str, Any]:
    """Validate a connector definition without storing credentials or claiming a live connection."""
    required={"name","system","endpoint"}
    missing=sorted(required-set(config))
    endpoint=str(config.get("endpoint","")).strip()
    valid=not missing and (endpoint.startswith("https://") or endpoint.startswith("http://"))
    return {"valid":valid,"missing":missing,"system":config.get("system"),"endpoint":endpoint,"credential_handling":"External secret store required for production credentials."}

def executive_report_pdf(title: str, summary: dict[str, Any], tables: dict[str, pd.DataFrame]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=36,leftMargin=36,topMargin=36,bottomMargin=36)
    styles=getSampleStyleSheet(); story=[Paragraph(title,styles["Title"]),Paragraph(datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),styles["Normal"]),Spacer(1,12)]
    for k,v in summary.items(): story.append(Paragraph(f"<b>{k}</b>: {v}",styles["Normal"]))
    for name,df in tables.items():
        story += [Spacer(1,12),Paragraph(str(name),styles["Heading2"])]
        view=df.head(25).copy().astype(str)
        data=[list(view.columns)]+view.values.tolist() if not view.empty else [["No rows"]]
        t=Table(data,repeatRows=1); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17365D")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.25,colors.grey),("FONTSIZE",(0,0),(-1,-1),7)])); story.append(t)
    doc.build(story); return buf.getvalue()
