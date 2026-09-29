import pytest
import numpy as np
from shoir_full_governance import (
    WORKFLOW_STAGES, ModuleManifest, WorkflowContract, CapabilityLedger,
    DigitalLineage, uncertainty_envelope, factorial_design,
    response_surface_design, replication_plan, scenario_compare,
    constraint_violations, convert_unit, rolling_forecast, backtest_forecast,
    replay_manifest, safe_numeric_expression,
)

def test_workflow_contract_is_strict_and_complete():
    manifest = ModuleManifest("demo", "Demo", execution_entrypoint="demo.run")
    assert manifest.validate() == []
    c = WorkflowContract(manifest)
    for stage in WORKFLOW_STAGES[:-1]: c.complete(stage, {"ok": True})
    assert c.ready_to_verify
    c.complete("VERIFY", {"ok": True})
    assert c.completed == list(WORKFLOW_STAGES)

def test_capability_ledger_never_fakes_verification():
    ledger = CapabilityLedger(["Universal Workflow"])
    assert ledger.summary()["PARTIAL"] == 1
    ledger.verify("Universal Workflow", verifier="CI", evidence=["tests/test_full_governance.py"], test_coverage=1.0)
    assert ledger.summary()["VERIFIED"] == 1

def test_lineage_trace():
    g = DigitalLineage()
    for node, typ in [("dataset","Dataset"),("model","Model"),("kpi","KPI"),("decision","Decision")]: g.node(node,typ)
    g.edge("dataset","DERIVED_FROM","model")
    g.edge("model","ANALYZED_BY","kpi")
    g.edge("kpi","INFLUENCES","decision")
    assert len(g.trace("dataset")) == 3

def test_uncertainty_and_constraint_probability():
    env = uncertainty_envelope(np.arange(1, 101), constraint=80)
    assert env.p50 == 50.5
    assert env.probability_of_constraint_violation == 0.2

def test_doe_and_replication():
    d = factorial_design({"A":[-1,1],"B":[-1,1]})
    assert len(d) == 4
    f = factorial_design({"A":[-1,1],"B":[-1,1],"C":[-1,1]}, fraction="1/2")
    assert len(f) == 4
    r = response_surface_design({"A":[0,10],"B":[0,20]}, center_reps=3)
    assert len(r) == 11
    p = replication_plan(3, 4)
    assert len(p) == 12 and p["seed"].is_unique

def test_scenarios_constraints_units():
    out = scenario_compare({"cost":100,"throughput":10},{"stress":{"cost":120,"throughput":8}})
    assert float(out.loc[0,"cost_delta"]) == 20
    violations = constraint_violations({"cost":120,"service":.92},{"cost":{"max":100},"service":{"min":.95}})
    assert violations["violated"].tolist() == [True, True]
    assert convert_unit(1,"km","m") == 1000
    with pytest.raises(ValueError): convert_unit(1,"kg","m")

def test_forecast_and_replay():
    x = list(range(1,31))
    f = rolling_forecast(x,horizon=3,window=7)
    assert len(f) == 3 and f["forecast"].iloc[0] == 27
    metrics = backtest_forecast(x,window=5)
    assert metrics["MAE"] >= 0
    manifest = replay_manifest(module_id="forecast",run_id="r1",dataset_hash="abc",parameters={"window":5},seed=2026,code_version="test")
    assert manifest["manifest_hash"]

def test_safe_expression_blocks_code_execution():
    assert safe_numeric_expression("a * 2 + b", {"a":3,"b":4}) == 10
    with pytest.raises(ValueError): safe_numeric_expression("__import__('os').system('id')", {})
