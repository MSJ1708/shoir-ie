# Shoir-IE Release Evidence — 26 October 2026

**Decision: NO-GO. Keep BETA visible; do not enable paid general availability.**

This is a dated evidence snapshot, not legal approval, a security certification, or release-owner authorization. It distinguishes source and CI evidence from authenticated staging and external approvals.

## 1. Executive outcome

Current main SHA: 267be8889c310d90141c047d8aadd42c942423fb.

Completed this session:
- Refreshed repository, PR, workflow, migration, schema and deployed-function state.
- Deployed repository-matched index.ts plus security.ts to the staging Supabase project only. Staging shoir-persistence is active at version 9; the returned bundle was re-read and verified to include both files, bounded request handling/safe error mapping, and the refund-policy v2 constant.
- Verified the master-admin invariant in both databases with aggregate-only queries. Each has exactly one active Enterprise Admin with tier Enterprise Plus Tier ($399) and expiry 2099-01-01T00:00:00Z. No account identifier was queried or emitted and the account was not used for testing.
- Created staging-only draft PR #196 to make referral summary an optional extension during startup, add regression assertions, and use the exact staging banner required by the release plan. It remains draft and its current validation checks were still running at last observation.
- Created no production application deployment, migration, Edge Function mutation, payment, subscription mutation, master-admin change, branch-protection change, or BETA-label removal.

The release is NO-GO because the authenticated staging gate was skipped on the latest recorded staging branch candidate, branch protection could not be verified, production schema/function parity is incomplete, T096 and T098 need provider-backed evidence, the 100-tool matrix has zero verified-working entries, and required legal/commercial/operations approvals remain open.

## 2. Main CI evidence

| Check | SHA | Result | Evidence |
|---|---|---|---|
| Shoir-IE validation | 267be8889c310d90141c047d8aadd42c942423fb | PASS | https://github.com/MSJ1708/shoir-ie/actions/runs/40291784799 |
| Engine Regression | same SHA | PASS | https://github.com/MSJ1708/shoir-ie/actions/runs/40291784823 |
| Security and quality gates | same SHA | PASS | https://github.com/MSJ1708/shoir-ie/actions/runs/40291784836 |
| Hosted anonymous entry-screen smoke | same SHA; not exact deployment-revision proof | PASS in run 40291784799; later same-SHA run skipped hosted job | https://github.com/MSJ1708/shoir-ie/actions/runs/40291784799 and https://github.com/MSJ1708/shoir-ie/actions/runs/40295759250 |

An earlier candidate's hosted desktop/mobile smoke failed because Streamlit showed the sleeping screen rather than the app frame: https://github.com/MSJ1708/shoir-ie/actions/runs/40290645125, SHA 215805d00599ccd8e17bdccd71bdbf38a2b422ab. The later successful public shell smoke does not establish authenticated app correctness or prove that Streamlit runs the reviewed commit.

## 3. Branch protection and open PR disposition

The current main branch-protection API call returned 403 Resource not accessible by integration. The accessible repository rulesets list returned an empty array. Branch protection therefore remains NOT VERIFIED; do not infer the actual saved policy from green checks.

| PR | Latest disposition | Next action |
|---|---|---|
| #196 | Open, draft, staging base, head 7c0219385fe33bcb68b963b23dfac9a9c0fb886c | Validation runs 40303682913 and 40303680055 were still in progress; hosted smoke job skipped. Finish CI and obtain independent review before staging merge/deploy. https://github.com/MSJ1708/shoir-ie/pull/196 |
| #195 | Open, draft, main base, head 26d5e4f2a6569223976eff4fe43db83b0967d2e2 | Exact-head validation 40298783424, tests 40298783902, platform tests 40298783416, engine regression 40298783672 and security/quality 40298783645 passed. No independent review or live REST connector test. https://github.com/MSJ1708/shoir-ie/pull/195 |
| #192 | Open, draft, documentation; head e83405b68a77c3b2673258bd782391b981da4f49 | Exact-head validation/tests/platform/engine/security checks passed (runs 40298234438, 40298234458, 40298234404, 40298234386, 40298234489). Its base is stale/diverged; refresh to current main. Legal texts are drafts, not approvals. https://github.com/MSJ1708/shoir-ie/pull/192 |
| #191 | Open draft, non-mergeable stale main base | Refresh and review full diff/dependencies before deciding. |
| #189 | Open draft, non-mergeable old staging base | Reconcile with PR #190 which already moved staging to 8b36e3737705867019b9cf29e603cfc37e7911e6; refresh and review redundancy. |
| #182, #172, #184, #173, #181, #174, #188, #178, #179, #180, #175, #170 | Open draft PRs with stale or stacked bases; several marked non-mergeable | Audit overlap/dependency order, refresh bases, rerun current checks, and get independent reviews. Do not bulk-merge. |

