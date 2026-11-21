# Shoir-IE T096 Integration Management Centre Acceptance

Assessment date: 2026-11-21. Status: **provider-specific SAP S/4HANA and Oracle Fusion read transports are implemented; real tenant configuration and hosted acceptance remain open**.

## Verified repository implementation

The generic HTTPS REST path is now more than a metadata stub:

- `shoir_remaining_tool_engines.py` exposes `integration_configuration_status`. Inspection is the default and performs no DNS or HTTP operation. A live read requires the explicit `verify_rest_read` action, an authenticated entitled Enterprise administrator and a server-configured profile.
- `shoir_rest_connector.py` supports HTTPS + Bearer token only. It resolves credentials from server environment/Streamlit secrets, requires an exact hostname/port allowlist, pins a validated DNS address for the socket connection, verifies TLS against the original hostname, rejects redirects, bounds response bytes and timeouts, and redacts sensitive fields from optional previews.
- `tests/test_shoir_rest_connector.py` covers disabled/missing configuration, endpoint allowlisting, metadata and private-network blocking, authorization/tier checks, response limits, redirect handling, malformed responses, secret redaction and no-network configuration inspection. These tests use controlled mocks; they are not proof of a real provider connection.
- `shoir_erp_connectors.py` defines SAP S/4HANA Public/Private, SAP ECC, Oracle Fusion ERP, Oracle Fusion SCM and Oracle EBS product/resource contracts, canonical mapping, GET-only transport protocol and server-side authorization contract. It intentionally has no provider HTTP implementation or provider token handling.

## What is not verified

No SAP, Oracle or other customer ERP sandbox endpoint, provider tenant, least-privilege credential, API scope or network route has been configured for a live test. The generic adapter is not a vendor-specific SAP/Oracle adapter. The provider-specific transport implementation is now present in the candidate branch; its supported cloud-product scope and the remaining hosted acceptance requirements are recorded below.

The 22-row `docs/integrations/ERP_ACCEPTANCE_MATRIX.csv` remains NOT RUN for live product acceptance. No live connection, data import, ongoing sync or external ERP persistence is claimed.

## Required completion sequence

1. Select one supported product and exact read-only API resource with an authorized customer/provider owner.
2. Provision the staging-only service identity and secret in the approved secret store; never place credentials in a browser, workbook, source file or chat.
3. Add the exact endpoint hostname/port to the allowlist and, only where required, the precise approved private CIDR. Reject broad wildcard/network access.
4. Configure the implemented product-specific token flow: SAP S/4HANA Cloud Public/Private OAuth client credentials; Oracle Fusion Applications JWT User Assertion plus signed client assertion. Verify the exact tenant resource scope, certificate, identity claims and credential references. Do not reuse generic client-credentials settings for Oracle Fusion Applications.
5. Run live staging health/read tests with synthetic or approved non-personal data; verify 401/403, token expiry/revocation, rate limits, schema drift, pagination, duplicate/conflicting IDs, field/unit/currency mapping and lineage hashes.
6. Prove that no write method exists, no network call occurs at import/configuration-inspection time, and secrets or personal data cannot appear in logs/previews.
7. Capture exact endpoint profile (without secret values), source SHA, CI run, redacted output, provider/API version and customer owner sign-off. Only then mark that specific connector verified.

Mocks and product profile metadata do not count as live SAP/Oracle acceptance. T096 remains **EXTERNAL_CONFIGURATION_REQUIRED** until an actual provider-backed test is completed.

## Workbench route added — 2026-11-08

The existing Workbench now exposes a focused T096 form. It provides configuration inspection without outbound network access and a separate confirmed live-read action. The latter is guarded by the server-resolved application environment and refuses to run unless it is exactly `staging`; credentials remain referenced only by server-side environment/Streamlit secret names. A new AppTest exercises the inspection route, and connector unit coverage asserts that production is denied before the adapter can make a network request. This UI/test addition does not replace provider-specific SAP/Oracle implementation or a live provider acceptance run.



## Repository implementation update — 2026-11-20

The candidate includes `shoir_erp_provider_transport.py` with two distinct, server-side provider authentication paths:

