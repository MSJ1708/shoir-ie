"""Dedicated, bounded dispatch for nine canonical Workbench targets."""
from __future__ import annotations
import hashlib, json, math, re
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlparse
import pandas as pd
from shoir_tool_registry import TOOL_BY_ID, TOOL_TARGETS, require_tool_access, tier_allows_tool

CANONICAL_TOOL_IDS = ("T001","T003","T008","T053","T057","T064","T088","T090","T093")
_SECRET = ("password","secret","token","api_key","apikey","credential","private_key","access_key","authorization","cookie","session")

def _actor(value: Any) -> str:
    actor = str(value or "").strip()
    if actor.casefold() in {"","guest","guest visitor","anonymous"}:
        raise PermissionError("Sign in with an active Shoir-IE account before running this tool.")
    return actor

def _base(tid: str, actor: str, provenance: str, warning: str) -> dict:
    return {"tool_id":tid,"status":"COMPLETED_WITH_DECLARED_LIMITATIONS","actor":actor,"created_at":datetime.now(timezone.utc).isoformat(),"method_version":"canonical-dispatch-v1","data_provenance":provenance,"warning":warning}

def _parse(value: Any, kind: type, field: str):
    if isinstance(value,str):
        if len(value.encode("utf-8")) > 1_000_000: raise ValueError(f"{field} exceeds 1 MB.")
        try: value=json.loads(value or ("[]" if kind is list else "{}"))
        except json.JSONDecodeError as exc: raise ValueError(f"{field} must be valid JSON.") from exc
    if not isinstance(value,kind): raise ValueError(f"{field} must be a JSON {kind.__name__}.")
    try: json.dumps(value,allow_nan=False)
    except (TypeError,ValueError) as exc: raise ValueError(f"{field} must contain finite JSON values.") from exc
    return value

def _rows(value: Any, field: str, limit: int=1000) -> list[dict]:
    rows=_parse(value,list,field)
    if not 1 <= len(rows) <= limit or any(not isinstance(row,dict) for row in rows): raise ValueError(f"{field} must contain 1 to {limit} JSON objects.")
    return rows

def _obj(value: Any, field: str) -> dict: return _parse(value,dict,field)

def _num(value: Any, field: str, minimum: float|None=None) -> float:
    try: result=float(value)
    except (TypeError,ValueError,OverflowError) as exc: raise ValueError(f"{field} must be a finite number.") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum): raise ValueError(f"{field} must be finite" + (f" and at least {minimum}" if minimum is not None else "") + ".")
    return result

def _utc(value: Any, field: str) -> datetime:
    try: stamp=pd.Timestamp(str(value))
    except Exception as exc: raise ValueError(f"{field} must be a valid ISO-8601 timestamp.") from exc
    if stamp.tzinfo is None: raise ValueError(f"{field} must include a timezone offset or Z.")
    return stamp.tz_convert("UTC").tz_localize(None).to_pydatetime()

def _safe(value: Any, depth: int=0):
    if depth>8: return "[DEPTH_LIMIT]"
    if isinstance(value,Mapping):
        return {str(k):("[REDACTED]" if any(term in str(k).casefold() for term in _SECRET) else _safe(v,depth+1)) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_safe(x,depth+1) for x in list(value)[:5000]]
    if isinstance(value,pd.DataFrame): return {"columns":[str(c) for c in value.columns],"row_count":len(value),"preview":_safe(value.head(50).to_dict("records"),depth+1)}
    if isinstance(value,(datetime,pd.Timestamp)): return value.isoformat()
    if isinstance(value,float) and not math.isfinite(value): return "[NON_FINITE]"
    if value is None or isinstance(value,(str,int,float,bool)): return value
    return str(value)[:1000]

def _t001(p,state,actor):
    rows=[]
    for key,val in state.items():
        m=re.fullmatch(r"shoir_tool_result_(T\d{3})",str(key))
        if m and isinstance(val,dict) and tier_allows_tool(p["tier"],m.group(1)):
            tid=m.group(1); rows.append({"tool_id":tid,"tool_name":TOOL_BY_ID[tid]["canonical_name"],"status":str(val.get("status","RESULT_PRESENT"))[:80],"provenance":str(val.get("data_provenance","NOT_DECLARED"))[:80]})
    rows.sort(key=lambda r:r["tool_id"],reverse=True)
    return {**_base("T001",actor,"SESSION_METADATA_ONLY","Authenticated session summary only; not a live operations dashboard or cross-tenant search."),"workspace":str(state.get("shoir_workspace_name") or state.get("active_workspace_name") or state.get("workspace") or "default")[:120],"available_tool_count":sum(tier_allows_tool(p["tier"],t["tool_id"]) for t in TOOL_TARGETS),"recent_tool_count":len(rows),"recent_tools":pd.DataFrame(rows[:20],columns=["tool_id","tool_name","status","provenance"]),"next_action":"Select a tool whose required inputs and validation evidence are available."}

