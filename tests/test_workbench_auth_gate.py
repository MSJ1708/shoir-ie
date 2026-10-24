"""Regression tests for direct Workbench access and fail-closed tier resolution."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "pages" / "Industrial_Engineering_Workbench.py"


def _run_workbench(**session_values):
    at = AppTest.from_file(PAGE, default_timeout=45)
    for key, value in session_values.items():
        at.session_state[key] = value
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(exc.value) for exc in at.exception)
    return at


def _has_gate_only_surface(at):
    # Guard failures must stop before the platform database setup and module UI.
    assert not any("Search modules" == item.label for item in at.text_input)
    assert not any("Module" == item.label for item in at.selectbox)
    assert not any("Import / Validate" in str(getattr(item, "label", "")) for item in at.button)
    assert not at.metric


def test_direct_workbench_url_requires_authenticated_user_and_explicit_tier():
    at = _run_workbench()
    assert any(
        "Sign in to Shoir-IE" in str(item.value) for item in at.warning
    )
    _has_gate_only_surface(at)


def test_authenticated_session_with_unknown_tier_is_denied_before_module_render():
    at = _run_workbench(
        authenticated=True,
        current_user="disposable-workbench-test-user",
        user_tier="Super Enterprise",
    )
    assert any(
        "package could not be verified" in str(item.value).lower()
        for item in at.error
    )
    _has_gate_only_surface(at)


def test_missing_tier_does_not_fall_back_to_enterprise_plus():
    at = _run_workbench(
        authenticated=True,
        current_user="disposable-workbench-test-user",
    )
    assert any(
        "package could not be verified" in str(item.value).lower()
        for item in at.error
    )
    _has_gate_only_surface(at)
