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
    assert "getSession(" in listing
    assert 'String(body.token || "")' in listing
    assert "username" in listing
    assert '"workspace"' in listing
    assert '.rpc(' in save
    assert '"shoir_platform_upsert_record"' in save
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



def test_dataset_version_registration_requires_session_and_calls_atomic_rpc(monkeypatch):
    calls = []
    monkeypatch.setattr(
        store, "_edge_call",
        lambda action, payload: calls.append((action, payload)) or {
            "ok": True, "registration": {"dataset_id": payload["dataset_id"], "version": 1}
        },
    )
    result = store.edge_register_dataset_version(
        username="synthetic-user",
        token="opaque-session-token",
        workspace="plant-a",
        dataset_id="DS-ABCDEF012345",
        name="Production",
        source_name="production.csv",
        data_hash="a" * 64,
        version_fingerprint="b" * 64,
        row_count=100,
        column_count=8,
        schema={"asset_id": {"dtype": "object"}},
        transformations=[{"operation": "import", "status": "validated"}],
    )
    assert result["ok"] is True
    assert calls[0][0] == "dataset_version_register"
    assert calls[0][1]["workspace"] == "plant-a"
    assert calls[0][1]["dataset_id"] == "DS-ABCDEF012345"


def test_dataset_version_registration_rejects_invalid_metadata_before_network(monkeypatch):
    monkeypatch.setattr(
        store, "_edge_call",
        lambda *_: pytest.fail("invalid dataset metadata must not reach the Edge Function"),
    )
    with pytest.raises(ValueError, match="content hash"):
        store.edge_register_dataset_version(
            username="synthetic-user", token="opaque-session-token",
            workspace="plant-a", dataset_id="DS-ABCDEF012345",
            name="Production", source_name="production.csv",
            data_hash="not-a-hash", version_fingerprint="b" * 64,
            row_count=100, column_count=8, schema={},
        )


def test_dataset_version_edge_action_uses_authenticated_session_and_atomic_rpc():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    action = source.split('if (action === "dataset_version_register") {', 1)[1].split(
        'if (action === "platform_record_save") {', 1
    )[0]
    assert "getSession(" in action
    assert 'String(body.token || "")' in action
    assert "username" in action
    assert '"workspace"' in action
    assert 'supabase.rpc(' in action
    assert '"shoir_platform_register_dataset_version"' in action
    assert 'p_workspace_key: workspaceKey' in action



def test_private_dataset_upload_verifies_hash_and_finalizes_after_signed_upload(monkeypatch):
    import hashlib
    import durable_account_store as store
    import requests

    raw = b"asset_id,throughput_tph\nA-1,12.5\n"
    calls = []
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "STAGING_SUPABASE_PROJECT_HOST", "hfhrosthswcybccepmak.supabase.co")
    def edge(action, payload):
        calls.append((action, dict(payload)))
        if action == "dataset_upload_create":
            return {
                "ok": True,
                "upload_url": "https://hfhrosthswcybccepmak.supabase.co/storage/v1/object/upload/sign/shoir-industrial-datasets/tmp/workspace/DS-ABCDEF012345/upload.csv?token=opaque",
                "upload_path": "tmp/workspace/DS-ABCDEF012345/upload.csv",
            }
        return {"ok": True, "registration": {"dataset_id": payload["dataset_id"], "version": 1}}
    monkeypatch.setattr(store, "_edge_call", edge)
    uploads = []
    monkeypatch.setattr(
        requests, "put",
        lambda url, data, headers, timeout: uploads.append((url, data, headers, timeout)) or
            type("Response", (), {"status_code": 200, "text": ""})(),
    )
    digest = hashlib.sha256(raw).hexdigest()
    result = store.edge_upload_and_register_dataset_version(
        "synthetic-user", "opaque-session-token", "plant-a",
        "DS-ABCDEF012345", "Production", "production.csv", raw,
        digest, "c" * 64, 1, 2, {"asset_id": {"dtype": "object"}}, [],
    )
    assert result["registration"]["version"] == 1
    assert [item[0] for item in calls] == [
        "dataset_upload_create", "dataset_version_finalize"
    ]
    assert uploads[0][1] == raw
    assert uploads[0][2]["Content-Type"] == "text/csv"
    assert calls[1][1]["upload_path"].startswith("tmp/workspace/")


