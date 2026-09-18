"""Shoir-IE platform upgrade services."""
import io, os, re, sqlite3, hashlib
from datetime import datetime
import pandas as pd
import numpy as np

TIER_ORDER=["Starter","Mid-Tier Pro","Enterprise","Research Pack"]
UPGRADE_MODULES={
"Excel Data Cleaning & Import":"Starter","Scenario Versioning":"Mid-Tier Pro","Localization & Multi-Currency":"Mid-Tier Pro",
"Advanced ML Demand Forecasting":"Enterprise","Stochastic & Monte Carlo Risk Modeling":"Enterprise","ERP & WMS API Connectors":"Enterprise",
"Team Workspaces & RBAC":"Enterprise","Executive Report Center":"Enterprise","Interactive DES Simulation Canvas":"Enterprise",
"Predictive Maintenance Digital Twin":"Enterprise","Owner Usage Analytics":"Enterprise",
"Multi-Echelon Inventory Optimization":"Enterprise","Carbon Footprint & ESG Accounting":"Mid-Tier Pro"
}

def tier_name(t):
    t=str(t or "Starter")
    return "Research Pack" if "Research" in t else "Enterprise" if "Enterprise" in t else "Mid-Tier Pro" if "Pro" in t else "Starter"
def tier_allows(current,required): return TIER_ORDER.index(tier_name(current))>=TIER_ORDER.index(required)

