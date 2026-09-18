"""Shoir-IE Industrial Operating System.

Shared, governed decision-intelligence services that sit on top of the existing
Shoir-IE industrial data/model layer. No duplicate business state is created.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import sqlite3
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd
from scipy import stats

METHOD_LIBRARY = [
    {"Category":"Operations Research","Method":"Linear Programming (LP)","When":"Continuous allocation and production planning","Inputs":"Decision variables, objective, constraints","Equation":"min/max cᵀx subject to Ax ≤ b","Limits":"Requires linear relationships."},
    {"Category":"Operations Research","Method":"Mixed-Integer Linear Programming (MILP)","When":"Binary, integer and network decisions","Inputs":"Continuous/integer/binary variables","Equation":"min/max cᵀx subject to Ax ≤ b","Limits":"Complexity can grow rapidly."},
    {"Category":"Operations Research","Method":"Transportation Model","When":"Ship from sources to destinations","Inputs":"Supply, demand, lane cost/capacity","Equation":"min Σcᵢⱼxᵢⱼ","Limits":"Classical model assumes known supply/demand."},
    {"Category":"Operations Research","Method":"Assignment Model","When":"Job/person/machine assignment","Inputs":"Eligible assignments and costs","Equation":"min Σcᵢⱼxᵢⱼ","Limits":"Classical form is one-to-one."},
    {"Category":"Operations Research","Method":"Facility Location","When":"Choose facilities and allocate demand","Inputs":"Fixed cost, variable cost, demand, capacity","Equation":"min fixed + allocation cost","Limits":"Results depend on input assumptions."},
    {"Category":"Supply Chain","Method":"EOQ","When":"Repeated independent replenishment","Inputs":"Demand, setup/order cost, holding cost","Equation":"Q*=√(2DS/H)","Limits":"Stable-demand assumptions."},
    {"Category":"Supply Chain","Method":"Safety Stock","When":"Protect service from variability","Inputs":"Demand/lead-time variability and service target","Equation":"service factor × variability","Limits":"Distribution assumptions matter."},
    {"Category":"Supply Chain","Method":"Reorder Point","When":"Trigger replenishment","Inputs":"Lead-time demand + safety stock","Equation":"ROP = LT demand + SS","Limits":"Needs credible lead-time data."},
    {"Category":"Supply Chain","Method":"MEIO","When":"Multi-echelon inventory positioning","Inputs":"Network, demand, lead time, service","Equation":"Network-wide inventory optimization","Limits":"Network model quality matters."},
    {"Category":"Operations","Method":"Little's Law","When":"Stable flow systems","Inputs":"WIP, throughput, cycle time","Equation":"WIP = Throughput × Cycle Time","Limits":"Requires stable long-run conditions."},
    {"Category":"Operations","Method":"Takt Time","When":"Match production pace to demand","Inputs":"Available time, demand","Equation":"Takt = Available Time / Demand","Limits":"Does not capture all variability by itself."},
    {"Category":"Operations","Method":"Line Balancing","When":"Assign work elements to stations","Inputs":"Element times, precedence, takt","Equation":"Minimize stations / idle time","Limits":"Precedence quality matters."},
    {"Category":"Operations","Method":"CPM","When":"Deterministic project timing","Inputs":"Activities, durations, precedence","Equation":"Longest path through network","Limits":"Durations treated as deterministic."},
    {"Category":"Operations","Method":"PERT","When":"Project timing with uncertainty","Inputs":"Optimistic, likely and pessimistic duration","Equation":"E[T]≈(O+4M+P)/6","Limits":"Approximation depends on assumptions."},
    {"Category":"Queueing","Method":"M/M/1","When":"Single-server stochastic queue","Inputs":"Arrival/service rates","Equation":"ρ=λ/μ","Limits":"Poisson/exponential assumptions."},
    {"Category":"Queueing","Method":"M/M/c","When":"Multi-server stochastic queue","Inputs":"Arrival/service rates and server count","Equation":"Erlang-C family","Limits":"Classical assumptions."},
    {"Category":"Simulation","Method":"Discrete-Event Simulation","When":"Queues, machines, WIP and event-driven operations","Inputs":"Events, distributions, logic","Equation":"State changes at event times","Limits":"Calibration and validation dominate."},
    {"Category":"Simulation","Method":"Monte Carlo Simulation","When":"Risk and uncertainty ranges","Inputs":"Input distributions and sampling","Equation":"Estimate E[g(X)] by repeated sampling","Limits":"Needs credible distributions and replications."},
    {"Category":"Simulation","Method":"System Dynamics","When":"Strategic feedback and accumulation","Inputs":"Stocks, flows, feedback","Equation":"dx/dt=inflow-outflow","Limits":"Less entity-level detail."},
    {"Category":"Quality","Method":"SPC I-MR","When":"Individual observations over time","Inputs":"Time-ordered measurements","Equation":"Individuals + moving-range limits","Limits":"Time order and stability matter."},
    {"Category":"Quality","Method":"X-bar/R","When":"Rational subgroups","Inputs":"Subgroup measurements","Equation":"Control limits from subgroup statistics","Limits":"Needs rational subgrouping."},
    {"Category":"Quality","Method":"Cp/Cpk","When":"Process capability","Inputs":"LSL, USL, mean, σ","Equation":"Cp=(USL-LSL)/(6σ); Cpk=min(Cpu,Cpl)","Limits":"Stability/measurement assumptions."},
    {"Category":"Quality","Method":"Pp/Ppk","When":"Overall process performance","Inputs":"LSL, USL, overall variation","Equation":"Pp=(USL-LSL)/(6s); Ppk=min(Ppu,Ppl)","Limits":"Does not replace stability analysis."},
    {"Category":"Quality","Method":"Gage R&R","When":"Measurement-system assessment","Inputs":"Part/operator/repeat measurements","Equation":"Variance decomposition","Limits":"Study design matters."},
    {"Category":"Quality","Method":"DOE","When":"Factor-effect investigation","Inputs":"Factors, levels, response","Equation":"Effects + ANOVA","Limits":"Design quality matters."},
    {"Category":"Reliability","Method":"Weibull","When":"Time-to-failure analysis","Inputs":"Failure/censor times","Equation":"F(t)=1-exp(-(t/η)^β)","Limits":"Fit quality must be assessed."},
    {"Category":"Reliability","Method":"FMEA / PFMEA","When":"Failure-risk prioritization","Inputs":"Severity, occurrence, detection","Equation":"RPN=S×O×D","Limits":"RPN is a prioritization aid, not a probability."},
    {"Category":"Economics","Method":"NPV","When":"Capital investment analysis","Inputs":"Cash flows, discount rate","Equation":"ΣCFₜ/(1+r)ᵗ","Limits":"Forecast assumptions dominate."},
    {"Category":"Economics","Method":"IRR","When":"Rate-of-return analysis","Inputs":"Investment and cash flows","Equation":"NPV(r)=0","Limits":"Multiple/no IRRs are possible."},
    {"Category":"Sustainability","Method":"Carbon Accounting","When":"GHG footprinting","Inputs":"Activity data + emission factor","Equation":"Emissions=Activity×Factor","Limits":"Boundary/factor quality matters."},
    {"Category":"Sustainability","Method":"Life-Cycle Assessment","When":"Lifecycle environmental analysis","Inputs":"Inventory + impact factors","Equation":"Inventory → impact characterization","Limits":"Functional unit and boundary matter."},
    {"Category":"Decision Science","Method":"Pareto Frontier","When":"Multiple competing objectives","Inputs":"Alternatives/objectives","Equation":"Non-dominated solution set","Limits":"Does not select business preference."},
    {"Category":"Decision Science","Method":"Robust Optimization","When":"Decisions under bounded uncertainty","Inputs":"Uncertainty sets and constraints","Equation":"Optimize worst-case/robust criterion","Limits":"Uncertainty-set design matters."},
    {"Category":"Analytics","Method":"Population Stability Index (PSI)","When":"Monitor numerical distribution drift","Inputs":"Reference and current distributions","Equation":"Σ(current-reference)ln(current/reference)","Limits":"Thresholds are context-specific."},
    {"Category":"Analytics","Method":"Process Mining","When":"Discover actual process behavior","Inputs":"Case, activity, timestamp","Equation":"Variants + transitions + conformance","Limits":"Event semantics must be consistent."},
]

KPI_LIBRARY = [
    {"KPI":"OEE","Formula":"Availability * Performance * Quality / 10000","Inputs":"Availability, Performance, Quality","Unit":"%"},
    {"KPI":"OTIF","Formula":"OnTimeOrders / TotalOrders * 100","Inputs":"OnTimeOrders, TotalOrders","Unit":"%"},
    {"KPI":"FPY","Formula":"GoodFirstPass / TotalUnits * 100","Inputs":"GoodFirstPass, TotalUnits","Unit":"%"},
    {"KPI":"Inventory Turns","Formula":"COGS / AverageInventory","Inputs":"COGS, AverageInventory","Unit":"turns"},
    {"KPI":"Cycle Time","Formula":"WIP / Throughput","Inputs":"WIP, Throughput","Unit":"time"},
    {"KPI":"Capacity Utilization","Formula":"ActualOutput / AvailableCapacity * 100","Inputs":"ActualOutput, AvailableCapacity","Unit":"%"},
    {"KPI":"Energy per Unit","Formula":"Energy / UnitsProduced","Inputs":"Energy, UnitsProduced","Unit":"kWh/unit"},
    {"KPI":"Carbon per Unit","Formula":"tCO2e / UnitsProduced","Inputs":"tCO2e, UnitsProduced","Unit":"tCO2e/unit"},
]

TEMPLATE_LIBRARY = {
    "Assembly Line": {
        "description":"Line-balance, takt and workforce starter model.",
        "tables":{
            "Stations":pd.DataFrame({"Station":["S1","S2","S3","S4"],"WorkMinutes":[4.2,3.8,5.1,4.5],"Operators":[1,1,1,1]}),
            "Demand":pd.DataFrame({"Day":["Mon","Tue","Wed","Thu","Fri"],"Demand":[420,460,455,470,440]}),
        },
    },
    "Warehouse": {
        "description":"Warehouse flow and travel-analysis starter model.",
        "tables":{
            "Locations":pd.DataFrame({"Location":["A01","A02","B01","B02"],"X":[0,10,0,10],"Y":[0,0,10,10],"Capacity":[100,120,90,110]}),
            "Orders":pd.DataFrame({"Order":["O1","O2","O3","O4"],"SKU":["K1","K2","K1","K3"],"Qty":[10,12,8,15],"PickMin":[2.5,3.0,2.0,4.0]}),
        },
    },
    "Supply Chain": {
        "description":"Multi-echelon network starter model.",
        "tables":{
            "Nodes":pd.DataFrame({"Node":["SUP-1","DC-1","DC-2","CUST-1","CUST-2"],"Type":["Supplier","DC","DC","Customer","Customer"]}),
            "Lanes":pd.DataFrame({"From":["SUP-1","SUP-1","DC-1","DC-2"],"To":["DC-1","DC-2","CUST-1","CUST-2"],"CostPerUnit":[2.2,2.5,0.8,0.9]}),
        },
    },
    "Quality Study": {
        "description":"SPC/capability starter dataset.",
        "tables":{"Measurements":pd.DataFrame({"Sample":range(1,21),"Measurement":np.random.default_rng(11).normal(10,0.18,20)})},
    },
    "Process Improvement": {
        "description":"DMAIC/A3 starter baseline and target model.",
        "tables":{"Baseline":pd.DataFrame({"Metric":["Cycle Time","FPY","OEE","Scrap Rate"],"Baseline":[19.2,94.2,79.5,3.8],"Target":[17.0,97.0,85.0,2.0]})},
    },
}

_SAFE_FUNCS={"abs":abs,"min":min,"max":max,"round":round}
_SAFE_BINOPS={ast.Add:lambda a,b:a+b,ast.Sub:lambda a,b:a-b,ast.Mult:lambda a,b:a*b,
              ast.Div:lambda a,b:a/b if b!=0 else math.nan,ast.Pow:lambda a,b:a**b}
_SAFE_UNARY={ast.UAdd:lambda a:+a,ast.USub:lambda a:-a}

def safe_formula(formula: str, variables: Mapping[str,float]) -> float:
    tree=ast.parse(str(formula),mode="eval")
    def visit(node):
        if isinstance(node,ast.Expression): return visit(node.body)
        if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)): return node.value
        if isinstance(node,ast.Name):
            if node.id not in variables: raise ValueError(f"Unknown variable: {node.id}")
            return float(variables[node.id])
        if isinstance(node,ast.BinOp) and type(node.op) in _SAFE_BINOPS: return _SAFE_BINOPS[type(node.op)](visit(node.left),visit(node.right))
        if isinstance(node,ast.UnaryOp) and type(node.op) in _SAFE_UNARY: return _SAFE_UNARY[type(node.op)](visit(node.operand))
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in _SAFE_FUNCS:
            return _SAFE_FUNCS[node.func.id](*[visit(x) for x in node.args])
        raise ValueError("Unsupported formula operation.")
    out=float(visit(tree))
    if not math.isfinite(out): raise ValueError("Formula returned a non-finite result.")
    return out

def now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")

def ensure_os_db(db_path: str="enterprise_full_workspace.db") -> None:
    with sqlite3.connect(db_path) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS os_kpi_definitions(
            kpi_id TEXT PRIMARY KEY,name TEXT,formula TEXT,unit TEXT,owner TEXT,
            created_at TEXT,updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS os_scenarios(
            scenario_id TEXT PRIMARY KEY,name TEXT,parent_id TEXT,version INTEGER,
            description TEXT,parameters_json TEXT,kpis_json TEXT,created_by TEXT,
            created_at TEXT,updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS os_improvement_projects(
            project_id TEXT PRIMARY KEY,title TEXT,method TEXT,phase TEXT,owner TEXT,
            baseline_json TEXT,target_json TEXT,actions_json TEXT,status TEXT,
            created_at TEXT,updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS os_decision_verifications(
            verification_id TEXT PRIMARY KEY,decision_id TEXT,metric TEXT,
            predicted REAL,actual REAL,absolute_error REAL,percent_error REAL,
            verified_by TEXT,verified_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS os_process_mining_runs(
            run_id TEXT PRIMARY KEY,name TEXT,cases INTEGER,events INTEGER,
            variants INTEGER,conformance REAL,created_by TEXT,created_at TEXT,
            diagnostics_json TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS os_drift_runs(
            run_id TEXT PRIMARY KEY,name TEXT,features INTEGER,drifted INTEGER,
            created_by TEXT,created_at TEXT,summary_json TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS os_artifact_manifest(
            artifact_id TEXT PRIMARY KEY,module TEXT,label TEXT,rows INTEGER,
            columns INTEGER,sha256 TEXT,created_by TEXT,created_at TEXT)""")
        c.commit()

