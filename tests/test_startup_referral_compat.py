from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def test_referral_summary_is_not_a_required_startup_export():
    required = APP.split("_DURABLE_STORE_REQUIRED_EXPORTS = (", 1)[1].split("\n)", 1)[0]
    assert '"edge_referral_summary"' not in required


def test_older_persistence_module_can_still_serve_referral_summary_via_edge_caller():
    assert 'if callable(getattr(_durable_account_store, "edge_referral_summary", None)):' in APP
    assert 'getattr(_durable_account_store, "_edge_call", None)' in APP
    assert '"referral_summary_session"' in APP
    assert "Referral summary is unavailable in this persistence module version." in APP


def test_essential_account_exports_remain_required():
    required = APP.split("_DURABLE_STORE_REQUIRED_EXPORTS = (", 1)[1].split("\n)", 1)[0]
    for name in (
        "durable_backend_configured",
        "edge_login",
        "edge_logout",
        "edge_admin_approve",
        "edge_admin_decline",
        "remote_account",
        "account_is_expired",
    ):
        assert f'"{name}"' in required


def test_staging_notice_uses_the_required_exact_text():
    assert 'STAGING TEST ENVIRONMENT · use disposable test accounts and synthetic data only.' in APP