def _t003(p,state,actor):
    q=str(p.get("query") or "").strip()
    if not 2<=len(q)<=120: raise ValueError("Search phrase must be 2 to 120 characters.")
    found={}
    for t in TOOL_TARGETS:
        if tier_allows_tool(p["tier"],t["tool_id"]) and q.casefold() in " ".join(str(t.get(k) or "") for k in ("tool_id","canonical_name","workbench","existing_module_or_route","calculation_or_action","input_contract","output_contract")).casefold():
            found[("TOOL",t["tool_id"])]={"kind":"TOOL","id":t["tool_id"],"title":t["canonical_name"],"location":t["workbench"],"readiness":t["implementation_status"]}
    for key,val in state.items():
        m=re.fullmatch(r"shoir_tool_result_(T\d{3})",str(key))
        if m and isinstance(val,dict) and tier_allows_tool(p["tier"],m.group(1)):
            tid=m.group(1); t=TOOL_BY_ID[tid]
            if q.casefold() in (tid+" "+t["canonical_name"]+" "+str(val.get("status",""))).casefold():
                found[("RESULT",tid)]={"kind":"CURRENT_SESSION_RESULT","id":tid,"title":t["canonical_name"],"location":"Current session","readiness":str(val.get("status","RESULT_PRESENT"))[:80]}
    frame=pd.DataFrame(list(found.values()),columns=["kind","id","title","location","readiness"])
    return {**_base("T003",actor,"CANONICAL_REGISTRY_AND_CURRENT_SESSION","Search covers permitted tool metadata and current-session result labels only; it does not search private tenant records or external systems."),"query":q,"result_count":len(frame),"results":frame}

