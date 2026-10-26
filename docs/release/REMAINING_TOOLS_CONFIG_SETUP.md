# Remaining target tools — implementation and configuration guide

**Branch:** `feat/t096-rest-readonly-adapter-20261026`  
**State:** T096 generic REST adapter added; automated mocks required on the exact head and no live provider is verified. T098 remains configuration-only and release-gated.  
**Safety rule:** configuration inspection is not proof of a live connection. Do not copy credentials into the Workbench JSON input, source code, CSV files, screenshots, test output, or Git.

## Implemented deterministic target handlers

The existing grouped Industrial Engineering Workbench now offers a structured JSON editor for the target methods below. It uses stable target IDs, the existing authenticated focused-runner boundary and `require_tool_access` before dispatch. No new top-level navigation page was created.

| ID | Method now available | Important limitation |
|---|---|---|
| T006 | Undo/redo/recovery over integrity-checked revision snapshots, including explicit recovery by snapshot ID | The handler returns the updated history; actual cross-session recovery depends on successful authenticated workspace persistence and must be browser-tested. |
| T020 | Content-addressed dataset version record, source/transform metadata, schema/hash, lineage history and stale downstream-run flags | A downstream run is truly blocked only when the calling workflow persists and checks the hash/version. |
| T039 | Existing D1–D8 completeness review plus validated status transitions and transition audit | It does not establish that a root cause is correct or that corrective action is effective. Closure requires effectiveness evidence and approval reference. |
| T060 | Deterministic min-cost supplier-to-customer allocation with capacities, unit costs and shortage variables | Single-period direct routes only; no intermediate network, lead-time optimization, fixed facility costs or multi-period inventory. |
| T074 | Bounded least-squares affine fit with scale, offset, RMSE, MAE, R² and residual table | Empirical correction only, not physical model parameter calibration. Validate units, time alignment and held-out data. |
| T080 | Explicit disruption/recovery scenario comparison for capacity, demand, cost and lead time | Deterministic what-if model; not a calibrated digital twin or probabilistic forecast. |
| T094 | KPI threshold, freshness and duplicate-open-alert evaluation | Inputs must be supplied; durable state and notifications need governed persistence plus an approved notification provider. |
| T097 | API/plugin manifest validation for version, tier, scope, schema and safe entrypoint metadata | Manifests remain inert. It does not deploy a public API or run arbitrary plugin code. |
| T099 | Hashed recovery snapshots, snapshot integrity verification, retention review and non-destructive deletion plans | No data deletion is executed. Restore, deletion and legal retention still require authorization and isolated testing. |

Example JSON inputs are labelled synthetic and provided per target ID. Replace the examples with reviewed user data and preserve units, sources, assumptions and provenance.

## T096 — Integration Management Center configuration

### Supported code-side adapter

The generic adapter currently supports **HTTPS REST with a server-side Bearer token and GET-only health/data-read operations**. It is not a native SAP, Oracle, MQTT, OPC-UA, SQL, WMS, MES or ERP adapter. A provider-specific protocol or authentication method needs its own reviewed adapter using the provider's real documentation and approved staging contract.

Default JSON action `inspect` checks configuration and performs no DNS lookup or outbound request. Only an explicit submitted payload with `"action": "verify_rest_read"` attempts a connection. That action is restricted to an authenticated user with the T096 entitlement and an Owner/Admin role.

Example T096 JSON payload (key names only; never add a real token or endpoint value):

```json
{
  "action": "verify_rest_read",
  "profile": {
    "name": "Approved plant REST API",
    "protocol": "REST",
    "endpoint_env": "SHOIR_CONNECTOR_PLANT_ENDPOINT",
    "credential_env": "SHOIR_CONNECTOR_PLANT_TOKEN"
  },
  "include_sample_data": false
}
```

### Required server-side configuration

Store the following in the deployment's approved secret store or environment; do not enter values in Workbench JSON or commit them:

- `SHOIR_CONNECTOR_PLANT_ENABLED=true` — explicit opt-in; absent/false disables attempts.
- `SHOIR_CONNECTOR_PLANT_ENDPOINT=https://approved-host.example/path-prefix` — the configured service origin/base path.
- `SHOIR_CONNECTOR_PLANT_TOKEN` — short-lived or rotatable least-privilege Bearer token, permitted only for approved health/read access.
- `SHOIR_CONNECTOR_PLANT_HEALTH_PATH=health` — administrator-specified relative health path from the real provider contract.
- `SHOIR_CONNECTOR_PLANT_READ_PATH=sample` — administrator-specified relative read-only JSON resource path from the real provider contract.
- `SHOIR_CONNECTOR_ALLOWED_HOSTS=approved-host.example` — comma-separated exact hostnames or explicit `hostname:port` entries. Wildcards and arbitrary URLs are rejected.
- `SHOIR_CONNECTOR_APPROVED_PRIVATE_CIDRS` — optional exact private industrial-network CIDRs only when an administrator approves them and deployment network policy restricts egress. Leave blank for public-only destinations.
- `SHOIR_CONNECTOR_TIMEOUT_SECONDS=5` — optional request timeout between 0.5 and 10 seconds.

