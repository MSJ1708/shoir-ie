import ipaddress
import json
import socket

import pytest

import shoir_remaining_tool_engines as engines
import shoir_rest_connector as connector


def _valid_config(**overrides):
    values = {
        "SHOIR_CONNECTOR_PLANT_ENABLED": "true",
        "SHOIR_CONNECTOR_PLANT_ENDPOINT": "https://plant.example.test/api/v1",
        "SHOIR_CONNECTOR_PLANT_TOKEN": "secret-token-never-return",
        "SHOIR_CONNECTOR_PLANT_HEALTH_PATH": "health",
        "SHOIR_CONNECTOR_PLANT_READ_PATH": "sample",
        "SHOIR_CONNECTOR_ALLOWED_HOSTS": "plant.example.test",
        "SHOIR_CONNECTOR_APPROVED_PRIVATE_CIDRS": "",
        "SHOIR_CONNECTOR_TIMEOUT_SECONDS": "5",
    }
    values.update(overrides)
    return values


def _profile():
    return {
        "name": "Synthetic plant REST API",
        "protocol": "REST",
        "endpoint_env": "SHOIR_CONNECTOR_PLANT_ENDPOINT",
        "credential_env": "SHOIR_CONNECTOR_PLANT_TOKEN",
    }


def _install_success_mocks(monkeypatch, values=None, *, health=(200, "application/json", b'{"ok":true}'),
                           data=(200, "application/json", b'[{"station":"S1","count":7,"api_token":"fake-secret"}]')):
    cfg = values or _valid_config()
    monkeypatch.setattr(connector, "_config_value", lambda key: cfg.get(key, ""))
    monkeypatch.setattr(connector, "_resolve_pinned_ip", lambda *args, **kwargs: "8.8.8.8")
    responses = iter([health, data])
    calls = []

    def fake_get_response(host, port, pinned_ip, base_path, relative_path, token, timeout):
        calls.append({
            "host": host, "port": port, "path": relative_path,
            "token": token, "timeout": timeout, "pinned_ip": pinned_ip,
        })
        return next(responses)

    monkeypatch.setattr(connector, "_get_response", fake_get_response)
    return calls


def test_successful_readonly_rest_health_and_data_retrieval_redacts_preview(monkeypatch):
    calls = _install_success_mocks(monkeypatch)
    out = connector.verify_readonly_rest_connector(_profile(), include_sample_data=True)

    assert out["status"] == "DATA_RETRIEVAL_VERIFIED"
    assert out["connection_verified"] is True
    assert out["data_retrieval_verified"] is True
    assert out["health_http_status"] == 200
    assert out["read_http_status"] == 200
    assert out["record_count"] == 1
    assert out["sample_keys"] == ["station", "count", "api_token"]
    assert out["sample_preview"][0]["api_token"] == "[REDACTED]"
    assert calls[0]["path"] == "health"
    assert calls[1]["path"] == "sample"
    assert all(call["token"] == "secret-token-never-return" for call in calls)
    assert "secret-token-never-return" not in json.dumps(out)
    assert "https://plant.example.test" not in json.dumps(out)


def test_success_does_not_expose_preview_unless_explicitly_requested(monkeypatch):
    _install_success_mocks(monkeypatch)
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == "DATA_RETRIEVAL_VERIFIED"
    assert out["sample_preview"] is None
    assert len(out["response_sha256"]) == 64


def test_disabled_connector_fails_closed_without_network(monkeypatch):
    cfg = _valid_config(SHOIR_CONNECTOR_PLANT_ENABLED="false")
    monkeypatch.setattr(connector, "_config_value", lambda key: cfg.get(key, ""))
    monkeypatch.setattr(connector, "_resolve_pinned_ip", lambda *a, **k: pytest.fail("DNS must not run"))
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == "DISABLED_OR_REVOKED"
    assert out["attempted"] is False


@pytest.mark.parametrize("endpoint,expected", [
    ("http://plant.example.test/api", "CONFIGURATION_INVALID"),
    ("file:///etc/passwd", "CONFIGURATION_INVALID"),
    ("https://user:pass@plant.example.test/api", "CONFIGURATION_INVALID"),
    ("https://plant.example.test/api?token=x", "CONFIGURATION_INVALID"),
    ("https://unlisted.example.test/api", "DESTINATION_BLOCKED"),
])
def test_invalid_or_untrusted_endpoint_is_rejected(monkeypatch, endpoint, expected):
    cfg = _valid_config(SHOIR_CONNECTOR_PLANT_ENDPOINT=endpoint)
    monkeypatch.setattr(connector, "_config_value", lambda key: cfg.get(key, ""))
    monkeypatch.setattr(connector, "_resolve_pinned_ip", lambda *a, **k: "8.8.8.8")
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == expected
    assert out["connection_verified"] is False