def test_private_dataset_upload_rejects_wrong_hash_before_network(monkeypatch):
    import durable_account_store as store

    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        store, "_edge_call",
        lambda *_: pytest.fail("wrong content hash must be rejected before creating an upload URL"),
    )
    with pytest.raises(ValueError, match="do not match"):
        store.edge_upload_and_register_dataset_version(
            "synthetic-user", "opaque-session-token", "plant-a",
            "DS-ABCDEF012345", "Production", "production.csv", b"actual bytes",
            "0" * 64, "c" * 64, 1, 1, {"asset_id": {"dtype": "object"}}, [],
        )


def test_private_dataset_upload_rejects_unexpected_signed_upload_host(monkeypatch):
    import hashlib
    import durable_account_store as store
    import requests

    raw = b"asset_id\nA-1\n"
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "STAGING_SUPABASE_PROJECT_HOST", "hfhrosthswcybccepmak.supabase.co")
    monkeypatch.setattr(
        store, "_edge_call",
        lambda *_: {
            "ok": True,
            "upload_url": "https://attacker.invalid/storage/v1/object/upload/sign/shoir-industrial-datasets/file.csv?token=x",
            "upload_path": "tmp/workspace/DS-ABCDEF012345/file.csv",
        },
    )
    monkeypatch.setattr(
        requests, "put",
        lambda *_args, **_kwargs: pytest.fail("unexpected upload host must not be contacted"),
    )
    with pytest.raises(RuntimeError, match="unexpected signed upload URL"):
        store.edge_upload_and_register_dataset_version(
            "synthetic-user", "opaque-session-token", "plant-a",
            "DS-ABCDEF012345", "Production", "production.csv", raw,
            hashlib.sha256(raw).hexdigest(), "c" * 64, 1, 1,
            {"asset_id": {"dtype": "object"}}, [],
        )



def test_dataset_upload_edge_actions_require_session_and_private_storage():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    create = source.split('if (action === "dataset_upload_create") {', 1)[1].split(
        'if (action === "dataset_version_finalize") {', 1
    )[0]
    finalize = source.split('if (action === "dataset_version_finalize") {', 1)[1].split(
        'if (action === "dataset_version_register") {', 1
    )[0]
    assert "getSession(" in create
    assert 'String(body.token || "")' in create
    assert "username" in create
    assert '"workspace"' in create
    assert "getSession(" in finalize
    assert 'String(body.token || "")' in finalize
    assert "username" in finalize
    assert '"workspace"' in finalize
    assert '.createSignedUploadUrl(uploadPath, { upsert: false })' in create
    assert 'await sha256Bytes(bytes)' in finalize
    assert 'digest !== dataHash' in finalize
    assert '"shoir_platform_register_dataset_version_with_storage"' in finalize
    assert 'p_storage_key: storageKey' in finalize


def test_private_dataset_storage_migration_excludes_bucket_from_permissive_policy():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "supabase/migrations/20261104192857_shoir_private_dataset_file_storage_and_linkage.sql").read_text(encoding="utf-8")
    assert "'shoir-industrial-datasets'" in source
    assert "public = false" in source
    assert "file_size_limit = EXCLUDED.file_size_limit" in source
    assert "bucket_id <> 'shoir-industrial-datasets'" in source
    assert "REVOKE ALL ON FUNCTION public.shoir_platform_register_dataset_version_with_storage" in source
    assert "TO service_role" in source



def test_private_dataset_download_checks_signed_host_and_content_hash(monkeypatch):
    import hashlib
    import durable_account_store as store
    import requests

    content = b"asset_id,units\nA-1,10\n"
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "STAGING_SUPABASE_PROJECT_HOST", "hfhrosthswcybccepmak.supabase.co")
    monkeypatch.setattr(
        store, "_edge_call",
        lambda action, payload: {
            "ok": True,
            "download_url": "https://hfhrosthswcybccepmak.supabase.co/storage/v1/object/sign/shoir-industrial-datasets/workspace/dataset/file.csv?token=x",
            "data_hash": hashlib.sha256(content).hexdigest(),
            "version": 2,
            "row_count": 1,
            "column_count": 2,
        },
    )
    monkeypatch.setattr(
        requests, "get",
        lambda *_args, **_kwargs: type("Response", (), {
            "status_code": 200, "content": content, "text": ""
        })(),
    )
    raw, metadata = store.edge_download_dataset_version(
        "synthetic-user", "opaque-session-token", "plant-a", "DS-ABCDEF012345"
    )
    assert raw == content
    assert metadata["version"] == 2