- **SAP S/4HANA Cloud Public/Private:** OAuth 2.0 client-credentials token exchange with bounded token caching and OData V2/V4 pagination (`value` / `d.results`, OData next links).
- **Oracle Fusion Applications ERP/SCM:** JWT User Assertion grant with separate signed RS256 user and client assertions, RSA key-size validation, certificate `kid`, explicit identity-domain application issuer/client-subject/user-subject values, and token-cache invalidation when the signing key or identity settings rotate. Standard Fusion Applications REST resources must not use generic Client Credentials; Oracle documents that grant only for Spectra services.

Both paths use exact HTTPS host allowlisting, DNS/IP pinning, TLS verification, redirects denied, bounded timeouts/response sizes/pages, sanitized failures and GET-only resource reads. SAP ECC and Oracle E-Business Suite remain explicitly unsupported until their distinct legacy authentication/API adapters are implemented and reviewed.

A server-side credential resolver is injected by the deployment. It receives only the opaque `credential_ref` and returns provider-specific values from the approved secret manager. SAP credentials contain the exact token URL, OAuth client ID, client secret and approved read scope. Oracle credentials contain the token URL, identity-domain root URL, OAuth client ID, identity-domain application-name issuer/client-assertion subject, Oracle read-only username, certificate alias (`kid`), server-side RSA private-key PEM and approved Fusion resource scope. No private key, client secret or access token belongs in a Workbench payload, repository file, GitHub Actions secret set or browser. The common connector adapter still performs authenticated actor, workspace and resource authorization before any transport call.

Automated transport-contract tests cover token exchange/cache, SAP OData and Oracle Fusion pagination, redirect rejection and cross-origin pagination rejection. These are synthetic HTTP-contract tests; they do **not** prove a live provider endpoint, real account scopes, tenant-specific schemas, pagination variants or provider rate-limit behavior. The existing T096 Workbench form is wired to an explicitly confirmed, staging-only provider read action. It accepts only a server-configured connection ID and logical resource key; it does not create or manage provider credentials in the browser. Connection metadata, resource mappings, host allowlists and opaque credential references are loaded from server-side configuration, while provider secrets are resolved by the injected server-side credential resolver. The currently implemented provider scope is SAP S/4HANA Cloud Public/Private and Oracle Fusion ERP/SCM. SAP ECC and Oracle EBS remain unsupported and fail closed until their own authentication/API adapters are designed and reviewed. Live provider acceptance remains blocked on an owner-selected sandbox, approved host and credential reference, secret-manager configuration, real provider round-trip, durable import/lineage decisions and independent security review. Keep T096 `EXTERNAL_CONFIGURATION_REQUIRED` until that evidence exists.


## Workbench integration update — 2026-11-20

The provider-aware SAP/Oracle read path is now wired into the existing T096 Workbench form. Operators select a server-configured connection reference and resource key; the browser does not submit a base URL, tenant credential, client secret, OAuth token or host allowlist. The action requires an explicit confirmation, an authenticated Enterprise workspace owner/admin, matching active workspace scope, an enabled read-only server connection, a server-side resource mapping, an approved HTTPS host and the staging application environment.

Server-side settings consumed by the provider action:

- `SHOIR_ERP_CONNECTIONS_JSON`: connection IDs mapped to product/workspace/tenant/base URL/opaque credential reference and approved resource bindings.
- `SHOIR_ERP_CREDENTIALS_JSON`: opaque credential-reference map to provider-specific secret records. SAP uses token URL, client ID, client secret and read scope. Oracle Fusion uses token URL, identity-domain URL, OAuth client ID, `assertion_issuer`, `client_assertion_subject`, `user_subject`, `signing_key_id`, `signing_private_key_pem` and the exact approved resource scope.
- `SHOIR_ERP_ALLOWED_HOSTS`: semicolon- or comma-separated exact host[:port] allowlist.
- `SHOIR_ERP_APPROVED_PRIVATE_CIDRS`: optional narrow private CIDRs, subject to the existing network-policy checks.
- `SHOIR_ERP_TIMEOUT_SECONDS`: bounded 0.5–10 second request timeout.

The Workbench displays only read status, row/page counts, mapping version and a SHA-256 digest. It does not persist or display fetched provider records. Tests use synthetic server-side settings and a mocked provider result to prove authorization, workspace scoping, secret redaction and metadata-only output. This is not a live SAP/Oracle tenant connection or a durable import/sync feature; real provider configuration and acceptance remain required.
