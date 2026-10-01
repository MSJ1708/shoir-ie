"""Shoir-IE Streamlit entrypoint.

The runtime owns the application workflow; this launcher owns page configuration
and provides a visible recovery screen when startup/import fails before the
authentication UI can render.
"""
import streamlit as st

st.set_page_config(
    page_title="shoir",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

try:
    import shoir_app_runtime  # noqa: F401
except Exception as exc:  # pragma: no cover - last-resort production boundary
    st.markdown(
        """
        <div style="max-width:900px;margin:6vh auto;padding:32px;border:1px solid #dbe4f0;"
             "border-radius:20px;background:#ffffff;box-shadow:0 10px 30px rgba(15,23,42,.06);">
          <div style="font-size:12px;font-weight:800;letter-spacing:.08em;color:#0f766e;">SHOIR-IE STARTUP</div>
          <h1 style="margin:.25rem 0 .5rem;color:#0f172a;">Shoir-IE is starting in recovery mode</h1>
          <p style="color:#64748b;">
            The application runtime could not finish loading, so the normal sign-in screen
            was not available. No workspace data was intentionally modified.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.error("Startup error: the Shoir-IE runtime could not be loaded.")
    with st.expander("Technical diagnostic", expanded=False):
        st.code(f"{type(exc).__name__}: {exc}")
        st.caption("Check the deployment logs for the full traceback, then reload the application after the runtime issue is corrected.")
