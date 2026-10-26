# T096 / T098 Acceptance Report — 26 October 2026

**Overall: PARTIAL / BLOCKED. These capabilities are not cleared for enterprise production.**

This report separates source-level implementation, deterministic tests, and live service evidence. A UI status or passing mock test does not establish provider-backed operation.

## T096 — Integration Management Center

**Status: PARTIAL; live endpoint configuration and acceptance BLOCKED.**

### Verified in source / test records
- PR [#195](https://github.com/MSJ1708/shoir-ie/pull/195) was merged at `33f75d27af73d4e33de87b62e44f278ddefbf6fe`.
- The implementation adds a generic HTTPS read-only REST verification path with exact host/port policy, bounded request behavior, sanitized errors and redaction tests.
- Five standard CI workflows were reported successful on PR head `05cac4c8cc40f4da0d884b5b26a0a008e387a4de`; its validation workflow's `live-deployment-smoke` job was skipped.
- Existing T096 UI has a connector registry and config validation. Endpoint registration/URL validation is not proof that the endpoint accepted authentication or returned the needed business resource.
- New isolated PR [#198](https://github.com/MSJ1708/shoir-ie/pull/198) contains the six-product ERP boundary, an explicit field-mapping/read-only adapter foundation, a non-secret product selector within the existing T096 Integration Map, documentation and automated tests. For its exact head `f55e30415ea06153bf57b92a6759e93fdf8934c2`, Tests, Security/Quality, Engine Regression, Platform Tests and Validation jobs report success. The validation workflow's `live-deployment-smoke` job is skipped. The PR is draft and has no independent review submission.

### Not established
- No live non-production HTTPS endpoint/resource read was verified by this audit.
- No production-grade live SAP or Oracle transport, provider-specific OAuth/token lifecycle, durable incremental sync, persistent workspace import, or provider live contract acceptance is implemented in PR #198.
- No live resource-level proof is available for plant, work center, production order, material, inventory, maintenance, procurement or cost APIs.
- No independent review has approved the merged generic connector or draft ERP branch, according to currently returned GitHub review records.

### Required acceptance
1. Obtain a customer-approved non-production endpoint and exact permitted resource.
2. Store the least-privilege credential in authorized server-side secret storage; no token in Streamlit state, browser input, source code, logs or artifacts.
3. Run positive and negative endpoint/credential/permission/timeout/redirect/rate-limit/response-schema tests against the real endpoint with redacted evidence.
4. Prove the live returned records map to canonical fields with explicit units/currency/timezone and lineage, then verify saved output after reload/re-login and actual export.
5. For SAP/Oracle, finish provider-specific authentication/transport, exact resource contracts, UI operation states, durable synchronization, revoke/pause flow and product-specific live non-production acceptance. Keep each product/resource capability disabled/unverified until its own acceptance passes.

## T098 — Enterprise Identity and Audit Center

**Status: BLOCKED for provider-backed SSO/MFA and durable security-audit acceptance.**

Source-level identity/session safeguards and logging-related components exist, but this audit found no evidence of a configured external identity provider tenant and no provider-backed OIDC login/callback test. A UI setting, application role label, or ordinary local audit row is not evidence of SSO, provider-enforced MFA, or tamper-resistant durable security audit.

### Required acceptance
1. Select the actual identity provider and create an approved staging tenant/client.
2. Verify OIDC discovery, issuer/audience/redirect URI/state/nonce checks, authorization-code exchange, token validation and logout/session expiry.
3. Verify identity-to-account mapping and server-side workspace/tier/role authorization; reject role claims sourced from user-editable metadata.
4. Enable provider-enforced MFA and demonstrate allowed and denied login paths in the provider test tenant.
5. Record an approved security event, retrieve it through authorized audit access, verify timestamps/actor/action/outcome, retention and access restrictions, and confirm secrets and unnecessary personal data are not logged.
6. Test revoked users/sessions and changed entitlements; direct API paths must deny access even if the UI has stale state.
7. Obtain independent security review and evidence for every step.

## External dependencies

| Item | Owner | Status |
|---|---|---|
| Approved live T096 non-production endpoint + least-privilege credential | Integration owner / customer IT | BLOCKED |
| SAP tenant/resource contracts per product profile | Customer SAP administrator | BLOCKED |
| Oracle Fusion/EBS tenant/resource contracts per product profile | Customer Oracle administrator | BLOCKED |
| Secret-manager implementation and provider-specific auth/transport | Software maintainer / security reviewer | NOT IMPLEMENTED / BLOCKED |
| OIDC tenant and client credentials | Identity provider administrator | BLOCKED |
| Provider-enforced MFA policy | Identity/security administrator | BLOCKED |
| Durable audit acceptance and retention | Security owner / database owner | NOT VERIFIED |
| Independent code/security review | Authorized reviewer | NOT RECORDED |

## Release consequence

T096 and T098 remain external-configuration-required. Do not claim enterprise SSO/MFA, durable audit, generic REST live acceptance or native SAP/Oracle live connectivity until the respective acceptance case passes on an exact reviewed staging candidate. These blocked capabilities need not halt independent documentation and deterministic adapter work, but they do block the relevant commercial/enterprise claims.