def test_private_dataset_download_rejects_hash_mismatch(monkeypatch):
    import durable_account_store as store
    import requests

    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(store, "STAGING_SUPABASE_PROJECT_HOST", "hfhrosthswcybccepmak.supabase.co")
    monkeypatch.setattr(
        store, "_edge_call",
        lambda *_: {
            "download_url": "https://hfhrosthswcybccepmak.supabase.co/storage/v1/object/sign/shoir-industrial-datasets/workspace/file.csv?token=x",
            "data_hash": "0" * 64,
        },
    )
    monkeypatch.setattr(
        requests, "get",
        lambda *_args, **_kwargs: type("Response", (), {
            "status_code": 200, "content": b"wrong", "text": ""
        })(),
    )
    with pytest.raises(RuntimeError, match="SHA-256 integrity"):
        store.edge_download_dataset_version(
            "synthetic-user", "opaque-session-token", "plant-a", "DS-ABCDEF012345"
        )



def test_dataset_download_edge_action_is_session_and_workspace_scoped():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] /
              "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    action = source.split('if (action === "dataset_download_url") {', 1)[1].split(
        'if (action === "dataset_upload_create") {', 1
    )[0]
    assert "getSession(" in action
    assert 'String(body.token || "")' in action
    assert "username" in action
    assert '"workspace"' in action
    assert '.eq("workspace_key", workspaceKey)' in action
    assert 'const recordType = requestedVersion === null' in action
    assert 'const entityKey = requestedVersion === null' in action
    assert '.eq("record_type", recordType)' in action
    assert '.eq("entity_key", entityKey)' in action
    assert 'datasetId + ":v" + requestedVersion' in action
    assert 'datasetEntitlementDenialForRequest(' in action
    assert 'resolveManagedWorkspaceKey(' in action
    assert '.createSignedUrl(storageKey, 300, { download: true })' in action
    assert 'expectedPrefix = workspaceKey + "/" + datasetId + "/"' in action



def test_private_dataset_download_can_select_a_historical_version(monkeypatch):
    import hashlib
    import durable_account_store as store
    import requests

    content = b"asset_id,units\nA-1,9\n"
    calls = []
    monkeypatch.setattr(store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(
        store, "_edge_call",
        lambda action, payload: calls.append((action, dict(payload))) or {
            "ok": True,
            "download_url": "https://hfhrosthswcybccepmak.supabase.co/storage/v1/object/sign/shoir-industrial-datasets/workspace/dataset/file.csv?token=x",
            "data_hash": hashlib.sha256(content).hexdigest(),
            "version": 1,
            "row_count": 1,
            "column_count": 2,
        },
    )
    monkeypatch.setattr(store, "STAGING_SUPABASE_PROJECT_HOST", "hfhrosthswcybccepmak.supabase.co")
    monkeypatch.setattr(
        requests, "get",
        lambda *_args, **_kwargs: type("Response", (), {
            "status_code": 200, "content": content, "text": ""
        })(),
    )
    data, metadata = store.edge_download_dataset_version(
        "synthetic-user", "opaque-session-token", "plant-a",
        "DS-ABCDEF012345", version=1,
    )
    assert data == content
    assert metadata["version"] == 1
    assert calls[0][1]["version"] == 1



def test_historical_dataset_download_passes_selected_version_to_edge_action(monkeypatch):
    calls = []
    monkeypatch.setattr(
        store, "APP_ENVIRONMENT", "staging"
    )
    import hashlib
    import requests
    content = b"asset_id,units\nA-1,8\n"
    monkeypatch.setattr(
        store, "STAGING_SUPABASE_PROJECT_HOST",
        "hfhrosthswcybccepmak.supabase.co",
    )
    monkeypatch.setattr(
        store, "_edge_call",
        lambda action, payload: calls.append((action, dict(payload))) or {
            "ok": True,
            "download_url": "https://hfhrosthswcybccepmak.supabase.co/storage/v1/object/sign/shoir-industrial-datasets/workspace/DS-ABCDEF012345/file.csv?token=x",
            "data_hash": hashlib.sha256(content).hexdigest(),
            "version": 1,
            "row_count": 1,
            "column_count": 2,
        },
    )
    monkeypatch.setattr(
        requests, "get",
        lambda *_args, **_kwargs: type("Response", (), {
            "status_code": 200, "content": content, "text": ""
        })(),
    )
    downloaded, metadata = store.edge_download_dataset_version(
        "synthetic-user", "opaque-session-token", "plant-a",
        "DS-ABCDEF012345", version=1,
    )
    assert downloaded == content
    assert metadata["version"] == 1
    assert calls[0][0] == "dataset_download_url"
    assert calls[0][1]["version"] == 1


def test_historical_download_edge_action_selects_immutable_version_record():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] /
              "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    action = source.split('if (action === "dataset_download_url") {', 1)[1].split(
        'if (action === "dataset_upload_create") {', 1
    )[0]
    assert 'const recordType = requestedVersion === null' in action
    assert '"dataset_version"' in action
    assert 'datasetId + ":v" + requestedVersion' in action
    assert '.eq("workspace_key", workspaceKey)' in action



