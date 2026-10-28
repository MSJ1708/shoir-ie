"""Fail-closed tests for legacy ERP/WMS placeholders.

These tests ensure the legacy supply-chain shell cannot present synthetic hard-coded
inventory as a live ERP read or report an unperformed write as successful.
"""
import pytest

from enterprise_engine import EnterpriseConnectorStub, EnterpriseSupplyChainEngine


def test_legacy_connector_read_refuses_to_fabricate_live_ledger():
    connector = EnterpriseConnectorStub("SAP_S4HANA_Cloud")

    with pytest.raises(NotImplementedError, match="no live ledger was read"):
        connector.fetch_live_ledger()


def test_legacy_connector_write_refuses_to_claim_transaction_success():
    connector = EnterpriseConnectorStub("Oracle_Cloud_ERP")

    with pytest.raises(NotImplementedError, match="no transaction was sent"):
        connector.push_transaction_back({"synthetic_order": "ORDER-001"})


def test_supply_chain_optimization_does_not_run_from_fake_erp_values():
    engine = EnterpriseSupplyChainEngine()

    with pytest.raises(NotImplementedError, match="no live ledger was read"):
        engine.optimize_network_flow(
            user_context={"role": "enterprise_controller", "user": "synthetic-reviewer"}
        )
