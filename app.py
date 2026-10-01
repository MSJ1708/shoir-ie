"""Shoir-IE entrypoint with startup recovery."""
import streamlit as st

st.set_page_config(page_title="shoir", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

try:
    import shoir_app_runtime  # noqa: F401
except Exception as exc:  # pragma: no cover
    st.markdown(
        """
        <div style="max-width:900px;margin:7vh auto;padding:32px;border:1px solid #dbe4f0;border-radius:20px;background:#fff">
          <div style="font-size:12px;font-weight:800;letter-spacing:.08em;color:#0f766e">SHOIR-IE STARTUP</div>
          <h1 style="margin:.25rem 0;color:#0f172a">Shoir-IE could not finish loading</h1>
          <p style="color:#64748b">The sign-in screen was blocked by a startup error. No workspace data was intentionally modified.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.error("Startup error: the application runtime could not be loaded.")
    with st.expander("Technical diagnostic"):
        st.code(f"{type(exc).__name__}: {exc}")