def test_dataset_finalize_recomputes_version_fingerprint_server_side():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] /
              "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    action = source.split('if (action === "dataset_version_finalize") {', 1)[1].split(
        'if (action === "dataset_version_register") {', 1
    )[0]
    assert "const expectedFingerprint = await sha256Hex(" in action
    assert "stablePlatformJson({" in action
    assert "dataset_id: datasetId" in action
    assert "data_hash: dataHash" in action
    assert "schema," in action
    assert "transformations," in action
    assert "expectedFingerprint !== fingerprint" in action



def test_every_dataset_edge_action_enforces_server_side_professional_entitlement():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] /
              "supabase/functions/shoir-persistence/index.ts").read_text(encoding="utf-8")
    actions = (
        "dataset_upload_create",
        "dataset_version_finalize",
        "dataset_version_register",
        "dataset_download_url",
    )
    for action_name in actions:
        action = source.split(
            f'if (action === "{action_name}") {{', 1
        )[1]
        next_action = action.find('if (action === "')
        action = action[:next_action] if next_action >= 0 else action
        assert "getSession(" in action, action_name
        assert "datasetEntitlementDenialForRequest(" in action, action_name
        assert "resolveManagedWorkspaceKey(" in action, action_name

    save = source.split('if (action === "platform_record_save") {', 1)[1].split(
        'if (action === "platform_record_list") {', 1
    )[0]
    assert 'recordType === "dataset"' in save
    assert 'recordType === "dataset_version"' in save
    assert "datasetEntitlementDenialForRequest(" in save

    listing = source.split('if (action === "platform_record_list") {', 1)[1].split(
        'if (action === "workspace_load") {', 1
    )[0]
    assert 'recordType === "dataset"' in listing
    assert 'recordType === "dataset_version"' in listing
    assert "datasetEntitlementDenialForRequest(" in listing

    personal_tier_guard = source.split(
        "function datasetEntitlementDenied(", 1
    )[1].split("\n}", 1)[0]
    assert 'platformTierAllows(row.tier, "Professional")' in personal_tier_guard

    request_guard = source.split(
        "async function datasetEntitlementDenialForRequest(", 1
    )[1].split("\n}", 1)[0]
    assert "if (organizationId || workspaceId)" in request_guard
    assert "if (!organizationId || !workspaceId)" in request_guard
    assert "await organizationForActor(" in request_guard
    assert "return datasetEntitlementDenial(row)" in request_guard



def test_platform_record_payload_rejects_bare_dob_key_on_python_and_edge():
    from pathlib import Path

    with pytest.raises(ValueError, match="Credential or sensitive"):
        store._validate_platform_record_payload({
            "asset": {"metadata": {"dob": "1980-01-01"}}
        })

    edge_source = (
        Path(__file__).resolve().parents[1]
        / "supabase/functions/shoir-persistence/index.ts"
    ).read_text(encoding="utf-8")
    # Ensure the Edge Function uses a real word-boundary escape rather than
    # matching a literal backslash sequence.
    assert r"\bdob\b" in edge_source
    assert r"\\bdob\\b" not in edge_source
