import hashlib
import json

import pytest

import shoir_erp_connectors as erp


def connection(**overrides):
    values = {
        "product_id": "SAP_S4HANA_CLOUD_PUBLIC",
        "workspace_id": "workspace-a",
        "connection_id": "conn-a",
        "tenant_ref": "sap-sandbox-a",
        "base_url": "https://sap.example.test/sap/opu/odata4",
        "credential_ref": "env:SAP_SANDBOX_TOKEN",
        "enabled": True,
        "read_only": True,
    }
    values.update(overrides)
    return erp.ERPConnectionProfile(**values)


def binding(**overrides):
    values = {
        "resource_key": "production_orders",
        "source_path": "API_PRODUCTION_ORDER_2_SRV/A_ProductionOrder_2",
        "records_path": "value",
        "entity_type": "Order",
        "id_path": "ProductionOrder",
        "field_map": {
            "plant_code": "ProductionPlant",
            "planned_quantity": "PlannedTotalQuantity",
        },
        "required_fields": ("plant_code",),
        "units": {"planned_quantity": "EA"},
        "currency_path": "",
        "source_timestamp_path": "LastChangeDateTime",
        "source_timezone": "Europe/Berlin",
        "mapping_version": "sap-prod-order-v1",
        "max_records": 100,
        "max_pages": 3,
    }
    values.update(overrides)
    return erp.ERPResourceBinding(**values)


class FakeTransport:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get_json(self, conn, path, *, page_token, page_size):
        self.calls.append((conn.connection_id, path, page_token, page_size))
        return self.pages.pop(0)


def auth_ok(actor, workspace_id, connection_id, resource_key):
    return actor == "admin-a" and workspace_id == "workspace-a" and connection_id == "conn-a" and resource_key == "production_orders"


def test_exact_product_ids_keep_cloud_and_legacy_adapters_separate():
    assert type(erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC")).__name__ == "SAPS4HANACloudPublicAdapter"
    assert type(erp.adapter_for("SAP_ECC")).__name__ == "SAPECCAdapter"
    assert type(erp.adapter_for("ORACLE_FUSION_ERP")).__name__ == "OracleFusionERPAdapter"
    assert type(erp.adapter_for("ORACLE_FUSION_SCM")).__name__ == "OracleFusionSCMAdapter"
    assert type(erp.adapter_for("ORACLE_EBS")).__name__ == "OracleEBSAdapter"
    with pytest.raises(erp.ERPConnectorError, match="exact product ID"):
        erp.adapter_for("ORACLE")


def test_product_catalog_does_not_claim_a_live_connection():
    catalog = erp.product_catalog()
    assert len(catalog) == 6
    assert {item["status"] for item in catalog} == {"SPECIFICATION_ONLY_UNCONFIGURED"}
    assert "credential" not in json.dumps(catalog).lower()


def test_missing_authorization_fails_before_transport():
    transport = FakeTransport([erp.TransportPage({"value": []})])
    with pytest.raises(erp.ERPConnectorError) as error:
        erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
            connection(), binding(), transport, actor_id="admin-a",
            active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)},
            authorize=None,
        )
    assert error.value.code == "AUTHORIZATION_REQUIRED"
    assert transport.calls == []


def test_cross_workspace_use_fails_before_transport():
    transport = FakeTransport([erp.TransportPage({"value": []})])
    with pytest.raises(erp.ERPConnectorError) as error:
        erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
            connection(), binding(), transport, actor_id="admin-a",
            active_workspace_id="workspace-b", allowed_hosts={("sap.example.test", 443)},
            authorize=auth_ok,
        )
    assert error.value.code == "WORKSPACE_DENIED"
    assert transport.calls == []


def test_authorization_denial_fails_before_transport():
    transport = FakeTransport([erp.TransportPage({"value": []})])
    with pytest.raises(erp.ERPConnectorError) as error:
        erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
            connection(), binding(), transport, actor_id="viewer",
            active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)},
            authorize=lambda *args: False,
        )
    assert error.value.code == "ACCESS_DENIED"
    assert transport.calls == []


