"""Shoir-IE Industrial Platform Suite.

Additive, production-oriented services for the unified industrial decision platform:
digital thread, APS/MRP, MES, quality/reliability, simulation, 3D layout,
connectivity, multi-objective/robust optimization, registry/experiments,
economics, workforce, sustainability, validation, benchmarking, decision center,
and enterprise governance.

The module functions are deterministic where possible, persist important metadata,
and return explicit diagnostics rather than inventing data.
"""
from __future__ import annotations
import io, json, math, os, re, sqlite3, hashlib, heapq, time
from datetime import datetime, timedelta
from itertools import product
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

PLATFORM_CATALOG = [
    {"tier":"Starter","category":"Core Platform","name":"Engineering Validation Center","when":"Validate tables, model assumptions, units, ranges and result health before acting.","example":"Upload an engineering table and receive a data-quality, feasibility and reproducibility checklist."},
    {"tier":"Mid-Tier Pro","category":"Industrial Model","name":"Industrial Data Model & Digital Thread","when":"Keep products, customers, suppliers, facilities, machines, people, materials, routes and orders linked.","example":"Change a facility or machine attribute once and trace the affected planning records."},
    {"tier":"Professional","category":"Planning","name":"Advanced Planning & Scheduling","when":"Create finite-capacity schedules that respect machines, labor, setup time, material availability and due dates.","example":"Schedule rush orders around maintenance downtime without overbooking a machine."},
    {"tier":"Professional","category":"Quality","name":"Quality Engineering & Reliability","when":"Run statistical quality, measurement, FMEA and reliability analysis from one workspace.","example":"Combine SPC, Cp/Cpk, Gage R&R, DOE, ANOVA and Weibull analysis for a process study."},
    {"tier":"Professional","category":"Economics","name":"Capital Investment & Engineering Economics","when":"Compare industrial investments using NPV, IRR, payback and sensitivity.","example":"Compare automation CAPEX against labor, maintenance and energy savings."},
    {"tier":"Professional","category":"Workforce","name":"Workforce Engineering","when":"Design staffing, takt, balance, shifts, skills and ergonomic workloads.","example":"Balance work elements to takt and identify understaffed stations."},
    {"tier":"Professional","category":"Sustainability","name":"Industrial Sustainability & LCA","when":"Evaluate energy, water, waste and lifecycle emissions alongside cost and service.","example":"Compare process alternatives on carbon, water, waste and operating cost."},
    {"tier":"Professional","category":"Benchmarking","name":"Benchmarking & Engineering Standards","when":"Compare configurable KPIs against your chosen benchmark sources and dates.","example":"Compare OEE, OTIF, inventory turns and energy per unit against configured targets."},
    {"tier":"Enterprise","category":"Manufacturing","name":"Manufacturing Execution System","when":"Connect work orders, dispatch, actual production, downtime, quality, WIP and genealogy.","example":"Track a work order from dispatch through production confirmation and quality release."},
    {"tier":"Enterprise","category":"Simulation","name":"Industrial Simulation Lab","when":"Test DES, agent-based and system-dynamics scenarios before changing the real operation.","example":"Compare queue throughput under one versus two packing stations with confidence intervals."},
    {"tier":"Enterprise","category":"Facilities","name":"3D Factory Designer","when":"Model equipment, people, storage, flow, travel distance and facility geometry visually.","example":"Place machines in 3D, review travel paths and feed the same layout into simulation."},
    {"tier":"Enterprise","category":"Connectivity","name":"Industrial Connectivity Hub","when":"Manage and test REST, SQL, MQTT and OPC-UA connector profiles.","example":"Test a plant endpoint, record sync health and keep credentials out of analytics logs."},
    {"tier":"Enterprise","category":"Optimization","name":"Multi-Objective Optimization","when":"Trade off cost, service, carbon, risk, inventory, lead time and capacity together.","example":"Explore the Pareto frontier between logistics cost and carbon."},
    {"tier":"Enterprise","category":"Optimization","name":"Robust & Resilient Optimization","when":"Evaluate decisions against demand, lead-time, supplier, energy and capacity uncertainty.","example":"Compare nominal capacity with the probability of meeting demand across thousands of shocks."},
    {"tier":"Enterprise","category":"Governance","name":"Engineering Model Registry","when":"Version models, parameters, data hashes, assumptions, solvers and results for reproducibility.","example":"Reproduce a planning study six months later from its registered snapshot."},
    {"tier":"Enterprise","category":"Experimentation","name":"Experiment Lab","when":"Run many controlled scenarios and compare cost, service, risk, inventory, carbon and capacity.","example":"Batch-test baseline, demand surge, supplier outage and capacity-expansion cases."},
    {"tier":"Enterprise","category":"Control","name":"Industrial Control Center","when":"See demand, inventory, production, supplier, transport, machine, quality, carbon, risk and finance health together.","example":"Click a red issue and jump into the module responsible for the underlying KPI."},
    {"tier":"Enterprise","category":"Decisions","name":"Engineering Decision Center","when":"Turn model results into auditable decisions with assumptions, deltas, uncertainty and approvals.","example":"Create an approval-ready decision card from a network optimization run."},
    {"tier":"Enterprise","category":"Data Platform","name":"Industrial Data Platform","when":"Ingest, profile, hash, catalog and prepare operational datasets for downstream modules.","example":"Upload a multi-sheet workbook, validate schema and register a reusable dataset."},
    {"tier":"Enterprise Plus","category":"AI","name":"Advanced Engineering Copilot","when":"Orchestrate multi-step engineering workflows with preview, approval and tool execution.","example":"Clean a workbook, forecast demand, test risk, compare scenarios and prepare a report after one approval."},
    {"tier":"Enterprise Plus","category":"Digital Twin","name":"Live Industrial Digital Twin","when":"Maintain a common live state for assets, telemetry, production and planning.","example":"Combine telemetry and production events into a current machine and line state."},
    {"tier":"Enterprise Plus","category":"Security","name":"Enterprise Security & Governance","when":"Manage policy, audit, API access, retention, workspace isolation and identity configuration.","example":"Review security posture, role assignments and auditable configuration changes."},
]

