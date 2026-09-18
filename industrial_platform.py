"""Shoir-IE Industrial Platform Suite.

Additive, production-oriented services for the unified industrial decision platform:
digital thread, APS/MRP, MES, quality/reliability, simulation, 3D layout,
connectivity, multi-objective/robust optimization, registry/experiments,
economics, workforce, sustainability, validation, benchmarking, decision center,
and enterprise governance.

The module functions are deterministic where possible, persist important metadata,
and return explicit diagnostics rather than inventing data.
"""
from __future__ import annotations
import io, json, math, os, re, sqlite3, hashlib, heapq, time
from datetime import datetime, timedelta
from itertools import product
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

PLATFORM_CATALOG = [
    {"tier":"Starter","category":"Core Platform","name":"Engineering Validation Center","when":"Validate tables, model assumptions, units, ranges and result health before acting.","example":"Upload an engineering table and receive a data-quality, feasibility and reproducibility checklist."},
    {"tier":"Mid-Tier Pro","category":"Industrial Model","name":"Industrial Data Model & Digital Thread","when":"Keep products, customers, suppliers, facilities, machines, people, materials, routes and orders linked.","example":"Change a facility or machine attribute once and trace the affected planning records."},
    {"tier":"Professional","category":"Planning","name":"Advanced Planning & Scheduling","when":"Create finite-capacity schedules that respect machines, labor, setup time, material availability and due dates.","example":"Schedule rush orders around maintenance downtime without overbooking a machine."},
    {"tier":"Professional","category":"Quality","name":"Quality Engineering & Reliability","when":"Run statistical quality, measurement, FMEA and reliability analysis from one workspace.","example":"Combine SPC, Cp/Cpk, Gage R&R, DOE, ANOVA and Weibull analysis for a process study."},
    {"tier":"Professional","category":"Economics","name":"Capital Investment & Engineering Economics","when":"Compare industrial investments using NPV, IRR, payback and sensitivity.","example":"Compare automation CAPEX against labor, maintenance and energy savings."},
    {"tier":"Professional","category":"Workforce","name":"Workforce Engineering","when":"Design staffing, takt, balance, shifts, skills and ergonomic workloads.","example":"Balance work elements to takt and identify understaffed stations."},
    {"tier":"Professional","category":"Sustainability","name":"Industrial Sustainability & LCA","when":"Evaluate energy, water, waste and lifecycle emissions alongside cost and service.","example":"Compare process alternatives on carbon, water, waste and operating cost."},
    {"tier":"Professional","category":"Benchmarking","name":"Benchmarking & Engineering Standards","when":"Compare configurable KPIs against your chosen benchmark sources and dates.","example":"Compare OEE, OTIF, inventory turns and energy per unit against configured targets."},
    {"tier":"Enterprise","category":"Manufacturing","name":"Manufacturing Execution System","when":"Connect work orders, dispatch, actual production, downtime, quality, WIP and genealogy.","example":"Track a work order from dispatch through production confirmation and quality release."},
    {"tier":"Enterprise","category":"Simulation","name":"Industrial Simulation Lab","when":"Test DES, agent-based and system-dynamics scenarios before changing the real operation.","example":"Compare queue throughput under one versus two packing stations with confidence intervals."},
    {"tier":"Enterprise","category":"Facilities","name":"3D Factory Designer","when":"Model equipment, people, storage, flow, travel distance and facility geometry visually.","example":"Place machines in 3D, review travel paths and feed the same layout into simulation."},
    {"tier":"Enterprise","category":"Connectivity","name":"Industrial Connectivity Hub","when":"Manage and test REST, SQL, MQTT and OPC-UA connector profiles.","example":"Test a plant endpoint, record sync health and keep credentials out of analytics logs."},
    {"tier":"Enterprise","category":"Optimization","name":"Multi-Objective Optimization","when":"Trade off cost, service, carbon, risk, inventory, lead time and capacity together.","example":"Explore the Pareto frontier between logistics cost and carbon."},
    {"tier":"Enterprise","category":"Optimization","name":"Robust & Resilient Optimization","when":"Evaluate decisions against demand, lead-time, supplier, energy and capacity uncertainty.","example":"Compare nominal capacity with the probability of meeting demand across thousands of shocks."},
    {"tier":"Enterprise","category":"Governance","name":"Engineering Model Registry","when":"Version models, parameters, data hashes, assumptions, solvers and results for reproducibility.","example":"Reproduce a planning study six months later from its registered snapshot."},
    {"tier":"Enterprise","category":"Experimentation","name":"Experiment Lab","when":"Run many controlled scenarios and compare cost, service, risk, inventory, carbon and capacity.","example":"Batch-test baseline, demand surge, supplier outage and capacity-expansion cases."},
    {"tier":"Enterprise","category":"Control","name":"Industrial Control Center","when":"See demand, inventory, production, supplier, transport, machine, quality, carbon, risk and finance health together.","example":"Click a red issue and jump into the module responsible for the underlying KPI."},
    {"tier":"Enterprise","category":"Decisions","name":"Engineering Decision Center","when":"Turn model results into auditable decisions with assumptions, deltas, uncertainty and approvals.","example":"Create an approval-ready decision card from a network optimization run."},
    {"tier":"Enterprise","category":"Data Platform","name":"Industrial Data Platform","when":"Ingest, profile, hash, catalog and prepare operational datasets for downstream modules.","example":"Upload a multi-sheet workbook, validate schema and register a reusable dataset."},
    {"tier":"Enterprise Plus","category":"AI","name":"Advanced Engineering Copilot","when":"Orchestrate multi-step engineering workflows with preview, approval and tool execution.","example":"Clean a workbook, forecast demand, test risk, compare scenarios and prepare a report after one approval."},
    {"tier":"Enterprise Plus","category":"Digital Twin","name":"Live Industrial Digital Twin","when":"Maintain a common live state for assets, telemetry, production and planning.","example":"Combine telemetry and production events into a current machine and line state."},
    {"tier":"Enterprise","category":"AI & Forecasting","name":"Advanced ML Demand Forecasting","when":"Forecast SKU demand using history plus seasonality and optional promotions, weather and macroeconomic variables.","example":"Train a transparent regression forecast with external drivers and export the forecast and uncertainty."},
    {"tier":"Mid-Tier Pro","category":"Scenario Management","name":"Scenario Versioning & Comparison","when":"Save named baseline and alternative configurations and compare their KPI deltas.","example":"Compare Baseline Q3 Logistics with High-Tariff Expansion side by side."},
    {"tier":"Enterprise","category":"Collaboration","name":"Team Workspaces & RBAC","when":"Share industrial projects with planners, engineers, managers and viewers using explicit permissions.","example":"Give planners edit rights while managers can approve decisions and viewers remain read-only."},
    {"tier":"Enterprise","category":"Reporting","name":"Executive Report Center","when":"Turn solver tables and charts into board-ready PDF and PowerPoint packages.","example":"Export a scenario comparison with KPIs, charts, assumptions and decision notes."},
    {"tier":"Enterprise Plus","category":"Maintenance","name":"Predictive Maintenance Digital Twin","when":"Use telemetry trends or labeled failures to estimate maintenance risk and remaining-useful-life proxies.","example":"Score assets from vibration, temperature and runtime data and schedule inspection candidates."},
    {"tier":"Mid-Tier Pro","category":"Global Operations","name":"Localization & Multi-Currency","when":"Normalize financial values across currencies and maintain configurable regional trade-compliance rules.","example":"Convert facility costs to a reporting currency and flag routes requiring a compliance rule review."},
    {"tier":"Enterprise Plus","category":"Security","name":"Enterprise Security & Governance","when":"Manage policy, audit, API access, retention, workspace isolation and identity configuration.","example":"Review security posture, role assignments and auditable configuration changes."},
]

TIER_FEATURES = {
    "Starter": ["Engineering Validation Center", "Excel Data Cleaning & Import"],
    "Mid-Tier Pro": [
        "Industrial Data Model & Digital Thread",
        "Engineering Validation Center",
        "Excel Data Cleaning & Import",
        "Carbon Accounting",
    ],
    "Professional": [
        "Industrial Data Model & Digital Thread","Advanced Planning & Scheduling","Quality Engineering & Reliability",
        "Capital Investment & Engineering Economics","Workforce Engineering","Industrial Sustainability & LCA",
        "Benchmarking & Engineering Standards","Engineering Validation Center","Excel Data Cleaning & Import",
        "Carbon Accounting","MEIO Matrix","Fleet Routing","Production Planning & Control (PPC)",
    ],
    "Enterprise": [
        "Manufacturing Execution System","Industrial Simulation Lab","3D Factory Designer",
        "Industrial Connectivity Hub","Multi-Objective Optimization","Robust & Resilient Optimization",
        "Engineering Model Registry","Experiment Lab","Industrial Control Center","Engineering Decision Center",
        "Industrial Data Platform","Advanced Planning & Scheduling","Quality Engineering & Reliability",
        "Capital Investment & Engineering Economics","Workforce Engineering","Industrial Sustainability & LCA",
        "Benchmarking & Engineering Standards","Industrial Data Model & Digital Thread",
        "AI Copilot","Monte Carlo Sim","Sensitivity Analysis","Digital Twin & Discrete-Event Simulation",
    ],
    "Enterprise Plus": [
        "Advanced Engineering Copilot","Live Industrial Digital Twin","Enterprise Security & Governance",
        "Manufacturing Execution System","Industrial Simulation Lab","3D Factory Designer",
        "Industrial Connectivity Hub","Multi-Objective Optimization","Robust & Resilient Optimization",
        "Engineering Model Registry","Experiment Lab","Industrial Control Center","Engineering Decision Center",
        "Industrial Data Platform","Advanced Planning & Scheduling","Quality Engineering & Reliability",
        "Capital Investment & Engineering Economics","Workforce Engineering","Industrial Sustainability & LCA",
        "Benchmarking & Engineering Standards","Industrial Data Model & Digital Thread",
    ],
}

TIER_ORDER = ["Starter","Mid-Tier Pro","Professional","Enterprise","Enterprise Plus","Research Pack"]

def normalize_tier(value: str) -> str:
    v=str(value or "Starter").lower()
    if "research" in v: return "Research Pack"
    if "enterprise plus" in v or "industrial enterprise" in v: return "Enterprise Plus"
    if "enterprise" in v: return "Enterprise"
    if "professional" in v: return "Professional"
    if "pro" in v: return "Mid-Tier Pro"
    return "Starter"

def tier_allows(current: str, required: str) -> bool:
    c=normalize_tier(current); r=normalize_tier(required)
    if c=="Research Pack": c="Enterprise Plus"
    if r=="Research Pack": r="Enterprise Plus"
    return TIER_ORDER.index(c) >= TIER_ORDER.index(r)

