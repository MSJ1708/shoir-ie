import base64
import json
from urllib.parse import parse_qs
import pytest

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

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

def serialized_calls(calls):
    """JSON-safe request trace for assertions; decode bounded byte bodies."""
    return json.dumps([
        {
            "method": method,
            "url": url,
            "headers": headers,
            "body": body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body,
            "max_response_bytes": response_limit,
        }
        for method, url, headers, body, response_limit in calls
    ])



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


def test_transport_factory_supports_sap_and_oracle_cloud_products_but_refuses_legacy():
    assert isinstance(transport_for(
        "SAP_S4HANA_CLOUD_PUBLIC",
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
        credential_resolver=credentials,
    ), SAPODataOAuthTransport)
    for oracle in ("ORACLE_FUSION_ERP", "ORACLE_FUSION_SCM"):
        assert isinstance(transport_for(
            oracle,
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
    assert "synthetic-secret" not in serialized_calls(fake.calls)


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


def _oracle_signing_key():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    return private_pem, private_key.public_key()


def _decode_and_verify_rs256(token, public_key):
    encoded_header, encoded_claims, encoded_signature = token.split(".")
    def decode(part):
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
    header = json.loads(decode(encoded_header))
    claims = json.loads(decode(encoded_claims))
    signature = decode(encoded_signature)
    public_key.verify(
        signature,
        (encoded_header + "." + encoded_claims).encode("ascii"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return header, claims


def test_oracle_fusion_jwt_user_and_client_assertions_are_signed_and_pagination_is_cached():
    private_pem, public_key = _oracle_signing_key()
    oracle_credentials = {
        "token_url": "https://identity.example.test/oauth2/v1/token",
        "identity_domain_url": "https://identity.example.test/",
        "client_id": "oracle-client",
        "user_subject": "shoir-readonly-service",
        "signing_key_id": "shoir-registered-cert",
        "signing_private_key_pem": private_pem,
        "scope": "https://identity.example.test/fscmRestApi.read",
    }
    fake = FakeHTTP([
        (200, "application/json", json.dumps({"access_token": "oracle-synthetic-token", "token_type": "Bearer", "expires_in": 1800}).encode()),
        (200, "application/json", json.dumps({"items": [{"id": 1}, {"id": 2}], "hasMore": True}).encode()),
        (200, "application/json", json.dumps({"items": [{"id": 3}], "hasMore": False}).encode()),
    ])
    transport = OracleFusionOAuthTransport(
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
        credential_resolver=lambda _ref: dict(oracle_credentials),
        http_client=fake,
    )

    first = transport.get_json(
        profile("ORACLE_FUSION_ERP"),
        "fscmRestApi/resources/11.13.18.05/orders",
        page_token=None,
        page_size=2,
    )
    assert first.next_page_token == "offset:2"
    second = transport.get_json(
        profile("ORACLE_FUSION_ERP"),
        "fscmRestApi/resources/11.13.18.05/orders",
        page_token=first.next_page_token,
        page_size=2,
    )
    assert [item["id"] for item in second.payload["items"]] == [3]
    assert [call[0] for call in fake.calls] == ["POST", "GET", "GET"]
    assert "offset=2" in fake.calls[2][1]

    form = parse_qs(fake.calls[0][3].decode("ascii"))
    assert form["grant_type"] == [OracleFusionOAuthTransport.USER_ASSERTION_GRANT]
    assert form["client_assertion_type"] == [OracleFusionOAuthTransport.CLIENT_ASSERTION_TYPE]
    assert form["client_id"] == ["oracle-client"]
    assert form["scope"] == [oracle_credentials["scope"]]
    assert "Authorization" not in fake.calls[0][2]
    assert "synthetic-secret" not in serialized_calls(fake.calls)
    assert private_pem not in serialized_calls(fake.calls)

    user_header, user_claims = _decode_and_verify_rs256(form["assertion"][0], public_key)
    client_header, client_claims = _decode_and_verify_rs256(form["client_assertion"][0], public_key)
    for header in (user_header, client_header):
        assert header == {"alg": "RS256", "kid": "shoir-registered-cert", "typ": "JWT"}
    assert user_claims["iss"] == "oracle-client"
    assert user_claims["sub"] == "shoir-readonly-service"
    assert client_claims["iss"] == "oracle-client"
    assert client_claims["sub"] == "oracle-client"
    for claims in (user_claims, client_claims):
        assert claims["aud"] == ["https://identity.example.test/"]
        assert claims["exp"] - claims["iat"] == OracleFusionOAuthTransport.ASSERTION_TTL_SECONDS
        assert claims["jti"]


def test_oracle_fusion_rejects_unapproved_token_host_and_non_rsa_signing_key_before_http():
    private_pem, _ = _oracle_signing_key()
    base_credentials = {
        "token_url": "https://identity.example.test/oauth2/v1/token",
        "identity_domain_url": "https://identity.example.test/",
        "client_id": "oracle-client",
        "user_subject": "shoir-readonly-service",
        "signing_key_id": "shoir-registered-cert",
        "signing_private_key_pem": private_pem,
        "scope": "https://identity.example.test/fscmRestApi.read",
    }
    for changed in (
        {**base_credentials, "token_url": "https://attacker.example.test/oauth2/v1/token"},
        {**base_credentials, "token_url": "https://identity.example.test/not-token"},
        {**base_credentials, "identity_domain_url": "https://attacker.example.test/"},
    ):
        fake = FakeHTTP([])
        transport = OracleFusionOAuthTransport(
            allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
            credential_resolver=lambda _ref, row=changed: row,
            http_client=fake,
        )
        with pytest.raises(ERPProviderTransportError):
            transport.get_json(
                profile("ORACLE_FUSION_ERP"),
                "fscmRestApi/resources/11.13.18.05/orders",
                page_token=None,
                page_size=2,
            )
        assert fake.calls == []

    small_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    small_pem = small_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    fake = FakeHTTP([])
    transport = OracleFusionOAuthTransport(
        allowed_hosts={("erp.example.test", 443), ("identity.example.test", 443)},
        credential_resolver=lambda _ref: {**base_credentials, "signing_private_key_pem": small_pem},
        http_client=fake,
    )
    with pytest.raises(ERPProviderTransportError, match="at least 2048 bits"):
        transport.get_json(
            profile("ORACLE_FUSION_ERP"),
            "fscmRestApi/resources/11.13.18.05/orders",
            page_token=None,
            page_size=2,
        )
    assert fake.calls == []


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
    assert "rotated-synthetic-secret" not in serialized_calls(fake.calls)
