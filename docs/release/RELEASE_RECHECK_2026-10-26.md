# Shoir-IE live release recheck — 26 October 2026

**Decision: NO-GO. Keep BETA visible. Production is read-only for this review.**

The current external blocker register, with owner roles, dependencies, exact actions and closure evidence, is in [`EXTERNAL_ACTION_REGISTER_2026-10-26.md`](EXTERNAL_ACTION_REGISTER_2026-10-26.md). The PR disposition matrix is in [`PULL_REQUEST_DISPOSITION_MATRIX_2026-10-26.csv`](PULL_REQUEST_DISPOSITION_MATRIX_2026-10-26.csv).

The authoritative closure checklist for the 20+ mandatory readiness areas, including status, evidence, owner role and objective next action, is [`MASTER_GO_NO_GO_CHECKLIST_2026-10-26.md`](MASTER_GO_NO_GO_CHECKLIST_2026-10-26.md).

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

A fresh open-PR query for this synchronization found 20 open PRs: #202, #201, #200, #199, #198, #192, #191, #189, #188, #184, #182, #181, #180, #179, #178, #175, #174, #173, #172 and #170. Several are drafts or have stale bases, dirty mergeability or overlapping work. PR #200 remains a draft but its current head `c135f5b1b3cbe5ac40fd515509bd55f4a7fb0876` passed exact-head validation run [40378115693](https://github.com/MSJ1708/shoir-ie/actions/runs/40378115693); that is code/CI evidence, not a live authenticated staging pass. PR #202 is a draft targeting staging to prevent silent PDF/PowerPoint table truncation. Core pagination at commit `8263f30b945d8fda1329f54805b9017903da7e1c` passed [run 40378862787](https://github.com/MSJ1708/shoir-ie/actions/runs/40378862787): 826 passed, 2 skipped, 71 warnings, 5 subtests passed; compile/import and local desktop/mobile browser smoke passed. A later revision adds exact PR-head stamping, artifact retention, and assertions for every numeric value; its current head `2ed36435b75c9a97da38d06479b92001b962c422` is in validation run [40380788440](https://github.com/MSJ1708/shoir-ie/actions/runs/40380788440), currently in progress. The hosted deployment smoke is skipped; this does not prove hosted staging or production behavior. PR #201 is policy-version documentation/test work; PR #199 is this recheck report; PR #198 remains an adapter foundation only. Do not bulk merge; recheck each PR head, base, current checks, review, overlap and integration dependencies before action.

### Branch governance: FAIL / BLOCKED

- Fresh branch reads report `main.protected=true` and `staging-e2e-20261019.protected=true`. The earlier `protected=false` statement in a previous snapshot is stale and corrected by this recheck.
- The current branch summary reports no configured required status-check contexts for `main` (`enforcement_level=everyone`, `contexts=[]`, `checks=[]`); staging reports `enforcement_level=off` with empty contexts/checks. The repository rulesets endpoint returned an empty list.
- Therefore, branch protection exists but required-check enforcement is not established; staging explicitly reports required-check enforcement off. Review-count, stale-approval dismissal, direct/force-push restriction and deletion protection are not fully verifiable through the available branch summary. An authorized repository administrator must configure and independently verify PR-only changes, eligible independent review, current required checks, stale-approval dismissal, resolved review conversations, direct/force-push restrictions and branch deletion protection; document any exception.
- No protection setting was changed by this review.

### Main/staging divergence: FAIL / BLOCKED

GitHub compare for `main` vs `staging-e2e-20261019` reports `status=diverged`, staging 98 commits ahead and main 412 commits ahead from merge base `6071ece0241cd9043be98675a81244d55b313918`. The tool lists extensive differences, including application code, workbench, workflows, migrations and the 100-tool matrix. This is not a safe basis for merging the staging branch wholesale into main. Identify the reviewed release commit and reconcile changes deliberately.

## 2. Authenticated staging evidence