PR #194 merged to main at 267be8889c310d90141c047d8aadd42c942423fb. It made edge_referral_summary optional at startup while keeping essential authentication/persistence exports fail-closed. PR #190 merged to staging branch staging-e2e-20261019 at 8b36e3737705867019b9cf29e603cfc37e7911e6; it was not a production release.

## 4. Supabase schema and Edge Function parity

Projects returned as active/healthy, both region eu-central-1:
- Staging: hfhrosthswcybccepmak
- Production: gcsamrdaeraxieaagsta

Both have core migrations 20261019124815_server_side_login_rate_limits and 20261019140600_atomic_subscription_request_decisions. Do not rerun them.

Staging has these additional beta/legal entries not recorded in production:
- 20261021130000_shoir_beta_legal_referrals
- 20261022110000_enforce_beta_legal_acceptance
- history version 20261025164602, named 20261023130000_refresh_refund_policy_acceptance_version

Read-only schema checks:

| Capability | Staging | Production |
|---|---|---|
| public.shoir_referrals | Present | Absent |
| shoir_subscription_requests.terms_accepted | Present | Absent |
| shoir_require_legal_acceptance_before_approval trigger | Present | Absent |
| refund_policy_version column | Present | Absent |
| shoir_* table count | 12 | 11 |

Reconcile the migration history version/name mismatch before production changes. Production shoir-persistence remains version 8, bundle hash 410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d and was not changed. Staging shoir-persistence is active at version 9, bundle hash 0551d88aceeca45ede2b890e874a75f542df670d2f2332a0878f23b5cc0b187e. The deployed bundle contains index.ts and security.ts and the updated refund-policy version. No matching staging function logs were returned after deployment, so runtime acceptance remains unproven.

Do not blindly copy staging schema or migrations to production. Before any production mutation: review migration SQL and compatibility, resolve ledger naming, assess legal-policy impact, verify backup and recovery, approve a change window and rollback plan, then deploy only the approved artifacts and verify post-deployment behavior.

## 5. Staging app and authenticated release gate

The latest recorded staging branch tip is 8b36e3737705867019b9cf29e603cfc37e7911e6. Validation run 40273588613 passed, but the authenticated release gate run 40273588637 was SKIPPED on that exact SHA.

The staging gate is opt-in: dispatch it manually in GitHub Actions or use its exact [run-authenticated-gate] marker on an approved staging-branch push. The connected toolset did not provide a workflow-dispatch write action, and no dummy commit was pushed to force a run. The workflow checks disposable shoir-e2e-* accounts, authenticated module rendering, Edge API lifecycle/workspace isolation, and browser shell/Excel/logout, uploading redacted artifacts.

The gate expects secrets including SHOIR_E2E_EDGE_URL, SHOIR_E2E_PUBLISHABLE_KEY, SHOIR_E2E_APP_URL and disposable account usernames/passwords for active, module, research, second-user, starter, expired and inactive cases; it also expects staging-host, expected-tier and throttle-verification variables. Configure them only in approved GitHub Actions secrets/variables, never in chat or source.

The app change in PR #196 is not yet merged or deployed to the staging app. The connected integrations could not establish the exact Streamlit URL-to-branch/running-SHA mapping; external web reads of the production and historical staging URLs returned cache-miss errors. Verify this through Streamlit Cloud before claiming the hosted revision matches the reviewed branch.

## 6. Master admin invariant

Aggregate-only database queries confirmed one active record in each environment matching:
- role: Enterprise Admin
- tier: Enterprise Plus Tier ($399)
- UTC expiry: 2099-01-01T00:00:00Z

Both environments had exactly one Enterprise Admin row. No username was selected. No master-account testing or mutation occurred.

## 7. Canonical 100-tool matrix

Source: docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv at main, blob SHA d1d5cb14c4b2e78ece1d8d78a19b26329761025a. It has 100 data rows and 19 columns.

| Status | Count |
|---|---:|
| VERIFIED_WORKING | 0 |
| IMPLEMENTED_NEEDS_VALIDATION | 98 |
| EXTERNAL_CONFIGURATION_REQUIRED | 2 |
| FOUNDATION_ONLY | 0 |
| MISSING | 0 |
| BLOCKED | 0 |

