"""Shoir-IE Full Industrial Governance Layer.

Evidence-backed, framework-light services shared by specialist modules.
The layer does not mark a capability verified merely because a UI exists.
"""
from __future__ import annotations
import ast, hashlib, json, math, re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from itertools import product
from typing import Any, Callable, Iterable, Mapping, Sequence
import numpy as np
import pandas as pd

WORKFLOW_STAGES = ("DATA","VALIDATE","MAP","MODEL","RUN","VISUALIZE","COMPARE","EXPLAIN","DECIDE","EXPORT","VERIFY")
ACTION_LEVELS = ("READ","ANALYZE","SIMULATE","RECOMMEND","PREPARE","EXECUTE","ADMIN")
LINEAGE_RELATIONS = ("USES","CONSUMES","AFFECTS","HAS","MONITORED_BY","ANALYZED_BY","PART_OF","INFLUENCES","DERIVED_FROM","VERIFIED_BY")

def utc_now() -> str: return datetime.now(timezone.utc).isoformat()
def stable_hash(value: Any) -> str: return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,separators=(",",":")).encode()).hexdigest()

@dataclass
class VerificationRecord:
    capability: str
    status: str = "PARTIAL"
    coverage: float = 0.0
    test_coverage: float = 0.0
    verified_at: str = ""
    verifier: str = ""
    dependencies: list[str] = field(default_factory=list)
    deployment_requirements: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    notes: str = ""
    def verify(self, *, verifier: str, evidence: Sequence[str], test_coverage: float = 1.0):
        self.status="VERIFIED"; self.coverage=1.0; self.test_coverage=max(0,min(1,float(test_coverage))); self.verified_at=utc_now(); self.verifier=verifier; self.evidence=list(evidence); return self

@dataclass
class ModuleManifest:
    module_id: str
    name: str
    version: str = "1.0"
    owner: str = "Shoir-IE"
    stages: tuple[str,...] = WORKFLOW_STAGES
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=lambda:list(ACTION_LEVELS))
    verification: VerificationRecord|None = None
    execution_entrypoint: str = ""
    replayable: bool = False
    def validate(self):
        errors=[]
        if tuple(self.stages)!=WORKFLOW_STAGES: errors.append("module must expose all universal workflow stages")
        errors += [f"unknown action levels: {sorted(set(self.actions)-set(ACTION_LEVELS))}"] if set(self.actions)-set(ACTION_LEVELS) else []
        if not self.execution_entrypoint: errors.append("execution_entrypoint is required")
        return errors

class WorkflowContract:
    def __init__(self,manifest:ModuleManifest): self.manifest=manifest; self.state={s:None for s in WORKFLOW_STAGES}; self.completed=[]
    def complete(self,stage,payload=None):
        if stage not in WORKFLOW_STAGES: raise ValueError(f"Unknown workflow stage: {stage}")
        expected=WORKFLOW_STAGES[len(self.completed)]
        if stage!=expected: raise RuntimeError(f"Workflow order violation: expected {expected}, received {stage}")
        self.state[stage]=payload; self.completed.append(stage); return payload
    @property
    def ready_to_verify(self): return tuple(self.completed)==WORKFLOW_STAGES[:-1]
    def snapshot(self): return {"manifest":asdict(self.manifest),"state":self.state,"completed":self.completed}

class CapabilityLedger:
    def __init__(self,capabilities:Iterable[str]=()): self.records={c:VerificationRecord(c) for c in capabilities}
    def register(self,capability,**kwargs):
        rec=self.records.setdefault(capability,VerificationRecord(capability))
        for k,v in kwargs.items():
            if hasattr(rec,k): setattr(rec,k,v)
        return rec
    def verify(self,capability,*,verifier,evidence,test_coverage=1.0): return self.records.setdefault(capability,VerificationRecord(capability)).verify(verifier=verifier,evidence=evidence,test_coverage=test_coverage)
    def dataframe(self): return pd.DataFrame([asdict(v) for v in self.records.values()])
    def summary(self):
        if not self.records:return {}
        return {str(k):int(v) for k,v in self.dataframe()["status"].value_counts().to_dict().items()}

