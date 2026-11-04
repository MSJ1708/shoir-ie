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
    with pytest.raises(ValueError, match="between 1 and 10,000"):
        store.edge_list_platform_records(
            "synthetic-user", "opaque-session-token", "site-1", limit=10001
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



def test_edge_list_platform_records_retrieves_all_bounded_pages(monkeypatch):
    calls = []
    def fake(action, payload):
        calls.append((action, dict(payload)))
        offset = payload["offset"]
        if offset == 0:
            return {
                "ok": True,
                "records": [{"record_id": f"SPR-{i}"} for i in range(200)],
                "has_more": True,
                "next_offset": 200,
            }
        if offset == 200:
            return {
                "ok": True,
                "records": [{"record_id": f"SPR-{i}"} for i in range(200, 400)],
                "has_more": True,
                "next_offset": 400,
            }
        return {
            "ok": True,
            "records": [{"record_id": f"SPR-{i}"} for i in range(400, 450)],
            "has_more": False,
            "next_offset": 450,
        }
    monkeypatch.setattr(store, "_edge_call", fake)
    records = store.edge_list_platform_records(
        "synthetic-user", "opaque-session-token", "site-1",
        "canonical_entity", limit=450,
    )
    assert len(records) == 450
    assert [call[1]["offset"] for call in calls] == [0, 200, 400]
    assert all(call[1]["limit"] <= 200 for call in calls)
    assert all(call[1]["workspace"] == "site-1" for call in calls)


def test_edge_list_platform_records_fails_closed_on_bad_page_cursor(monkeypatch):
    monkeypatch.setattr(
        store, "_edge_call",
        lambda *_: {
            "ok": True, "records": [{"record_id": "SPR-1"}],
            "has_more": True, "next_offset": 0,
        },
    )
    with pytest.raises(RuntimeError, match="pagination cursor"):
        store.edge_list_platform_records(
            "synthetic-user", "opaque-session-token", "site-1",
            "canonical_entity", limit=500,
        )


def test_edge_platform_list_uses_stable_secondary_ordering_and_safe_offset():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    listing = source.split('if (action === "platform_record_list") {', 1)[1].split(
        'if (action === "workspace_load") {', 1
    )[0]
    assert '.order("updated_at", { ascending: false })' in listing
    assert '.order("record_id", { ascending: true })' in listing
    assert '.range(requestedOffset, requestedOffset + requestedLimit)' in listing
    assert 'next_offset: requestedOffset + records.length' in listing
