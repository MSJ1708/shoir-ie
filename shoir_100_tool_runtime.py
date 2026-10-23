"""Deterministic engines backing the additive Engineering Tool Library."""
from __future__ import annotations
import csv, hashlib, io, json, math, random
from datetime import datetime, timezone
from statistics import mean, stdev
from typing import Any, Iterable, Mapping, Sequence

def _finite(value: Any, label: str) -> float:
    try: n = float(value)
    except (TypeError, ValueError, OverflowError) as exc: raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(n): raise ValueError(f"{label} must be a finite number.")
    return n

def _positive(value: Any, label: str, *, allow_zero: bool = False) -> float:
    n = _finite(value, label)
    if n < 0 or (n == 0 and not allow_zero): raise ValueError(f"{label} must be {'non-negative' if allow_zero else 'greater than zero'}.")
    return n

def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

def _result(tool_id: str, metrics: Mapping[str, Any], *, units: Mapping[str, str] | None = None,
            method: str, assumptions: Sequence[str] = (), warnings: Sequence[str] = (),
            chart: Sequence[Mapping[str, Any]] = (), tables: Mapping[str, Any] | None = None,
            source_payload: Any = None, provenance: str = "USER_INPUT") -> dict[str, Any]:
    payload = source_payload if source_payload is not None else {"tool_id": tool_id, "metrics": metrics, "units": units or {}}
    return {"tool_id": tool_id, "status": "CALCULATED", "provenance": provenance,
            "metrics": dict(metrics), "units": dict(units or {}), "method": method,
            "assumptions": list(assumptions), "warnings": list(warnings),
            "chart": [dict(x) for x in chart], "tables": dict(tables or {}),
            "source_fingerprint": _fingerprint(payload), "created_at": datetime.now(timezone.utc).isoformat()}

def profile_dataframe(frame: Any) -> dict[str, Any]:
    if frame is None or not hasattr(frame, "columns") or not hasattr(frame, "isna"):
        raise ValueError("Provide a valid tabular dataset before profiling.")
    rows, cols = int(frame.shape[0]), int(frame.shape[1])
    missing_cells = int(frame.isna().sum().sum()) if cols else 0
    duplicate_rows = int(frame.duplicated().sum()) if rows else 0
    details = []
    try:
        import pandas as pd
    except Exception: pd = None
    for name in frame.columns:
        series = frame[name]; missing = int(series.isna().sum())
        numeric = bool(pd.api.types.is_numeric_dtype(series)) if pd is not None else False
        item = {"column": str(name), "dtype": str(series.dtype), "missing_count": missing,
                "missing_percent": round(100*missing/rows, 4) if rows else 0.0,
                "distinct_values": int(series.nunique(dropna=True))}
        if numeric and series.notna().any():
            vals = [float(v) for v in series.dropna().tolist()]
            avg = mean(vals); sd = stdev(vals) if len(vals) > 1 else 0.0
            item.update({"min":min(vals),"max":max(vals),"mean":avg,"sample_std":sd,
                         "possible_outliers_3sd":sum(1 for v in vals if sd > 0 and abs(v-avg)>3*sd)})
        details.append(item)
    cells = rows*cols; warnings = []
    if rows == 0 or cols == 0: warnings.append("The dataset has no rows or no columns; import data before analysis.")
    if cells and missing_cells/cells > .2: warnings.append("More than 20% of cells are missing; investigate source quality before modeling.")
    return _result("T013", {"row_count":rows,"column_count":cols,"duplicate_rows":duplicate_rows,
        "missing_cells":missing_cells,"missing_percent":round(100*missing_cells/cells,4) if cells else 0.0},
        method="Descriptive column profile: data type, missingness, distinct values, numeric range/mean/std and 3-sigma flags.",
        assumptions=["Profiling is descriptive; potential outliers are not automatically errors."], warnings=warnings,
        tables={"columns":details}, source_payload={"columns":[str(x) for x in frame.columns],"values":frame.to_dict(orient="records")},
        provenance="IMPORTED")