TIER_FEATURES = {
    "Starter": ["Engineering Validation Center", "Excel Data Cleaning & Import"],
    "Mid-Tier Pro": [
        "Industrial Data Model & Digital Thread",
        "Engineering Validation Center",
        "Excel Data Cleaning & Import",
        "Carbon Accounting",
    ],
    "Professional": [
        "Industrial Data Model & Digital Thread","Advanced Planning & Scheduling","Quality Engineering & Reliability",
        "Capital Investment & Engineering Economics","Workforce Engineering","Industrial Sustainability & LCA",
        "Benchmarking & Engineering Standards","Engineering Validation Center","Excel Data Cleaning & Import",
        "Carbon Accounting","MEIO Matrix","Fleet Routing","Production Planning & Control (PPC)",
    ],
    "Enterprise": [
        "Manufacturing Execution System","Industrial Simulation Lab","3D Factory Designer",
        "Industrial Connectivity Hub","Multi-Objective Optimization","Robust & Resilient Optimization",
        "Engineering Model Registry","Experiment Lab","Industrial Control Center","Engineering Decision Center",
        "Industrial Data Platform","Advanced Planning & Scheduling","Quality Engineering & Reliability",
        "Capital Investment & Engineering Economics","Workforce Engineering","Industrial Sustainability & LCA",
        "Benchmarking & Engineering Standards","Industrial Data Model & Digital Thread",
        "AI Copilot","Monte Carlo Sim","Sensitivity Analysis","Digital Twin & Discrete-Event Simulation",
    ],
    "Enterprise Plus": [
        "Advanced Engineering Copilot","Live Industrial Digital Twin","Enterprise Security & Governance",
        "Manufacturing Execution System","Industrial Simulation Lab","3D Factory Designer",
        "Industrial Connectivity Hub","Multi-Objective Optimization","Robust & Resilient Optimization",
        "Engineering Model Registry","Experiment Lab","Industrial Control Center","Engineering Decision Center",
        "Industrial Data Platform","Advanced Planning & Scheduling","Quality Engineering & Reliability",
        "Capital Investment & Engineering Economics","Workforce Engineering","Industrial Sustainability & LCA",
        "Benchmarking & Engineering Standards","Industrial Data Model & Digital Thread",
    ],
}

TIER_ORDER = ["Starter","Mid-Tier Pro","Professional","Enterprise","Enterprise Plus","Research Pack"]

MODULE_TABLE_KEYS = {
    "Engineering Validation Center":["validation_df"],
    "Industrial Data Model & Digital Thread":["thread_df","thread_rel"],
    "Advanced Planning & Scheduling":["aps_demand","aps_bom","aps_orders"],
    "Manufacturing Execution System":["mes_wo_df","mes_events_df","mes_oee_df"],
    "Quality Engineering & Reliability":["quality_df","msa_df","anova_df","fmea_df"],
    "Industrial Simulation Lab":[],
    "3D Factory Designer":["factory3d_df"],
    "Industrial Connectivity Hub":["conn_df"],
    "Multi-Objective Optimization":["multiobj_df"],
    "Robust & Resilient Optimization":["robust_df"],
    "Engineering Model Registry":["model_registry_df"],
    "Experiment Lab":["experiment_df"],
    "Industrial Data Platform":[],
    "Capital Investment & Engineering Economics":["capex_df"],
    "Workforce Engineering":["work_elements","skills_df"],
    "Industrial Sustainability & LCA":["sustain_df"],
    "Benchmarking & Engineering Standards":["benchmark_actual","benchmark_targets"],
    "Live Industrial Digital Twin":["twin_tel"],
    "Enterprise Security & Governance":["security_roles"],
}

def _module_slug(module: str) -> str:
    return re.sub(r"[^a-z0-9]+","_",module.lower()).strip("_")

def module_reset(module: str, st) -> None:
    for key in MODULE_TABLE_KEYS.get(module, []):
        st.session_state.pop(key, None)
        st.session_state.pop(key.replace("_df","_editor"), None)
    slug=_module_slug(module)
    for key in list(st.session_state.keys()):
        if str(key).startswith(f"{slug}_"):
            st.session_state.pop(key,None)

def render_module_data_exchange(module: str, st, tier: str, username: str) -> None:
    slug=_module_slug(module)
    has_module_tables=any(key in st.session_state for key in MODULE_TABLE_KEYS.get(module,[]))
    if not has_module_tables:
        st.markdown("### 📥 First-load Data Import")
        st.caption("Upload an Excel/CSV file and Shoir-IE will map matching column names into this module's table.")
        up=st.file_uploader("Import Excel / CSV",type=["xlsx","csv"],key=f"{slug}_first_upload")
        if up is not None:
            try:
                from shoir_upgrade import read_uploaded_workbook
                books=read_uploaded_workbook(up.getvalue(),up.name)
                sheet=st.selectbox("Sheet",list(books),key=f"{slug}_import_sheet")
                imported=books[sheet].copy(deep=True)
                st.session_state[f"{slug}_import_df"]=imported
                st.success(f"Loaded {len(imported):,} rows × {len(imported.columns):,} columns.")
            except Exception as exc:
                st.error(f"Import failed safely: {exc}")
    imported=st.session_state.get(f"{slug}_import_df")
    if isinstance(imported,pd.DataFrame) and has_module_tables:
        if st.button("🔄 Apply imported table",use_container_width=True,key=f"{slug}_apply_import"):
            applied=0
            for key in MODULE_TABLE_KEYS.get(module,[]):
                target=st.session_state.get(key)
                if isinstance(target,pd.DataFrame) and len(set(imported.columns)&set(target.columns)):
                    st.session_state[key]=align_imported_table(imported,target)
                    st.session_state.pop(key.replace("_df","_editor"),None)
                    applied+=1
            if applied:
                st.success(f"Imported data applied to {applied} compatible table(s).")
                st.rerun()
            else:
                st.warning("No compatible table was found. Review the expected columns.")
    st.markdown("### ⚙️ Module Workspace")
    if st.button("↩️ Reset Entire Module Workspace",use_container_width=True,key=f"{slug}_reset"):
        module_reset(module,st)
        st.rerun()

