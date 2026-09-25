"""Shoir-IE visual design system.

A small, dependency-free presentation layer that can be applied on top of the
existing Streamlit application without changing engineering calculations.
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st


SHOIR_CSS = r"""
<style>
:root {
    --shoir-ink: #0b1220;
    --shoir-muted: #64748b;
    --shoir-line: #dbe4ef;
    --shoir-surface: rgba(255,255,255,.86);
    --shoir-blue: #2563eb;
    --shoir-teal: #0f766e;
    --shoir-navy: #0f172a;
    --shoir-shadow: 0 18px 55px rgba(15, 23, 42, .09);
}

/* ---- global canvas ---- */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 6% 4%, rgba(37,99,235,.09), transparent 26rem),
        radial-gradient(circle at 95% 7%, rgba(15,118,110,.08), transparent 25rem),
        linear-gradient(180deg, #f5f8fc 0%, #f8fafc 32%, #ffffff 100%);
}
[data-testid="stHeader"] {
    background: rgba(255,255,255,.72) !important;
    backdrop-filter: blur(14px);
}
.block-container {
    max-width: 1520px !important;
    padding-top: 1.35rem !important;
}

/* ---- hero / brand ---- */
.hero-card {
    position: relative;
    overflow: hidden;
    border: 1px solid rgba(203,213,225,.86) !important;
    border-radius: 24px !important;
    background:
        linear-gradient(135deg, rgba(255,255,255,.96), rgba(248,251,255,.97) 48%, rgba(239,252,250,.94)) !important;
    box-shadow: 0 20px 60px rgba(15,23,42,.09) !important;
}
.hero-card::before {
    content: "";
    position: absolute;
    inset: -60% 55% auto -12%;
    height: 220px;
    background: radial-gradient(circle, rgba(37,99,235,.18), transparent 65%);
    pointer-events: none;
}
.hero-card::after {
    content: "";
    position: absolute;
    right: -80px;
    bottom: -110px;
    width: 280px;
    height: 280px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(15,118,110,.13), transparent 68%);
    pointer-events: none;
}
.hero-title {
    letter-spacing: -.02em !important;
    font-size: clamp(2rem, 3.2vw, 2.55rem) !important;
}
.hero-copy {
    max-width: 880px;
    line-height: 1.65;
}

/* ---- compact system ribbon ---- */
.shoir-system-ribbon {
    display: grid;
    grid-template-columns: minmax(240px, 1.4fr) repeat(3, minmax(135px, .55fr));
    gap: 10px;
    margin: 0 0 18px 0;
    padding: 10px;
    border: 1px solid rgba(203,213,225,.82);
    border-radius: 16px;
    background: rgba(255,255,255,.72);
    backdrop-filter: blur(12px);
    box-shadow: 0 9px 26px rgba(15,23,42,.045);
}
.shoir-system-ribbon .system-cell {
    min-height: 50px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 8px 12px;
    border-radius: 11px;
    background: rgba(248,250,252,.76);
}
.shoir-system-ribbon .system-label {
    font-size: 10px;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
    color: #94a3b8;
}
.shoir-system-ribbon .system-value {
    margin-top: 2px;
    color: var(--shoir-ink);
    font-size: 12px;
    font-weight: 800;
}
.shoir-system-ribbon .system-value.good::before {
    content: "●";
    margin-right: 6px;
    color: #0f766e;
    font-size: 10px;
}
.shoir-system-ribbon .system-value.info::before {
    content: "●";
    margin-right: 6px;
    color: #2563eb;
    font-size: 10px;
}

/* ---- sidebar ---- */
section[data-testid="stSidebar"] {
    background:
        linear-gradient(180deg, rgba(248,250,252,.98), rgba(241,245,249,.96)) !important;
    border-right: 1px solid #e2e8f0 !important;
}
section[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.1rem;
}
section[data-testid="stSidebar"] div[data-testid="stExpander"] {
    border-radius: 16px !important;
    background: rgba(255,255,255,.72);
}

/* ---- controls ---- */
div.stButton > button,
div[data-testid="stFormSubmitButton"] button,
div[data-testid="stDownloadButton"] button {
    border-radius: 12px !important;
    min-height: 42px !important;
    border: 1px solid #d7e0eb !important;
    background: rgba(255,255,255,.94) !important;
    color: #0f172a !important;
    font-weight: 750 !important;
    letter-spacing: -.01em;
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease, background .16s ease;
}
div.stButton > button:hover,
div[data-testid="stFormSubmitButton"] button:hover,
div[data-testid="stDownloadButton"] button:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 24px rgba(15,23,42,.10) !important;
    border-color: #93c5fd !important;
}
div.stButton > button[kind="primary"],
div[data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: linear-gradient(135deg, #2563eb, #0f766e) !important;
    color: #fff !important;
    border-color: transparent !important;
    box-shadow: 0 9px 24px rgba(37,99,235,.20) !important;
}
div.stButton > button[kind="primary"]:hover,
div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
    box-shadow: 0 13px 30px rgba(37,99,235,.25) !important;
}