def init_platform_db(db_path: str="enterprise_full_workspace.db") -> bool:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        ddl = [
            ("industrial_entities","CREATE TABLE IF NOT EXISTS industrial_entities(entity_id TEXT PRIMARY KEY, entity_type TEXT, name TEXT, attributes_json TEXT, updated_at TEXT)"),
            ("platform_datasets","CREATE TABLE IF NOT EXISTS platform_datasets(dataset_id TEXT PRIMARY KEY, name TEXT, source_name TEXT, row_count INTEGER, column_count INTEGER, sha256 TEXT, created_at TEXT, schema_json TEXT)"),
            ("platform_models","CREATE TABLE IF NOT EXISTS platform_models(model_id TEXT PRIMARY KEY, name TEXT, version TEXT, model_type TEXT, parameters_json TEXT, data_hash TEXT, assumptions_json TEXT, created_by TEXT, created_at TEXT, status TEXT)"),
            ("platform_experiments","CREATE TABLE IF NOT EXISTS platform_experiments(experiment_id TEXT PRIMARY KEY, name TEXT, module TEXT, scenarios_json TEXT, results_json TEXT, created_by TEXT, created_at TEXT)"),
            ("platform_benchmarks","CREATE TABLE IF NOT EXISTS platform_benchmarks(id INTEGER PRIMARY KEY AUTOINCREMENT, metric TEXT, value REAL, unit TEXT, source TEXT, source_date TEXT, created_at TEXT)"),
            ("platform_decisions","CREATE TABLE IF NOT EXISTS platform_decisions(decision_id TEXT PRIMARY KEY, title TEXT, module TEXT, metrics_json TEXT, assumptions_json TEXT, uncertainty_json TEXT, created_by TEXT, created_at TEXT, status TEXT)"),
            ("mes_work_orders","CREATE TABLE IF NOT EXISTS mes_work_orders(work_order TEXT PRIMARY KEY, product TEXT, quantity REAL, due_date TEXT, status TEXT, machine TEXT, operator TEXT, updated_at TEXT)"),
            ("mes_events","CREATE TABLE IF NOT EXISTS mes_events(id INTEGER PRIMARY KEY AUTOINCREMENT, work_order TEXT, event_type TEXT, event_time TEXT, quantity REAL, reason TEXT, operator TEXT)"),
            ("quality_runs","CREATE TABLE IF NOT EXISTS quality_runs(id INTEGER PRIMARY KEY AUTOINCREMENT, study_name TEXT, metric TEXT, result_json TEXT, created_by TEXT, created_at TEXT)"),
            ("connector_profiles","CREATE TABLE IF NOT EXISTS connector_profiles(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, system_type TEXT, endpoint TEXT, status TEXT, last_test TEXT, notes TEXT, created_by TEXT)"),
            ("telemetry_events","CREATE TABLE IF NOT EXISTS telemetry_events(id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT, ts TEXT, metric TEXT, value REAL, source TEXT)"),
            ("security_events","CREATE TABLE IF NOT EXISTS security_events(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, event_type TEXT, details TEXT, created_at TEXT)"),
            ("platform_scenarios","CREATE TABLE IF NOT EXISTS platform_scenarios(scenario_id TEXT PRIMARY KEY, name TEXT UNIQUE, parent_name TEXT, parameters_json TEXT, kpis_json TEXT, created_by TEXT, created_at TEXT)"),
            ("workspace_members","CREATE TABLE IF NOT EXISTS workspace_members(workspace TEXT, username TEXT, role TEXT, updated_at TEXT, PRIMARY KEY(workspace,username))"),
            ("fx_rates","CREATE TABLE IF NOT EXISTS fx_rates(currency TEXT PRIMARY KEY, rate_to_base REAL, updated_at TEXT)"),
            ("trade_rules","CREATE TABLE IF NOT EXISTS trade_rules(id INTEGER PRIMARY KEY AUTOINCREMENT, region_from TEXT, region_to TEXT, product_class TEXT, rule TEXT, active INTEGER, updated_at TEXT)"),
        ]
        for _,sql in ddl: conn.execute(sql)
        conn.commit()
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok": raise RuntimeError("SQLite quick_check failed")
    return True

def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")

def log_security_event(username: str, event_type: str, details: str="", db_path: str="enterprise_full_workspace.db"):
    try:
        with sqlite3.connect(db_path) as c:
            c.execute("INSERT INTO security_events(username,event_type,details,created_at) VALUES(?,?,?,?)",(username,event_type,details,_now()))
            c.commit()
    except Exception:
        pass

def register_dataset(name: str, source_name: str, df: pd.DataFrame, db_path: str="enterprise_full_workspace.db") -> str:
    raw=df.to_csv(index=False).encode()
    dataset_id="DS-"+hashlib.sha256((name+source_name+str(len(raw))).encode()).hexdigest()[:12].upper()
    schema={str(c):str(df[c].dtype) for c in df.columns}
    with sqlite3.connect(db_path) as c:
        c.execute("INSERT OR REPLACE INTO platform_datasets VALUES(?,?,?,?,?,?,?,?)",(dataset_id,name,source_name,len(df),len(df.columns),hashlib.sha256(raw).hexdigest(),_now(),json.dumps(schema)))
        c.commit()
    return dataset_id

def data_quality_report(df: pd.DataFrame) -> dict:
    if df is None: return {"score":0.0,"rows":0,"columns":0,"missing_pct":100.0,"duplicate_pct":100.0,"issues":["No data"]}
    rows=max(1,len(df)); missing=float(df.isna().mean().mean()*100) if df.shape[1] else 100.0
    duplicate=float(df.duplicated().mean()*100) if len(df) else 0.0
    issues=[]
    if missing>10: issues.append(f"Missing values: {missing:.1f}%")
    if duplicate>5: issues.append(f"Duplicate rows: {duplicate:.1f}%")
    for col in df.select_dtypes(include=np.number).columns:
        s=pd.to_numeric(df[col],errors="coerce").dropna()
        if len(s)>=8:
            q1,q3=s.quantile(.25),s.quantile(.75); iqr=q3-q1
            if iqr>0 and ((s<q1-1.5*iqr)|(s>q3+1.5*iqr)).mean()>0.1: issues.append(f"Potential outliers: {col}")
    score=max(0.0,min(100.0,100-missing*0.7-duplicate*0.5-min(30,len(issues)*5)))
    return {"score":round(score,1),"rows":len(df),"columns":len(df.columns),"missing_pct":round(missing,2),"duplicate_pct":round(duplicate,2),"issues":issues}

def validate_table(df: pd.DataFrame, required: Optional[Sequence[str]]=None, numeric_ranges: Optional[dict]=None) -> dict:
    errors=[]; warnings=[]
    required=list(required or [])
    for c in required:
        if c not in df.columns: errors.append(f"Missing required column: {c}")
    if len(df)==0: errors.append("Table is empty")
    if df.columns.duplicated().any(): errors.append("Duplicate column names")
    if numeric_ranges:
        for c,(lo,hi) in numeric_ranges.items():
            if c in df.columns:
                s=pd.to_numeric(df[c],errors="coerce")
                bad=int(((s<lo)|(s>hi)).fillna(False).sum())
                if bad: errors.append(f"{bad} values outside {c} range [{lo}, {hi}]")
    q=data_quality_report(df); warnings.extend(q["issues"])
    feasible=len(errors)==0
    return {"valid":feasible,"quality":q,"errors":errors,"warnings":warnings}

def model_health(df: pd.DataFrame, feasible: bool=True, solver_status: str="Not Run", stability: str="Not assessed", uncertainty: str="Not assessed", reproducible: bool=True) -> dict:
    q=data_quality_report(df)
    return {"data_quality":q["score"],"feasibility":"Pass" if feasible else "Fail","solver_status":solver_status,"model_stability":stability,"forecast_uncertainty":uncertainty,"reproducible":"Yes" if reproducible else "No","issues":q["issues"]}

def upsert_entities(df: pd.DataFrame, entity_type: str, id_col: str, db_path: str="enterprise_full_workspace.db") -> int:
    if id_col not in df.columns: raise KeyError(f"{id_col} not found")
    count=0
    with sqlite3.connect(db_path) as c:
        for rec in df.to_dict("records"):
            eid=f"{entity_type}:{rec[id_col]}"
            name=str(rec.get("name",rec.get("Customer",rec.get("Product",rec[id_col]))))
            attrs={k:v for k,v in rec.items() if k!=id_col}
            c.execute("INSERT OR REPLACE INTO industrial_entities VALUES(?,?,?, ?, ?)",(eid,entity_type,name,json.dumps(attrs,default=str),_now()))
            count+=1
        c.commit()
    return count

def finite_schedule(orders: pd.DataFrame, machine_capacity: Optional[dict]=None, start_time: Optional[datetime]=None) -> pd.DataFrame:
    req={"Order","Product","Qty","DueDate","ProcessingMin"}
    missing=req-set(orders.columns)
    if missing: raise ValueError(f"Missing scheduling columns: {sorted(missing)}")
    d=orders.copy()
    d["DueDate"]=pd.to_datetime(d["DueDate"],errors="coerce")
    d["Qty"]=pd.to_numeric(d["Qty"],errors="coerce").fillna(0)
    d["ProcessingMin"]=pd.to_numeric(d["ProcessingMin"],errors="coerce").fillna(0)
    d["SetupMin"]=pd.to_numeric(d.get("SetupMin",0),errors="coerce").fillna(0)
    d["Machine"]=d.get("Machine","M-01").astype(str)
    d["Priority"]=pd.to_numeric(d.get("Priority",0),errors="coerce").fillna(0)
    d=d.sort_values(["Priority","DueDate"],ascending=[False,True]).reset_index(drop=True)
    avail={m:(start_time or datetime.now()) for m in d["Machine"].unique()}
    rows=[]
    for r in d.itertuples(index=False):
        m=str(r.Machine); ready=avail[m]; duration=max(0.1,float(r.ProcessingMin)+float(r.SetupMin))
        finish=ready+timedelta(minutes=duration)
        due=r.DueDate.to_pydatetime() if pd.notna(r.DueDate) else finish
        rows.append({"Order":r.Order,"Product":r.Product,"Qty":r.Qty,"Machine":m,"Start":ready,"Finish":finish,"DueDate":due,"LateMin":max(0,(finish-due).total_seconds()/60)})
        avail[m]=finish
    return pd.DataFrame(rows)

def mrp_explode(demand: pd.DataFrame, bom: pd.DataFrame, lead_times: Optional[pd.DataFrame]=None) -> pd.DataFrame:
    if not {"Product","DemandQty"}<=set(demand.columns) or not {"Parent","Component","QtyPer"}<=set(bom.columns): raise ValueError("Demand needs Product/DemandQty and BOM needs Parent/Component/QtyPer")
    dt=demand.copy(); b=bom.copy()
    dt["DemandQty"]=pd.to_numeric(dt["DemandQty"],errors="coerce").fillna(0); b["QtyPer"]=pd.to_numeric(b["QtyPer"],errors="coerce").fillna(0)
    out=[]
    for r in dt.itertuples(index=False):
        for q in b[b["Parent"].astype(str)==str(r.Product)].itertuples(index=False):
            out.append({"Parent":r.Product,"Component":q.Component,"Gross Requirement":float(r.DemandQty)*float(q.QtyPer)})
    res=pd.DataFrame(out)
    if lead_times is not None and not res.empty and {"Component","LeadTimeDays"}<=set(lead_times.columns):
        res=res.merge(lead_times,on="Component",how="left")
    return res

def calculate_oee(availability: float, performance: float, quality: float) -> dict:
    a=max(0,min(100,float(availability))); p=max(0,min(100,float(performance))); q=max(0,min(100,float(quality)))
    oee=a*p*q/10000
    return {"Availability %":a,"Performance %":p,"Quality %":q,"OEE %":oee}

def oee_from_events(events: pd.DataFrame) -> dict:
    req={"PlannedMin","DowntimeMin","IdealCycleSec","TotalCount","GoodCount"}
    if not req<=set(events.columns): raise ValueError(f"OEE events require {sorted(req)}")
    r=events.sum(numeric_only=True)
    planned=max(1,float(r.PlannedMin)); run=max(0,planned-float(r.DowntimeMin))
    avail=run/planned*100; perf=((float(r.TotalCount)*float(r.IdealCycleSec))/60)/max(run,1)*100; qual=float(r.GoodCount)/max(float(r.TotalCount),1)*100
    return calculate_oee(avail,perf,qual)

def spc_limits(values: Sequence[float], sigma: float=3.0) -> dict:
    x=pd.to_numeric(pd.Series(values),errors="coerce").dropna().astype(float)
    if len(x)<2: raise ValueError("At least two observations are required.")
    mean=float(x.mean()); sd=float(x.std(ddof=1))
    return {"mean":mean,"ucl":mean+sigma*sd,"lcl":mean-sigma*sd,"sigma":sd}

def capability(values: Sequence[float], lsl: float, usl: float) -> dict:
    x=pd.to_numeric(pd.Series(values),errors="coerce").dropna().astype(float)
    if len(x)<2 or usl<=lsl: raise ValueError("Need at least two values and USL > LSL.")
    sd=float(x.std(ddof=1)); mean=float(x.mean())
    cp=(usl-lsl)/(6*sd) if sd else math.inf; cpu=(usl-mean)/(3*sd) if sd else math.inf; cpl=(mean-lsl)/(3*sd) if sd else math.inf
    return {"mean":mean,"std":sd,"Cp":cp,"Cpk":min(cpu,cpl)}