def clean_dataframe(frame: Any, *, drop_duplicates: bool = True, missing_strategy: str = "keep") -> tuple[Any, dict[str, Any]]:
    if frame is None or not hasattr(frame, "copy") or not hasattr(frame, "isna"): raise ValueError("Provide a valid tabular dataset before cleaning.")
    if missing_strategy not in {"keep","drop_rows","fill_median"}: raise ValueError("missing_strategy must be keep, drop_rows, or fill_median.")
    candidate=frame.copy(deep=True); original_rows=int(len(candidate)); original_missing=int(candidate.isna().sum().sum())
    removed_duplicates=0
    if drop_duplicates:
        before=len(candidate); candidate=candidate.drop_duplicates().copy(); removed_duplicates=int(before-len(candidate))
    dropped_missing=0; filled_cells=0
    if missing_strategy=="drop_rows":
        before=len(candidate); candidate=candidate.dropna().copy(); dropped_missing=int(before-len(candidate))
    elif missing_strategy=="fill_median":
        try:
            import pandas as pd
            for col in candidate.select_dtypes(include="number").columns:
                count=int(candidate[col].isna().sum())
                if count:
                    med=candidate[col].median()
                    if pd.notna(med): candidate[col]=candidate[col].fillna(med); filled_cells+=count
        except Exception as exc: raise ValueError("Numeric median imputation could not be applied safely.") from exc
    return candidate, {"source_rows":original_rows,"result_rows":int(len(candidate)),
        "removed_duplicate_rows":removed_duplicates,"dropped_missing_rows":dropped_missing,
        "imputed_numeric_cells":filled_cells,"source_missing_cells":original_missing,
        "strategy":missing_strategy,"reversible":True,
        "note":"The source table is unchanged; apply the candidate only after reviewing this audit."}

_UNIT_TO_BASE={"length":{"m":1.0,"cm":.01,"mm":.001,"km":1000.0,"ft":.3048,"in":.0254},
               "mass":{"kg":1.0,"g":.001,"lb":.45359237,"tonne":1000.0},
               "time":{"s":1.0,"min":60.0,"h":3600.0,"day":86400.0}}
def convert_unit(value: Any, source_unit: str, target_unit: str) -> dict[str, Any]:
    n=_finite(value,"value"); src=str(source_unit).strip(); dst=str(target_unit).strip()
    if src in {"°C","°F","K"} and dst in {"°C","°F","K"}:
        k=n+273.15 if src=="°C" else (n-32)*5/9+273.15 if src=="°F" else n
        out=k-273.15 if dst=="°C" else (k-273.15)*9/5+32 if dst=="°F" else k; dimension="temperature"
    else:
        dimension=next((d for d,m in _UNIT_TO_BASE.items() if src in m and dst in m),None)
        if dimension is None: raise ValueError("Unsupported or dimensionally incompatible unit pair; live currency conversion is not available.")
        out=n*_UNIT_TO_BASE[dimension][src]/_UNIT_TO_BASE[dimension][dst]
    return _result("T016",{"input_value":n,"output_value":out},units={"input_value":src,"output_value":dst},
        method=f"Fixed dimensional conversion ({dimension}); no live exchange rates used.",
        assumptions=["Source and target quantities are physically compatible.","Rounding is not applied internally."],
        source_payload={"value":n,"source_unit":src,"target_unit":dst})

def generate_synthetic_industrial_data(rows: int = 100, seed: int = 7) -> dict[str, Any]:
    n=int(rows)
    if n<1 or n>10000: raise ValueError("rows must be between 1 and 10,000.")
    rng=random.Random(int(seed)); records=[]
    for i in range(n):
        total=rng.randint(250,650); good=max(0,min(total,int(round(total*rng.uniform(.93,.995)))))
        records.append({"observation_id":i+1,"station":f"Station-{rng.randint(1,5)}","planned_time_min":480.0,
            "downtime_min":round(rng.uniform(0,45),2),"ideal_cycle_time_min":.5,"total_count":total,"good_count":good,
            "cycle_time_s":round(rng.gauss(54,5),2)})
    return {"tool_id":"T019","status":"SYNTHETIC","provenance":"SYNTHETIC","seed":int(seed),
        "row_count":n,"records":records,"note":"Synthetic practice/test data only; not plant observations.",
        "source_fingerprint":_fingerprint({"seed":int(seed),"rows":n,"records":records})}