class DigitalLineage:
    def __init__(self): self.nodes={}; self.edges=[]
    def node(self,node_id,node_type,**attrs): self.nodes[node_id]={"id":node_id,"type":node_type,**attrs}; return self.nodes[node_id]
    def edge(self,source,relation,target,**attrs):
        if relation not in LINEAGE_RELATIONS: raise ValueError(f"Unsupported lineage relation: {relation}")
        edge={"source":source,"relation":relation,"target":target,**attrs}; self.edges.append(edge); return edge
    def trace(self,node_id,max_depth=20):
        seen={node_id}; frontier=[node_id]; result=[]
        for _ in range(max_depth):
            nxt=[]
            for e in self.edges:
                if e["source"] in frontier and e["target"] not in seen: result.append(e); seen.add(e["target"]); nxt.append(e["target"])
            if not nxt: break
            frontier=nxt
        return result
    def explain(self,node_id): return {"node":self.nodes.get(node_id),"lineage":self.trace(node_id)}

@dataclass
class UncertaintyEnvelope:
    estimate: float; samples:int; mean:float; std:float; p05:float; p50:float; p95:float; lower:float; upper:float; probability_of_constraint_violation:float|None=None

def uncertainty_envelope(samples,*,lower_q=.05,upper_q=.95,constraint=None,greater_is_violation=True):
    a=np.asarray(samples,dtype=float)
    if a.size==0 or not np.isfinite(a).all(): raise ValueError("samples must contain finite numeric values")
    violation=None if constraint is None else float(np.mean(a>constraint) if greater_is_violation else np.mean(a<constraint))
    return UncertaintyEnvelope(float(a.mean()),int(a.size),float(a.mean()),float(a.std(ddof=1)) if a.size>1 else 0,float(np.quantile(a,.05)),float(np.quantile(a,.5)),float(np.quantile(a,.95)),float(np.quantile(a,lower_q)),float(np.quantile(a,upper_q)),violation)

def monte_carlo(simulator:Callable,*,n=1000,seed=2026,constraint=None,greater_is_violation=True):
    if n<2: raise ValueError("n must be >= 2")
    rng=np.random.default_rng(seed); return uncertainty_envelope([float(simulator(rng)) for _ in range(n)],constraint=constraint,greater_is_violation=greater_is_violation)

def bootstrap_mean(values,*,n=2000,seed=2026):
    x=np.asarray(values,dtype=float)
    if x.size<2: raise ValueError("bootstrap requires at least two observations")
    rng=np.random.default_rng(seed); return uncertainty_envelope(rng.choice(x,size=(n,x.size),replace=True).mean(axis=1))

def sensitivity(values:Mapping[str,float],baseline:float):
    rows=[]
    for name,value in values.items():
        delta=float(value)-float(baseline); rows.append({"factor":name,"value":float(value),"delta":delta,"absolute_effect":abs(delta),"relative_effect":delta/baseline if baseline else math.nan})
    return pd.DataFrame(rows).sort_values("absolute_effect",ascending=False,ignore_index=True)

def factorial_design(factors:Mapping[str,Sequence[Any]],*,fraction=None):
    if not factors: raise ValueError("at least one factor is required")
    names=list(factors); rows=list(product(*(list(factors[k]) for k in names)))
    if fraction:
        m=re.fullmatch(r"1/(\d+)",fraction)
        if not m or int(m.group(1))<1: raise ValueError("fraction must look like 1/2, 1/4, ...")
        rows=rows[::int(m.group(1))]
    return pd.DataFrame(rows,columns=names).assign(Run=lambda d:np.arange(1,len(d)+1))