def test_configuration_missing_and_token_revocation_are_reported(monkeypatch):
    cfg = _valid_config(SHOIR_CONNECTOR_PLANT_TOKEN="")
    monkeypatch.setattr(connector, "_config_value", lambda key: cfg.get(key, ""))
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == "NOT_CONFIGURED"
    assert out["attempted"] is False
    assert "secret-token-never-return" not in json.dumps(out)


@pytest.mark.parametrize("health_status,expected", [
    (302, "REDIRECT_BLOCKED"),
    (401, "AUTHENTICATION_REJECTED"),
    (403, "AUTHORIZATION_REJECTED"),
    (429, "RATE_LIMITED"),
    (503, "CONNECTION_FAILED"),
])
def test_health_failures_are_classified_without_reading_data(monkeypatch, health_status, expected):
    calls = _install_success_mocks(
        monkeypatch,
        health=(health_status, "application/json", b'{"ignored":"body"}'),
    )
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == expected
    assert len(calls) == 1
    assert out["data_retrieval_verified"] is False


@pytest.mark.parametrize("read_status,expected", [
    (302, "REDIRECT_BLOCKED"),
    (401, "AUTHENTICATION_REJECTED"),
    (403, "AUTHORIZATION_REJECTED"),
    (429, "RATE_LIMITED"),
    (500, "DATA_RETRIEVAL_FAILED"),
])
def test_data_read_failures_are_not_reported_as_verified(monkeypatch, read_status, expected):
    calls = _install_success_mocks(
        monkeypatch,
        data=(read_status, "application/json", b'{"ignored":"body"}'),
    )
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == expected
    assert len(calls) == 2
    assert out["connection_verified"] is False
    assert out["data_retrieval_verified"] is False


def test_malformed_json_and_wrong_content_type_fail_closed(monkeypatch):
    _install_success_mocks(monkeypatch, data=(200, "text/plain", b"not json"))
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == "MALFORMED_RESPONSE"

    _install_success_mocks(monkeypatch, data=(200, "application/json", b"{broken"))
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == "MALFORMED_RESPONSE"


def test_timeout_or_transport_failure_is_sanitized(monkeypatch):
    cfg = _valid_config()
    monkeypatch.setattr(connector, "_config_value", lambda key: cfg.get(key, ""))
    monkeypatch.setattr(connector, "_resolve_pinned_ip", lambda *args, **kwargs: "8.8.8.8")

    def timeout(*args, **kwargs):
        raise connector.ConnectorFailure("CONNECTION_FAILED_TIMEOUT", "safe remediation")

    monkeypatch.setattr(connector, "_get_response", timeout)
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == "CONNECTION_FAILED_TIMEOUT"
    assert out["remediation"] == "safe remediation"
    assert "secret-token-never-return" not in json.dumps(out)


def test_dns_resolver_blocks_cloud_metadata_and_unapproved_private_networks():
    metadata_records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))]
    with pytest.raises(connector.ConnectorFailure) as err:
        connector._resolve_pinned_ip("metadata.example.test", 443, (), resolver=lambda *a, **k: metadata_records)
    assert err.value.status == "DESTINATION_BLOCKED"

    private_records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.10.1.5", 443))]
    with pytest.raises(connector.ConnectorFailure) as err:
        connector._resolve_pinned_ip("plant.private.test", 443, (), resolver=lambda *a, **k: private_records)
    assert err.value.status == "DESTINATION_BLOCKED"

    approved = (ipaddress.ip_network("10.0.0.0/8"),)
    assert connector._resolve_pinned_ip(
        "plant.private.test", 443, approved, resolver=lambda *a, **k: private_records
    ) == "10.10.1.5"


