"""Shoir-IE Platform Excellence Layer.

This module strengthens the existing industrial_platform service layer without
creating a second application data model. It adds:
- canonical tier mapping and module governance
- deep validation / data profiling
- digital-thread relationships and impact analysis
- constrained planning/scheduling helpers
- richer quality/reliability analytics
- experiment-ready simulation statistics
- 3D layout collision and flow checks
- multi-objective / robust decision analysis
- engineering economics, workforce and sustainability scenario tools
- model/decision/approval governance
- deterministic Copilot workflow planning with an approval gate
- connector configuration validation and security-safe audit helpers

It deliberately does not fake plant connectivity or security protocols. Live
protocol sessions still require customer endpoints, credentials, and deployment
infrastructure.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import product
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats

CANONICAL_TIERS = [
    {
        "key": "Starter",
        "legacy": ["Starter", "Starter Tier"],
        "label": "Starter",
        "focus": "Core engineering, clean data, validation and guided analysis",
        "module_limit": "Core",
    },
    {
        "key": "Professional",
        "legacy": ["Mid-Tier Pro", "Professional", "Professional Tier"],
        "label": "Professional",
        "focus": "Advanced planning, quality, workforce, economics and sustainability",
        "module_limit": "Professional",
    },
    {
        "key": "Operations",
        "legacy": ["Operations", "Industrial Operations Tier"],
        "label": "Industrial Operations",
        "focus": "Connected manufacturing, simulation, control and operational execution",
        "module_limit": "Enterprise",
    },
    {
        "key": "Enterprise",
        "legacy": ["Enterprise", "Enterprise Tier"],
        "label": "Enterprise",
        "focus": "Optimization, digital thread, governance, simulation and collaboration",
        "module_limit": "Enterprise",
    },
    {
        "key": "Enterprise Plus",
        "legacy": ["Enterprise Plus", "Enterprise Plus Tier", "Industrial Enterprise"],
        "label": "Enterprise Plus",
        "focus": "Advanced Copilot, live twin, governance and enterprise-scale orchestration",
        "module_limit": "Enterprise Plus",
    },
    {
        "key": "Research",
        "legacy": ["Research Pack", "Research & Innovation", "Research Tier"],
        "label": "Research & Innovation",
        "focus": "Experiments, reproducibility, advanced analytics and academic workflows",
        "module_limit": "Enterprise Plus",
    },
]

TIER_ORDER = [x["key"] for x in CANONICAL_TIERS]

MODULE_MATRIX = [
    ("Platform","Industrial Operating System","Enterprise"),
    ("Core Platform","Engineering Validation Center","Starter"),
    ("Core Platform","Excel Data Cleaning & Import","Starter"),
    ("Digital Thread","Industrial Data Model & Digital Thread","Professional"),
    ("Planning","Advanced Planning & Scheduling","Professional"),
    ("Planning","Production Planning & Control (PPC)","Professional"),
    ("Manufacturing","Manufacturing Execution System","Operations"),
    ("Manufacturing","Lean Manufacturing & Shop Floor Operations","Professional"),
    ("Quality","Quality Engineering & Reliability","Professional"),
    ("Quality","Quality Control, Six Sigma & Reliability","Professional"),
    ("Simulation","Industrial Simulation Lab","Enterprise"),
    ("Simulation","Digital Twin & Discrete-Event Simulation","Enterprise"),
    ("Facilities","3D Factory Designer","Enterprise"),
    ("Connectivity","Industrial Connectivity Hub","Enterprise"),
    ("Optimization","MILP Solvers","Starter"),
    ("Optimization","Multi-Objective Optimization","Enterprise"),
    ("Optimization","Robust & Resilient Optimization","Enterprise"),
    ("Inventory","MEIO Matrix","Professional"),
    ("Supply Chain","Fleet Routing","Professional"),
    ("Supply Chain","Supplier Risk Matrix","Professional"),
    ("Analytics","Advanced ML Demand Forecasting","Enterprise"),
    ("Maintenance","Predictive Maintenance Hub","Enterprise"),
    ("Maintenance","Predictive Maintenance Digital Twin","Enterprise Plus"),
    ("Economics","Capital Investment & Engineering Economics","Professional"),
    ("Workforce","Workforce Engineering","Professional"),
    ("Sustainability","Industrial Sustainability & LCA","Professional"),
    ("Benchmarking","Benchmarking & Engineering Standards","Professional"),
    ("Governance","Engineering Model Registry","Enterprise"),
    ("Governance","Scenario Versioning & Comparison","Professional"),
    ("Governance","Experiment Lab","Enterprise"),
    ("Governance","Engineering Decision Center","Enterprise"),
    ("Governance","Enterprise Security & Governance","Enterprise Plus"),
    ("Collaboration","Team Workspaces & RBAC","Enterprise"),
    ("Reporting","Executive Report Center","Enterprise"),
    ("Control","Industrial Control Center","Enterprise"),
    ("AI","Advanced Engineering Copilot","Enterprise Plus"),
    ("AI","AI Copilot","Enterprise"),
    ("Global","Localization & Multi-Currency","Professional"),
]

UNIT_DIMENSIONS = {
    "kg": "mass", "g": "mass", "lb": "mass",
    "m": "length", "cm": "length", "mm": "length", "ft": "length",
    "s": "time", "sec": "time", "min": "time", "hr": "time", "day": "time",
    "kwh": "energy", "mwh": "energy",
    "usd": "currency", "eur": "currency", "sar": "currency",
    "%": "ratio", "pct": "ratio",
    "units": "count", "unit": "count",
}

ROLE_PERMISSIONS = {
    "Owner": {"read","write","execute","approve","admin"},
    "Planner": {"read","write","execute"},
    "Engineer": {"read","write","execute"},
    "Manager": {"read","write","execute","approve"},
    "Viewer": {"read"},
}

@dataclass(frozen=True)
class ApprovalState:
    status: str
    actor: str
    changed_at: str
    note: str = ""

def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")

def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()

def canonical_tier(value: str) -> str:
    v = _norm(value)
    for tier in CANONICAL_TIERS:
        if any(_norm(alias) == v for alias in tier["legacy"]):
            return tier["key"]
    if "enterprise plus" in v or "industrial enterprise" in v:
        return "Enterprise Plus"
    if "enterprise" in v:
        return "Enterprise"
    if "operations" in v:
        return "Operations"
    if "professional" in v or "mid tier pro" in v or v == "pro":
        return "Professional"
    if "research" in v:
        return "Research"
    return "Starter"

def tier_allows(current: str, required: str) -> bool:
    c = canonical_tier(current)
    r = canonical_tier(required)
    return TIER_ORDER.index(c) >= TIER_ORDER.index(r)

def tier_matrix() -> pd.DataFrame:
    rows = []
    for t in CANONICAL_TIERS:
        rows.append({
            "Tier": t["label"],
            "Focus": t["focus"],
            "Level": TIER_ORDER.index(t["key"]) + 1,
            "Module Limit": t["module_limit"],
        })
    return pd.DataFrame(rows)

def module_matrix() -> pd.DataFrame:
    return pd.DataFrame(MODULE_MATRIX, columns=["Category","Module","Required Tier"])

def module_availability(current: str) -> pd.DataFrame:
    d = module_matrix()
    d["Available"] = d["Required Tier"].map(lambda r: tier_allows(current, r))
    return d

def ensure_excellence_db(db_path: str = "enterprise_full_workspace.db") -> bool:
    with sqlite3.connect(db_path) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS industrial_relationships(
            relationship_id TEXT PRIMARY KEY,
            from_entity TEXT NOT NULL,
            relationship TEXT NOT NULL,
            to_entity TEXT NOT NULL,
            created_by TEXT,
            created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS decision_approvals(
            approval_id TEXT PRIMARY KEY,
            decision_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            note TEXT,
            created_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS connector_health(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            connector_name TEXT,
            system_type TEXT,
            status TEXT,
            message TEXT,
            tested_at TEXT,
            tested_by TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS platform_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT,
            event_type TEXT,
            payload_json TEXT,
            created_at TEXT
        )""")
        c.commit()
    return True

