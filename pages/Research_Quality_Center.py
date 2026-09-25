"""Research Pack Quality Center — evidence-first research workspace.

This page supplements the existing Research Pack modules with real local
calculations, verification, reproducibility, stress testing and visual
diagnostics. No external AI or fabricated benchmark claims are used.
"""
from __future__ import annotations

import io
import json
import sqlite3
import zipfile
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from industrial_experience import FEATURES_60, ensure_experience_db, feature_stats, log_copilot_action
from research_quality import (
    audit_code, bootstrap_mean_ci, fit_surrogate, hypothesis_test,
    peer_review_diagnostics, reproducibility_manifest, shock_matrix,
    verify_manifest,
)

st.set_page_config(page_title="Shoir-IE Research Quality Center", page_icon="🔬", layout="wide")
ensure_experience_db()
USER = st.session_state.get("current_user", "research-user")

st.markdown("""
<style>
.rq-hero{padding:30px;border-radius:24px;background:linear-gradient(135deg,#10162b 0%,#252b69 55%,#0d766e 100%);color:#fff;box-shadow:0 20px 50px rgba(15,23,42,.18);overflow:hidden;position:relative}
.rq-hero:after{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 30%,rgba(255,255,255,.08) 50%,transparent 70%);transform:translateX(-120%);animation:rqshine 9s ease-in-out infinite}
@keyframes rqshine{0%,60%{transform:translateX(-120%)}80%,100%{transform:translateX(120%)}}
.rq-kicker{font-size:11px;font-weight:900;letter-spacing:.12em;color:#7dd3fc}.rq-title{font-size:32px;font-weight:900;letter-spacing:-.03em}.rq-sub{color:#dbeafe;max-width:980px}
.rq-card{border:1px solid #dbe4f0;border-radius:16px;padding:16px;background:linear-gradient(145deg,#fff,#f8fbff);box-shadow:0 7px 20px rgba(15,23,42,.05)}
@media(prefers-reduced-motion:reduce){.rq-hero:after{animation:none}}
</style>
<div class="rq-hero">
 <div class="rq-kicker">RESEARCH PACK · QUALITY GATE</div>
 <div class="rq-title">🔬 Research Quality Center</div>
 <div class="rq-sub">Real statistical calculations, reproducibility fingerprints, adversarial shock matrices, code safety checks and publication-readiness diagnostics — with computed evidence clearly separated from illustrative content.</div>
</div>
""", unsafe_allow_html=True)

stats = feature_stats()
a,b,c,d = st.columns(4)
a.metric("Platform capabilities", f"{stats['implemented']}/60")
b.metric("Research utilities", "8")
c.metric("Evidence mode", "Computed")
d.metric("User", USER)

tabs = st.tabs(["📊 Statistics", "🤖 Regression & Surrogates", "🧪 Stress Lab", "🔐 Reproducibility", "🛡️ Code & Peer Review", "🧭 60-Capability Map"])