def response_surface_design(factors:Mapping[str,Sequence[float]],center_reps=5):
    names=list(factors)
    if not names or any(len(v)<2 for v in factors.values()): raise ValueError("response surface requires numeric factors with at least two levels")
    levels={k:(float(min(v)),float(max(v))) for k,v in factors.items()}; rows=[]
    for point in product([-1.,1.],repeat=len(names)): rows.append({k:levels[k][0] if c<0 else levels[k][1] for k,c in zip(names,point)})
    for k in names:
        for c in (-1.41421356237,1.41421356237):
            row={n:(levels[n][0]+levels[n][1])/2 for n in names}; row[k]+=(levels[k][1]-levels[k][0])/2*c; rows.append(row)
    center={k:(levels[k][0]+levels[k][1])/2 for k in names}; rows.extend([center.copy() for _ in range(max(1,center_reps))])
    return pd.DataFrame(rows).assign(Run=lambda d:np.arange(1,len(d)+1))

def replication_plan(runs,replications,seed=2026):
    if runs<1 or replications<1: raise ValueError("runs and replications must be positive")
    rng=np.random.default_rng(seed); rows=[{"run":r,"replication":rep,"seed":int(rng.integers(0,2**31-1))} for r in range(1,runs+1) for rep in range(1,replications+1)]
    return pd.DataFrame(rows).sample(frac=1,random_state=seed).reset_index(drop=True)

def scenario_compare(baseline,scenarios):
    rows=[]
    for name,values in scenarios.items():
        row={"scenario":name}
        for key in sorted(set(baseline)|set(values)):
            b,v=float(baseline.get(key,np.nan)),float(values.get(key,np.nan)); row[f"{key}_baseline"]=b; row[f"{key}_value"]=v; row[f"{key}_delta"]=v-b if np.isfinite(b) and np.isfinite(v) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)

def constraint_violations(metrics,constraints):
    rows=[]
    for key,rule in constraints.items():
        value=float(metrics.get(key,np.nan))
        if "max" in rule:
            limit=float(rule["max"]); rows.append({"metric":key,"value":value,"constraint":"max","limit":limit,"violated":value>limit,"margin":limit-value})
        if "min" in rule:
            limit=float(rule["min"]); rows.append({"metric":key,"value":value,"constraint":"min","limit":limit,"violated":value<limit,"margin":value-limit})
    return pd.DataFrame(rows)

UNIT_FACTORS={"m":1.,"km":1000.,"mm":.001,"s":1.,"min":60.,"h":3600.,"kg":1.,"g":.001,"t":1000.,"W":1.,"kW":1000.,"MW":1000000.}
UNIT_DIMENSIONS={"m":"length","km":"length","mm":"length","s":"time","min":"time","h":"time","kg":"mass","g":"mass","t":"mass","W":"power","kW":"power","MW":"power"}
def convert_unit(value,from_unit,to_unit):
    if from_unit not in UNIT_FACTORS or to_unit not in UNIT_FACTORS: raise ValueError("Unsupported unit")
    if UNIT_DIMENSIONS[from_unit]!=UNIT_DIMENSIONS[to_unit]: raise ValueError("Incompatible dimensions")
    return float(value)*UNIT_FACTORS[from_unit]/UNIT_FACTORS[to_unit]
def validate_quantity(value,unit,minimum=None,maximum=None):
    if unit not in UNIT_FACTORS: raise ValueError(f"Unknown unit: {unit}")
    if minimum is not None and value<minimum: raise ValueError("quantity below allowed range")
    if maximum is not None and value>maximum: raise ValueError("quantity above allowed range")
    return {"value":float(value),"unit":unit,"dimension":UNIT_DIMENSIONS[unit]}

def optimization_diagnostics(*,objective,feasible,status,gap=None,runtime_s=None,iterations=None,binding_constraints=(),shadow_prices=None):
    return {"objective":float(objective),"feasible":bool(feasible),"status":status,"optimality_gap":None if gap is None else float(gap),"runtime_s":runtime_s,"iterations":iterations,"binding_constraints":list(binding_constraints),"shadow_prices":dict(shadow_prices or {})}