These are readiness classifications, not a completion percentage. No tool has the full acceptance evidence needed for VERIFIED_WORKING.

T096: PR #195 adds a generic HTTPS GET-only REST health/JSON-read path with host/port controls, DNS validation/pinning, TLS verification, redirect/proxy protections, time/size bounds, redaction, and role/tier gates. Automated tests passed, but no approved live endpoint/token/read exists. Keep EXTERNAL_CONFIGURATION_REQUIRED. It is not a native SAP/Oracle/SQL/MQTT/OPC-UA/WMS/MES adapter. Closure requires a real approved staging HTTPS endpoint/path/schema, least-privilege token in authorized secret storage, synthetic or approved data, and positive/negative test evidence.

T098: No verified OIDC login/callback/session mapping, provider-backed MFA enforcement, or durable security-audit persistence evidence exists. Closure requires an actual selected provider/client/issuer/audience/redirect configuration, correct state/nonce/PKCE and session/account/role mapping tests, MFA evidence, and durable authorized audit read/persistence/tamper-denial tests. Configuration flags are not proof that SSO/MFA works.

## 8. Release gate matrix

| Gate | Status | Closure evidence |
|---|---|---|
| Main automated validation, engine regression, security/quality | PASS | Exact-SHA runs listed above. |
| Branch protection and required independent review/checks | NOT VERIFIED / EXTERNAL ACTION REQUIRED | Authorized repository admin configures and verifies settings and exact check names. |
| Hosted Streamlit running revision equals reviewed candidate | NOT RUN | Streamlit owner verifies app repo, branch, entrypoint and deployed SHA. |
| Current staging authenticated release gate | NOT RUN; latest recorded run skipped | Authorized operator dispatches gate after secrets/variables and disposable users are confirmed; require non-skipped success and artifacts. |
| Staging Edge Function deployment/source inspection | PASS for deployment/source only; runtime acceptance NOT RUN | Execute authorized authenticated positive/negative staging flows and record results. |
| Production schema and function parity | FAIL | Production lacks the staging beta/legal/referral schema/migrations and still runs function v8; complete reviewed migration/release plan and rollback. |
| Admin invariant | PASS | Aggregate-only counts above. |
| Login/account/session lifecycle, backend tier enforcement, two-user isolation on current hosted staging | NOT RUN | Authenticated gate and browser evidence required. |
| T001-T100 full acceptance | 0 VERIFIED_WORKING | Independent numerical fixtures, auth/tenancy, persistence, exports and browser evidence per tool. |
| T096 live connector | EXTERNAL ACTION REQUIRED | Approved endpoint/token and actual successful/negative staging tests. |
| T098 OIDC/MFA/audit | EXTERNAL ACTION REQUIRED | Provider-backed authentication, MFA and durable audit evidence. |
| Saudi legal/privacy/tax/commercial approvals | EXTERNAL ACTION REQUIRED | Qualified professionals approve applicability, terms, data-transfer safeguards, tax/invoicing/payment and public claims. |
| Support, incident response, monitoring, recovery and rollback exercises | NOT RUN / EXTERNAL ACTION REQUIRED | Named owners, configured alerts, tested backup restoration/rollback and recorded evidence. |
| Production deploy and BETA removal | NO-GO / NOT AUTHORIZED | Do not deploy/remove BETA until mandatory gates pass and release owner records GO. |

## 9. Legal/commercial review

Both Supabase projects report region eu-central-1 outside KSA, so Saudi privacy counsel should map personal-data flows and assess PDPL applicability and safeguards for data transfers. This is a reason to perform a transfer assessment, not by itself a conclusion that the deployment is unlawful. Official starting points:
- SDAIA PDPL controller/processor guidance: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPLCP/
- SDAIA transfer regulation: https://dgp.sdaia.gov.sa/wps/portal/pdp/knowledgecenter/details/PDPL2/
- ZATCA Wave 25 e-invoicing update dated 24 July 2026: https://zatca.gov.sa/en/MediaCenter/News/Pages/Wave25-E-invoicing.aspx

Before paid launch, named Saudi legal/privacy counsel and the business owner must review the correct contracting identity; terms/privacy/cookie/refund/referral and engineering calculation disclaimer; PDPL purposes/retention/rights/subprocessors/transfers; intellectual property and marketing claims. A qualified tax/accounting professional must determine VAT/e-invoicing obligations from actual legal-entity and revenue status. Payment/subscription, refund/dispute, cancellation, webhook idempotency, support, incident response, monitoring, backup/restore, rollback, licensing and dependency review must be tested and owned. Drafts in PR #192 are not approvals; no compliance claim is made.

