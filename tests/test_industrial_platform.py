import sqlite3
import pandas as pd
import pytest

from industrial_platform import (
    init_platform_db, data_quality_report, validate_table, finite_schedule,
    mrp_explode, calculate_oee, spc_limits, capability, fmea_score,
    weibull_analysis, queue_simulation, pareto_frontier, robust_risk_analysis,
    capital_metrics, line_balance, sustainability_accounting, benchmark_compare,
    tier_allows, normalize_tier, PLATFORM_CATALOG,
)

def test_catalog_and_tiers():
    names={x["name"] for x in PLATFORM_CATALOG}
    assert "Advanced Planning & Scheduling" in names
    assert tier_allows("Enterprise Plus Tier", "Enterprise")
    assert tier_allows("Professional Tier", "Mid-Tier Pro")
    assert not tier_allows("Starter Tier", "Enterprise")

def test_db_migration(tmp_path):
    db=tmp_path/"platform.db"
    assert init_platform_db(str(db))
    with sqlite3.connect(db) as c:
        tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
    assert {"industrial_entities","platform_datasets","platform_models","platform_experiments","platform_decisions"} <= tables

def test_validation_and_quality():
    df=pd.DataFrame({"ID":["001","002","002"],"Value":["1,000","2,000","2,000"]})
    q=data_quality_report(df)
    assert q["rows"]==3
    res=validate_table(df,["ID","Value"])
    assert res["valid"] is True
    assert res["quality"]["duplicate_pct"]>0

def test_mrp_and_schedule():
    demand=pd.DataFrame({"Product":["P1"],"DemandQty":[10]})
    bom=pd.DataFrame({"Parent":["P1"],"Component":["C1"],"QtyPer":[2]})
    out=mrp_explode(demand,bom)
    assert out.iloc[0]["Gross Requirement"]==20
    orders=pd.DataFrame({"Order":["O1","O2"],"Product":["P1","P2"],"Qty":[10,20],
                         "DueDate":["2026-09-19","2026-09-20"],"ProcessingMin":[30,40],
                         "SetupMin":[5,5],"Machine":["M1","M1"],"Priority":[2,1]})
    sch=finite_schedule(orders)
    assert len(sch)==2 and sch["Finish"].is_monotonic_increasing

def test_quality_reliability():
    vals=[10,10.1,9.9,10.05,9.95]
    lim=spc_limits(vals)
    cap=capability(vals,9,11)
    assert lim["ucl"]>lim["mean"]>lim["lcl"]
    assert cap["Cpk"]>0
    fmea=fmea_score(pd.DataFrame({"Failure":["A","B"],"Severity":[8,4],"Occurrence":[5,3],"Detection":[2,4]}))
    assert fmea.iloc[0]["RPN"]==80
    w=weibull_analysis([10,20,30,40,50])
    assert w["Shape (Beta)"]>0 and w["Scale (Eta)"]>0

def test_simulation_and_risk():
    sim=queue_simulation(10,20,servers=2,replications=3,duration_min=120)
    assert len(sim)==3
    risk=robust_risk_analysis(100,10,120,7,1,0.1,0.5,simulations=1000)
    assert 0<=risk["Service Probability"]<=1
    assert risk["P95 Exposure"]>=risk["P50 Exposure"]

def test_optimization_and_economics():
    df=pd.DataFrame({"Scenario":["A","B","C"],"Cost":[100,80,120],"Carbon":[50,80,40],"Service":[90,95,98]})
    front=pareto_frontier(df,["Cost","Carbon","Service"],[True,True,False])
    assert len(front)>=1
    risk=robust_risk_analysis(100,5,110,5,1,0,0.5,500)
    assert risk["Stockout Probability"]<1
    metrics=capital_metrics(100,[40,50,60],.1)
    assert "NPV" in metrics and "IRR" in metrics
    bal,meta=line_balance(pd.DataFrame({"Element":["A","B","C"],"TimeMin":[2,2,1]}),3)
    assert meta["Stations"]==2

def test_sustainability_and_benchmarks():
    df=pd.DataFrame({"Activity":["Electricity"],"Scope":["Scope 2"],"Quantity":[1000],"EmissionFactor":[0.42]})
    out=sustainability_accounting(df)
    assert out.iloc[0]["tCO2e"]==0.42
    actual=pd.DataFrame({"Metric":["OEE"],"Actual":[80]})
    bench=pd.DataFrame({"Metric":["OEE"],"Benchmark":[85]})
    comp=benchmark_compare(actual,bench)
    assert comp.iloc[0]["Delta"]==-5
