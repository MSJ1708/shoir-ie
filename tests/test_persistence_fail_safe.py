from durable_account_store import ephemeral_local_storage_allowed

def test_ephemeral_local_storage_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SHOIR_ALLOW_EPHEMERAL_LOCAL_STORAGE", raising=False)
    assert ephemeral_local_storage_allowed() is False