## 10. External actions required

1. Repository administrator: in GitHub Settings, configure and verify main protection, independent reviews, current required CI, conversation resolution and force-push/direct-push restrictions; provide saved-settings evidence. Current access receives 403 for the protection endpoint.
2. Release operator: finish exact-head CI and get independent review for PR #196; merge to staging only after review; deploy and confirm the staging app revision, exact banner and optional-referral startup.
3. GitHub Actions admin: verify dedicated shoir-e2e-* accounts/tier assignments; configure required SHOIR_E2E_* secrets/variables without exposing values; dispatch the authenticated release gate on the final staging revision and preserve redacted artifacts.
4. Streamlit Cloud owner: verify approved staging URL, repository/branch/entrypoint, secrets separation and running commit; capture sanitized evidence.
5. Supabase/DB release owner: reconcile migration ledger history; plan production schema/function rollout with review, backup/recovery, approved window, compatibility check and rollback; deploy only approved artifacts after release gates.
6. Integration owner: configure T096 approved endpoint and least-privilege secret; execute real success and security-denial tests.
7. Identity/security owner: select provider; configure and test OIDC, MFA, session/account mapping and durable audit.
8. Saudi legal/privacy counsel and business owner: approve legal identity, policies, calculation disclaimer, marketing/referral, PDPL and cross-border transfer review.
9. Tax/accounting/payment owner: determine VAT/e-invoicing and merchant eligibility, test payment/subscription/refund/cancellation/webhook flows before real payments.
10. Operations owner: finalize support/escalation, incident response, monitoring/alerts, backup restoration and rollback rehearsal.
11. Tool owners/QA: execute per-tool acceptance against independent fixtures and update registry/matrix/status claims with evidence.
12. Accountable release owner: record dated GO only after every mandatory gate passes on the exact reviewed/deployed candidate; then deploy through the approved process and remove BETA only after successful production smoke/monitoring.

## Final decision

**NO-GO. Keep BETA visible.** Production was not changed. Staging Edge Function deployment is verified at version 9, but the app fix is still in draft PR #196, the authenticated staging gate has not passed on the current candidate, and production migration/function parity plus provider-backed, legal, commercial and operations gates remain open.


---

## 11. Current-state reconciliation addendum — 26 October 2026, 12:16 UTC

This addendum supersedes status statements above that were explicitly phrased as “still running” or were based on earlier snapshots. The source documentation PR has been extended with the following dated artifacts:

- [Baseline audit](BASELINE_AUDIT_2026-10-26.md)
- [Pull request and dependency reconciliation](PR_RECONCILIATION_2026-10-26.md)
- [Staging and production schema/function parity](STAGING_PARITY_2026-10-26.md)
- [T096/T098 acceptance boundaries](T096_T098_ACCEPTANCE_2026-10-26.md)
- [Security and authorization acceptance](SECURITY_AUTH_ACCEPTANCE_2026-10-26.md)
- [Saudi legal, privacy and commercial checklist](LEGAL_COMMERCIAL_CHECKLIST_2026-10-26.md)
- [Production change plan](PRODUCTION_CHANGE_PLAN_2026-10-26.md)
- [Final gate matrix and handover](GO_NO_GO_HANDOVER_2026-10-26.md)

### Updated evidence facts

- PR #196 head is 7c0219385fe33bcb68b963b23dfac9a9c0fb886c. Validation test job passed in run 40303682913; the hosted deployment smoke job was SKIPPED. PR #196 is still a draft with no review submissions found. This is not a pass for hosted deployment or authenticated acceptance.
- Current staging SHA 8b36e3737705867019b9cf29e603cfc37e7911e6 has validation run 40273588613 success, while authenticated gate run 40273588637 was SKIPPED.
- Last actual manual authenticated gate found was run 39613907604 on older SHA 3c91c83db17724f415e7fb92d83ed338d9eb5a9a and FAILED. Its backend lifecycle/isolation and all 96 module routes passed, but two per-module logout-settlement cases failed (Enterprise Plus and Research Pack). The separate browser shell/Excel/logout step passed. Its redacted artifact belongs to a failed, stale run and does not establish current release readiness.
- Main reports protected=false; the accessible repository rulesets endpoint returned an empty array, while the detailed protection endpoint returned 403. Full branch protection is therefore not configured/verified through available evidence; administrator action is required.
- Aggregate-only read-only invariant checks found exactly one intended admin and one exact role/tier/active/expiry match in each environment. The admin identity was not queried and was not used for testing.
- Staging function inventory remains version 9 with bundle hash 0551d88aceeca45ede2b890e874a75f542df670d2f2332a0878f23b5cc0b187e; production remains version 8 with hash 410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d. No production mutation occurred.
- The canonical 100-tool matrix remains 100 unique IDs/names, 98 IMPLEMENTED_NEEDS_VALIDATION, 2 EXTERNAL_CONFIGURATION_REQUIRED, and zero VERIFIED_WORKING. It was not upgraded without evidence.
- The staging security advisor reports RLS enabled/no policies for public.shoir_referrals; the inspected grants inventory returned no explicit anon/authenticated/PUBLIC grants for the inspected shoir_* tables. This was documented for review; no policy change was made.

