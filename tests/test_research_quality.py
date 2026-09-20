import pandas as pd
import numpy as np

from research_quality import (
    audit_code, bootstrap_mean_ci, fit_surrogate, hypothesis_test,
    peer_review_diagnostics, reproducibility_manifest, shock_matrix,
    verify_manifest,
)

def test_hypothesis_test_is_real_and_structured():
    df = pd.DataFrame({"Group":["A"]*5+["B"]*5, "Value":[1,2,3,2,2,4,5,4,5,4]})
    out = hypothesis_test(df, "Independent two-sample t-test", 0.05, "Value", "Group", "A", "B")
    assert {"statistic","p_value","alpha","significant_at_alpha","evidence_status"} <= set(out)
    assert 0 <= out["p_value"] <= 1

def test_bootstrap_ci_is_reproducible():
    a = bootstrap_mean_ci([1,2,3,4,5], resamples=500, seed=7)
    b = bootstrap_mean_ci([1,2,3,4,5], resamples=500, seed=7)
    assert a == b
    assert a["lower"] <= a["mean"] <= a["upper"]

def test_surrogate_has_holdout_metrics():
    x = pd.DataFrame({"x1":np.arange(20), "x2":np.arange(20)**2})
    y = 3*x["x1"] - .1*x["x2"] + 5
    pred, metrics = fit_surrogate(x, y, seed=11)
    assert len(pred) >= 2
    assert metrics["test_rows"] >= 2
    assert "RMSE_test" in metrics

def test_shock_matrix_is_seed_reproducible():
    shocks=[{"Demand":.1},{"Capacity":-.2}]
    a=shock_matrix({"Demand":100,"Capacity":120},shocks,seed=4,noise_pct=2,replications=50)
    b=shock_matrix({"Demand":100,"Capacity":120},shocks,seed=4,noise_pct=2,replications=50)
    pd.testing.assert_frame_equal(a,b)

def test_manifest_verification_and_static_audit():
    payload={"x":1,"seed":"demo"}
    manifest=reproducibility_manifest(payload,seed=3)
    assert verify_manifest(payload,manifest)
    assert not audit_code("import os\nos.system('echo bad')")["safe_for_static_review"]
    assert audit_code("import numpy as np\nprint(1)")["safe_for_static_review"]

def test_peer_review_diagnostics_flags_missing_research_details():
    out=peer_review_diagnostics("We report a method and limitations.", sample_size=None)
    assert "REVIEW" in set(out["Status"])