def time_study(observed_times: Iterable[Any], rating_percent: Any=100.0, allowance_percent: Any=15.0, unit: str="s") -> dict[str, Any]:
    times=[_positive(x,"observed time") for x in observed_times]
    if not times: raise ValueError("Enter at least one observed time.")
    rating=_positive(rating_percent,"performance rating")/100
    allowance=_finite(allowance_percent,"allowance percent")/100
    if allowance<0 or allowance>=1: raise ValueError("Allowance percent must be at least 0 and less than 100.")
    avg=mean(times); normal=avg*rating; standard=normal/(1-allowance)
    warnings=["Small observation counts may not represent normal operating variation."] if len(times)<10 else []
    return _result("T021",{"observation_count":len(times),"mean_observed_time":avg,"normal_time":normal,"standard_time":standard},
        units={"mean_observed_time":unit,"normal_time":unit,"standard_time":unit},
        method="Normal time = mean observed time × performance rating; standard time = normal time ÷ (1 − allowance fraction).",
        assumptions=["Allowance is expressed as a share of total standard time.","All observations use one consistent time unit."],
        warnings=warnings,chart=[{"metric":"Observed mean","value":avg},{"metric":"Normal time","value":normal},{"metric":"Standard time","value":standard}],
        source_payload={"times":times,"rating_percent":rating_percent,"allowance_percent":allowance_percent,"unit":unit})

def work_sampling(activity_count: Any, total_count: Any, z_value: Any=1.96) -> dict[str, Any]:
    active,total=int(activity_count),int(total_count); z=_positive(z_value,"z value")
    if total<=0 or active<0 or active>total: raise ValueError("Counts must satisfy 0 ≤ activity count ≤ total observations, with total > 0.")
    p=active/total; se=math.sqrt(p*(1-p)/total); low=max(0.0,p-z*se); high=min(1.0,p+z*se); warnings=[]
    if total<30: warnings.append("Sample size is small; the normal-approximation interval may be poor.")
    if p in {0.0,1.0}: warnings.append("A sample proportion of 0 or 1 can understate uncertainty with this interval method.")
    return _result("T022",{"activity_count":active,"sample_size":total,"proportion":p,"ci_low":low,"ci_high":high},
        units={"proportion":"fraction","ci_low":"fraction","ci_high":"fraction"},
        method="Wald normal-approximation interval p ± z√(p(1−p)/n), bounded to [0,1].",
        assumptions=["Observations are independent and sampled under one consistent activity definition."],warnings=warnings,
        chart=[{"metric":"Proportion","value":p},{"metric":"CI lower","value":low},{"metric":"CI upper","value":high}],
        source_payload={"activity_count":active,"total_count":total,"z_value":z})

def takt_capacity(available_time: Any, demand: Any, time_unit: str="min") -> dict[str, Any]:
    t=_positive(available_time,"available time"); d=_positive(demand,"demand"); takt=t/d
    return _result("T023",{"available_time":t,"demand":d,"takt_time":takt,"theoretical_capacity":t/takt},
        units={"available_time":time_unit,"demand":"units per period","takt_time":f"{time_unit}/unit","theoretical_capacity":"units per period"},
        method="Takt time = available production time ÷ required demand; theoretical capacity = available time ÷ takt.",
        assumptions=["Time and demand refer to the same period.","Available time must be defined consistently for planned breaks/losses."],
        source_payload={"available_time":t,"demand":d,"time_unit":time_unit})

def oee(planned_time: Any,downtime: Any,ideal_cycle_time: Any,total_count: Any,good_count: Any,time_unit: str="min") -> dict[str, Any]:
    planned=_positive(planned_time,"planned time"); down=_finite(downtime,"downtime"); ideal=_positive(ideal_cycle_time,"ideal cycle time")
    total,good=int(total_count),int(good_count)
    if down<0 or down>planned: raise ValueError("Downtime must be between zero and planned time.")
    if total<0 or good<0 or good>total: raise ValueError("Counts must satisfy 0 ≤ good count ≤ total count.")
    operating=planned-down
    if operating<=0: raise ValueError("Operating time must be greater than zero.")
    if total<=0: raise ValueError("Total production count must be greater than zero.")
    availability=operating/planned; performance=ideal*total/operating; quality=good/total; combined=availability*performance*quality
    warnings=[]
    if performance>1: warnings.append("Performance exceeds 100%; check ideal cycle time, units, and counts.")
    if good<total: warnings.append(f"{total-good} units are counted as non-good output.")
    return _result("T026",{"planned_time":planned,"downtime":down,"operating_time":operating,"availability":availability,
        "performance":performance,"quality":quality,"oee":combined},
        units={"planned_time":time_unit,"downtime":time_unit,"operating_time":time_unit,"availability":"fraction","performance":"fraction","quality":"fraction","oee":"fraction"},
        method="Availability = operating/planned; performance = ideal cycle × total/operating; quality = good/total; OEE = their product.",
        assumptions=["All time inputs and ideal cycle use the same time unit.","Counts cover the same operating window.","Loss factors are not added together."],
        warnings=warnings,chart=[{"metric":"Availability %","value":100*availability},{"metric":"Performance %","value":100*performance},
        {"metric":"Quality %","value":100*quality},{"metric":"OEE %","value":100*combined}],
        source_payload={"planned_time":planned,"downtime":down,"ideal_cycle_time":ideal,"total_count":total,"good_count":good,"time_unit":time_unit})