def pareto_counts(values: Sequence[Any]) -> pd.DataFrame:
    s=pd.Series(values).astype(str); out=s.value_counts().rename_axis("Category").reset_index(name="Count"); out["Cumulative %"]=out["Count"].cumsum()/max(1,out["Count"].sum())*100; return out

def gage_rr(measurements: pd.DataFrame, part_col="Part", operator_col="Operator", value_col="Measurement") -> dict:
    req={part_col,operator_col,value_col}
    if not req<=set(measurements.columns): raise ValueError(f"Gage R&R requires {sorted(req)}")
    d=measurements.copy(); d[value_col]=pd.to_numeric(d[value_col],errors="coerce"); d=d.dropna(subset=[value_col])
    grand=d[value_col].mean(); part_means=d.groupby(part_col)[value_col].mean(); op_means=d.groupby(operator_col)[value_col].mean()
    repeat_var=float(d.groupby([part_col,operator_col])[value_col].var(ddof=1).fillna(0).mean()); part_var=float(part_means.var(ddof=1)) if len(part_means)>1 else 0.0; op_var=float(op_means.var(ddof=1)) if len(op_means)>1 else 0.0
    total_var=max(1e-12,repeat_var+part_var+op_var); return {"Repeatability SD":math.sqrt(repeat_var),"Part-to-Part SD":math.sqrt(max(part_var,0)),"Operator SD":math.sqrt(max(op_var,0)),"%GRR":repeat_var/total_var*100,"%Part":part_var/total_var*100,"Mean":float(grand)}

def one_way_anova(df: pd.DataFrame, group_col: str, value_col: str) -> dict:
    groups=[g[value_col].dropna().values for _,g in df.groupby(group_col)]
    if len(groups)<2: raise ValueError("Need at least two groups.")
    stat,p=stats.f_oneway(*groups); return {"F":float(stat),"p_value":float(p),"groups":len(groups)}

def regression_fit(df: pd.DataFrame, target: str, features: Sequence[str]) -> tuple[pd.DataFrame,dict]:
    d=df.dropna(subset=[target]+list(features)).copy()
    X=d[list(features)].apply(pd.to_numeric,errors="coerce"); y=pd.to_numeric(d[target],errors="coerce")
    mask=X.notna().all(axis=1)&y.notna(); X=X.loc[mask]; y=y.loc[mask]
    if len(X)<3: raise ValueError("Need at least three complete observations.")
    model=LinearRegression().fit(X,y); pred=model.predict(X); metrics={"R2":float(r2_score(y,pred)),"MAE":float(mean_absolute_error(y,pred)),"RMSE":float(math.sqrt(mean_squared_error(y,pred)))}
    coef=pd.DataFrame({"Feature":list(features),"Coefficient":model.coef_}); metrics["Intercept"]=float(model.intercept_); return coef,metrics

def fmea_score(df: pd.DataFrame, severity="Severity", occurrence="Occurrence", detection="Detection") -> pd.DataFrame:
    d=df.copy()
    for c in [severity,occurrence,detection]:
        d[c]=pd.to_numeric(d[c],errors="coerce")
    d["RPN"]=d[severity]*d[occurrence]*d[detection]
    return d.sort_values("RPN",ascending=False)

def weibull_analysis(failures: Sequence[float]) -> dict:
    x=pd.to_numeric(pd.Series(failures),errors="coerce").dropna().values
    if len(x)<3 or np.any(x<=0): raise ValueError("Need at least three positive failure times.")
    shape,loc,scale=stats.weibull_min.fit(x,floc=0)
    return {"Shape (Beta)":float(shape),"Scale (Eta)":float(scale),"B10 Life":float(scale*(-math.log(0.9))**(1/shape))}

def full_factorial_2level(factors: Sequence[str]) -> pd.DataFrame:
    rows=[]
    for vals in product([-1,1], repeat=len(factors)):
        rows.append(dict(zip(factors,vals)))
    return pd.DataFrame(rows)

def queue_simulation(arrival_rate: float, service_rate: float, servers: int=1, duration_min: float=1440, replications: int=10, seed: int=42) -> pd.DataFrame:
    if min(arrival_rate,service_rate,servers,duration_min,replications)<=0: raise ValueError("Rates, servers, duration and replications must be positive.")
    rows=[]; rng=np.random.default_rng(seed)
    for rep in range(replications):
        t=0.; arrivals=[]; n=int(max(1,duration_min*arrival_rate/60*1.25))
        for _ in range(n):
            t += rng.exponential(60/arrival_rate); 
            if t<=duration_min: arrivals.append(t)
        servers_heap=[0.0]*servers; heapq.heapify(servers_heap); waits=[]
        for a in arrivals:
            available=heapq.heappop(servers_heap); start=max(a,available); waits.append(start-a)
            finish=start+rng.exponential(60/service_rate); heapq.heappush(servers_heap,finish)
        rows.append({"Replication":rep+1,"Arrivals":len(arrivals),"Mean Wait Min":float(np.mean(waits) if waits else 0),"P95 Wait Min":float(np.percentile(waits,95) if waits else 0),"Utilization":float(min(1.0, len(arrivals)/(max(1,servers)*max(1,duration_min*service_rate/60))))})
    return pd.DataFrame(rows)

def agent_simulation(agents: int=20, steps: int=100, step_size: float=1.0, seed: int=42) -> pd.DataFrame:
    rng=np.random.default_rng(seed); pos=rng.uniform(-10,10,size=(agents,2)); rows=[]
    for step in range(steps):
        direction=rng.normal(size=(agents,2)); norm=np.linalg.norm(direction,axis=1,keepdims=True); direction=direction/np.maximum(norm,1e-9); pos+=direction*step_size
        rows.append({"Step":step,"Mean Distance":float(np.linalg.norm(pos,axis=1).mean()),"Max Distance":float(np.linalg.norm(pos,axis=1).max())})
    return pd.DataFrame(rows)

def system_dynamics_inventory(initial_inventory: float, demand_per_day: float, replenishment_per_day: float, feedback: float=0.15, days: int=90) -> pd.DataFrame:
    inv=float(initial_inventory); rows=[]
    for day in range(1,days+1):
        demand=max(0,demand_per_day*(1+feedback*(1000/(1000+max(inv,0))-0.5)))
        inv=max(0,inv+replenishment_per_day-demand)
        rows.append({"Day":day,"Inventory":inv,"Demand":demand,"Replenishment":replenishment_per_day})
    return pd.DataFrame(rows)

def pareto_frontier(df: pd.DataFrame, objectives: Sequence[str], minimize: Optional[Sequence[bool]]=None) -> pd.DataFrame:
    if not objectives: return df.copy()
    d=df.copy(); mins=list(minimize or [True]*len(objectives))
    mask=np.ones(len(d),dtype=bool)
    arr=d[list(objectives)].apply(pd.to_numeric,errors="coerce").to_numpy()
    for i in range(len(arr)):
        for j in range(len(arr)):
            if i==j: continue
            better_or_equal=True; strictly=False
            for k in range(len(objectives)):
                if mins[k]:
                    if arr[j,k] > arr[i,k]: better_or_equal=False; break
                    if arr[j,k] < arr[i,k]: strictly=True
                else:
                    if arr[j,k] < arr[i,k]: better_or_equal=False; break
                    if arr[j,k] > arr[i,k]: strictly=True
            if better_or_equal and strictly: mask[i]=False; break
    return d.loc[mask].reset_index(drop=True)

def robust_risk_analysis(demand_mean: float, demand_std: float, capacity: float, lead_time_mean: float, lead_time_std: float, disruption_probability: float=0.0, disruption_capacity_multiplier: float=0.6, simulations: int=5000, seed: int=42) -> dict:
    rng=np.random.default_rng(seed); demand=np.maximum(0,rng.normal(demand_mean,max(demand_std,1e-9),simulations)); lead=np.maximum(0,rng.normal(lead_time_mean,max(lead_time_std,1e-9),simulations)); shock=rng.random(simulations)<max(0,min(1,disruption_probability)); effective=np.maximum(0,capacity*np.where(shock,disruption_capacity_multiplier,1.0)); service=(demand<=effective).astype(float); exposure=np.maximum(0,demand-effective)*(1+np.maximum(0,lead-lead_time_mean)/max(lead_time_mean,1e-9))
    return {"Service Probability":float(service.mean()),"Stockout Probability":float(1-service.mean()),"P50 Exposure":float(np.percentile(exposure,50)),"P90 Exposure":float(np.percentile(exposure,90)),"P95 Exposure":float(np.percentile(exposure,95)),"P99 Exposure":float(np.percentile(exposure,99))}

def multiobjective_score(df: pd.DataFrame, weights: dict, minimize: Optional[dict]=None) -> pd.DataFrame:
    d=df.copy(); minimize=minimize or {k:True for k in weights}; score=np.zeros(len(d))
    for col,w in weights.items():
        x=pd.to_numeric(d[col],errors="coerce").astype(float); lo,hi=x.min(),x.max(); norm=(x-lo)/(hi-lo) if hi>lo else pd.Series(np.zeros(len(d)),index=d.index)
        score += float(w)*(norm if minimize.get(col,True) else 1-norm)
    d["Composite Score"]=score
    return d.sort_values("Composite Score").reset_index(drop=True)

def capital_metrics(initial_investment: float, cash_flows: Sequence[float], discount_rate: float=0.1, salvage_value: float=0.0) -> dict:
    flows=np.array([-abs(initial_investment)]+[float(x) for x in cash_flows],dtype=float); flows[-1]+=float(salvage_value)
    npv=float(sum(flows[t]/((1+discount_rate)**t) for t in range(len(flows))))
    def npv_at(r): return float(sum(flows[t]/((1+r)**t) for t in range(len(flows))))
    lo,hi=-0.99,10.0
    low_val, high_val = npv_at(lo), npv_at(hi)
    if low_val * high_val > 0:
        irr = None
    else:
        mid = 0.1
        for _ in range(200):
            mid=(lo+hi)/2; val=npv_at(mid)
            if abs(val)<1e-8: break
            if npv_at(lo)*val<=0: hi=mid
            else: lo=mid
        irr=float(mid)
    cumulative=-abs(initial_investment); payback=None
    for i,cf in enumerate(flows[1:],1):
        prev=cumulative; cumulative+=cf
        if cumulative>=0 and cf!=0:
            payback=(i-1)+(-prev)/cf; break
    return {"NPV":npv,"IRR":irr,"Payback Period":payback}

def line_balance(elements: pd.DataFrame, takt_min: float, element_col="Element", time_col="TimeMin") -> Tuple[pd.DataFrame,dict]:
    if takt_min<=0: raise ValueError("Takt must be positive.")
    d=elements.copy(); d[time_col]=pd.to_numeric(d[time_col],errors="coerce").fillna(0); d=d.sort_values(time_col,ascending=False)
    stations=[]; loads=[]
    for r in d.itertuples(index=False):
        idx=next((i for i,l in enumerate(loads) if l+float(getattr(r,time_col))<=takt_min),None)
        if idx is None: loads.append(0.0); stations.append([]); idx=len(loads)-1
        stations[idx].append({"Element":getattr(r,element_col),"TimeMin":float(getattr(r,time_col))}); loads[idx]+=float(getattr(r,time_col))
    out=[]; 
    for i,(items,load) in enumerate(zip(stations,loads),1):
        out.append({"Station":f"S{i}","Load Min":load,"Utilization %":load/takt_min*100,"Elements":", ".join(x["Element"] for x in items)})
    return pd.DataFrame(out),{"Stations":len(out),"Balance Efficiency %":sum(loads)/(len(loads)*takt_min)*100,"Idle Min":sum(len(loads)*[takt_min][0]-sum(loads) for _ in [0])}

