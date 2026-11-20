# Shoir-IE T096 Integration Management Centre Acceptance

Assessment date: 2026-11-08. Status: **generic read-only REST adapter implemented; provider configuration and hosted acceptance remain open**.

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
4. For SAP/Oracle, implement the provider-specific OAuth/token and pagination layer behind the GET-only contract; retain TLS verification, DNS/IP pinning, redirect rejection, bounded timeouts/bytes/pages/rates and sanitized diagnostics.
5. Run live staging health/read tests with synthetic or approved non-personal data; verify 401/403, token expiry/revocation, rate limits, schema drift, pagination, duplicate/conflicting IDs, field/unit/currency mapping and lineage hashes.
6. Prove that no write method exists, no network call occurs at import/configuration-inspection time, and secrets or personal data cannot appear in logs/previews.
7. Capture exact endpoint profile (without secret values), source SHA, CI run, redacted output, provider/API version and customer owner sign-off. Only then mark that specific connector verified.

Mocks and product profile metadata do not count as live SAP/Oracle acceptance. T096 remains **EXTERNAL_CONFIGURATION_REQUIRED** until an actual provider-backed test is completed.

## Workbench route added — 2026-11-08

The existing Workbench now exposes a focused T096 form. It provides configuration inspection without outbound network access and a separate confirmed live-read action. The latter is guarded by the server-resolved application environment and refuses to run unless it is exactly `staging`; credentials remain referenced only by server-side environment/Streamlit secret names. A new AppTest exercises the inspection route, and connector unit coverage asserts that production is denied before the adapter can make a network request. This UI/test addition does not replace provider-specific SAP/Oracle implementation or a live provider acceptance run.



## Repository implementation update — 2026-11-20

The candidate now includes `shoir_erp_provider_transport.py` with a server-side OAuth 2.0 client-credentials token resolver, bounded token caching, TLS-verified HTTPS requests pinned to a validated DNS address, exact host allowlisting, redirect rejection, bounded JSON responses and sanitized transport failures. It provides distinct pagination handling for SAP S/4HANA Cloud OData V2/V4 (`value` / `d.results`, OData next links) and Oracle Fusion REST (`items`, `hasMore`, next links or bounded offset pagination). The first transport scope is SAP S/4HANA Cloud Public/Private and Oracle Fusion ERP/SCM. SAP ECC and Oracle EBS remain explicitly unsupported until their legacy authentication/API profiles receive separate adapters; they fail closed rather than silently using the cloud flow.

A server-side credential resolver is injected by the deployment. It receives only the opaque `credential_ref` and must return the provider's token URL, client ID, client secret and scope from the approved secret manager. No client secret or access token belongs in a Workbench payload, repository file or browser. The common connector adapter still performs authenticated actor, workspace and resource authorization before any transport call.

Automated transport-contract tests cover token exchange/cache, SAP OData and Oracle Fusion pagination, redirect rejection and cross-origin pagination rejection. These are synthetic HTTP-contract tests; they do **not** prove a live provider endpoint, real account scopes, tenant-specific schemas, pagination variants or provider rate-limit behavior. The existing Workbench T096 form has not yet been wired to create/manage these provider credentials and run the provider-aware resource flow. Live provider acceptance remains blocked on an owner-selected sandbox, approved host and credential reference, secret-manager configuration, end-to-end UI integration and independent security review. Keep T096 `EXTERNAL_CONFIGURATION_REQUIRED` until that evidence exists.
