from unittest.mock import patch

import streamlit as st

from shoir_visual_system import apply_shoir_design_system, render_workspace_status


def test_design_system_is_injected_once(monkeypatch):
    st.session_state.clear()
    calls = []

    def fake_markdown(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(st, "markdown", fake_markdown)
    apply_shoir_design_system()
    apply_shoir_design_system()

    assert len(calls) == 1
    assert st.session_state["_shoir_design_system_applied"] is True


def test_workspace_status_escapes_user(monkeypatch):
    st.session_state.clear()
    calls = []

    def fake_markdown(*args, **kwargs):
        calls.append(args[0])

    monkeypatch.setattr(st, "markdown", fake_markdown)
    render_workspace_status(
        user="<script>alert(1)</script>",
        tier="Professional Tier",
        durable=True,
    )

    assert "<script>" not in calls[0]
    assert "Cloud workspace" in calls[0]
    assert "Autosave active" in calls[0]