def ensure_upgrade_schema(db_path="enterprise_full_workspace.db"):
    with sqlite3.connect(db_path) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS module_usage_events(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT,module TEXT,action TEXT,tier TEXT,created_at TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS report_exports(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT,module TEXT,format TEXT,created_at TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS scenario_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT,scenario_name TEXT,module TEXT,payload_json TEXT,created_at TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS workspace_members(id INTEGER PRIMARY KEY AUTOINCREMENT,workspace_name TEXT,username TEXT,role TEXT,created_at TEXT,UNIQUE(workspace_name,username))")
        c.execute("CREATE TABLE IF NOT EXISTS integration_connections(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT,system_name TEXT,base_url TEXT,endpoint TEXT,method TEXT,status TEXT,last_sync_at TEXT,last_error TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS system_migrations(version INTEGER PRIMARY KEY,description TEXT,applied_at TEXT)")
        c.execute("INSERT OR IGNORE INTO system_migrations VALUES(1,?,?)",("Additive platform upgrade schema",datetime.utcnow().isoformat()))
        if c.execute("PRAGMA quick_check").fetchone()[0]!="ok": raise RuntimeError("SQLite integrity check failed")
        c.commit()
    return True

def record_module_usage(username,module,tier,action="open",db_path="enterprise_full_workspace.db"):
    if username:
        with sqlite3.connect(db_path) as c:
            c.execute("INSERT INTO module_usage_events(username,module,action,tier,created_at) VALUES(?,?,?,?,?)",(username,module,action,tier,datetime.utcnow().isoformat())); c.commit()
def record_report_export(username,module,fmt,db_path="enterprise_full_workspace.db"):
    with sqlite3.connect(db_path) as c:
        c.execute("INSERT INTO report_exports(username,module,format,created_at) VALUES(?,?,?,?)",(username,module,fmt,datetime.utcnow().isoformat())); c.commit()

def clean_dataframe(df):
    out=df.copy(); audit=[]; out.columns=[re.sub(r"\s+"," ",str(c).strip()) or "Unnamed" for c in out.columns]
    out=out.loc[~out.isna().all(axis=1)].copy(); out=out.drop(columns=[c for c in out.columns if out[c].isna().all()])
    for c in out.columns:
        if pd.api.types.is_object_dtype(out[c]) or pd.api.types.is_string_dtype(out[c]):
            out[c]=out[c].astype("string").str.replace(r"[\x00-\x1F\x7F]","",regex=True).str.strip()
            x=out[c].dropna().astype(str)
            n=pd.to_numeric(x.str.replace(",","",regex=False),errors="coerce")
            leading_zero_ratio=x.str.match(r"^0\d+$").mean() if len(x) else 0
            if len(x) and n.notna().mean()>=.85 and leading_zero_ratio<=.25:
                out[c]=pd.to_numeric(out[c].astype(str).str.replace(",","",regex=False),errors="coerce")
            mask=out[c].isin(["#N/A","#VALUE!","#DIV/0!","#REF!","#NAME?"]); out.loc[mask,c]=pd.NA
    out=out.drop_duplicates().reset_index(drop=True); audit.append({"Action":"Final dimensions","Details":f"{len(out)} rows × {len(out.columns)} columns"})
    return out,audit

def align_imported_table(imported, target):
    """Align uploaded CSV/XLSX columns to an existing module table without inventing values."""
    imported = imported.copy()
    target = target.copy()
    source_by_normalized = {}
    for col in imported.columns:
        source_by_normalized.setdefault(str(col).strip().lower(), col)
    rename = {}
    for target_col in target.columns:
        source_col = source_by_normalized.get(str(target_col).strip().lower())
        if source_col is not None:
            rename[source_col] = target_col
    imported = imported.rename(columns=rename)
    for col in target.columns:
        if col not in imported.columns:
            imported[col] = pd.NA
    ordered = [col for col in target.columns if col in imported.columns]
    extras = [col for col in imported.columns if col not in ordered]
    return imported[ordered + extras]

def _png(fig):
    try: return fig.to_image(format="png",width=1200,height=650,scale=2)
    except Exception: return None

def build_excel_report(title,tables,figures):
    from openpyxl import load_workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.drawing.image import Image as XLImage
    b=io.BytesIO()
    with pd.ExcelWriter(b,engine="openpyxl") as w:
        pd.DataFrame([{"Report":title,"Generated UTC":datetime.utcnow().isoformat()}]).to_excel(w,index=False,sheet_name="Summary")
        used={"Summary"}
        for label,df in tables:
            name=re.sub(r"[\\/*?:\[\]]","-",str(label))[:31] or "Data"; base=name; i=1
            while name in used: name=(base[:27]+f"-{i}"); i+=1
            used.add(name); df.to_excel(w,index=False,sheet_name=name)
    b.seek(0); wb=load_workbook(b); fill=PatternFill("solid",fgColor="1F4E78")
    for ws in wb.worksheets:
        ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]: cell.fill=fill; cell.font=Font(color="FFFFFF",bold=True); cell.alignment=Alignment(horizontal="center")
        for col in ws.columns: ws.column_dimensions[col[0].column_letter].width=min(55,max(10,max(len(str(x.value or "")) for x in col)+2))
    for i,(label,fig) in enumerate(figures,1):
        p=_png(fig)
        if p: wb.create_sheet(f"Chart {i}"[:31]).add_image(XLImage(io.BytesIO(p)),"A1")
    out=io.BytesIO(); wb.save(out); return out.getvalue()

def build_pdf_report(title,tables,figures):
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    b=io.BytesIO(); doc=SimpleDocTemplate(b,pagesize=landscape(A4)); styles=getSampleStyleSheet(); story=[Paragraph(title,styles["Title"]),Spacer(1,10)]
    for label,df in tables[:6]:
        d=df.head(25).fillna("").astype(str); t=Table([list(d.columns)]+d.values.tolist(),repeatRows=1); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#1F4E78")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.25,colors.grey),("FONTSIZE",(0,0),(-1,-1),7)])); story += [Paragraph(str(label),styles["Heading2"]),t,Spacer(1,8)]
    for label,fig in figures:
        p=_png(fig)
        if p: story += [Paragraph(str(label),styles["Heading2"]),Image(io.BytesIO(p),width=10.5*inch,height=5.5*inch)]
    doc.build(story); return b.getvalue()

def build_pptx_report(title,tables,figures):
    from pptx import Presentation
    from pptx.util import Inches
    prs=Presentation(); s=prs.slides.add_slide(prs.slide_layouts[0]); s.shapes.title.text=title; s.placeholders[1].text="Shoir-IE Executive Report"
    for label,fig in figures:
        p=_png(fig)
        if p:
            s=prs.slides.add_slide(prs.slide_layouts[5]); s.shapes.title.text=str(label); s.shapes.add_picture(io.BytesIO(p),Inches(.7),Inches(1.2),width=Inches(12))
    for label,df in tables[:5]:
        s=prs.slides.add_slide(prs.slide_layouts[5]); s.shapes.title.text=str(label); d=df.head(12).fillna("").astype(str); t=s.shapes.add_table(max(1,len(d)+1),max(1,len(d.columns)),Inches(.3),Inches(1.1),Inches(12.7),Inches(5.6)).table
        for j,c in enumerate(d.columns): t.cell(0,j).text=str(c)
        for i,row in enumerate(d.itertuples(index=False),1):
            for j,v in enumerate(row): t.cell(i,j).text=str(v)
    b=io.BytesIO(); prs.save(b); return b.getvalue()

_ORIG_EDITOR=None; _ORIG_DF=None; _ORIG_PLOT=None; _ORIG_STOP=None; _PATCHED=False
def _cap(module):
    import streamlit as st
    return st.session_state.setdefault("_upgrade_captures",{}).setdefault(module,{"tables":[],"figures":[]})

def _table_registry():
    import streamlit as st
    return st.session_state.setdefault("_upgrade_table_registry",{})

def _register_table(module, key, factory_key, label):
    reg=_table_registry().setdefault(module,{})
    reg[key]={"factory_key":factory_key,"label":label}

def _module_tools(module):
    import streamlit as st
    reg=_table_registry().get(module,{})
    if not reg: return
    st.markdown("---")
    st.subheader("🧰 Module Table Tools")
    labels=[v["label"] for v in reg.values()]
    keys=list(reg.keys())
    sel_key="upgrade_target_"+hashlib.sha1(module.encode()).hexdigest()[:10]
    selected_label=st.selectbox("Target table",labels,key=sel_key)
    selected_key=keys[labels.index(selected_label)]
    target=reg[selected_key]
    a,b=st.columns(2)
    with a:
        upload_key="upgrade_global_import_"+hashlib.sha1((module+selected_key).encode()).hexdigest()[:10]
        up=st.file_uploader("Import CSV / Excel into the selected table",type=["csv","xlsx"],key=upload_key)
        if up is not None:
            sig=hashlib.sha256(up.getvalue()).hexdigest()
            sig_key=upload_key+"_sig"
            if st.session_state.get(sig_key)!=sig:
                try:
                    raw=up.getvalue()
                    imp=pd.read_csv(io.BytesIO(raw)) if up.name.lower().endswith(".csv") else pd.read_excel(io.BytesIO(raw))
                    base=st.session_state[target["factory_key"]]
                    st.session_state[target["factory_key"]+"_active"]=align_imported_table(imp,base)
                    st.session_state[sig_key]=sig
                    st.success(f"Imported {len(imp):,} rows into {selected_label}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Import failed: {exc}")
    with b:
        reset_key="upgrade_global_reset_"+hashlib.sha1((module+selected_key).encode()).hexdigest()[:10]
        if st.button("↩️ Reset selected table",key=reset_key,use_container_width=True):
            st.session_state[target["factory_key"]+"_active"]=st.session_state[target["factory_key"]].copy(deep=True)
            st.rerun()
        reset_all_key="upgrade_global_reset_all_"+hashlib.sha1(module.encode()).hexdigest()[:10]
        if st.button("🧹 Reset all module tables",key=reset_all_key,use_container_width=True):
            for item in reg.values():
                st.session_state[item["factory_key"]+"_active"]=st.session_state[item["factory_key"]].copy(deep=True)
            st.rerun()
def init_upgrade_services():
    global _ORIG_EDITOR,_ORIG_DF,_ORIG_PLOT,_ORIG_STOP,_PATCHED
    import streamlit as st
    ensure_upgrade_schema()
    if _PATCHED:return
    _ORIG_EDITOR,_ORIG_DF,_ORIG_PLOT,_ORIG_STOP=st.data_editor,st.dataframe,st.plotly_chart,st.stop
    def editor(data,*a,**k):
        m=st.session_state.get("upgrade_current_module","Unknown"); key=str(k.get("key") or "table"); d=hashlib.sha1((m+"|"+key).encode()).hexdigest()[:10]; fk="up_factory_"+d; ik="up_import_"+d; sk=ik+"_sig"; rk="up_reset_"+d
        base=data.copy(deep=True) if isinstance(data,pd.DataFrame) else pd.DataFrame(data); st.session_state.setdefault(fk,base.copy(deep=True)); _register_table(m,key,fk,key)
        with st.expander("📥 Import / Reset this table"):
            up=st.file_uploader("Import CSV / Excel",type=["csv","xlsx"],key=ik)
            if up is not None:
                raw=up.getvalue(); sig=hashlib.sha256(raw).hexdigest()
                if st.session_state.get(sk)!=sig:
                    try:
                        imp=pd.read_csv(io.BytesIO(raw)) if up.name.lower().endswith(".csv") else pd.read_excel(io.BytesIO(raw))
                        target=st.session_state[fk]
                        imp=align_imported_table(imp, target)
                        st.session_state[fk+"_active"]=imp
                        st.session_state[sk]=sig
                        st.success(f"Imported {len(imp):,} rows.")
                    except Exception as e: st.error("Import failed: "+str(e))
            if st.button("↩️ Reset this table",key=rk,use_container_width=True): st.session_state[fk+"_active"]=st.session_state[fk].copy(deep=True); st.session_state.pop(sk,None); st.rerun()
        result=_ORIG_EDITOR(st.session_state.get(fk+"_active",data),*a,**k)
        if isinstance(result,pd.DataFrame): _cap(m)["tables"]=[x for x in _cap(m)["tables"] if x[0]!=key]; _cap(m)["tables"].append((key,result.copy(deep=True)))
        return result
    def df(data,*a,**k):
        r=_ORIG_DF(data,*a,**k); m=st.session_state.get("upgrade_current_module","Unknown")
        if isinstance(data,pd.DataFrame): _cap(m)["tables"].append((str(k.get("caption") or "Data Table"),data.copy(deep=True)))
        return r
    def plot(fig,*a,**k):
        m=st.session_state.get("upgrade_current_module","Unknown"); _cap(m)["figures"].append((str(k.get("key") or "Chart"),fig)); return _ORIG_PLOT(fig,*a,**k)
    def stop_with_report(*args,**kwargs):
        module=st.session_state.get("upgrade_current_module","Unknown")
        _module_tools(module)
        render_module_report_panel(module)
        return _ORIG_STOP(*args,**kwargs)
    st.data_editor,st.dataframe,st.plotly_chart,st.stop=editor,df,plot,stop_with_report; _PATCHED=True

def render_module_report_panel(module):
    import streamlit as st
    cap=_cap(module)
    if not cap["tables"] and not cap["figures"]: return
    st.markdown("---"); st.subheader("📥 Module Report & Export"); a,b,c=st.columns(3); user=st.session_state.get("current_user","unknown")
    with a:
        x=build_excel_report("Shoir-IE · "+module,cap["tables"],cap["figures"]); clicked=st.download_button("📊 Excel Report",x,"shoir_ie_report.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
        if clicked: record_report_export(user,module,"xlsx")
    with b:
        if tier_allows(st.session_state.get("user_tier"),"Enterprise"):
            y=build_pdf_report("Shoir-IE · "+module,cap["tables"],cap["figures"]); clicked=st.download_button("📄 PDF Report",y,"shoir_ie_report.pdf","application/pdf",use_container_width=True)
            if clicked: record_report_export(user,module,"pdf")
        else: st.info("PDF: Enterprise")
    with c:
        if tier_allows(st.session_state.get("user_tier"),"Enterprise"):
            z=build_pptx_report("Shoir-IE · "+module,cap["tables"],cap["figures"]); clicked=st.download_button("📽️ PowerPoint",z,"shoir_ie_report.pptx","application/vnd.openxmlformats-officedocument.presentationml.presentation",use_container_width=True)
            if clicked: record_report_export(user,module,"pptx")
        else: st.info("PowerPoint: Enterprise")

def _gate(module,req,cur):
    import streamlit as st
    if not tier_allows(cur,req): st.warning(f"🔒 {module} requires {req}. Your tier is {cur}. Upgrade in Subscriptions to unlock it."); return False
    return True

def _table(key,default):
    import streamlit as st
    st.session_state.setdefault(key,default.copy()); df=st.data_editor(st.session_state[key],num_rows="dynamic",use_container_width=True,key=key+"_editor"); st.session_state[key]=df; return df

def render_module_upgrade(module):
    import streamlit as st
    cur=st.session_state.get("user_tier","Starter"); req=UPGRADE_MODULES.get(module)
    if not req or not _gate(module,req,cur): return
    if module=="Excel Data Cleaning & Import":
        st.header("🧹 Excel Data Cleaning & Import"); df=_table("cleaner_df",pd.DataFrame({"Customer":["  Example  ","Example"],"Sales":["1,200","1,200"]}))
        if st.button("✨ Auto Clean & Professionalize",type="primary",use_container_width=True):
            st.session_state["cleaned"],st.session_state["audit"]=clean_dataframe(df); st.success("Workbook cleaned.")
        if "cleaned" in st.session_state:
            st.dataframe(st.session_state["cleaned"],use_container_width=True); st.download_button("📥 Download Cleaned Excel",build_excel_report("Cleaned Workbook",[("Cleaned Data",st.session_state["cleaned"]),("Cleaning Audit",pd.DataFrame(st.session_state["audit"]))],[]),"shoir_ie_cleaned.xlsx","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",type="primary",use_container_width=True)
    elif module=="Advanced ML Demand Forecasting":
        st.header("📈 Advanced ML Demand Forecasting"); df=_table("forecast_df",pd.DataFrame({"Date":pd.date_range("2026-01-01",periods=20),"SKU":["SKU-A"]*20,"Demand":np.arange(20)*3+100,"Promotion":[0]*20,"Temperature":[25]*20,"GDP_Index":[100]*20}))
        if st.button("🚀 Train & Forecast",type="primary",use_container_width=True):
            from sklearn.ensemble import RandomForestRegressor
            w=df.copy(); w["Date"]=pd.to_datetime(w["Date"],errors="coerce"); w["Demand"]=pd.to_numeric(w["Demand"],errors="coerce"); w=w.dropna(subset=["Date","Demand"]); w["week"]=w.Date.dt.isocalendar().week.astype(int); w["month"]=w.Date.dt.month; fs=["week","month"]+[c for c in ["Promotion","Temperature","GDP_Index"] if c in w.columns]
            if len(w)>=8:
                model=RandomForestRegressor(n_estimators=150,random_state=42); model.fit(w[fs].fillna(0),w.Demand); future=[]
                for i in range(1,9):
                    d=w.Date.max()+pd.Timedelta(weeks=i); row={"week":int(d.isocalendar().week),"month":d.month}; row.update({c:float(w[c].iloc[-1]) if c in w else 0 for c in fs[2:]}); future.append({"Date":d,"SKU":w.SKU.iloc[-1],"Forecast":max(0,float(model.predict(pd.DataFrame([row])[fs])[0]))})
                st.session_state["forecast_result"]=pd.DataFrame(future)
        if "forecast_result" in st.session_state:
            import plotly.express as px; st.dataframe(st.session_state["forecast_result"],use_container_width=True); st.plotly_chart(px.line(st.session_state["forecast_result"],x="Date",y="Forecast",color="SKU",markers=True,title="Demand Forecast"),use_container_width=True)
    elif module=="Stochastic & Monte Carlo Risk Modeling":
        st.header("🎲 Stochastic & Monte Carlo Risk Modeling"); df=_table("risk_df",pd.DataFrame([{"Scenario":"Baseline","Demand Mean":1000,"Demand Std":100,"Lead Time Mean":7,"Lead Time Std":1.5,"Disruption Probability":.05,"Disruption Multiplier":1.3}])); sims=st.slider("Simulations",500,20000,5000,500)
        if st.button("🎲 Run Simulation",type="primary",use_container_width=True):
            r=df.iloc[0]; rng=np.random.default_rng(42); d=rng.normal(float(r["Demand Mean"]),max(1,float(r["Demand Std"])),sims); l=rng.normal(float(r["Lead Time Mean"]),max(.1,float(r["Lead Time Std"])),sims); sh=rng.random(sims)<float(r["Disruption Probability"]); e=np.maximum(0,d)*np.where(sh,float(r["Disruption Multiplier"]),1)*(1+np.maximum(0,l-float(r["Lead Time Mean"]))/max(1,float(r["Lead Time Mean"]))); st.session_state["risk_result"]=pd.DataFrame([{"Percentile":f"P{q}","Risk Exposure":np.percentile(e,q)} for q in [50,90,95,99]]); st.session_state["risk_fig"]=__import__("plotly.express",fromlist=[""]).histogram(pd.DataFrame({"Exposure":e}),x="Exposure",nbins=50,title="Risk Exposure Distribution")
        if "risk_result" in st.session_state: st.dataframe(st.session_state["risk_result"],use_container_width=True); st.plotly_chart(st.session_state["risk_fig"],use_container_width=True)
    elif module=="Scenario Versioning":
        st.header("🧪 Scenario Versioning"); df=_table("scenario_df",pd.DataFrame([{"Parameter":"Demand Growth %","Baseline":5,"Scenario A":10},{"Parameter":"Lead Time","Baseline":7,"Scenario A":12},{"Parameter":"Capacity","Baseline":12000,"Scenario A":11000}])); name=st.text_input("Scenario name","New Scenario")
        if st.button("💾 Save Scenario",type="primary",use_container_width=True):
            with sqlite3.connect("enterprise_full_workspace.db") as c: c.execute("INSERT INTO scenario_versions(username,scenario_name,module,payload_json,created_at) VALUES(?,?,?,?,?)",(st.session_state.get("current_user","unknown"),name,module,df.to_json(orient="records"),datetime.utcnow().isoformat())); c.commit()
            st.success("Scenario saved.")
    elif module=="Team Workspaces & RBAC":
        st.header("👥 Team Workspaces & RBAC"); df=_table("workspace_df",pd.DataFrame([{"Workspace":"Operations","User":"planner","Role":"Editor"},{"Workspace":"Operations","User":"manager","Role":"Viewer"}]))
        if st.button("💾 Save Workspace",type="primary",use_container_width=True):
            with sqlite3.connect("enterprise_full_workspace.db") as c:
                for r in df.to_dict("records"): c.execute("INSERT OR REPLACE INTO workspace_members(workspace_name,username,role,created_at) VALUES(?,?,?,?,?)",(r["Workspace"],r["User"],r["Role"],datetime.utcnow().isoformat()))
                c.commit()
    elif module=="ERP & WMS API Connectors":
        st.header("🔌 ERP & WMS API Connectors"); df=_table("connector_df",pd.DataFrame([{"System":"SAP","Base URL":"","Endpoint":"/inventory","Method":"GET"},{"System":"Oracle","Base URL":"","Endpoint":"/inventory","Method":"GET"},{"System":"WMS","Base URL":"","Endpoint":"/stock","Method":"GET"}])); st.info("Configure your organization's endpoint; tokens are session-only.")
        system=st.selectbox("System",df.System.astype(str).tolist()); token=st.text_input("Bearer token",type="password")
        if st.button("🔄 Test Connector",type="primary",use_container_width=True):
            import requests
            row=df[df.System.astype(str)==system].iloc[0]; url=str(row["Base URL"]).strip().rstrip("/")+"/"+str(row["Endpoint"]).strip().lstrip("/"); status="Demo"; detail="No Base URL supplied."
            if str(row["Base URL"]).strip():
                try: rr=requests.get(url,headers={"Authorization":"Bearer "+token} if token else {},timeout=15); status=f"HTTP {rr.status_code}"; detail=rr.text[:500]
                except Exception as e: status="Connection error"; detail=str(e)
            st.write({"Status":status,"Detail":detail})
    elif module=="Localization & Multi-Currency":
        st.header("🌍 Localization & Multi-Currency"); rates=_table("rates_df",pd.DataFrame([{"Base":"USD","Target":"SAR","Rate":3.75},{"Base":"USD","Target":"EUR","Rate":.92}])); rules=_table("rules_df",pd.DataFrame([{"Region":"Saudi Arabia","Rule":"Commercial Invoice","Status":"Active"},{"Region":"EU","Rule":"HS Code Validation","Status":"Active"}])); base=st.text_input("Base","USD"); target=st.text_input("Target","SAR"); amount=st.number_input("Amount",0.0,1000000.0,1000.0)
        if st.button("💱 Convert",type="primary",use_container_width=True):
            q=rates[(rates.Base.astype(str).str.upper()==base.upper())&(rates.Target.astype(str).str.upper()==target.upper())]; st.metric("Converted",f"{amount*(1 if base.upper()==target.upper() else float(q.Rate.iloc[0])):,.2f} {target.upper()}") if not q.empty or base.upper()==target.upper() else st.error("Add the FX pair to the rate table first.")
    elif module=="Interactive DES Simulation Canvas":
        st.header("🏭 Interactive DES Simulation Canvas"); nodes=_table("des_df",pd.DataFrame([{"Node":"Receiving","Capacity":1000,"Service Time":2,"X":0,"Y":1},{"Node":"Assembly","Capacity":80,"Service Time":7,"X":1,"Y":1},{"Node":"Packing","Capacity":60,"Service Time":9,"X":2,"Y":1}])); import plotly.express as px; st.plotly_chart(px.scatter(nodes,x="X",y="Y",text="Node",title="Process Canvas"),use_container_width=True)
        if st.button("▶️ Simulate",type="primary",use_container_width=True): st.metric("Estimated throughput / hr",round(float((60/pd.to_numeric(nodes["Service Time"],errors="coerce").fillna(1)*pd.to_numeric(nodes["Capacity"],errors="coerce").fillna(1)).min()),2))
    elif module=="Predictive Maintenance Digital Twin":
        st.header("🛠️ Predictive Maintenance Digital Twin"); df=_table("maintenance_df",pd.DataFrame({"Timestamp":pd.date_range("2026-07-01",periods=30,freq="h"),"Machine":["M-101"]*30,"Vibration":np.linspace(2,3,30),"Temperature":np.linspace(65,75,30),"Pressure":[205]*30,"Run Hours":range(30)}))
        if st.button("🔬 Estimate RUL",type="primary",use_container_width=True):
            v=float(pd.to_numeric(df.Vibration,errors="coerce").iloc[-1]); med=max(.1,float(pd.to_numeric(df.Vibration,errors="coerce").median())); st.session_state["maint_result"]=pd.DataFrame([{"Machine":df.Machine.iloc[-1],"Failure Risk":min(.99,max(.01,v/(med*1.6))),"Estimated RUL Hours":max(4,168/(.6*v/med+.4))}])
        if "maint_result" in st.session_state: st.dataframe(st.session_state["maint_result"],use_container_width=True)
    elif module=="Owner Usage Analytics":
        st.header("📊 Owner Usage Analytics")
        with sqlite3.connect("enterprise_full_workspace.db") as c: usage=pd.read_sql("SELECT module,action,tier,created_at FROM module_usage_events",c); signups=pd.read_sql("SELECT tier,status,timestamp FROM pending_payments",c); exports=pd.read_sql("SELECT module,format,created_at FROM report_exports",c)
        st.metric("Module events",len(usage)); st.metric("Signup requests",len(signups)); st.metric("Report exports",len(exports))
        if not usage.empty:
            import plotly.express as px; counts=usage.groupby("module",as_index=False).size(); st.plotly_chart(px.bar(counts,x="module",y="size",title="Module usage"),use_container_width=True); usage["created_at"]=pd.to_datetime(usage.created_at,errors="coerce"); tr=usage.dropna(subset=["created_at"]).assign(day=lambda x:x.created_at.dt.date).groupby("day",as_index=False).size(); st.plotly_chart(px.line(tr,x="day",y="size",markers=True,title="Usage over time"),use_container_width=True)
    elif module=="Executive Report Center":
        st.header("📚 Executive Report Center"); caps=st.session_state.get("_upgrade_captures",{}); choices=[k for k,v in caps.items() if v["tables"] or v["figures"]]
        if choices: render_module_report_panel(st.selectbox("Module output",choices))