def _t008(p,state,actor):
    tid=str(p.get("result_tool_id") or "MANUAL").upper()
    if tid=="MANUAL": record=_obj(p.get("record_json") or "{}","Inspection record")
    else:
        require_tool_access(p["tier"],tid); record=state.get("shoir_tool_result_"+tid)
        if not isinstance(record,dict): raise ValueError(f"No current-session result exists for {tid}; rerun it first.")
    safe=_safe(record); allowed=("formula","method","method_version","units","unit","assumptions","limits","boundary","warning","data_provenance","status","source","source_tool_id","inputs_summary","validation")
    details={k:safe[k] for k in allowed if k in safe}
    expectations={"method/formula":("method","formula"),"units":("units","unit"),"assumptions":("assumptions",),"limits/boundary":("limits","boundary"),"provenance":("data_provenance",)}
    missing=[label for label,keys in expectations.items() if not any(k in details for k in keys)]
    digest=hashlib.sha256(json.dumps(details,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
    return {**_base("T008",actor,"INSPECTED_RESULT_METADATA","Only recorded fields are shown; missing formulas, units, assumptions and limits are disclosed, not inferred or certified."),"source":tid,"details":details,"missing_metadata":missing,"metadata_sha256":digest}

def _t053(p,actor):
    orders=pd.DataFrame(_rows(p.get("orders_json"),"Orders",500))
    required={"Order","Product","Qty","DueDate","ProcessingMin","Machine","SetupMin","Priority","MaterialReady"}
    if required-set(orders.columns): raise ValueError("Orders require: "+", ".join(sorted(required))+".")
    for col in ("Order","Product","Machine"):
        if orders[col].astype(str).str.strip().eq("").any(): raise ValueError(f"{col} cannot be blank.")
    for col in ("Qty","ProcessingMin","SetupMin","Priority"):
        orders[col]=pd.to_numeric(orders[col],errors="coerce")
        if orders[col].isna().any() or not all(math.isfinite(float(v)) for v in orders[col]): raise ValueError(f"{col} must be finite numeric values.")
    if (orders["Qty"]<=0).any() or (orders["ProcessingMin"]<=0).any() or (orders["SetupMin"]<0).any(): raise ValueError("Qty and ProcessingMin must be positive; SetupMin cannot be negative.")
    for col in ("DueDate","MaterialReady"):
        parsed=pd.to_datetime(orders[col].replace("",pd.NA),utc=True,errors="coerce")
        if col=="DueDate" and parsed.isna().any(): raise ValueError("Every DueDate must be a timezone-aware ISO timestamp.")
        orders[col]=parsed.dt.tz_convert(None)
    maint_raw=p.get("maintenance_json") or "[]"
    maint=pd.DataFrame(columns=["Machine","Start","End"]) if isinstance(maint_raw,str) and maint_raw.strip()=="[]" else pd.DataFrame(_rows(maint_raw,"Maintenance windows"))
    if not maint.empty:
        if not {"Machine","Start","End"}.issubset(maint.columns): raise ValueError("Maintenance windows require Machine, Start and End.")
        for col in ("Start","End"): maint[col]=pd.to_datetime(maint[col],utc=True,errors="coerce").dt.tz_convert(None)
        if maint[["Start","End"]].isna().any().any() or (maint["End"]<=maint["Start"]).any(): raise ValueError("Maintenance windows must have valid timezone-aware start/end values.")
    materials={str(k):_num(v,f"Material {k}",0) for k,v in _obj(p.get("materials_json") or "{}","Materials").items()}
    start=_utc(p["start_time_utc"],"Start time") if p.get("start_time_utc") else datetime.now(timezone.utc).replace(tzinfo=None)
    from industrial_platform_excellence import constrained_schedule
    frame,diag=constrained_schedule(orders,maintenance=maint,materials=materials,start_time=start)
    return {**_base("T053",actor,"USER_ENTERED_UNVERIFIED","Priority/earliest-due-date list heuristic, not a globally optimal job-shop solver. Precedence, shifts, labor, tools and full plant calendars are not modeled."),"schedule":frame,"diagnostics":diag,"schedule_method":"priority then earliest due date with machine sequence, setup, material and maintenance inputs","time_basis":"UTC"}

def _t057(p,actor):
    staff=_rows(p.get("staff_json"),"Staff",1000); shifts=_rows(p.get("shifts_json"),"Shifts",1000)
    people={}
    for x in staff:
        sid=str(x.get("staff_id") or "").strip()
        if not sid or sid in people or not isinstance(x.get("skills",[]),list) or not isinstance(x.get("available_shifts",[]),list): raise ValueError("Staff require unique staff_id, skills and available_shifts lists.")
        people[sid]={"skills":set(map(str,x.get("skills",[]))),"available":set(map(str,x.get("available_shifts",[])))}
    if not people: raise ValueError("At least one staff member is required.")
    max_hours=_num(p.get("max_hours_per_person",40),"Maximum hours",0.01); parsed=[]; seen=set()
    for x in shifts:
        sid=str(x.get("shift_id") or "").strip()
        if not sid or sid in seen: raise ValueError("Shifts require unique IDs.")
        seen.add(sid); start=_utc(x.get("start_utc"),sid+" start"); end=_utc(x.get("end_utc"),sid+" end"); req=x.get("required_skills")
        if end<=start or not isinstance(req,dict) or not req: raise ValueError(f"{sid} requires valid times and required_skills.")
        clean={}
        for skill,count in req.items():
            if isinstance(count,bool) or int(count)!=count or int(count)<1: raise ValueError(f"{sid} headcount for {skill} must be a positive integer.")
            clean[str(skill)]=int(count)
        parsed.append((sid,start,end,clean))
    parsed.sort(key=lambda x:x[1]); assigned={sid:[] for sid in people}; hours={sid:0.0 for sid in people}; counts={sid:0 for sid in people}; rows=[]; gaps=[]
    for shift,start,end,req in parsed:
        used=set(); duration=(end-start).total_seconds()/3600
        for skill,n in req.items():
            candidates=[]
            for sid,person in people.items():
                conflict=any(start<old_end and end>old_start for old_start,old_end in assigned[sid])
                if sid not in used and skill in person["skills"] and (not person["available"] or shift in person["available"]) and hours[sid]+duration<=max_hours and not conflict: candidates.append(sid)
            candidates.sort(key=lambda sid:(counts[sid],hours[sid],sid))
            selected=candidates[:n]
            for sid in selected:
                used.add(sid); assigned[sid].append((start,end)); hours[sid]+=duration; counts[sid]+=1
                rows.append({"shift_id":shift,"staff_id":sid,"skill":skill,"start_utc":start.isoformat(),"end_utc":end.isoformat(),"hours":round(duration,3)})
            if len(selected)<n: gaps.append({"shift_id":shift,"skill":skill,"required":n,"filled":len(selected),"unfilled":n-len(selected)})
    return {**_base("T057",actor,"USER_ENTERED_UNVERIFIED","Greedy skill/availability roster only. Does not verify labor law, contracts, fatigue, certifications or attendance."),"assignments":pd.DataFrame(rows),"fairness":pd.DataFrame([{"staff_id":sid,"assigned_shifts":counts[sid],"assigned_hours":round(hours[sid],3)} for sid in sorted(people)]),"unmet_coverage":pd.DataFrame(gaps),"feasible":not gaps,"time_basis":"UTC"}

def _t064(p,actor):
    depot=str(p.get("depot") or "").strip()
    if not depot: raise ValueError("Depot ID is required.")
    stops=_rows(p.get("stops_json"),"Stops",1000); vehicles=_rows(p.get("vehicles_json"),"Vehicles",100); matrix=_rows(p.get("travel_matrix_json"),"Travel matrix",10000)
    sm={}
    for x in stops:
        sid=str(x.get("id") or "").strip()
        if not sid or sid==depot or sid in sm: raise ValueError("Stop IDs must be unique and different from depot.")
        earliest=_num(x.get("earliest_minute",0),sid+" earliest",0); latest=_num(x.get("latest_minute"),sid+" latest",0)
        if latest<earliest: raise ValueError(f"{sid} latest time precedes earliest.")
        sm[sid]={"demand":_num(x.get("demand"),sid+" demand",0),"earliest":earliest,"latest":latest,"service":_num(x.get("service_minutes",0),sid+" service",0)}
    if not sm or not vehicles: raise ValueError("At least one stop and vehicle required.")
    nodes={depot,*sm}; arcs={}
    for x in matrix:
        a,b=str(x.get("from") or "").strip(),str(x.get("to") or "").strip()
        if a not in nodes or b not in nodes or a==b: raise ValueError(f"Invalid travel arc {a}->{b}.")
        arcs[(a,b)]=(_num(x.get("distance"),"Distance",0),_num(x.get("travel_minutes"),"Travel minutes",0))
    missing={(a,b) for a in nodes for b in nodes if a!=b}-set(arcs)
    if missing: raise ValueError(f"Travel matrix is missing {len(missing)} directed arcs.")
    fleet=[]; seen=set()
    for x in vehicles:
        vid=str(x.get("id") or "").strip()
        if not vid or vid in seen: raise ValueError("Vehicle IDs must be unique.")
        seen.add(vid); fleet.append({"id":vid,"capacity":_num(x.get("capacity"),"Capacity",0.000001),"limit":_num(x.get("max_route_minutes"),"Route limit",0.000001)})
    remaining=set(sm); rows=[]; summary=[]
    for v in fleet:
        current=depot; elapsed=distance=load=0.0; seq=0; route=[depot]
        while remaining:
            choices=[]
            for sid in remaining:
                stop=sm[sid]; d,t=arcs[(current,sid)]; arrival=max(elapsed+t,stop["earliest"]); finish=arrival+stop["service"]
                if load+stop["demand"]<=v["capacity"] and arrival<=stop["latest"] and finish+arcs[(sid,depot)][1]<=v["limit"]: choices.append((d,arrival,sid,finish))
            if not choices: break
            d,arrival,sid,finish=min(choices,key=lambda z:(z[0],z[1],z[2])); elapsed=finish; distance+=d; load+=sm[sid]["demand"]; seq+=1; route.append(sid)
            rows.append({"vehicle_id":v["id"],"sequence":seq,"stop_id":sid,"arrival_minute":round(arrival,3),"departure_minute":round(finish,3),"load_after_stop":round(load,3),"travel_distance":d})
            current=sid; remaining.remove(sid)
        if current==depot: back_d,back_t=0.0,0.0
        else: back_d,back_t=arcs[(current,depot)]
        distance+=back_d; elapsed+=back_t; route.append(depot)
        summary.append({"vehicle_id":v["id"],"route":" -> ".join(route),"stops_served":seq,"load":round(load,3),"distance":round(distance,3),"route_minutes":round(elapsed,3),"within_route_limit":elapsed<=v["limit"]})
    return {**_base("T064",actor,"USER_ENTERED_UNVERIFIED","Nearest-feasible-stop heuristic, not an exact/global optimum VRP solver. Distance/time matrix is user entered, not live traffic or verified road routing."),"routes":pd.DataFrame(rows),"vehicle_summary":pd.DataFrame(summary),"unserved_stops":pd.DataFrame([{"stop_id":sid,"reason":"No vehicle satisfies declared capacity, time window and route-duration constraints."} for sid in sorted(remaining)]),"served_stop_count":len(sm)-len(remaining),"unserved_stop_count":len(remaining),"feasible":not remaining,"distance_total":round(sum(x["distance"] for x in summary),3)}

def _t088(p,actor):
    out=[]; seen=set()
    for i,x in enumerate(_rows(p.get("records_json"),"Literature records",3000),1):
        title,claim,method=(str(x.get(k) or "").strip() for k in ("title","claim","method")); source=str(x.get("source") or x.get("doi") or x.get("url") or "").strip()
        if not title or not claim or not method or not source: raise ValueError(f"Literature record {i} needs title, claim, method and source.")
        try: year=int(x.get("year"))
        except (TypeError,ValueError) as exc: raise ValueError(f"Record {i} year is invalid.") from exc
        if not 1800<=year<=2100: raise ValueError(f"Record {i} year must be between 1800 and 2100.")
        doi=bool(re.fullmatch(r"10\.\d{4,9}/\S+",source,re.I)); u=urlparse(source); valid=doi or (u.scheme in {"http","https"} and bool(u.netloc))
        out.append({"citation_id":str(x.get("citation_id") or f"REF-{i:04d}"),"title":title[:500],"authors":str(x.get("authors") or "")[:500],"year":year,"source":source[:1000],"claim":claim[:2000],"method":method[:1000],"evidence_strength":str(x.get("evidence_strength") or "NOT_ASSESSED"),"review_status":str(x.get("review_status") or "NOT_REVIEWED"),"source_status":"FORMAT_VALID_NOT_VERIFIED" if valid else "INVALID_SOURCE_FORMAT","duplicate_source":source.casefold() in seen})
        seen.add(source.casefold())
    frame=pd.DataFrame(out)
    return {**_base("T088",actor,"USER_ENTERED_UNVERIFIED","DOI/URL syntax only; no publisher, registry, paper, peer-review status or scientific claim was verified."),"evidence_matrix":frame,"record_count":len(frame),"format_valid_count":int(frame.source_status.eq("FORMAT_VALID_NOT_VERIFIED").sum()),"invalid_source_count":int(frame.source_status.eq("INVALID_SOURCE_FORMAT").sum()),"duplicate_source_count":int(frame.duplicate_source.sum())}

def _t090(p,actor):
    title,objective,method=(str(p.get(k) or "").strip() for k in ("study_title","objective","method"))
    if not title or not objective or not method or not str(p.get("limitations") or "").strip(): raise ValueError("Title, objective, method and limitations are required.")
    inputs=_safe(_obj(p.get("inputs_json") or "{}","Inputs")); results=_safe(_obj(p.get("results_json") or "{}","Results")); assumptions=_safe(_rows(p.get("assumptions_json"),"Assumptions",200)); sources=_safe(_rows(p.get("sources_json"),"Sources",500)) if p.get("sources_json") else []
    lines=["# "+title[:300],"","Generated UTC: "+datetime.now(timezone.utc).isoformat(),"Method: "+method[:2000],"Method version: "+str(p.get("method_version") or "Not recorded"),"Data provenance: "+str(p.get("data_provenance") or "NOT_DECLARED"),"","## Objective",objective[:5000],"","## Input summary",json.dumps(inputs,ensure_ascii=False,indent=2,default=str),"","## Supplied results",json.dumps(results,ensure_ascii=False,indent=2,default=str),"","## Assumptions"]
    lines += ["- "+str(x.get("assumption") or x.get("description") or x)[:1000] for x in assumptions]
    lines += ["","## Sources (not independently verified)"]+["- "+str(x.get("citation") or x.get("title") or x)[:1000]+" — "+str(x.get("source") or x.get("doi") or x.get("url") or "No locator supplied")[:1000] for x in sources]
    lines += ["","## Limitations",str(p["limitations"])[:10000],"","This builder formats supplied content only. It does not rerun the analysis, validate calculations, retrieve citations, inspect source documents or verify operational outcomes."]
    body="\n".join(lines)
    return {**_base("T090",actor,"USER_SUPPLIED_REPORT_CONTENT","Structured report builder only. It does not generate or verify calculations, citations, figures or peer-review evidence."),"report_markdown":body,"sha256":hashlib.sha256(body.encode()).hexdigest(),"filename":re.sub(r"[^A-Za-z0-9_-]+","-",title).strip("-_")[:70] or "shoir_ie_report","report_bytes":len(body.encode()),"source_count":len(sources)}

def _t093(p,tier,actor):
    steps=_rows(p.get("steps_json"),"Workflow steps",300); by={}
    for x in steps:
        sid,tid=str(x.get("step_id") or "").strip(),str(x.get("tool_id") or "").upper()
        if not sid or sid in by or tid not in TOOL_BY_ID: raise ValueError("Each step needs a unique ID and valid canonical tool ID.")
        deps,inputs,required,outputs=x.get("depends_on",[]),x.get("inputs",{}),x.get("required_inputs",[]),x.get("outputs",{})
        if not isinstance(deps,list) or not isinstance(inputs,dict) or not isinstance(required,list) or not isinstance(outputs,dict): raise ValueError(f"{sid} has an invalid workflow contract.")
        by[sid]={"tool_id":tid,"deps":list(map(str,deps)),"inputs":inputs,"required":list(map(str,required)),"outputs":outputs}
    for sid,x in by.items():
        for dep in x["deps"]:
            if dep not in by: raise ValueError(f"{sid} dependency {dep} does not exist.")
        for name,val in x["inputs"].items():
            if isinstance(val,dict) and "from_step" in val:
                src,out=str(val.get("from_step") or ""),str(val.get("output") or "")
                if src not in x["deps"] or src not in by or out not in by[src]["outputs"]: raise ValueError(f"{sid}.{name} references an undeclared dependency output.")
                typ=str(by[src]["outputs"][out])
                if str(val.get("type") or typ)!=typ or typ not in {"string","number","boolean","array","object"}: raise ValueError(f"{sid}.{name} has an incompatible data type.")
    degree={sid:len(x["deps"]) for sid,x in by.items()}; children={sid:[] for sid in by}
    for sid,x in by.items():
        for dep in x["deps"]: children[dep].append(sid)
    ready=sorted(sid for sid,n in degree.items() if n==0); order=[]
    while ready:
        sid=ready.pop(0); order.append(sid)
        for child in sorted(children[sid]):
            degree[child]-=1
            if degree[child]==0: ready.append(child); ready.sort()
    if len(order)!=len(by): raise ValueError("Workflow dependencies contain a cycle.")
    states={}; out=[]
    for sid in order:
        x=by[sid]; tool=TOOL_BY_ID[x["tool_id"]]; missing=[k for k in x["required"] if k not in x["inputs"]]; blocked=[d for d in x["deps"] if states.get(d)!="READY_FOR_APPROVAL_NOT_VALIDATED"]
        if not tier_allows_tool(tier,x["tool_id"]): current="BLOCKED_TIER"
        elif tool["implementation_status"]=="EXTERNAL_CONFIGURATION_REQUIRED": current="BLOCKED_EXTERNAL_CONFIGURATION"
        elif tool["implementation_status"] in {"MISSING","BLOCKED"}: current="BLOCKED_CAPABILITY"
        elif missing: current="BLOCKED_INPUTS"
        elif blocked: current="BLOCKED_DEPENDENCY"
        else: current="READY_FOR_APPROVAL_NOT_VALIDATED"
        states[sid]=current; out.append({"step_id":sid,"tool_id":x["tool_id"],"tool_name":tool["canonical_name"],"depends_on":", ".join(x["deps"]),"status":current,"missing_inputs":", ".join(missing),"blocked_dependencies":", ".join(blocked),"capability_readiness":tool["implementation_status"],"execution_permitted":False})
    frame=pd.DataFrame(out)
    return {**_base("T093",actor,"USER_DECLARED_WORKFLOW_CONTRACTS","DAG and typed contracts are validated as a plan only; no tools, data transfers, approvals or downstream success are executed or claimed."),"steps":frame,"step_count":len(frame),"ready_for_approval_count":int(frame.status.eq("READY_FOR_APPROVAL_NOT_VALIDATED").sum()),"blocked_step_count":int((~frame.status.eq("READY_FOR_APPROVAL_NOT_VALIDATED")).sum()),"plan_only":True,"requires_approval":True,"execution_permitted":False}

def execute_canonical_tool(tool_id: str,payload: Mapping[str,Any],tier: str,actor: str,session_state: Mapping[str,Any]|None=None)->dict:
    tid=str(tool_id or "").strip().upper()
    if tid not in CANONICAL_TOOL_IDS: raise ValueError("Unsupported canonical dispatcher tool ID.")
    require_tool_access(str(tier),tid); actor=_actor(actor)
    if not isinstance(payload,Mapping): raise ValueError("Inputs must be a structured object.")
    p=dict(payload); p["tier"]=str(tier); state=session_state if isinstance(session_state,Mapping) else {}
    funcs={"T001":lambda:_t001(p,state,actor),"T003":lambda:_t003(p,state,actor),"T008":lambda:_t008(p,state,actor),"T053":lambda:_t053(p,actor),"T057":lambda:_t057(p,actor),"T064":lambda:_t064(p,actor),"T088":lambda:_t088(p,actor),"T090":lambda:_t090(p,actor),"T093":lambda:_t093(p,str(tier),actor)}
    return funcs[tid]()

def _render_result(tid,result):
    import streamlit as st
    for label,key in (("Available tools","available_tool_count"),("Recent tools","recent_tool_count"),("Search results","result_count"),("Literature records","record_count"),("Valid source formats","format_valid_count"),("Invalid source formats","invalid_source_count"),("Served stops","served_stop_count"),("Unserved stops","unserved_stop_count"),("Workflow steps","step_count"),("Ready for approval","ready_for_approval_count"),("Blocked steps","blocked_step_count")):
        if key in result: st.metric(label,result[key])
    if tid=="T090":
        st.download_button("Download research report (Markdown)",result["report_markdown"].encode(),result["filename"]+".md","text/markdown",key="canonical_t090_download")
        st.caption("SHA-256: "+result["sha256"])
        with st.expander("Report preview",expanded=True): st.markdown(result["report_markdown"])
    for key,value in result.items():
        if key in {"tool_id","status","actor","created_at","method_version","data_provenance","warning","report_markdown","filename","sha256"}: continue
        if isinstance(value,pd.DataFrame):
            st.markdown("**"+key.replace("_"," ").title()+"**"); st.dataframe(value,use_container_width=True,hide_index=True)
        elif isinstance(value,(dict,list)):
            st.markdown("**"+key.replace("_"," ").title()+"**"); st.json(_safe(value))
        elif key not in {"report_bytes"}: st.write(key.replace("_"," ").title()+": "+str(value))
    st.warning(str(result.get("warning") or "Review assumptions and limitations."))

def render_canonical_tool(selected_tool,tier,username,require_actor_callback,persist_callback,show_persistence_callback):
    import streamlit as st
    tid=str(selected_tool.get("tool_id") or "").upper(); require_tool_access(str(tier),tid)
    st.markdown("### "+str(selected_tool.get("canonical_name") or tid)); st.caption("Dedicated canonical route. Access is checked again when submitted.")
    p={}
    with st.form("canonical_tool_form_"+tid):
        if tid=="T001": st.info("Summary is built from this authenticated session only.")
        elif tid=="T003": p["query"]=st.text_input("Search tools and current-session results",key="canonical_t003_query")
        elif tid=="T008":
            choices=["MANUAL"]+[str(k).replace("shoir_tool_result_","") for k,v in st.session_state.items() if re.fullmatch(r"shoir_tool_result_T\d{3}",str(k)) and isinstance(v,dict) and tier_allows_tool(str(tier),str(k).replace("shoir_tool_result_",""))]
            p["result_tool_id"]=st.selectbox("Inspect current-session result",choices,key="canonical_t008_source")
            p["record_json"]=st.text_area("Manual method/assumption record JSON",value='{"method":"Replace with actual method","units":"Not supplied","assumptions":[],"limits":[],"data_provenance":"USER_ENTERED_UNVERIFIED"}',key="canonical_t008_record")
        elif tid=="T053":
            p["orders_json"]=st.text_area("Orders JSON",value='[{"Order":"O-001","Product":"P-A","Qty":10,"DueDate":"2026-11-18T16:00:00+03:00","ProcessingMin":60,"Machine":"M-01","SetupMin":10,"Priority":2,"MaterialReady":"2026-11-16T08:00:00+03:00"}]',key="canonical_t053_orders")
            p["maintenance_json"]=st.text_area("Maintenance windows JSON",value="[]",key="canonical_t053_maintenance")
            p["materials_json"]=st.text_area("Available materials JSON",value='{"P-A":10}',key="canonical_t053_materials")
            p["start_time_utc"]=st.text_input("Schedule start UTC",value="2026-11-16T08:00:00Z",key="canonical_t053_start")
        elif tid=="T057":
            p["staff_json"]=st.text_area("Staff JSON",value='[{"staff_id":"EMP-01","skills":["Mechanical"],"available_shifts":["DAY"]},{"staff_id":"EMP-02","skills":["Electrical"],"available_shifts":["DAY"]}]',key="canonical_t057_staff")
            p["shifts_json"]=st.text_area("Shift demand JSON",value='[{"shift_id":"DAY","start_utc":"2026-11-17T06:00:00Z","end_utc":"2026-11-17T14:00:00Z","required_skills":{"Mechanical":1,"Electrical":1}}]',key="canonical_t057_shifts")
            p["max_hours_per_person"]=st.number_input("Maximum declared hours per person",min_value=0.5,max_value=168.0,value=40.0,key="canonical_t057_max_hours")
        elif tid=="T064":
            p["depot"]=st.text_input("Depot ID",value="DEPOT",key="canonical_t064_depot")
            p["stops_json"]=st.text_area("Stops JSON",value='[{"id":"A","demand":4,"earliest_minute":0,"latest_minute":240,"service_minutes":10}]',key="canonical_t064_stops")
            p["vehicles_json"]=st.text_area("Vehicles JSON",value='[{"id":"V-01","capacity":8,"max_route_minutes":360}]',key="canonical_t064_vehicles")
            p["travel_matrix_json"]=st.text_area("Directed matrix JSON for every distinct node pair",value='[{"from":"DEPOT","to":"A","distance":5,"travel_minutes":10},{"from":"A","to":"DEPOT","distance":5,"travel_minutes":10}]',key="canonical_t064_matrix")
        elif tid=="T088":
            p["records_json"]=st.text_area("Literature records JSON",value='[{"title":"Replace with real title","authors":"Author","year":2025,"source":"10.1234/example","claim":"State source claim","method":"Describe method"}]',key="canonical_t088_records")
        elif tid=="T090":
            p["study_title"]=st.text_input("Report title",value="Engineering study report",key="canonical_t090_title")
            p["objective"]=st.text_area("Study objective",key="canonical_t090_objective"); p["method"]=st.text_area("Method used",key="canonical_t090_method")
            p["method_version"]=st.text_input("Method/version",key="canonical_t090_version")
            p["data_provenance"]=st.selectbox("Data provenance",["LIVE","IMPORTED","MANUAL","SYNTHETIC","SIMULATED","NOT_DECLARED"],index=5,key="canonical_t090_provenance")
            p["inputs_json"]=st.text_area("Inputs JSON",value="{}",key="canonical_t090_inputs"); p["results_json"]=st.text_area("Supplied results JSON",value="{}",key="canonical_t090_results")
            p["assumptions_json"]=st.text_area("Assumptions JSON list",value='[{"assumption":"State material assumptions"}]',key="canonical_t090_assumptions")
            p["sources_json"]=st.text_area("Sources JSON list",value="[]",key="canonical_t090_sources"); p["limitations"]=st.text_area("Limitations",value="State what has not been verified.",key="canonical_t090_limits")
        elif tid=="T093":
            p["steps_json"]=st.text_area("Workflow DAG JSON (plan only)",value='[{"step_id":"profile","tool_id":"T011","depends_on":[],"required_inputs":["dataset"],"inputs":{"dataset":{"value":"DS-001","type":"string"}},"outputs":{"profile":"object"}},{"step_id":"quality","tool_id":"T024","depends_on":["profile"],"required_inputs":["profile"],"inputs":{"profile":{"from_step":"profile","output":"profile","type":"object"}},"outputs":{"quality":"object"}}]',key="canonical_t093_steps")
        submitted=st.form_submit_button("Run "+str(selected_tool.get("canonical_name") or tid),type="primary",use_container_width=True,key="canonical_run_"+tid)
    safe_inputs=_safe(p)
    if submitted:
        try:
            require_tool_access(str(tier),tid); actor=require_actor_callback()
            result=execute_canonical_tool(tid,p,tier,actor,st.session_state)
            persist_callback(tid,result,safe_inputs)
            st.success("The method returned a result. Review its limits and save status below.")
        except Exception as exc: st.error("Tool run could not be completed safely: "+str(exc))
    result=st.session_state.get("shoir_tool_result_"+tid)
    if isinstance(result,dict):
        show_persistence_callback(tid,result,safe_inputs); _render_result(tid,result)

__all__=["CANONICAL_TOOL_IDS","execute_canonical_tool","render_canonical_tool"]
