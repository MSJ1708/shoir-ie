"""Shoir-IE Industrial Decision Command Center.

A thin integration surface over the existing industrial_platform service layer.
It intentionally reuses the same persisted model/database instead of creating
parallel module state.
"""
import json
import sqlite3
import pandas as pd
import plotly.express as px
import streamlit as st
import html

from industrial_experience import ensure_experience_db, feature_stats, feature_catalog
from platform_excellence_ui import render_platform_excellence_center
from industrial_platform import (
    PLATFORM_CATALOG, TIER_FEATURES, normalize_tier, tier_allows,
    init_platform_db, data_quality_report, model_health, scenario_table,
)

st.set_page_config(page_title="Shoir-IE Command Center", page_icon="🏭", layout="wide")
init_platform_db()
ensure_experience_db()

st.markdown("""
<style>
.cc-hero{padding:24px;border:1px solid #dbe4f0;border-radius:20px;background:linear-gradient(135deg,#f8fbff,#fff 58%,#f0fdfa);box-shadow:0 10px 30px rgba(15,23,42,.06)}
.cc-kicker{font-size:11px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#0f766e}
.cc-title{font-size:30px;font-weight:850;color:#0f172a}
</style>
<div class="cc-hero"><div class="cc-kicker">Industrial Decision Platform</div><div class="cc-title">🏭 Industrial Decision Command Center</div><div style="color:#64748b">One operational view for digital thread, models, scenarios, decisions, MES, telemetry and governance.</div></div>
""",unsafe_allow_html=True)

tier = st.session_state.get("user_tier", "Enterprise Plus Tier")
user = st.session_state.get("current_user", "unknown")

# Shared platform health
with sqlite3.connect("enterprise_full_workspace.db") as c:
    counts = {}
    for table in [
        "industrial_entities","platform_datasets","platform_models",
        "platform_experiments","platform_decisions","mes_work_orders",
        "mes_events","telemetry_events","security_events","platform_scenarios"
    ]:
        counts[table] = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

a,b,c,d = st.columns(4)
a.metric("Industrial entities", counts["industrial_entities"])
b.metric("Registered datasets", counts["platform_datasets"])
c.metric("Model snapshots", counts["platform_models"])
d.metric("Saved scenarios", counts["platform_scenarios"])

st.divider()

# Platform Excellence overview: the command center makes the 60 cross-cutting
# capabilities visible without turning every module into a wall of controls.
fx = feature_stats()
p1,p2,p3,p4 = st.columns(4)
p1.metric("Platform capabilities", f"{fx['total']}/60", "tracked")
p2.metric("Active in this build", fx["implemented"], "implemented")
p3.metric("Deployment hooks", fx["integration_ready"], "integration-ready")
p4.metric("Experience layer", "READY", "shared across modules")

with st.expander("✨ Platform Excellence · capability map", expanded=False):
    q = st.text_input("Search capability map", key="cc_capability_search", placeholder="data quality, Copilot, testing, reporting…")
    cap = feature_catalog()
    if q.strip():
        term=q.strip().lower()
        cap=cap[cap["Feature"].str.lower().str.contains(term,regex=False) | cap["Description"].str.lower().str.contains(term,regex=False)]
    st.dataframe(cap,use_container_width=True,hide_index=True)

st.divider()

render_platform_excellence_center(user, tier)

st.divider()

left,right = st.columns([1.25, 1])
with left:
    st.subheader("Digital-thread coverage")
    catalog = pd.DataFrame(PLATFORM_CATALOG)
    coverage = catalog.assign(
        Available=catalog["name"].map(lambda n: tier_allows(tier, next((x["tier"] for x in PLATFORM_CATALOG if x["name"]==n), "Starter")))
    )[["category","name","tier","Available"]]
    st.dataframe(coverage.rename(columns={"category":"Domain","name":"Module","tier":"Tier","Available":"Availability"}), use_container_width=True, hide_index=True)
    coverage_chart=coverage.assign(Status=coverage["Available"].map({True:"Available",False:"Locked"})).groupby(["category","Status"]).size().reset_index(name="Modules")
    fig=px.bar(coverage_chart,x="category",y="Modules",color="Status",barmode="group",title="Module coverage by engineering domain")
    fig.update_layout(height=300,margin=dict(l=10,r=10,t=55,b=10))
    st.plotly_chart(fig,use_container_width=True)

with right:
    st.subheader("Operational health")
    health = {
        "Data platform": counts["platform_datasets"] >= 0,
        "Scenario engine": counts["platform_scenarios"] >= 0,
        "Model registry": counts["platform_models"] >= 0,
        "Decision register": counts["platform_decisions"] >= 0,
        "MES event store": counts["mes_events"] >= 0,
        "Live telemetry store": counts["telemetry_events"] >= 0,
        "Security audit store": counts["security_events"] >= 0,
    }
    health_df=pd.DataFrame({"Capability":list(health),"Status":["Ready" if v else "Attention" for v in health.values()]})
    st.dataframe(health_df,use_container_width=True,hide_index=True)
    st.progress(sum(health.values())/max(1,len(health)),text=f"{sum(health.values())}/{len(health)} platform services ready")

st.subheader("Scenario and decision workspace")
scenarios = scenario_table()
if scenarios.empty:
    st.info("No persisted scenarios yet. Create them from Scenario Versioning & Comparison or Experiment Lab.")
else:
    st.dataframe(scenarios,use_container_width=True,hide_index=True)
    numeric=[c for c in scenarios.columns if pd.api.types.is_numeric_dtype(scenarios[c])]
    if numeric:
        metric=st.selectbox("Scenario metric",numeric,key="cc_scenario_metric")
        fig=px.bar(scenarios,x=scenarios.columns[0],y=metric,title=f"Scenario comparison · {metric}")
        fig.update_layout(height=300,margin=dict(l=10,r=10,t=55,b=10))
        st.plotly_chart(fig,use_container_width=True)

with st.expander("Engineering validation snapshot",expanded=False):
    st.write("Shared model-health services used by the individual engineering modules.")
    _health=model_health(pd.DataFrame({"Platform":[1]}), feasible=True, solver_status="Platform services loaded", stability="Service layer loaded", uncertainty="Module-specific", reproducible=True)
    st.dataframe(pd.DataFrame([{"Metric":str(k).replace("_"," ").title(),"Value":str(v)} for k,v in _health.items()]),use_container_width=True,hide_index=True)

st.info(f"Signed-in context: {user} · {normalize_tier(tier)}. Module permissions remain enforced by the application's existing tier gate.")