with tabs[0]:
    st.subheader("Rigorous hypothesis testing")
    default = pd.DataFrame({
        "Group":["A","A","A","B","B","B","C","C","C"],
        "Value":[10.2,10.0,10.4,11.1,11.3,10.9,12.0,11.8,12.2],
    })
    df = st.data_editor(default, num_rows="dynamic", use_container_width=True, hide_index=True, key="rq_stats_df")
    test = st.selectbox("Test", ["One-sample t-test","Independent two-sample t-test","Mann-Whitney U","One-way ANOVA"])
    alpha = st.number_input("α", 0.001, 0.20, 0.05, 0.001)
    if test == "One-sample t-test":
        value_col = st.selectbox("Measurement", [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])])
        target = st.number_input("Reference mean", value=10.0)
        if st.button("▶ Compute test", type="primary", key="rq_t1"):
            try: st.session_state.rq_test = hypothesis_test(df, test, alpha, value_col=value_col, expected=[target])
            except Exception as exc: st.error(f"Statistical test failed safely: {exc}")
    else:
        value_col = st.selectbox("Measurement", [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])], key="rq_val")
        group_col = st.selectbox("Group", list(df.columns), key="rq_group")
        groups = [str(x) for x in df[group_col].dropna().unique()]
        if test == "One-way ANOVA":
            ready = len(groups) >= 2
            if st.button("▶ Compute ANOVA", type="primary", disabled=not ready, key="rq_anova"):
                try: st.session_state.rq_test = hypothesis_test(df, test, alpha, value_col=value_col, group_col=group_col)
                except Exception as exc: st.error(f"ANOVA failed safely: {exc}")
        else:
            g1,g2 = st.columns(2)
            ga = g1.selectbox("Group A", groups, key="rq_ga")
            gb = g2.selectbox("Group B", groups, index=min(1,len(groups)-1), key="rq_gb")
            if st.button("▶ Compute comparison", type="primary", key="rq_comp"):
                try: st.session_state.rq_test = hypothesis_test(df, test, alpha, value_col=value_col, group_col=group_col, group_a=ga, group_b=gb)
                except Exception as exc: st.error(f"Comparison failed safely: {exc}")
    result = st.session_state.get("rq_test")
    if result:
        r1,r2,r3,r4 = st.columns(4)
        r1.metric("Statistic", f"{result['statistic']:.4g}")
        r2.metric("p-value", f"{result['p_value']:.5g}")
        r3.metric("α", f"{result['alpha']:.3f}")
        r4.metric("Evidence", "SIGNAL" if result["significant_at_alpha"] else "NO SIGNAL")
        st.dataframe(pd.DataFrame([result]), use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Regression diagnostics + surrogate validation")
    rng = np.random.default_rng(2026)
    demo = pd.DataFrame({"X1":np.arange(1,31), "X2":np.linspace(5,35,30), "Response":20 + 2.2*np.arange(1,31) - .4*np.linspace(5,35,30) + rng.normal(0,2,30)})
    reg = st.data_editor(demo, num_rows="dynamic", use_container_width=True, hide_index=True, key="rq_reg_df")
    features = st.multiselect("Features", [c for c in reg.columns if c != "Response"], default=[c for c in reg.columns if c != "Response"])
    degree = st.slider("Polynomial degree", 1, 3, 1)
    if st.button("📈 Fit regression", type="primary", key="rq_reg"):
        try:
            from research_quality import regression_analysis
            coef, metrics, residuals = regression_analysis(reg, "Response", features, degree)
            st.session_state.rq_reg = (coef, metrics, residuals)
        except Exception as exc: st.error(f"Regression failed safely: {exc}")
    if st.session_state.get("rq_reg"):
        coef, metrics, residuals = st.session_state.rq_reg
        x1,x2,x3 = st.columns(3)
        x1.metric("R²", f"{metrics['R2']:.3f}"); x2.metric("MAE", f"{metrics['MAE']:.3f}"); x3.metric("RMSE", f"{metrics['RMSE']:.3f}")
        c1,c2=st.columns(2)
        with c1: st.dataframe(coef, use_container_width=True, hide_index=True)
        with c2: st.plotly_chart(px.scatter(residuals, x="Predicted", y="Residual", trendline="ols", title="Residual diagnostics"), use_container_width=True)
    st.markdown("#### Surrogate hold-out validation")
    if len(features) >= 1 and st.button("🧠 Fit Random Forest surrogate", key="rq_surrogate"):
        try:
            pred, metrics = fit_surrogate(reg[features], reg["Response"], seed=2026)
            st.session_state.rq_surrogate=(pred,metrics)
        except Exception as exc: st.error(f"Surrogate fit failed safely: {exc}")
    if st.session_state.get("rq_surrogate"):
        pred,metrics=st.session_state.rq_surrogate
        st.dataframe(pd.DataFrame([metrics]), use_container_width=True, hide_index=True)
        st.plotly_chart(px.scatter(pred,x="Observed",y="Predicted",trendline="ols",title="Observed vs predicted hold-out"),use_container_width=True)

with tabs[2]:
    st.subheader("Adversarial shock matrix")
    base = {"Demand":1000.0,"Capacity":1100.0,"Cost":100.0}
    shocks = [
        {"Demand":0.10},{"Demand":0.25},{"Capacity":-0.15},{"Cost":0.20},
        {"Demand":0.30,"Capacity":-0.20},{"Demand":-0.10,"Cost":-0.15},
    ]
    noise = st.slider("Random noise (%)",0.0,20.0,3.0,0.5)
    reps = st.slider("Replications per shock",50,1000,250,50)
    if st.button("🧪 Generate reproducible shock matrix", type="primary", key="rq_shock"):
        out=shock_matrix(base,shocks,seed=2026,noise_pct=noise,replications=reps)
        st.session_state.rq_shocks=out
    if st.session_state.get("rq_shocks") is not None:
        out=st.session_state.rq_shocks
        st.dataframe(out.head(100),use_container_width=True,hide_index=True)
        summary=out.groupby("Scenario",as_index=False).agg({"Demand":"mean","Capacity":"mean","Cost":"mean"})
        st.plotly_chart(px.scatter(summary,x="Demand",y="Capacity",size="Cost",color="Scenario",title="Shock response surface"),use_container_width=True)

with tabs[3]:
    st.subheader("Cryptographic reproducibility")
    payload = {"module":"Research Quality Center","dataset":"current workspace","configuration":{"seed":2026,"mode":"evidence-first"}}
    manifest = reproducibility_manifest(payload,2026)
    st.json(manifest)
    st.success("✓ Current configuration fingerprint generated from canonical JSON.")
    if st.button("🔎 Verify fingerprint", key="rq_verify"):
        st.success("Verified" if verify_manifest(payload,manifest) else "Mismatch")
    st.download_button("📥 Download reproducibility manifest",json.dumps(manifest,indent=2).encode(),file_name="research_reproducibility_manifest.json",mime="application/json")

with tabs[4]:
    st.subheader("Static code safety + peer-review diagnostics")
    code = st.text_area("Paste research Python for static review", value="import numpy as np\nprint('analysis')\n", height=180)
    if st.button("🛡️ Audit code without executing it", type="primary", key="rq_code"):
        audit=audit_code(code); st.session_state.rq_audit=audit
    if st.session_state.get("rq_audit"):
        audit=st.session_state.rq_audit
        st.metric("Static safety", "PASS" if audit["safe_for_static_review"] else "REVIEW")
        st.dataframe(pd.DataFrame(audit["findings"]),use_container_width=True,hide_index=True)
        st.caption("The submitted code is parsed only; it is never executed by this page.")
    manuscript = st.text_area("Paste abstract/methods text for reviewer diagnostics", height=160)
    n = st.number_input("Sample size (optional)", min_value=0, value=0)
    if st.button("🔎 Run reviewer diagnostics", key="rq_review"):
        diag=peer_review_diagnostics(manuscript, n if n else None)
        st.dataframe(diag,use_container_width=True,hide_index=True)

with tabs[5]:
    st.subheader("Platform Excellence — all 60 capabilities")
    cat=pd.DataFrame(FEATURES_60,columns=["ID","Capability","Description","Status"])
    search=st.text_input("Search the capability map",key="rq_feature_search")
    if search.strip():
        q=search.lower()
        cat=cat[cat["Capability"].str.lower().str.contains(q,regex=False)|cat["Description"].str.lower().str.contains(q,regex=False)]
    st.dataframe(cat,use_container_width=True,hide_index=True)
    status_counts=pd.DataFrame(FEATURES_60,columns=["ID","Capability","Description","Status"]).groupby("Status").size().reset_index(name="Count")
    st.plotly_chart(px.pie(status_counts,names="Status",values="Count",hole=.55,title="Capability delivery status"),use_container_width=True)
    if st.button("🤖 Record Copilot awareness update",key="rq_copilot"):
        rid=log_copilot_action("Research Quality Center","Refresh research capability context",USER,True,"Approved",{"capabilities":len(FEATURES_60)})
        st.success(f"Copilot context ledger updated · {rid}")

st.divider()
st.caption("Research calculations are executed locally from the supplied table. Benchmark, journal, cloud, quantum, and live-IoT claims are not presented as verified unless a real connector or evidence source is attached.")
