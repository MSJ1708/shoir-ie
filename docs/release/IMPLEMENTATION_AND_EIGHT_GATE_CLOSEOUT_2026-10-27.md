# Shoir-IE — Implementation Disposition and Eight-Gate Closeout

**Assessment date:** 27 October 2026  
**Decision:** **HOLD / NO-GO** for production deployment and paid commercial launch.  
**Purpose:** Current disposition of open PR recommendations, exact commit evidence, and release gates. This is not legal/security certification or production approval.

## Executive result

Implement recommendations selectively on clean current branches. Do not merge every historical PR: multiple open PRs duplicate functionality or contain stale stacks that should only be used as patch sources.

- **Main** is at 2ef44057f84162389d39998e922b505dcfe4d3e9. Its latest validation test job succeeded, but live-deployment-smoke was skipped.
- **Staging** is at 0558c23d59a3f0b79558a8d3407869d0238aceaf. A validation test passed, but latest hosted smoke and authenticated release-gate jobs were skipped.
- **PR #215** is the clean staging implementation candidate, head 0c0b8117c351d886c23134b6b077dab82945496e. Its current exact-head checks were queued at the time of assessment; hosted smoke was skipped.
- **PR #216** consolidates main-branch authentication and Streamlit security changes, head 5ec46249dddc096bf7efecf8d9cd5fc879db8ee9. It remains draft pending exact-head validation and review.
- **PR #217** ports complete PDF/PPTX exports to a clean main-based branch, head 231001c7b985ab34c110060df19e6c77fd708fa5. Test/security/engine jobs were queued or in progress; hosted smoke was skipped. Do not merge before checks pass and rendered artifacts are reviewed.
- The 100-target matrix classifies **98 IMPLEMENTED_NEEDS_VALIDATION, 2 EXTERNAL_CONFIGURATION_REQUIRED, and 0 VERIFIED_WORKING**. These are implementation classifications, not a product pass rate.
- Current release evidence reports production persistence Edge Function v8 versus staging v10, different deployed source hashes and migration histories. Production's login path still has reserved-admin auto-repair logic. Do not deploy staging v10 directly or replay the historic referral/legal migration in production.
- GitHub reports main and staging as protected. Reading detailed protection policy returned HTTP 403; the rulesets listing was empty. A repository owner must verify saved required-check and review rules in GitHub settings. The protected flag is not proof of the required-check configuration.

## Current automated evidence