def test_private_cidr_configuration_rejects_link_local_and_metadata_ranges():
    with pytest.raises(connector.ConnectorFailure):
        connector._parse_approved_private_cidrs("169.254.0.0/16")
    with pytest.raises(connector.ConnectorFailure):
        connector._parse_approved_private_cidrs("0.0.0.0/0")
    assert connector._parse_approved_private_cidrs("10.0.0.0/8")


def test_bounded_response_limit_and_no_redirect_following(monkeypatch):
    class FakeResponse:
        status = 200

        def __init__(self, headers, body):
            self.headers = headers
            self.body = body

        def getheader(self, name):
            return self.headers.get(name)

        def read(self, amount):
            return self.body[:amount]

    class FakeConnection:
        def __init__(self, *args, **kwargs):
            self.response = FakeResponse({"Content-Length": str(connector._MAX_RESPONSE_BYTES + 1)}, b"x")

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return self.response

        def close(self):
            pass

    monkeypatch.setattr(connector, "_PinnedHTTPSConnection", FakeConnection)
    with pytest.raises(connector.ConnectorFailure) as err:
        connector._get_response("plant.example.test", 443, "8.8.8.8", "", "sample", "token", 5)
    assert err.value.status == "RESPONSE_TOO_LARGE"


def test_configuration_inspection_never_triggers_dns_or_http(monkeypatch):
    monkeypatch.setattr(connector.socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS must not run during inspection"))
    monkeypatch.setattr(connector.socket, "create_connection", lambda *a, **k: pytest.fail("HTTP must not run during inspection"))
    out = engines.integration_configuration_status({
        "profiles": [{
            "name": "Synthetic plant",
            "protocol": "REST",
            "endpoint_env": "SHOIR_CONNECTOR_PLANT_ENDPOINT",
            "credential_env": "SHOIR_CONNECTOR_PLANT_TOKEN",
        }],
    })
    assert out["status"] == "CONFIGURATION_INSPECTED"
    assert out["connected_count"] == 0


def test_non_rest_protocol_cannot_use_generic_adapter(monkeypatch):
    cfg = _valid_config()
    monkeypatch.setattr(connector, "_config_value", lambda key: cfg.get(key, ""))
    out = connector.verify_readonly_rest_connector({**_profile(), "protocol": "SAP"})
    assert out["status"] == "CONFIGURATION_INVALID"

def test_live_t096_operation_requires_authenticated_admin_and_entitlement(monkeypatch):
    import streamlit as st

    state = {
        "authenticated": False,
        "current_user": "",
        "user_role": "Engineer",
        "user_tier": "Enterprise",
    }
    monkeypatch.setattr(st, "session_state", state, raising=True)
    with pytest.raises(PermissionError):
        engines._require_connector_operator()

    state.update({
        "authenticated": True,
        "current_user": "disposable-admin",
        "user_role": "Engineer",
        "user_tier": "Enterprise",
    })
    with pytest.raises(PermissionError):
        engines._require_connector_operator()

    state.update({"user_role": "Enterprise Admin", "user_tier": "Starter"})
    with pytest.raises(PermissionError):
        engines._require_connector_operator()

    state.update({"user_tier": "Enterprise"})
    engines._require_connector_operator()


def test_explicit_live_action_checks_authorization_before_adapter(monkeypatch):
    monkeypatch.setattr(engines, "_require_connector_operator", lambda: (_ for _ in ()).throw(PermissionError("denied")))
    monkeypatch.setattr(
        engines, "verify_readonly_rest_connector",
        lambda *a, **k: pytest.fail("adapter must not run after authorization denial"),
    )
    with pytest.raises(PermissionError, match="denied"):
        engines.integration_configuration_status({
            "action": "verify_rest_read",
            "profile": _profile(),
        })


def test_explicit_live_action_routes_approved_profile_to_adapter(monkeypatch):
    import durable_account_store

    observed = {}
    monkeypatch.setattr(engines, "_require_connector_operator", lambda: None)
    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")

    def fake_adapter(profile, include_sample_data=False):
        observed["profile"] = profile
        observed["include_sample_data"] = include_sample_data
        return {"tool_id": "T096", "status": "DATA_RETRIEVAL_VERIFIED"}

    monkeypatch.setattr(engines, "verify_readonly_rest_connector", fake_adapter)
    out = engines.integration_configuration_status({
        "action": "verify_rest_read",
        "profile": _profile(),
        "include_sample_data": True,
    })
    assert out["status"] == "DATA_RETRIEVAL_VERIFIED"
    assert observed["profile"] == _profile()
    assert observed["include_sample_data"] is True


def test_live_t096_rest_verification_is_denied_outside_staging(monkeypatch):
    import durable_account_store

    monkeypatch.setattr(engines, "_require_connector_operator", lambda: None)
    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "production")
    monkeypatch.setattr(
        engines,
        "verify_readonly_rest_connector",
        lambda *a, **k: pytest.fail("Production must not make outbound connector requests."),
    )
    with pytest.raises(PermissionError, match="only in the authorized staging environment"):
        engines.integration_configuration_status({
            "action": "verify_rest_read",
            "profile": _profile(),
        })


