import pandas as pd
import numpy as np

from industrial_platform_excellence import (
    canonical_tier, tier_allows, deep_data_quality, validate_schema, validate_units,
    referential_integrity, constrained_schedule, control_chart, proportion_chart,
    capability_extended, gage_rr_extended, doe_2level_effects, reliability_summary,
    simulation_statistics, warmup_diagnostic, bbox_collision_check, flow_distance,
    pareto_frontier_v2, robust_scenarios, economics_sensitivity, workforce_scenario,
    sustainability_scenario, benchmark_gap, copilot_execution_plan,
    connector_validation, model_version, result_health
)

def test_tiers_and_matrix():
    assert canonical_tier("Starter Tier") == "Starter"
    assert canonical_tier("Professional Tier ($129)") == "Professional"
    assert canonical_tier("Enterprise Plus Tier ($399)") == "Enterprise Plus"
    assert tier_allows("Enterprise Plus Tier", "Enterprise")
    assert tier_allows("Research Pack", "Enterprise Plus")
    assert not tier_allows("Starter", "Enterprise")

def test_validation():
    df=pd.DataFrame({"ID":["A","B","B"],"Value":[1,2,np.nan]})
    q=deep_data_quality(df)
    assert q["rows"]==3 and q["score"]<100
    res=validate_schema(df,required=["ID","Value"],unique=[])
    assert res["valid"] is True
    units=validate_units({"mass":"kg","bad":"widgets"})
    assert not units["valid"] and units["unknown"]["bad"]=="widgets"
    ref=referential_integrity(pd.DataFrame({"Supplier":["S1","S2"]}),"Supplier",pd.DataFrame({"ID":["S1"]}),"ID")
    assert ref["missing_count"]==1

def test_schedule_and_quality():
    orders=pd.DataFrame({
        "Order":["O1","O2"],
        "Product":["P1","P2"],
        "Qty":[10,20],
        "DueDate":["2026-09-20","2026-09-21"],
        "ProcessingMin":[30,40],
        "SetupMin":[5,5],
        "Machine":["M1","M1"],
        "Priority":[2,1],
        "MaterialReady":["2026-09-19","2026-09-19"],
    })
    maint=pd.DataFrame({"Machine":["M1"],"Start":["2026-09-19 00:20"],"End":["2026-09-19 01:00"]})
    sch,diag=constrained_schedule(orders,maint,{"M1":8},{"P1":10,"P2":20},{("P1","P2"):12},pd.Timestamp("2026-09-19 00:00").to_pydatetime())
    assert len(sch)==2 and diag["feasible"]
    spc=control_chart([10,10.1,9.9,10.0,10.05,10.02])
    assert "OutOfControl" in spc.columns
    cap=capability_extended([9.9,10.0,10.1,10.05,9.95],9,11,10)
    assert cap["Cpk"]>0
    rr=gage_rr_extended(pd.DataFrame({"Part":[1,1,2,2],"Operator":["A","B","A","B"],"Measurement":[10,10.1,11,10.9]}))
    assert rr["%GRR"]>=0

def test_experiments_layout_and_risk():
    doe=doe_2level_effects(pd.DataFrame({"A":[-1,-1,1,1],"B":[-1,1,-1,1],"Response":[10,12,14,16]}),"Response",["A","B"])
    assert not doe.empty
    rel=reliability_summary([10,20,30,40,50])
    assert rel["Beta"]>0 and rel["Eta"]>0
    sim=simulation_statistics(pd.DataFrame({"Metric":[10,11,12,9,10]}),"Metric")
    assert sim["CI95 Lower"] <= sim["Mean"] <= sim["CI95 Upper"]
    warm=warmup_diagnostic([1,1,1,1,2,2,2,2,2,2,2,2],3)
    assert warm["recommended_cutoff"]>=0
    layout=pd.DataFrame({"Asset":["A","B"],"X":[0,0.5],"Y":[0,0.5],"Length":[2,2],"Width":[2,2]})
    assert len(bbox_collision_check(layout))==1
    flow=flow_distance(pd.DataFrame({"Asset":["A","B","C"],"X":[0,3,6],"Y":[0,0,4]}),["A","B","C"])
    assert abs(flow["Total Distance"]-(3+5))<1e-9

def test_decision_and_governance_helpers():
    df=pd.DataFrame({"Scenario":["A","B","C"],"Cost":[100,80,120],"Carbon":[50,80,40],"Service":[90,95,98]})
    pareto=pareto_frontier_v2(df,["Cost","Carbon","Service"],[True,True,False])
    assert len(pareto)>=1
    robust=robust_scenarios({},pd.DataFrame({"Scenario":["Base"],"Demand Mean":[100],"Demand Std":[10],"Capacity":[120],"Disruption Probability":[.1],"Disruption Multiplier":[.6]}),1000)
    assert 0<=robust.iloc[0]["Service Probability"]<=1
    econ=economics_sensitivity(100,[40,50], [.08,.1],[.9,1.0])
    assert len(econ)==4 and "NPV" in econ
    workforce=workforce_scenario(10,480,85,5,2,25)
    assert workforce["Effective Staff"]<10
    lca=sustainability_scenario(pd.DataFrame({"Activity":["Electricity"],"Scope":["Scope 2"],"Quantity":[1000],"EmissionFactor":[.42]}))
    assert abs(lca["total_tCO2e"]-.42)<1e-9
    bench=benchmark_gap(pd.DataFrame({"Metric":["OEE"],"Actual":[80]}),pd.DataFrame({"Metric":["OEE"],"Benchmark":[85]}))
    assert bench.iloc[0]["Delta"]==-5
    plan=copilot_execution_plan("forecast demand and prepare an executive report")
    assert len(plan["steps"])>=2 and plan["approval_required"]
    con=connector_validation("Plant","MQTT","mqtts://broker.example")
    assert con["valid"]
    assert model_version([])=="1.0.0"
    assert result_health(pd.DataFrame({"x":[1,2,3]}),True,"OPTIMAL","95% CI")["Feasibility"]=="Pass"
