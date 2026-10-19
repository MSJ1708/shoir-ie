"""Shoir-IE Platform Excellence Hub.

A calm, high-density command surface for the cross-cutting capabilities that make
the engineering modules feel like one product: digital thread, governance,
experiments, verification, decisions, Copilot controls, exports and platform health.
"""
from __future__ import annotations

import io
import json
import hashlib
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

from industrial_experience import (
    FEATURES_60,
    COPILOT_TOOLS,
    ensure_experience_db,
    feature_catalog,
    feature_stats,
    create_job,
    update_job,
    create_decision,
    transition_decision,
    add_comment,
    log_copilot_action,
    save_project,
    autosave_project,
    compute_evidence_roi,
    verification_snapshot,
)


def _db():
    ensure_experience_db()
    return sqlite3.connect("enterprise_full_workspace.db", timeout=30)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _key(text: str) -> str:
    return hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:10]


def _init_extra_tables() -> None:
    with _db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS excellence_entities("
            "entity_id TEXT PRIMARY KEY, entity_type TEXT, name TEXT, status TEXT,"
            "payload_json TEXT, owner TEXT, created_at TEXT, updated_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS excellence_edges("
            "edge_id TEXT PRIMARY KEY, source_id TEXT, target_id TEXT, relation TEXT,"
            "owner TEXT, created_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS excellence_connectors("
            "connector_id TEXT PRIMARY KEY, name TEXT, connector_type TEXT, status TEXT,"
            "freshness_min REAL, error_rate REAL, last_sync TEXT, owner TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS excellence_benchmarks("
            "benchmark_id TEXT PRIMARY KEY, name TEXT, metric TEXT, value REAL,"
            "unit TEXT, source TEXT, observed_at TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS excellence_memory("
            "memory_id TEXT PRIMARY KEY, problem TEXT, decision TEXT, outcome TEXT,"
            "lesson TEXT, owner TEXT, created_at TEXT)"
        )
        conn.commit()


def _seed() -> None:
    _init_extra_tables()
    with _db() as conn:
        if conn.execute("SELECT COUNT(*) FROM excellence_connectors").fetchone()[0] == 0:
            rows = [
                ("CON-ERP", "ERP / MRP", "Ready", 4.2, 0.0),
                ("CON-WMS", "WMS / Inventory", "Ready", 7.8, 0.2),
                ("CON-IOT", "IoT / Telemetry", "Monitor", 18.4, 0.8),
            ]
            for cid, name, status, fresh, err in rows:
                conn.execute(
                    "INSERT INTO excellence_connectors VALUES(?,?,?,?,?,?,?,?)",
                    (cid, name, "Enterprise", status, fresh, err, _now(), "platform"),
                )
        if conn.execute("SELECT COUNT(*) FROM excellence_entities").fetchone()[0] == 0:
            entities = [
                ("FAC-001", "Facility", "Main Plant", "Active"),
                ("WC-001", "Work Center", "Assembly Line A", "Active"),
                ("SKU-001", "SKU", "Industrial Pump P-100", "Active"),
                ("SUP-001", "Supplier", "Primary Supplier", "Active"),
                ("ASSET-001", "Asset", "CNC-01", "Active"),
                ("SCN-BASE", "Scenario", "Baseline", "Baseline"),
            ]
            for eid, etype, name, status in entities:
                conn.execute(
                    "INSERT INTO excellence_entities VALUES(?,?,?,?,?,?,?,?)",
                    (eid, etype, name, status, "{}", "platform", _now(), _now()),
                )
        if conn.execute("SELECT COUNT(*) FROM excellence_edges").fetchone()[0] == 0:
            edges = [
                ("FAC-001", "WC-001", "contains"),
                ("WC-001", "ASSET-001", "uses"),
                ("SKU-001", "WC-001", "produced_by"),
                ("SUP-001", "SKU-001", "supplies"),
                ("SCN-BASE", "FAC-001", "evaluates"),
            ]
            for source, target, relation in edges:
                conn.execute(
                    "INSERT INTO excellence_edges VALUES(?,?,?,?,?,?)",
                    ("EDGE-" + uuid.uuid4().hex[:10].upper(), source, target, relation, "platform", _now()),
                )
        conn.commit()