- Candidate SHA: `9e3899d6f5147584cf27585d946fa7b5d18d92d5`.
- Authenticated release gate #88: [run 40369188234](https://github.com/MSJ1708/shoir-ie/actions/runs/40369188234), workflow conclusion `success`, exact branch `staging-e2e-20261019`, candidate SHA `9e3899d6f5147584cf27585d946fa7b5d18d92d5`.
- Redacted evidence artifact: [artifact 12672656752](https://github.com/MSJ1708/shoir-ie/actions/runs/40369188234/artifacts/12672656752), name `shoir-ie-authenticated-release-evidence`, 472,693 bytes, SHA-256 `697cce352663dd9574f702846a876631e2ca695036ed6934982a7ac4e4d7dcf8`, recorded expiry 9 November 2026. The job log and report summaries were inspected; all three gate steps and evidence upload completed.
- Gate #88 reported preflight/candidate-build success; backend **24 PASS / 0 FAIL / 0 SKIP**, 96/96 module-route/default-state rendering PASS, and 7/7 browser shell/Excel/logout PASS. The inactive-account denial and login-throttle probes both executed and passed in this run.
- Important scope limit: session-revocation entries in this report confirm logout cleanup calls; they do not reuse each revoked token to prove subsequent requests are denied. The gate also does not contain a real workbook import-transform-download round-trip, parsed XLSX assertions, general PDF/PPT/XLSX acceptance, formula-by-formula numerical validation, or production runtime parity.
- PR #200's strict gate hardening remains a draft and has no independent review, but its current head `c135f5b1b3cbe5ac40fd515509bd55f4a7fb0876` passed [validation run 40378115693](https://github.com/MSJ1708/shoir-ie/actions/runs/40378115693): 835 passed, 2 skipped, 71 warnings and 5 subtests passed; Python compilation, top-level import smoke and local Streamlit desktop/mobile browser smoke also passed. The hosted live-deployment-smoke check was skipped, as expected for an ordinary PR. The revised helper now probes the same token after logout and requires HTTP 401; this has not yet run against an updated live staging candidate. After independent review and authorized integration, dispatch the strict gate against that exact resulting staging SHA.
- The actual authoritative Streamlit staging app, configured branch/entry point, startup banner and runtime SHA remain BLOCKED/NOT RUN through the available deployment access. The run identifies `shoir-ie-atvvfsacfxvqtrka37owfx.streamlit.app` as its target host, but that does not independently prove platform settings or deployed revision. This is not evidence that the app is down.

## 3. Direct read-only Supabase comparison

Projects were confirmed by the Supabase project listing:

| Property | Staging | Production |
|---|---|---|
| Project ref | `hfhrosthswcybccepmak` | `gcsamrdaeraxieaagsta` |
| Project status | ACTIVE_HEALTHY | ACTIVE_HEALTHY |
| Postgres build | `17.11.0.003` | `17.6.1.166` |
| Accounts (aggregate count, latest read-only check) | 9 | 5 |
| Enterprise Admin role count | 1 | 1 |
| Exact admin invariant matches (role, tier `Enterprise Plus Tier ($399)`, active state, expiry `2099-01-01T00:00:00Z`) | 1 | 1 |
| Referral rewrite predicate matches (`affiliate_code` null/blank or `AFF-%-15`) | 1 | 5 |
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


## 8. Consolidated latest execution evidence — 26 October 2026

This consolidated section supersedes the older appended snapshots and addenda below the original Sections 1–7. Historical evidence is retained only where it explains how current status changed; current state is stated here.

### Current branch identity and governance

- `main`: `2ef44057f84162389d39998e922b505dcfe4d3e9`.
- `staging-e2e-20261019`: `9e3899d6f5147584cf27585d946fa7b5d18d92d5`.
- GitHub currently reports `protected=true` for both branches. However, the branch summary lists no required status-check contexts on `main`; staging has required-check enforcement `off`; the accessible repository-rulesets endpoint is empty. Protection exists but effective required-check/review enforcement is not established. Repository-administrator action remains BLOCKED.
- GitHub compare remains divergent: staging is 98 commits ahead and main is 412 commits ahead of merge base `6071ece0241cd9043be98675a81244d55b313918`. Do not merge staging wholesale into main.
- The synchronized open-PR query found 20 open PRs: #202, #201, #200, #199, #198, #192, #191, #189, #188, #184, #182, #181, #180, #179, #178, #175, #174, #173, #172 and #170. Most are drafts or have stale/overlapping bases. Keep selected changes isolated; do not bulk merge.
- PR #199 is this draft evidence/checklist PR targeting `main`. Its head at the start of this final evidence sync was `d896ea9a03e4c1edabec03f00f7a9f5b54be3df5`; the documentation edit replacing the stale appended snapshots advances the branch again. Re-fetch the live PR head and current checks before any merge decision.
- PR #200 is draft, targeting staging, current head `c135f5b1b3cbe5ac40fd515509bd55f4a7fb0876`. Exact-head validation [40378115693](https://github.com/MSJ1708/shoir-ie/actions/runs/40378115693) completed SUCCESS: **835 passed, 2 skipped, 71 warnings, 5 subtests passed**, with compile/import and local browser smoke successful; hosted deployment smoke was skipped. No independent review is recorded; live authenticated staging gate remains outstanding.
- PR #201 is draft, targeting staging, head `f5bd0c7a7fe95aa393da56986ced451b75b83e6f`. Validation [40372201071](https://github.com/MSJ1708/shoir-ie/actions/runs/40372201071) succeeded; live-deployment smoke was skipped. No independent review or legal sign-off is recorded.
- PR #202 is draft, targeting staging, current head `2ed36435b75c9a97da38d06479b92001b962c422`. Earlier pagination commit `8263f30b945d8fda1329f54805b9017903da7e1c` passed [40378862787](https://github.com/MSJ1708/shoir-ie/actions/runs/40378862787): 826 passed, 2 skipped, 71 warnings, 5 subtests passed, including the 67-row PDF/PPTX parser tests. The current head adds checks for all numeric values, optional PDF/PPTX plus SHA-256 manifest evidence, and 14-day artifact upload; exact-head run [40380788440](https://github.com/MSJ1708/shoir-ie/actions/runs/40380788440) was IN_PROGRESS at this snapshot. Treat the newest change as unverified until the run succeeds and its artifact is inspected; live deployment smoke was skipped.
- PR #198 remains a separate draft foundation (`38093374614a60c1c26721a1f1b4b2cafb1041ba)); the adapter work is not live SAP/Oracle connectivity.

### Authenticated staging evidence: current versus historical

- **Current gate evidence:** authenticated gate #88, [run 40369188234](https://github.com/MSJ1708/shoir-ie/actions/runs/40369188234), concluded success on branch `staging-e2e-20261019`, source SHA `9e3899d6f5147584cf27585d946fa7b5d18d92d5`.
- Artifact [12672656752](https://github.com/MSJ1708/shoir-ie/actions/runs/40369188234/artifacts/12672656752) is `shoir-ie-authenticated-release-evidence`, 472,693 bytes, SHA-256 `697cce352663dd9574f702846a876631e2ca695036ed6934982a7ac4e4d7dcf8`; recorded expiry 9 November 2026.
- Run #88 reported **24 backend PASS / 0 FAIL / 0 SKIP**, 96/96 authenticated module-route/default-state render cases PASS, and 7/7 browser shell/Excel-route/logout cases PASS. The inactive-account denial and login-throttle probes both ran and passed. This supersedes run [40326994939](https://github.com/MSJ1708/shoir-ie/actions/runs/40326994939), whose older artifact reported 22 PASS / 0 FAIL / 2 SKIP.
- Scope limits still apply: historical gate #88 proves its tested route/API/browser behavior, not all module calculations, every protected action, real Excel file round-trip, full PDF/PPT/XLSX export correctness, live enterprise providers or production runtime parity. Gate #88 only confirmed logout cleanup and did not reuse the token. PR #200 now contains a no-write same-token-after-logout probe and mock regression tests that passed on its latest exact head, but the live probe still needs to run on the reviewed/integrated staging candidate.
- Gate #88 predates the strict classifier now in PR #200. After independent review and approved integration, dispatch a fresh authenticated gate on the exact resulting staging SHA. An earlier passing gate cannot validate later workflow code.
- The connected access did not independently verify authoritative Streamlit app settings, deployed runtime SHA, branch/entry point, secret target project, startup logs and visible banner. This remains BLOCKED/NOT RUN, not evidence that the app is down.

### Current database and Edge Function parity (read-only)

- Supabase production project `gcsamrdaeraxieaagsta` is ACTIVE_HEALTHY on Postgres `17.6.1.166`; staging project `hfhrosthswcybccepmak` is ACTIVE_HEALTHY on `17.11.0.003`.
- Migration ledger: production has **14** entries and ends at `20261019140600_atomic_subscription_request_decisions`; staging has **17** entries. Staging additionally records `20261021130000_shoir_beta_legal_referrals`, `20261022110000_enforce_beta_legal_acceptance`, and ledger version `20261025164602` with name `20261023130000_refresh_refund_policy_acceptance_version`. The filename/ledger mismatch requires SQL/checksum/DDL reconciliation, not a blind rename or ledger rewrite.
- Production has no `public.shoir_referrals` table, none of the six legal-acceptance columns on `shoir_subscription_requests`, and no matching legal-acceptance approval trigger; staging has the table, all six columns and the trigger.
- `shoir-persistence`: production version 8, source SHA-256 `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`; staging version 9, source SHA-256 `0551d88aceeca45ede2b890e874a75f542df670d2f2332a0878f23b5cc0b187e`. Staging contains legal/referral behavior absent from production. No Edge Function deployment was performed.
- Latest aggregate-only SQL observed **5 production accounts** and **9 staging accounts**, with exactly one account matching the full master-admin invariant in each environment. No identifying account data was selected and no row was changed.
- The existing referral migration predicate matches all 5 production accounts because `affiliate_code` is NULL; it matches 1 staging account. The migration also changes `updated_at`. Do not run the migration verbatim. Preserve existing values and timestamps unless a separate data/backfill decision is explicitly approved and rehearsed.
- Payment-proof storage bucket `subscription-payment-proofs` is private in both projects.
- Staging advisor at `2026-10-26T18:03:53Z` has one INFO `rls_enabled_no_policy` finding for `public.shoir_referrals`. Read-only SQL finds no policies and no effective SELECT/INSERT/UPDATE/DELETE table grants to `anon`/ `authenticated`; `service_role` does have CRUD grants. This narrows direct client exposure risk but does not establish all service-role code paths are owner/actor scoped. Keep REVIEW REQUIRED; do not add permissive policies just to silence the advisor.

### Tool, integration, commercial and legal status

- Both main and staging inventory files have 100 tool rows, but classifications differ. The recorded main matrix has 98 `IMPLEMENTED_NEEDS_VALIDATION`, 0 `FOUNDATION_ONLY`, 2 `EXTERNAL_CONFIGURATION_REQUIRED`; staging has 87, 11 and 2 respectively. Both report **zero verified-working tools**. Route-render counts are not acceptance percentages; reconcile to one canonical matrix and add reference fixtures or narrow paid launch scope.
- T096 remains PARTIAL: generic REST foundation exists, but approved live non-production endpoint/credential acceptance is missing. T098 remains BLOCKED for provider-backed OIDC/MFA and durable audit acceptance.
- SAP/Oracle: no approved non-production provider tenant or live provider-level acceptance is recorded. PR #198 is mapping/specification foundation only; do not market SAP/Oracle as connected.
- Excel workbook import-transform-download and parsed XLSX assertions remain NOT RUN. PR #202's core PDF/PowerPoint pagination and 67-row parser tests passed at `8263f30`; the latest evidence-retention/numeric-value assertion revision `2ed36435b75c9a97da38d06479b92001b962c422` is still being validated in run [40380788440](https://github.com/MSJ1708/shoir-ie/actions/runs/40380788440). Independent export acceptance remains NOT RUN until the exact latest head passes, its actual synthetic artifact bundle is verified, and representative outputs are reviewed. Full PDF/PPT/XLSX export opening/structural validation, calculation fixtures, units/boundaries/solver-error validation and tool-level persistence evidence remain blocked for unverified launch-critical tools.
- Qualified Saudi legal/privacy counsel has not approved the actual operator, processing/data-transfer flows, terms, payment/refund/cancellation semantics or consumer disclosures. PDPL, implementing and data-transfer regulations, E-Commerce Law applicability, subprocessors, hosting regions, AI-provider processing, retention/deletion, rights requests and incident obligations must be assessed by qualified counsel against the real service. Current official references are listed in [the master checklist](MASTER_GO_NO_GO_CHECKLIST_2026-10-26.md).
- Release-specific SBOM, licence/asset/IP sign-off, complete operational monitoring ownership, and verified backup/PITR plus isolated restoration rehearsal are not evidenced as complete.

### Authoritative checklist and decision

Use [MASTER_GO_NO_GO_CHECKLIST_2026-10-26.md](MASTER_GO_NO_GO_CHECKLIST_2026-10-26.md) as the source of truth for each requirement's status, evidence, owner role and closure action. The supporting [authenticated staging matrix](AUTHENTICATED_STAGING_TEST_MATRIX_2026-10-26.csv), [external action register](EXTERNAL_ACTION_REGISTER_2026-10-26.md), [PR disposition matrix](PULL_REQUEST_DISPOSITION_MATRIX_2026-10-26.csv), [T096/T098 report](T096_T098_ACCEPTANCE_REPORT_2026-10-26.md), and [tool matrix reconciliation](TOOL_MATRIX_RECONCILIATION_2026-10-26.csv) remain linked references.

**Decision: HOLD — safe work continues; production release remains blocked. Keep BETA visible.** This update was documentation/source review only. No production database, Edge Function, account, subscription, hosted secret, deployment or BETA state was changed. Production deployment and post-deployment verification are NOT RUN and not authorized.



## 10. Incremental live recheck — 26 Oct 2026, 19:09 UTC

This addendum records checks performed after the snapshot above. It supersedes earlier status text only where explicitly stated; the historical runs and previous findings remain historical evidence.

### Exact current source and CI

- `main` remains `2ef44057f84162389d39998e922b505dcfe4d3e9`. Exact-SHA push workflows are green: [validation 40333856836](https://github.com/MSJ1708/shoir-ie/actions/runs/40333856836), [engine regression 40333856673](https://github.com/MSJ1708/shoir-ie/actions/runs/40333856673), and [security/quality 40333856656](https://github.com/MSJ1708/shoir-ie/actions/runs/40333856656). This is not production deployment evidence.
- `staging-e2e-20261019` remains `9e3899d6f5147584cf27585d946fa7b5d18d92d5`. The authenticated gate [40369188234](https://github.com/MSJ1708/shoir-ie/actions/runs/40369188234) completed successfully on that exact SHA. Recorded cases: backend 24/24 PASS; module-route/default-state rendering 96/96 PASS; browser shell, Excel module and logout 7/7 PASS. It does not certify the full calculation engine, comprehensive data import/export, provider connectivity, or the exact hosted Streamlit revision.
- The branch comparison still reports the branches as diverged: staging is 98 commits ahead and 412 behind main from the API comparison. Do not merge either branch wholesale.
- Detailed GitHub branch-protection reads now return HTTP 403 to the connected integration. Branch metadata still reports `protected=true`, but that alone does not prove required-check enforcement. Treat the previously recorded missing/disabled required-check enforcement as unresolved until an authorized admin independently verifies the saved settings and direct-push denial.

### Schema, Edge Function and protected-account recheck

- Read-only aggregate checks found exactly one account matching the protected master-admin invariant in staging and one in production. No account identity was returned or used for testing. Aggregate account counts were staging 9 and production 5; no account records were changed.
- Staging reports migrations `20261021130000_shoir_beta_legal_referrals`, `20261022110000_enforce_beta_legal_acceptance`, and `20261023130000_refresh_refund_policy_acceptance_version` that are absent from production's migration history. The production schema lacks `public.shoir_referrals` and its related legal-acceptance fields.
- `shoir-persistence` remains staging version 9, SHA-256 `0551d88aceeca45ede2b890e874a75f542df670d2f2332a0878f23b5cc0b187e`; production is version 8, SHA-256 `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`. The deployed sources are not equivalent. Do not deploy version 9 or apply production migrations until the compatibility and recovery gate is satisfied.
- Staging's security advisor reports one informational `rls_enabled_no_policy` finding for `public.shoir_referrals`. The repository migration explicitly revokes table access from `PUBLIC`, `anon`, and `authenticated`, and grants table access to `service_role` only. Do not create a broad user-facing RLS policy just to silence this advisor; independently verify effective grants before any release.
- The historical referral migration rewrites `affiliate_code` for existing NULL/blank values and values matching `AFF-%-15`, changes `updated_at`, and repairs duplicate codes. Since staging has already applied it but production has not, migration promotion is blocked pending an explicit data-preservation decision and rehearsal. No migration was run in either environment during this recheck.

### Export acceptance and current code work

- PR [#202](https://github.com/MSJ1708/shoir-ie/pull/202), head `6d81ea3e2482e7ef29a66404dc2f34f3c6c58e35), has a successful exact-head validation run [40382266287](https://github.com/MSJ1708/shoir-ie/actions/runs/40382266287). I downloaded and independently parsed its synthetic artifact [12678948973](https://github.com/MSJ1708/shoir-ie/actions/runs/40382266287/artifacts/12678948973): the PDF contains all 67 metric labels across 4 pages; the PPTX contains all 67 labels and values in the original order across 5 table slides (6 total slides), uses a 16:9 canvas, and has no out-of-bounds shapes. Artifact hashes from its manifest: PDF `33fd6f0919b433a196cc2ebf2fe29a6b498efcf320605c9152263fbeaf691836`; PPTX `5b1bdf06436d447181ebcc642612066b94d11963c74abae24d0b05f62430c654`. The separate hosted deployment smoke was skipped; live staging acceptance and XLSX acceptance remain open.
- New draft PR [#203](https://github.com/MSJ1708/shoir-ie/pull/203), based directly on staging, disables XlsxWriter formula/URL auto-conversion in `build_excel_report` and adds a parser-level regression test for formula-like titles, headers, values, audit fields and URL-like text. Candidate SHA: `8fc8a676fc127af5ff43d417d8d2a09c03998289`. Exact-head validation [40383978529](https://github.com/MSJ1708/shoir-ie/actions/runs/40383978529) and push validation [40383935924](https://github.com/MSJ1708/shoir-ie/actions/runs/40383935924) were still in progress at this snapshot. **Do not mark this patch tested until both relevant current-head results are refreshed and the test is confirmed passing.**
- This session did not perform a production or staging deploy, database migration, Edge Function deployment, account/subscription change, or secret change. The Streamlit-hosted application settings and running revision could not be read through the connected tools; the live app URL was not independently verifiable here.

### Updated disposition

**HOLD — safe work continues; production and paid general availability are not approved.** Current hard blockers remain: exact hosted runtime identity, enforced branch governance, independent review/integration of drafts, production/staging schema and function compatibility, data-preservation plan for referral identifiers, comprehensive calculation and workbook/export acceptance, live provider integrations where advertised, backup/restore evidence, and qualified legal/commercial approval.


## 11. XLSX export hardening follow-up

A wider source search found direct report-generation paths in addition to the shared `build_excel_report` helper. The new draft [PR #203](https://github.com/MSJ1708/shoir-ie/pull/203), base `staging-e2e-20261019`, now covers these source routes:

- `shoir_upgrade.py`: disables XlsxWriter automatic formula and URL conversion in the shared report builder.
- `shoir_excel_studio.py`: disables XlsxWriter automatic formula/URL conversion in both the cleaned workbook and governance report paths.
- `shoir_industrial_workbook.py`: disables automatic formula/URL conversion in both presentation export and internal persistence workbook serialization. Formula metadata remains separate from calculated workbook values.
- `shoir_facility_layout.py` and `shoir_enterprise_integration.py`: apply `literalize_untrusted_formula_cells` to generated OpenPyXL data/audit exports where spreadsheet formulas are not an intended feature.
- `tests/test_xlsx_export_formula_injection.py`: reopens generated workbooks and checks formula-like strings, URL-like values, data, headers and audit values.

### Exact-head regression outcome and correction

- Candidate `0241454c28697f986dae45a466a2ce086b146466` failed [pull-request validation run 40385420275](https://github.com/MSJ1708/shoir-ie/actions/runs/40385420275): `827 passed, 2 skipped, 1 failed, 71 warnings, 5 subtests passed`. The single failure was a test-fixture row offset (`A3` was the intended header, not the first data row). The failure was not suppressed.
- The assertion was corrected in commit `8663d612f820ac1ae6d6af8c1776e7a619c1a029` to check the actual data row and an adjacent URL-like value.
- Exact-head push validation [40386115815](https://github.com/MSJ1708/shoir-ie/actions/runs/40386115815) was in progress, and PR validation [40386126755](https://github.com/MSJ1708/shoir-ie/actions/runs/40386126755) was queued at this report update. **Do not mark the expanded patch tested until exact-head checks finish successfully.** The local hosted-app smoke lane is skipped by workflow conditions and is not live deployment evidence.
- PR #203 remains a draft and has no independent review in this audit. It has not been merged, and the change has not been deployed to staging or production.

### Effective referral-table privileges

A read-only privilege check on staging returned:
- `anon`: no SELECT or INSERT on `public.shoir_referrals`.
- `authenticated`: no SELECT or INSERT on `public.shoir_referrals`.
- `service_role`: SELECT and INSERT privileges present.

Production's catalog query confirmed that `public.shoir_referrals` and `public.shoir_legal_acceptances` are absent. This confirms the staging-only service-role boundary observed in the migration and reinforces the production schema mismatch. Do not add public or general authenticated-user policies merely to silence the staging RLS advisor; validate actual Edge Function server-side authorization before considering the feature complete.

The Supabase performance advisor reports unused-index informational findings in both projects (19 on staging, 16 on production in this snapshot). These are advisory-only; do not drop indexes without workload evidence and an independent review.

**Disposition remains HOLD.** No staging or production migration, Edge Function deploy, user/account/subscription mutation, secret change, or app deployment has been performed.


## 12. Current candidate outcomes and protected-admin remediation

### XLSX export hardening — latest exact PR head

- Expanded PR #203's latest head is `8663d612f820ac1ae6d6af8c1776e7a619c1a029`.
- Exact-head pull-request validation [40386126755](https://github.com/MSJ1708/shoir-ie/actions/runs/40386126755) completed **success** with `828 passed, 2 skipped, 71 warnings, 5 subtests passed`.
- The previous failure was corrected transparently and remains visible in history: [40385420275](https://github.com/MSJ1708/shoir-ie/actions/runs/40385420275) failed only because a test expected the data cell at A3 when A3 was the writer's header row; the corrected test checks A4 and A5.
- Push validation [40386115815](https://github.com/MSJ1708/shoir-ie/actions/runs/40386115815) was in progress at the last status read. The exact PR-run green result is real, but the PR remains draft; independent review and broader release checks are still required. Hosted deployment smoke was skipped.

### Protected-administrator login behavior — new draft PR #204

Code review of the currently deployed `shoir-persistence` sources found that both staging v9 and production v8 include a login-time code path that updates the protected administrator's tier and `updated_at` when the tier is not the expected value. That silently changes the record if configuration drift occurs, contrary to the no-automatic-mutation invariant.

Draft [PR #204](https://github.com/MSJ1708/shoir-ie/pull/204), on branch `fix/protect-master-admin-config-20261026`, based on staging SHA `9e3899d6f5147584cf27585d946fa7b5d18d92d5`, changes source code only:

- It removes the login-time account update.
- It checks the reserved administrator's role, tier, active flag, and UTC expiry through a pure read-only helper.
- It refuses to issue the normal administrator session if that protected configuration is inconsistent, returning a generic manual-review response instead of repairing the account.
- It adds synthetic Deno tests for canonical and drifted invariant values and adds a Deno test step to `.github/workflows/shoir-validation.yml`.

The staging and production records were verified read-only to each contain exactly one account matching the expected invariant. The test does not sign in as or mutate the real protected account. Exact-head CI had not completed when this report was updated: the PR run [40386711214](https://github.com/MSJ1708/shoir-ie/actions/runs/40386711214) was queued and push run [40386644642](https://github.com/MSJ1708/shoir-ie/actions/runs/40386644642) was in progress. **PR #204 is not yet tested/verified and remains draft.** No deployed function, database, account, session, secret, or subscription was changed.

### Release impact

These drafts are intentionally separate: #203 covers workbook output safety; #204 covers protected administrative state integrity and Edge Function test coverage. Neither has been merged or deployed. No production or staging environment state has been altered in this execution.

**Disposition remains HOLD.** Current engineering evidence improves but does not eliminate the staging/production migration and function-version mismatch, hosted Streamlit revision uncertainty, unverified branch-protection enforcement, broader feature acceptance gaps, backup/restore evidence, provider connection requirements, or qualified Saudi legal/commercial approval.
