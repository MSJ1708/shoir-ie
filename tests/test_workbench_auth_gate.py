"""Regression tests for direct page access and fail-closed tier resolution."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_PAGES = [
    pytest.param(ROOT / "pages" / "Industrial_Engineering_Workbench.py", id="workbench"),
    pytest.param(ROOT / "pages" / "Industrial_Platform_Command_Center.py", id="command-center"),
]


def _run_page(page, **session_values):
    at = AppTest.from_file(page, default_timeout=45)
    for key, value in session_values.items():
        at.session_state[key] = value
    at.run(timeout=45)
    assert not at.exception, "\\n".join(str(exc.value) for exc in at.exception)
    return at


def _assert_gate_stopped_protected_surface(at):
    # Guard failures must stop before the platform database setup and module UI.
    assert len(at.text_input) == 0
    assert len(at.selectbox) == 0
    assert len(at.metric) == 0


@pytest.mark.parametrize("page", PROTECTED_PAGES)
def test_direct_page_url_requires_authenticated_user_and_explicit_tier(page):
    at = _run_page(page)
    assert any("Sign in to Shoir-IE" in str(item.value) for item in at.warning)
    _assert_gate_stopped_protected_surface(at)


@pytest.mark.parametrize("page", PROTECTED_PAGES)
def test_authenticated_session_with_unknown_tier_is_denied_before_render(page):
    at = _run_page(
        page,
        authenticated=True,
        current_user="disposable-protected-page-test-user",
        user_tier="Super Enterprise",
    )
    assert any(
        "package could not be verified" in str(item.value).lower()
        for item in at.error
    )
    _assert_gate_stopped_protected_surface(at)


@pytest.mark.parametrize("page", PROTECTED_PAGES)
def test_missing_tier_does_not_fall_back_to_enterprise_plus(page):
    at = _run_page(
        page,
        authenticated=True,
        current_user="disposable-protected-page-test-user",
    )
    assert any(
        "package could not be verified" in str(item.value).lower()
        for item in at.error
    )
    _assert_gate_stopped_protected_surface(at)



def test_command_center_requires_enterprise_level_access():
    page = ROOT / "pages" / "Industrial_Platform_Command_Center.py"
    at = _run_page(
        page,
        authenticated=True,
        current_user="disposable-command-center-test-user",
        user_tier="Starter Tier",
    )
    assert any(
        "requires Enterprise-level access" in str(item.value)
        for item in at.warning
    )
    _assert_gate_stopped_protected_surface(at)