def audit_event(actor: str, event_type: str, payload: Mapping[str, Any] | None = None,
                db_path: str = "enterprise_full_workspace.db") -> None:
    ensure_excellence_db(db_path)
    with sqlite3.connect(db_path) as c:
        c.execute(
            "INSERT INTO platform_events(actor,event_type,payload_json,created_at) VALUES(?,?,?,?)",
            (actor, event_type, json.dumps(payload or {}, default=str), _now()),
        )
        c.commit()

def dataframe_fingerprint(df: pd.DataFrame) -> str:
    raw = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def infer_column_types(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in df.columns:
        s = df[col]
        numeric = pd.to_numeric(s, errors="coerce")
        parsed = pd.to_datetime(s, errors="coerce")
        if numeric.notna().mean() >= 0.95:
            kind = "numeric"
        elif parsed.notna().mean() >= 0.95:
            kind = "datetime"
        elif s.dropna().astype(str).str.lower().isin(["true","false","yes","no"]).mean() >= 0.95 if len(s.dropna()) else False:
            kind = "boolean"
        else:
            kind = "text/categorical"
        rows.append({
            "Column": str(col),
            "Storage dtype": str(s.dtype),
            "Inferred type": kind,
            "Missing %": round(float(s.isna().mean()*100),2),
            "Unique values": int(s.nunique(dropna=True)),
        })
    return pd.DataFrame(rows)

def deep_data_quality(df: pd.DataFrame) -> dict:
    if df is None:
        return {"score":0.0,"rows":0,"columns":0,"issues":["No dataframe supplied"],"fingerprint":None}
    rows, cols = len(df), len(df.columns)
    issues: List[str] = []
    missing_pct = float(df.isna().mean().mean()*100) if cols else 100.0
    duplicate_pct = float(df.duplicated().mean()*100) if rows else 0.0
    if missing_pct > 0:
        issues.append(f"Missing cells: {missing_pct:.1f}%")
    if duplicate_pct > 0:
        issues.append(f"Duplicate rows: {duplicate_pct:.1f}%")
    if df.columns.duplicated().any():
        issues.append("Duplicate column names")
    for col in df.select_dtypes(include=np.number).columns:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(s) >= 8:
            q1, q3 = s.quantile(.25), s.quantile(.75)
            iqr = q3-q1
            if iqr > 0:
                out_pct = float(((s < q1-1.5*iqr) | (s > q3+1.5*iqr)).mean()*100)
                if out_pct > 1:
                    issues.append(f"Potential outliers in {col}: {out_pct:.1f}%")
    score = 100.0 - min(70.0, missing_pct*0.7) - min(20.0, duplicate_pct*0.5) - min(20.0, max(0,len(issues)-1)*3)
    return {
        "score": round(max(0,min(100,score)),1),
        "rows": rows, "columns": cols,
        "missing_pct": round(missing_pct,2),
        "duplicate_pct": round(duplicate_pct,2),
        "issues": issues,
        "fingerprint": dataframe_fingerprint(df),
    }

def validate_schema(df: pd.DataFrame, required: Sequence[str] = (),
                    unique: Sequence[str] = (), numeric_ranges: Mapping[str, Tuple[float,float]] | None = None) -> dict:
    errors: List[str] = []
    warnings: List[str] = []
    for c in required:
        if c not in df.columns:
            errors.append(f"Missing required column: {c}")
    for c in unique:
        if c in df.columns and df[c].duplicated(keep=False).any():
            errors.append(f"Uniqueness violation: {c}")
    for c, (lo, hi) in (numeric_ranges or {}).items():
        if c in df.columns:
            vals = pd.to_numeric(df[c], errors="coerce")
            bad = int(((vals < lo) | (vals > hi)).fillna(False).sum())
            if bad:
                errors.append(f"{bad} values outside {c} range [{lo}, {hi}]")
    q = deep_data_quality(df)
    warnings.extend(q["issues"])
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "quality": q,
        "types": infer_column_types(df).to_dict("records"),
    }