def test_live_rest_adapter_rejects_non_token_credentials(monkeypatch):
    cfg = _valid_config()
    monkeypatch.setattr(connector, "_config_value", lambda key: cfg.get(key, ""))
    profile = {**_profile(), "credential_env": "SHOIR_CONNECTOR_PLANT_CREDENTIAL"}
    out = connector.verify_readonly_rest_connector(profile)
    assert out["status"] == "CONFIGURATION_INVALID"

def test_live_rest_action_requires_boolean_sample_preview(monkeypatch):
    monkeypatch.setattr(engines, "_require_connector_operator", lambda: None)
    monkeypatch.setattr(
        engines, "verify_readonly_rest_connector",
        lambda *a, **k: pytest.fail("string values must not enable preview"),
    )
    with pytest.raises(ValueError, match="must be a JSON boolean"):
        engines.integration_configuration_status({
            "action": "verify_rest_read",
            "profile": _profile(),
            "include_sample_data": "false",
        })


def test_endpoint_not_allowlisted_is_not_reported_as_network_attempt(monkeypatch):
    cfg = _valid_config(SHOIR_CONNECTOR_PLANT_ENDPOINT="https://unlisted.example.test/api")
    monkeypatch.setattr(connector, "_config_value", lambda key: cfg.get(key, ""))
    monkeypatch.setattr(connector, "_resolve_pinned_ip", lambda *a, **k: pytest.fail("allowlist check precedes DNS"))
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == "DESTINATION_BLOCKED"
    assert out["attempted"] is False


def test_connector_token_control_characters_are_rejected_without_exposure(monkeypatch):
    cfg = _valid_config(SHOIR_CONNECTOR_PLANT_TOKEN="token\r\nInjected: header")
    monkeypatch.setattr(connector, "_config_value", lambda key: cfg.get(key, ""))
    out = connector.verify_readonly_rest_connector(_profile())
    assert out["status"] == "CONFIGURATION_INVALID"
    assert out["attempted"] is False
    assert "Injected" not in json.dumps(out)

def test_sample_preview_redacts_common_personal_and_location_fields():
    preview = connector._redacted_preview({
        "full_name": "SYNTHETIC PERSON",
        "employee_id": "SYNTH-EMP-001",
        "customer_name": "SYNTHETIC CUSTOMER",
        "home_address": "123 Example Road",
        "birth_date": "1990-01-01",
        "contact_phone": "+1-555-0100",
        "location": "SYNTHETIC LOCATION",
        "station": "S1",
        "count": 7,
    })
    for key in (
        "full_name",
        "employee_id",
        "customer_name",
        "home_address",
        "birth_date",
        "contact_phone",
        "location",
    ):
        assert preview[key] == "[REDACTED]"
    assert preview["station"] == "S1"
    assert preview["count"] == 7

