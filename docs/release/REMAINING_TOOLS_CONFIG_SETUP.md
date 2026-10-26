# Remaining target tools — implementation and configuration guide

**Branch:** \`feat/shoir-remaining-tools-config-20261026\`  
**State:** implementation tranche; exact-head CI and authenticated staging acceptance still required.  
**Safety rule:** configuration inspection is not proof of a live connection. Do not copy credentials into the Workbench JSON input, source code, CSV files, screenshots, test output, or Git.

## Implemented deterministic target handlers

The existing grouped Industrial Engineering Workbench now offers a structured JSON editor for the target methods below. It uses stable target IDs, the existing authenticated focused-runner boundary and \`require_tool_access\` before dispatch. No new top-level navigation page was created.

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

The handler checks configuration presence and basic endpoint syntax without returning secret values or making outbound network calls. This protects against mistaking a profile or an entered URL for an authorized connection.

Use the approved deployment secret store (for example, Streamlit Community Cloud secrets or process environment) to define one endpoint key and one credential key per approved connector. Example **key names only**:

- \`SHOIR_CONNECTOR_PLANT_ENDPOINT\`
- \`SHOIR_CONNECTOR_PLANT_TOKEN\`
- \`SHOIR_CONNECTOR_MES_ENDPOINT\`
- \`SHOIR_CONNECTOR_MES_CREDENTIAL\`

For a REST connector, the endpoint should use HTTPS. Other protocols have their own allowlisted schemes. A profile refers to these names; it must not include the secret value. Do not use an unapproved endpoint or broaden network access just to make a health test pass.

**Still required to mark a connector connected:** select the actual source system, obtain owner-approved endpoint and least-privilege credentials, confirm contract/schema and data scope, run a controlled staging connection test, verify read/write permissions independently, confirm redacted health/error logs and freshness, and record a successful test timestamp. The current handler intentionally reports readiness for an authorized test rather than \`CONNECTED\`.

## T098 — Enterprise Identity and Audit Center configuration

The handler checks for these server-side configuration keys without displaying their values:

- \`SHOIR_OIDC_ISSUER_URL\`
- \`SHOIR_OIDC_CLIENT_ID\`
- \`SHOIR_OIDC_CLIENT_SECRET\`
- \`SHOIR_OIDC_REDIRECT_URI\`
- \`SHOIR_OIDC_SCOPES\`
- \`SHOIR_MFA_ENFORCED\`
- \`SHOIR_AUDIT_LOG_ENABLED\`

Issuer and redirect URLs must use HTTPS and include a host. Scopes must include \`openid\`; MFA and audit flags must be explicitly enabled. These flags are configuration-readiness evidence only. They do not enable OIDC login, enforce an MFA challenge, configure an identity provider or prove audit coverage.

**Still required to activate SSO/MFA:** the accountable owner must choose an OIDC provider, create a staging application/client, register exact callback/logout URLs, store the secret in the deployment's secret manager, agree group/role mapping and MFA policy, and implement/review the authorization-code callback, state/nonce validation, session handling, logout, expiry and revocation. Then run authenticated tests for both allowed and denied roles, MFA challenge and failure, callback mismatch, replay/state failures, logout, expired/revoked sessions, and security audit events. No provider was supplied or activated by this change, and the tool deliberately continues to report \`sso_active=false\` and \`mfa_active=false\`.

## Verification and release gates

The unit tests cover method behavior, malformed input, numerical/boundary conditions, content hashes, stale-run detection, transition denials, secret redaction, and all example JSON payloads. CI results are valid only for the exact commit SHA reported by GitHub Actions.

Before marking any of these targets \`VERIFIED_WORKING\`, complete:
1. Exact-candidate CI: validation, tests, platform tests, engine regression and security/quality.
2. Authenticated Workbench browser walkthrough with each target's minimum tier and an unauthorized tier.
3. Save/reload/re-login, error recovery and two-user workspace isolation; confirm the previous valid state survives a failed action.
4. Independent reference outputs and units for the supply-chain allocator, calibration and disruption scenarios.
5. Direct action/API/Copilot/export entitlement denial where those paths apply.
6. Real external connection and identity-provider tests for T096/T098 in a disposable staging environment.
7. Evidence capture, named reviewer and limitations documented in the acceptance matrix.

**No production app, database, Edge Function, connector, identity provider, account, payment or data record is changed by these deterministic handlers.** Production activation requires a separate reviewed release, parity verification, backup/restore evidence and explicit authorization.
