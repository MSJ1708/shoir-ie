import base64
import json
import pytest

import shoir_erp_connectors as erp
import shoir_erp_provider_transport as provider_transport
from shoir_erp_provider_transport import (
    ERPProviderTransportError,
    OracleFusionOAuthTransport,
    PinnedHTTPSJsonClient,
    SAPODataOAuthTransport,
    transport_for,
)


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers, body=None, max_response_bytes=None):
        self.calls.append((method, url, dict(headers), body, max_response_bytes))
        return self.responses.pop(0)


def profile(product_id="SAP_S4HANA_CLOUD_PUBLIC"):
    return erp.ERPConnectionProfile(
        product_id=product_id,
        workspace_id="workspace-a",
        connection_id="connection-a",
        tenant_ref="tenant-a",
        base_url="https://erp.example.test/odata",
        credential_ref="vault://shoir/sandbox-a",
        enabled=True,
        read_only=True,
    )


def credentials(_ref):
    return {
        "token_url": "https://identity.example.test/oauth2/token",
        "client_id": "synthetic-client",
        "client_secret": "synthetic-secret",
        "scope": "erp.read",
    }


def test_transport_factory_supports_cloud_products_and_fails_closed_for_legacy():
    assert isinstance(transport_for(
        "SAP_S4HANA_CLOUD_PUBLIC",
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
        credential_resolver=credentials,
    ), SAPODataOAuthTransport)
    assert isinstance(transport_for(
        "ORACLE_FUSION_ERP",
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
        credential_resolver=credentials,
    ), OracleFusionOAuthTransport)
    for legacy in ("SAP_ECC", "ORACLE_EBS"):
        with pytest.raises(ERPProviderTransportError, match="legacy auth adapters"):
            transport_for(
                legacy,
                allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
                credential_resolver=credentials,
            )


def test_sap_oauth_token_exchange_is_cached_and_odata_next_link_is_same_origin():
    fake = FakeHTTP([
        (200, "application/json", json.dumps({"access_token": "synthetic-access-token", "token_type": "Bearer", "expires_in": 3600}).encode()),
        (200, "application/json", json.dumps({"value": [{"Order": "1"}], "@odata.nextLink": "https://erp.example.test/odata/Orders?$skiptoken=abc"}).encode()),
        (200, "application/json", json.dumps({"value": [{"Order": "2"}]}).encode()),
    ])
    transport = SAPODataOAuthTransport(
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
        credential_resolver=credentials,
        http_client=fake,
    )
    first = transport.get_json(profile(), "Orders", page_token=None, page_size=100)
    assert first.payload["value"] == [{"Order": "1"}]
    assert first.next_page_token == "https://erp.example.test/odata/Orders?$skiptoken=abc"
    second = transport.get_json(profile(), "Orders", page_token=first.next_page_token, page_size=100)
    assert second.payload["value"] == [{"Order": "2"}]
    assert len(fake.calls) == 3  # one token POST, two read-only GETs
    assert fake.calls[0][0] == "POST"
    assert fake.calls[1][0] == "GET" and fake.calls[2][0] == "GET"
    assert "synthetic-secret" not in json.dumps(fake.calls)


def test_sap_transport_rejects_cross_origin_or_cross_path_next_link():
    fake = FakeHTTP([
        (200, "application/json", json.dumps({"access_token": "token", "token_type": "Bearer", "expires_in": 3600}).encode()),
        (200, "application/json", json.dumps({"value": [], "@odata.nextLink": "https://attacker.example.test/odata/Orders?$skiptoken=x"}).encode()),
    ])
    transport = SAPODataOAuthTransport(
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443), ("attacker.example.test", 443)},
        credential_resolver=credentials,
        http_client=fake,
    )
    with pytest.raises(ERPProviderTransportError, match="pagination link left"):
        transport.get_json(profile(), "Orders", page_token=None, page_size=100)