def test_provider_erp_read_uses_server_configuration_and_returns_metadata_only(monkeypatch):
    import durable_account_store
    import shoir_remaining_tool_engines as engines
    import streamlit as st
    import shoir_erp_provider_transport as provider_transport

    state = {
        "authenticated": True,
        "current_user": "provider-admin",
        "remote_session_token": "synthetic-session-token",
        "user_role": "Enterprise Admin",
        "user_tier": "Enterprise Plus Tier",
    }
    monkeypatch.setattr(st, "session_state", state, raising=True)
    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(engines, "_require_connector_operator", lambda: None)
    monkeypatch.setattr(
        durable_account_store,
        "_active_organization_workspace_context",
        lambda: {"organization_id": "org-a", "organization_workspace_id": "workspace-a"},
    )
    edge_actions = []
    def fake_edge_call(action, payload):
        edge_actions.append(action)
        if action != "session_verify":
            pytest.fail("The server-side session verifier should be the only direct Edge call.")
        assert payload["username"] == "provider-admin"
        assert payload["token"] == "synthetic-session-token"
        return {
            "ok": True, "username": "provider-admin", "role": "Enterprise Admin",
            "tier": "Enterprise Plus Tier", "active": True,
        }
    monkeypatch.setattr(durable_account_store, "_edge_call", fake_edge_call)
    def fake_org_action(action, username, token, **payload):
        edge_actions.append(action)
        assert action == "workspace_manage_check"
        assert username == "provider-admin"
        assert token == "synthetic-session-token"
        assert payload == {"organization_id": "org-a", "organization_workspace_id": "workspace-a"}
        return {"ok": True}
    monkeypatch.setattr(durable_account_store, "edge_organization_action", fake_org_action)
    connection_catalog = {
        "sap-plant": {
            "connection": {
                "product_id": "SAP_S4HANA_CLOUD_PUBLIC",
                "workspace_id": "workspace-a",
                "tenant_ref": "synthetic-tenant",
                "base_url": "https://erp.example.test/odata",
                "credential_ref": "vault://shoir/sap-plant",
                "enabled": True,
                "read_only": True,
            },
            "bindings": {
                "production_orders": {
                    "source_path": "API_PRODUCTION_ORDER_2_SRV/A_ProductionOrder_2",
                    "records_path": "value",
                    "entity_type": "Order",
                    "id_path": "ProductionOrder",
                    "field_map": {"order_number": "ProductionOrder"},
                    "required_fields": ["order_number"],
                    "mapping_version": "1",
                    "max_records": 100,
                    "max_pages": 5,
                },
            },
        },
    }
    credential_catalog = {
        "vault://shoir/sap-plant": {
            "token_url": "https://identity.example.test/oauth2/token",
            "client_id": "synthetic-client",
            "client_secret": "synthetic-provider-secret",
            "scope": "erp.read",
        },
    }
    values = {
        "SHOIR_ERP_CONNECTIONS_JSON": json.dumps(connection_catalog),
        "SHOIR_ERP_CREDENTIALS_JSON": json.dumps(credential_catalog),
        "SHOIR_ERP_ALLOWED_HOSTS": "erp.example.test;identity.example.test",
        "SHOIR_ERP_APPROVED_PRIVATE_CIDRS": "",
        "SHOIR_ERP_TIMEOUT_SECONDS": "5",
    }
    monkeypatch.setattr(engines, "_configuration_value", lambda key: values.get(key, ""))
    captured = {}

    def fake_read(connection, binding, **kwargs):
        captured["connection"] = connection
        captured["binding"] = binding
        captured["kwargs"] = kwargs
        credential = kwargs["credential_resolver"](connection.credential_ref)
        captured["credential"] = credential
        assert kwargs["authorize"](
            "provider-admin", "workspace-a", "sap-plant", "production_orders"
        ) is True
        return {
            "tool_id": "T096",
            "product_id": connection.product_id,
            "resource_key": binding.resource_key,
            "status": "READ_COMPLETED",
            "read_only": True,
            "pages_read": 1,
            "record_count": 2,
            "rejected_record_count": 0,
            "duplicate_record_count": 0,
            "conflicting_duplicate_count": 0,
            "truncated": False,
            "mapping_version": "1",
            "records_sha256": "a" * 64,
            "read_at_utc": "2026-11-20T18:00:00+00:00",
            "records": [{"entity_type": "Order", "fields": {"order_number": "1000"}}],
            "warning": "Synthetic test only.",
        }

    monkeypatch.setattr(provider_transport, "read_provider_resource", fake_read)
    out = engines.integration_configuration_status({
        "action": "verify_provider_read",
        "profile": {"connection_id": "sap-plant", "resource_key": "production_orders"},
    })
    assert out["status"] == "READ_COMPLETED"
    assert out["record_count"] == 2
    assert out["records_sha256"] == "a" * 64
    assert out["data_provenance"] == "EXTERNAL_PROVIDER_READ_UNVERIFIED"
    assert "records" not in out
    assert "synthetic-provider-secret" not in json.dumps(out)
    assert captured["connection"].read_only is True
    assert captured["binding"].resource_key == "production_orders"
    assert captured["credential"]["client_secret"] == "synthetic-provider-secret"
    assert edge_actions == ["session_verify", "workspace_manage_check"]