@pytest.mark.parametrize(
    "profile,hosts,code",
    [
        ({"base_url": "http://sap.example.test/api"}, {("sap.example.test", 443)}, "CONFIGURATION_INVALID"),
        ({"base_url": "https://user:pass@sap.example.test/api"}, {("sap.example.test", 443)}, "CONFIGURATION_INVALID"),
        ({"base_url": "https://sap.example.test/api?token=x"}, {("sap.example.test", 443)}, "CONFIGURATION_INVALID"),
        ({"base_url": "https://unapproved.example.test/api"}, {("sap.example.test", 443)}, "DESTINATION_BLOCKED"),
        ({"credential_ref": "Bearer super-secret-token"}, {("sap.example.test", 443)}, "CREDENTIAL_REFERENCE_INVALID"),
        ({"read_only": False}, {("sap.example.test", 443)}, "READ_ONLY_REQUIRED"),
    ],
)
def test_invalid_connection_profiles_fail_closed(profile, hosts, code):
    conn = connection(**profile)
    transport = FakeTransport([erp.TransportPage({"value": []})])
    with pytest.raises(erp.ERPConnectorError) as error:
        erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
            conn, binding(), transport, actor_id="admin-a",
            active_workspace_id="workspace-a", allowed_hosts=hosts, authorize=auth_ok,
        )
    assert error.value.code == code
    assert transport.calls == []


def test_provider_mismatch_and_unsafe_resource_path_are_rejected():
    transport = FakeTransport([erp.TransportPage({"value": []})])
    with pytest.raises(erp.ERPConnectorError) as mismatch:
        erp.adapter_for("ORACLE_EBS").read_resource(
            connection(), binding(), transport, actor_id="admin-a",
            active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)}, authorize=auth_ok,
        )
    assert mismatch.value.code == "PRODUCT_MISMATCH"
    with pytest.raises(erp.ERPConnectorError) as path:
        erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
            connection(), binding(source_path="../private"), transport, actor_id="admin-a",
            active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)}, authorize=auth_ok,
        )
    assert path.value.code == "RESOURCE_PATH_INVALID"
    assert transport.calls == []


def test_only_explicitly_mapped_fields_are_emitted_with_lineage():
    raw = {
        "value": [{
            "ProductionOrder": "1000243",
            "ProductionPlant": "PL01",
            "PlannedTotalQuantity": 12,
            "EmployeeName": "do not map",
            "email": "private@example.test",
            "access_token": "never copy",
            "LastChangeDateTime": "2026-10-26T10:00:00+02:00",
            "unmapped_field": "not copied",
        }]
    }
    transport = FakeTransport([erp.TransportPage(raw)])
    result = erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
        connection(), binding(), transport, actor_id="admin-a",
        active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)}, authorize=auth_ok,
    )
    assert result["status"] == "READ_COMPLETED"
    assert result["read_only"] is True
    assert result["record_count"] == 1
    record = result["records"][0]
    assert record["fields"] == {"plant_code": "PL01", "planned_quantity": 12}
    assert record["lineage"]["source_timestamp_utc"] == "2026-10-26T08:00:00+00:00"
    assert record["lineage"]["units"] == {"planned_quantity": "EA"}
    assert record["lineage"]["currency"] is None
    serialized = json.dumps(result)
    for secret in ("private@example.test", "never copy", "do not map", "1000243"):
        assert secret not in serialized
    expected_hash = hashlib.sha256(b"conn-a|production_orders|1000243").hexdigest()
    assert record["lineage"]["source_object_hash"] == expected_hash


