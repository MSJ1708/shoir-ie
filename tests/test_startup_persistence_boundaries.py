import json

import pytest

import durable_account_store as durable
import shoir_enterprise_layer as ent
import workspace_persistence as wp


def test_edge_mode_does_not_activate_direct_postgres_connection(monkeypatch):
    monkeypatch.setattr(durable, "database_url", lambda: "")
    monkeypatch.setattr(durable, "psycopg2", object())
    monkeypatch.setattr(durable, "edge_backend_configured", lambda: True)

    assert durable.durable_backend_configured() is True
    with pytest.raises(RuntimeError, match="Direct PostgreSQL backend is not configured"):
        durable._pg_connect()


def test_enterprise_schema_ignores_empty_host_postgres_dsn(monkeypatch):
    monkeypatch.setattr(ent, "postgres_backend_configured", lambda: True)
    monkeypatch.setattr(ent, "database_url", lambda: "postgresql:///enterprise")
    monkeypatch.setattr(ent, "_pg_connect", object())

    assert ent._remote() is False


def test_enterprise_schema_requires_opt_in_for_localhost_postgres(monkeypatch):
    monkeypatch.delenv("SHOIR_ALLOW_LOCAL_POSTGRES", raising=False)
    monkeypatch.setattr(ent, "postgres_backend_configured", lambda: True)
    monkeypatch.setattr(ent, "database_url", lambda: "postgresql://user:pass@localhost/enterprise")
    monkeypatch.setattr(ent, "_pg_connect", object())

    assert ent._remote() is False

    monkeypatch.setenv("SHOIR_ALLOW_LOCAL_POSTGRES", "true")
    assert ent._remote() is True


def test_workspace_snapshot_and_restore_drop_streamlit_widget_state(monkeypatch, tmp_path):
    monkeypatch.setattr(wp, "durable_backend_configured", lambda: False)
    db_path = str(tmp_path / "workspace.db")
    state = {
        "selected_module": "Industrial Workbook",
        "shoir_shell_section_radio": "HOME",
        "shoir_shell_module_search": "excel",
        "shoir_shell_module_selector_HOME": "Industrial Workbook",
        "shoir_universal_advance_Industrial_Workbook": True,
        "useful_workspace_value": {"saved": True},
    }

    assert wp.save_user_workspace("Alice", state, db_path=db_path) is True

    with wp.shoir_sqlite_connect(db_path) as conn:
        payload = conn.execute(
            "SELECT state_json FROM workspace_states WHERE username='alice'"
        ).fetchone()[0]
    stored = json.loads(payload)
    assert "shoir_shell_section_radio" not in stored
    assert "shoir_shell_module_search" not in stored
    assert "shoir_universal_advance_Industrial_Workbook" not in stored
    assert stored["selected_module"] == "Industrial Workbook"

    restored = {}
    assert wp.load_user_workspace("Alice", restored, db_path=db_path) is True
    assert restored["selected_module"] == "Industrial Workbook"
    assert restored["useful_workspace_value"] == {"__type__": "dict", "value": {"saved": True}} or restored["useful_workspace_value"] == {"saved": True}
    assert "shoir_shell_section_radio" not in restored
    assert "shoir_shell_module_search" not in restored