/* ---- inputs ---- */
div[data-baseweb="input"],
div[data-baseweb="select"],
div[data-baseweb="textarea"] {
    border-radius: 12px !important;
}
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
div[data-baseweb="textarea"] > div {
    border-radius: 12px !important;
    border-color: #dbe4ef !important;
    background: rgba(255,255,255,.94) !important;
}
div[data-baseweb="input"] > div:focus-within,
div[data-baseweb="select"] > div:focus-within,
div[data-baseweb="textarea"] > div:focus-within {
    border-color: #60a5fa !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,.09) !important;
}

/* ---- metrics/cards ---- */
div[data-testid="stMetric"] {
    border: 1px solid #dbe4ef !important;
    border-radius: 16px !important;
    padding: 14px 16px !important;
    background: rgba(255,255,255,.90) !important;
    box-shadow: 0 7px 24px rgba(15,23,42,.05) !important;
}
div[data-testid="stMetricValue"] {
    color: #0f4fa8 !important;
    font-weight: 850 !important;
    letter-spacing: -.025em;
}
div[data-testid="stMetricLabel"] {
    color: #64748b !important;
}

/* ---- tabs ---- */
div[data-baseweb="tab-list"] {
    gap: 6px;
    padding: 5px;
    border-radius: 14px;
    background: rgba(241,245,249,.85);
    border: 1px solid #e2e8f0;
}
button[data-baseweb="tab"] {
    border-radius: 10px !important;
    font-weight: 750 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    background: #ffffff !important;
    box-shadow: 0 4px 12px rgba(15,23,42,.07);
}

/* ---- expanders / tables ---- */
div[data-testid="stExpander"] {
    border-radius: 16px !important;
    border-color: #dbe4ef !important;
    background: rgba(255,255,255,.74);
}
div[data-testid="stDataFrame"] {
    border: 1px solid #dbe4ef;
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 7px 24px rgba(15,23,42,.04);
}

/* ---- alerts ---- */
div[data-testid="stAlert"] {
    border-radius: 14px !important;
}

/* ---- subtle motion; keep it restrained ---- */
@keyframes shoirPulse {
    0%, 100% { box-shadow: 0 8px 24px rgba(37,99,235,.08); }
    50% { box-shadow: 0 12px 32px rgba(15,118,110,.11); }
}
.shoir-live-pulse {
    animation: shoirPulse 4s ease-in-out infinite;
}

/* ---- mobile safety ---- */
@media (max-width: 900px) {
    .shoir-system-ribbon {
        grid-template-columns: 1fr 1fr;
    }
}
@media (max-width: 620px) {
    .shoir-system-ribbon {
        grid-template-columns: 1fr;
    }
    .hero-title { font-size: 1.72rem !important; }
}
</style>
"""


def apply_shoir_design_system() -> None:
    """Inject the Shoir-IE presentation layer once per Streamlit run."""
    marker = "_shoir_design_system_applied"
    if st.session_state.get(marker):
        return
    st.markdown(SHOIR_CSS, unsafe_allow_html=True)
    st.session_state[marker] = True


def render_workspace_status(*, user: str, tier: str, durable: bool, autosave: bool = True) -> None:
    """Render a compact system-health ribbon beneath the hero."""
    user_safe = html.escape(str(user or "Workspace"))
    tier_safe = html.escape(str(tier or "Starter Tier"))
    storage_label = "Cloud workspace" if durable else "Local workspace"
    storage_class = "good" if durable else "info"
    autosave_label = "Autosave active" if autosave else "Autosave limited"
    autosave_class = "good" if autosave else "info"

    st.markdown(
        f"""
        <div class="shoir-system-ribbon shoir-live-pulse" aria-label="Shoir-IE workspace status">
          <div class="system-cell">
            <div class="system-label">Workspace</div>
            <div class="system-value info">{user_safe} · {tier_safe}</div>
          </div>
          <div class="system-cell">
            <div class="system-label">Storage</div>
            <div class="system-value {storage_class}">{storage_label}</div>
          </div>
          <div class="system-cell">
            <div class="system-label">State</div>
            <div class="system-value {autosave_class}">{autosave_label}</div>
          </div>
          <div class="system-cell">
            <div class="system-label">Platform</div>
            <div class="system-value good">Industrial Command Center</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
