# Customer IT Setup Guide — SAP / Oracle Read-Only Pilot

This guide lists the information required to prepare a non-production ERP connection. It is not evidence that Shoir-IE is connected, nor does it authorize access to any customer system.

## 1. Select the exact product

The customer IT owner must provide:
- Product and edition from the supported-products matrix.
- Application release/version and relevant enabled modules.
- The approved tenant alias and environment (sandbox/non-production only for the pilot).
- The business data/resource objectives and intended read frequency.
- An authorized technical owner and a security/privacy reviewer.

Do not provide passwords, API tokens, private keys or client secrets in email, chat, a GitHub issue, a workbook or this guide.

## 2. Agree the smallest read scope

Choose only the first one or two resource workflows needed for the pilot. Examples include work-center master data, material master data, production orders or inventory balances. For each selected resource, agree an official API reference, API/version, field list, primary-key path, collection path, permitted role/scope, data classification and acceptance fixture.

Do not enable the full catalogue by default. Do not include personal workforce records unless a separate lawful-purpose, minimization, retention and access review has approved them. Aggregated measures are preferred.

## 3. SAP S/4HANA Cloud Public Edition

1. An SAP administrator identifies each released API in SAP Business Accelerator Hub and confirms that it is available in the customer's edition/release.
2. The administrator configures the required communication system/arrangement and only the authorizations required by the chosen API.
3. The SAP and Shoir-IE security owners agree the supported authentication method for the specific API and deployment. Never assume one authentication method applies to all APIs.
4. A customer IT network owner approves the outbound destination, TLS behavior, host allowlist and egress policy.
5. Export a sanitized schema/response example with realistic identifiers and personal data removed.
6. Test in the non-production tenant only after connection setup is reviewed.

**Current Shoir-IE adapter:** standard Fusion Applications REST resources are read using the JWT User Assertion grant plus a signed JWT client assertion; generic Client Credentials is only supported by Oracle for Spectra services. Shoir-IE now implements both RS256 assertions. The tenant administrator must create and activate a trusted confidential app with JWT assertion enabled, import the matching public certificate (alias must equal the JWT `kid`), authorize the exact resource scope, and configure the correct identity-domain application-name issuer/subject claims, OAuth client ID, user subject, identity-domain URL and token endpoint in server-side staging secrets. The private key must stay server-side. Do not attempt a live read until a non-production Oracle tenant and read-only resource are approved and the credential/certificate/claim values are verified.

Reference: https://api.sap.com/

## 4. SAP S/4HANA Private Edition / on-premise / ECC

1. Confirm exact product, release, services and customer-supported API/gateway.
2. Prohibit direct public exposure of internal application servers.
3. Have customer architecture/security owners choose an approved route, for example SAP BTP Integration Suite with SAP Cloud Connector where appropriate and supported.
4. Scope virtual hosts/resources to the exact required paths; do not grant broad internal network access.
5. Confirm DNS, certificates, outbound connectivity, monitoring and escalation ownership.
6. Validate the adapter against a customer-managed non-production endpoint before any production use.

References:
- https://api.sap.com/package/S4HANAOPAPI/odata
- https://help.sap.com/docs/integration-suite/sap-integration-suite/using-sap-cloud-connector-with-cloud-integration-adapters?version=CLOUD

## 5. Oracle Fusion Cloud ERP / SCM

1. Confirm the exact Fusion product family, release, API resource version and whether the target is a Fusion Applications REST API or a Spectra service.
2. Review the official resource documentation, API scopes and permissions for that resource.
3. For normal Fusion Applications REST resources, select the JWT User Assertion grant (two-legged, on behalf of a user) and use a separate signed client assertion. Do not select Client Credentials for standard Fusion Applications resources; Oracle documents that grant only for Spectra services.
4. Register a Confidential Application in the Fusion Applications identity domain. Enable the JWT assertion grant, mark the client Trusted, import the public X.509 certificate that corresponds to the Shoir-IE server-side RSA private key, and set the certificate alias to exactly the `kid` used in the JWT header.
5. Record the generated OAuth Client ID, exact identity-domain root URL, token URL (`/oauth2/v1/token`), exact application-name values used as `assertion_issuer` and `client_assertion_subject`, least-privilege Oracle username for `user_subject`, and the exact authorized resource scope. The OAuth Client ID and JWT application-name claim values are distinct settings; confirm the values in the identity-domain UI and do not infer them.
6. Store the private key only in the dedicated staging Streamlit server-side secret store or approved vault. Never put it in Git, browser input, GitHub Actions, a workbook or chat. The key must be RSA 2048-bit or stronger; rotate the certificate and key together and update the registered certificate alias/`kid`.
7. Use the exact Oracle Fusion tenant REST base URL and confirm the API resource/version, scopes and pagination contract with the tenant owner.
8. Use the tenant's official REST base URL. Do not copy an example URL from a different customer's tenant.
9. Provide a sanitized example response and pagination contract.
10. Test only with a non-production account/tenant.

References:
- https://docs.oracle.com/en/cloud/saas/financials/26d/api.html
- https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26d/api.html
- https://docs.oracle.com/en/cloud/saas/project-management/26d/fapap/configure_oauth.html

## 6. Oracle E-Business Suite

Oracle EBS requires its own product/release review. Confirm that the required service has been enabled through the appropriate EBS interface and review the service contract, authorizations, network controls and release-specific documentation. Do not use the Fusion Cloud adapter or OAuth assumptions by default.

Reference: https://docs.oracle.com/cd/E26401_01/doc.122/e20923/T291171T509750.htm

## 7. Secure handoff to the Shoir-IE owner

Share only:
- Product and release metadata.
- Tenant alias and approved hostname (no account ID or secret).
- Official API reference and approved resource names.
- Non-personal, sanitized example payload/schema.
- Secret-manager reference name, not its value.
- Expected units, currency, timezone, business calendar and watermark field where available.
- Named IT/security/data owners and an agreed test window.

The credential itself must be entered by an authorized administrator into the approved server-side secret store, not into the application UI or repository.

## 8. Acceptance before a capability is enabled

A designated operator must run a live read against the non-production tenant. Record the exact application SHA, product/API resource/version, test time, result counts and redacted evidence. Test wrong credentials, insufficient privilege, cross-workspace access denial, unsafe host rejection, timeout, rate limits, pagination, duplicates, unexpected schema, revocation and personal-data redaction. Verify that the connector has no write operation and that mapped output retains lineage and explicit units.

A successful URL/health check, unit test or mocked response is insufficient. Until the live resource read passes, the status remains Configuration required or Test pending.
