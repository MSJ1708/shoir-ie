# Shoir-IE live release recheck — 26 October 2026

**Decision: NO-GO. Keep BETA visible. Production is read-only for this review.**

This is a time-stamped verification snapshot, not a deployment authorization. It records current GitHub and Supabase metadata and aggregate-only read queries. It does not disclose account identifiers or credential values. The checks below do not establish the exact Streamlit deployed SHA; that remains unverified.

## 1. Exact source and PR baseline

| Item | Verified state |
|---|---|
| Main HEAD at this snapshot | `2ef44057f84162389d39998e922b505dcfe4d3e9` |
| Staging branch HEAD | `9e3899d6f5147584cf27585d946fa7b5d18d92d5` |
| PR #195 — T096 generic read-only REST and T098 readiness boundary | Merged at `33f75d27af73d4e33de87b62e44f278ddefbf6fe`; latest PR head `05cac4c8cc40f4da0d884b5b26a0a008e387a4de`. This is generic REST + Bearer only, not native SAP/Oracle. The GitHub reviews endpoint inspected during the audit returned no review submissions. |
| PR #196 — staging startup compatibility | Merged to staging at `32ac85493bfadfbae172f546741aae74cd647069`. |
| PR #197 — release evidence snapshot | Merged to main; current main includes its merge result. |
| ERP foundation PR #198 | Draft: [read-only SAP/Oracle ERP adapter foundation](https://github.com/MSJ1708/shoir-ie/pull/198), current head `38093374614a60c1c26721a1f1b4b2cafb1041ba` at the latest API recheck. Keep isolated from release changes. |

Before opening this audit-report PR, GitHub search returned 16 open PRs: #198, #192, #191, #189, #188, #184, #182, #181, #180, #179, #178, #175, #174, #173, #172 and #170. PR #199 itself adds a seventeenth open PR. All 17 were open as of the latest inventory: #199, #198, #192, #191, #189, #188, #184, #182, #181, #180, #179, #178, #175, #174, #173, #172 and #170. Most are drafts; several report `mergeable=false` and point at older base SHAs. Do not bulk merge. Recheck each PR's current head, checks, dependency order, review and disposition before action.

### Branch governance: FAIL / BLOCKED

- Live GitHub branch reads show `main.protected=false` and `staging-e2e-20261019.protected=false`.
- The accessible repository rulesets endpoint returned an empty list.
- The branch protection detail endpoint returned 403 for the connected integration. An authorized repository administrator must configure and independently verify enforced rules: pull requests, at least one eligible independent approval, required current checks, stale approval dismissal, review-conversation resolution and restrictions on direct/force push and branch deletion. Record and justify any bypass.
- No protection setting was changed by this review.

### Main/staging divergence: FAIL / BLOCKED

GitHub compare for `main` vs `staging-e2e-20261019` reports `status=diverged`, staging 98 commits ahead and main 412 commits ahead from merge base `6071ece0241cd9043be98675a81244d55b313918`. The tool lists extensive differences, including application code, workbench, workflows, migrations and the 100-tool matrix. This is not a safe basis for merging the staging branch wholesale into main. Identify the reviewed release commit and reconcile changes deliberately.

## 2. Authenticated staging evidence