def compare_frames(left: pd.DataFrame,right: pd.DataFrame,key: Optional[str]=None) -> pd.DataFrame:
    if not isinstance(left,pd.DataFrame) or not isinstance(right,pd.DataFrame):
        raise TypeError("Both comparison inputs must be DataFrames.")
    a,b=left.copy(),right.copy()
    if key and key in a.columns and key in b.columns:
        numeric=sorted(set(a.select_dtypes(include=np.number).columns)&set(b.select_dtypes(include=np.number).columns))
        cols=[key]+numeric
        m=a[cols].merge(b[cols],on=key,how="outer",suffixes=(" — A"," — B"))
    else:
        n=min(len(a),len(b)); numeric=sorted(set(a.select_dtypes(include=np.number).columns)&set(b.select_dtypes(include=np.number).columns))
        m=pd.DataFrame({"Row":range(n)})
        for col in numeric:
            m[f"{col} — A"]=pd.to_numeric(a[col].iloc[:n],errors="coerce").to_numpy()
            m[f"{col} — B"]=pd.to_numeric(b[col].iloc[:n],errors="coerce").to_numpy()
    for base in sorted({c.replace(" — B","") for c in m.columns if c.endswith(" — B")}):
        left_col=f"{base} — A"; right_col=f"{base} — B"
        if left_col in m.columns:
            av=pd.to_numeric(m[left_col],errors="coerce"); bv=pd.to_numeric(m[right_col],errors="coerce")
            m[f"{base} — Δ"]=bv-av
            m[f"{base} — Δ%"]=(bv-av)/av.replace(0,np.nan)*100
    return m