def staffing_capacity(staff: int, minutes_per_shift: float, productive_pct: float, days: int=1) -> dict:
    productive=max(0,min(100,float(productive_pct))); capacity=max(0,int(staff))*minutes_per_shift*(productive/100)*days
    return {"Staff":int(staff),"Available Min":staff*minutes_per_shift*days,"Productive Min":capacity,"Productive %":productive}

def sustainability_accounting(df: pd.DataFrame) -> pd.DataFrame:
    cols=set(df.columns); required={"Activity","Scope","Quantity","EmissionFactor"}
    if not required<=cols: raise ValueError(f"Sustainability data requires {sorted(required)}")
    d=df.copy(); d["Quantity"]=pd.to_numeric(d["Quantity"],errors="coerce").fillna(0); d["EmissionFactor"]=pd.to_numeric(d["EmissionFactor"],errors="coerce").fillna(0); d["tCO2e"]=d["Quantity"]*d["EmissionFactor"]/1000
    if "Energy_kWh" in d.columns: d["Energy_kWh"]=pd.to_numeric(d["Energy_kWh"],errors="coerce").fillna(0)
    if "Water_m3" in d.columns: d["Water_m3"]=pd.to_numeric(d["Water_m3"],errors="coerce").fillna(0)
    if "Waste_kg" in d.columns: d["Waste_kg"]=pd.to_numeric(d["Waste_kg"],errors="coerce").fillna(0)
    return d

def lca_summary(df: pd.DataFrame) -> pd.DataFrame:
    d=sustainability_accounting(df); group=[c for c in ["LifeCycleStage","Scope"] if c in d.columns] or ["Scope"]; return d.groupby(group,as_index=False)["tCO2e"].sum()

def benchmark_compare(actual: pd.DataFrame, benchmarks: pd.DataFrame, metric_col="Metric", actual_col="Actual", benchmark_col="Benchmark") -> pd.DataFrame:
    x=actual.merge(benchmarks,on=metric_col,how="left",suffixes=("","_bench")); x["Delta"]=pd.to_numeric(x[actual_col],errors="coerce")-pd.to_numeric(x[benchmark_col],errors="coerce"); x["Gap %"]=x["Delta"]/pd.to_numeric(x[benchmark_col],errors="coerce").replace(0,np.nan)*100; return x

def create_decision_card(title: str, module: str, metrics: dict, assumptions: dict, uncertainty: dict, status="Proposed") -> dict:
    return {"title":title,"module":module,"metrics":metrics,"assumptions":assumptions,"uncertainty":uncertainty,"status":status,"created_at":_now()}

def save_decision_card(card: dict, username: str, db_path="enterprise_full_workspace.db") -> str:
    did="DEC-"+hashlib.sha256(json.dumps(card,sort_keys=True,default=str).encode()).hexdigest()[:12].upper()
    with sqlite3.connect(db_path) as c:
        c.execute("INSERT OR REPLACE INTO platform_decisions VALUES(?,?,?,?,?,?,?,?,?)",(did,card["title"],card["module"],json.dumps(card["metrics"],default=str),json.dumps(card["assumptions"],default=str),json.dumps(card["uncertainty"],default=str),username,card["created_at"],card["status"])); c.commit()
    return did

def save_model_snapshot(name: str, model_type: str, parameters: dict, data_hash: str, username: str, assumptions: dict, status="Draft", db_path="enterprise_full_workspace.db") -> str:
    base=f"{name}|{json.dumps(parameters,sort_keys=True,default=str)}|{data_hash}"
    mid="MOD-"+hashlib.sha256(base.encode()).hexdigest()[:12].upper()
    with sqlite3.connect(db_path) as c:
        c.execute("INSERT OR REPLACE INTO platform_models VALUES(?,?,?,?,?,?,?,?,?,?)",(mid,name,"1.0.0",model_type,json.dumps(parameters,default=str),data_hash,json.dumps(assumptions,default=str),username,_now(),status)); c.commit()
    return mid

def save_experiment(name: str, module: str, scenarios: list, results: dict, username: str, db_path="enterprise_full_workspace.db") -> str:
    eid="EXP-"+hashlib.sha256((name+module+_now()).encode()).hexdigest()[:12].upper()
    with sqlite3.connect(db_path) as c:
        c.execute("INSERT INTO platform_experiments VALUES(?,?,?,?,?,?)",(eid,name,module,json.dumps(scenarios,default=str),json.dumps(results,default=str),username,_now())); c.commit()
    return eid

def export_pdf(title: str, tables: Sequence[Tuple[str,pd.DataFrame]], figures: Sequence[Tuple[str,Any]]=()) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    out=io.BytesIO(); doc=SimpleDocTemplate(out,pagesize=landscape(A4)); styles=getSampleStyleSheet(); story=[Paragraph(title,styles["Title"]),Spacer(1,8)]
    for label,df in tables:
        safe=df.head(30).fillna("").astype(str); story.append(Paragraph(str(label),styles["Heading2"]))
        if len(safe.columns):
            t=Table([list(safe.columns)]+safe.values.tolist(),repeatRows=1); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1E3A8A")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.25,colors.grey),("FONTSIZE",(0,0),(-1,-1),7)])); story += [t,Spacer(1,8)]
    for label,fig in figures:
        try:
            png=fig.to_image(format="png",width=1200,height=650,scale=2)
            story += [Paragraph(str(label),styles["Heading2"]),Image(io.BytesIO(png),width=10.5*inch,height=5.7*inch)]
        except Exception:
            story += [Paragraph(f"{label} (interactive chart is included in the HTML/Excel export where supported)",styles["Normal"])]
    doc.build(story); return out.getvalue()

def export_pptx(title: str, tables: Sequence[Tuple[str,pd.DataFrame]], figures: Sequence[Tuple[str,Any]]=()) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches
    prs=Presentation(); cover=prs.slides.add_slide(prs.slide_layouts[0]); cover.shapes.title.text=title; cover.placeholders[1].text="Shoir-IE Industrial Decision Platform"
    for label,fig in figures:
        try:
            png=fig.to_image(format="png",width=1600,height=900,scale=2); s=prs.slides.add_slide(prs.slide_layouts[5]); s.shapes.title.text=str(label); s.shapes.add_picture(io.BytesIO(png),Inches(.4),Inches(1.1),width=Inches(12.5))
        except Exception: pass
    for label,df in tables:
        d=df.head(15).fillna("").astype(str); s=prs.slides.add_slide(prs.slide_layouts[5]); s.shapes.title.text=str(label)
        rows=max(1,len(d)+1); cols=max(1,len(d.columns)); table=s.shapes.add_table(rows,cols,Inches(.25),Inches(1.1),Inches(12.8),Inches(5.6)).table
        for j,col in enumerate(d.columns): table.cell(0,j).text=str(col)
        for i,row in enumerate(d.itertuples(index=False),1):
            for j,val in enumerate(row): table.cell(i,j).text=str(val)
    b=io.BytesIO(); prs.save(b); return b.getvalue()