def process_capability(observations: Iterable[Any],lsl: Any,usl: Any) -> dict[str, Any]:
    vals=[_finite(x,"observation") for x in observations]; lower,upper=_finite(lsl,"LSL"),_finite(usl,"USL")
    if lower>=upper: raise ValueError("Lower specification limit must be less than upper specification limit.")
    if len(vals)<2: raise ValueError("At least two observations are required to estimate sample standard deviation.")
    sd=stdev(vals)
    if sd<=0: raise ValueError("Observations must have non-zero variation to calculate capability indices.")
    avg=mean(vals); cp=(upper-lower)/(6*sd); cpu=(upper-avg)/(3*sd); cpl=(avg-lower)/(3*sd); cpk=min(cpu,cpl); warnings=[]
    if len(vals)<30: warnings.append("Fewer than 30 observations: assess subgroup, stability and normality assumptions.")
    if avg<lower or avg>upper: warnings.append("Sample mean is outside the specification interval.")
    return _result("T032",{"sample_size":len(vals),"mean":avg,"sample_std":sd,"cp":cp,"cpk":cpk,"pp":cp,"ppk":cpk,"cpu":cpu,"cpl":cpl},
        units={"mean":"input unit","sample_std":"input unit","cp":"index","cpk":"index","pp":"index","ppk":"index","cpu":"index","cpl":"index"},
        method="Cp=(USL−LSL)/(6s); Cpk=min(USL−mean,mean−LSL)/(3s). Pp/Ppk use the same overall sample s here.",
        assumptions=["s is the overall sample standard deviation, not a within-subgroup estimate.","Indices do not prove statistical control or normality."],
        warnings=warnings,chart=[{"metric":"Cp","value":cp},{"metric":"Cpk","value":cpk},{"metric":"Pp","value":cp},{"metric":"Ppk","value":cpk}],
        source_payload={"observations":vals,"lsl":lower,"usl":upper})

def mtbf_mttr(observation_hours: Any,downtime_hours: Any,failures: Any) -> dict[str, Any]:
    period=_positive(observation_hours,"observation hours"); down=_finite(downtime_hours,"downtime hours"); count=int(failures)
    if down<0 or down>period: raise ValueError("Downtime must be between zero and observation hours.")
    if count<0: raise ValueError("Failure count must be non-negative.")
    uptime=period-down; warnings=[]
    if count==0: mtbf=mttr=None; warnings.append("No failures were recorded; MTBF and MTTR are undefined for this window.")
    else: mtbf,mttr=uptime/count,down/count
    return _result("T042",{"observation_hours":period,"downtime_hours":down,"uptime_hours":uptime,"failure_count":count,"mtbf_hours":mtbf,"mttr_hours":mttr},
        units={"observation_hours":"h","downtime_hours":"h","uptime_hours":"h","mtbf_hours":"h","mttr_hours":"h"},
        method="Uptime = observation period − downtime; MTBF = uptime/failure count; MTTR = downtime/failure count.",
        assumptions=["Period, downtime and failures refer to the same asset and observation window.","Censoring and asset-specific schedules are not modeled."],
        warnings=warnings,chart=[{"metric":"MTBF h","value":mtbf},{"metric":"MTTR h","value":mttr}] if count else [],
        source_payload={"observation_hours":period,"downtime_hours":down,"failures":count})