def _metric_status(score: float) -> str:
    if score >= 90:
        return "Healthy"
    if score >= 75:
        return "Watch"
    return "Action"


def _hero(username: str, tier: str) -> None:
    stats = feature_stats()
    st.markdown(
        f"""
        <div class="px-hero">
          <div class="px-kicker">SHOIR-IE · PLATFORM EXCELLENCE</div>
          <div class="px-title">The industrial engineering command layer.</div>
          <div class="px-sub">One calm workspace for data → models → experiments → decisions → implementation → verified results.</div>
          <div class="px-pills">
            <span>✓ {stats["implemented"]}/60 catalog entries marked Implemented</span>
            <span>◈ Evidence-first</span>
            <span>⌁ {tier}</span>
            <span>● Workspace · {username}</span>
          </div>
        </div>
        <style>
        .px-hero{{position:relative;overflow:hidden;padding:28px 30px;border-radius:24px;
          background:linear-gradient(135deg,#07111f 0%,#172554 54%,#0f766e 100%);
          color:#fff;border:1px solid rgba(255,255,255,.10);box-shadow:0 22px 55px rgba(15,23,42,.16);margin-bottom:16px}}
        .px-hero:before{{content:"";position:absolute;width:360px;height:360px;right:-150px;top:-210px;border-radius:50%;
          background:radial-gradient(circle,rgba(125,211,252,.18),transparent 68%);animation:pxFloat 10s ease-in-out infinite}}
        .px-hero:after{{content:"";position:absolute;inset:0;background:linear-gradient(105deg,transparent 35%,rgba(255,255,255,.08) 50%,transparent 65%);
          transform:translateX(-130%);animation:pxShine 9s ease-in-out infinite}}
        .px-kicker{{position:relative;font-size:11px;font-weight:900;letter-spacing:.12em;color:#7dd3fc}}
        .px-title{{position:relative;font-size:31px;font-weight:900;line-height:1.12;margin-top:5px;letter-spacing:-.03em}}
        .px-sub{{position:relative;color:#dbeafe;font-size:14px;margin-top:9px;max-width:940px}}
        .px-pills{{position:relative;display:flex;gap:9px;flex-wrap:wrap;margin-top:15px}}
        .px-pills span{{font-size:11px;font-weight:750;padding:6px 10px;border-radius:999px;background:rgba(255,255,255,.08);
          border:1px solid rgba(255,255,255,.12);color:#e2e8f0}}
        @keyframes pxShine{{0%,62%{{transform:translateX(-130%)}}82%,100%{{transform:translateX(130%)}}}}
        @keyframes pxFloat{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(18px)}}}}
        @media(prefers-reduced-motion:reduce){{.px-hero:after,.px-hero:before{{animation:none}}}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _overview(username: str) -> None:
    stats = feature_stats()
    with _db() as conn:
        counts = {
            "projects": conn.execute(
                "SELECT COUNT(*) FROM experience_projects WHERE owner=?", (username,)
            ).fetchone()[0],
            "decisions": conn.execute(
                "SELECT COUNT(*) FROM experience_decisions WHERE owner=?", (username,)
            ).fetchone()[0],
            "jobs": conn.execute(
                "SELECT COUNT(*) FROM experience_jobs WHERE owner=?", (username,)
            ).fetchone()[0],
            "copilot": conn.execute(
                "SELECT COUNT(*) FROM experience_copilot_actions WHERE actor=?", (username,)
            ).fetchone()[0],
            "lineage": conn.execute(
                "SELECT COUNT(*) FROM experience_lineage WHERE actor=?", (username,)
            ).fetchone()[0],
        }
        run_status = pd.read_sql_query(
            """SELECT status, COUNT(*) AS count
               FROM experience_module_runs WHERE owner=?
               GROUP BY status ORDER BY status""",
            conn,
            params=(username,),
        )
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Catalog labels", f'{stats["implemented"]}/60', "source metadata; not runtime tests")
    c2.metric("Your studies", f'{counts["projects"]:,}', "saved")
    c3.metric("Your decisions", f'{counts["decisions"]:,}', "governed")
    c4.metric("Your jobs", f'{counts["jobs"]:,}', "owned records")
    c5.metric("Your lineage links", f'{counts["lineage"]:,}', "attributed records")

    st.caption("Workspace counts are filtered to this account. Catalog statuses are source-declared labels, not module readiness certification.")
    left, right = st.columns([1.05, 1.95])
    with left:
        st.markdown("#### Your recorded module runs")
        if run_status.empty:
            st.info("No module-run records are saved for this account yet. No workflow coverage percentage is inferred.")
        else:
            fig = px.bar(
                run_status, x="status", y="count", text="count",
                title="Recorded runs by status",
            )
            fig.update_layout(height=260, margin=dict(l=8,r=8,t=35,b=8), xaxis_title=None, yaxis_title="Recorded runs")
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with right:
        st.markdown("#### Capability status declarations")
        catalog = feature_catalog().copy()
        catalog["Group"] = catalog["Feature"].str.extract(r"^(.+?)(?: /| &|,|$)")[0]
        groups = catalog.groupby("Status", as_index=False).size().rename(columns={"size":"Count"})
        fig = px.bar(groups, x="Status", y="Count", text="Count")
        fig.update_layout(height=260, margin=dict(l=8,r=8,t=15,b=8), xaxis_title=None, yaxis_title="Catalog entries")
        fig.update_traces(textposition="outside")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.caption("Counts show static catalog labels. They do not prove runtime functionality or authenticated verification.")

    st.markdown("#### What changed")
    items = [
        ("✓", "Supported workflows can record source and run evidence.", "Evidence"),
        ("✓", "Decision records can preserve assumptions and approval transitions.", "Decision"),
        ("✓", "Evidence-bundle export paths exist for supported workflows.", "Reporting"),
        ("✓", "Copilot previews are logged; execution controls remain workflow-specific.", "AI"),
    ]
    cols = st.columns(4)
    for col, (icon, title, tag) in zip(cols, items):
        col.markdown(
            f'<div class="px-card"><div class="px-icon">{icon}</div><b>{title}</b><div class="px-tag">{tag}</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        """<style>
        .px-card{min-height:105px;padding:15px;border:1px solid #dbe4f0;border-radius:16px;background:linear-gradient(145deg,#fff,#f8fbff);
        box-shadow:0 7px 20px rgba(15,23,42,.05);transition:.18s ease}.px-card:hover{transform:translateY(-2px);box-shadow:0 12px 26px rgba(15,23,42,.09)}
        .px-icon{font-size:20px;margin-bottom:7px}.px-tag{margin-top:9px;font-size:10px;color:#0f766e;font-weight:800;text-transform:uppercase;letter-spacing:.07em}
        </style>""",
        unsafe_allow_html=True,
    )


    with st.expander("🧪 Benchmark Laboratory", expanded=False):
        _benchmark_lab(username)
    with st.expander("📊 Visualization Readiness Audit", expanded=False):
        _visualization_readiness(username)


def _benchmark_lab(username: str) -> None:
    st.markdown("### 🧪 Benchmark Laboratory")
    st.caption("Deterministic synthetic engineering workloads for runtime/reproducibility validation. These results are not customer ROI claims.")
    from benchmark_harness import run_standard_benchmarks
    if st.button("▶️ Run standard engineering benchmarks", type="primary", use_container_width=True, key="px_run_standard_benchmarks"):
        with st.spinner("Running deterministic platform benchmarks..."):
            st.session_state["px_benchmark_results"] = run_standard_benchmarks(repetitions=3, rows=10000)
    results = st.session_state.get("px_benchmark_results")
    if isinstance(results, pd.DataFrame) and not results.empty:
        st.dataframe(
            results[["label","benchmark_type","dataset_rows","mean_ms","median_ms","p95_ms","min_ms","max_ms"]].rename(
                columns={"label":"Benchmark","benchmark_type":"Type","dataset_rows":"Rows","mean_ms":"Mean ms","median_ms":"Median ms","p95_ms":"P95 ms","min_ms":"Min ms","max_ms":"Max ms"}
            ),
            use_container_width=True,
            hide_index=True,
        )
        fig = px.bar(results, x="label", y="mean_ms", title="Standard Benchmark Runtime")
        fig.update_layout(xaxis_title=None, yaxis_title="Mean runtime (ms)")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.download_button(
            "📥 Download benchmark evidence (CSV)",
            results.to_csv(index=False).encode("utf-8"),
            "shoir_ie_standard_benchmark_evidence.csv",
            "text/csv",
            use_container_width=True,
            key="px_download_benchmark_results",
        )


def _visualization_readiness(username: str) -> None:
    st.markdown("### 📊 Universal Visualization Readiness")
    st.caption("Every populated registered table must produce a real graph; empty modules are shown as ready for incoming data.")
    from shoir_live_visuals import audit_all_module_visualizations, visualization_readiness_summary
    summary = visualization_readiness_summary(max_figures=4)
    v1, v2, v3, v4 = st.columns(4)
    v1.metric("Catalog modules", f'{summary["modules"]:,}')
    v2.metric("Verified", f'{summary["verified"]:,}')
    v3.metric("Awaiting data", f'{summary["awaiting_data"]:,}')
    v4.metric("Gaps", f'{summary["gaps"]:,}')
    audit = audit_all_module_visualizations(max_figures=4)
    if not audit.empty:
        st.dataframe(audit, use_container_width=True, hide_index=True)
        if int(summary["gaps"]) == 0:
            st.success("No populated module table is currently graphless.")
        else:
            st.warning(f'{summary["gaps"]:,} populated module table(s) require visualization work.')


def _digital_thread(username: str) -> None:
    st.markdown("### 🔗 Digital Thread")
    st.caption("Shared seeded examples plus entities and relationships owned by this account. Seeded examples are illustrative, not customer evidence.")
    with _db() as conn:
        entities = pd.read_sql(
            "SELECT entity_id,entity_type,name,status,owner,updated_at FROM excellence_entities WHERE owner=? OR owner='platform' ORDER BY entity_type,name",
            conn, params=(username,),
        )
        edges = pd.read_sql(
            "SELECT source_id,target_id,relation,created_at FROM excellence_edges WHERE owner=? OR owner='platform' ORDER BY created_at DESC",
            conn, params=(username,),
        )
    c1, c2, c3 = st.columns(3)
    c1.metric("Entities", len(entities), "shared IDs")
    c2.metric("Relationships", len(edges), "traceable")
    c3.metric("Entity types", entities["entity_type"].nunique() if not entities.empty else 0, "canonical")

    left, right = st.columns([1.15, 1])
    with left:
        st.dataframe(entities, use_container_width=True, hide_index=True)
    with right:
        st.dataframe(edges, use_container_width=True, hide_index=True)
        if not edges.empty:
            st.plotly_chart(
                px.bar(edges.groupby("relation", as_index=False).size().rename(columns={"size":"Links"}),
                       x="relation", y="Links", text="Links"),
                use_container_width=True, config={"displayModeBar": False},
            )

    with st.expander("➕ Add an industrial entity", expanded=False):
        a,b,c = st.columns(3)
        etype = a.selectbox("Entity type", ["Product","SKU","BOM","Customer","Order","Supplier","Material","Facility","Warehouse","Machine","Work Center","Operation","Routing","Employee","Skill","Asset","Maintenance Event","Quality Event","Shipment","Route","Scenario","Experiment","Model Run","Decision"])
        name = b.text_input("Name", key="thread_entity_name")
        status = c.selectbox("Status", ["Active","Draft","Watch","Archived"])
        if st.button("Create entity", type="primary", use_container_width=True):
            if not name.strip():
                st.warning("Give the entity a name first.")
            else:
                eid = etype.upper().replace(" ","-")[:8] + "-" + uuid.uuid4().hex[:8].upper()
                with _db() as conn:
                    conn.execute("INSERT INTO excellence_entities VALUES(?,?,?,?,?,?,?,?)",
                                 (eid, etype, name.strip(), status, "{}", username, _now(), _now()))
                    conn.commit()
                st.success(f"Created {eid}")
                st.rerun()

    st.info("Impact tracing is relationship-based: the same entity ID can be reused by optimization, simulation, quality, sustainability and reporting workflows.")


def _data_lab(username: str) -> None:
    st.markdown("### 🧪 Data & Experiment Lab")
    st.caption("Validate a dataset, quantify uncertainty, sweep scenarios and preserve a reproducible run record.")
    upload = st.file_uploader("Upload CSV for validation", type=["csv"], key="px_data_upload")
    if upload is not None:
        try:
            df = pd.read_csv(upload)
        except Exception as exc:
            st.error(f"Could not read this CSV safely: {exc}")
            return
    else:
        df = pd.DataFrame({
            "Scenario": ["Baseline","Stress +10%","Stress +20%","Recovery"],
            "Demand": [1000,1100,1200,1080],
            "Capacity": [1100,1100,1100,1150],
            "Service": [97.2,94.8,89.1,96.0],
        })

    check = verification_snapshot(df)
    q1,q2,q3,q4 = st.columns(4)
    q1.metric("Rows", f'{len(df):,}')
    q2.metric("Columns", f'{len(df.columns):,}')
    q3.metric("Verification", f'{check["score"]:.0f}%')
    q4.metric("Missing cells", f'{int(df.isna().sum().sum()):,}')
    st.dataframe(df, use_container_width=True, hide_index=True)

    nums = list(df.select_dtypes(include=np.number).columns)
    if nums:
        metric = st.selectbox("Response metric", nums, key="px_exp_metric")
        fig = px.line(df, x=df.columns[0], y=metric, markers=True, title=f"Scenario response · {metric}")
        fig.update_layout(height=300, margin=dict(l=8,r=8,t=45,b=8))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    a,b,c = st.columns(3)
    if a.button("✅ Validate & register", type="primary", use_container_width=True):
        run = "RUN-" + uuid.uuid4().hex[:12].upper()
        with _db() as conn:
            conn.execute(
                "INSERT INTO experience_observability(run_id,module,event_type,duration_ms,details_json,created_at) VALUES(?,?,?,?,?,?)",
                (run, "Platform Excellence", "dataset_validation", 0.0,
                 json.dumps({"verification": check, "rows": len(df), "columns": list(df.columns)}), _now()),
            )
            conn.commit()
        st.session_state["px_last_run"] = run
        st.success(f"Validation recorded · {run}")
    if b.button("🧪 Queue experiment", use_container_width=True):
        jid = create_job("Platform Excellence", "scenario-sweep", username, {"rows": len(df), "metric": nums[0] if nums else None})
        update_job(jid, "Running", 25, "Experiment prepared", actor=username)
        st.session_state["px_job"] = jid
        st.success(f"Experiment queued · {jid}")
    if c.button("💾 Save study", use_container_width=True):
        pid = save_project("Platform Excellence Study", "Platform Excellence", username, {"rows": len(df), "verification": check})
        st.session_state["px_project"] = pid
        st.success(f"Study saved · {pid}")

    st.markdown("#### Transparent value model")
    r1,r2,r3 = st.columns(3)
    volume = r1.number_input("Monthly volume", min_value=0.0, value=1000.0, step=100.0)
    unit_cost = r2.number_input("Baseline unit value", min_value=0.0, value=100.0, step=5.0)
    delta = r3.number_input("Assumed change (%)", min_value=-100.0, max_value=100.0, value=5.0, step=0.5)
    roi = compute_evidence_roi(volume, unit_cost, delta)
    x1,x2 = st.columns(2)
    x1.metric("Baseline monthly value", f'{roi["baseline_monthly_value"]:,.0f}')
    x2.metric("Illustrative annual impact", f'{roi["illustrative_annual_impact"]:,.0f}')
    st.caption("Illustrative only: the value model exposes the assumptions instead of presenting an unsupported guaranteed savings claim.")


def _governance(username: str, tier: str) -> None:
    st.markdown("### 🛡️ Governance, Decisions & Copilot")
    st.caption("Move from analysis to an auditable decision without hiding assumptions or approval state.")
    tab1, tab2, tab3, tab4 = st.tabs(["Decision cards","Copilot","Approval flow","Decision memory"])

    with tab1:
        with _db() as conn:
            decisions = pd.read_sql("SELECT decision_id,title,module,status,owner,created_at,updated_at FROM experience_decisions WHERE owner=? ORDER BY updated_at DESC", conn, params=(username,))
        if decisions.empty:
            st.info("No decision cards yet. Create one from the action bar below.")
        else:
            st.dataframe(decisions, use_container_width=True, hide_index=True)
            did = st.selectbox("Decision", decisions["decision_id"].tolist(), key="px_decision_pick")
            status = decisions.loc[decisions["decision_id"] == did, "status"].iloc[0]
            next_state = st.selectbox("Move to", ["Validated","Proposed","Review","Approved","Implemented","Verified"], key="px_decision_next")
            comment = st.text_input("Approval note", key="px_decision_note")
            if st.button("➡️ Transition decision", type="primary", use_container_width=True):
                try:
                    transition_decision(did, username, next_state, comment)
                    st.success(f"Decision moved to {next_state}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Transition blocked safely: {exc}")
            st.caption(f"Current state: {status}")

        a,b = st.columns(2)
        if a.button("📝 Create decision card", use_container_width=True):
            did = create_decision("Platform Excellence decision", "Platform Excellence",
                                  {"verification": "Pending"}, {"tier": tier},
                                  {"uncertainty": "Document in review"}, username)
            st.success(f"Created {did}")
            st.rerun()
        if b.button("💬 Add workspace comment", use_container_width=True):
            add_comment(None, st.session_state.get("px_selected_decision"), username, "Operator comment captured from Excellence Hub.")
            st.toast("Comment saved", icon="💬")

    with tab2:
        st.markdown("#### Approval-gated Copilot toolbelt")
        tools = pd.DataFrame(COPILOT_TOOLS, columns=["Tool","Scope","Approval"])
        st.dataframe(tools, use_container_width=True, hide_index=True)
        action = st.selectbox("Preview action", tools["Tool"].tolist(), key="px_copilot_action")
        if st.button("🤖 Stage Copilot action", type="primary", use_container_width=True):
            rid = log_copilot_action("Platform Excellence", action, username, True, "Preview",
                                     {"source":"Excellence Hub","tier":tier})
            st.session_state["px_copilot_run"] = rid
            st.info(f"Preview staged · {rid} · approval required")
        st.markdown("**Guardrail:** imported text is data; execution requires an explicit approval event.")

    with tab3:
        states = ["Draft","Validated","Proposed","Review","Approved","Implemented","Verified"]
        cols = st.columns(len(states))
        for i, state in enumerate(states):
            cols[i].markdown(f'<div class="px-state">{"✓" if i < 1 else "○"}<br><small>{state}</small></div>', unsafe_allow_html=True)
        st.caption("Reference lifecycle only. The selected decision's actual state is shown above; each saved transition is written to the approval history.")
        st.markdown("#### Workspace comments")
        with _db() as conn:
            comments = pd.read_sql(
                """SELECT c.actor,c.comment,c.created_at
                   FROM experience_comments AS c
                   WHERE c.decision_id IN (
                       SELECT decision_id FROM experience_decisions WHERE owner=?
                   )
                   OR c.project_id IN (
                       SELECT project_id FROM experience_projects WHERE owner=?
                   )
                   OR (c.decision_id IS NULL AND c.project_id IS NULL AND c.actor=?)
                   ORDER BY c.id DESC LIMIT 12""",
                conn, params=(username, username, username),
            )
        st.dataframe(comments, use_container_width=True, hide_index=True)

    with tab4:
        with _db() as conn:
            memory = pd.read_sql("SELECT memory_id,problem,decision,outcome,lesson,owner,created_at FROM excellence_memory WHERE owner=? ORDER BY created_at DESC", conn, params=(username,))
        if memory.empty:
            st.info("Decision Memory is ready. Record the first verified lesson after an implementation.")
        else:
            st.dataframe(memory, use_container_width=True, hide_index=True)
        with st.form("px_memory_form"):
            problem = st.text_input("Problem")
            decision = st.text_input("Decision")
            outcome = st.text_input("Actual outcome")
            lesson = st.text_area("Lesson learned")
            if st.form_submit_button("💡 Save lesson", type="primary"):
                if not problem.strip() or not lesson.strip():
                    st.warning("Problem and lesson are required.")
                else:
                    mid = "MEM-" + uuid.uuid4().hex[:12].upper()
                    with _db() as conn:
                        conn.execute("INSERT INTO excellence_memory VALUES(?,?,?,?,?,?)",
                                     (mid, problem.strip(), decision.strip(), outcome.strip(), lesson.strip(), username, _now()))
                        conn.commit()
                    st.success(f"Lesson saved · {mid}")
                    st.rerun()


def _self_diagnostic_report() -> pd.DataFrame:
    """Run real structural checks and explicitly mark checks not performed."""
    records: list[dict[str, str]] = []
    try:
        with _db() as conn:
            integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
            table_names = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            job_columns = {
                str(row[1]) for row in conn.execute("PRAGMA table_info(experience_jobs)")
            }
        required_tables = {
            "experience_projects", "experience_decisions", "experience_jobs",
            "experience_copilot_actions", "experience_lineage",
            "experience_module_runs",
        }
        missing_tables = sorted(required_tables - table_names)
        records.extend([
            {
                "Check": "SQLite integrity",
                "Status": "PASS" if integrity.lower() == "ok" else "FAIL",
                "Evidence": integrity,
            },
            {
                "Check": "Required experience tables",
                "Status": "PASS" if not missing_tables else "FAIL",
                "Evidence": "All present" if not missing_tables else "Missing: " + ", ".join(missing_tables),
            },
            {
                "Check": "Job owner column",
                "Status": "PASS" if "owner" in job_columns else "FAIL",
                "Evidence": "Owner column present" if "owner" in job_columns else "Owner column missing",
            },
        ])
    except Exception as exc:
        records.extend([
            {"Check": "SQLite integrity", "Status": "FAIL", "Evidence": f"Check raised {type(exc).__name__}"},
            {"Check": "Required experience tables", "Status": "FAIL", "Evidence": "Schema inspection failed"},
            {"Check": "Job owner column", "Status": "FAIL", "Evidence": "Schema inspection failed"},
        ])

    records.extend([
        {
            "Check": "Feature catalog declarations",
            "Status": "PASS" if len(FEATURES_60) == 60 else "REVIEW",
            "Evidence": f"{len(FEATURES_60)} declared rows; module behavior was not tested",
        },
        {
            "Check": "Copilot tool registry",
            "Status": "PASS" if len(COPILOT_TOOLS) >= 8 else "REVIEW",
            "Evidence": f"{len(COPILOT_TOOLS)} declared tool entries; execution was not tested",
        },
        {
            "Check": "Live connector connectivity",
            "Status": "NOT TESTED",
            "Evidence": "Stored profile/demo metadata is not evidence of a live handshake",
        },
        {
            "Check": "Authenticated imports, exports and tenant isolation",
            "Status": "NOT TESTED",
            "Evidence": "Requires authorized integration/browser walkthroughs",
        },
    ])
    return pd.DataFrame(records)


def _platform_health(username: str) -> None:
    st.markdown("### ⚙️ Platform Health & Delivery")
    with _db() as conn:
        connectors = pd.read_sql(
            """SELECT name,connector_type,status,freshness_min,error_rate,last_sync,owner
               FROM excellence_connectors WHERE owner=? OR owner='platform'""",
            conn, params=(username,),
        )
        jobs = pd.read_sql(
            """SELECT job_id,module,job_type,status,progress,message,started_at,finished_at
               FROM experience_jobs WHERE owner=? ORDER BY rowid DESC LIMIT 20""",
            conn, params=(username,),
        )
        job_count = int(conn.execute(
            "SELECT COUNT(*) FROM experience_jobs WHERE owner=?", (username,)
        ).fetchone()[0])
        run_count = int(conn.execute(
            "SELECT COUNT(*) FROM experience_module_runs WHERE owner=?", (username,)
        ).fetchone()[0])
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])

    if not connectors.empty:
        connectors["Evidence"] = connectors["owner"].map(
            lambda owner: (
                "Seeded sample metadata — no live connection test"
                if str(owner) == "platform"
                else "Saved profile metadata — live connection not verified"
            )
        )

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Connector profiles", f"{len(connectors):,}", "live connectivity unverified")
    c2.metric("Your jobs", f"{job_count:,}", "owner-scoped")
    c3.metric("Your recorded runs", f"{run_count:,}", "owner-scoped")
    c4.metric("SQLite integrity", "PASS" if integrity.lower() == "ok" else "CHECK", "PRAGMA integrity_check")

    a,b = st.columns(2)
    with a:
        st.markdown("#### Stored connector metadata")
        st.caption("Freshness and error values below are stored metadata. Seeded demo rows are not live connectivity measurements.")
        if not connectors.empty:
            fig = px.bar(
                connectors, x="name", y="freshness_min", text="freshness_min",
                title="Stored freshness metadata (minutes; not live-tested)",
            )
            fig.update_layout(height=280, margin=dict(l=8,r=8,t=45,b=8), yaxis_title="Stored minutes")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.dataframe(connectors, use_container_width=True, hide_index=True)
        else:
            st.info("No connector profiles are saved for this account.")

    with b:
        st.markdown("#### Your recent jobs")
        if jobs.empty:
            st.info("No owned job records are available for this account. Existing legacy jobs without owner metadata are retained but not shown in another user's workspace.")
        else:
            st.dataframe(jobs, use_container_width=True, hide_index=True)
            if st.button("🛑 Cancel newest queued job", use_container_width=True):
                queued = jobs[jobs["status"] == "Queued"]
                if not queued.empty:
                    try:
                        update_job(
                            str(queued.iloc[0]["job_id"]),
                            "Cancelled",
                            float(queued.iloc[0]["progress"]),
                            "Cancelled by operator",
                            actor=username,
                        )
                        st.success("Your queued job was cancelled.")
                        st.rerun()
                    except PermissionError:
                        st.error("The job could not be updated because it is not owned by this account.")
                else:
                    st.info("No queued jobs owned by this account need cancellation.")

    st.markdown("#### Delivery verification status")
    checks = pd.DataFrame([
        {"Control":"Automated CI", "Status":"Not queried live", "Evidence":"This panel does not fetch GitHub workflow state; check the repository Actions page"},
        {"Control":"Export resilience", "Status":"UNVERIFIED end-to-end", "Evidence":"Export paths exist; generated files still require round-trip validation"},
        {"Control":"Approval gating", "Status":"Source present; e2e UNVERIFIED", "Evidence":"Persistent action ledger exists; authorized browser journey remains open"},
        {"Control":"Data lineage", "Status":"Source present; coverage UNVERIFIED", "Evidence":"Lineage store exists; not every module is proven to emit complete lineage"},
        {"Control":"Accessibility", "Status":"Partially implemented", "Evidence":"Some labels and reduced-motion CSS exist; formal accessibility audit not run"},
        {"Control":"Arabic / RTL", "Status":"Preference support present", "Evidence":"Locale/direction persistence exists; complete RTL walkthrough not verified"},
    ])
    st.dataframe(checks, use_container_width=True, hide_index=True)

    if st.button("🔍 Run self-diagnostic", type="primary", use_container_width=True):
        result = _self_diagnostic_report()
        st.dataframe(result, use_container_width=True, hide_index=True)
        if (result["Status"] == "FAIL").any():
            st.error("One or more structural checks failed. Review the evidence above.")
        elif (result["Status"] == "NOT TESTED").any():
            st.warning("Structural checks completed, but NOT TESTED controls remain unverified.")
        else:
            st.info("Structural checks passed. This is not a production-readiness or end-to-end certification.")

def render_platform_excellence_hub(username: str, tier: str) -> None:
    """Render the polished cross-cutting command center."""
    _seed()
    _hero(username, tier)
    tabs = st.tabs(["✨ Command Center","🔗 Digital Thread","🧪 Experiment Lab","🛡️ Decisions + Copilot","⚙️ Health + Delivery"])
    with tabs[0]:
        _overview(username)
    with tabs[1]:
        _digital_thread(username)
    with tabs[2]:
        _data_lab(username)
    with tabs[3]:
        _governance(username, tier)
    with tabs[4]:
        _platform_health(username)
