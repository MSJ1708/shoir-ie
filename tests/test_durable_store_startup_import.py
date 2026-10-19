"""Startup regression coverage for the durable account-store import contract."""

import ast
from pathlib import Path

import durable_account_store


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_EXPORTS = (
    "durable_backend_configured",
    "sync_durable_accounts",
    "sync_remote_requests_to_local",
    "edge_login",
    "edge_logout",
    "edge_admin_list_requests",
    "edge_renew_request",
    "upsert_remote_account",
    "insert_remote_request",
    "remote_account",
    "account_is_expired",
    "renewed_expiry",
)


def test_durable_account_store_exports_every_required_startup_function():
    missing = [
        name
        for name in REQUIRED_EXPORTS
        if not callable(getattr(durable_account_store, name, None))
    ]
    assert not missing, (
        "durable_account_store.py is missing required startup exports: "
        + ", ".join(missing)
    )


def test_app_validates_store_exports_before_binding_them():
    app_path = ROOT / "app.py"
    source = app_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(app_path))

    # A direct named import fails before Streamlit can render a useful
    # diagnostic if even one required export is missing.
    direct_required_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "durable_account_store":
            imported = {alias.name for alias in node.names}
            direct_required_imports.extend(sorted(imported.intersection(REQUIRED_EXPORTS)))

    assert not direct_required_imports
    assert "import durable_account_store as _durable_account_store" in source
    assert "_DURABLE_STORE_MISSING_EXPORTS" in source
    assert "Shoir-IE could not initialize its required account and persistence layer." in source
    assert "Account access is disabled until the required persistence functions are available." in source