The endpoint host and port must exactly match the allowlist. HTTPS certificate validation remains on. The adapter validates all DNS answers, pins the selected validated address for the connection, blocks loopback/link-local/reserved and known metadata addresses, blocks redirects, sends no requests during import/render/configuration inspection, uses GET only, performs no automatic retry, limits response bodies to 1 MiB, and requires the data-read response to be JSON. If any DNS answer is prohibited, the connection is denied.

### Expected results and operations

- `NOT_CONFIGURED` / `CONFIGURATION_INVALID`: missing or malformed server settings; no claim of connectivity.
- `DISABLED_OR_REVOKED`: the administrator has not enabled the connector; no request is attempted.
- `DESTINATION_BLOCKED`: endpoint host/port is not allowlisted or DNS resolves to an unapproved range.
- `CONNECTION_FAILED_TIMEOUT`, `TLS_VERIFICATION_FAILED`, `CONNECTION_FAILED`: correct DNS, egress, provider health or valid TLS configuration; never disable TLS verification.
- `AUTHENTICATION_REJECTED` / `AUTHORIZATION_REJECTED`: rotate the token or ask the service owner to review the requested read scope.
- `REDIRECT_BLOCKED`, `RATE_LIMITED`, `RESPONSE_TOO_LARGE`, `MALFORMED_RESPONSE`, `DATA_RETRIEVAL_FAILED`: correct the real provider contract or respect the provider's rate-limit guidance; no redirect is followed and no retry is attempted.
- `DATA_RETRIEVAL_VERIFIED`: proves only that the configured health path and read-only JSON path succeeded at the stated timestamp. The response hash, size, shape and keys are reported; sample rows are omitted by default. If an authorized administrator explicitly enables the preview, likely sensitive keys are redacted. This is not proof of vendor-wide functionality, write permission, ongoing availability or engineering data quality.

To disable the connector, set `SHOIR_CONNECTOR_PLANT_ENABLED=false` or remove the enable setting, and revoke/rotate the token in the provider and secret store. There are no pooled long-lived sessions; each submitted check obtains current configuration and performs fresh requests. After rotation/revocation, repeat the negative test and confirm access is denied. Do not paste credentials into screenshots, reports, issues or chat.

## T098 — Enterprise Identity and Audit Center configuration

The handler checks for these server-side configuration keys without displaying their values:

- `SHOIR_OIDC_ISSUER_URL`
- `SHOIR_OIDC_CLIENT_ID`
- `SHOIR_OIDC_CLIENT_SECRET`
- `SHOIR_OIDC_REDIRECT_URI`
- `SHOIR_OIDC_SCOPES`
- `SHOIR_MFA_ENFORCED`
- `SHOIR_AUDIT_LOG_ENABLED`

Issuer and redirect URLs must use HTTPS and include a host. Scopes must include `openid`; MFA and audit flags must be explicitly enabled. These flags are configuration-readiness evidence only. They do not enable OIDC login, enforce an MFA challenge, configure an identity provider or prove audit coverage.

**Still required to activate SSO/MFA:** the accountable owner must choose an OIDC provider, create a staging application/client, register exact callback/logout URLs, store the secret in the deployment's secret manager, agree group/role mapping and MFA policy, and implement/review the authorization-code callback, state/nonce validation, session handling, logout, expiry and revocation. Then run authenticated tests for both allowed and denied roles, MFA challenge and failure, callback mismatch, replay/state failures, logout, expired/revoked sessions, and security audit events. No provider was supplied or activated by this change, and the tool deliberately continues to report `sso_active=false` and `mfa_active=false`.

## Verification and release gates

The unit tests cover method behavior, malformed input, numerical/boundary conditions, content hashes, stale-run detection, transition denials, secret redaction, and all example JSON payloads. CI results are valid only for the exact commit SHA reported by GitHub Actions.

Before marking any of these targets `VERIFIED_WORKING`, complete:
1. Exact-candidate CI: validation, tests, platform tests, engine regression and security/quality.
2. Authenticated Workbench browser walkthrough with each target's minimum tier and an unauthorized tier.
3. Save/reload/re-login, error recovery and two-user workspace isolation; confirm the previous valid state survives a failed action.
4. Independent reference outputs and units for the supply-chain allocator, calibration and disruption scenarios.
5. Direct action/API/Copilot/export entitlement denial where those paths apply.
6. Real external connection and identity-provider tests for T096/T098 in a disposable staging environment.
7. Evidence capture, named reviewer and limitations documented in the acceptance matrix.

**No production app, database, Edge Function, connector, identity provider, account, payment or data record is changed by these deterministic handlers.** Production activation requires a separate reviewed release, parity verification, backup/restore evidence and explicit authorization.