def render_export_bar(module: str, tables: Sequence[Tuple[str,pd.DataFrame]], figures: Sequence[Tuple[str,Any]]=(), tier: str="Starter", username: str="unknown"):
    import streamlit as st
    from shoir_upgrade import build_excel_report
    if not tables: return
    st.markdown("---"); st.subheader("📤 Results & Executive Exports")
    x=build_excel_report("Shoir-IE | "+module,tables,figures)
    a,b,c=st.columns(3)
    with a:
        if st.download_button("📊 Download Excel",x,"shoir_ie_"+re.sub(r"[^A-Za-z0-9]+","_",module).lower()+".xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True):
            log_security_event(username,"report_export",module+"|xlsx")
    with b:
        if tier_allows(tier,"Enterprise"):
            y=export_pdf("Shoir-IE | "+module,tables,figures)
            if st.download_button("📄 Download PDF",y,"shoir_ie_"+re.sub(r"[^A-Za-z0-9]+","_",module).lower()+".pdf","application/pdf",use_container_width=True): log_security_event(username,"report_export",module+"|pdf")
        else: st.info("PDF export: Enterprise")
    with c:
        if tier_allows(tier,"Enterprise"):
            z=export_pptx("Shoir-IE | "+module,tables,figures)
            if st.download_button("📽️ Download PowerPoint",z,"shoir_ie_"+re.sub(r"[^A-Za-z0-9]+","_",module).lower()+".pptx","application/vnd.openxmlformats-officedocument.presentationml.presentation",use_container_width=True): log_security_event(username,"report_export",module+"|pptx")
        else: st.info("PowerPoint: Enterprise")

MODULE_TABLE_KEYS = {
    "Engineering Validation Center":["validation_df"],
    "Industrial Data Model & Digital Thread":["thread_df","thread_rel"],
    "Advanced Planning & Scheduling":["aps_demand","aps_bom","aps_orders"],
    "Manufacturing Execution System":["mes_wo_df","mes_events_df","mes_oee_df"],
    "Quality Engineering & Reliability":["quality_df","msa_df","anova_df","fmea_df"],
    "Industrial Simulation Lab":[],
    "3D Factory Designer":["factory3d_df"],
    "Industrial Connectivity Hub":["conn_df"],
    "Multi-Objective Optimization":["multiobj_df"],
    "Robust & Resilient Optimization":["robust_df"],
    "Engineering Model Registry":["model_registry_df"],
    "Experiment Lab":["experiment_df"],
    "Industrial Data Platform":[],
    "Capital Investment & Engineering Economics":["capex_df"],
    "Workforce Engineering":["work_elements","skills_df"],
    "Industrial Sustainability & LCA":["sustain_df"],
    "Benchmarking & Engineering Standards":["benchmark_actual","benchmark_targets"],
    "Live Industrial Digital Twin":["twin_tel"],
    "Enterprise Security & Governance":["security_roles"],
}

def _module_slug(module: str) -> str:
    return re.sub(r"[^a-z0-9]+","_",module.lower()).strip("_")

def module_reset(module: str, st) -> None:
    for key in MODULE_TABLE_KEYS.get(module, []):
        st.session_state.pop(key, None)
        st.session_state.pop(key.replace("_df","_editor"), None)
    slug=_module_slug(module)
    for key in list(st.session_state.keys()):
        if str(key).startswith(f"{slug}_"):
            st.session_state.pop(key,None)

def render_module_data_exchange(module: str, st, tier: str, username: str) -> None:
    slug=_module_slug(module)
    has_module_tables=any(key in st.session_state for key in MODULE_TABLE_KEYS.get(module,[]))
    if not has_module_tables:
        st.markdown("### 📥 First-load Data Import")
        st.caption("Upload an Excel/CSV file and Shoir-IE will map matching column names into this module's table.")
        up=st.file_uploader("Import Excel / CSV",type=["xlsx","csv"],key=f"{slug}_first_upload")
        if up is not None:
            try:
                from shoir_upgrade import read_uploaded_workbook
                books=read_uploaded_workbook(up.getvalue(),up.name)
                sheet=st.selectbox("Sheet",list(books),key=f"{slug}_import_sheet")
                st.session_state[f"{slug}_import_df"]=books[sheet].copy(deep=True)
                st.success(f"Loaded {len(books[sheet]):,} rows × {len(books[sheet].columns):,} columns.")
            except Exception as exc:
                st.error(f"Import failed safely: {exc}")
    imported=st.session_state.get(f"{slug}_import_df")
    if isinstance(imported,pd.DataFrame) and has_module_tables:
        if st.button("🔄 Apply imported table",use_container_width=True,key=f"{slug}_apply_import"):
            applied=0
            for key in MODULE_TABLE_KEYS.get(module,[]):
                target=st.session_state.get(key)
                if isinstance(target,pd.DataFrame) and len(set(imported.columns)&set(target.columns)):
                    st.session_state[key]=align_imported_table(imported,target)
                    st.session_state.pop(key.replace("_df","_editor"),None)
                    applied+=1
            if applied:
                st.success(f"Imported data applied to {applied} compatible table(s).")
                st.rerun()
            else:
                st.warning("No compatible table was found. Review the expected columns.")
    st.markdown("### ⚙️ Module Workspace")
    if st.button("↩️ Reset Entire Module Workspace",use_container_width=True,key=f"{slug}_reset"):
        module_reset(module,st)
        st.rerun()

def ml_demand_forecast(df: pd.DataFrame, date_col: str, target_col: str, external_cols: Sequence[str]=(), horizon: int=12) -> tuple[pd.DataFrame,dict]:
    if date_col not in df.columns or target_col not in df.columns: raise ValueError("Forecast requires date and target columns.")
    d=df.copy(); d[date_col]=pd.to_datetime(d[date_col],errors="coerce"); d[target_col]=pd.to_numeric(d[target_col],errors="coerce")
    d=d.dropna(subset=[date_col,target_col]).sort_values(date_col).reset_index(drop=True)
    if len(d)<8: raise ValueError("At least 8 historical observations are required.")
    x=pd.DataFrame(index=d.index); x["trend"]=np.arange(len(d)); x["sin_month"]=np.sin(2*np.pi*d[date_col].dt.month/12); x["cos_month"]=np.cos(2*np.pi*d[date_col].dt.month/12)
    used=[]
    for col in external_cols:
        if col in d.columns:
            vals=pd.to_numeric(d[col],errors="coerce")
            if vals.notna().sum()>=max(5,len(d)//2):
                x[col]=vals.fillna(vals.median()); used.append(col)
    model=LinearRegression().fit(x,d[target_col]); pred=model.predict(x); residual=d[target_col]-pred
    freq=pd.infer_freq(d[date_col]) or "D"; future_dates=pd.date_range(d[date_col].iloc[-1],periods=horizon+1,freq=freq)[1:]
    fx=pd.DataFrame(index=range(horizon)); fx["trend"]=np.arange(len(d),len(d)+horizon); fx["sin_month"]=np.sin(2*np.pi*future_dates.month/12); fx["cos_month"]=np.cos(2*np.pi*future_dates.month/12)
    for col in used: fx[col]=float(x[col].iloc[-1])
    forecast=np.maximum(0,model.predict(fx)); sigma=float(np.std(residual,ddof=max(1,min(1,len(residual)-1))))
    out=pd.DataFrame({"Date":future_dates,"Forecast":forecast,"Lower 95%":np.maximum(0,forecast-1.96*sigma),"Upper 95%":forecast+1.96*sigma})
    return out,{"R2":float(r2_score(d[target_col],pred)),"MAE":float(mean_absolute_error(d[target_col],pred)),"RMSE":float(math.sqrt(mean_squared_error(d[target_col],pred))),"Residual Std":sigma,"External Drivers":used}

def save_scenario(name: str, parent_name: str, parameters: dict, kpis: dict, username: str, db_path="enterprise_full_workspace.db") -> str:
    sid="SCN-"+hashlib.sha256((name+username).encode()).hexdigest()[:12].upper()
    with sqlite3.connect(db_path) as c:
        c.execute("INSERT OR REPLACE INTO platform_scenarios VALUES(?,?,?,?,?,?,?)",(sid,name,parent_name,json.dumps(parameters,default=str),json.dumps(kpis,default=str),username,_now())); c.commit()
    return sid

def scenario_table(db_path="enterprise_full_workspace.db") -> pd.DataFrame:
    with sqlite3.connect(db_path) as c: return pd.read_sql("SELECT * FROM platform_scenarios ORDER BY created_at DESC",c)

def predictive_maintenance_score(df: pd.DataFrame) -> pd.DataFrame:
    req={"Asset","Temperature","Vibration","RuntimeHours"}
    if not req<=set(df.columns): raise ValueError(f"Maintenance scoring requires {sorted(req)}")
    d=df.copy()
    for col in ["Temperature","Vibration","RuntimeHours"]: d[col]=pd.to_numeric(d[col],errors="coerce").fillna(0)
    d["Risk Score"]=0.35*(d["Temperature"]/(d["Temperature"].abs().median()+1e-9)).clip(0,2)*50 + 0.45*(d["Vibration"]/(d["Vibration"].abs().median()+1e-9)).clip(0,2)*50 + 0.20*(d["RuntimeHours"]/(d["RuntimeHours"].abs().median()+1e-9)).clip(0,2)*50
    d["Risk Score"]=d["Risk Score"].clip(0,100); d["Maintenance Action"]=np.select([d["Risk Score"]>=75,d["Risk Score"]>=50],["Inspect / schedule maintenance","Monitor closely"],default="Normal monitoring")
    return d.sort_values("Risk Score",ascending=False)

def currency_convert(df: pd.DataFrame, amount_col: str, currency_col: str, base_currency: str, rates: dict) -> pd.DataFrame:
    if amount_col not in df.columns or currency_col not in df.columns: raise ValueError("Currency conversion requires amount and currency columns.")
    d=df.copy(); d[amount_col]=pd.to_numeric(d[amount_col],errors="coerce").fillna(0); d[currency_col]=d[currency_col].astype(str).str.upper()
    d["Base Amount"]=d.apply(lambda r: r[amount_col]/float(rates[r[currency_col]]) if r[currency_col] in rates and float(rates[r[currency_col]])>0 else np.nan,axis=1)
    d["Base Currency"]=base_currency.upper(); return d

def render_module(module: str, tier: str, username: str):
    import streamlit as st
    import plotly.express as px
    init_platform_db()
    render_module_data_exchange(module, st, tier, username)
    required=next((x["tier"] for x in PLATFORM_CATALOG if x["name"]==module),None)
    if required and not tier_allows(tier,required):
        st.warning(f"🔒 {module} requires {required}. Your current tier is {tier}. Open Subscriptions to review upgrade options.")
        return
    st.markdown(f"## {module}")
    st.caption(next((x["when"] for x in PLATFORM_CATALOG if x["name"]==module),"Industrial engineering workspace"))
    if module=="Engineering Validation Center":
        df=st.session_state.setdefault("validation_df",pd.DataFrame({"Metric":["Cost","Service Level","Capacity"],"Value":[100000,95,12000],"Unit":["USD","%","units"]}))
        edited=st.data_editor(df,num_rows="dynamic",use_container_width=True,key="validation_editor")
        if st.button("🔎 Validate Model",type="primary",use_container_width=True,key="validation_run"):
            res=validate_table(edited,required=["Metric","Value"]); st.session_state["validation_result"]=res
        if st.session_state.get("validation_result"):
            res=st.session_state.validation_result; st.metric("Data Quality",f'{res["quality"]["score"]:.1f}%'); st.write(res)
        st.dataframe(edited,use_container_width=True)
        render_export_bar(module,[("Validation Table",edited)],tier=tier,username=username)
    elif module=="Industrial Data Model & Digital Thread":
        tabs=st.tabs(["Entities","Relationships","Data Quality"])
        with tabs[0]:
            entity_type=st.selectbox("Entity type",["Product","SKU","Customer","Supplier","Facility","Machine","Employee","Material","Route","Operation","Order"])
            id_col=st.text_input("ID column","ID")
            df=st.data_editor(st.session_state.setdefault("thread_df",pd.DataFrame({"ID":["FAC-001","MCH-001"],"name":["Riyadh DC","CNC-01"],"capacity":[1000,80]})),num_rows="dynamic",use_container_width=True,key="thread_editor")
            if st.button("🔗 Register Entities",type="primary",use_container_width=True,key="thread_register"):
                if id_col in df.columns: st.success(f"Registered {upsert_entities(df,entity_type,id_col):,} entities into the digital thread.")
                else: st.error(f"ID column '{id_col}' not found.")
            with sqlite3.connect("enterprise_full_workspace.db") as c: ent=pd.read_sql("SELECT * FROM industrial_entities ORDER BY updated_at DESC LIMIT 100",c)
            st.dataframe(ent,use_container_width=True,hide_index=True)
        with tabs[1]:
            rel=st.data_editor(st.session_state.setdefault("thread_rel",pd.DataFrame({"From":["FAC-001"],"Relationship":["contains"],"To":["MCH-001"]})),num_rows="dynamic",use_container_width=True,key="thread_rel_editor")
            st.info("Relationships are intentionally explicit: use entity IDs and relationship names; no hidden inference.")
        with tabs[2]:
            st.write(data_quality_report(df))
        render_export_bar(module,[("Entities",df),("Relationships",rel)],tier=tier,username=username)
    elif module=="Advanced Planning & Scheduling":
        tabs=st.tabs(["Demand / MRP","Finite Schedule","Dispatch"])
        with tabs[0]:
            demand=st.data_editor(st.session_state.setdefault("aps_demand",pd.DataFrame({"Product":["P-100","P-200"],"DemandQty":[1000,600]})),num_rows="dynamic",use_container_width=True,key="aps_demand_editor")
            bom=st.data_editor(st.session_state.setdefault("aps_bom",pd.DataFrame({"Parent":["P-100","P-200"],"Component":["C-1","C-2"],"QtyPer":[2,3]})),num_rows="dynamic",use_container_width=True,key="aps_bom_editor")
            if st.button("🧮 Explode MRP",use_container_width=True,key="aps_mrp"): st.session_state["aps_mrp_result"]=mrp_explode(demand,bom)
            if "aps_mrp_result" in st.session_state: st.dataframe(st.session_state["aps_mrp_result"],use_container_width=True)
        with tabs[1]:
            orders=st.data_editor(st.session_state.setdefault("aps_orders",pd.DataFrame({"Order":["WO-001","WO-002","WO-003"],"Product":["P-100","P-200","P-100"],"Qty":[100,200,150],"DueDate":[datetime.now()+timedelta(hours=8),datetime.now()+timedelta(hours=10),datetime.now()+timedelta(hours=12)],"ProcessingMin":[30,40,25],"SetupMin":[5,10,5],"Machine":["M-01","M-01","M-02"],"Priority":[2,1,3]})),num_rows="dynamic",use_container_width=True,key="aps_orders_editor")
            if st.button("📅 Build Finite Schedule",type="primary",use_container_width=True,key="aps_schedule"): st.session_state["aps_schedule_result"]=finite_schedule(orders)
            if "aps_schedule_result" in st.session_state:
                sch=st.session_state["aps_schedule_result"]; st.dataframe(sch,use_container_width=True); fig=px.timeline(sch,x_start="Start",x_end="Finish",y="Machine",color="Product",hover_data=["Order","LateMin"]); st.plotly_chart(fig,use_container_width=True)
        with tabs[2]:
            st.info("Dispatch uses the validated finite schedule as the release list. Export it as Excel/PDF/PPT from the panel below.")
            st.dataframe(st.session_state.get("aps_schedule_result",pd.DataFrame()),use_container_width=True)
        tables=[("Demand",demand),("BOM",bom),("Finite Schedule",st.session_state.get("aps_schedule_result",pd.DataFrame()))]
        figs=[("Finite Schedule",fig)] if "fig" in locals() else []
        render_export_bar(module,tables,figs,tier=tier,username=username)
    elif module=="Manufacturing Execution System":
        tabs=st.tabs(["Work Orders","Execution Events","OEE & WIP"])
        with tabs[0]:
            wo=st.data_editor(st.session_state.setdefault("mes_wo_df",pd.DataFrame({"Work Order":["WO-001","WO-002"],"Product":["P-100","P-200"],"Quantity":[1000,600],"Due Date":[str(datetime.now()+timedelta(days=1)),str(datetime.now()+timedelta(days=2))],"Status":["Released","Released"],"Machine":["M-01","M-02"],"Operator":[""]*2})),num_rows="dynamic",use_container_width=True,key="mes_wo_editor")
            if st.button("💾 Save Work Orders",type="primary",use_container_width=True,key="mes_save"): 
                with sqlite3.connect("enterprise_full_workspace.db") as c:
                    for r in wo.to_dict("records"): c.execute("INSERT OR REPLACE INTO mes_work_orders VALUES(?,?,?,?,?,?,?,?)",(r["Work Order"],r["Product"],float(r["Quantity"]),str(r["Due Date"]),r["Status"],r["Machine"],r["Operator"],_now()))
                    c.commit()
                st.success("Work orders saved.")
        with tabs[1]:
            ev=st.data_editor(st.session_state.setdefault("mes_events_df",pd.DataFrame({"Work Order":["WO-001"],"Event":["START"],"Event Time":[_now()],"Quantity":[0],"Reason":[""],"Operator":[""]})),num_rows="dynamic",use_container_width=True,key="mes_event_editor")
            if st.button("📝 Record Events",use_container_width=True,key="mes_event_save"):
                with sqlite3.connect("enterprise_full_workspace.db") as c:
                    for r in ev.to_dict("records"): c.execute("INSERT INTO mes_events(work_order,event_type,event_time,quantity,reason,operator) VALUES(?,?,?,?,?,?)",(r["Work Order"],r["Event"],str(r["Event Time"]),float(r["Quantity"] or 0),str(r["Reason"]),str(r["Operator"])))
                    c.commit()
        with tabs[2]:
            oe=st.data_editor(st.session_state.setdefault("mes_oee_df",pd.DataFrame({"PlannedMin":[480],"DowntimeMin":[45],"IdealCycleSec":[30],"TotalCount":[800],"GoodCount":[760]})),num_rows="dynamic",use_container_width=True,key="mes_oee_editor")
            if st.button("📊 Calculate OEE",type="primary",use_container_width=True,key="mes_oee_run"):
                st.session_state["mes_oee_result"]=oee_from_events(oe.iloc[[0]])
            if "mes_oee_result" in st.session_state: st.json(st.session_state["mes_oee_result"])
            with sqlite3.connect("enterprise_full_workspace.db") as c: saved=pd.read_sql("SELECT * FROM mes_work_orders",c)
            st.write("Persisted Work Orders"); st.dataframe(saved,use_container_width=True,hide_index=True)
        render_export_bar(module,[("Work Orders",wo),("Events",ev),("OEE Input",oe),("Persisted Work Orders",saved if "saved" in locals() else pd.DataFrame())],tier,username)
    elif module=="Quality Engineering & Reliability":
        tabs=st.tabs(["SPC & Capability","MSA","DOE / ANOVA / Regression","FMEA & Reliability"])
        with tabs[0]:
            qc=st.data_editor(st.session_state.setdefault("quality_df",pd.DataFrame({"Sample":range(1,21),"Measurement":np.random.default_rng(1).normal(10,0.2,20)})),num_rows="dynamic",use_container_width=True,key="quality_editor")
            lsl=st.number_input("LSL",value=9.0,key="quality_lsl"); usl=st.number_input("USL",value=11.0,key="quality_usl")
            if st.button("📈 Analyze SPC & Capability",type="primary",use_container_width=True,key="quality_spc"): st.session_state["quality_spc"]=capability(qc["Measurement"],lsl,usl); st.session_state["quality_limits"]=spc_limits(qc["Measurement"])
            if "quality_spc" in st.session_state: st.json({**st.session_state["quality_spc"],**st.session_state["quality_limits"]})
        with tabs[1]:
            msa=st.data_editor(st.session_state.setdefault("msa_df",pd.DataFrame({"Part":[1,1,2,2,3,3],"Operator":["A","B"]*3,"Measurement":[10.1,10.2,11.0,10.9,9.9,10.0]})),num_rows="dynamic",use_container_width=True,key="msa_editor")
            if st.button("🔬 Calculate Gage R&R",use_container_width=True,key="msa_run"): st.json(gage_rr(msa))
        with tabs[2]:
            anova=st.data_editor(st.session_state.setdefault("anova_df",pd.DataFrame({"Group":["A","A","B","B","C","C"],"Value":[1.0,1.1,1.8,1.7,2.2,2.1],"X1":[1,2,3,4,5,6]})),num_rows="dynamic",use_container_width=True,key="anova_editor")
            if st.button("🧪 Run ANOVA",use_container_width=True,key="anova_run"): st.json(one_way_anova(anova,"Group","Value"))
            target=st.selectbox("Regression target",list(anova.columns),key="quality_reg_target"); feats=st.multiselect("Regression features",[c for c in anova.columns if c!=target],key="quality_reg_feats")
            if feats and st.button("📐 Fit Regression",use_container_width=True,key="reg_run"): coef,met=regression_fit(anova,target,feats); st.dataframe(coef); st.json(met)
        with tabs[3]:
            fmea=st.data_editor(st.session_state.setdefault("fmea_df",pd.DataFrame({"Failure Mode":["Bearing wear","Loose fastener"],"Severity":[8,6],"Occurrence":[5,4],"Detection":[3,5]})),num_rows="dynamic",use_container_width=True,key="fmea_editor")
            if st.button("⚠️ Calculate RPN",use_container_width=True,key="fmea_run"): st.session_state["fmea_result"]=fmea_score(fmea)
            if "fmea_result" in st.session_state: st.dataframe(st.session_state["fmea_result"],use_container_width=True)
            failures=st.number_input("Weibull sample count",1,1000,20,key="weibull_n")
            sample=np.maximum(.1,np.random.default_rng(2).weibull(2,failures)*100)
            if st.button("📉 Fit Weibull",use_container_width=True,key="weibull_run"): st.json(weibull_analysis(sample))
        render_export_bar(module,[("Quality Data",qc),("MSA",msa),("ANOVA",anova),("FMEA",fmea)],tier,username)
    elif module=="Industrial Simulation Lab":
        tabs=st.tabs(["Discrete Event","Agent Based","System Dynamics"])
        with tabs[0]:
            c1,c2,c3=st.columns(3); ar=c1.number_input("Arrival rate / hr",1.0,1000.0,20.0,key="sim_ar"); sr=c2.number_input("Service rate / hr / server",1.0,1000.0,25.0,key="sim_sr"); servers=c3.number_input("Servers",1,20,2,key="sim_servers")
            if st.button("▶ Run DES Replications",type="primary",use_container_width=True,key="sim_des"): st.session_state["sim_des"]=queue_simulation(ar,sr,servers)
            if "sim_des" in st.session_state: st.dataframe(st.session_state["sim_des"],use_container_width=True)
        with tabs[1]:
            agents=st.slider("Agents",5,200,30,key="sim_agents"); steps=st.slider("Steps",20,500,100,key="sim_steps")
            if st.button("🤖 Run Agent Simulation",use_container_width=True,key="sim_agent"): st.session_state["sim_agent"]=agent_simulation(agents,steps)
            if "sim_agent" in st.session_state: st.dataframe(st.session_state["sim_agent"],use_container_width=True)
        with tabs[2]:
            inv=st.number_input("Initial inventory",0.0,100000.0,5000.0,key="sd_inv"); demand=st.number_input("Demand/day",0.1,10000.0,500.0,key="sd_dem"); repl=st.number_input("Replenishment/day",0.0,10000.0,550.0,key="sd_repl")
            if st.button("📈 Run System Dynamics",use_container_width=True,key="sd_run"): st.session_state["sd"]=system_dynamics_inventory(inv,demand,repl)
            if "sd" in st.session_state: st.dataframe(st.session_state["sd"],use_container_width=True); st.line_chart(st.session_state["sd"].set_index("Day")[["Inventory","Demand","Replenishment"]])
        figs=[]; tables=[]
        if "sim_des" in st.session_state: tables.append(("DES Replications",st.session_state["sim_des"]))
        if "sim_agent" in st.session_state: tables.append(("Agent Summary",st.session_state["sim_agent"]))
        if "sd" in st.session_state: tables.append(("System Dynamics",st.session_state["sd"]))
        render_export_bar(module,tables,[],tier=tier,username=username)
    elif module=="3D Factory Designer":
        df=st.data_editor(st.session_state.setdefault("factory3d_df",pd.DataFrame({"Asset":["CNC-01","Assembly","Packing","WIP Buffer"],"Type":["Machine","Station","Station","Storage"],"X":[0,6,12,3],"Y":[0,2,2,5],"Z":[0,0,0,0],"Length":[2,4,4,3],"Width":[2,2,2,3],"Height":[2,3,3,2]})),num_rows="dynamic",use_container_width=True,key="factory3d_editor")
        fig=px.scatter_3d(df,x="X",y="Y",z="Z",color="Type",text="Asset",size="Height",title="3D Factory Model"); st.plotly_chart(fig,use_container_width=True)
        if st.button("📏 Analyze Travel Distances",use_container_width=True,key="factory3d_dist"):
            pts=pd.to_numeric(df[["X","Y","Z"]].stack(),errors="coerce").unstack().fillna(0).to_numpy(); pairs=[] 
            for i in range(len(pts)):
                for j in range(i+1,len(pts)): pairs.append({"From":df.iloc[i]["Asset"],"To":df.iloc[j]["Asset"],"Distance":float(np.linalg.norm(pts[i]-pts[j]))})
            st.session_state["factory3d_dist"]=pd.DataFrame(pairs).sort_values("Distance")
        if "factory3d_dist" in st.session_state: st.dataframe(st.session_state["factory3d_dist"].head(50),use_container_width=True)
        render_export_bar(module,[("3D Layout",df),("Travel Matrix",st.session_state.get("factory3d_dist",pd.DataFrame()))],[("3D Factory",fig)],tier,username)
    elif module=="Industrial Connectivity Hub":
        tabs=st.tabs(["REST / SAP / Oracle / WMS","SQL","MQTT / OPC-UA"])
        with tabs[0]:
            conn_df=st.data_editor(st.session_state.setdefault("conn_df",pd.DataFrame({"Name":["SAP Demo","Oracle Demo","WMS Demo"],"System Type":["SAP","Oracle","WMS"],"Endpoint":["https://example.com","",""],"Status":["Not Tested","",""]})),num_rows="dynamic",use_container_width=True,key="conn_editor")
            selected=st.selectbox("Connector",conn_df["Name"].tolist(),key="conn_selected"); token=st.text_input("Bearer token (session only)",type="password",key="conn_token")
            if st.button("🔌 Test REST Connector",type="primary",use_container_width=True,key="conn_rest"):
                import requests
                row=conn_df[conn_df["Name"]==selected].iloc[0]; url=str(row["Endpoint"]).strip()
                if not url: st.error("Enter an endpoint."); 
                else:
                    try:
                        rr=requests.get(url,headers={"Authorization":"Bearer "+token} if token else {},timeout=10); st.success(f"HTTP {rr.status_code}"); log_security_event(username,"connector_test",f"{selected}|HTTP {rr.status_code}")
                    except Exception as exc: st.error(f"Connection failed safely: {exc}")
        with tabs[1]:
            query=st.text_area("Read-only SQL query","SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            if st.button("🗄️ Execute Read-Only SQL",use_container_width=True,key="conn_sql"):
                if not query.lstrip().lower().startswith("select"): st.error("Only SELECT queries are permitted.")
                else:
                    try:
                        with sqlite3.connect("enterprise_full_workspace.db") as c: st.dataframe(pd.read_sql_query(query,c))
                    except Exception as exc: st.error(f"SQL failed safely: {exc}")
        with tabs[2]:
            st.info("MQTT and OPC-UA connectors are configuration-ready. Live sessions require the site broker/server and protocol libraries.")
            mqtt_topic=st.text_input("MQTT topic","factory/telemetry/#"); opc_url=st.text_input("OPC-UA endpoint","opc.tcp://localhost:4840")
            if st.button("🧪 Validate Connector Settings",use_container_width=True,key="conn_validate"): st.write({"MQTT":mqtt_topic,"OPC-UA":opc_url,"Status":"Configuration accepted; no live connection attempted."})
        render_export_bar(module,[("Connector Profiles",conn_df)],tier,username)
    elif module=="Multi-Objective Optimization":
        df=st.data_editor(st.session_state.setdefault("multiobj_df",pd.DataFrame({"Scenario":["A","B","C","D"],"Cost":[100,90,130,110],"Carbon":[80,120,60,75],"Service":[94,97,99,96],"Risk":[12,20,8,15]})),num_rows="dynamic",use_container_width=True,key="multiobj_editor")
        weights={c:st.number_input(c+" weight",0.0,1.0,0.25,key="mo_w_"+c) for c in ["Cost","Carbon","Service","Risk"]}
        if st.button("⚖️ Calculate Composite Trade-off",type="primary",use_container_width=True,key="multiobj_run"):
            st.session_state["multiobj_result"]=multiobjective_score(df,weights,{"Service":False,"Cost":True,"Carbon":True,"Risk":True})
            st.session_state["pareto"]=pareto_frontier(df,["Cost","Carbon","Risk"],[True,True,True])
        st.dataframe(st.session_state.get("multiobj_result",df),use_container_width=True)
        if "pareto" in st.session_state: st.write("Pareto Frontier"); st.dataframe(st.session_state["pareto"],use_container_width=True)
        render_export_bar(module,[("Scenarios",df),("Scored Scenarios",st.session_state.get("multiobj_result",pd.DataFrame())),("Pareto",st.session_state.get("pareto",pd.DataFrame()))],tier,username)
    elif module=="Robust & Resilient Optimization":
        d=st.data_editor(st.session_state.setdefault("robust_df",pd.DataFrame({"Metric":["Demand Mean","Demand Std","Capacity","Lead Time Mean","Lead Time Std","Disruption Probability","Disruption Capacity Multiplier"],"Value":[1000,150,1100,7,1.5,.05,.6]})),num_rows="dynamic",use_container_width=True,key="robust_editor")
        sims=st.number_input("Simulations",500,100000,5000,500,key="robust_sims")
        if st.button("🎲 Run Robust Risk Analysis",type="primary",use_container_width=True,key="robust_run"):
            vals=d.set_index("Metric")["Value"].to_dict(); st.session_state["robust_result"]=robust_risk_analysis(float(vals["Demand Mean"]),float(vals["Demand Std"]),float(vals["Capacity"]),float(vals["Lead Time Mean"]),float(vals["Lead Time Std"]),float(vals["Disruption Probability"]),float(vals["Disruption Capacity Multiplier"]),int(sims))
        if "robust_result" in st.session_state: st.json(st.session_state["robust_result"])
        render_export_bar(module,[("Risk Inputs",d),("Robust Result",pd.DataFrame([st.session_state.get("robust_result",{})]))],tier,username)
    elif module=="Engineering Model Registry":
        df=st.data_editor(st.session_state.setdefault("model_registry_df",pd.DataFrame({"Model Name":["Network Baseline"],"Type":["MILP"],"Version":["1.0.0"],"Status":["Draft"],"Data Hash":[""]})),num_rows="dynamic",use_container_width=True,key="model_registry_editor")
        name=st.text_input("Model name","My Industrial Model",key="registry_name"); model_type=st.text_input("Model type","Optimization",key="registry_type"); params=st.text_area("Parameters JSON",'{"objective":"cost"}',key="registry_params")
        if st.button("💾 Register Model Snapshot",type="primary",use_container_width=True,key="registry_save"):
            try:
                mid=save_model_snapshot(name,model_type,json.loads(params),hashlib.sha256(df.to_csv(index=False).encode()).hexdigest(),username,{"user_entered":"true"}); st.success(f"Registered {mid}")
            except Exception as exc: st.error(f"Could not register model: {exc}")
        with sqlite3.connect("enterprise_full_workspace.db") as c: reg=pd.read_sql("SELECT * FROM platform_models ORDER BY created_at DESC",c)
        st.dataframe(reg,use_container_width=True,hide_index=True)
        render_export_bar(module,[("Registry",df),("Persisted Models",reg)],tier,username)
    elif module=="Experiment Lab":
        scenarios=st.data_editor(st.session_state.setdefault("experiment_df",pd.DataFrame({"Scenario":["Baseline","High Demand","Supplier Shock","Capacity Expansion"],"Cost":[100000,125000,142000,115000],"Service":[95,90,82,98],"Risk":[10,18,35,8],"Inventory":[5000,6200,7000,4700],"Carbon":[1000,1100,1300,850]})),num_rows="dynamic",use_container_width=True,key="experiment_editor")
        if st.button("🧪 Analyze Scenario Set",type="primary",use_container_width=True,key="experiment_run"):
            st.session_state["experiment_results"]=scenarios.assign(CostDelta=scenarios["Cost"]-scenarios["Cost"].iloc[0],ServiceDelta=scenarios["Service"]-scenarios["Service"].iloc[0],RiskDelta=scenarios["Risk"]-scenarios["Risk"].iloc[0])
            expid=save_experiment("Scenario Matrix",module,scenarios.to_dict("records"),st.session_state["experiment_results"].to_dict("records"),username); st.success(f"Experiment saved: {expid}")
        st.dataframe(st.session_state.get("experiment_results",scenarios),use_container_width=True)
        render_export_bar(module,[("Scenarios",scenarios),("Experiment Results",st.session_state.get("experiment_results",pd.DataFrame()))],tier,username)
    elif module=="Industrial Control Center":
        st.subheader("Unified Operations Health")
        entities={}
        for key,label in [("customers_list","Demand / Customers"),("warehouses_list","Facilities / Warehouses"),("fleet_list","Fleet"),("meio_data","MEIO"),("slotting_data","Warehouse Slotting")]:
            val=st.session_state.get(key); entities[label]=len(val) if isinstance(val,(list,pd.DataFrame)) else 0
        metrics=pd.DataFrame({"Area":list(entities.keys()),"Records":list(entities.values())}); metrics["Health"]=np.where(metrics["Records"]>0,"Ready","Needs Data")
        st.dataframe(metrics,use_container_width=True,hide_index=True)
        st.metric("Data quality score",f"{data_quality_report(metrics)['score']:.1f}%")
        render_export_bar(module,[("Control Center",metrics)],tier,username)
    elif module=="Engineering Decision Center":
        st.subheader("Decision Card Builder")
        title=st.text_input("Decision title","Network redesign decision",key="decision_title"); metric_text=st.text_area("Metrics JSON",'{"Cost Delta %":-8.2,"Service Delta %":2.1,"Carbon Delta %":-4.5}',key="decision_metrics"); ass_text=st.text_area("Assumptions JSON",'{"Demand horizon":"12 weeks","Lead time":"7 days"}',key="decision_assumptions"); unc_text=st.text_area("Uncertainty JSON",'{"P95 cost exposure":"12%"}',key="decision_unc")
        status=st.selectbox("Status",["Proposed","Under Review","Approved","Rejected"],key="decision_status")
        if st.button("📝 Save Decision Card",type="primary",use_container_width=True,key="decision_save"):
            try:
                card=create_decision_card(title,module,json.loads(metric_text),json.loads(ass_text),json.loads(unc_text),status); did=save_decision_card(card,username); st.success(f"Saved decision {did}")
            except Exception as exc: st.error(f"Decision card error: {exc}")
        with sqlite3.connect("enterprise_full_workspace.db") as c: dec=pd.read_sql("SELECT * FROM platform_decisions ORDER BY created_at DESC",c)
        st.dataframe(dec,use_container_width=True,hide_index=True)
        render_export_bar(module,[("Decision Cards",dec)],tier,username)
    elif module=="Industrial Data Platform":
        up=st.file_uploader("📥 Ingest CSV / XLSX",type=["csv","xlsx"],key="data_platform_upload")
        if up is not None:
            try:
                raw=up.getvalue(); lower=up.name.lower()
                sheets={"CSV":pd.read_csv(io.BytesIO(raw))} if lower.endswith(".csv") else {s:pd.read_excel(io.BytesIO(raw),sheet_name=s) for s in pd.ExcelFile(io.BytesIO(raw)).sheet_names}
                st.write({"file":up.name,"sheets":list(sheets),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
                for name,df in sheets.items():
                    did=register_dataset(name,up.name,df); st.subheader(name); st.write(data_quality_report(df)); st.dataframe(df.head(25),use_container_width=True)
                    st.success(f"Registered dataset {did}")
                with sqlite3.connect("enterprise_full_workspace.db") as c: cat=pd.read_sql("SELECT * FROM platform_datasets ORDER BY created_at DESC",c)
                st.dataframe(cat,use_container_width=True,hide_index=True)
            except Exception as exc: st.error(f"Ingestion failed safely: {exc}")
    elif module=="Capital Investment & Engineering Economics":
        cf=st.data_editor(st.session_state.setdefault("capex_df",pd.DataFrame({"Year":[1,2,3,4,5],"Cash Flow":[45000,50000,55000,60000,65000]})),num_rows="dynamic",use_container_width=True,key="capex_editor")
        initial=st.number_input("Initial investment",0.0,100000000.0,180000.0,key="capex_initial"); rate=st.number_input("Discount rate",0.0,1.0,.1,key="capex_rate")
        salvage=st.number_input("Salvage value",0.0,100000000.0,0.0,key="capex_salvage")
        if st.button("💰 Calculate NPV / IRR / Payback",type="primary",use_container_width=True,key="capex_run"): st.session_state["capex_result"]=capital_metrics(initial,cf["Cash Flow"].tolist(),rate,salvage)
        if "capex_result" in st.session_state: st.json(st.session_state["capex_result"])
        render_export_bar(module,[("Cash Flows",cf),("Capital Metrics",pd.DataFrame([st.session_state.get("capex_result",{})]))],tier,username)
    elif module=="Workforce Engineering":
        tabs=st.tabs(["Balance & Takt","Staffing","Skills / Ergonomics"])
        with tabs[0]:
            elems=st.data_editor(st.session_state.setdefault("work_elements",pd.DataFrame({"Element":["Pick","Assemble","Inspect","Pack"],"TimeMin":[2.5,3.5,1.5,2.0]})),num_rows="dynamic",use_container_width=True,key="work_editor")
            takt=st.number_input("Takt time (min)",0.1,120.0,5.0,key="takt")
            if st.button("⚖️ Balance Line",type="primary",use_container_width=True,key="balance_run"): st.session_state["balance_result"],st.session_state["balance_metrics"]=line_balance(elems,takt)
            if "balance_result" in st.session_state: st.dataframe(st.session_state["balance_result"],use_container_width=True); st.json(st.session_state["balance_metrics"])
        with tabs[1]:
            staff=st.number_input("Staff",1,500,10,key="staff"); mins=st.number_input("Minutes/shift",60.0,1440.0,480.0,key="staff_mins"); prod=st.slider("Productive %",10,100,85,key="staff_prod")
            st.json(staffing_capacity(staff,mins,prod))
        with tabs[2]:
            skill=st.data_editor(st.session_state.setdefault("skills_df",pd.DataFrame({"Employee":["E1","E2","E3"],"Skill":["Welding","Assembly","Inspection"],"Level":[3,2,4]})),num_rows="dynamic",use_container_width=True,key="skills_editor")
            st.dataframe(skill,use_container_width=True)
        render_export_bar(module,[("Work Elements",elems),("Balance",st.session_state.get("balance_result",pd.DataFrame())),("Skills",skill)],tier,username)
    elif module=="Industrial Sustainability & LCA":
        df=st.data_editor(st.session_state.setdefault("sustain_df",pd.DataFrame({"Activity":["Electricity","Diesel","Freight"],"Scope":["Scope 2","Scope 1","Scope 3"],"LifeCycleStage":["Operations","Operations","Distribution"],"Quantity":[10000,2500,15000],"EmissionFactor":[0.42,2.68,0.1]})),num_rows="dynamic",use_container_width=True,key="sustain_editor")
        if st.button("🌱 Calculate Footprint",type="primary",use_container_width=True,key="sustain_run"): st.session_state["sustain_result"]=sustainability_accounting(df)
        if "sustain_result" in st.session_state:
            res=st.session_state["sustain_result"]; st.metric("Total tCO2e",f'{res["tCO2e"].sum():,.2f}'); st.dataframe(lca_summary(res),use_container_width=True); fig=px.bar(res,x="Activity",y="tCO2e",color="Scope",title="Lifecycle Footprint")
            st.plotly_chart(fig,use_container_width=True)
        render_export_bar(module,[("Sustainability Inputs",df),("Footprint",st.session_state.get("sustain_result",pd.DataFrame()))],[("Footprint",fig)] if "fig" in locals() else [],tier,username)
    elif module=="Benchmarking & Engineering Standards":
        actual=st.data_editor(st.session_state.setdefault("benchmark_actual",pd.DataFrame({"Metric":["OEE","OTIF","Inventory Turns","Energy per Unit"],"Actual":[82,96,5.2,1.8]})),num_rows="dynamic",use_container_width=True,key="benchmark_actual_editor")
        bench=st.data_editor(st.session_state.setdefault("benchmark_targets",pd.DataFrame({"Metric":["OEE","OTIF","Inventory Turns","Energy per Unit"],"Benchmark":[85,98,6.0,1.5],"Unit":["%","%","x","kWh/unit"],"Source":["Company Target"]*4,"Source Date":["2026-01"]*4})),num_rows="dynamic",use_container_width=True,key="benchmark_targets_editor")
        if st.button("📏 Compare Benchmarks",type="primary",use_container_width=True,key="benchmark_run"): st.session_state["benchmark_result"]=benchmark_compare(actual,bench)
        if "benchmark_result" in st.session_state: st.dataframe(st.session_state["benchmark_result"],use_container_width=True)
        render_export_bar(module,[("Actual",actual),("Benchmarks",bench),("Comparison",st.session_state.get("benchmark_result",pd.DataFrame()))],tier,username)
    elif module=="Engineering Validation Center":
        pass
    elif module=="Advanced Engineering Copilot":
        st.info("Advanced Copilot orchestration is configured through the main AI Copilot module. Use the AI Copilot to approve multi-step workflows; this module exposes governance and execution history.")
        st.write("Available tool families:",[x["name"] for x in PLATFORM_CATALOG if x["tier"] in ("Starter","Mid-Tier Pro","Professional","Enterprise")][:20])
    elif module=="Live Industrial Digital Twin":
        tel=st.data_editor(st.session_state.setdefault("twin_tel",pd.DataFrame({"Asset":["CNC-01","CNC-01","Packing-01"],"Timestamp":[_now(),_now(),_now()],"Metric":["Temperature","Vibration","Temperature"],"Value":[65,2.4,72],"Source":["simulated","simulated","simulated"]})),num_rows="dynamic",use_container_width=True,key="twin_editor")
        if st.button("🌐 Update Twin State",type="primary",use_container_width=True,key="twin_update"):
            with sqlite3.connect("enterprise_full_workspace.db") as c:
                for r in tel.to_dict("records"): c.execute("INSERT INTO telemetry_events(asset_id,ts,metric,value,source) VALUES(?,?,?,?,?)",(r["Asset"],str(r["Timestamp"]),r["Metric"],float(r["Value"]),r["Source"]))
                c.commit()
        with sqlite3.connect("enterprise_full_workspace.db") as c: stored=pd.read_sql("SELECT * FROM telemetry_events ORDER BY id DESC LIMIT 100",c)
        st.dataframe(stored,use_container_width=True,hide_index=True)
        st.success("Twin state synchronized from persisted telemetry.")
        render_export_bar(module,[("Telemetry Input",tel),("Stored Telemetry",stored)],tier,username)
    elif module=="Advanced ML Demand Forecasting":
        st.subheader("📈 ML Demand Forecasting")
        df=st.data_editor(st.session_state.setdefault("forecast_df",pd.DataFrame({"Date":pd.date_range("2026-01-01",periods=24,freq="MS"),"Demand":np.maximum(100,np.linspace(500,700,24)+np.sin(np.arange(24))*60),"Promotion":[0,0,1,0]*6,"WeatherIndex":[20,21,22,19]*6,"MacroIndex":[100,101,102,103]*6})),num_rows="dynamic",use_container_width=True,key="forecast_editor")
        date_col=st.selectbox("Date column",list(df.columns),index=0,key="forecast_date"); target_col=st.selectbox("Demand/SKU target",list(df.columns),index=1,key="forecast_target"); ext=st.multiselect("External drivers", [c for c in df.columns if c not in [date_col,target_col]],key="forecast_ext"); horizon=st.number_input("Forecast periods",1,104,12,key="forecast_horizon")
        if st.button("🧠 Train & Forecast",type="primary",use_container_width=True,key="forecast_run"):
            try: st.session_state["forecast_result"],st.session_state["forecast_metrics"]=ml_demand_forecast(df,date_col,target_col,ext,int(horizon))
            except Exception as exc: st.error(f"Forecast failed safely: {exc}")
        if "forecast_result" in st.session_state:
            fr=st.session_state["forecast_result"]; st.dataframe(fr,use_container_width=True); st.json(st.session_state["forecast_metrics"])
            fig=px.line(fr,x="Date",y=["Forecast","Lower 95%","Upper 95%"],title="Demand Forecast with 95% uncertainty band"); st.plotly_chart(fig,use_container_width=True)
            render_export_bar(module,[("History",df),("Forecast",fr)],[("Demand Forecast",fig)],tier,username)
    elif module=="Scenario Versioning & Comparison":
        st.subheader("🧪 Scenario Versioning")
        base=st.data_editor(st.session_state.setdefault("scenario_df",pd.DataFrame({"Scenario":["Baseline Q3 Logistics","High-Tariff Expansion","Supplier Shock"],"Cost":[100000,125000,140000],"Service":[95,91,84],"Capacity":[10000,9500,8200],"Carbon":[1000,1100,1250]})),num_rows="dynamic",use_container_width=True,key="scenario_editor")
        if st.button("💾 Save Scenario Versions",type="primary",use_container_width=True,key="scenario_save"):
            for r in base.to_dict("records"): save_scenario(r["Scenario"],"Baseline Q3 Logistics",r,{},username)
            st.success("Scenario versions saved.")
        saved=scenario_table(); st.dataframe(saved,use_container_width=True,hide_index=True)
        if len(base)>=2:
            st.plotly_chart(px.bar(base,x="Scenario",y=["Cost","Service","Capacity","Carbon"],barmode="group",title="Side-by-side Scenario Comparison"),use_container_width=True)
        render_export_bar(module,[("Scenario Inputs",base),("Persisted Scenarios",saved)],tier,username)
    elif module=="Team Workspaces & RBAC":
        st.subheader("👥 Team Workspace & Role-Based Access")
        ws=st.text_input("Workspace name","Plant-01 Engineering",key="workspace_name")
        members=st.data_editor(st.session_state.setdefault("workspace_members_df",pd.DataFrame({"Username":[username],"Role":["Owner"]})),num_rows="dynamic",use_container_width=True,key="workspace_members_editor")
        if st.button("💾 Save Workspace Members",type="primary",use_container_width=True,key="workspace_save"):
            with sqlite3.connect("enterprise_full_workspace.db") as c:
                for r in members.to_dict("records"): c.execute("INSERT OR REPLACE INTO workspace_members VALUES(?,?,?,?)",(ws,r["Username"],r["Role"],_now()))
                c.commit()
            st.success("Workspace membership saved with explicit roles.")
        with sqlite3.connect("enterprise_full_workspace.db") as c: saved=pd.read_sql("SELECT * FROM workspace_members WHERE workspace=?",(c),params=(ws,))
        st.dataframe(saved,use_container_width=True,hide_index=True)
        render_export_bar(module,[("Workspace Members",saved)],tier,username)
    elif module=="Executive Report Center":
        st.subheader("📋 Executive Report Center")
        report=st.data_editor(st.session_state.setdefault("exec_report_df",pd.DataFrame({"KPI":["Cost","Service Level","Carbon","Risk"],"Baseline":[100,95,100,10],"Scenario":[92,97,84,8],"Unit":["index","%","index","index"]})),num_rows="dynamic",use_container_width=True,key="exec_report_editor")
        fig=px.bar(report,x="KPI",y=["Baseline","Scenario"],barmode="group",title="Executive KPI Comparison")
        st.plotly_chart(fig,use_container_width=True)
        render_export_bar(module,[("Executive KPIs",report)],[("Executive KPI Chart",fig)],tier,username)
    elif module=="Predictive Maintenance Digital Twin":
        st.subheader("🛠️ Predictive Maintenance")
        maint=st.data_editor(st.session_state.setdefault("maint_df",pd.DataFrame({"Asset":["CNC-01","Press-02","Packing-01"],"Temperature":[65,82,71],"Vibration":[1.1,3.8,2.2],"RuntimeHours":[1200,3200,2100]})),num_rows="dynamic",use_container_width=True,key="maint_editor")
        if st.button("🔮 Score Maintenance Risk",type="primary",use_container_width=True,key="maint_run"):
            try: st.session_state["maint_result"]=predictive_maintenance_score(maint)
            except Exception as exc: st.error(f"Maintenance analysis failed safely: {exc}")
        if "maint_result" in st.session_state: st.dataframe(st.session_state["maint_result"],use_container_width=True)
        render_export_bar(module,[("Telemetry Features",maint),("Maintenance Risk",st.session_state.get("maint_result",pd.DataFrame()))],tier,username)
    elif module=="Localization & Multi-Currency":
        st.subheader("🌍 Localization & Multi-Currency")
        fx=st.data_editor(st.session_state.setdefault("currency_df",pd.DataFrame({"Item":["Facility A","Facility B","Supplier C"],"Amount":[100000,85000,120000],"Currency":["USD","EUR","SAR"],"Region":["US","EU","SA"]})),num_rows="dynamic",use_container_width=True,key="currency_editor")
        rates=st.text_area("Rates to base currency (1 base = rate units)",'{"USD":1,"EUR":0.92,"SAR":3.75}',key="currency_rates")
        base_cur=st.text_input("Base currency","USD",key="base_currency")
        if st.button("💱 Convert to Base Currency",type="primary",use_container_width=True,key="currency_run"):
            try: st.session_state["currency_result"]=currency_convert(fx,"Amount","Currency",base_cur,json.loads(rates))
            except Exception as exc: st.error(f"Currency conversion failed safely: {exc}")
        if "currency_result" in st.session_state: st.dataframe(st.session_state["currency_result"],use_container_width=True)
        rules=st.data_editor(st.session_state.setdefault("trade_rules_df",pd.DataFrame({"Region From":["SA","EU"],"Region To":["EU","SA"],"Product Class":["Industrial","Industrial"],"Rule":["Check customs code","Check origin documentation"],"Active":[True,True]})),num_rows="dynamic",use_container_width=True,key="trade_rules_editor")
        render_export_bar(module,[("Currency Inputs",fx),("Converted",st.session_state.get("currency_result",pd.DataFrame())),("Trade Rules",rules)],tier,username)
    elif module=="Enterprise Security & Governance":
        tabs=st.tabs(["Posture","Roles","Audit"])
        with tabs[0]:
            st.json({"MFA":"Configurable","SSO/OIDC":"Configuration surface","SAML":"Configuration surface","SCIM":"Configuration surface","Workspace isolation":"Enabled by application role model","Audit logging":"Enabled","Data retention":"Configurable","Secrets":"Use Streamlit secrets/environment variables"})
        with tabs[1]:
            role=st.data_editor(st.session_state.setdefault("security_roles",pd.DataFrame({"Role":["Owner","Planner","Engineer","Viewer"],"Read":["Yes","Yes","Yes","Yes"],"Write":["Yes","Yes","Yes","No"],"Execute":["Yes","Yes","Yes","No"],"Admin":["Yes","No","No","No"]})),num_rows="dynamic",use_container_width=True,key="security_roles_editor")
            st.dataframe(role,use_container_width=True)
        with tabs[2]:
            with sqlite3.connect("enterprise_full_workspace.db") as c: audit=pd.read_sql("SELECT * FROM security_events ORDER BY id DESC LIMIT 200",c)
            st.dataframe(audit,use_container_width=True,hide_index=True)
            render_export_bar(module,[("Roles",role),("Security Events",audit)],tier,username)
