# SAP and Oracle ERP Support Boundary

**Status: specification and mapper foundation only. No live SAP or Oracle tenant has been connected or accepted.**

Last reviewed: 26 October 2026. Product API and authentication configuration must be rechecked against the customer's exact release and enabled services before a connector is enabled.

## Product compatibility matrix

| Product ID used by Shoir-IE | Intended adapter boundary | Authoritative API source | Authentication and network prerequisite | Current status |
|---|---|---|---|---|
| `SAP_S4HANA_CLOUD_PUBLIC` | SAP S/4HANA Cloud Public Edition only | [SAP Business Accelerator Hub — S/4HANA Cloud](https://api.sap.com/) | Customer confirms the exact released API, communication scenario/arrangement, service account or provider-supported OAuth/certificate setup, and least-privilege scopes | Specification only; endpoint, auth and tenant acceptance not configured |
| `SAP_S4HANA_CLOUD_PRIVATE` | SAP S/4HANA Cloud Private Edition and customer-managed S/4HANA deployments only after version/API review | [SAP S/4HANA APIs](https://api.sap.com/package/S4HANAOPAPI/odata) | Approved customer network design; for private/on-premise access evaluate SAP BTP Integration Suite and SAP Cloud Connector; no public exposure of internal SAP services | Specification only; gateway and tenant required |
| `SAP_ECC` | SAP ECC as a separate legacy product profile; exact ECC release, deployed services and authorizations must be confirmed | SAP customer/API documentation for the specific ECC release; SAP Integration Suite where approved | Customer-approved API/gateway architecture, scoped technical identity and endpoint allowlist | Separately scoped; no ECC adapter claim |
| `ORACLE_FUSION_ERP` | Oracle Fusion Cloud ERP/Financials resources that the customer tenant exposes | [Oracle Fusion Cloud Financials REST API — 26D](https://docs.oracle.com/en/cloud/saas/financials/26d/api.html) | Confirm Fusion Applications versus Spectra resource platform, current API version, resource permissions, tenant identity and the OAuth grant type supported for that platform/resource | Specification only; OAuth client and tenant required |
| `ORACLE_FUSION_SCM` | Oracle Fusion Cloud SCM/Manufacturing resources only when licensed, enabled and authorized in the customer's tenant | [Oracle Fusion Cloud SCM APIs — 26D](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/api.html) | Verify resource-level API/version/permissions, pagination, units and object semantics; evaluate Oracle Integration Cloud if the approved flow needs orchestration | Specification only; SCM resources not validated live |
| `ORACLE_EBS` | Oracle E-Business Suite as a separate legacy product profile; never treated as Fusion REST | [Oracle E-Business Suite Integrated SOA Gateway](https://docs.oracle.com/cd/E26401_01/doc.122/e20923/T291171T509750.htm) | Customer confirms EBS release, deployed and enabled REST/SOAP services, Integration Repository exposure, network path and least-privilege service account | Separately scoped; no EBS adapter claim |

These product IDs are deliberate compatibility boundaries. They are not a statement that a default endpoint, auth grant, resource path, licensing right or API is universally available.

## Read-only MVP capability catalogue

The MVP is for explicitly configured GET-only reads. Candidates are:

- Plant and work-center/resource master data.
- Product, material and bill-of-material data.
- Production orders, operations and confirmations.
- Production quantities, yield, scrap and quality results.
- Inventory balances and material movements.
- Equipment and maintenance work orders.
- Procurement/material availability and costs where specifically authorized.

Each candidate must be enabled independently for the product, tenant, resource, API version and role. It is not enough to pass a root URL health check. No write-back is included: creating/updating orders, purchase orders, inventory, time, maintenance or any other ERP business object is out of scope.

## Evidence needed before a capability can be called supported

For every advertised product/resource combination, retain:

1. Customer-approved product/version and official API resource reference.
2. Sanitized API schema/response contract and explicit field map.
3. Approved tenant host, credential reference (never the value), authorization scope and owner.
4. Positive live read from an authorized non-production tenant.
5. Negative authentication, authorization, tenant-isolation, timeout, pagination, schema and redaction tests.
6. Canonical output validation including unit/currency/timezone and source lineage.
7. Evidence that all ERP requests are read-only.
8. Independent code/security review and exact-SHA CI evidence.

A mocked transport test proves deterministic mapping behavior only. It does not prove provider connectivity, deployed authentication, API availability, licensing, data correctness or production readiness.

## Official references

- SAP S/4HANA Cloud public API discovery: https://api.sap.com/
- SAP S/4HANA on-premise API package: https://api.sap.com/package/S4HANAOPAPI/odata
- SAP Cloud Connector and integration with on-premise systems: https://help.sap.com/docs/integration-suite/sap-integration-suite/using-sap-cloud-connector-with-cloud-integration-adapters?version=CLOUD
- Oracle Fusion Financials 26D APIs: https://docs.oracle.com/en/cloud/saas/financials/26d/api.html
- Oracle Fusion SCM 26D APIs: https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/api.html
- Oracle Fusion OAuth flow and resource-platform distinctions: https://docs.oracle.com/en/cloud/saas/project-management/26d/fapap/configure_oauth.html
- Oracle E-Business Suite Integrated SOA Gateway: https://docs.oracle.com/cd/E26401_01/doc.122/e20923/T291171T509750.htm