### Evidence and workflow limitations

The connected GitHub tool cannot invoke workflow_dispatch or inspect Actions secret values. An authorized Actions operator must check the required staging-only secrets/variables and disposable shoir-e2e-* accounts, then manually dispatch .github/workflows/authenticated-release-gate.yml on staging-e2e-20261019. Require a real non-skipped success on the exact reviewed/deployed candidate and inspect the redacted artifact. The Streamlit Cloud URL/repository/branch/entrypoint/running SHA mapping could not be verified from the connected tools.

All eight linked artifacts are documentation changes on this PR branch. Those new commits invalidate earlier CI as exact-head evidence; rerun the required checks on the final PR #197 SHA before requesting approval or merging.

**Decision remains NO-GO.** Keep BETA visible; production schema, Edge Function, application, accounts, tiers, subscriptions, payments, branch protections and BETA state were not changed.

---

## 12. Current-state reconciliation — after PR #196 staging merge, 26 October 2026

This section supersedes earlier statements in this report that PR #196 remains open/draft or that the staging branch head is still 8b36e3737705867019b9cf29e603cfc37e7911e6.

- **PR #196 merged staging-only** at 2026-10-26T12:37:51Z. Merge commit: `32ac85493bfadfbae172f546741aae74cd647069`. PR: https://github.com/MSJ1708/shoir-ie/pull/196. This is not a production merge or release.
- The subsequent opt-in workflow-trigger record was committed only to the staging branch as `bf1f9c7750b48e74d140a929eb94d521974ec0a9`. It changes documentation only and uses the workflow's documented `[run-authenticated-gate]` marker. Current staging branch tip at this check: `bf1f9c7750b48e74d140a929eb94d521974ec0a9`.
- Authenticated gate run **40324443387** is in progress on that exact SHA: https://github.com/MSJ1708/shoir-ie/actions/runs/40324443387. At last observation it was installing test dependencies. No preflight, backend isolation, module matrix, or browser result is yet available; therefore **no authenticated staging pass is claimed**.
- Ordinary push validation run **40324443559** is in progress on the same SHA. Its hosted `live-deployment-smoke` job is skipped by the workflow's documented branch/event condition and is not proof of the deployed Streamlit revision.
- PR #195 remains open/ready-for-review on `26d5e4f2a6569223976eff4fe43db83b0967d2e2`. Automated source/mock checks passed: test, engine regression and security/quality; the hosted live-smoke job is skipped on this non-audit PR. No independent review/approval is recorded and there is still no authorized real T096 endpoint/token test. Do not merge on CI alone.
- PR #197 remains draft/open on `86c995ff0f3b7ccea39139fe026645ca99f6b8fe`. Engine regression and security/quality succeeded; three PR workflows were still in progress when checked. The current head therefore is not yet fully validated, and no independent review is recorded.
- Open PR count is now 17 after #196 closed by merge. The repository branch API still reports `main.protected=false`; the visible repository rulesets endpoint is empty. The connected integration does not expose branch-protection mutation, workflow-dispatch, or secrets read access.
- The main head remains `267be8889c310d90141c047d8aadd42c942423fb`. No production app/schema/function, production user, payment, subscription, BETA flag, or master-administrator record was changed by this update.

## Updated release decision

**NO-GO. Keep BETA visible.** Re-evaluate only after the in-progress exact-SHA checks finish and the authenticated gate produces an inspected, non-skipped pass. The Streamlit Cloud app-to-branch/SHA mapping, saved branch-protection settings, production parity/change approval, external T096/T098 integrations, legal/commercial review, and operational recovery tests remain open.
