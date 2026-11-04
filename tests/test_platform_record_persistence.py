"""Contract tests for authenticated, workspace-scoped platform record persistence."""
import pytest
import durable_account_store as store


def test_platform_record_payload_rejects_nested_credentials():
    with pytest.raises(ValueError, match="Credential or sensitive"):
        store._validate_platform_record_payload({
            "asset": {"id": "P-100", "metadata": {"email": "person@example.invalid"}}
        })


def test_platform_record_payload_rejects_oversize_and_nonfinite():
    with pytest.raises(ValueError, match="256 KiB"):
        store._validate_platform_record_payload({"text": "x" * (256 * 1024)})
    with pytest.raises(ValueError):
        store._validate_platform_record_payload({"value": float("nan")})


def test_edge_save_platform_record_sends_only_validated_workspace_scoped_action(monkeypatch):
    calls = []
    def fake(action, payload):
        calls.append((action, payload))
        return {"ok": True, "record": {"record_id": "SPR-ABC", "version": 1}}
    monkeypatch.setattr(store, "_edge_call", fake)
    result = store.edge_save_platform_record(
        "synthetic-user", "opaque-session-token", "site-1",
        "asset", "ASSET-100", {"name": "Press 100", "capacity_tph": 42.0}
    )
    assert result["ok"] is True
    assert calls[0][0] == "platform_record_save"
    assert calls[0][1]["username"] == "synthetic-user"
    assert calls[0][1]["workspace"] == "site-1"
    assert calls[0][1]["record_type"] == "asset"
    assert "token" in calls[0][1]


def test_edge_save_platform_record_rejects_invalid_record_type_before_network(monkeypatch):
    monkeypatch.setattr(store, "_edge_call", lambda *_: pytest.fail("network must not be called"))
    with pytest.raises(ValueError, match="not supported"):
        store.edge_save_platform_record(
            "synthetic-user", "opaque-session-token", "site-1",
            "sql", "drop-tables", {"value": "x"}
        )


def test_edge_list_platform_records_bounds_limit_and_uses_authenticated_scope(monkeypatch):
    calls = []
    monkeypatch.setattr(store, "_edge_call", lambda action, payload: (
        calls.append((action, payload)) or {"ok": True, "records": [{"record_id": "SPR-1"}]}
    ))
    records = store.edge_list_platform_records(
        "synthetic-user", "opaque-session-token", "site-1", "asset", 25
    )
    assert records == [{"record_id": "SPR-1"}]
    assert calls[0][0] == "platform_record_list"
    assert calls[0][1]["workspace"] == "site-1"
    with pytest.raises(ValueError, match="between 1 and 200"):
        store.edge_list_platform_records(
            "synthetic-user", "opaque-session-token", "site-1", limit=201
        )


def test_edge_platform_record_actions_validate_session_before_data_access():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    save = source.split('if (action === "platform_record_save") {', 1)[1].split(
        'if (action === "platform_record_list") {', 1
    )[0]
    listing = source.split('if (action === "platform_record_list") {', 1)[1].split(
        'if (action === "workspace_load") {', 1
    )[0]
    assert 'getSession(token, username, "workspace")' in save
    assert 'getSession(String(body.token || ""), username, "workspace")' in listing
    assert 'supabase.rpc("shoir_platform_upsert_record"' in save
    assert '.eq("workspace_key", workspaceKey)' in listing
    assert 'PLATFORM_SECRET_KEY.test(key)' in source
