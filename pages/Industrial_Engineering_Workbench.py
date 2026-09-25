"""Unified Shoir-IE Engineering Workbench.

The workbench is the user-facing shell for the common industrial platform.
It reuses the established industrial_platform module implementations and the
new excellence layer, with one consistent workflow for data, validation,
execution, scenarios, health, governance and downloads.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import html

from industrial_platform import render_module, PLATFORM_CATALOG, init_platform_db
from industrial_platform_excellence import (
    CANONICAL_TIERS, MODULE_MATRIX, canonical_tier, tier_allows, tier_matrix,
    module_matrix, module_availability, deep_data_quality, validate_schema,
    validate_units, referential_integrity, constrained_schedule, control_chart,
    proportion_chart, capability_extended, gage_rr_extended, doe_2level_effects,
    reliability_summary, simulation_statistics, warmup_diagnostic,
    bbox_collision_check, flow_distance, pareto_frontier_v2, robust_scenarios,
    economics_sensitivity, workforce_scenario, sustainability_scenario,
    benchmark_gap, build_decision_card, save_decision, record_approval,
    permission_check, connector_validation, copilot_execution_plan,
    reproducibility_manifest, result_health, export_manifest_tables,
    audit_event, ensure_excellence_db,
)

st.set_page_config(page_title="Shoir-IE | Unified Engineering Workbench", page_icon="🏭", layout="wide")
init_platform_db()
ensure_excellence_db()

USER = st.session_state.get("current_user","guest")
RAW_TIER = st.session_state.get("user_tier","Enterprise Plus Tier")
TIER = canonical_tier(RAW_TIER)

st.markdown("""
<style>
.workbench-hero{padding:22px 24px;border:1px solid #dbe4f0;border-radius:18px;background:linear-gradient(135deg,#f8fbff,#ffffff 58%,#f0fdfa);box-shadow:0 10px 30px rgba(15,23,42,.06);margin-bottom:18px}
.workbench-kicker{font-size:11px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:#0f766e}
.workbench-hero h1{margin:4px 0 4px;font-size:31px;color:#0f172a}
.workbench-hero p{margin:0;color:#64748b}
.result-card{padding:15px 17px;border:1px solid #dbeafe;border-radius:15px;background:#fff;box-shadow:0 5px 18px rgba(15,23,42,.04)}
.action-row{margin-top:10px}
</style>
<div class="workbench-hero">
  <div class="workbench-kicker">Industrial Decision Platform</div>
  <h1>🏭 Shoir-IE Engineering Command Center</h1>
  <p>Validate → Analyze → Visualize → Decide → Export. Technical details stay available without cluttering the engineering result.</p>
</div>
""",unsafe_allow_html=True)

# Header health/status strip
h1,h2,h3,h4,h5 = st.columns(5)
h1.metric("User", USER)
h2.metric("Tier", TIER)
h3.metric("Modules", len(MODULE_MATRIX))
with sqlite3.connect("enterprise_full_workspace.db") as c:
    ds_count = c.execute("SELECT COUNT(*) FROM platform_datasets").fetchone()[0]
    model_count = c.execute("SELECT COUNT(*) FROM platform_models").fetchone()[0]
h4.metric("Datasets", ds_count)
h5.metric("Models", model_count)

st.divider()

def render_engineering_result(value, title="Analysis result", key_prefix="result"):
    """Render structured results as readable KPIs/tables/charts, not raw JSON."""
    st.markdown(f"### {title}")
    if isinstance(value, dict):
        scalar={k:v for k,v in value.items() if not isinstance(v,(dict,list,pd.DataFrame,np.ndarray))}
        frames={k:v for k,v in value.items() if isinstance(v,pd.DataFrame)}
        nested={k:v for k,v in value.items() if isinstance(v,(dict,list))}
        if scalar:
            cols=st.columns(min(4,max(1,len(scalar))))
            for i,(k,v) in enumerate(scalar.items()):
                label=str(k).replace("_"," ").title()
                display=f"{v:,.3f}" if isinstance(v,(float,np.floating)) else f"{v:,}" if isinstance(v,(int,np.integer)) else str(v)
                cols[i%len(cols)].metric(label,display)
        for k,df in frames.items():
            st.markdown(f"**{str(k).replace('_',' ').title()}**")
            st.dataframe(df,use_container_width=True,hide_index=True)
            _render_result_chart(df,f"{str(k).replace('_',' ').title()} chart",f"{key_prefix}_{k}")
        if nested:
            with st.expander("🔎 Detailed diagnostics",expanded=False):
                for k,v in nested.items():
                    st.markdown(f"**{str(k).replace('_',' ').title()}**")
                    if isinstance(v,(dict,list)):
                        st.dataframe(pd.json_normalize(v) if isinstance(v,list) else pd.DataFrame([v]),use_container_width=True,hide_index=True)
        return
    if isinstance(value,pd.DataFrame):
        st.dataframe(value,use_container_width=True,hide_index=True)
        _render_result_chart(value,title+" chart",key_prefix)
        return
    st.write(value)

def _render_result_chart(df,title,key_prefix):
    if not isinstance(df,pd.DataFrame) or df.empty:
        return
    numeric=[c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if not numeric:
        return
    y=st.selectbox("Chart metric",numeric,key=f"{key_prefix}_metric")
    x_candidates=[c for c in df.columns if c != y]
    x=st.selectbox("X-axis / category",x_candidates,key=f"{key_prefix}_x") if x_candidates else None
    chart=st.selectbox("Visualization",["Bar","Line","Scatter"],key=f"{key_prefix}_type")
    plot=df[[x,y]].dropna() if x else df[[y]].dropna()
    if plot.empty: return
    if chart=="Line" and x: fig=px.line(plot,x=x,y=y,markers=True,title=title)
    elif chart=="Scatter" and x: fig=px.scatter(plot,x=x,y=y,title=title)
    else: fig=px.bar(plot,x=x,y=y,title=title) if x else px.bar(plot,y=y,title=title)
    fig.update_layout(height=340,margin=dict(l=10,r=10,t=55,b=10))
    st.plotly_chart(fig,use_container_width=True)

# Sidebar navigation
st.sidebar.header("Workbench")
search = st.sidebar.text_input("🔎 Search modules", "")
category = st.sidebar.selectbox("Category", ["All"] + sorted({x[0] for x in MODULE_MATRIX}))
available = module_availability(RAW_TIER)
filtered = available.copy()
if category != "All":
    filtered = filtered[filtered["Category"] == category]
if search.strip():
    q=search.strip().lower()
    filtered=filtered[filtered["Module"].str.lower().str.contains(q, regex=False)]

labels = filtered["Module"].tolist()
if not labels:
    st.sidebar.warning("No modules match the current filter.")
    selected = "Engineering Validation Center"
else:
    _module_rows = {row["Module"]: row for _, row in filtered.iterrows()}
    _display_labels = [
        f"{_module_rows[m]['Category']} · {m}" for m in labels
    ]
    _display_to_module = dict(zip(_display_labels, labels))
    _selected_display = st.sidebar.selectbox("Module", _display_labels, key="workbench_module_selector")
    selected = _display_to_module[_selected_display]
    _selected_row = _module_rows[selected]
    st.sidebar.markdown(
        f"""<div class="result-card">
        <div style="font-size:10px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#0f766e">{html.escape(str(_selected_row['Category']))}</div>
        <div style="font-size:15px;font-weight:800;margin-top:4px;color:#0f172a">{html.escape(str(selected))}</div>
        <div style="font-size:11px;color:#64748b;margin-top:4px">Required tier: {html.escape(str(required)) if 'required' in locals() else 'Configured'}</div>
        </div>""",
        unsafe_allow_html=True,
    )

required = next((x[2] for x in MODULE_MATRIX if x[1] == selected), "Starter")
if not tier_allows(RAW_TIER, required):
    st.warning(f"🔒 {selected} requires the {required} capability level. Your current tier maps to {TIER}.")
    st.dataframe(available[["Category","Module","Required Tier","Available"]], use_container_width=True, hide_index=True)
    st.stop()

# New cross-cutting platform controls
top1,top2,top3,top4 = st.columns(4)
with top1:
    if st.button("📥 Import / Validate", use_container_width=True):
        st.session_state["show_exchange"]=True
with top2:
    if st.button("🧪 Scenario Lab", use_container_width=True):
        st.session_state["show_scenario"]=True
with top3:
    if st.button("🩺 Model Health", use_container_width=True):
        st.session_state["show_health"]=True
with top4:
    if st.button("📋 Decision Card", use_container_width=True):
        st.session_state["show_decision"]=True

# Specialized upgraded surfaces
if selected == "Engineering Validation Center":
    st.subheader("🔎 Engineering Validation Center")
    st.caption("Validate schema, missingness, duplicates, types, units, ranges and cross-table references before running engineering logic.")
    source = st.session_state.get("workbench_df", pd.DataFrame({
        "ID":["A-001","A-002","A-002","A-004"],
        "Value":[10,11,np.nan,999],
        "Unit":["units","units","units","units"],
    }))
    edited = st.data_editor(source, num_rows="dynamic", use_container_width=True, key="wb_validation_editor")
    a,b,c = st.columns(3)
    with a:
        required_cols = st.multiselect("Required columns", list(edited.columns), default=[edited.columns[0]] if len(edited.columns) else [])
    with b:
        unique_cols = st.multiselect("Unique columns", list(edited.columns), default=[])
    with c:
        unit = st.text_input("Primary unit", "units")
    if st.button("🔎 Run Full Validation", type="primary", use_container_width=True):
        schema=validate_schema(edited,required_cols,unique_cols)
        units=validate_units({"Primary":unit})
        st.session_state["wb_validation_result"]={"schema":schema,"units":units}
        audit_event(USER,"validation_run",{"module":selected,"fingerprint":deep_data_quality(edited)["fingerprint"]})
    res=st.session_state.get("wb_validation_result")
    if res:
        m1,m2,m3=st.columns(3)
        m1.metric("Data quality",f"{res['schema']['quality']['score']:.1f}%")
        m2.metric("Validation", "PASS" if res["schema"]["valid"] and res["units"]["valid"] else "ATTENTION")
        m3.metric("Rows", len(edited))
        render_engineering_result(res,"Validation result","validation_result")
    st.dataframe(edited,use_container_width=True)

elif selected == "Industrial Data Model & Digital Thread":
    st.subheader("🔗 Industrial Digital Thread")
    tab1,tab2,tab3 = st.tabs(["Entities","Relationships","Impact Analysis"])
    with tab1:
        entities=st.data_editor(st.session_state.get("wb_entities",pd.DataFrame({
            "ID":["FAC-001","MCH-001","SKU-001","SUP-001"],
            "Name":["Riyadh DC","CNC-01","SKU-A","Supplier A"],
            "Type":["Facility","Machine","SKU","Supplier"],
        })),num_rows="dynamic",use_container_width=True,key="wb_entities_editor")
        st.session_state["wb_entities"]=entities
        entity_type=st.selectbox("Entity type",sorted(entities["Type"].dropna().astype(str).unique()) if "Type" in entities.columns else ["Facility"])
        if st.button("🔗 Sync Entity Records",type="primary",use_container_width=True):
            from industrial_platform import upsert_entities
            count=upsert_entities(entities.rename(columns={"ID":"EntityID"}),"IndustrialEntity","EntityID")
            st.success(f"Synchronized {count:,} entities into the shared digital-thread store.")
    with tab2:
        rel=st.data_editor(st.session_state.get("wb_relationships",pd.DataFrame({
            "From":["FAC-001","FAC-001","MCH-001"],
            "Relationship":["contains","ships","produces"],
            "To":["MCH-001","SKU-001","SKU-001"],
        })),num_rows="dynamic",use_container_width=True,key="wb_relationship_editor")
        st.session_state["wb_relationships"]=rel
        if st.button("🔗 Persist Relationships",type="primary",use_container_width=True):
            from industrial_platform_excellence import upsert_relationships
            st.success(f"Saved {upsert_relationships(rel,USER):,} relationships.")
    with tab3:
        target=st.text_input("Start entity","FAC-001")
        hops=st.number_input("Maximum hops",1,10,4)
        if st.button("🧭 Trace downstream impact",use_container_width=True):
            from industrial_platform_excellence import impact_analysis
            impact=impact_analysis(target,int(hops))
            st.session_state["impact"]=impact
        st.dataframe(st.session_state.get("impact",pd.DataFrame()),use_container_width=True,hide_index=True)

elif selected == "Advanced Planning & Scheduling":
    st.subheader("📅 Advanced Planning & Scheduling")
    tab1,tab2,tab3 = st.tabs(["Orders","Constraints","Schedule"])
    with tab1:
        orders=st.data_editor(st.session_state.get("wb_orders",pd.DataFrame({
            "Order":["WO-001","WO-002","WO-003","WO-004"],
            "Product":["P-100","P-200","P-100","P-300"],
            "Qty":[100,200,150,120],
            "DueDate":[datetime.now()+pd.Timedelta(hours=8),datetime.now()+pd.Timedelta(hours=10),datetime.now()+pd.Timedelta(hours=12),datetime.now()+pd.Timedelta(hours=15)],
            "ProcessingMin":[30,45,25,35],
            "SetupMin":[5,10,5,8],
            "Machine":["M-01","M-01","M-02","M-02"],
            "Priority":[3,1,2,2],
            "MaterialReady":[datetime.now(),datetime.now()+pd.Timedelta(hours=1),datetime.now(),datetime.now()+pd.Timedelta(hours=2)],
        })),num_rows="dynamic",use_container_width=True,key="wb_orders_editor")
        st.session_state["wb_orders"]=orders
    with tab2:
        c1,c2=st.columns(2)
        with c1:
            labor_df=st.data_editor(st.session_state.get("wb_labor",pd.DataFrame({"Machine":["M-01","M-02"],"CapacityHours":[8,8]})),num_rows="dynamic",use_container_width=True,key="wb_labor_editor")
        with c2:
            material_df=st.data_editor(st.session_state.get("wb_material",pd.DataFrame({"Product":["P-100","P-200","P-300"],"Available":[500,300,100]})),num_rows="dynamic",use_container_width=True,key="wb_material_editor")
        maintenance=st.data_editor(st.session_state.get("wb_maintenance",pd.DataFrame({
            "Machine":["M-02"],"Start":[datetime.now()+pd.Timedelta(hours=3)],"End":[datetime.now()+pd.Timedelta(hours=4)],
        })),num_rows="dynamic",use_container_width=True,key="wb_maintenance_editor")
        setup_text=st.text_area("Sequence-dependent setup matrix JSON",'{"P-100|P-200":15,"P-200|P-100":12}')
    with tab3:
        if st.button("▶ Build Constraint-Aware Schedule",type="primary",use_container_width=True):
            setup={}
            try:
                for k,v in json.loads(setup_text).items():
                    a_,b_=k.split("|",1); setup[(a_,b_)]=float(v)
                labor={r["Machine"]:float(r["CapacityHours"]) for r in labor_df.to_dict("records")}
                materials={r["Product"]:float(r["Available"]) for r in material_df.to_dict("records")}
                schedule,diag=constrained_schedule(orders,maintenance,labor,materials,setup)
                st.session_state["wb_schedule"]=schedule
                st.session_state["wb_schedule_diag"]=diag
            except Exception as exc:
                st.error(f"Schedule could not be completed safely: {exc}")
        sch=st.session_state.get("wb_schedule")
        if sch is not None:
            st.dataframe(sch,use_container_width=True,hide_index=True)
            render_engineering_result(st.session_state["wb_schedule_diag"],"Schedule diagnostics","schedule_diag")
            fig=px.timeline(sch,x_start="Start",x_end="Finish",y="Machine",color="Product",hover_data=["Order","LateMin"])
            st.plotly_chart(fig,use_container_width=True)

elif selected == "Quality Engineering & Reliability":
    st.subheader("📈 Quality Engineering & Reliability")
    tab1,tab2,tab3,tab4 = st.tabs(["SPC","Capability / MSA","DOE / ANOVA","Reliability"])
    with tab1:
        vals=st.text_area("Measurements","10,10.1,9.9,10.05,9.95,10.2,10.0,9.8")
        chart=st.selectbox("Chart type",["I-MR","Individuals","p","u"])
        if st.button("📊 Build control chart",type="primary",use_container_width=True):
            try:
                nums=[float(x.strip()) for x in vals.split(",") if x.strip()]
                if chart in {"p","u"}:
                    counts=nums
                    samples=[100]*len(nums)
                    out=proportion_chart(counts,samples,chart)
                else:
                    out=control_chart(nums,chart)
                st.session_state["wb_spc"]=out
            except Exception as exc:
                st.error(f"SPC analysis failed safely: {exc}")
        if "wb_spc" in st.session_state:
            out=st.session_state["wb_spc"]; st.dataframe(out,use_container_width=True,hide_index=True)
            ycol="Rate" if "Rate" in out else "Value"
            st.line_chart(out.set_index(out.columns[0])[[ycol]])
    with tab2:
        qc=st.data_editor(st.session_state.get("wb_qc",pd.DataFrame({"Measurement":[10.1,10.0,9.9,10.2,9.8,10.05],"Part":[1,1,2,2,3,3],"Operator":["A","B","A","B","A","B"]})),num_rows="dynamic",use_container_width=True,key="wb_qc_editor")
        lsl=st.number_input("LSL",value=9.0); usl=st.number_input("USL",value=11.0); target=st.number_input("Target",value=10.0)
        if st.button("🔬 Capability + Gage R&R",use_container_width=True):
            render_engineering_result({"Capability":capability_extended(qc["Measurement"],lsl,usl,target),"Gage R&R":gage_rr_extended(qc)},"Capability & Gage R&R","capability_result")
    with tab3:
        doe=st.data_editor(st.session_state.get("wb_doe",pd.DataFrame({"A":[-1,-1,1,1],"B":[-1,1,-1,1],"Response":[10,12,14,16]})),num_rows="dynamic",use_container_width=True,key="wb_doe_editor")
        response=st.selectbox("Response",list(doe.columns),index=2 if len(doe.columns)>2 else 0)
        factors=st.multiselect("Factors",[c for c in doe.columns if c!=response])
        if factors and st.button("🧪 Estimate effects",use_container_width=True):
            st.dataframe(doe_2level_effects(doe,response,factors),use_container_width=True,hide_index=True)
    with tab4:
        failures=st.text_area("Failure times","10,20,30,40,50,65,80")
        if st.button("📉 Fit reliability model",use_container_width=True):
            try:
                nums=[float(x.strip()) for x in failures.split(",") if x.strip()]
                render_engineering_result(reliability_summary(nums),"Reliability result","reliability_result")
            except Exception as exc:
                st.error(f"Reliability analysis failed safely: {exc}")

elif selected == "Industrial Simulation Lab":
    st.subheader("🧪 Industrial Simulation Lab")
    tab1,tab2 = st.tabs(["Replication Statistics","Warm-up Diagnostics"])
    with tab1:
        sim=st.data_editor(st.session_state.get("wb_sim",pd.DataFrame({"Replication":range(1,11),"Throughput":[95,99,101,98,100,102,97,100,99,101],"MeanWait":[11,13,12,14,10,12,13,11,12,12]})),num_rows="dynamic",use_container_width=True,key="wb_sim_editor")
        metric=st.selectbox("Metric", [c for c in sim.columns if c!="Replication"] or ["Throughput"])
        if st.button("📏 Calculate 95% confidence interval",type="primary",use_container_width=True):
            render_engineering_result(simulation_statistics(sim,metric),"Simulation statistics","simulation_result")
    with tab2:
        series=st.text_area("Observed metric series","100,101,102,102,101,100,100,99,100,100,101,100,100,101,100,100")
        window=st.number_input("Rolling window",3,50,5)
        if st.button("🧭 Diagnose warm-up",use_container_width=True):
            try:
                nums=[float(x.strip()) for x in series.split(",") if x.strip()]
                render_engineering_result(warmup_diagnostic(nums,int(window)),"Warm-up diagnostics","warmup_result")
            except Exception as exc:
                st.error(f"Warm-up diagnostic failed safely: {exc}")

elif selected == "3D Factory Designer":
    st.subheader("🧱 3D Factory Engineering")
    layout=st.data_editor(st.session_state.get("wb_layout",pd.DataFrame({
        "Asset":["CNC-01","Assembly-01","Packing-01","WIP"],
        "Type":["Machine","Station","Station","Storage"],
        "X":[0,5,11,3],"Y":[0,2,2,5],"Z":[0,0,0,0],
        "Length":[2,4,4,3],"Width":[2,2,2,3],"Height":[2,3,3,2],
    })),num_rows="dynamic",use_container_width=True,key="wb_layout_editor")
    st.session_state["wb_layout"]=layout
    fig=px.scatter_3d(layout,x="X",y="Y",z="Z",color="Type",text="Asset",size="Height",title="Factory Model")
    st.plotly_chart(fig,use_container_width=True)
    c1,c2=st.columns(2)
    with c1:
        if st.button("🧱 Collision check",use_container_width=True):
            st.session_state["wb_collisions"]=bbox_collision_check(layout)
    with c2:
        seq=st.text_input("Flow sequence","CNC-01,Assembly-01,Packing-01")
        if st.button("🚶 Analyze flow distance",use_container_width=True):
            st.session_state["wb_flow"]=flow_distance(layout,[x.strip() for x in seq.split(",") if x.strip()])
    if "wb_collisions" in st.session_state:
        st.dataframe(st.session_state["wb_collisions"],use_container_width=True,hide_index=True)
    if "wb_flow" in st.session_state:
        st.metric("Flow distance",f"{st.session_state['wb_flow']['Total Distance']:.2f}")
        st.dataframe(st.session_state["wb_flow"]["Legs"],use_container_width=True,hide_index=True)

elif selected == "Multi-Objective Optimization":
    st.subheader("⚖️ Multi-Objective Optimization")
    df=st.data_editor(st.session_state.get("wb_multi",pd.DataFrame({
        "Scenario":["A","B","C","D"],"Cost":[100,90,120,110],"Carbon":[80,120,60,75],"Service":[94,97,99,96],"Risk":[12,20,8,15]
    })),num_rows="dynamic",use_container_width=True,key="wb_multi_editor")
    objectives=st.multiselect("Objectives",["Cost","Carbon","Service","Risk"],default=["Cost","Carbon","Service"])
    minimize={c:st.checkbox(f"Minimize {c}",value=(c!="Service"),key=f"wb_min_{c}") for c in objectives}
    if objectives and st.button("⚖️ Calculate Pareto frontier",type="primary",use_container_width=True):
        st.session_state["wb_pareto"]=pareto_frontier_v2(df,objectives,[minimize[c] for c in objectives])
    st.dataframe(st.session_state.get("wb_pareto",pd.DataFrame()),use_container_width=True,hide_index=True)

elif selected == "Robust & Resilient Optimization":
    st.subheader("🎲 Robust & Resilient Optimization")
    scenarios=st.data_editor(st.session_state.get("wb_robust",pd.DataFrame({
        "Scenario":["Baseline","High Demand","Supplier Shock","Capacity Expansion"],
        "Demand Mean":[1000,1200,1050,1000],"Demand Std":[100,150,120,100],
        "Capacity":[1100,1100,700,1300],"Disruption Probability":[0.05,0.1,0.2,0.05],
        "Disruption Multiplier":[0.6,0.6,0.5,0.8],
    })),num_rows="dynamic",use_container_width=True,key="wb_robust_editor")
    sims=st.number_input("Simulations",1000,100000,5000,500)
    if st.button("🎲 Run robust scenarios",type="primary",use_container_width=True):
        out=robust_scenarios({},scenarios,int(sims))
        st.session_state["wb_robust_result"]=out
    if "wb_robust_result" in st.session_state:
        st.dataframe(st.session_state["wb_robust_result"],use_container_width=True,hide_index=True)
        st.plotly_chart(px.bar(st.session_state["wb_robust_result"],x="Scenario",y="Service Probability",title="Service probability by scenario"),use_container_width=True)

elif selected == "Capital Investment & Engineering Economics":
    st.subheader("💰 Capital Investment & Engineering Economics")
    capex=st.number_input("Initial investment",0.0,1e9,100000.0,1000.0)
    flows=st.text_input("Annual cash flows","40000,50000,60000,70000")
    c1,c2=st.columns(2)
    rates_text=c1.text_input("Discount rates","0.08,0.10,0.12")
    mult_text=c2.text_input("CAPEX multipliers","0.9,1.0,1.1")
    if st.button("💰 Run sensitivity",type="primary",use_container_width=True):
        try:
            cf=[float(x.strip()) for x in flows.split(",") if x.strip()]
            rates=[float(x.strip()) for x in rates_text.split(",") if x.strip()]
            mult=[float(x.strip()) for x in mult_text.split(",") if x.strip()]
            out=economics_sensitivity(capex,cf,rates,mult)
            st.session_state["wb_econ"]=out
        except Exception as exc:
            st.error(f"Economics calculation failed safely: {exc}")
    if "wb_econ" in st.session_state:
        st.dataframe(st.session_state["wb_econ"],use_container_width=True,hide_index=True)
        st.plotly_chart(px.density_heatmap(st.session_state["wb_econ"],x="Discount Rate",y="CAPEX Multiplier",z="NPV",text_auto=".0f"),use_container_width=True)

elif selected == "Workforce Engineering":
    st.subheader("👷 Workforce Engineering")
    a,b,c=st.columns(3)
    staff=a.number_input("Staff",1,10000,20)
    minutes=b.number_input("Minutes/shift",60.0,1440.0,480.0)
    prod=c.slider("Productive %",1,100,85)
    absent=st.slider("Absenteeism %",0,50,5)
    overtime=st.number_input("Overtime hours",0.0,24.0,2.0)
    wage=st.number_input("Wage/hour",0.0,1000.0,25.0)
    if st.button("👷 Evaluate workforce scenario",type="primary",use_container_width=True):
        render_engineering_result(workforce_scenario(staff,minutes,prod,absent,overtime,wage),"Workforce scenario","workforce_result")

elif selected == "Industrial Sustainability & LCA":
    st.subheader("🌱 Industrial Sustainability & LCA")
    df=st.data_editor(st.session_state.get("wb_lca",pd.DataFrame({
        "Activity":["Electricity","Diesel","Freight","Water","Waste"],
        "Scope":["Scope 2","Scope 1","Scope 3","Resource","Resource"],
        "LifeCycleStage":["Operations","Operations","Distribution","Operations","Operations"],
        "Quantity":[10000,2500,15000,3000,12000],
        "EmissionFactor":[0.42,2.68,0.10,0.0,0.0],
        "Energy_kWh":[10000,0,0,0,0],
        "Water_m3":[0,0,0,3000,0],
        "Waste_kg":[0,0,0,0,12000],
    })),num_rows="dynamic",use_container_width=True,key="wb_lca_editor")
    if st.button("🌱 Calculate lifecycle impacts",type="primary",use_container_width=True):
        st.session_state["wb_lca_result"]=sustainability_scenario(df)
    if "wb_lca_result" in st.session_state:
        r=st.session_state["wb_lca_result"]
        st.metric("Total tCO2e",f"{r['total_tCO2e']:,.3f}")
        st.dataframe(r["scope_summary"],use_container_width=True,hide_index=True)
        st.dataframe(r["detail"],use_container_width=True,hide_index=True)

elif selected == "Benchmarking & Engineering Standards":
    st.subheader("📏 Benchmarking & Engineering Standards")
    actual=st.data_editor(st.session_state.get("wb_bench_actual",pd.DataFrame({"Metric":["OEE","OTIF","Inventory Turns","Energy / Unit"],"Actual":[82,96,5.2,1.8]})),num_rows="dynamic",use_container_width=True,key="wb_bench_actual_editor")
    bench=st.data_editor(st.session_state.get("wb_bench_benchmark",pd.DataFrame({"Metric":["OEE","OTIF","Inventory Turns","Energy / Unit"],"Benchmark":[85,98,6,1.5],"Source":["Configured Target"]*4,"Source Date":["2026-01"]*4})),num_rows="dynamic",use_container_width=True,key="wb_bench_benchmark_editor")
    if st.button("📏 Compare benchmark gaps",type="primary",use_container_width=True):
        st.session_state["wb_bench_result"]=benchmark_gap(actual,bench)
    if "wb_bench_result" in st.session_state:
        st.dataframe(st.session_state["wb_bench_result"],use_container_width=True,hide_index=True)

elif selected == "Engineering Decision Center":
    st.subheader("📋 Engineering Decision Center")
    title=st.text_input("Decision title","Open additional packing capacity")
    metrics_df=st.data_editor(pd.DataFrame({"Metric":["Cost Delta","Service Delta","Carbon Delta"],"Value":[-8.2,2.1,-4.5]}),num_rows="dynamic",use_container_width=True,key="wb_decision_metrics")
    assumptions=st.text_area("Assumptions JSON",'{"Demand":"12-week forecast v4","Capacity":"Verified"}')
    uncertainty=st.text_area("Uncertainty JSON",'{"Demand P95":"Base + 18%","Supplier disruption":"5%"}')
    status=st.selectbox("Status",["Proposed","Needs Revision","Approved","Rejected"])
    if st.button("📋 Save Decision Card",type="primary",use_container_width=True):
        try:
            card=build_decision_card(title,selected,{r["Metric"]:r["Value"] for r in metrics_df.to_dict("records")},json.loads(assumptions),json.loads(uncertainty),status)
            did=save_decision(card,USER)
            st.success(f"Decision saved: {did}")
            st.session_state["last_decision_id"]=did
        except Exception as exc:
            st.error(f"Decision could not be saved safely: {exc}")
    decision_id=st.session_state.get("last_decision_id")
    if decision_id:
        note=st.text_input("Approval note","")
        a1,a2,a3=st.columns(3)
        with a1:
            if st.button("✅ Approve",use_container_width=True) and permission_check(st.session_state.get("role","Viewer"),"approve"):
                st.write(record_approval(decision_id,USER,"Approved",note))
        with a2:
            if st.button("↩ Needs Revision",use_container_width=True) and permission_check(st.session_state.get("role","Viewer"),"approve"):
                st.write(record_approval(decision_id,USER,"Needs Revision",note))
        with a3:
            if st.button("❌ Reject",use_container_width=True) and permission_check(st.session_state.get("role","Viewer"),"approve"):
                st.write(record_approval(decision_id,USER,"Rejected",note))

elif selected == "Advanced Engineering Copilot":
    st.subheader("🧠 Advanced Engineering Copilot")
    st.caption("Planning layer first: Shoir-IE shows the proposed workflow, asks for approval, then hands execution to the relevant deterministic module.")
    prompt=st.text_area("Engineering request","Import the demand workbook, clean it, forecast 12 weeks, test supplier disruption risk, compare scenarios and prepare an executive report.")
    if st.button("🧠 Build execution plan",type="primary",use_container_width=True):
        st.session_state["wb_plan"]=copilot_execution_plan(prompt)
    plan=st.session_state.get("wb_plan")
    if plan:
        render_engineering_result(plan,"Proposed execution plan","copilot_plan")
        approve=st.button("✅ Approve this workflow")
        if approve:
            st.session_state["wb_plan_approved"]=True
            audit_event(USER,"copilot_plan_approved",{"steps":plan["steps"]})
            st.success("Workflow approved. Execute each step from its governed module; this layer does not silently mutate data.")
        st.metric("Approval required","YES" if plan["approval_required"] else "NO")

elif selected == "Industrial Connectivity Hub":
    st.subheader("🔌 Industrial Connectivity Hub")
    conns=st.data_editor(st.session_state.get("wb_connectors",pd.DataFrame({
        "Name":["Plant REST","Plant MQTT","Machine OPC-UA","Analytics SQL"],
        "System Type":["REST","MQTT","OPC-UA","SQL"],
        "Endpoint":["https://example.com/api","mqtts://broker.example","opc.tcp://localhost:4840","sqlite://enterprise_full_workspace.db"]
    })),num_rows="dynamic",use_container_width=True,key="wb_conn_editor")
    for row in conns.to_dict("records"):
        if st.button(f"🧪 Validate {row['Name']}",use_container_width=True,key="conn_"+re.sub(r"[^A-Za-z0-9]","_",str(row["Name"]))):
            render_engineering_result(connector_validation(row["Name"],row["System Type"],row["Endpoint"]),f"Connector validation · {row['Name']}","connector_"+re.sub(r"[^A-Za-z0-9]","_",str(row["Name"])))

elif selected in {"Manufacturing Execution System","Industrial Control Center","Executive Report Center","Enterprise Security & Governance","Team Workspaces & RBAC","Engineering Model Registry","Experiment Lab","Live Industrial Digital Twin","Predictive Maintenance Digital Twin","Advanced ML Demand Forecasting","Localization & Multi-Currency"}:
    # Reuse existing mature module implementations under the unified shell.
    render_module(selected, RAW_TIER, USER)

else:
    render_module(selected, RAW_TIER, USER)

# Universal footer controls
st.divider()
st.subheader("📤 Unified Results & Governance")
source_tables=[]
for key in ["wb_validation_result","wb_schedule","wb_spc","wb_pareto","wb_robust_result","wb_econ","wb_lca_result","wb_bench_result","impact","wb_collisions","wb_flow"]:
    val=st.session_state.get(key)
    if isinstance(val,pd.DataFrame):
        source_tables.append((key,val))
    elif isinstance(val,dict):
        for k,v in val.items():
            if isinstance(v,pd.DataFrame):
                source_tables.append((f"{key}_{k}",v))
if source_tables:
    manifest=export_manifest_tables(selected,source_tables,USER)
    csv=manifest.to_csv(index=False).encode()
    st.download_button("📋 Download audit manifest",csv,f"shoir_ie_{re.sub(r'[^A-Za-z0-9]+','_',selected).lower()}_manifest.csv","text/csv",use_container_width=False)
    # Keep the platform's existing export engine as the canonical workbook/PDF/PPT path.
    from industrial_platform import render_export_bar
    render_export_bar(selected,source_tables,[],RAW_TIER,USER)

with st.expander("🏗️ Tier architecture"):
    st.dataframe(tier_matrix(),use_container_width=True,hide_index=True)
with st.expander("🧩 Complete module map"):
    st.dataframe(module_availability(RAW_TIER),use_container_width=True,hide_index=True)