def inventory_policy(annual_demand: Any,order_cost: Any,annual_holding_cost: Any,daily_demand: Any,lead_time_days: Any,
                     *,daily_demand_std: Any=0.0,service_z: Any=0.0,working_days: Any=250) -> dict[str, Any]:
    demand=_positive(annual_demand,"annual demand"); order=_positive(order_cost,"order cost"); hold=_positive(annual_holding_cost,"annual holding cost per unit")
    daily=_positive(daily_demand,"daily demand",allow_zero=True); lead=_positive(lead_time_days,"lead time",allow_zero=True)
    sd=_positive(daily_demand_std,"daily demand standard deviation",allow_zero=True); z=_positive(service_z,"service z value",allow_zero=True); days=_positive(working_days,"working days")
    eoq=math.sqrt(2*demand*order/hold); safety=z*sd*math.sqrt(lead); rop=daily*lead+safety
    return _result("T055",{"eoq_units":eoq,"safety_stock_units":safety,"reorder_point_units":rop,"annual_demand":demand,"assumed_daily_demand_from_annual":demand/days},
        units={"eoq_units":"units","safety_stock_units":"units","reorder_point_units":"units","annual_demand":"units/year"},
        method="EOQ=√(2DS/H); safety stock=z·σdaily·√lead time; reorder point=mean daily demand·lead time+safety stock.",
        assumptions=["Deterministic EOQ with constant costs.","Safety stock assumes independent daily demand and fixed lead time.","MOQ, capacity, expiry and supplier constraints are not modeled."],
        warnings=["Review service-level and lead-time assumptions before use."],
        chart=[{"metric":"EOQ","value":eoq},{"metric":"Safety stock","value":safety},{"metric":"Reorder point","value":rop}],
        source_payload={"annual_demand":demand,"order_cost":order,"annual_holding_cost":hold,"daily_demand":daily,"lead_time_days":lead,"daily_demand_std":sd,"service_z":z,"working_days":days})

def _percentile(values: Sequence[float],p: float) -> float:
    if not values: raise ValueError("Cannot calculate a percentile from an empty sample.")
    pos=(len(values)-1)*p; lo,hi=math.floor(pos),math.ceil(pos)
    return values[lo] if lo==hi else values[lo]*(1-(pos-lo))+values[hi]*(pos-lo)

def monte_carlo_triangular(low: Any,mode: Any,high: Any,iterations: Any=5000,seed: Any=7) -> dict[str, Any]:
    lo,md,hi=_finite(low,"low"),_finite(mode,"mode"),_finite(high,"high"); n,random_seed=int(iterations),int(seed)
    if not lo<=md<=hi or lo==hi: raise ValueError("Bounds must satisfy low ≤ mode ≤ high and low < high.")
    if n<100 or n>100000: raise ValueError("iterations must be between 100 and 100,000.")
    rng=random.Random(random_seed); samples=sorted(rng.triangular(lo,hi,md) for _ in range(n)); avg=sum(samples)/n
    m={"iterations":n,"seed":random_seed,"mean":avg,"p05":_percentile(samples,.05),"p50":_percentile(samples,.5),
       "p95":_percentile(samples,.95),"min":samples[0],"max":samples[-1]}
    return _result("T072",m,method="Independent triangular Monte Carlo sampling with fixed seed and linearly interpolated percentiles.",
        assumptions=["One independent triangular input is modeled.","Input correlations and convergence guarantees are not modeled."],
        warnings=["Compare seeds and replication sizes before treating results as stable."],
        chart=[{"metric":"P05","value":m["p05"]},{"metric":"Median","value":m["p50"]},{"metric":"P95","value":m["p95"]}],
        source_payload={"low":lo,"mode":md,"high":hi,"iterations":n,"seed":random_seed})

def carbon_emissions(activity: Any,factor: Any,*,activity_unit: str,emission_unit: str,factor_source: str="",factor_version: str="",factor_date: str="") -> dict[str, Any]:
    amount=_positive(activity,"activity quantity",allow_zero=True); rate=_positive(factor,"emissions factor",allow_zero=True); warnings=[]
    if not all(str(x).strip() for x in (factor_source,factor_version,factor_date)): warnings.append("Factor source, version and date are incomplete; verify before reporting.")
    emissions=amount*rate
    return _result("T078",{"activity_quantity":amount,"emissions_factor":rate,"estimated_emissions":emissions},
        units={"activity_quantity":activity_unit,"emissions_factor":f"{emission_unit}/{activity_unit}","estimated_emissions":emission_unit},
        method="Estimated emissions = activity quantity × user-supplied factor.",
        assumptions=["Activity and emissions factor cover matching units and system boundaries."],warnings=warnings,
        chart=[{"metric":"Activity","value":amount},{"metric":"Estimated emissions","value":emissions}],
        source_payload={"activity":amount,"factor":rate,"activity_unit":activity_unit,"emission_unit":emission_unit,"factor_source":factor_source,"factor_version":factor_version,"factor_date":factor_date},
        provenance="IMPORTED" if all(str(x).strip() for x in (factor_source,factor_version,factor_date)) else "USER_INPUT")