def validate_units(units: Mapping[str,str]) -> dict:
    unknown = {}
    dimensions = {}
    for name, unit in units.items():
        u = str(unit).strip().lower()
        dimensions[name] = UNIT_DIMENSIONS.get(u)
        if dimensions[name] is None:
            unknown[name] = unit
    return {"valid": not unknown, "unknown": unknown, "dimensions": dimensions}

def referential_integrity(left: pd.DataFrame, left_key: str, right: pd.DataFrame, right_key: str) -> dict:
    if left_key not in left.columns or right_key not in right.columns:
        return {"valid": False, "missing": None, "message": "Reference columns not found"}
    left_vals = set(left[left_key].dropna().astype(str))
    right_vals = set(right[right_key].dropna().astype(str))
    missing = sorted(left_vals-right_vals)
    return {"valid": not missing, "missing": missing[:100], "missing_count": len(missing)}

def upsert_relationships(rows: pd.DataFrame, username: str,
                         db_path: str = "enterprise_full_workspace.db") -> int:
    req = {"From","Relationship","To"}
    if not req.issubset(rows.columns):
        raise ValueError(f"Relationship table requires {sorted(req)}")
    ensure_excellence_db(db_path)
    count = 0
    with sqlite3.connect(db_path) as c:
        for r in rows.to_dict("records"):
            raw = f"{r['From']}|{r['Relationship']}|{r['To']}"
            rid = "REL-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()
            c.execute(
                "INSERT OR REPLACE INTO industrial_relationships VALUES(?,?,?,?,?,?)",
                (rid, str(r["From"]), str(r["Relationship"]), str(r["To"]), username, _now()),
            )
            count += 1
        c.commit()
    audit_event(username, "digital_thread_relationship_upsert", {"count":count}, db_path)
    return count

def impact_analysis(entity_id: str, max_hops: int = 3,
                    db_path: str = "enterprise_full_workspace.db") -> pd.DataFrame:
    ensure_excellence_db(db_path)
    edges = pd.DataFrame()
    with sqlite3.connect(db_path) as c:
        edges = pd.read_sql("SELECT from_entity AS From, relationship AS Relationship, to_entity AS To FROM industrial_relationships", c)
    if edges.empty:
        return pd.DataFrame(columns=["Entity","Hops","Path"])
    frontier = [(entity_id,0,entity_id)]
    seen = {entity_id}
    out = []
    while frontier:
        node, hops, path = frontier.pop(0)
        if hops >= max_hops:
            continue
        next_edges = edges[edges["From"].eq(node)]
        for r in next_edges.itertuples(index=False):
            target = str(r.To)
            if target not in seen:
                seen.add(target)
                new_path = f"{path} → {r.Relationship} → {target}"
                out.append({"Entity":target,"Hops":hops+1,"Path":new_path})
                frontier.append((target,hops+1,new_path))
    return pd.DataFrame(out)