def test_missing_required_field_and_identifier_are_counted_without_raw_payload():
    transport = FakeTransport([erp.TransportPage({"value": [
        {"ProductionOrder": "1001", "PlannedTotalQuantity": 5},
        {"ProductionPlant": "PL01", "PlannedTotalQuantity": 7},
    ]})])
    result = erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
        connection(), binding(), transport, actor_id="admin-a",
        active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)}, authorize=auth_ok,
    )
    assert result["record_count"] == 0
    assert result["rejected_record_count"] == 2
    assert result["status"] == "PARTIAL_READ"


def test_nested_response_contract_is_explicit_for_oracle_style_collection():
    transport = FakeTransport([erp.TransportPage({"items": [{"orderNumber": "OR-1", "organizationCode": "M1"}]})])
    oracle_binding = binding(
        records_path="items", id_path="orderNumber",
        field_map={"plant_code": "organizationCode"},
        required_fields=("plant_code",), units={}, source_timestamp_path="",
        source_timezone="", mapping_version="oracle-fusion-contract-v1",
    )
    result = erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
        connection(), oracle_binding, transport, actor_id="admin-a",
        active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)}, authorize=auth_ok,
    )
    assert result["record_count"] == 1
    assert result["records"][0]["fields"]["plant_code"] == "M1"


def test_pagination_is_bounded_and_token_loop_is_rejected():
    transport = FakeTransport([
        erp.TransportPage({"value": [{"ProductionOrder": "1001", "ProductionPlant": "PL01"}]}, "next"),
        erp.TransportPage({"value": [{"ProductionOrder": "1002", "ProductionPlant": "PL02"}]}, "next"),
    ])
    with pytest.raises(erp.ERPConnectorError) as error:
        erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
            connection(), binding(), transport, actor_id="admin-a",
            active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)}, authorize=auth_ok,
        )
    assert error.value.code == "PAGINATION_LOOP"
    assert len(transport.calls) == 2


def test_identical_duplicate_is_counted_and_conflicting_duplicate_is_excluded():
    raw = {"value": [
        {"ProductionOrder": "1001", "ProductionPlant": "PL01"},
        {"ProductionOrder": "1001", "ProductionPlant": "PL01"},
        {"ProductionOrder": "1002", "ProductionPlant": "PL02"},
        {"ProductionOrder": "1002", "ProductionPlant": "PL99"},
    ]}
    transport = FakeTransport([erp.TransportPage(raw)])
    result = erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
        connection(), binding(), transport, actor_id="admin-a",
        active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)}, authorize=auth_ok,
    )
    assert result["record_count"] == 1
    assert result["duplicate_record_count"] == 1
    assert result["conflicting_duplicate_count"] == 1
    assert result["status"] == "PARTIAL_READ"
    assert [item["fields"]["plant_code"] for item in result["records"]] == ["PL01"]


def test_transport_exception_is_redacted():
    transport = FakeTransport([])
    def fail(*args, **kwargs):
        raise RuntimeError("Bearer super-secret-token at https://sap.example.test/private?token=private")
    transport.get_json = fail
    with pytest.raises(erp.ERPConnectorError) as error:
        erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
            connection(), binding(), transport, actor_id="admin-a",
            active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)}, authorize=auth_ok,
        )
    assert error.value.code == "TRANSPORT_FAILURE"
    assert "super-secret-token" not in str(error.value)
    assert "private" not in str(error.value)


def test_missing_or_invalid_currency_does_not_create_a_canonical_record():
    transport = FakeTransport([erp.TransportPage({"value": [
        {"ProductionOrder": "1001", "ProductionPlant": "PL01", "Currency": "usd"}
    ]})])
    oracle_binding = binding(currency_path="Currency")
    result = erp.adapter_for("SAP_S4HANA_CLOUD_PUBLIC").read_resource(
        connection(), oracle_binding, transport, actor_id="admin-a",
        active_workspace_id="workspace-a", allowed_hosts={("sap.example.test", 443)}, authorize=auth_ok,
    )
    assert result["record_count"] == 0
    assert result["rejected_record_count"] == 1
    assert result["status"] == "PARTIAL_READ"