| Candidate | Exact commit | Observed result | Evidence / limitation |
|---|---|---|---|
| Main | 2ef44057f84162389d39998e922b505dcfe4d3e9 | Validation test succeeded; hosted smoke skipped | [Main validation](https://github.com/MSJ1708/shoir-ie/actions/runs/40492293278) is not proof of the deployed app |
| Staging | 0558c23d59a3f0b79558a8d3407869d0238aceaf | Validation test succeeded; hosted smoke skipped | [Staging validation](https://github.com/MSJ1708/shoir-ie/actions/runs/40491846643) |
| Authenticated staging gate | Earlier candidate only | Current gate skipped | [Run 40486542492](https://github.com/MSJ1708/shoir-ie/actions/runs/40486542492); not an acceptance pass |
| PR #215 | 0c0b8117c351d886c23134b6b077dab82945496e | Engine, platform, security and validation jobs queued; smoke skipped | [PR #215](https://github.com/MSJ1708/shoir-ie/pull/215) |
| PR #217 | 231001c7b985ab34c110060df19e6c77fd708fa5 | Test/security/engine jobs queued or in progress; smoke skipped | [PR #217](https://github.com/MSJ1708/shoir-ie/pull/217); exact-head export artifact not accepted |

A historical authenticated staging gate passed on an earlier candidate: [run 40369188234](https://github.com/MSJ1708/shoir-ie/actions/runs/40369188234) reported 24/24 backend cases, 96/96 module-route/default-state render cases, and 7/7 browser-shell/Excel/logout checks. This is not a fresh pass for PR #215 or production source.

## Open PR recommendation-by-recommendation disposition

“Ported into candidate” means included in a branch for validation, not merged, deployed or verified.

| PR | Recommendation | Disposition |
|---|---|---|
| [#218](https://github.com/MSJ1708/shoir-ie/pull/218) | Safe main legal/referral schema migration, current policy-version approval trigger, preservation tests and migration-recovery runbook | New draft on main-based branch. Exact-head checks are queued. Do not merge/deploy until legacy migration-ledger reconciliation and isolated preservation/restore rehearsal receive independent review. |
| [#216](https://github.com/MSJ1708/shoir-ie/pull/216) | Fail-closed protected-admin invariant plus Streamlit CORS/XSRF/host restrictions on main | Primary main security consolidation. Review and test; do not deploy alone while production schema/function parity is unresolved. |
| [#215](https://github.com/MSJ1708/shoir-ie/pull/215) | Clean staging integration of focused methods, Facility Layout provenance/cost evidence, T065 authorization, mobile fix and staging CI wiring | Primary staging candidate. Require exact-head CI, authenticated gate, isolation and workbook acceptance. |
| [#214](https://github.com/MSJ1708/shoir-ie/pull/214) | CORS and host allowlists on main | Duplicate source scope consolidated into #216; do not merge separately. |
| [#213](https://github.com/MSJ1708/shoir-ie/pull/213) | Stop reserved-admin login-time mutation | Consolidated into #216; do not merge separately. |
| [#212](https://github.com/MSJ1708/shoir-ie/pull/212) | Mobile-only public tabs and clipping smoke | Selectively ported into #215. Test narrow viewports on hosted staging. |
| [#211](https://github.com/MSJ1708/shoir-ie/pull/211) | Release evidence and eight closeout gates | Keep as documentation/evidence track; record only verified dated results. |
| [#208](https://github.com/MSJ1708/shoir-ie/pull/208) | T006, T020, T037, T039, T044, T046, T060, T074, T080, T094, T097 and T099 methods | Selectively ported into #215. Original stack had four reported failures and stale ancestry; do not merge wholesale. |
| [#199](https://github.com/MSJ1708/shoir-ie/pull/199) | Live release/database parity recheck | Historical only; superseded for current state by #211 and this dated report. |
| [#191](https://github.com/MSJ1708/shoir-ie/pull/191) | T006 recovery, T020 lineage and T039 registry classification | Covered selectively in #215. Port only a demonstrated missing behavior. |
| [#189](https://github.com/MSJ1708/shoir-ie/pull/189) | Staging release-gate validation on older candidate | Superseded by #215; old runs are not final acceptance. |
| [#188](https://github.com/MSJ1708/shoir-ie/pull/188) | T046 RNLE ergonomics screening | Ported into #215; limited screening, not certified ergonomic assessment. |
| [#184](https://github.com/MSJ1708/shoir-ie/pull/184) | T044 RCM and responsive smoke fixes | RCM overlaps focused engine work; distinct mobile behavior was ported through #212 to #215. Do not merge stale stack. |
| [#182](https://github.com/MSJ1708/shoir-ie/pull/182) | Nine focused engineering methods | Shared targets are covered by #215 unified engine/Workbench; validate method-level behavior and port only gaps. |
| [#181](https://github.com/MSJ1708/shoir-ie/pull/181) | 100-tool workbench expansion | Selected Facility Layout improvements ported into #215: missing reason-column safety, data origin, weighted flow distance, explicit cost-rate handling and workbook evidence sheets. |
| [#180](https://github.com/MSJ1708/shoir-ie/pull/180) | Eight more engineering tools | Earlier wave overlaps current engine; validate unique methods rather than merging wholesale. |
| [#179](https://github.com/MSJ1708/shoir-ie/pull/179) | Unit converter and fail-closed entitlements | Verify whether unit-converter behavior is already covered; keep canonical tier checks fail-closed. |
| [#178](https://github.com/MSJ1708/shoir-ie/pull/178) | Registry, limited engines and matrix | Older competing stack; use current registry/matrix and #215. |
| [#175](https://github.com/MSJ1708/shoir-ie/pull/175) | Grouped library and tier policy | Older competing library implementation; reconcile only genuinely unique UX. |
| [#174](https://github.com/MSJ1708/shoir-ie/pull/174) | Grouped 100-tool hub | Superseded candidate; do not merge alongside current Workbench registry. |
| [#173](https://github.com/MSJ1708/shoir-ie/pull/173) | Workbench and fail-closed entitlement foundations | Superseded candidate; retain canonical tier tests/current shell. |
| [#172](https://github.com/MSJ1708/shoir-ie/pull/172) | Old 100-tool tranche | Superseded audit branch; validate relevant methods against #215, not stale ancestry. |
| [#170](https://github.com/MSJ1708/shoir-ie/pull/170) | Beta legal notice, consent and referral attribution | Do not publish/merge unchanged. Use safe additive migration route from #205 but require compatibility review and qualified Saudi legal/privacy review. Attribution is not a rewards programme. |

### Previously merged staging recommendations that still require release validation

- **#202 — PDF/PPTX completeness:** merged on staging. Earlier artifact review flagged PDF width/readability and PowerPoint continuation-row visibility. [PR #217](https://github.com/MSJ1708/shoir-ie/pull/217) ports the correction to main; its exact-head artifact is not accepted yet.
- **#203 — XLSX formula/URL injection safeguards:** retain and re-test hostile synthetic strings on relevant export/import paths.
- **#205 — non-destructive legal/referral schema path:** do not replay historic migration that rewrites existing identifiers/timestamps. Production needs an additive reviewed migration and preservation/restore rehearsal.
- **#206 — admin and Streamlit security:** integrated on staging; production source-level correction remains pending via #216.
- **#207 — SAP/Oracle adapter foundation:** read-only adapter contract/specification only. No live provider transport, credentials, customer tenant, sync or writes are proven; do not market as connected.
- **#210 — launch, PDPL, pilot, rollback and legal templates:** documentation only; templates are not sign-offs or test evidence.

## Eight final closeout gates

### Gate 1 — Reconcile recommendations into clean supported PRs
**Status: IN PROGRESS.** Use #215 for staging code, #216 for main security, #217 for main export completeness and #211 for release evidence. Keep superseded branches as patch sources. Every accepted method needs tests and stable tool/permission coverage.

**Evidence required:** disposition table, current-base diff review, conflict-free branch, reviewer approval and exact candidate SHA.

### Gate 2 — Exact-head automated checks
**Status: NOT PASSED for current candidates; jobs queued/in progress.** Complete tests, engine regression, platform tests and security/quality on the exact head. Fix failures on that candidate and rerun. Confirm no required job is skipped.

**Evidence required:** successful completed checks on each exact head, run IDs and a repository-owner-verified saved branch-protection policy listing required checks/reviews.

### Gate 3 — Hosted browser smoke and authenticated staging
**Status: BLOCKED / NOT RUN on current candidate.** Latest hosted smoke jobs are skipped. Run the public app on desktop/mobile and verify deployed branch/entry point. Then run the authenticated gate with disposable shoir-e2e-* staging accounts and synthetic data only; never use the reserved administrator. Test consent, account approval/decline, expiry/renewal, exports and save/reload/re-login.

**Evidence required:** green hosted smoke on verified URL/entry point, authenticated release-gate artifact on the exact candidate, sanitized logs/screenshots and explicit skipped/unsupported probes.

### Gate 4 — Authorization, workspace isolation and persistence
**Status: NOT ESTABLISHED for final candidate.** Test two independent users/workspaces across all six tiers, unknown tier/tool, expired/revoked session, direct route/action and cross-workspace list/read/insert/update/delete/export/object-reference attempts. Test save/reload/re-login and fail-closed denied/stale-policy writes.

**Evidence required:** sanitized two-user negative tests, RLS/RPC and actor/workspace ownership assertions, tier-route-action matrix, persistence/re-login and denied-write results. No production data or account probes.

### Gate 5 — Calculation correctness and truthful tool readiness
**Status: BLOCKED for commercial claims.** Matrix remains 98 needing validation, two requiring external configuration and zero verified-working. For each paid-pilot tool, test against independent references, units, invalid/missing/nonfinite values, boundaries, tolerances, infeasible/timeout/error outcomes and limits. Label measured/imported/edited/simulated/AI/synthetic results separately; never claim a screening is certification or a heuristic is globally optimal.

**Evidence required:** per-tool acceptance row with stable ID, exact SHA, reference source, expected/actual tolerance, boundary tests, entitlement/persistence/export/provenance results, limitations and named reviewer role/date. ROI claims require measured baseline/post-state, cost, dates, provenance and human review.

### Gate 6 — PDF/PPTX/XLSX/ZIP integrity and visual output
**Status: PASS for the exact-head synthetic PDF/PPTX pagination/rendering check on PR #217; PARTIAL for the full export/import release gate.** On SHA `231001c7b985ab34c110060df19e6c77fd708fa5`, validation run [40496541791](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541791), platform tests [40496541571](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541571), and engine regression [40496541634](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541634) passed. The synthetic PDF has 3 landscape A4 pages; the PowerPoint has 10 table slides plus a title slide and renders to 11 pages. All 67 unique row markers survived both renders. A human visual inspection of all 3 PDF pages and 11 PPTX render pages found no visible missing rows or clipping, with full-size checks on representative first/middle/final pages. Artifact ZIP digest and output hashes are recorded above. This acceptance is scoped to these exact-head synthetic PDF/PPTX artifacts; hosted export parity is not established because remote smoke is skipped. XLSX/ZIP hostile-content tests, full workbook round-trip and malformed/empty/oversized-input acceptance remain separate work.

**Evidence still required:** complete XLSX/ZIP parsing/round-trip, hostile formula/URL input tests for every relevant path, malformed/empty/oversized-input behavior, and verification on the final candidate after any subsequent code changes. Do not carry this PASS to a different SHA without rerunning artifact validation.

### Gate 7 — Production/staging parity, migration and recovery
**Status: BLOCKED; no production rollout authorized.** Draft [PR #218](https://github.com/MSJ1708/shoir-ie/pull/218) now prepares an additive schema/guard path and a disposable preservation test, but its checks are queued and its migration-ledger reconciliation/backup/restore rehearsal are not approved or complete. Evidence reports production persistence Edge Function v8 versus staging v10, mismatched source hashes and different migration histories. Production lacks staging legal-consent/referral schema, and production login still auto-repairs reserved-admin state while staging fails closed. Do not deploy staging v10 directly or replay the historical data-rewriting migration. Build app/schema/RPC/Edge compatibility manifest; review additive migration; rehearse preservation, backup/restore and partial-deployment rollback on an isolated target.

**Evidence required:** exact app/DB/Edge hashes, migration diff, approved forward/rollback plan, successful verified restore, preservation proof, exact-candidate staging gate, signed change window, postflight and explicit release-owner approval. No production mutation is included here.

### Gate 8 — Operator, Saudi legal/privacy, IP, billing and support
**Status: BLOCKED; actual operator facts and qualified review required.** Verify contracting person/entity, commercial registration where applicable, official address/contact, price/currency/term/tax/refund/subscription rules and invoice/payment owner. Get qualified Saudi review of e-commerce disclosures, Terms, privacy/PDPL, transfer safeguards, retention/deletion, refunds, cancellation and complaints. Confirm actual providers/regions and data flows across DB, files, logs, backups, AI/Copilot, support and payment proofs. Generate SBOM, review licenses/notices and asset/contributor rights, and record trademark/name search. Keep STC Pay/manual payment status truthful; do not imply automatic activation. Assign role owners for support, privacy requests, incident response, restore and launch approval.

**Evidence required:** verified operator and price/terms matrix; counsel/privacy sign-off; approved live policy/version screenshots; data/provider/region/transfer inventory; tested data-subject request, retention/deletion and incident runbook; SBOM/license/asset register; invoice/payment/refund/renewal evidence; support/monitoring/restore runbooks; dated accountable-owner GO decision.

## Addendum — latest exact-head recheck, 27 October 2026

This addendum supersedes earlier candidate SHA/check-status details above where they conflict.

- **PR #215 staging candidate** now heads `d96abd66ab325fdba5ae4a5f25e8f736c5be7396`. I also changed its workflow so a push or manual dispatch on `staging-e2e-20261019` runs the read-only hosted public-shell smoke against `https://shoirieverified.streamlit.app/`; main/audit flows keep the production URL. These current PR checks are newly queued (5 pending) and the pull-request-context smoke jobs are skipped by design; the staging-targeted probe can execute after a staging push or a manual staging dispatch. No candidate PASS or hosted staging result is established yet.
- **PR #218 safe legal/referral schema candidate** is draft at `0866687b12443ec9237547ee65f8f02ed4630fc1`, based on `main`. It adds the additive safe migration `20261026110000`, a current-policy approval guard `20261027120000`, the staging migration-recovery runbook, a source-inventory check, and a disposable PostgreSQL test that seeds synthetic codes/timestamps and confirms the safe migration preserves them while PostgreSQL rejects normalized duplicates. Latest head `0866687b12443ec9237547ee65f8f02ed4630fc1` has 7 queued checks and 2 hosted-smoke jobs skipped as of the last poll; no CI pass is established yet. Latest check overview: [commit checks](https://github.com/MSJ1708/shoir-ie/commit/0866687b12443ec9237547ee65f8f02ed4630fc1/checks). Production preflight showed 5 accounts and 0 nonblank referral codes (aggregate only). The normal `db push` is still unsafe without an approved ledger-reconciliation plan because the current source tree tracks historical migration IDs `20261021130000`, `20261022110000`, and `20261023130000` that production has not recorded. No migration or function was deployed.
- **PR #216 security candidate** originally failed the test and security-quality jobs for one shared regression-test defect: the dependency test filtered every line beginning with `streamlit`, so it mistakenly included the separate package `streamlit-folium`. Application compile completed and the test run reported 978 passed, 2 skipped, 1 failed; the failed assertion was in `tests/test_streamlit_security_config.py`. An initial selector adjustment to `startswith("streamlit=")` was insufficient for the declared `streamlit>=1.61,<2` requirement. I then changed the test to recognize the version operators (`>`, `=`, `<`, `!`) after the exact package name while excluding `streamlit-folium`. Latest head: `5b3438b9a0f74cc1c7a29848e59989e7c15c456f`. The new exact-head checks are queued, not passed; hosted smoke remains skipped. Re-read the exact-head checks after completion.
- **PR #217 export candidate** remains at `231001c7b985ab34c110060df19e6c77fd708fa5`. All main candidate validations now completed successfully: engine regression [40496541634](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541634); platform tests [40496541571](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541571); exact-head validation/render/local-browser smoke [40496541791](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541791); full test suite [40496541818](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541818); and security/quality [40496541876](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541876). Both full regression-suite runs reported **980 passed, 2 skipped, 71 warnings**. The validation generated and rendered the exact-head synthetic exports, checked all 67 row markers, performed Python compile/module/top-level import checks, and passed local public-shell browser smoke. Artifact `shoir-ie-report-export-validation` ID `12731026975`, ZIP SHA-256 `640c3491adcee8f7c11d0fc0df8402a7b4f6d71abb6a9c588f401be17e8d6ffd`; inside it, PDF SHA-256 `1aaf1b7b3e1b899acf19464e90551164c9ae40248b4569084c1885e5e9c7b84f` (3 landscape A4 pages) and PPTX SHA-256 `dc83f4dfb17c06b533a962f990323d277a514b41a0f696ab84fa53a4e3b77f7e` (title + 10 table slides, rendered to 11 pages) contain all `ROW-001` to `ROW-067` markers. All 3 PDF pages and all 11 rendered PowerPoint pages were inspected using contact sheets, with full-size spot-checks; no visible clipping or missing continuation rows were observed. Local runtime artifact `12731032015` (SHA-256 `dd81fa595cfc31fc55ff2d6e2a9edc8c153fcea2ceb99f78b3c454faa168cd4e`) reports PASS at desktop 1440×1000 and mobile 390×844; HTTP 200, no horizontal overflow or uncaught JavaScript errors, and both public registration and module-explorer tabs pass. It explicitly says authenticated checks were NOT RUN because authorized CI credentials were not supplied. The remote hosted deployment-smoke jobs remain skipped. One redundant exact-SHA `test` check at [run 40496522281](https://github.com/MSJ1708/shoir-ie/actions/runs/40496522281) was still queued at the last poll; PR #217 is kept draft until the redundant queue/check state is cleared and review is complete.
- **PR #211 evidence branch** now includes this disposition document (commit `8a68bb2155247cdc4715eb3f404c2b0c69ea2c32`). Its validation tests were queued and hosted smoke was skipped after this commit.

## Latest workflow wiring change — 27 October 2026

PR #215 received commit `d96abd66ab325fdba5ae4a5f25e8f736c5be7396`, which enables the hosted public-shell smoke on staging-branch pushes and manual workflow dispatches on `staging-e2e-20261019`, and adds a regression test in `tests/test_hosted_smoke_workflow_contract.py` for that routing. It directs those events to `https://shoirieverified.streamlit.app/`, while main and audit flows remain pointed at production. This makes a post-push/manual staging availability probe possible without probing production from the staging branch. It does not automatically run from the open PR event, and it does not establish that Streamlit finished deploying the triggering SHA. Exact-head CI has restarted on this latest head and is queued; a staging push/manual dispatch and authenticated gate remain outstanding.

## Read-only Supabase control-plane recheck — 27 October 2026

I re-read project metadata, migration history, the deployed `shoir-persistence` Edge Function inventory/source, selected schema metadata, and Supabase Advisors through the connected Supabase tools. No SQL changes, deployments, or user/account mutations were performed.

| Check | Production (`gcsamrdaeraxieaagsta`) | Staging (`hfhrosthswcybccepmak`) |
|---|---|---|
| Project state | `ACTIVE_HEALTHY` | `ACTIVE_HEALTHY` |
| Database region | `eu-central-1` | `eu-central-1` |
| Deployed `shoir-persistence` | ACTIVE, version 8 | ACTIVE, version 10 |
| Deployed source SHA-256 | `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d` | `5605d40e61feac6d010e7e1097565a7090bdf3325c862cc09de32af650b5a232` |
| Migration history count | 14 | 17 |
| Consent column count on `shoir_subscription_requests` | 0 of 6 | 6 of 6 |
| `public.shoir_referrals` | Absent | Present |
| Referral table grants to `anon`/`authenticated` | None (table absent) | None |
| Referral RLS policies | Table absent | 0 (RLS enabled) |

Source inspection confirms production v8 still contains login-time tier/updated_at mutation for the reserved administrator and does not contain referral-handling code. Staging v10 contains a fail-closed protected-admin check and referral-handling code. This is a live compatibility mismatch, not merely stale documentation.

Supabase Security Advisors returned no security lint rows for production and one informational `rls_enabled_no_policy` lint for staging's `public.shoir_referrals`. The migration and metadata show this table has RLS enabled and no direct table grants to `anon` or `authenticated`, consistent with intended server-only access. Keep that access model explicit and retain the advisor finding as a tracked intentional exception only after confirming every caller runs through reviewed server logic. Do not “fix” this by adding public grants or broad policies.

Performance advisors reported unused-index informational findings (16 in production, 19 in staging). Do not drop indexes based on this snapshot alone; it is not enough workload evidence to establish safe removal.

These direct checks strengthen the Gate 7 NO-GO rationale. Follow the current Supabase guidance to verify function and migration deployments as one controlled change; project health or a successful deployment operation alone is not proof of schema/application compatibility. Reference: [Supabase deployment guide](https://supabase.com/docs/guides/deployment) and [database migrations guide](https://supabase.com/docs/guides/local-development/database-migrations).

## Final recommendation

**NO-GO for production deployment or paid general availability today.** Keep beta/manual-payment boundaries and synthetic-only test data. Do not claim 100 verified tools, live SAP/Oracle connectivity, validated savings, legal compliance or current hosted staging acceptance without evidence.

Next: finish exact-head checks and visual artifact review for #217; finish exact-head validation of #215 and #216; rerun hosted smoke and authenticated staging acceptance on the exact accepted staging candidate; reconcile production schema/Edge compatibility and complete backup/restore rehearsal; and obtain operator plus qualified Saudi legal/privacy sign-off. Only the accountable release owner should record a dated GO after every applicable gate passes.

No production deployment, database migration, Edge Function deployment, billing change, public policy publication, or reserved-administrator login/mutation was performed for this assessment.

## Fresh execution snapshot — 27 October 2026, approximately 12:18 UTC

This addendum supersedes earlier candidate-head and queue-status statements where they differ. It is evidence only, not a release approval. All database checks below were read-only aggregate/schema/privilege checks; no customer records were selected, no administrator login was attempted, and no database/function/host configuration was changed.

### Git branches and enforcement metadata

| Resource | Exact observed state | Result |
|---|---|---|
| `main` | `2ef44057f84162389d39998e922b505dcfe4d3e9` | Baseline confirmed |
| `staging-e2e-20261019` | `0558c23d59a3f0b79558a8d3407869d0238aceaf` | Baseline confirmed |
| Main branch metadata | Protected = true; required status-check contexts/checks arrays are empty; branch-protection detail endpoint returned 403 to the connected integration | BLOCKED: owner must verify/configure named required checks and review requirements |
| Staging branch metadata | Protected = true; enforcement level reported `off`; required status-check contexts/checks arrays are empty | FAIL for a dependable staging release gate until owner configures and verifies enforcement |
| Repository rulesets | Empty array | No repository ruleset evidence |
| Reviews on PRs #211, #215, #216, #217 and #218 | No submitted review records returned | Independent reviews remain outstanding; no self-approval was performed |

### Exact-head CI evidence

| Candidate | Exact head / relevant runs | Current status and limitation |
|---|---|---|
| [PR #217 — PDF/PPTX completeness](https://github.com/MSJ1708/shoir-ie/pull/217) | `231001c7b985ab34c110060df19e6c77fd708fa5`; [validation 40496541791](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541791), [platform tests 40496541571](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541571), [engine regression 40496541634](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541634), [tests 40496541818](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541818), [security/quality 40496541876](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541876) | PASS for those five exact-head CI runs. The hosted live-deployment-smoke job is SKIPPED, not passed. PR is open and has no review record in the connected review query. Existing PR evidence states its synthetic PDF/PPTX artifacts preserved all 67 row markers and all 14 rendered pages were visually inspected; this is not live-hosted acceptance. |
| [PR #216 — auth, Streamlit and persistence CORS hardening](https://github.com/MSJ1708/shoir-ie/pull/216) | Latest head `28516cbf1556d147f25479bd01515ed01e6c6775`; includes exact-origin CORS restrictions and regression tests. Current jobs: [tests 40503028241](https://github.com/MSJ1708/shoir-ie/actions/runs/40503028241) and [Platform Tests 40503028222](https://github.com/MSJ1708/shoir-ie/actions/runs/40503028222) IN PROGRESS; [validation 40503027970](https://github.com/MSJ1708/shoir-ie/actions/runs/40503027970), [Edge Function verification 40503028120](https://github.com/MSJ1708/shoir-ie/actions/runs/40503028120), [engine regression 40503028127](https://github.com/MSJ1708/shoir-ie/actions/runs/40503028127), [security/quality 40503028101](https://github.com/MSJ1708/shoir-ie/actions/runs/40503028101) QUEUED. | NOT YET PASSED on the latest head. Prior green runs were for old SHA `5b3438b...` and must not carry over. Hosted smoke is SKIPPED. PR remains draft, undeployed, and awaits independent security review. |
| [PR #218 — safe legal/referral migrations](https://github.com/MSJ1708/shoir-ie/pull/218) | `0866687b12443ec9237547ee65f8f02ed4630fc1`; [validation 40499158757](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158757) PASS; [engine regression 40499158851](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158851) PASS; [transaction contract 40499158915](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158915) PASS. | [tests 40499158841](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158841) and [Platform Tests 40499158867](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158867) IN PROGRESS; [security/quality 40499158822](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158822) QUEUED. Hosted smoke is SKIPPED. No production mutation is authorized; require independent DB/security review, duplicate-code preflight and preservation/restore rehearsal. |
| [PR #215 — clean staging integration](https://github.com/MSJ1708/shoir-ie/pull/215) | Latest head `701c5ee0c167df35539bfba70ac751b45dd0e5df`; [validation 40503170743](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170743) and [tests 40503170856](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170856) QUEUED; [engine regression 40503170787](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170787) IN PROGRESS; [security/quality 40503170729](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170729) QUEUED. | NOT YET PASSED on latest head. Previous head `d96abd6...` security/quality run [40499245211](https://github.com/MSJ1708/shoir-ie/actions/runs/40499245211) failed one AppTest assertion because it requested the wrong result key; commit `701c5ee...` changes only that key to the canonical `mean_difference` while preserving expected value −6. Awaiting exact-head reruns. Hosted smoke is SKIPPED and authenticated lifecycle/tenant-isolation is NOT RUN. |
| [PR #211 — release evidence](https://github.com/MSJ1708/shoir-ie/pull/211) | Latest head `fb1de62f509824e588b1f47894b8014aab8840f9`; [validation 40502701316](https://github.com/MSJ1708/shoir-ie/actions/runs/40502701316) | Test QUEUED; hosted smoke SKIPPED. The follow-up commit below updates the table for subsequent source fixes, and its own CI is also not a substitute for hosted acceptance. |

### Fresh Supabase control-plane and aggregate checks

| Check | Production | Staging |
|---|---|---|
| Project ref / status | `gcsamrdaeraxieaagsta` / ACTIVE_HEALTHY | `hfhrosthswcybccepmak` / ACTIVE_HEALTHY |
| Database version | PostgreSQL 17.6.1.166 | PostgreSQL 17.11.0.003 |
| Applied migration records | 14, ending `20261019140600_atomic_subscription_request_decisions` | 17, including `20261021130000_shoir_beta_legal_referrals`, `20261022110000_enforce_beta_legal_acceptance`, and policy-version refresh record `20261025164602` |
| `shoir-persistence` | v8; SHA-256 `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d` | v10; SHA-256 `5605d40e61feac6d010e7e1097565a7090bdf3325c862cc09de32af650b5a232` |
| Reserved-admin invariant | Exactly one row matched the required role, Enterprise Plus $399 tier, active state and 2099-01-01 UTC expiry | Same aggregate result |
| Legal acceptance schema | Six acceptance columns absent from `shoir_subscription_requests` | Six expected acceptance columns present |
| `public.shoir_referrals` | Absent | Present, RLS enabled, no row policies; `anon` and `authenticated` lack SELECT while `service_role` has SELECT |
| Security advisor | 0 findings returned | 1 INFO finding: RLS enabled without policies on `public.shoir_referrals` |

The staging referrals advisor result is consistent with the documented server-only access design only if all sensitive operations truly remain server-mediated and the grants remain tightly restricted. Do not add broad client policies just to clear the informational advisor. Production/staging schema and function versions remain incompatible for a direct function rollout. The historic staging referral migration is not safe to replay blindly against production; preserve account identifiers, referral codes and timestamps with a reviewed forward-only plan and isolated restore rehearsal.

**Additional deployed-source finding, checked read-only on 27 October:** The live production persistence Edge Function v8 still returns `Access-Control-Allow-Origin: *` and contains login-time administrator tier auto-repair when the reserved account's tier differs. Its current aggregate invariant happens to hold, but the mutation path remains a source-level release blocker; no admin login was attempted. The live staging Edge Function v10 also still returns wildcard CORS, although it includes the reserved-admin fail-closed invariant and the four current legal-version checks. PR #216 now contains an exact-origin allowlist and CORS tests, but that candidate has not passed its current-head CI and has not been deployed. Thus the CORS/admin fix is **prepared, not active**.

The current staging app source, notice files, Edge Function and PR #218 approval trigger consistently use Terms `2026-10-21-beta-v1`, Privacy `2026-10-21-v1`, Refund `2026-10-23-v2`, and Cookie `2026-10-21-v1`. This verifies identifier consistency only, not legal adequacy. Direct hosted-app retrieval from this execution environment was unavailable; classify live browser acceptance as NOT CHECKED rather than assuming either failure or success. PR-triggered hosted smoke remains SKIPPED.

Production performance advisors also returned 16 informational unused-index findings. They are not proof of a defect and must be individually reviewed before any index removal. No migration, Edge Function deploy, SQL write, entitlement change, or production host change was performed during this check.

### Human gates that remain mandatory

1. Repository owner: configure and verify branch protection for `main` and `staging-e2e-20261019`, including the actual named CI checks, enforcement, and appropriate review requirements. Provide the saved settings or API evidence; gate cleared: controlled source promotion.
2. Independent code/security reviewer: review #216 and #217; do not self-approve. Provide submitted review records and exact reviewed SHA; gate cleared: source acceptance.
3. Independent DB/security reviewer and release operator: finish #218 exact-head checks, rehearse the safe additive migration on an isolated production-shaped database, prove preservation and backup restoration/rollback, inspect the final migration ledger, and approve a coordinated schema/function sequence; provide test logs, hashes and sign-off; gate cleared: data-preservation and recovery.
4. Staging operator: after the candidate is integrated into the protected staging branch and deployed by the authorized host, verify deployed commit/entry point and pass authenticated acceptance with two disposable users, tenant-isolation negative tests, persistence/re-login, exports and recovery. The public smoke is not a substitute; gate cleared: hosted beta acceptance.
5. Qualified Saudi legal/privacy professional and business owner: review PDPL/cross-border/data-processing facts, final legal documents, operator identity and contracting entity, IP/licence questions, subscription/refund/cancellation/payment terms and launch scope. Provide explicit sign-off and completed factual disclosures; gate cleared: legal and commercial approval.
6. Accountable release owner/platform operator: provide current backup and successful restore evidence, rollback window/operator and explicit production approval before any production database/function rollout; gate cleared: production authorization.

**Decision remains HOLD / NO-GO for both paid general availability and a controlled beta that depends on the unverified staging candidate.** A later controlled-beta GO can only cover the exact restricted pilot scope that passes all mandatory technical, hosted, tenant-isolation, recovery and approval gates. No such GO is authorized by this addendum.

### Artifact-level export inspection — completed 27 October 2026

Retrieved and independently inspected the artifact from [PR #217 validation run 40496541791](https://github.com/MSJ1708/shoir-ie/actions/runs/40496541791). Artifact [shoir-ie-report-export-validation (ID 12731026975)](https://github.com/MSJ1708/shoir-ie/actions/artifacts/12731026975) was ZIP-tested and matched the reported archive hash:

- ZIP SHA-256: `640c3491adcee8f7c11d0fc0df8402a7b4f6d71abb6a9c588f401be17e8d6ffd`
- Manifest source commit: `231001c7b985ab34c110060df19e6c77fd708fa5` (the exact PR #217 candidate)
- `synthetic_data_only=true`; no customer data in the artifact.
- PDF SHA-256: `1aaf1b7b3e1b899acf19464e90551164c9ae40248b4569084c1885e5e9c7b84f`; 3 A4 landscape pages. Re-parsed all page text and confirmed all expected identifiers ROW-001 through ROW-067 exist; page ranges were 001–023, 024–050, and 051–067. Rendered and visually inspected all three pages. Headers repeat on each page; no row clipping/omission observed. Text is compact for a 67-row synthetic table but legible at full page view.
- PPTX SHA-256: `dc83f4dfb17c06b533a962f990323d277a514b41a0f696ab84fa53a4e3b77f7e`; 16:9 presentation with one cover and 10 continued-table slides. Parsed the actual PPTX, verified 67 ordered row identifiers, a repeated Metric/Value header on every table slide, no shape extending outside slide bounds, and no missing rows. All 11 pre-rendered slide images were visually inspected; no clipping or hidden rows observed.
- The manifest's hashes for the PDF and PPTX independently matched the file bytes. ZIP contents passed integrity test.

**Export gate: PASS for this synthetic artifact and exact PR #217 source SHA.** This is not proof of export behavior on a hosted production/staging app or on arbitrary customer workbooks. The live-deployment-smoke job for the PR remains SKIPPED.

## Latest execution update — 27 October 2026, approximately 12:47 UTC

This is the latest exact-head update; earlier rows above describe the pre-hardening commits and must not be interpreted as checks for the current candidate heads. This update was assembled from live GitHub API and connected Supabase reads. No production deployment or write occurred.

### Current candidate heads and checks

| PR | Current exact head | Exact-head checks observed | Decision |
|---|---|---|---|
| [#215 staging/workbench/mobile integration](https://github.com/MSJ1708/shoir-ie/pull/215) | `701c5ee0c167df35539bfba70ac751b45dd0e5df` | [tests 40503170856](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170856) PASS; [engine regression 40503170787](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170787) PASS; [security/quality 40503170729](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170729) IN PROGRESS; [validation 40503170743](https://github.com/MSJ1708/shoir-ie/actions/runs/40503170743) IN PROGRESS, with another validation/test attempt queued; live smoke SKIPPED. | Partially validated; do not promote yet. |
| [#216 security, CORS, reserved-admin protection and SBOM workflow](https://github.com/MSJ1708/shoir-ie/pull/216) | `80ac709fb173d1ccc098c5346346abad653459cf` | Latest-head engine, Edge Function, tests and security/quality checks are QUEUED, with one test job IN PROGRESS; e.g. [security/quality 40504818823](https://github.com/MSJ1708/shoir-ie/actions/runs/40504818823), [Edge Function 40504818935](https://github.com/MSJ1708/shoir-ie/actions/runs/40504818935), [engine 40504819009](https://github.com/MSJ1708/shoir-ie/actions/runs/40504819009). Hosted smoke SKIPPED. | Not yet CI-passed; source fix prepared only, not deployed. |
| [#217 PDF/PPTX and XLSX export protections](https://github.com/MSJ1708/shoir-ie/pull/217) | `7c0ddde187c36c53e591c3742a5d770b1b0703f9` | New test, platform, engine and security/quality runs [40505702284](https://github.com/MSJ1708/shoir-ie/actions/runs/40505702284), [40505702266](https://github.com/MSJ1708/shoir-ie/actions/runs/40505702266), [40505702256](https://github.com/MSJ1708/shoir-ie/actions/runs/40505702256), [40505702421](https://github.com/MSJ1708/shoir-ie/actions/runs/40505702421), [40505702519](https://github.com/MSJ1708/shoir-ie/actions/runs/40505702519) are QUEUED. Hosted smoke SKIPPED. | The synthetic PDF/PPTX artifact inspection passes for source SHA `231001c...`; formula/URL defenses and the new five-test XLSX suite are committed to `7c0ddde...` but await CI. The earlier artifact PASS does not transfer to the new code SHA. |
| [#218 safe legal/referral migration](https://github.com/MSJ1708/shoir-ie/pull/218) | `0866687b12443ec9237547ee65f8f02ed4630fc1` | Validation [405? latest historical checks include 40499158757](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158757), tests [40499158841](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158841), platform tests [40499158867](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158867), engine regression [40499158851](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158851) and Postgres transaction contract [40499158915](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158915) PASS. Security/quality [40499158822](https://github.com/MSJ1708/shoir-ie/actions/runs/40499158822) remains QUEUED; live smoke SKIPPED. | Migration code tests partly PASS; not sufficient for production because security gate, independent review, duplicate-code preflight and restore rehearsal remain. |
| [#211 release closeout](https://github.com/MSJ1708/shoir-ie/pull/211) | Prior source head `bd1d3fbbd7f693d384b6f97db4c7dcf7c62e6d51`; this report update produces a new commit. | Latest observed report-validation runs [40504059868](https://github.com/MSJ1708/shoir-ie/actions/runs/40504059868) and [40504054219](https://github.com/MSJ1708/shoir-ie/actions/runs/40504054219) are QUEUED. The report cannot self-certify. | Awaiting the new documentation head's own CI. |

### Source changes prepared since prior snapshot

- **#216**: current branch contains exact-origin CORS enforcement, tests for allowlisted and rejected origins, insert-only reserved-admin metadata initialization (no password/role/tier/email repair of existing row), no local SQLite sync on reserved-admin login, no legacy affiliate-code rotation for `sho`, 2099-01-01 UTC expiry on insert-only local defaults, and CycloneDX generation for the *resolved Python CI environment*. None of these changes is deployed; current-head CI is queued/in progress. The SBOM is not a hosted-runtime inventory or a license clearance.
- **#215**: the original security/quality failure from prior SHA `d96abd6...` was traced to the test asking `run_hypothesis_test` for the wrong return key. Commit `701c5ee...` changes only the field key to `mean_difference`; expected value remains `-6`. On that exact head both the main test run and engine regression now PASS; security/quality and validation are still in progress.
- **#217**: commits `cee7ecbe1bb1b389c00987d5a4a883713b81a742` and `7c0ddde187c36c53e591c3742a5d770b1b0703f9` port the staging XLSX injection controls into the main-based export candidate: XlsxWriter formula/URL conversion disabled in export/persistence writers; formula-typed user strings literalized in data-only OpenPyXL reports; five regression tests for the affected paths. This is statically present but not test-passed yet. The prior PDF/PPTX artifact evidence is for earlier exact source SHA `231001c...`; regeneration is required if later code alters PDF/PPTX output behavior. The latest formula changes are XLSX-only, but final exact-head validation still applies.
- **#218**: source review confirms the safe proposed migration does not rewrite current affiliate codes or timestamps, unlike the earlier #170 migration. Still no production migration or Edge Function deploy occurred.

### CI queue evidence and limits

The latest-head PR checks created around 12:34–12:41 UTC were still queued at the latest read, while multiple unrelated historical PR runs remained queued or in progress. This is a verified backlog; the exact root cause (runner capacity, GitHub service delay or organization concurrency limits) is not available from permitted metadata. No rerun was forced because these checks were queued rather than failed and the connected GitHub integration does not expose a supported dispatch/cancel action. Continue to classify queued as NOT PASSED.

### Final status at this point

- **GO — controlled beta: NOT AUTHORIZED.**
- **GO — paid general availability: NOT AUTHORIZED.**
- Export artifact integrity for the synthetic old-head PDF/PPTX: PASS.
- Current-head XLSX formula/URL injection suite: NOT RUN to completion / QUEUED.
- Current-head CORS/admin source fix: NOT RUN to completion / QUEUED.
- Hosted application, desktop/mobile browser acceptance, authenticated two-user tenant-isolation, live save/reload/re-login and live download acceptance: NOT RUN in this execution.
- Production deployed CORS/admin mutation issues remain until #216 is reviewed, merged and deployed under explicit authorization.

The mandatory human actions at the end of this document remain unchanged: owner must enforce branch protection and named checks; independent security/code review; safe migration rehearsal and rollback/restore sign-off; authorized staging operator must run hosted acceptance with disposable accounts; Saudi legal/privacy counsel and operator must approve actual policies and business facts; release owner must authorize any production rollout.