def scenario_save(name: str,parameters: Mapping[str,Any],kpis: Mapping[str,Any],
                  created_by: str,parent_id: Optional[str]=None,description: str="") -> str:
    ensure_os_db()
    p=json.dumps(parameters,sort_keys=True,default=str)
    sid="SCN-"+hashlib.sha256(f"{name}|{p}".encode()).hexdigest()[:12].upper()
    with sqlite3.connect("enterprise_full_workspace.db") as c:
        version=int(c.execute("SELECT COALESCE(MAX(version),0) FROM os_scenarios WHERE name=?",(name,)).fetchone()[0])+1
        c.execute("INSERT OR REPLACE INTO os_scenarios VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (sid,name,parent_id,version,description,p,json.dumps(kpis,default=str),created_by,now(),now()))
        c.commit()
    return sid

def scenario_list() -> pd.DataFrame:
    ensure_os_db()
    with sqlite3.connect("enterprise_full_workspace.db") as c:
        return pd.read_sql("SELECT scenario_id,name,parent_id,version,description,created_by,created_at,updated_at FROM os_scenarios ORDER BY updated_at DESC",c)

def scenario_compare(name_a: str,name_b: str) -> pd.DataFrame:
    ensure_os_db()
    with sqlite3.connect("enterprise_full_workspace.db") as c:
        a=c.execute("SELECT kpis_json FROM os_scenarios WHERE name=? ORDER BY version DESC LIMIT 1",(name_a,)).fetchone()
        b=c.execute("SELECT kpis_json FROM os_scenarios WHERE name=? ORDER BY version DESC LIMIT 1",(name_b,)).fetchone()
    if not a or not b: return pd.DataFrame(columns=["KPI","Scenario A","Scenario B","Delta","Delta %"])
    ka,kb=json.loads(a[0]),json.loads(b[0]); keys=sorted(set(ka)|set(kb)); rows=[]
    for k in keys:
        try:
            av=float(ka.get(k,np.nan)); bv=float(kb.get(k,np.nan)); delta=bv-av
            rows.append({"KPI":k,"Scenario A":av,"Scenario B":bv,"Delta":delta,"Delta %":delta/av*100 if av!=0 else np.nan})
        except Exception:
            rows.append({"KPI":k,"Scenario A":ka.get(k),"Scenario B":kb.get(k),"Delta":None,"Delta %":None})
    return pd.DataFrame(rows)

def process_mining_discovery(events: pd.DataFrame,case_col="Case ID",activity_col="Activity",
                             time_col="Timestamp",expected_sequence: Optional[Sequence[str]]=None) -> dict:
    req={case_col,activity_col,time_col}
    if not req.issubset(events.columns): raise ValueError(f"Event log requires {sorted(req)}")
    d=events.copy(); d[time_col]=pd.to_datetime(d[time_col],errors="coerce")
    d=d.dropna(subset=[case_col,activity_col,time_col]).sort_values([case_col,time_col])
    if d.empty: raise ValueError("Event log has no valid events.")
    variants=d.groupby(case_col)[activity_col].apply(lambda s:" → ".join(map(str,s))).value_counts().reset_index()
    variants.columns=["Variant","Cases"]
    trans=[]; cycles=[]; mismatches=[]
    for case,g in d.groupby(case_col):
        vals=g[activity_col].astype(str).tolist(); ts=g[time_col].tolist()
        for i in range(len(vals)-1):
            trans.append({"From":vals[i],"To":vals[i+1],"Minutes":max(0,(ts[i+1]-ts[i]).total_seconds()/60)})
        if len(ts)>1: cycles.append((ts[-1]-ts[0]).total_seconds()/60)
        if expected_sequence and vals != [str(x) for x in expected_sequence]:
            mismatches.append({"Case ID":case,"Actual":" → ".join(vals),"Expected":" → ".join(expected_sequence)})
    transitions=pd.DataFrame(trans)
    if not transitions.empty:
        transitions=transitions.groupby(["From","To"],as_index=False).agg(Cases=("Minutes","size"),MeanMinutes=("Minutes","mean"))
    conformance=100.0
    if expected_sequence:
        total=d[case_col].nunique()
        conformance=(total-len(mismatches))/max(total,1)*100
    return {"events":d,"variants":variants,"transitions":transitions,
            "cycle_times":pd.DataFrame({"Case Cycle Minutes":cycles}),
            "cases":int(d[case_col].nunique()),"event_count":len(d),"variant_count":len(variants),
            "conformance":conformance,"mismatches":pd.DataFrame(mismatches)}

def _psi_numeric(reference: Sequence[Any],current: Sequence[Any],bins=10) -> float:
    a=pd.to_numeric(pd.Series(reference),errors="coerce").dropna().astype(float)
    b=pd.to_numeric(pd.Series(current),errors="coerce").dropna().astype(float)
    if len(a)<20 or len(b)<20: raise ValueError("At least 20 numeric observations are required per sample.")
    edges=np.unique(np.quantile(a,np.linspace(0,1,bins+1)))
    if len(edges)<3: return 0.0
    edges[0],edges[-1]=-np.inf,np.inf
    ah,_=np.histogram(a,bins=edges); bh,_=np.histogram(b,bins=edges)
    ap=np.clip(ah/ah.sum(),1e-9,1); bp=np.clip(bh/bh.sum(),1e-9,1)
    return float(np.sum((bp-ap)*np.log(bp/ap)))

def drift_report(reference: pd.DataFrame,current: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for col in [c for c in reference.columns if c in current.columns]:
        a,b=reference[col],current[col]
        if pd.api.types.is_numeric_dtype(a) or pd.api.types.is_numeric_dtype(b):
            score=_psi_numeric(a,b)
            rows.append({"Feature":col,"Type":"Numeric","Drift Score":score,"Flagged":score>=0.2})
        else:
            ap=a.astype(str).value_counts(normalize=True); bp=b.astype(str).value_counts(normalize=True)
            cats=set(ap)|set(bp); js=0.0
            for cat in cats:
                p=max(float(ap.get(cat,0)),1e-9); q=max(float(bp.get(cat,0)),1e-9); m=(p+q)/2
                js += .5*p*math.log(p/m)+.5*q*math.log(q/m)
            rows.append({"Feature":col,"Type":"Categorical","Drift Score":js,"Flagged":js>=0.1})
    return pd.DataFrame(rows).sort_values("Drift Score",ascending=False) if rows else pd.DataFrame(columns=["Feature","Type","Drift Score","Flagged"])

def decision_verify(decision_id: str,predicted: pd.DataFrame,actual: pd.DataFrame,
                    metric_col="Metric",value_col="Value",verified_by="system") -> pd.DataFrame:
    a=predicted[[metric_col,value_col]].copy().rename(columns={value_col:"Predicted"})
    b=actual[[metric_col,value_col]].copy().rename(columns={value_col:"Actual"})
    out=a.merge(b,on=metric_col,how="outer")
    out["Absolute Error"]=(pd.to_numeric(out["Actual"],errors="coerce")-pd.to_numeric(out["Predicted"],errors="coerce")).abs()
    out["Percent Error"]=out["Absolute Error"]/pd.to_numeric(out["Predicted"],errors="coerce").abs().replace(0,np.nan)*100
    ensure_os_db()
    with sqlite3.connect("enterprise_full_workspace.db") as c:
        for r in out.to_dict("records"):
            raw=f"{decision_id}|{r.get(metric_col)}|{now()}"
            vid="VER-"+hashlib.sha256(raw.encode()).hexdigest()[:12].upper()
            c.execute("INSERT OR REPLACE INTO os_decision_verifications VALUES(?,?,?,?,?,?,?,?,?)",
                      (vid,decision_id,str(r.get(metric_col)),float(r.get("Predicted",np.nan)),
                       float(r.get("Actual",np.nan)),float(r.get("Absolute Error",np.nan)),
                       float(r.get("Percent Error",np.nan)),verified_by,now()))
        c.commit()
    return out

def improvement_create(title,method,owner,baseline,target,phase="Define") -> str:
    ensure_os_db()
    pid="IMP-"+hashlib.sha256(f"{title}|{owner}|{now()}".encode()).hexdigest()[:12].upper()
    with sqlite3.connect("enterprise_full_workspace.db") as c:
        c.execute("INSERT INTO os_improvement_projects VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (pid,title,method,phase,owner,json.dumps(baseline,default=str),json.dumps(target,default=str),"[]","Active",now(),now()))
        c.commit()
    return pid

def improvement_list() -> pd.DataFrame:
    ensure_os_db()
    with sqlite3.connect("enterprise_full_workspace.db") as c:
        return pd.read_sql("SELECT project_id,title,method,phase,owner,status,created_at,updated_at FROM os_improvement_projects ORDER BY updated_at DESC",c)

def platform_health(db_path="enterprise_full_workspace.db") -> pd.DataFrame:
    rows=[]
    import importlib.metadata as md, sys
    rows.append({"Component":"Python","Status":"Ready","Detail":sys.version.split()[0]})
    ensure_os_db(db_path)
    try:
        with sqlite3.connect(db_path) as c: ok=c.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        rows.append({"Component":"Database","Status":"Ready" if ok else "Attention","Detail":"PRAGMA quick_check"})
    except Exception as exc: rows.append({"Component":"Database","Status":"Attention","Detail":str(exc)})
    for pkg in ["pandas","numpy","scipy","plotly","streamlit","xlsxwriter","openpyxl"]:
        try: rows.append({"Component":pkg,"Status":"Ready","Detail":md.version(pkg)})
        except Exception as exc: rows.append({"Component":pkg,"Status":"Attention","Detail":str(exc)})
    return pd.DataFrame(rows)

def render_exports(module,tables,figures=(),tier="Enterprise",username="unknown"):
    from industrial_platform import render_export_bar
    safe=[(str(label),df if isinstance(df,pd.DataFrame) else pd.DataFrame(df)) for label,df in tables if df is not None]
    render_export_bar(module,safe,figures,tier,username)

def render_industrial_operating_system(tier="Enterprise",username="unknown"):
    import streamlit as st
    import plotly.express as px
    import plotly.graph_objects as go
    ensure_os_db()

    st.markdown("## 🏭 Industrial Operating System")
    st.caption("A unified layer for KPIs, engineering methods, scenario control, process intelligence, model health, improvement projects and decision verification.")
    tabs=st.tabs(["📊 KPI Studio","📚 Methods","⚖️ Compare","🌿 Scenario Git","🔎 Process Mining",
                  "🧠 Model Health","✅ Decision Verify","🛠️ DMAIC / A3","🧩 Templates","🩺 Platform Health"])

    with tabs[0]:
        st.subheader("KPI Studio")
        left,right=st.columns([1,2])
        with left:
            lib=pd.DataFrame(KPI_LIBRARY)
            kpi=st.selectbox("KPI library",lib["KPI"].tolist(),key="os_kpi_name")
            row=lib[lib["KPI"]==kpi].iloc[0]
            st.markdown(f"**Formula:** {row['Formula']}")
            st.caption(f"Inputs: {row['Inputs']} · Unit: {row['Unit']}")
        with right:
            variables=st.text_area("Variables JSON",'{"Availability":92,"Performance":89,"Quality":98}',key="os_kpi_variables")
            formula=st.text_input("Formula",row["Formula"],key="os_kpi_formula")
            if st.button("Calculate KPI",type="primary",use_container_width=True,key="os_kpi_run"):
                try:
                    val=safe_formula(formula,{k:float(v) for k,v in json.loads(variables).items()})
                    st.metric(kpi,f"{val:,.4g}")
                except Exception as exc: st.error(f"KPI could not be calculated safely: {exc}")
        st.dataframe(lib,use_container_width=True,hide_index=True)

    with tabs[1]:
        st.subheader("Engineering Methods & Equation Library")
        mdf=pd.DataFrame(METHOD_LIBRARY)
        q=st.text_input("Search method, equation, input or limitation",key="os_methods_search")
        cat=st.selectbox("Category",["All"]+sorted(mdf["Category"].unique()),key="os_methods_cat")
        if q: mdf=mdf[mdf.astype(str).apply(lambda s:s.str.contains(q,case=False,regex=False)).any(axis=1)]
        if cat!="All": mdf=mdf[mdf["Category"]==cat]
        st.dataframe(mdf,use_container_width=True,hide_index=True)
        if not mdf.empty:
            chosen=st.selectbox("Open method",mdf["Method"].tolist(),key="os_method_choice")
            st.json(next(x for x in METHOD_LIBRARY if x["Method"]==chosen))

    with tabs[2]:
        st.subheader("Compare Anything")
        a=st.data_editor(st.session_state.setdefault("os_compare_a",pd.DataFrame({"ID":["A","B","C"],"Cost":[100,120,110],"Service":[92,95,94]})),num_rows="dynamic",use_container_width=True,key="os_compare_a_editor")
        b=st.data_editor(st.session_state.setdefault("os_compare_b",pd.DataFrame({"ID":["A","B","C"],"Cost":[90,130,108],"Service":[94,96,97]})),num_rows="dynamic",use_container_width=True,key="os_compare_b_editor")
        match=st.selectbox("Matching",["Row"]+sorted(set(a.columns)&set(b.columns)),key="os_compare_match")
        if st.button("Compare",type="primary",use_container_width=True,key="os_compare_run"):
            try: st.session_state["os_compare_result"]=compare_frames(a,b,None if match=="Row" else match)
            except Exception as exc: st.error(f"Comparison failed safely: {exc}")
        r=st.session_state.get("os_compare_result")
        if isinstance(r,pd.DataFrame) and not r.empty:
            st.dataframe(r,use_container_width=True,hide_index=True)
            delta=[c for c in r.columns if c.endswith("— Δ%")]
            if delta:
                melt=r.melt(id_vars=[r.columns[0]],value_vars=delta,var_name="Metric",value_name="Delta %")
                st.plotly_chart(px.bar(melt,x="Metric",y="Delta %",title="Relative change by metric"),use_container_width=True)
            render_exports("Compare Anything",[("Comparison",r)],[],tier,username)

    with tabs[3]:
        st.subheader("🌿 Scenario Git")
        a,b=st.columns(2)
        with a:
            name=st.text_input("Scenario name","Baseline",key="os_sc_name")
            parent=st.text_input("Parent scenario ID (optional)","",key="os_sc_parent")
            desc=st.text_area("Description","",key="os_sc_desc")
        with b:
            params=st.text_area("Parameters JSON",'{"Capacity":1000,"Demand":900,"LeadTimeDays":7}',key="os_sc_params")
            kpis=st.text_area("KPIs JSON",'{"Cost":100000,"Service":96,"Carbon":120}',key="os_sc_kpis")
        if st.button("Save Scenario Version",type="primary",use_container_width=True,key="os_scenario_save"):
            try: st.success(f"Saved {scenario_save(name,json.loads(params),json.loads(kpis),username,parent or None,desc)}")
            except Exception as exc: st.error(f"Scenario could not be saved safely: {exc}")
        st.dataframe(scenario_list(),use_container_width=True,hide_index=True)
        scs=scenario_list()
        if len(scs)>=2:
            names=scs["name"].tolist()
            x,y=st.columns(2); sa=x.selectbox("Scenario A",names,key="os_sa"); sb=y.selectbox("Scenario B",names,index=min(1,len(names)-1),key="os_sb")
            if sa!=sb and st.button("Compare Scenarios",use_container_width=True,key="os_scenario_compare"):
                try:
                    comp=scenario_compare(sa,sb); st.dataframe(comp,use_container_width=True,hide_index=True)
                    numeric=comp.dropna(subset=["Delta"])
                    if not numeric.empty: st.plotly_chart(px.bar(numeric,x="KPI",y="Delta",title="Scenario KPI Delta"),use_container_width=True)
                    render_exports("Scenario Git",[("Scenario Comparison",comp)],[],tier,username)
                except Exception as exc: st.error(f"Scenario comparison failed safely: {exc}")

    with tabs[4]:
        st.subheader("🔎 Process Mining & Conformance")
        ev=st.data_editor(st.session_state.setdefault("os_event_log",pd.DataFrame({
            "Case ID":["O1","O1","O1","O2","O2","O2"],"Activity":["Create","Pick","Ship","Create","Pick","Ship"],
            "Timestamp":["2026-09-01 08:00","2026-09-01 09:00","2026-09-01 11:00","2026-09-02 08:30","2026-09-02 10:00","2026-09-02 12:30"]
        })),num_rows="dynamic",use_container_width=True,key="os_event_log_editor")
        expected=st.text_input("Expected sequence","Create,Pick,Ship",key="os_expected_sequence")
        if st.button("Discover Process",type="primary",use_container_width=True,key="os_process_run"):
            try: st.session_state["os_process_result"]=process_mining_discovery(ev,expected_sequence=[x.strip() for x in expected.split(",") if x.strip()])
            except Exception as exc: st.error(f"Process mining failed safely: {exc}")
        r=st.session_state.get("os_process_result")
        if isinstance(r,dict):
            q1,q2,q3,q4=st.columns(4); q1.metric("Cases",r["cases"]); q2.metric("Events",r["event_count"]); q3.metric("Variants",r["variant_count"]); q4.metric("Conformance",f'{r["conformance"]:.1f}%')
            st.dataframe(r["variants"],use_container_width=True,hide_index=True)
            if not r["transitions"].empty:
                tr=r["transitions"].sort_values("Cases",ascending=False).head(20)
                st.plotly_chart(px.bar(tr,x="From",y="Cases",color="To",title="Observed Process Transitions"),use_container_width=True)
                st.dataframe(r["transitions"],use_container_width=True,hide_index=True)
            if not r["mismatches"].empty: st.warning(f"{len(r['mismatches'])} case(s) differ from the expected sequence."); st.dataframe(r["mismatches"],use_container_width=True,hide_index=True)
            render_exports("Process Mining",[("Variants",r["variants"]),("Transitions",r["transitions"]),("Cycle Times",r["cycle_times"]),("Conformance Exceptions",r["mismatches"])],[],tier,username)

    with tabs[5]:
        st.subheader("🧠 Model & Data Drift Monitor")
        ref=st.data_editor(st.session_state.setdefault("os_drift_ref",pd.DataFrame({"FeatureA":np.random.default_rng(20).normal(100,10,100),"FeatureB":["A","B","A","A","C"]*20})),num_rows="dynamic",use_container_width=True,key="os_drift_ref_editor")
        cur=st.data_editor(st.session_state.setdefault("os_drift_cur",pd.DataFrame({"FeatureA":np.random.default_rng(21).normal(108,15,100),"FeatureB":["A","B","C","C","C"]*20})),num_rows="dynamic",use_container_width=True,key="os_drift_cur_editor")
        if st.button("Run Drift Analysis",type="primary",use_container_width=True,key="os_drift_run"):
            try: st.session_state["os_drift_result"]=drift_report(ref,cur)
            except Exception as exc: st.error(f"Drift analysis failed safely: {exc}")
        dr=st.session_state.get("os_drift_result")
        if isinstance(dr,pd.DataFrame) and not dr.empty:
            st.dataframe(dr,use_container_width=True,hide_index=True)
            st.plotly_chart(px.bar(dr,x="Feature",y="Drift Score",color="Type",title="Drift by Feature"),use_container_width=True)
            render_exports("Model Health",[("Drift Report",dr)],[],tier,username)

    with tabs[6]:
        st.subheader("✅ Decision Verification")
        did=st.text_input("Decision ID","DEC-EXAMPLE",key="os_verify_decision_id")
        pred=st.data_editor(st.session_state.setdefault("os_predicted",pd.DataFrame({"Metric":["Cost","Service","Carbon"],"Value":[100,95,80]})),num_rows="dynamic",use_container_width=True,key="os_pred_editor")
        act=st.data_editor(st.session_state.setdefault("os_actual",pd.DataFrame({"Metric":["Cost","Service","Carbon"],"Value":[108,94,83]})),num_rows="dynamic",use_container_width=True,key="os_actual_editor")
        if st.button("Verify Decision",type="primary",use_container_width=True,key="os_verify_run"):
            try: st.session_state["os_verify_result"]=decision_verify(did,pred,act,verified_by=username)
            except Exception as exc: st.error(f"Decision verification failed safely: {exc}")
        vr=st.session_state.get("os_verify_result")
        if isinstance(vr,pd.DataFrame) and not vr.empty:
            st.dataframe(vr,use_container_width=True,hide_index=True)
            nums=vr.dropna(subset=["Percent Error"])
            if not nums.empty: st.plotly_chart(px.bar(nums,x="Metric",y="Percent Error",title="Prediction Error"),use_container_width=True)
            render_exports("Decision Verification",[("Verification",vr)],[],tier,username)

    with tabs[7]:
        st.subheader("🛠️ Continuous Improvement")
        framework=st.radio("Framework",["DMAIC","A3"],horizontal=True,key="os_improvement_framework")
        c1,c2=st.columns(2)
        with c1:
            title=st.text_input("Project title","Reduce packing cycle time",key="os_imp_title")
            owner=st.text_input("Owner",username,key="os_imp_owner")
            phases=["Define","Measure","Analyze","Improve","Control"] if framework=="DMAIC" else ["Problem","Current State","Root Cause","Countermeasure","Follow-up"]
            phase=st.selectbox("Phase",phases,key="os_imp_phase")
        with c2:
            baseline=st.text_area("Baseline JSON",'{"CycleTime":19.2,"OEE":79.5}',key="os_imp_baseline")
            target=st.text_area("Target JSON",'{"CycleTime":17.0,"OEE":85.0}',key="os_imp_target")
        if st.button("Create Improvement Project",type="primary",use_container_width=True,key="os_imp_create"):
            try: st.success(f"Created {improvement_create(title,framework,owner,json.loads(baseline),json.loads(target),phase)}")
            except Exception as exc: st.error(f"Improvement project could not be created safely: {exc}")
        projects=improvement_list()
        st.dataframe(projects,use_container_width=True,hide_index=True)
        if not projects.empty:
            st.info("Use Quality, Lean, Simulation, APS and Economics outputs as evidence for each improvement phase.")

    with tabs[8]:
        st.subheader("🧩 Industrial Template Library")
        choice=st.selectbox("Template",list(TEMPLATE_LIBRARY),key="os_template_choice")
        selected_template=TEMPLATE_LIBRARY[choice]
        st.info(selected_template["description"])
        for label,df in selected_template["tables"].items():
            st.markdown(f"**{label}**"); st.dataframe(df,use_container_width=True,hide_index=True)
        render_exports("Industrial Template — "+choice,[(label,df) for label,df in selected_template["tables"].items()],[],tier,username)

    with tabs[9]:
        st.subheader("🩺 Platform Health & Diagnostics")
        health=platform_health()
        ready=int((health["Status"]=="Ready").sum()); total=len(health)
        st.metric("Runtime readiness",f"{ready}/{total}")
        st.dataframe(health,use_container_width=True,hide_index=True)
        st.caption("These checks verify runtime/database readiness. They do not claim external PLC/ERP connectivity unless that connector has actually been tested.")
        st.plotly_chart(px.bar(health,x="Component",y=health["Status"].eq("Ready").astype(int),title="Component Readiness"),use_container_width=True)