def rolling_forecast(values,horizon=1,window=7):
    x=pd.Series(values,dtype=float)
    if len(x)<max(2,window): raise ValueError("not enough observations for forecast window")
    mean=float(x.tail(window).mean()); sigma=float(x.tail(window).std(ddof=1)) if len(x.tail(window))>1 else 0
    return pd.DataFrame([{"horizon":h,"forecast":mean,"lower_95":mean-1.96*sigma,"upper_95":mean+1.96*sigma} for h in range(1,horizon+1)])

def backtest_forecast(values,window=7,horizon=1):
    x=np.asarray(values,dtype=float)
    if len(x)<=window+horizon: raise ValueError("not enough observations for backtest")
    actual=[];pred=[]
    for i in range(window,len(x)-horizon+1): pred.append(float(np.mean(x[i-window:i]))); actual.append(float(x[i]))
    a,p=np.asarray(actual),np.asarray(pred); denom=np.where(np.abs(a)<1e-12,np.nan,np.abs(a))
    return {"MAE":float(np.mean(np.abs(a-p))),"RMSE":float(np.sqrt(np.mean((a-p)**2))),"MAPE_percent":float(np.nanmean(np.abs((a-p)/denom))*100),"observations":float(len(a))}

def replay_manifest(*,module_id,run_id,dataset_hash,parameters,seed,code_version,environment=None):
    payload={"manifest_version":"2.0","run_id":run_id,"module_id":module_id,"dataset_hash":dataset_hash,"parameters":dict(parameters),"seed":seed,"code_version":code_version,"environment":dict(environment or {}),"created_at":utc_now()}
    payload["manifest_hash"]=stable_hash(payload); return payload

def decision_memory_key(problem): return stable_hash({k:problem[k] for k in sorted(problem)})
def find_similar_decisions(problem,decisions,limit=10):
    target={str(k):str(v).lower() for k,v in problem.items()}; scored=[]
    for d in decisions:
        fields={str(k):str(v).lower() for k,v in d.items()}; overlap=sum(1 for k,v in target.items() if k in fields and fields[k]==v); scored.append((overlap,d))
    scored.sort(key=lambda x:x[0],reverse=True); return [dict(d,similarity_score=s) for s,d in scored[:limit]]
def benchmark_record(metric,observed,reference,unit="",source=""):
    delta=observed-reference; return {"metric":metric,"observed":observed,"reference":reference,"delta":delta,"relative_delta":delta/reference if reference else math.nan,"unit":unit,"source":source,"version":"1"}
def accessibility_contract(component): return {"component":component,"keyboard":True,"focus_order":True,"screen_reader_label":True,"reduced_motion":True,"high_contrast":True,"rtl":True,"status":"REQUIRED"}
def report_actions(): return ("Expand","Filter","Compare","Explain","Export","Add to Report")

def safe_numeric_expression(expression,names):
    tree=ast.parse(expression,mode="eval"); allowed=(ast.Expression,ast.BinOp,ast.UnaryOp,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow,ast.Mod,ast.USub,ast.UAdd,ast.Constant,ast.Name,ast.Load,ast.FloorDiv)
    for node in ast.walk(tree):
        if not isinstance(node,allowed): raise ValueError("expression contains a prohibited operation")
        if isinstance(node,ast.Name) and node.id not in names: raise ValueError(f"unknown variable: {node.id}")
        if isinstance(node,ast.Constant) and not isinstance(node.value,(int,float)): raise ValueError("only numeric constants are allowed")
    return float(eval(compile(tree,"<engineering-expression>","eval"),{"__builtins__":{}},dict(names)))

def build_module_manifest(module_id,name,*,entrypoint,capabilities=(),replayable=True): return ModuleManifest(module_id,module_id if not name else name,execution_entrypoint=entrypoint,capabilities=list(capabilities),replayable=replayable)
def universal_module_report(manifest,capability_ledger=None):
    return {"module":asdict(manifest),"contract_valid":not manifest.validate(),"ledger":capability_ledger.summary() if capability_ledger else {},"required_stages":list(WORKFLOW_STAGES),"required_actions":list(ACTION_LEVELS),"visual_actions":list(report_actions()),"accessibility":accessibility_contract(manifest.module_id)}
