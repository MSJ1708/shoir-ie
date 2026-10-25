# Shoir-IE Security Threat Model

**Review date:** 2026-10-25  
**Scope:** repository-level source review of the Shoir-IE Streamlit application, Python engines, persistence Edge Function, workspace persistence, imports/exports and CI workflows.  
**Status:** In progress — not a penetration test, compliance opinion or security certification.

## Protected assets

| Asset | Potential impact if compromised |
|---|---|
| Account passwords, session bearer tokens and renewal-only sessions | Account takeover, unauthorized workspace access or subscription-action misuse |
| Workspace state, industrial datasets, run inputs/results, scenarios, decisions and exports | Cross-customer disclosure, tampering, loss of engineering evidence or misleading decisions |
| Subscription decisions and payment-proof files | Unauthorized entitlement changes, financial/identity-data exposure |
| Connector credentials, database keys and deployment secrets | Unauthorized system/data access, external service misuse |
| Engineering methods, calculations and provenance | Incorrect industrial decisions, unsafe recommendations or fabricated ROI claims |
| Logs, diagnostics, support bundles and CI artifacts | Accidental exposure of credentials, personal data or customer information |
| Production deployment and administrator identity | Service disruption, privilege escalation or irreversible customer/account changes |

## Trust boundaries and representative attackers

1. **Unauthenticated browser to Streamlit public shell.** An anonymous visitor can submit malformed input or abuse public authentication and discovery surfaces.
2. **Authenticated browser/session to protected tool execution.** A low-tier or malicious user may modify IDs, aliases, URLs, form fields or session state to reach a restricted action.
3. **Streamlit to persistence Edge Function to Supabase database/storage.** The browser-visible publishable key is not an authorization secret; the Edge Function service-role credential must remain private. Requests, user identifiers and saved state are untrusted.
4. **Imported workbook/CSV/JSON/text to parsing, calculations, rendering and Copilot.** Files may contain malformed structures, huge inputs, spreadsheet formulas, unsafe text or prompt-injection content.
5. **Connector configuration to outbound integration.** A malicious or mistaken endpoint may target internal/private services, leak credentials or consume unbounded resources.
6. **Repository changes/dependencies to CI and deployment.** A vulnerable dependency, unreviewed branch, insufficient required checks or secret in logs can compromise release integrity.

## Controls observed or added in the reviewed branch

| Threat | Existing or added mitigation | Evidence limitation / residual risk |
|---|---|---|
| SQL injection | Reviewed Supabase access uses query-builder filters; reviewed Python SQL examples use bound values for user data. Dynamic identifiers still require strict allowlists. | Not a complete line-by-line audit of every query, stored procedure or migration; database-backed injection tests were not executed here. |
| Cross-user/workspace access | Persistence operations require a valid server-side session and scope workspace reads/writes by normalized username; Edge Function operations use parameterized Supabase filters. | Two-account staging tests and RLS runtime tests have not been run; do not infer tenant-isolation proof from the source pattern. |
| Forged/expired session or scope escalation | Session tokens are stored hashed server-side; lookup checks expiry, account activity, username binding, scope, subscription status and admin role. | Staging revoke/expiry/renewal-only tests and end-to-end permission tests remain open. |
| Request-body resource exhaustion | Added bounded JSON stream parsing: maximum request body 12 MiB; request byte count is enforced independently of untrusted Content-Length; malformed UTF-8/JSON and non-object payloads are rejected. | Limits must be checked against representative workspace payloads in staging; large uploads may be safely rejected. |
| Workspace-state corruption/overwrite | Added object/JSON validation and an 8 MiB serialized workspace-state limit before database upsert. Invalid content is rejected before the existing saved state is replaced. | A live failed-save/recovery walkthrough is still required. |
| Error-message information disclosure | Added a public error mapping; known client/auth errors are mapped to controlled statuses, while unknown database/storage/provider errors return a generic message. | Application/edge logs must separately be checked for tokens and sensitive payloads; that log review is not complete. |
| Payment-proof upload attacks | Existing code limits proofs to 512 KiB, permits PNG/JPEG/PDF only, and checks file signatures before storage; private-bucket guard and signed short-lived URL flow exist. | Storage bucket configuration, anti-malware/sandbox expectations and deployed-policy parity need staging verification. |
| Unsafe spreadsheet/imported content | Existing import/export validation and the main matrix include relevant tests and limitations; imported text should be treated as data. | Formula injection, malformed archive exhaustion, HTML rendering, prompt injection and full workbook round-trip have not all been independently exercised on the final candidate. |
| SSRF / unsafe connector endpoints | Existing Supabase Edge configuration enforces HTTPS, exact declared project host and expected path for staging/production endpoint overrides. | Every connector URL-fetch/network code path and private/reserved address handling is not fully audited or tested. |
| Dependency compromise | Security workflow installs the project dependency set and runs pip-audit; this workflow was extended to run for the stacked integration PR. | Latest exact-head result must be checked; a scanner result alone does not establish security. |
| Secrets exposure | Browser code must use only publishable/anonymous credentials; service-role key is read by the Edge Function from server environment. Existing workflow scans for obvious credential patterns in three entry files. | The pattern scan is narrow and may miss secrets elsewhere, including logs, artifacts or history. Do not treat it as a complete secrets audit. |
| Authorization drift between modules and tiers | Canonical T001–T100 registry, fail-closed tier_allows_tool/require_tool_access, matrix/registry comparison and a new six-package truth-table regression test. | Legacy renderers, API/plugin entry points, Copilot actions and export paths are not proven to invoke the stable-ID gate universally. |
| Release integrity | Validation, security/quality, platform, engine-regression and Edge Function checks are configured to run for the integration PR. | The repository's main branch protection was observed disabled; branch protection still needs to be configured and verified by a repository administrator. |

## Highest-priority release blockers

1. **Branch protection:** main was observed with protection disabled and no required status checks. Enable required review/checks through repository settings and verify the resulting state.
2. **Tenant authorization:** run cross-user/cross-workspace reads and writes, direct-action tier bypass tests, session-expiry/revocation tests, and RLS checks with disposable staging accounts.
3. **Exact-head tests:** confirm all required workflows pass on the same exact candidate SHA; investigate every failure rather than suppressing it.
4. **Authenticated E2E and deployment parity:** execute the documented import-to-decision-to-export workflow plus critical module walkthroughs in staging; verify that the hosted environment runs the reviewed revision.
5. **Broader security assessment:** complete the remaining source audit for dynamic SQL identifiers, CSV/XLSX formula injection, archive/resource exhaustion, unsafe rendering, connector SSRF, API/Copilot/plugin paths, sensitive logs and dependencies.

## Safe testing boundaries

- Use isolated staging and disposable test accounts with synthetic data.
- Never use the protected production administrator for acceptance tests.
- Do not mutate production subscriptions, customer records, workspaces, schema or Edge Function deployment during this review.
- Redact test artifacts and do not commit real tokens, passwords, keys, payment proofs or customer data.

## Decision

**NO-GO for paid commercial release based on the evidence available in this source review.** This report does not assert zero vulnerabilities, complete security, full Saudi-law compliance or production readiness. Release status can change only after the listed automated and authenticated gates pass on the exact candidate revision and residual findings are dispositioned.
