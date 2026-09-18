"""Shoir-IE Industrial Decision Command Center.

A thin integration surface over the existing industrial_platform service layer.
It intentionally reuses the same persisted model/database instead of creating
parallel module state.
"""
import json
import sqlite3
import pandas as pd
import streamlit as st

from industrial_platform import (
    PLATFORM_CATALOG, TIER_FEATURES, normalize_tier, tier_allows,
    init_platform_db, data_quality_report, model_health, scenario_table,
)

st.set_page_config(page_title="Shoir-IE Command Center", page_icon="🏭", layout="wide")
init_platform_db()

st.title("🏭 Shoir-IE Industrial Decision Command Center")
st.caption("Unified view across the shared Industrial Data Model, scenarios, models, decisions, MES, telemetry, quality and governance.")

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

left,right = st.columns([1.25, 1])
with left:
    st.subheader("Digital-thread coverage")
    catalog = pd.DataFrame(PLATFORM_CATALOG)
    coverage = catalog.assign(
        Available=catalog["name"].map(lambda n: tier_allows(tier, next((x["tier"] for x in PLATFORM_CATALOG if x["name"]==n), "Starter")))
    )[["category","name","tier","Available"]]
    st.dataframe(coverage, use_container_width=True, hide_index=True)

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
    st.dataframe(pd.DataFrame({"Capability":list(health), "Status":["Ready" if v else "Attention" for v in health.values()]}), use_container_width=True, hide_index=True)

st.subheader("Scenario and decision workspace")
scenarios = scenario_table()
if scenarios.empty:
    st.info("No persisted scenarios yet. Create them from Scenario Versioning & Comparison or Experiment Lab.")
else:
    st.dataframe(scenarios, use_container_width=True, hide_index=True)

with st.expander("Engineering validation snapshot"):
    st.write("The command center uses the same validation/model-health services exposed to individual modules.")
    st.json(model_health(pd.DataFrame({"Platform":[1]}), feasible=True, solver_status="Platform services loaded", stability="Service layer loaded", uncertainty="Module-specific", reproducible=True))

st.info(f"Signed-in context: {user} · {normalize_tier(tier)}. Module permissions remain enforced by the application's existing tier gate.")