def constrained_schedule(orders: pd.DataFrame,
                         maintenance: pd.DataFrame | None = None,
                         labor: Mapping[str,float] | None = None,
                         materials: Mapping[str,float] | None = None,
                         setup_matrix: Mapping[Tuple[str,str],float] | None = None,
                         start_time: datetime | None = None) -> tuple[pd.DataFrame,dict]:
    req = {"Order","Product","Qty","DueDate","ProcessingMin","Machine"}
    missing = req - set(orders.columns)
    if missing:
        raise ValueError(f"Scheduling requires {sorted(missing)}")
    d = orders.copy()
    d["DueDate"] = pd.to_datetime(d["DueDate"], errors="coerce")
    for c in ["Qty","ProcessingMin"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["SetupMin"] = pd.to_numeric(d.get("SetupMin",0), errors="coerce").fillna(0)
    d["Priority"] = pd.to_numeric(d.get("Priority",0), errors="coerce").fillna(0)
    d["MaterialReady"] = pd.to_datetime(d.get("MaterialReady", pd.NaT), errors="coerce")
    d = d.sort_values(["Priority","DueDate"], ascending=[False,True]).reset_index(drop=True)
    maint = maintenance.copy() if maintenance is not None else pd.DataFrame(columns=["Machine","Start","End"])
    if not maint.empty:
        maint["Start"] = pd.to_datetime(maint["Start"], errors="coerce")
        maint["End"] = pd.to_datetime(maint["End"], errors="coerce")
    avail = {m: (start_time or datetime.now()) for m in d["Machine"].astype(str).unique()}
    previous_product: Dict[str,str] = {}
    material_remaining = dict(materials or {})
    rows = []
    blocked = []
    for r in d.itertuples(index=False):
        machine = str(r.Machine)
        ready = avail[machine]
        if pd.notna(r.MaterialReady):
            ready = max(ready, r.MaterialReady.to_pydatetime())
        qty = float(r.Qty)
        mat_available = material_remaining.get(str(r.Product), math.inf)
        if mat_available < qty:
            blocked.append({"Order":r.Order,"Reason":f"Material shortfall: need {qty:g}, available {mat_available:g}"})
            continue
        setup = float(r.SetupMin)
        prev = previous_product.get(machine)
        if setup_matrix and prev is not None:
            setup += float(setup_matrix.get((prev,str(r.Product)), setup_matrix.get((str(r.Product),prev),0)))
        finish = ready + timedelta(minutes=max(.1,float(r.ProcessingMin)+setup))
        # Push through maintenance windows until it does not overlap.
        changed = True
        while changed and not maint.empty:
            changed = False
            windows = maint[(maint["Machine"].astype(str)==machine)]
            for m in windows.itertuples(index=False):
                ms, me = m.Start, m.End
                if pd.isna(ms) or pd.isna(me):
                    continue
                if ready < me.to_pydatetime() and finish > ms.to_pydatetime():
                    ready = max(ready, me.to_pydatetime())
                    finish = ready + timedelta(minutes=max(.1,float(r.ProcessingMin)+setup))
                    changed = True
        if labor:
            cap = float(labor.get(machine, math.inf))
            if cap <= 0:
                blocked.append({"Order":r.Order,"Reason":"No available labor capacity for machine"})
                continue
        due = r.DueDate.to_pydatetime() if pd.notna(r.DueDate) else finish
        late = max(0.0,(finish-due).total_seconds()/60)
        rows.append({
            "Order":r.Order,"Product":r.Product,"Qty":qty,"Machine":machine,
            "Start":ready,"Finish":finish,"DueDate":due,"SetupMin":setup,
            "LateMin":round(late,2),"OnTime":late<=0,
        })
        avail[machine] = finish
        previous_product[machine] = str(r.Product)
        if str(r.Product) in material_remaining:
            material_remaining[str(r.Product)] -= qty
    out = pd.DataFrame(rows)
    diagnostics = {
        "scheduled_orders": len(out),
        "blocked_orders": len(blocked),
        "blocked": blocked,
        "total_late_min": float(out["LateMin"].sum()) if not out.empty else 0.0,
        "on_time_rate": float(out["OnTime"].mean()*100) if not out.empty else 0.0,
        "feasible": len(blocked) == 0,
    }
    return out, diagnostics

def control_chart(data: Sequence[float], chart: str = "I-MR", sigma: float = 3.0) -> pd.DataFrame:
    x = pd.to_numeric(pd.Series(data), errors="coerce").dropna().astype(float).reset_index(drop=True)
    if len(x) < 4:
        raise ValueError("At least four observations are required.")
    mean = x.mean()
    sd = x.std(ddof=1)
    z = (x-mean)/max(sd,1e-12)
    if chart.upper() == "I-MR":
        moving = x.diff().abs()
        mr_bar = moving.dropna().mean()
        sigma_i = mr_bar/1.128 if pd.notna(mr_bar) and mr_bar>0 else sd
        ucl = mean + sigma*sigma_i
        lcl = mean - sigma*sigma_i
    else:
        ucl, lcl = mean + sigma*sd, mean - sigma*sd
    result = pd.DataFrame({"Observation":np.arange(1,len(x)+1),"Value":x,"Z":z,"UCL":ucl,"LCL":lcl})
    result["OutOfControl"] = (result["Value"]>ucl)|(result["Value"]<lcl)
    return result

def proportion_chart(counts: Sequence[int], samples: Sequence[int], chart: str="p") -> pd.DataFrame:
    c = pd.to_numeric(pd.Series(counts), errors="coerce").fillna(0)
    n = pd.to_numeric(pd.Series(samples), errors="coerce").clip(lower=1)
    p = c/n
    pbar = float(c.sum()/n.sum())
    if chart.lower() == "u":
        mean = pbar
        limits = np.sqrt(np.maximum(mean/n,0))
        ucl, lcl = mean + 3*limits, np.maximum(0,mean-3*limits)
    else:
        se = np.sqrt(np.maximum(pbar*(1-pbar)/n,0))
        ucl, lcl = pbar + 3*se, np.maximum(0,pbar-3*se)
    return pd.DataFrame({"Sample":np.arange(1,len(p)+1),"Rate":p,"UCL":ucl,"LCL":lcl,"OutOfControl":(p>ucl)|(p<lcl)})

def capability_extended(values: Sequence[float], lsl: float, usl: float, target: float | None=None) -> dict:
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna().astype(float)
    if len(x) < 3 or usl <= lsl:
        raise ValueError("Need >=3 measurements and USL > LSL.")
    sd = float(x.std(ddof=1))
    mean = float(x.mean())
    if sd <= 0:
        return {"Mean":mean,"Std":0.0,"Cp":math.inf,"Cpk":math.inf,"Cpu":math.inf,"Cpl":math.inf,"Pp":math.inf,"Ppk":math.inf,"Zbench":math.inf}
    cp = (usl-lsl)/(6*sd)
    cpu, cpl = (usl-mean)/(3*sd), (mean-lsl)/(3*sd)
    pp = (usl-lsl)/(6*sd)
    ppk = min(cpu,cpl)
    zbench = 3*ppk
    out = {"Mean":mean,"Std":sd,"Cp":cp,"Cpk":min(cpu,cpl),"Cpu":cpu,"Cpl":cpl,"Pp":pp,"Ppk":ppk,"Zbench":zbench}
    if target is not None:
        out["Target"] = float(target)
        out["Cpm"] = (usl-lsl)/(6*math.sqrt(sd**2+(mean-target)**2))
    return out

def gage_rr_extended(df: pd.DataFrame, part="Part", operator="Operator", value="Measurement") -> dict:
    req={part,operator,value}
    if not req.issubset(df.columns):
        raise ValueError(f"Gage R&R requires {sorted(req)}")
    d=df.copy()
    d[value]=pd.to_numeric(d[value],errors="coerce")
    d=d.dropna(subset=[value])
    if d.empty:
        raise ValueError("No valid measurements.")
    repeat_var=float(d.groupby([part,operator])[value].var(ddof=1).fillna(0).mean())
    part_var=float(d.groupby(part)[value].mean().var(ddof=1)) if d[part].nunique()>1 else 0.0
    op_var=float(d.groupby(operator)[value].mean().var(ddof=1)) if d[operator].nunique()>1 else 0.0
    total=max(1e-12,repeat_var+part_var+op_var)
    grr=repeat_var+op_var
    ndc=1.41*math.sqrt(max(part_var,0)/max(grr,1e-12))
    return {"Repeatability SD":math.sqrt(max(repeat_var,0)),
            "Reproducibility SD":math.sqrt(max(op_var,0)),
            "Part SD":math.sqrt(max(part_var,0)),
            "%GRR":grr/total*100,"%Part":part_var/total*100,"ndc":int(max(0,math.floor(ndc)))}

def doe_2level_effects(df: pd.DataFrame, response: str, factors: Sequence[str]) -> pd.DataFrame:
    if response not in df.columns or any(c not in df.columns for c in factors):
        raise ValueError("Response/factor columns not found.")
    d=df[[response,*factors]].copy()
    y=pd.to_numeric(d[response],errors="coerce")
    rows=[]
    for col in factors:
        x=pd.to_numeric(d[col],errors="coerce")
        hi=y[x>0].mean() if (x>0).any() else np.nan
        lo=y[x<0].mean() if (x<0).any() else np.nan
        rows.append({"Factor":col,"Effect":float(hi-lo) if pd.notna(hi) and pd.notna(lo) else np.nan})
    if len(factors) >= 2:
        for a,b in product(factors,factors):
            if a>=b: continue
            xa=pd.to_numeric(d[a],errors="coerce"); xb=pd.to_numeric(d[b],errors="coerce")
            contrast=y[(xa*xb)>0].mean()-y[(xa*xb)<0].mean()
            rows.append({"Factor":f"{a} × {b}","Effect":float(contrast)})
    return pd.DataFrame(rows).sort_values("Effect",key=lambda s:s.abs(),ascending=False)

def reliability_summary(times: Sequence[float], censor: Sequence[bool] | None=None) -> dict:
    x=pd.to_numeric(pd.Series(times),errors="coerce").dropna().astype(float)
    if len(x)<3 or (x<=0).any():
        raise ValueError("Need at least three positive times.")
    shape, loc, scale = stats.weibull_min.fit(x, floc=0)
    b10=float(scale*(-math.log(.9))**(1/shape))
    median=float(scale*(math.log(2))**(1/shape))
    return {"Beta":float(shape),"Eta":float(scale),"B10":b10,"Median Life":median,
            "MTTF":float(scale*math.gamma(1+1/shape))}

def simulation_statistics(replication_df: pd.DataFrame, metric: str) -> dict:
    if metric not in replication_df.columns:
        raise ValueError(f"Metric not found: {metric}")
    x=pd.to_numeric(replication_df[metric],errors="coerce").dropna().astype(float)
    if len(x)<2:
        raise ValueError("At least two replications are required.")
    mean=float(x.mean()); sd=float(x.std(ddof=1)); se=sd/math.sqrt(len(x))
    tcrit=float(stats.t.ppf(.975,len(x)-1))
    return {"Replications":len(x),"Mean":mean,"Std Dev":sd,"SE":se,
            "CI95 Lower":mean-tcrit*se,"CI95 Upper":mean+tcrit*se,
            "Half Width":tcrit*se}

def warmup_diagnostic(series: Sequence[float], window: int = 10) -> dict:
    x=pd.to_numeric(pd.Series(series),errors="coerce").dropna().astype(float).reset_index(drop=True)
    if len(x)<window*2:
        return {"recommended_cutoff":0,"reason":"More observations required","stable":False}
    rolling=x.rolling(window).mean()
    tail=rolling.iloc[-window:].mean()
    candidates=[]
    for i in range(window,len(x)-window):
        local=rolling.iloc[i:i+window].mean()
        if abs(local-tail) <= max(abs(tail)*.02,1e-9):
            candidates.append(i)
    cutoff=int(candidates[0]) if candidates else int(len(x)*.1)
    return {"recommended_cutoff":cutoff,"tail_mean":float(tail),"stable":bool(candidates),"reason":"Rolling mean convergence diagnostic"}

def bbox_collision_check(layout: pd.DataFrame) -> pd.DataFrame:
    req={"Asset","X","Y","Length","Width"}
    if not req.issubset(layout.columns):
        raise ValueError(f"Layout requires {sorted(req)}")
    d=layout.copy()
    for c in ["X","Y","Length","Width"]:
        d[c]=pd.to_numeric(d[c],errors="coerce").fillna(0)
    rows=[]
    for i in range(len(d)):
        a=d.iloc[i]
        ax1, ax2 = a.X-a.Length/2, a.X+a.Length/2
        ay1, ay2 = a.Y-a.Width/2, a.Y+a.Width/2
        for j in range(i+1,len(d)):
            b=d.iloc[j]
            bx1, bx2 = b.X-b.Length/2, b.X+b.Length/2
            by1, by2 = b.Y-b.Width/2, b.Y+b.Width/2
            overlap=(ax1<bx2 and ax2>bx1 and ay1<by2 and ay2>by1)
            if overlap:
                rows.append({"Asset A":a.Asset,"Asset B":b.Asset,"Collision":True})
    return pd.DataFrame(rows, columns=["Asset A","Asset B","Collision"])

def flow_distance(layout: pd.DataFrame, sequence: Sequence[str]) -> dict:
    req={"Asset","X","Y"}
    if not req.issubset(layout.columns):
        raise ValueError(f"Layout requires {sorted(req)}")
    coords=layout.set_index("Asset")[["X","Y"]].apply(pd.to_numeric,errors="coerce")
    total=0.0; legs=[]
    for a,b in zip(sequence,sequence[1:]):
        if a not in coords.index or b not in coords.index:
            continue
        dx=float(coords.loc[b,"X"]-coords.loc[a,"X"]); dy=float(coords.loc[b,"Y"]-coords.loc[a,"Y"])
        dist=math.hypot(dx,dy); total += dist
        legs.append({"From":a,"To":b,"Distance":dist})
    return {"Total Distance":total,"Legs":pd.DataFrame(legs)}

def pareto_frontier_v2(df: pd.DataFrame, objectives: Sequence[str], minimize: Sequence[bool]) -> pd.DataFrame:
    if len(objectives)!=len(minimize): raise ValueError("Objectives and minimize must match.")
    arr=df[list(objectives)].apply(pd.to_numeric,errors="coerce").to_numpy()
    keep=np.ones(len(arr),dtype=bool)
    for i in range(len(arr)):
        for j in range(len(arr)):
            if i==j: continue
            dominates=True; strict=False
            for k in range(len(objectives)):
                if np.isnan(arr[j,k]) or np.isnan(arr[i,k]):
                    dominates=False; break
                if minimize[k]:
                    if arr[j,k] > arr[i,k]: dominates=False; break
                    strict |= arr[j,k] < arr[i,k]
                else:
                    if arr[j,k] < arr[i,k]: dominates=False; break
                    strict |= arr[j,k] > arr[i,k]
            if dominates and strict:
                keep[i]=False; break
    return df.loc[keep].reset_index(drop=True)

def robust_scenarios(base: Mapping[str,float], scenarios: pd.DataFrame, simulations: int=5000, seed: int=42) -> pd.DataFrame:
    rng=np.random.default_rng(seed)
    rows=[]
    for r in scenarios.to_dict("records"):
        demand_mean=float(r.get("Demand Mean",base.get("Demand Mean",1000)))
        demand_std=float(r.get("Demand Std",base.get("Demand Std",100)))
        capacity=float(r.get("Capacity",base.get("Capacity",1100)))
        disruption=float(r.get("Disruption Probability",base.get("Disruption Probability",0.05)))
        multiplier=float(r.get("Disruption Multiplier",base.get("Disruption Multiplier",0.6)))
        demand=np.maximum(0,rng.normal(demand_mean,max(demand_std,1e-9),simulations))
        shock=rng.random(simulations)<np.clip(disruption,0,1)
        cap=capacity*np.where(shock,multiplier,1.0)
        service=float(np.mean(demand<=cap))
        exposure=np.maximum(0,demand-cap)
        rows.append({"Scenario":r.get("Scenario","Unnamed"),"Service Probability":service,
                     "Stockout Probability":1-service,
                     "P95 Exposure":float(np.percentile(exposure,95)),
                     "Mean Exposure":float(np.mean(exposure))})
    return pd.DataFrame(rows)

def economics_sensitivity(initial_investment: float, cash_flows: Sequence[float],
                          discount_rates: Sequence[float], capex_multipliers: Sequence[float]) -> pd.DataFrame:
    rows=[]
    base=np.array(list(cash_flows),dtype=float)
    for rate in discount_rates:
        for mult in capex_multipliers:
            flows=np.r_[-abs(initial_investment)*float(mult),base]
            npv=float(sum(flows[t]/((1+float(rate))**t) for t in range(len(flows))))
            rows.append({"Discount Rate":rate,"CAPEX Multiplier":mult,"NPV":npv})
    return pd.DataFrame(rows)

def workforce_scenario(staff: int, minutes_per_shift: float, productive_pct: float,
                       absenteeism_pct: float, overtime_hours: float, wage_per_hour: float) -> dict:
    effective_staff=max(0,float(staff)*(1-float(absenteeism_pct)/100))
    productive_minutes=effective_staff*minutes_per_shift*float(productive_pct)/100
    overtime_minutes=effective_staff*float(overtime_hours)*60
    labor_cost=(effective_staff*minutes_per_shift/60 + effective_staff*float(overtime_hours))*float(wage_per_hour)
    return {"Effective Staff":effective_staff,"Productive Minutes":productive_minutes,
            "Overtime Minutes":overtime_minutes,"Estimated Labor Cost":labor_cost}

def sustainability_scenario(df: pd.DataFrame) -> dict:
    req={"Activity","Scope","Quantity","EmissionFactor"}
    if not req.issubset(df.columns):
        raise ValueError(f"Sustainability table requires {sorted(req)}")
    d=df.copy()
    d["Quantity"]=pd.to_numeric(d["Quantity"],errors="coerce").fillna(0)
    d["EmissionFactor"]=pd.to_numeric(d["EmissionFactor"],errors="coerce").fillna(0)
    d["tCO2e"]=d["Quantity"]*d["EmissionFactor"]/1000
    scope=d.groupby("Scope",dropna=False)["tCO2e"].sum().reset_index()
    total=float(d["tCO2e"].sum())
    return {"detail":d,"scope_summary":scope,"total_tCO2e":total}

def benchmark_gap(actual: pd.DataFrame, benchmark: pd.DataFrame) -> pd.DataFrame:
    req={"Metric","Actual"}
    if not req.issubset(actual.columns) or not {"Metric","Benchmark"}.issubset(benchmark.columns):
        raise ValueError("Actual needs Metric/Actual; benchmark needs Metric/Benchmark.")
    out=actual.merge(benchmark,on="Metric",how="left")
    out["Delta"]=pd.to_numeric(out["Actual"],errors="coerce")-pd.to_numeric(out["Benchmark"],errors="coerce")
    out["Gap %"]=out["Delta"]/pd.to_numeric(out["Benchmark"],errors="coerce").replace(0,np.nan)*100
    return out

def build_decision_card(title: str, module: str, metrics: Mapping[str,Any],
                       assumptions: Mapping[str,Any], uncertainty: Mapping[str,Any],
                       status: str="Proposed") -> dict:
    return {"title":title,"module":module,"metrics":dict(metrics),
            "assumptions":dict(assumptions),"uncertainty":dict(uncertainty),
            "status":status,"created_at":_now()}

def save_decision(card: dict, username: str, db_path: str="enterprise_full_workspace.db") -> str:
    ensure_excellence_db(db_path)
    raw=json.dumps(card,sort_keys=True,default=str)
    did="DEC-"+hashlib.sha256(raw.encode()).hexdigest()[:12].upper()
    with sqlite3.connect(db_path) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS platform_decisions(
            decision_id TEXT PRIMARY KEY,title TEXT,module TEXT,metrics_json TEXT,
            assumptions_json TEXT,uncertainty_json TEXT,created_by TEXT,created_at TEXT,status TEXT)""")
        c.execute("INSERT OR REPLACE INTO platform_decisions VALUES(?,?,?,?,?,?,?,?,?)",
                  (did,card["title"],card["module"],json.dumps(card["metrics"],default=str),
                   json.dumps(card["assumptions"],default=str),json.dumps(card["uncertainty"],default=str),
                   username,card["created_at"],card["status"]))
        c.commit()
    audit_event(username,"decision_created",{"decision_id":did,"module":card["module"]},db_path)
    return did

def record_approval(decision_id: str, actor: str, action: str, note: str="",
                    db_path: str="enterprise_full_workspace.db") -> ApprovalState:
    allowed={"Proposed","Approved","Rejected","Needs Revision"}
    action=str(action)
    if action not in allowed:
        raise ValueError(f"Action must be one of {sorted(allowed)}")
    ensure_excellence_db(db_path)
    with sqlite3.connect(db_path) as c:
        aid="APR-"+hashlib.sha256(f"{decision_id}|{actor}|{_now()}".encode()).hexdigest()[:12].upper()
        c.execute("INSERT INTO decision_approvals VALUES(?,?,?,?,?,?)",
                  (aid,decision_id,actor,action,note,_now()))
        c.execute("UPDATE platform_decisions SET status=? WHERE decision_id=?",(action,decision_id))
        c.commit()
    audit_event(actor,"decision_approval",{"decision_id":decision_id,"action":action},db_path)
    return ApprovalState(action,actor,_now(),note)

def permission_check(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role,set())

def connector_validation(name: str, system_type: str, endpoint: str) -> dict:
    stype=_norm(system_type)
    ep=str(endpoint or "").strip()
    errors=[]; warnings=[]
    if not name.strip():
        errors.append("Connector name is required.")
    if not ep and stype not in {"sql","local db","sqlite"}:
        errors.append("Endpoint is required for network connectors.")
    if stype in {"mqtt","opc ua","opc-ua"} and ep and not (ep.startswith("mqtt://") or ep.startswith("mqtts://") or ep.startswith("opc.tcp://")):
        warnings.append("Endpoint scheme does not match the selected protocol.")
    if stype in {"rest","sap","oracle","wms","api"} and ep and not ep.startswith(("http://","https://")):
        warnings.append("REST-style connectors normally use http:// or https://.")
    if stype=="sql" and ep and not any(x in ep.lower() for x in ("sqlite","postgres","mysql","sqlserver")):
        warnings.append("SQL endpoint is syntactically accepted but its dialect should be confirmed.")
    return {"valid":not errors,"errors":errors,"warnings":warnings,"credential_handling":"Session/environment secrets only; never log secret values."}

def copilot_execution_plan(prompt: str) -> dict:
    p=str(prompt or "").lower()
    steps=[]
    def add(key,title,reason,approval=True):
        steps.append({"id":f"S{len(steps)+1}","tool":key,"title":title,"reason":reason,"requires_approval":approval})
    if any(x in p for x in ["import","upload","excel","csv","clean"]):
        add("data.validate","Validate / clean source data","Normalize input and surface data-quality issues before analysis.")
    if any(x in p for x in ["forecast","demand","predict"]):
        add("forecast.ml","Forecast demand","Build a grounded forecast from selected historical and external-driver columns.")
    if any(x in p for x in ["schedule","aps","production"]):
        add("planning.aps","Build constrained production schedule","Respect machine, material, labor, maintenance and setup constraints.")
    if any(x in p for x in ["inventory","safety stock","meio"]):
        add("inventory.optimize","Analyze inventory policy","Evaluate service, stock exposure and inventory trade-offs.")
    if any(x in p for x in ["simulation","monte carlo","risk","disruption"]):
        add("risk.simulate","Run uncertainty / simulation analysis","Quantify ranges and probabilities rather than a single deterministic result.")
    if any(x in p for x in ["optimize","optimization","pareto","cost"]):
        add("optimization.multiobjective","Compare constrained alternatives","Expose objective trade-offs and the Pareto frontier.")
    if any(x in p for x in ["carbon","sustainability","emission","lca"]):
        add("sustainability.lca","Calculate sustainability impacts","Track scope/lifecycle impacts alongside operational metrics.")
    if any(x in p for x in ["report","executive","board","presentation"]):
        add("report.executive","Prepare executive reporting package","Assemble reproducible tables, charts, assumptions and model metadata.")
    if not steps:
        add("analysis.explain","Inspect request and map relevant modules","Build a read-only execution plan before changing data.",False)
    return {"prompt":prompt,"steps":steps,"approval_required":any(s["requires_approval"] for s in steps),
            "guardrail":"No write/execute action should occur until the user approves the proposed plan."}

def model_version(existing_versions: Sequence[str]) -> str:
    nums=[]
    for v in existing_versions:
        m=re.fullmatch(r"(\d+)\.(\d+)\.(\d+)",str(v))
        if m: nums.append(tuple(map(int,m.groups())))
    if not nums: return "1.0.0"
    a,b,c=max(nums)
    return f"{a}.{b}.{c+1}"

def reproducibility_manifest(module: str, inputs: Mapping[str,Any],
                             parameters: Mapping[str,Any], result: Any) -> dict:
    payload={"module":module,"inputs":dict(inputs),"parameters":dict(parameters),
             "result":result,"timestamp":_now()}
    raw=json.dumps(payload,sort_keys=True,default=str).encode()
    return {**payload,"manifest_sha256":hashlib.sha256(raw).hexdigest()}

def result_health(df: pd.DataFrame, feasible: bool, solver_status: str,
                  uncertainty: str, assumptions_complete: bool=True) -> dict:
    q=deep_data_quality(df)
    return {
        "Data Quality":q["score"],
        "Feasibility":"Pass" if feasible else "Fail",
        "Solver Status":solver_status,
        "Uncertainty":uncertainty,
        "Assumptions":"Complete" if assumptions_complete else "Incomplete",
        "Reproducibility":"Ready",
        "Issues":q["issues"],
    }

def export_manifest_tables(module: str, tables: Sequence[Tuple[str,pd.DataFrame]],
                           actor: str) -> pd.DataFrame:
    rows=[]
    for label,df in tables:
        rows.append({
            "Artifact":label,
            "Rows":len(df),
            "Columns":len(df.columns),
            "Fingerprint":dataframe_fingerprint(df),
            "Actor":actor,
            "Generated At":_now(),
        })
    return pd.DataFrame(rows)