def engineering_economics(cash_flows: Iterable[Any],discount_rate_percent: Any) -> dict[str, Any]:
    flows=[_finite(x,f"cash flow at period {i}") for i,x in enumerate(cash_flows)]; pct=_finite(discount_rate_percent,"discount rate"); rate=pct/100
    if not flows: raise ValueError("Enter cash flows; first value is period 0.")
    if rate<=-1: raise ValueError("Discount rate must be greater than -100%.")
    discounted=[cf/((1+rate)**i) for i,cf in enumerate(flows)]; npv=sum(discounted); payback=None; cumulative=discounted[0]
    for period in range(1,len(discounted)):
        previous=cumulative; cumulative+=discounted[period]
        if previous<0<=cumulative and discounted[period]>0: payback=(period-1)+(-previous/discounted[period]); break
    candidates=[math.exp(math.log(.001)+i*(math.log(101)-math.log(.001))/1000)-1 for i in range(1001)]
    roots=[]; pr=candidates[0]; pv=sum(cf/((1+pr)**i) for i,cf in enumerate(flows))
    for r in candidates[1:]:
        v=sum(cf/((1+r)**i) for i,cf in enumerate(flows))
        if pv==0: roots.append((pr,pr))
        elif v==0 or (pv<0<v) or (v<0<pv): roots.append((pr,r))
        pr,pv=r,v
    irr=None; warnings=[]
    if len(roots)==1:
        lo,hi=roots[0]
        if lo==hi: irr=lo
        else:
            flo=sum(cf/((1+lo)**i) for i,cf in enumerate(flows))
            for _ in range(100):
                mid=(lo+hi)/2; fm=sum(cf/((1+mid)**i) for i,cf in enumerate(flows))
                if abs(fm)<1e-10: lo=hi=mid; break
                if (flo<0<fm) or (fm<0<flo): hi=mid
                else: lo,flo=mid,fm
            irr=(lo+hi)/2
    else: warnings.append("IRR unavailable: no unique NPV sign-change root was bracketed in the supported search range.")
    if payback is None: warnings.append("Discounted payback is not reached within supplied cash-flow periods.")
    return _result("T081",{"npv":npv,"irr_percent":100*irr if irr is not None else None,"discounted_payback_period":payback},
        units={"npv":"currency units at period-0 valuation","irr_percent":"%","discounted_payback_period":"periods"},
        method="NPV=ΣCFₜ/(1+r)ᵗ; IRR is reported only for a unique bracketed NPV root; discounted payback is interpolated.",
        assumptions=["Cash-flow index 0 is today; equal intervals and one currency are assumed.","IRR may be undefined or non-unique."],
        warnings=warnings,chart=[{"metric":"NPV","value":npv}],source_payload={"cash_flows":flows,"discount_rate_percent":pct})

def read_dataset_bytes(filename: str,payload: bytes,*,max_bytes: int=25*1024*1024) -> Any:
    if not isinstance(payload,(bytes,bytearray)) or not payload: raise ValueError("The uploaded file is empty.")
    if len(payload)>max_bytes: raise ValueError(f"File exceeds the configured {max_bytes//(1024*1024)} MiB limit.")
    try:
        import pandas as pd
        lower=str(filename or "").lower()
        if lower.endswith(".csv"):
            try: return pd.read_csv(io.BytesIO(payload))
            except UnicodeDecodeError: return pd.read_csv(io.BytesIO(payload),encoding="utf-8-sig")
        if lower.endswith((".xlsx",".xls")): return pd.read_excel(io.BytesIO(payload),sheet_name=None)
    except Exception as exc: raise ValueError("File could not be parsed as supported CSV/Excel; existing dataset has not been changed.") from exc
    raise ValueError("Unsupported file type. Upload CSV, XLSX, or XLS.")

def result_to_csv_bytes(result: Mapping[str, Any]) -> bytes:
    required={"tool_id","status","metrics","units","method","source_fingerprint"}
    if not required.issubset(result): raise ValueError("Result is missing required metadata and cannot be exported.")
    out=io.StringIO(newline=""); writer=csv.writer(out)
    writer.writerow(["tool_id","status","provenance","metric","value","unit","method","source_fingerprint","created_at"])
    for key,value in (result.get("metrics") or {}).items():
        writer.writerow([result["tool_id"],result["status"],result.get("provenance","USER_INPUT"),key,value,
            (result.get("units") or {}).get(key,""),result["method"],result["source_fingerprint"],result.get("created_at","")])
    return out.getvalue().encode("utf-8-sig")