def test_provider_erp_read_fails_closed_without_server_allowlist(monkeypatch):
    import durable_account_store
    import shoir_remaining_tool_engines as engines
    import streamlit as st

    state = {
        "authenticated": True,
        "current_user": "provider-admin",
        "remote_session_token": "synthetic-session-token",
        "user_role": "Enterprise Admin",
        "user_tier": "Enterprise Plus Tier",
    }
    monkeypatch.setattr(st, "session_state", state, raising=True)
    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(engines, "_require_connector_operator", lambda: None)
    monkeypatch.setattr(durable_account_store, "_active_organization_workspace_context", lambda: None)
    monkeypatch.setattr(durable_account_store, "_edge_call", lambda action, payload: {
        "ok": True, "username": "provider-admin", "role": "Enterprise Admin",
        "tier": "Enterprise Plus Tier", "active": True,
    })
    monkeypatch.setattr(engines, "_configuration_value", lambda key: "")
    with pytest.raises(PermissionError, match="SHOIR_ERP_CONNECTIONS_JSON"):
        engines.integration_configuration_status({
            "action": "verify_provider_read",
            "profile": {"connection_id": "missing", "resource_key": "production_orders"},
        })


def test_provider_erp_read_rejects_shared_workspace_without_server_manage_permission(monkeypatch):
    import durable_account_store
    import shoir_remaining_tool_engines as engines
    import streamlit as st
    import shoir_erp_provider_transport as provider_transport

    state = {
        "authenticated": True,
        "current_user": "provider-admin",
        "remote_session_token": "synthetic-session-token",
        "user_role": "Enterprise Admin",
        "user_tier": "Enterprise Plus Tier",
    }
    monkeypatch.setattr(st, "session_state", state, raising=True)
    monkeypatch.setattr(durable_account_store, "APP_ENVIRONMENT", "staging")
    monkeypatch.setattr(engines, "_require_connector_operator", lambda: None)
    monkeypatch.setattr(
        durable_account_store, "_active_organization_workspace_context",
        lambda: {"organization_id": "org-a", "organization_workspace_id": "workspace-a"},
    )
    monkeypatch.setattr(
        durable_account_store, "_edge_call",
        lambda action, payload: {
            "ok": True, "username": "provider-admin", "role": "Enterprise Admin",
            "tier": "Enterprise Plus Tier", "active": True,
        } if action == "session_verify" else pytest.fail("unexpected direct Edge call"),
    )
    monkeypatch.setattr(
        durable_account_store, "edge_organization_action",
        lambda *args, **kwargs: {"error": "ORGANIZATION_WORKSPACE_ACCESS_DENIED"},
    )
    monkeypatch.setattr(engines, "_configuration_value", lambda key: pytest.fail("Provider config must not be read before workspace authorization."))
    monkeypatch.setattr(provider_transport, "read_provider_resource", lambda *args, **kwargs: pytest.fail("Provider request must not be sent without workspace manage permission."))
    with pytest.raises(PermissionError, match="Owner/Admin permission"):
        engines.integration_configuration_status({
            "action": "verify_provider_read",
            "profile": {"connection_id": "sap-plant", "resource_key": "production_orders"},
        })


def test_t096_provider_session_and_workspace_manage_routes_are_server_authorized():
    from pathlib import Path
    import durable_account_store

    root = Path(__file__).resolve().parents[1]
    edge = (
        root / "supabase/functions/shoir-persistence/index.ts"
    ).read_text(encoding="utf-8")
    session_start = edge.index('if (action === "session_verify")')
    session_end = edge.index('if (action === "workspace_manage_check")', session_start)
    session_action = edge[session_start:session_end]
    assert 'await getSession(' in session_action
    assert 'String(body.token || "")' in session_action
    assert 'String(body.username || "")' in session_action
    assert 'active: actor.active === true' in session_action
    manage_start = edge.index('if (action === "workspace_manage_check")')
    manage_end = edge.index('if (action === "workspace_access_check")', manage_start)
    manage_action = edge[manage_start:manage_end]
    assert 'await getSession(' in manage_action
    assert 'resolveManagedWorkspaceKey(' in manage_action
    assert '"manage"' in manage_action
    assert '"workspace_manage_check"' in durable_account_store._ORGANIZATION_EDGE_ACTIONS