- Candidate SHA: `9e3899d6f5147584cf27585d946fa7b5d18d92d5`.
- Authenticated release gate: [run 40326994939](https://github.com/MSJ1708/shoir-ie/actions/runs/40326994939), recorded successful.
- Redacted evidence artifact: [artifact 12653225915](https://github.com/MSJ1708/shoir-ie/actions/runs/40326994939/artifacts/12653225915), SHA-256 digest `d9e382b73e885d54257a22eaa50e2241fe273e2ac82915219f564f848be18695`, recorded expiry 9 November 2026.
- Standard validation: [run 40326994926](https://github.com/MSJ1708/shoir-ie/actions/runs/40326994926), recorded successful on the same candidate.
- Evidence summary in the release-gate report: preflight PASS; backend 22 PASS / 0 FAIL / 2 SKIP; 96/96 authenticated module routes PASS; browser shell/Excel/logout 7/7 PASS.
- Mandatory follow-ups remain: login-throttle probe was skipped because `SHOIR_E2E_VERIFY_LOGIN_THROTTLE` was not enabled; inactive-account denial was skipped because a dedicated inactive `shoir-e2e-*` account was not configured. Skips are not passes.
- The current workflow must be manually dispatched by an authorized GitHub Actions operator on `staging-e2e-20261019` after those staging-only prerequisites are configured. This review did not dispatch it.
- The actual authoritative Streamlit staging app, configured branch/entry point, startup banner and runtime SHA have not been independently verified through the available browser/deployment access. The app URLs listed in prior notes did not return inspectable page content through the available browser connector. This is NOT RUN/BLOCKED, not evidence that the app is down.

## 3. Direct read-only Supabase comparison

Projects were confirmed by the Supabase project listing:

| Property | Staging | Production |
|---|---|---|
| Project ref | `hfhrosthswcybccepmak` | `gcsamrdaeraxieaagsta` |
| Project status | ACTIVE_HEALTHY | ACTIVE_HEALTHY |
| Postgres build | `17.11.0.003` | `17.6.1.166` |
| Accounts (aggregate count) | 8 | 5 |
| Enterprise Admin role count | 1 | 1 |
| Exact admin invariant matches (role, tier `Enterprise Plus Tier ($399)`, active state, expiry `2099-01-01T00:00:00Z`) | 1 | 1 |
| Referral rewrite predicate matches (`affiliate_code` null/blank or `AFF-%-15`) | 0 | 5 |
| `shoir_referrals` table present | Yes | No |
| Legal acceptance columns in `shoir_subscription_requests` | 6 | 0 |
| Legal acceptance approval trigger present | Yes | No |
| `shoir-persistence` Edge Function version | 9 | 8 |
| Edge Function source SHA-256 metadata | `0551d88aceeca45ede2b890e874a75f542df670d2f2332a0878f23b5cc0b187e` | `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d` |

Queries returned aggregate counts only; no account identifiers, codes, password hashes or session tokens were selected. No database writes were made.

### Migration ledger and data-impact finding

Staging migration history includes:
- `20261021130000_shoir_beta_legal_referrals`
- `20261022110000_enforce_beta_legal_acceptance`
- ledger version `20261025164602`, name `20261023130000_refresh_refund_policy_acceptance_version`

Production migration history currently ends at `20261019140600_atomic_subscription_request_decisions`; the three later migration entries above are absent.

The repository migration `supabase/migrations/20261021130000_shoir_beta_legal_referrals.sql` updates `affiliate_code` and `updated_at` for blank/legacy affiliate codes and resolves duplicate codes before creating referral objects. The production aggregate confirms all five current accounts match the rewrite predicate, while the staging aggregate confirms zero matches. Applying that migration verbatim in production would therefore update existing account rows, not merely add a table. This migration is blocked until the migration is redesigned or its data effects are explicitly accepted by the data/business owner after independent review.

The refund-policy migration's source filename begins `20261023130000`, while staging's recorded version is `20261025164602`. Reconcile actual applied SQL/checksum, ledger and DDL; do not edit history or rerun a migration to make names appear consistent.

**No production migration, Edge Function deployment, account/subscription change, or master-admin mutation was performed.** Backup/PITR and restoration rehearsal were not independently verified by this read-only snapshot.

## 4. 100-tool readiness discrepancy

Both checked-in CSVs contain 100 tool target rows, but they do not reconcile:

| Matrix revision | Implemented, needs validation | Foundation only | External configuration | Verified working |
|---|---:|---:|---:|---:|
| Main blob `d3e7069adb73567cf5e40899eab07394c6381b16` | 98 | 0 | 2 | 0 |
| Staging blob `e5cd1f85c0dc2fa2dc17061441dc19ca95a69d45` | 87 | 11 | 2 | 0 |

The matrix difference is part of the source-branch divergence. Reconcile to a single reviewed authoritative matrix; do not interpret these counts as a pass percentage. Launch-critical calculation fixtures, workspace isolation, save/reload/re-login, exports opened and inspected, and hosted authenticated browser proof remain required per module.

## 5. T096, T098 and ERP scope

- **T096 PARTIAL / external configuration required.** PR #195 added the generic HTTPS GET-only REST verification path and redaction/security tests. A live non-production endpoint and least-privilege credentials have not been accepted yet.
- **T098 BLOCKED / external configuration required.** No provider-backed OIDC login/callback, account/role mapping, provider-enforced MFA or independently verified durable audit path has been evidenced.
- **SAP/Oracle BLOCKED for live support.** PR #198 is a separate draft foundation for six product-specific adapter boundaries, explicit field mapping, lineage, bounded pagination and fail-closed authorization tests. It also adds an informational product selector inside the existing T096 Integration Map. That selector is not a functional connection setup or test flow. The branch does not have provider-specific HTTP/auth, durable sync/checkpointing, import persistence or live non-production tenant acceptance. Do not advertise any SAP/Oracle product/resource as connected.
- A successful generic connector health check does not validate every resource API; each advertised resource requires its own positive and negative live acceptance.

## 6. Commercial, legal and operational gates

The current staging-branch legal package is present but not legally cleared:
- `docs/TERMS_AND_CONDITIONS.md` and `docs/PRIVACY_POLICY.md` explicitly state that the operating legal name, official address and applicable registration details must be published before a public commercial launch.
- The privacy notice requires verification of actual provider regions, contracts/subprocessors, transfer controls, retention and deletion. No completed counsel approval or end-to-end retention/deletion evidence was located in this source audit.
- The terms label calculations, forecasts, optimization, simulation, AI and report results as decision-support outputs requiring independent professional verification; this is not equivalent to formula-by-formula technical validation.
- The referral terms describe attribution only and do not promise rewards. Do not market rewards unless separately implemented and approved.
- `docs/LEGAL_RISK_REGISTER.md` says “NOT LEGALLY CLEARED FOR COMMERCIAL PRODUCTION”; `docs/THIRD_PARTY_LICENSE_REVIEW.md` says the licence review is incomplete; `docs/COMMERCIAL_LAUNCH_CHECKLIST.md` remains HOLD and its legal, privacy, calculation and operator approval rows are open.
- The live GitHub comparison shows these broader commercial/legal documents and the full 100-tool matrix are added on the staging branch relative to the current common base, not reconciled identically into the reviewed main tree. Reconcile the final versions into the reviewed release source and test the actual public notices in the deployed app before launch.

These remain NOT RUN / BLOCKED until accountable owners provide evidence and approvals:
- qualified Saudi legal and privacy review of the actual contracting entity, terms, privacy notices, refunds, referrals, legal acceptance and cross-border processing;
- real payment-lifecycle acceptance if payment collection is enabled;
- approved referral attribution/reward rules and abuse testing;
- monitoring/alerts, support ownership, credential rotation, backup restore rehearsal, incident tabletop and forward-recovery plan;
- written production change approval and named change/recovery owners.

The refund policy currently describes manual payment review and a separate STC Pay QR step rather than integrated card checkout. Do not market automated payment processing unless the actual server-verified lifecycle has been implemented and tested.

## 7. Required next actions

| Priority | Action | Owner | Release impact |
|---|---|---|---|
| P0 | Enforce and verify main branch protection/ruleset; record required checks | Repository administrator | Blocks safe review/merge |
| P0 | Configure dedicated inactive synthetic account and throttle verification variable; manually dispatch authenticated gate; inspect exact-SHA artifact | Authorized GitHub Actions/staging operator | Blocks complete staging gate |
| P0 | Identify authoritative Streamlit staging app and prove deployed branch/entry point/runtime candidate SHA and banner | Streamlit deployment owner | Blocks deployment verification |
| P0 | Redesign the referral migration so it does not silently rewrite existing production account state; independently review schema/checksum and aggregate impact | Database owner + reviewer | Blocks production schema change |
| P0 | Reconcile main/staging divergence and the two different tool matrices under a deliberate reviewed integration plan | Release engineer/reviewers | Blocks candidate promotion |
| P1 | Complete live non-production T096 endpoint tests and provider-backed T098 identity/audit acceptance | Integration/security owners | Blocks Enterprise integration claims |
| P1 | Continue ERP implementation in PR #198; finish tests, UI/persistence integration and live vendor acceptance separately | Integration owner + SAP/Oracle tenant admins | Does not block safe documentation foundation |
| P1 | Complete per-module reference fixtures, persistence/isolation and actual export round-trip evidence | Module owners/QA | Blocks any unverified module from launch scope |
| P0 | Obtain legal/commercial and operational approvals and publish explicit signed GO decision | Business/release owner | Blocks paid launch/BETA removal |

## Final decision

**NO-GO. BETA stays visible.** The connected checks have established current source and database facts, but they have not established a fully accepted hosted staging deployment, a clean mandatory authenticated gate, provider-backed T096/T098 operation, migration safety for existing production data, or paid-launch approvals.


## 8. Latest execution addendum — 26 October 2026

This section records the latest checks performed for this draft; it does not authorize production changes.

- **Branches:** `main` = `2ef44057f84162389d39998e922b505dcfe4d3e9`; `staging-e2e-20261019` = `9e3899d6f5147584cf27585d946fa7b5d18d92d5`. Both accessible branch API responses report `protected=false`; the visible repository-rulesets endpoint is empty, while the branch-protection detail endpoint returns HTTP 403 to this integration. Branch governance remains blocked pending authorized administrator configuration and verification.
- **Open PRs:** the current GitHub API lists 17: #199, #198, #192, #191, #189, #188, #184, #182, #181, #180, #179, #178, #175, #174, #173, #172 and #170. PR #199 is a draft at `906b9125a651b570f3e3c2e261933104a9bb8711`; PR #198 is a draft at `38093374614a60c1c26721a1f1b4b2cafb1041ba`. Neither has a requested reviewer or review submission recorded by the connected endpoints.
- **Staging candidate:** authenticated gate [40326994939](https://github.com/MSJ1708/shoir-ie/actions/runs/40326994939) and validation [40326994926](https://github.com/MSJ1708/shoir-ie/actions/runs/40326994926) succeeded on `9e3899d6f5147584cf27585d946fa7b5d18d92d5`. Reported outcomes remain backend 22 PASS / 0 FAIL / 2 SKIP, 96/96 authenticated module routes PASS, 7/7 browser shell/Excel/logout PASS. Login-throttle and inactive-account denial remain skipped mandatory probes. `live-deployment-smoke` is skipped on the validation run, so the deployed Streamlit runtime SHA, branch, entry point and staging banner are still unverified.
- **Supabase:** staging migration history contains 17 entries and production 14; `shoir-persistence` is version 9 in staging and 8 in production; staging has six legal-acceptance columns and one trigger while production has none; the referral table exists only in staging. Aggregate-only SQL confirmed 8 staging accounts and 5 production accounts, exactly one full master-admin invariant match in each, and blank affiliate codes 0/8 staging vs 5/5 production. This confirms existing-row data-impact from the referral migration. No database rows, Edge Functions, subscriptions or account fields were changed.
- **100-tool matrix:** robust CSV parsing confirms 100 target rows in both versions. Main blob `d3e7069adb73567cf5e40899eab07394c6381b16` has 98 `IMPLEMENTED_NEEDS_VALIDATION`, 0 `FOUNDATION_ONLY`, 2 `EXTERNAL_CONFIGURATION_REQUIRED`; staging blob `e5cd1f85c0dc2fa2dc17061441dc19ca95a69d45` has 87, 11, and 2 respectively. Both report zero verified-working tools. The matrix/source divergence still requires a reviewed reconciliation.
- **Supabase advisors:** staging reports an informational `rls_enabled_no_policy` finding for `public.shoir_referrals`. Read-only privilege checks show `anon` and `authenticated` have no SELECT or INSERT grants and no policy exists, matching the migration's server-only access intent. Do not add broader public access merely to silence the finding. Unused-index notices (19 staging, 17 production) require query-plan/workload analysis before any removal.
- **Decision:** **NO-GO; keep BETA visible.** Production migration/function deployment, subscription changes, master-admin tests/changes and BETA removal were not performed and remain unauthorized.

## 9. Follow-up after ERP secret-field hardening — 26 October 2026

- The mapper's sensitive-field filter now rejects source or canonical mappings containing access/refresh tokens, passwords, secrets, authorization headers, API/private keys, client secrets, credentials, bearer values and cookies. Seven parameterized regression cases were added for these patterns.
- CI on exact ERP head `38093374614a60c1c26721a1f1b4b2cafb1041ba` has progressed as follows:
  - [Python test suite — run 40339560945](https://github.com/MSJ1708/shoir-ie/actions/runs/40339560945): **PASS**. The workflow step `python -m pytest -q tests` succeeded, so the seven new regression cases are included in the passing suite.
  - [Security and quality — run 40339560898](https://github.com/MSJ1708/shoir-ie/actions/runs/40339560898): **PASS**.
  - [Engine regression — run 40339560969](https://github.com/MSJ1708/shoir-ie/actions/runs/40339560969): **PASS**.
  - [Validation — run 40339560897](https://github.com/MSJ1708/shoir-ie/actions/runs/40339560897): **IN PROGRESS**; local runtime/browser smoke steps are still running.
  - [Platform tests — run 40339560946](https://github.com/MSJ1708/shoir-ie/actions/runs/40339560946): **IN PROGRESS**; regression tests have not completed.
  - `live-deployment-smoke` is **SKIPPED**, so these results are not live SAP/Oracle acceptance and do not prove deployment.
- No independent review is available for PR #198 or #199. Keep both drafts and do not merge until every applicable required check has completed, an independent review is recorded, and release-owner approval is obtained.
- The six ERP products remain `SPECIFICATION_ONLY_UNCONFIGURED`. No provider authentication, real HTTP transport, durable sync/checkpointing, import persistence or live sandbox tenant has been implemented and accepted.
