"""HTTP-boundary tests for the authenticated staging release gate."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import authenticated_release_gate as gate


class FakeResponse:
    status_code = 200

    def __init__(self, body, error=None):
        self.body = body
        self.error = error

    def json(self):
        if self.error is not None:
            raise self.error
        return self.body


def test_edge_api_sends_current_publishable_key_only_as_apikey(monkeypatch):
    observed = {}

    def fake_post(url, *, json, headers, timeout):
        observed.update({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return FakeResponse({"ok": True})

    monkeypatch.setattr(gate.requests, "post", fake_post)
    api = gate.EdgeAPI(
        "https://hfhrosthswcybccepmak.supabase.co/functions/v1/shoir-persistence",
        "sb_publishable_synthetic-test-key",
    )
    status, data = api.call("org_list_session", {"username": "shoir-e2e-owner"})

    assert status == 200
    assert data == {"ok": True}
    assert observed["headers"]["apikey"] == "sb_publishable_synthetic-test-key"
    assert "Authorization" not in observed["headers"]
    assert observed["json"]["action"] == "org_list_session"
    assert observed["timeout"] == gate.TIMEOUT


def test_edge_api_supports_legacy_anon_jwt_bearer_header(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        gate.requests,
        "post",
        lambda url, **kwargs: captured.update(kwargs) or FakeResponse({"ok": True}),
    )
    api = gate.EdgeAPI("https://staging.example.invalid/function", "eyJ.synthetic.anon.jwt")
    api.call("login", {"username": "shoir-e2e-owner"})
    assert captured["headers"]["Authorization"] == "Bearer eyJ.synthetic.anon.jwt"
    assert captured["headers"]["apikey"] == "eyJ.synthetic.anon.jwt"


@pytest.mark.parametrize("body", [["unexpected"], "unexpected", 123, None])
def test_edge_api_normalizes_non_object_json_as_a_safe_error(monkeypatch, body):
    monkeypatch.setattr(
        gate.requests,
        "post",
        lambda url, **kwargs: FakeResponse(body),
    )
    api = gate.EdgeAPI("https://staging.example.invalid/function", "sb_publishable_synthetic")
    status, data = api.call("org_list_session", {"username": "shoir-e2e-owner"})

    assert status == 200
    assert data == {"error": "The staging API returned a non-object JSON response."}


def test_edge_api_normalizes_invalid_json_as_a_safe_error(monkeypatch):
    monkeypatch.setattr(
        gate.requests,
        "post",
        lambda url, **kwargs: FakeResponse(None, ValueError("synthetic parse error")),
    )
    api = gate.EdgeAPI("https://staging.example.invalid/function", "sb_publishable_synthetic")
    status, data = api.call("org_list_session", {"username": "shoir-e2e-owner"})

    assert status == 200
    assert data == {}