def test_oracle_fusion_has_more_uses_bounded_offset_pagination():
    fake = FakeHTTP([
        (200, "application/json", json.dumps({"access_token": "token", "token_type": "Bearer", "expires_in": 1800}).encode()),
        (200, "application/json", json.dumps({"items": [{"id": 1}, {"id": 2}], "hasMore": True}).encode()),
        (200, "application/json", json.dumps({"items": [{"id": 3}], "hasMore": False}).encode()),
    ])
    transport = OracleFusionOAuthTransport(
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
        credential_resolver=credentials,
        http_client=fake,
    )
    first = transport.get_json(profile("ORACLE_FUSION_ERP"), "fscmRestApi/resources/11.13.18.05/orders", page_token=None, page_size=2)
    assert first.next_page_token == "offset:2"
    second = transport.get_json(profile("ORACLE_FUSION_ERP"), "fscmRestApi/resources/11.13.18.05/orders", page_token=first.next_page_token, page_size=2)
    assert [item["id"] for item in second.payload["items"]] == [3]
    assert "offset=2" in fake.calls[2][1]


def test_provider_transport_refuses_redirect_and_invalid_token_response():
    fake = FakeHTTP([(302, "text/html", b"")])
    transport = SAPODataOAuthTransport(
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
        credential_resolver=credentials,
        http_client=fake,
    )
    with pytest.raises(ERPProviderTransportError, match="redirects are blocked"):
        transport.get_json(profile(), "Orders", page_token=None, page_size=100)


def test_pinned_http_client_checks_exact_host_and_never_follows_redirects():
    class NeverResolve:
        def __call__(self, *args, **kwargs):
            raise AssertionError("DNS must not be consulted for a non-allowlisted host.")
    client = PinnedHTTPSJsonClient(
        allowed_hosts={("erp.example.test", 443)},
        resolver=NeverResolve(),
    )
    with pytest.raises(ERPProviderTransportError, match="approved HTTPS destination"):
        client.request("GET", "https://attacker.example.test/odata", headers={})


@pytest.mark.parametrize("requested_limit", [0, -1, -2, 1025, True, 1.5])
def test_request_response_limit_override_must_remain_within_client_bound(monkeypatch, requested_limit):
    client = PinnedHTTPSJsonClient(
        allowed_hosts={("erp.example.test", 443)},
        max_response_bytes=1024,
    )

    def no_dns(*args, **kwargs):
        raise AssertionError("Invalid response limits must be rejected before DNS or network access.")

    monkeypatch.setattr(provider_transport, "_resolve_pinned_ip", no_dns)
    with pytest.raises(ERPProviderTransportError, match="response size limit"):
        client.request(
            "GET",
            "https://erp.example.test/odata/Orders",
            headers={},
            max_response_bytes=requested_limit,
        )


def test_oauth_token_cache_is_invalidated_when_client_secret_rotates():
    current_credentials = credentials(None)
    fake = FakeHTTP([
        (200, "application/json", json.dumps({"access_token": "token-before-rotation", "token_type": "Bearer", "expires_in": 3600}).encode()),
        (200, "application/json", json.dumps({"value": []}).encode()),
        (200, "application/json", json.dumps({"access_token": "token-after-rotation", "token_type": "Bearer", "expires_in": 3600}).encode()),
        (200, "application/json", json.dumps({"value": []}).encode()),
    ])
    transport = SAPODataOAuthTransport(
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
        credential_resolver=lambda _ref: dict(current_credentials),
        http_client=fake,
    )

    transport.get_json(profile(), "Orders", page_token=None, page_size=100)
    current_credentials["client_secret"] = "rotated-synthetic-secret"
    transport.get_json(profile(), "Orders", page_token=None, page_size=100)

    assert [call[0] for call in fake.calls] == ["POST", "GET", "POST", "GET"]
    assert "rotated-synthetic-secret" not in json.dumps(fake.calls)
