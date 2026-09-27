"""Research AI workspace for Shoir-IE Research Pack users."""

from __future__ import annotations

import io
import json
from typing import Any, Optional

import pandas as pd


def _call_model(messages: list[dict[str, str]], system_prompt: str) -> Optional[str]:
    try:
        import streamlit as st

        api_key = st.secrets["anthropic"]["api_key"]
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1000,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text
    except Exception:
        return None


def _read_dataset(uploaded) -> pd.DataFrame:
    raw = uploaded.getvalue()
    if uploaded.name.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw))
    book = pd.ExcelFile(io.BytesIO(raw), engine="openpyxl")
    return pd.read_excel(book, sheet_name=book.sheet_names[0])


def _research_prompt(prompt: str, study: dict[str, Any] | None, df: pd.DataFrame) -> str:
    context = {
        "study": study or {},
        "dataset_rows": int(len(df)),
        "dataset_columns": list(map(str, df.columns)),
        "numeric_columns": list(map(str, df.select_dtypes(include="number").columns)),
        "categorical_columns": list(
            map(str, df.select_dtypes(include=["object", "category", "string"]).columns)
        ),
    }
    return (
        "You are Shoir-IE Research AI. Help users conduct reproducible industrial-engineering research. "
        "Do not invent data, statistical results, citations, papers, study claims, or experimental outcomes. "
        "Separate observed evidence from proposed methods and interpretations. Identify missing evidence. "
        "Support research questions, hypotheses, variable/condition definitions, controls, sample-size and "
        "replication planning, statistical test selection, effect sizes, uncertainty, reproducibility, "
        "literature-review structure, manuscript sections and adversarial peer-review preparation. "
        "When a computation is requested, only report a result actually computed by Shoir-IE or explicitly "
        "present in the supplied workspace context. Context JSON: " + json.dumps(context, default=str)
    )


def _fallback(prompt: str, study: dict[str, Any] | None, df: pd.DataFrame) -> str:
    p = str(prompt or "").lower()
    numeric = list(map(str, df.select_dtypes(include="number").columns))
    if any(k in p for k in ("test", "anova", "t-test", "hypothesis")):
        if len(numeric) >= 2:
            return (
                f"I found {len(numeric)} numeric columns ({', '.join(numeric[:8])}). "
                "Define the primary endpoint and experimental structure first. A two-group comparison "
                "may use an independent or paired t-test depending on design; multiple groups may "
                "require ANOVA. The test must follow the design rather than the desired p-value."
            )
        return (
            "The dataset does not yet provide enough numeric structure to choose a defensible test. "
            "Define the primary endpoint plus the treatment/control or grouping structure."
        )
    if any(k in p for k in ("review", "reviewer", "peer")):
        return (
            "Research AI review checklist: verify a falsifiable research question, prespecified primary "
            "endpoint, explicit inclusion/exclusion rules, reproducible baseline/treatment definitions, "
            "replication, missing-data handling, planned statistical tests, uncertainty reporting, and "
            "traceability from every claim to a recorded result."
        )
    if any(k in p for k in ("method", "design", "experiment", "protocol")):
        return (
            "A reproducible protocol should lock the research question, hypothesis/H0, primary endpoint, "
            "independent variables, controls, baseline/treatment definitions, sample size, replications, "
            "seed, alpha/confidence level, planned tests, inclusion/exclusion criteria, data source and limitations."
        )
    if any(k in p for k in ("literature", "paper", "manuscript", "citation")):
        return (
            "I can structure a literature matrix or manuscript, but I will not invent citations. "
            "Provide the source set or use a connected literature workflow before claiming literature coverage."
        )
    if study:
        return (
            f"Your selected study is **{study.get('title', 'Untitled study')}**. "
            "I can help refine its question, hypothesis, protocol, analysis plan, reproducibility record or reviewer-facing evidence."
        )
    return "I am ready for a research question, protocol, dataset or reviewer concern. I will keep evidence separate from proposed analysis."


def render_research_ai(tier: str, username: str) -> None:
    import streamlit as st
    from shoir_tier_capabilities import tier_allows

    if not tier_allows(tier, "Research Pack"):
        st.warning("🔒 Research AI is included only with the Research Pack.")
        return

    from industrial_experience import list_research_studies, load_research_protocol

    st.markdown("## 🧪 Research AI")
    st.caption(
        "Research-grade Copilot for protocol design, statistical planning, reproducibility, "
        "peer-review preparation and manuscript structure. It never invents results or citations."
    )

    studies = list_research_studies(username)
    study_map: dict[str, dict[str, Any]] = {}
    if not studies.empty:
        for _, row in studies.iterrows():
            rid = str(row["Research ID"])
            study_map[rid] = {
                "research_id": rid,
                "study_id": str(row["Study ID"]),
                "title": str(row["Title"]),
                "methodology": str(row["Methodology"]),
                "primary_endpoint": str(row["Primary endpoint"]),
            }
        choice = st.selectbox(
            "Research study",
            list(study_map),
            format_func=lambda x: study_map[x]["title"],
            key="research_ai_study",
        )
        selected = study_map[choice]
        protocol = load_research_protocol(selected["study_id"], owner=username) or selected
    else:
        protocol = None
        st.info(
            "No saved study is available yet. Research AI is still usable with an uploaded dataset "
            "or a research question."
        )

    uploaded = st.file_uploader(
        "Research dataset (optional)",
        type=["xlsx", "csv"],
        key="research_ai_upload",
    )
    if uploaded:
        signature = f"{uploaded.name}:{uploaded.size}"
        if st.session_state.get("research_ai_dataset_signature") != signature:
            try:
                st.session_state["research_ai_dataset"] = _read_dataset(uploaded)
                st.session_state["research_ai_dataset_signature"] = signature
            except Exception as exc:
                st.error(f"Research dataset could not be loaded safely: {exc}")

    df = st.session_state.get("research_ai_dataset", pd.DataFrame())
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("Columns", f"{len(df.columns):,}")
    c3.metric("Numeric", f"{len(df.select_dtypes(include='number').columns):,}")
    c4.metric("Saved studies", f"{len(studies):,}")

    messages = st.session_state.setdefault("research_ai_messages", [])
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input(
        "Ask Research AI about your protocol, experiment, data or manuscript",
        key="research_ai_chat",
    )
    if prompt:
        messages.append({"role": "user", "content": prompt})
        system_prompt = _research_prompt(prompt, protocol, df)
        reply = _call_model(
            [{"role": m["role"], "content": m["content"]} for m in messages],
            system_prompt,
        ) or _fallback(prompt, protocol, df)
        messages.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)

    st.markdown("### Research workflow")
    st.write(
        "Question → Hypothesis → Protocol → Data → Analysis → Uncertainty → "
        "Reproducibility → Manuscript → Review"
    )