def render_module(module: str, tier: str, username: str):
    import streamlit as st
    import plotly.express as px
    init_platform_db()
    render_module_data_exchange(module, st, tier, username)
    required=next((x["tier"] for x in PLATFORM_CATALOG if x["name"]==module),None)
    if required and not tier_allows(tier,required):
        st.warning(f"🔒 {module} requires {required}. Your current tier is {tier}. Open Subscriptions to review upgrade options.")
        return
    st.markdown(f"## {module}")
    st.caption(next((x["when"] for x in PLATFORM_CATALOG if x["name"]==module),"Industrial engineering workspace"))
    if module=="Engineering Validation Center":
        df=st.session_state.setdefault("validation_df",pd.DataFrame({"Metric":["Cost","Service Level","Capacity"],"Value":[100000,95,12000],"Unit":["USD","%","units"]}))
        edited=st.data_editor(df,num_rows="dynamic",use_container_width=True,key="validation_editor")
        if st.button("🔎 Validate Model",type="primary",use_container_width=True,key="validation_run"):
            res=validate_table(edited,required=["Metric","Value"]); st.session_state["validation_result"]=res
        if st.session_state.get("validation_result"):
            res=st.session_state.validation_result; st.metric("Data Quality",f'{res["quality"]["score"]:.1f}%'); st.write(res)
        st.dataframe(edited,use_container_width=True)
        render_export_bar(module,[("Validation Table",edited)],tier,username=username)
    elif module=="Industrial Data Model & Digital Thread":
        tabs=st.tabs(["Entities","Relationships","Data Quality"])
        with tabs[0]:
            entity_type=st.selectbox("Entity type",["Product","SKU","Customer","Supplier","Facility","Machine","Employee","Material","Route","Operation","Order"])
            id_col=st.text_input("ID column","ID")
            df=st.data_editor(st.session_state.setdefault("thread_df",pd.DataFrame({"ID":["FAC-001","MCH-001"],"name":["Riyadh DC","CNC-01"],"capacity":[1000,80]})),num_rows="dynamic",use_container_width=True,key="thread_editor")
            if st.button("🔗 Register Entities",type="primary",use_container_width=True,key="thread_register"):
                if id_col in df.columns: st.success(f"Registered {upsert_entities(df,entity_type,id_col):,} entities into the digital thread.")
                else: st.error(f"ID column '{id_col}' not found.")
            with sqlite3.connect("enterprise_full_workspace.db") as c: ent=pd.read_sql("SELECT * FROM industrial_entities ORDER BY updated_at DESC LIMIT 100",c)
            st.dataframe(ent,use_container_width=True,hide_index=True)
        with tabs[1]:
            rel=st.data_editor(st.session_state.setdefault("thread_rel",pd.DataFrame({"From":["FAC-001"],"Relationship":["contains"],"To":["MCH-001"]})),num_rows="dynamic",use_container_width=True,key="thread_rel_editor")
            st.info("Relationships are intentionally explicit: use entity IDs and relationship names; no hidden inference.")
        with tabs[2]:
            st.write(data_quality_report(df))
        render_export_bar(module,[("Entities",df),("Relationships",rel)],tier,username=username)
    elif module=="Advanced Planning & Scheduling":
        tabs=st.tabs(["Demand / MRP","Finite Schedule","Dispatch"])
        with tabs[0]:
            demand=st.data_editor(st.session_state.setdefault("aps_demand",pd.DataFrame({"Product":["P-100","P-200"],"DemandQty":[1000,600]})),num_rows="dynamic",use_container_width=True,key="aps_demand_editor")
            bom=st.data_editor(st.session_state.setdefault("aps_bom",pd.DataFrame({"Parent":["P-100","P-200"],"Component":["C-1","C-2"],"QtyPer":[2,3]})),num_rows="dynamic",use_container_width=True,key="aps_bom_editor")
            if st.button("🧮 Explode MRP",use_container_width=True,key="aps_mrp"): st.session_state["aps_mrp_result"]=mrp_explode(demand,bom)
            if "aps_mrp_result" in st.session_state: st.dataframe(st.session_state["aps_mrp_result"],use_container_width=True)
        with tabs[1]:
            orders=st.data_editor(st.session_state.setdefault("aps_orders",pd.DataFrame({"Order":["WO-001","WO-002","WO-003"],"Product":["P-100","P-200","P-100"],"Qty":[100,200,150],"DueDate":[datetime.now()+timedelta(hours=8),datetime.now()+timedelta(hours=10),datetime.now()+timedelta(hours=12)],"ProcessingMin":[30,40,25],"SetupMin":[5,10,5],"Machine":["M-01","M-01","M-02"],"Priority":[2,1,3]})),num_rows="dynamic",use_container_width=True,key="aps_orders_editor")
            if st.button("📅 Build Finite Schedule",type="primary",use_container_width=True,key="aps_schedule"): st.session_state["aps_schedule_result"]=finite_schedule(orders)
            if "aps_schedule_result" in st.session_state:
                sch=st.session_state["aps_schedule_result"]; st.dataframe(sch,use_container_width=True); fig=px.timeline(sch,x_start="Start",x_end="Finish",y="Machine",color="Product",hover_data=["Order","LateMin"]); st.plotly_chart(fig,use_container_width=True)
        with tabs[2]:
            st.info("Dispatch uses the validated finite schedule as the release list. Export it as Excel/PDF/PPT from the panel below.")
            st.dataframe(st.session_state.get("aps_schedule_result",pd.DataFrame()),use_container_width=True)
        tables=[("Demand",demand),("BOM",bom),("Finite Schedule",st.session_state.get("aps_schedule_result",pd.DataFrame()))]
        figs=[("Finite Schedule",fig)] if "fig" in locals() else []
        render_export_bar(module,tables,figs,tier,username)
    elif module=="Manufacturing Execution System":
        tabs=st.tabs(["Work Orders","Execution Events","OEE & WIP"])
        with tabs[0]:
            wo=st.data_editor(st.session_state.setdefault("mes_wo_df",pd.DataFrame({"Work Order":["WO-001","WO-002"],"Product":["P-100","P-200"],"Quantity":[1000,600],"Due Date":[str(datetime.now()+timedelta(days=1)),str(datetime.now()+timedelta(days=2))],"Status":["Released","Released"],"Machine":["M-01","M-02"],"Operator":[""]*2})),num_rows="dynamic",use_container_width=True,key="mes_wo_editor")
            if st.button("💾 Save Work Orders",type="primary",use_container_width=True,key="mes_save"): 
                with sqlite3.connect("enterprise_full_workspace.db") as c:
                    for r in wo.to_dict("records"): c.execute("INSERT OR REPLACE INTO mes_work_orders VALUES(?,?,?,?,?,?,?,?)",(r["Work Order"],r["Product"],float(r["Quantity"]),str(r["Due Date"]),r["Status"],r["Machine"],r["Operator"],_now()))
                    c.commit()
                st.success("Work orders saved.")
        with tabs[1]:
            ev=st.data_editor(st.session_state.setdefault("mes_events_df",pd.DataFrame({"Work Order":["WO-001"],"Event":["START"],"Event Time":[_now()],"Quantity":[0],"Reason":[""],"Operator":[""]})),num_rows="dynamic",use_container_width=True,key="mes_event_editor")
            if st.button("📝 Record Events",use_container_width=True,key="mes_event_save"):
                with sqlite3.connect("enterprise_full_workspace.db") as c:
                    for r in ev.to_dict("records"): c.execute("INSERT INTO mes_events(work_order,event_type,event_time,quantity,reason,operator) VALUES(?,?,?,?,?,?)",(r["Work Order"],r["Event"],str(r["Event Time"]),float(r["Quantity"] or 0),str(r["Reason"]),str(r["Operator"])))
                    c.commit()
        with tabs[2]:
            oe=st.data_editor(st.session_state.setdefault("mes_oee_df",pd.DataFrame({"PlannedMin":[480],"DowntimeMin":[45],"IdealCycleSec":[30],"TotalCount":[800],"GoodCount":[760]})),num_rows="dynamic",use_container_width=True,key="mes_oee_editor")
            if st.button("📊 Calculate OEE",type="primary",use_container_width=True,key="mes_oee_run"):
                st.session_state["mes_oee_result"]=oee_from_events(oe.iloc[[0]])
            if "mes_oee_result" in st.session_state: st.json(st.session_state["mes_oee_result"])
            with sqlite3.connect("enterprise_full_workspace.db") as c: saved=pd.read_sql("SELECT * FROM mes_work_orders",c)
            st.write("Persisted Work Orders"); st.dataframe(saved,use_container_width=True,hide_index=True)
        render_export_bar(module,[("Work Orders",wo),("Events",ev),("OEE Input",oe),("Persisted Work Orders",saved if "saved" in locals() else pd.DataFrame())],tier,username)
    elif module=="Quality Engineering & Reliability":
        tabs=st.tabs(["SPC & Capability","MSA","DOE / ANOVA / Regression","FMEA & Reliability"])
        with tabs[0]:
            qc=st.data_editor(st.session_state.setdefault("quality_df",pd.DataFrame({"Sample":range(1,21),"Measurement":np.random.default_rng(1).normal(10,0.2,20)})),num_rows="dynamic",use_container_width=True,key="quality_editor")
            lsl=st.number_input("LSL",value=9.0,key="quality_lsl"); usl=st.number_input("USL",value=11.0,key="quality_usl")
            if st.button("📈 Analyze SPC & Capability",type="primary",use_container_width=True,key="quality_spc"): st.session_state["quality_spc"]=capability(qc["Measurement"],lsl,usl); st.session_state["quality_limits"]=spc_limits(qc["Measurement"])
            if "quality_spc" in st.session_state: st.json({**st.session_state["quality_spc"],**st.session_state["quality_limits"]})
        with tabs[1]:
            msa=st.data_editor(st.session_state.setdefault("msa_df",pd.DataFrame({"Part":[1,1,2,2,3,3],"Operator":["A","B"]*3,"Measurement":[10.1,10.2,11.0,10.9,9.9,10.0]})),num_rows="dynamic",use_container_width=True,key="msa_editor")
            if st.button("🔬 Calculate Gage R&R",use_container_width=True,key="msa_run"): st.json(gage_rr(msa))
        with tabs[2]:
            anova=st.data_editor(st.session_state.setdefault("anova_df",pd.DataFrame({"Group":["A","A","B","B","C","C"],"Value":[1.0,1.1,1.8,1.7,2.2,2.1],"X1":[1,2,3,4,5,6]})),num_rows="dynamic",use_container_width=True,key="anova_editor")
            if st.button("🧪 Run ANOVA",use_container_width=True,key="anova_run"): st.json(one_way_anova(anova,"Group","Value"))
            target=st.selectbox("Regression target",list(anova.columns),key="quality_reg_target"); feats=st.multiselect("Regression features",[c for c in anova.columns if c!=target],key="quality_reg_feats")
            if feats and st.button("📐 Fit Regression",use_container_width=True,key="reg_run"): coef,met=regression_fit(anova,target,feats); st.dataframe(coef); st.json(met)
        with tabs[3]:
            fmea=st.data_editor(st.session_state.setdefault("fmea_df",pd.DataFrame({"Failure Mode":["Bearing wear","Loose fastener"],"Severity":[8,6],"Occurrence":[5,4],"Detection":[3,5]})),num_rows="dynamic",use_container_width=True,key="fmea_editor")
            if st.button("⚠️ Calculate RPN",use_container_width=True,key="fmea_run"): st.session_state["fmea_result"]=fmea_score(fmea)
            if "fmea_result" in st.session_state: st.dataframe(st.session_state["fmea_result"],use_container_width=True)
            failures=st.number_input("Weibull sample count",1,1000,20,key="weibull_n")
            sample=np.maximum(.1,np.random.default_rng(2).weibull(2,failures)*100)
            if st.button("📉 Fit Weibull",use_container_width=True,key="weibull_run"): st.json(weibull_analysis(sample))
        render_export_bar(module,[("Quality Data",qc),("MSA",msa),("ANOVA",anova),("FMEA",fmea)],tier,username)
    elif module=="Industrial Simulation Lab":
        tabs=st.tabs(["Discrete Event","Agent Based","System Dynamics"])
        with tabs[0]:
            c1,c2,c3=st.columns(3); ar=c1.number_input("Arrival rate / hr",1.0,1000.0,20.0,key="sim_ar"); sr=c2.number_input("Service rate / hr / server",1.0,1000.0,25.0,key="sim_sr"); servers=c3.number_input("Servers",1,20,2,key="sim_servers")
            if st.button("▶ Run DES Replications",type="primary",use_container_width=True,key="sim_des"): st.session_state["sim_des"]=queue_simulation(ar,sr,servers)
            if "sim_des" in st.session_state: st.dataframe(st.session_state["sim_des"],use_container_width=True)
        with tabs[1]:
            agents=st.slider("Agents",5,200,30,key="sim_agents"); steps=st.slider("Steps",20,500,100,key="sim_steps")
            if st.button("🤖 Run Agent Simulation",use_container_width=True,key="sim_agent"): st.session_state["sim_agent"]=agent_simulation(agents,steps)
            if "sim_agent" in st.session_state: st.dataframe(st.session_state["sim_agent"],use_container_width=True)
        with tabs[2]:
            inv=st.number_input("Initial inventory",0.0,100000.0,5000.0,key="sd_inv"); demand=st.number_input("Demand/day",0.1,10000.0,500.0,key="sd_dem"); repl=st.number_input("Replenishment/day",0.0,10000.0,550.0,key="sd_repl")
            if st.button("📈 Run System Dynamics",use_container_width=True,key="sd_run"): st.session_state["sd"]=system_dynamics_inventory(inv,demand,repl)
            if "sd" in st.session_state: st.dataframe(st.session_state["sd"],use_container_width=True); st.line_chart(st.session_state["sd"].set_index("Day")[["Inventory","Demand","Replenishment"]])
        figs=[]; tables=[]
        if "sim_des" in st.session_state: tables.append(("DES Replications",st.session_state["sim_des"]))
        if "sim_agent" in st.session_state: tables.append(("Agent Summary",st.session_state["sim_agent"]))
        if "sd" in st.session_state: tables.append(("System Dynamics",st.session_state["sd"]))
        render_export_bar(module,tables,[],tier,username)
    elif module=="3D Factory Designer":
        df=st.data_editor(st.session_state.setdefault("factory3d_df",pd.DataFrame({"Asset":["CNC-01","Assembly","Packing","WIP Buffer"],"Type":["Machine","Station","Station","Storage"],"X":[0,6,12,3],"Y":[0,2,2,5],"Z":[0,0,0,0],"Length":[2,4,4,3],"Width":[2,2,2,3],"Height":[2,3,3,2]})),num_rows="dynamic",use_container_width=True,key="factory3d_editor")
        fig=px.scatter_3d(df,x="X",y="Y",z="Z",color="Type",text="Asset",size="Height",title="3D Factory Model"); st.plotly_chart(fig,use_container_width=True)
        if st.button("📏 Analyze Travel Distances",use_container_width=True,key="factory3d_dist"):
            pts=pd.to_numeric(df[["X","Y","Z"]].stack(),errors="coerce").unstack().fillna(0).to_numpy(); pairs=[] 
            for i in range(len(pts)):
                for j in range(i+1,len(pts)): pairs.append({"From":df.iloc[i]["Asset"],"To":df.iloc[j]["Asset"],"Distance":float(np.linalg.norm(pts[i]-pts[j]))})
            st.session_state["factory3d_dist"]=pd.DataFrame(pairs).sort_values("Distance")
        if "factory3d_dist" in st.session_state: st.dataframe(st.session_state["factory3d_dist"].head(50),use_container_width=True)
        render_export_bar(module,[("3D Layout",df),("Travel Matrix",st.session_state.get("factory3d_dist",pd.DataFrame()))],[("3D Factory",fig)],tier,username)
    elif module=="Industrial Connectivity Hub":
        tabs=st.tabs(["REST / SAP / Oracle / WMS","SQL","MQTT / OPC-UA"])
        with tabs[0]:
            conn_df=st.data_editor(st.session_state.setdefault("conn_df",pd.DataFrame({"Name":["SAP Demo","Oracle Demo","WMS Demo"],"System Type":["SAP","Oracle","WMS"],"Endpoint":["https://example.com","",""],"Status":["Not Tested","",""]})),num_rows="dynamic",use_container_width=True,key="conn_editor")
            selected=st.selectbox("Connector",conn_df["Name"].tolist(),key="conn_selected"); token=st.text_input("Bearer token (session only)",type="password",key="conn_token")
            if st.button("🔌 Test REST Connector",type="primary",use_container_width=True,key="conn_rest"):
                import requests
                row=conn_df[conn_df["Name"]==selected].iloc[0]; url=str(row["Endpoint"]).strip()
                if not url: st.error("Enter an endpoint."); 
                else:
                    try:
                        rr=requests.get(url,headers={"Authorization":"Bearer "+token} if token else {},timeout=10); st.success(f"HTTP {rr.status_code}"); log_security_event(username,"connector_test",f"{selected}|HTTP {rr.status_code}")
                    except Exception as exc: st.error(f"Connection failed safely: {exc}")
        with tabs[1]:
            query=st.text_area("Read-only SQL query","SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            if st.button("🗄️ Execute Read-Only SQL",use_container_width=True,key="conn_sql"):
                if not query.lstrip().lower().startswith("select"): st.error("Only SELECT queries are permitted.")
                else:
                    try:
                        with sqlite3.connect("enterprise_full_workspace.db") as c: st.dataframe(pd.read_sql_query(query,c))
                    except Exception as exc: st.error(f"SQL failed safely: {exc}")
        with tabs[2]:
            st.info("MQTT and OPC-UA connectors are configuration-ready. Live sessions require the site broker/server and protocol libraries.")
            mqtt_topic=st.text_input("MQTT topic","factory/telemetry/#"); opc_url=st.text_input("OPC-UA endpoint","opc.tcp://localhost:4840")
            if st.button("🧪 Validate Connector Settings",use_container_width=True,key="conn_validate"): st.write({"MQTT":mqtt_topic,"OPC-UA":opc_url,"Status":"Configuration accepted; no live connection attempted."})
        render_export_bar(module,[("Connector Profiles",conn_df)],tier,username)
    elif module=="Multi-Objective Optimization":
        df=st.data_editor(st.session_state.setdefault("multiobj_df",pd.DataFrame({"Scenario":["A","B","C","D"],"Cost":[100,90,130,110],"Carbon":[80,120,60,75],"Service":[94,97,99,96],"Risk":[12,20,8,15]})),num_rows="dynamic",use_container_width=True,key="multiobj_editor")
        weights={c:st.number_input(c+" weight",0.0,1.0,0.25,key="mo_w_"+c) for c in ["Cost","Carbon","Service","Risk"]}
        if st.button("⚖️ Calculate Composite Trade-off",type="primary",use_container_width=True,key="multiobj_run"):
            st.session_state["multiobj_result"]=multiobjective_score(df,weights,{"Service":False,"Cost":True,"Carbon":True,"Risk":True})
            st.session_state["pareto"]=pareto_frontier(df,["Cost","Carbon","Risk"],[True,True,True])
        st.dataframe(st.session_state.get("multiobj_result",df),use_container_width=True)
        if "pareto" in st.session_state: st.write("Pareto Frontier"); st.dataframe(st.session_state["pareto"],use_container_width=True)
        render_export_bar(module,[("Scenarios",df),("Scored Scenarios",st.session_state.get("multiobj_result",pd.DataFrame())),("Pareto",st.session_state.get("pareto",pd.DataFrame()))],tier,username)
    elif module=="Robust & Resilient Optimization":
        d=st.data_editor(st.session_state.setdefault("robust_df",pd.DataFrame({"Metric":["Demand Mean","Demand Std","Capacity","Lead Time Mean","Lead Time Std","Disruption Probability","Disruption Capacity Multiplier"],"Value":[1000,150,1100,7,1.5,.05,.6]})),num_rows="dynamic",use_container_width=True,key="robust_editor")
        sims=st.number_input("Simulations",500,100000,5000,500,key="robust_sims")
        if st.button("🎲 Run Robust Risk Analysis",type="primary",use_container_width=True,key="robust_run"):
            vals=d.set_index("Metric")["Value"].to_dict(); st.session_state["robust_result"]=robust_risk_analysis(float(vals["Demand Mean"]),float(vals["Demand Std"]),float(vals["Capacity"]),float(vals["Lead Time Mean"]),float(vals["Lead Time Std"]),float(vals["Disruption Probability"]),float(vals["Disruption Capacity Multiplier"]),int(sims))
        if "robust_result" in st.session_state: st.json(st.session_state["robust_result"])
        render_export_bar(module,[("Risk Inputs",d),("Robust Result",pd.DataFrame([st.session_state.get("robust_result",{})]))],tier,username)
    elif module=="Engineering Model Registry":
        df=st.data_editor(st.session_state.setdefault("model_registry_df",pd.DataFrame({"Model Name":["Network Baseline"],"Type":["MILP"],"Version":["1.0.0"],"Status":["Draft"],"Data Hash":[""]})),num_rows="dynamic",use_container_width=True,key="model_registry_editor")
        name=st.text_input("Model name","My Industrial Model",key="registry_name"); model_type=st.text_input("Model type","Optimization",key="registry_type"); params=st.text_area("Parameters JSON",'{"objective":"cost"}',key="registry_params")
        if st.button("💾 Register Model Snapshot",type="primary",use_container_width=True,key="registry_save"):
            try:
                mid=save_model_snapshot(name,model_type,json.loads(params),hashlib.sha256(df.to_csv(index=False).encode()).hexdigest(),username,{"user_entered":"true"}); st.success(f"Registered {mid}")
            except Exception as exc: st.error(f"Could not register model: {exc}")
        with sqlite3.connect("enterprise_full_workspace.db") as c: reg=pd.read_sql("SELECT * FROM platform_models ORDER BY created_at DESC",c)
        st.dataframe(reg,use_container_width=True,hide_index=True)
        render_export_bar(module,[("Registry",df),("Persisted Models",reg)],tier,username)
    elif module=="Experiment Lab":
        scenarios=st.data_editor(st.session_state.setdefault("experiment_df",pd.DataFrame({"Scenario":["Baseline","High Demand","Supplier Shock","Capacity Expansion"],"Cost":[100000,125000,142000,115000],"Service":[95,90,82,98],"Risk":[10,18,35,8],"Inventory":[5000,6200,7000,4700],"Carbon":[1000,1100,1300,850]})),num_rows="dynamic",use_container_width=True,key="experiment_editor")
        if st.button("🧪 Analyze Scenario Set",type="primary",use_container_width=True,key="experiment_run"):
            st.session_state["experiment_results"]=scenarios.assign(CostDelta=scenarios["Cost"]-scenarios["Cost"].iloc[0],ServiceDelta=scenarios["Service"]-scenarios["Service"].iloc[0],RiskDelta=scenarios["Risk"]-scenarios["Risk"].iloc[0])
            expid=save_experiment("Scenario Matrix",module,scenarios.to_dict("records"),st.session_state["experiment_results"].to_dict("records"),username); st.success(f"Experiment saved: {expid}")
        st.dataframe(st.session_state.get("experiment_results",scenarios),use_container_width=True)
        render_export_bar(module,[("Scenarios",scenarios),("Experiment Results",st.session_state.get("experiment_results",pd.DataFrame()))],tier,username)
    elif module=="Industrial Control Center":
        st.subheader("Unified Operations Health")
        entities={}
        for key,label in [("customers_list","Demand / Customers"),("warehouses_list","Facilities / Warehouses"),("fleet_list","Fleet"),("meio_data","MEIO"),("slotting_data","Warehouse Slotting")]:
            val=st.session_state.get(key); entities[label]=len(val) if isinstance(val,(list,pd.DataFrame)) else 0
        metrics=pd.DataFrame({"Area":list(entities.keys()),"Records":list(entities.values())}); metrics["Health"]=np.where(metrics["Records"]>0,"Ready","Needs Data")
        st.dataframe(metrics,use_container_width=True,hide_index=True)
        st.metric("Data quality score",f"{data_quality_report(metrics)['score']:.1f}%")
        render_export_bar(module,[("Control Center",metrics)],tier,username)
    elif module=="Engineering Decision Center":
        st.subheader("Decision Card Builder")
        title=st.text_input("Decision title","Network redesign decision",key="decision_title"); metric_text=st.text_area("Metrics JSON",'{"Cost Delta %":-8.2,"Service Delta %":2.1,"Carbon Delta %":-4.5}',key="decision_metrics"); ass_text=st.text_area("Assumptions JSON",'{"Demand horizon":"12 weeks","Lead time":"7 days"}',key="decision_assumptions"); unc_text=st.text_area("Uncertainty JSON",'{"P95 cost exposure":"12%"}',key="decision_unc")
        status=st.selectbox("Status",["Proposed","Under Review","Approved","Rejected"],key="decision_status")
        if st.button("📝 Save Decision Card",type="primary",use_container_width=True,key="decision_save"):
            try:
                card=create_decision_card(title,module,json.loads(metric_text),json.loads(ass_text),json.loads(unc_text),status); did=save_decision_card(card,username); st.success(f"Saved decision {did}")
            except Exception as exc: st.error(f"Decision card error: {exc}")
        with sqlite3.connect("enterprise_full_workspace.db") as c: dec=pd.read_sql("SELECT * FROM platform_decisions ORDER BY created_at DESC",c)
        st.dataframe(dec,use_container_width=True,hide_index=True)
        render_export_bar(module,[("Decision Cards",dec)],tier,username)
    elif module=="Industrial Data Platform":
        up=st.file_uploader("📥 Ingest CSV / XLSX",type=["csv","xlsx"],key="data_platform_upload")
        if up is not None:
            try:
                raw=up.getvalue(); lower=up.name.lower()
                sheets={"CSV":pd.read_csv(io.BytesIO(raw))} if lower.endswith(".csv") else {s:pd.read_excel(io.BytesIO(raw),sheet_name=s) for s in pd.ExcelFile(io.BytesIO(raw)).sheet_names}
                st.write({"file":up.name,"sheets":list(sheets),"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()})
                for name,df in sheets.items():
                    did=register_dataset(name,up.name,df); st.subheader(name); st.write(data_quality_report(df)); st.dataframe(df.head(25),use_container_width=True)
                    st.success(f"Registered dataset {did}")
                with sqlite3.connect("enterprise_full_workspace.db") as c: cat=pd.read_sql("SELECT * FROM platform_datasets ORDER BY created_at DESC",c)
                st.dataframe(cat,use_container_width=True,hide_index=True)
            except Exception as exc: st.error(f"Ingestion failed safely: {exc}")
    elif module=="Capital Investment & Engineering Economics":
        cf=st.data_editor(st.session_state.setdefault("capex_df",pd.DataFrame({"Year":[1,2,3,4,5],"Cash Flow":[45000,50000,55000,60000,65000]})),num_rows="dynamic",use_container_width=True,key="capex_editor")
        initial=st.number_input("Initial investment",0.0,100000000.0,180000.0,key="capex_initial"); rate=st.number_input("Discount rate",0.0,1.0,.1,key="capex_rate")
        salvage=st.number_input("Salvage value",0.0,100000000.0,0.0,key="capex_salvage")
        if st.button("💰 Calculate NPV / IRR / Payback",type="primary",use_container_width=True,key="capex_run"): st.session_state["capex_result"]=capital_metrics(initial,cf["Cash Flow"].tolist(),rate,salvage)
        if "capex_result" in st.session_state: st.json(st.session_state["capex_result"])
        render_export_bar(module,[("Cash Flows",cf),("Capital Metrics",pd.DataFrame([st.session_state.get("capex_result",{})]))],tier,username)
    elif module=="Workforce Engineering":
        tabs=st.tabs(["Balance & Takt","Staffing","Skills / Ergonomics"])
        with tabs[0]:
            elems=st.data_editor(st.session_state.setdefault("work_elements",pd.DataFrame({"Element":["Pick","Assemble","Inspect","Pack"],"TimeMin":[2.5,3.5,1.5,2.0]})),num_rows="dynamic",use_container_width=True,key="work_editor")
            takt=st.number_input("Takt time (min)",0.1,120.0,5.0,key="takt")
            if st.button("⚖️ Balance Line",type="primary",use_container_width=True,key="balance_run"): st.session_state["balance_result"],st.session_state["balance_metrics"]=line_balance(elems,takt)
            if "balance_result" in st.session_state: st.dataframe(st.session_state["balance_result"],use_container_width=True); st.json(st.session_state["balance_metrics"])
        with tabs[1]:
            staff=st.number_input("Staff",1,500,10,key="staff"); mins=st.number_input("Minutes/shift",60.0,1440.0,480.0,key="staff_mins"); prod=st.slider("Productive %",10,100,85,key="staff_prod")
            st.json(staffing_capacity(staff,mins,prod))
        with tabs[2]:
            skill=st.data_editor(st.session_state.setdefault("skills_df",pd.DataFrame({"Employee":["E1","E2","E3"],"Skill":["Welding","Assembly","Inspection"],"Level":[3,2,4]})),num_rows="dynamic",use_container_width=True,key="skills_editor")
            st.dataframe(skill,use_container_width=True)
        render_export_bar(module,[("Work Elements",elems),("Balance",st.session_state.get("balance_result",pd.DataFrame())),("Skills",skill)],tier,username)
    elif module=="Industrial Sustainability & LCA":
        df=st.data_editor(st.session_state.setdefault("sustain_df",pd.DataFrame({"Activity":["Electricity","Diesel","Freight"],"Scope":["Scope 2","Scope 1","Scope 3"],"LifeCycleStage":["Operations","Operations","Distribution"],"Quantity":[10000,2500,15000],"EmissionFactor":[0.42,2.68,0.1]})),num_rows="dynamic",use_container_width=True,key="sustain_editor")
        if st.button("🌱 Calculate Footprint",type="primary",use_container_width=True,key="sustain_run"): st.session_state["sustain_result"]=sustainability_accounting(df)
        if "sustain_result" in st.session_state:
            res=st.session_state["sustain_result"]; st.metric("Total tCO2e",f'{res["tCO2e"].sum():,.2f}'); st.dataframe(lca_summary(res),use_container_width=True); fig=px.bar(res,x="Activity",y="tCO2e",color="Scope",title="Lifecycle Footprint")
            st.plotly_chart(fig,use_container_width=True)
        render_export_bar(module,[("Sustainability Inputs",df),("Footprint",st.session_state.get("sustain_result",pd.DataFrame()))],[("Footprint",fig)] if "fig" in locals() else [],tier,username)
    elif module=="Benchmarking & Engineering Standards":
        actual=st.data_editor(st.session_state.setdefault("benchmark_actual",pd.DataFrame({"Metric":["OEE","OTIF","Inventory Turns","Energy per Unit"],"Actual":[82,96,5.2,1.8]})),num_rows="dynamic",use_container_width=True,key="benchmark_actual_editor")
        bench=st.data_editor(st.session_state.setdefault("benchmark_targets",pd.DataFrame({"Metric":["OEE","OTIF","Inventory Turns","Energy per Unit"],"Benchmark":[85,98,6.0,1.5],"Unit":["%","%","x","kWh/unit"],"Source":["Company Target"]*4,"Source Date":["2026-01"]*4})),num_rows="dynamic",use_container_width=True,key="benchmark_targets_editor")
        if st.button("📏 Compare Benchmarks",type="primary",use_container_width=True,key="benchmark_run"): st.session_state["benchmark_result"]=benchmark_compare(actual,bench)
        if "benchmark_result" in st.session_state: st.dataframe(st.session_state["benchmark_result"],use_container_width=True)
        render_export_bar(module,[("Actual",actual),("Benchmarks",bench),("Comparison",st.session_state.get("benchmark_result",pd.DataFrame()))],tier,username)
    elif module=="Engineering Validation Center":
        pass
    elif module=="Advanced Engineering Copilot":
        st.info("Advanced Copilot orchestration is configured through the main AI Copilot module. Use the AI Copilot to approve multi-step workflows; this module exposes governance and execution history.")
        st.write("Available tool families:",[x["name"] for x in PLATFORM_CATALOG if x["tier"] in ("Starter","Mid-Tier Pro","Professional","Enterprise")][:20])
    elif module=="Live Industrial Digital Twin":
        tel=st.data_editor(st.session_state.setdefault("twin_tel",pd.DataFrame({"Asset":["CNC-01","CNC-01","Packing-01"],"Timestamp":[_now(),_now(),_now()],"Metric":["Temperature","Vibration","Temperature"],"Value":[65,2.4,72],"Source":["simulated","simulated","simulated"]})),num_rows="dynamic",use_container_width=True,key="twin_editor")
        if st.button("🌐 Update Twin State",type="primary",use_container_width=True,key="twin_update"):
            with sqlite3.connect("enterprise_full_workspace.db") as c:
                for r in tel.to_dict("records"): c.execute("INSERT INTO telemetry_events(asset_id,ts,metric,value,source) VALUES(?,?,?,?,?)",(r["Asset"],str(r["Timestamp"]),r["Metric"],float(r["Value"]),r["Source"]))
                c.commit()
        with sqlite3.connect("enterprise_full_workspace.db") as c: stored=pd.read_sql("SELECT * FROM telemetry_events ORDER BY id DESC LIMIT 100",c)
        st.dataframe(stored,use_container_width=True,hide_index=True)
        st.success("Twin state synchronized from persisted telemetry.")
        render_export_bar(module,[("Telemetry Input",tel),("Stored Telemetry",stored)],tier,username)
    elif module=="Enterprise Security & Governance":
        tabs=st.tabs(["Posture","Roles","Audit"])
        with tabs[0]:
            st.json({"MFA":"Configurable","SSO/OIDC":"Configuration surface","SAML":"Configuration surface","SCIM":"Configuration surface","Workspace isolation":"Enabled by application role model","Audit logging":"Enabled","Data retention":"Configurable","Secrets":"Use Streamlit secrets/environment variables"})
        with tabs[1]:
            role=st.data_editor(st.session_state.setdefault("security_roles",pd.DataFrame({"Role":["Owner","Planner","Engineer","Viewer"],"Read":["Yes","Yes","Yes","Yes"],"Write":["Yes","Yes","Yes","No"],"Execute":["Yes","Yes","Yes","No"],"Admin":["Yes","No","No","No"]})),num_rows="dynamic",use_container_width=True,key="security_roles_editor")
            st.dataframe(role,use_container_width=True)
        with tabs[2]:
            with sqlite3.connect("enterprise_full_workspace.db") as c: audit=pd.read_sql("SELECT * FROM security_events ORDER BY id DESC LIMIT 200",c)
            st.dataframe(audit,use_container_width=True,hide_index=True)
            render_export_bar(module,[("Roles",role),("Security Events",audit)],tier,username)
