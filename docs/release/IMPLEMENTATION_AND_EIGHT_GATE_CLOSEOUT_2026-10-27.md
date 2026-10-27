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
**Status: PARTIAL; current candidate not accepted.** PR #217 ports paginated tables to main, limits PowerPoint continuation slides to seven data rows, creates exact-head synthetic artifacts, renders every slide and checks all 67 row markers in exported PDF and rendered PowerPoint PDF. Its checks have not passed yet; text extraction alone cannot confirm readability. Review every PDF page and PPTX continuation slide, especially boundaries 7/8, 14/15 and 21/22. Re-test hostile XLSX formula/URL strings and workbook/ZIP round trips.

**Evidence required:** source SHA + manifest SHA-256, PDF page/text checks, PPTX slide/table checks, rendered PNG for every slide, human visual-review note, XLSX/ZIP parsing/round-trip, malformed/empty/oversized-input results and no dropped/clipped rows. Keep #217 draft until reviewed.

### Gate 7 — Production/staging parity, migration and recovery
**Status: BLOCKED; no production rollout authorized.** Evidence reports production persistence Edge Function v8 versus staging v10, mismatched source hashes and different migration histories. Production lacks staging legal-consent/referral schema, and production login still auto-repairs reserved-admin state while staging fails closed. Do not deploy staging v10 directly or replay the historical data-rewriting migration. Build app/schema/RPC/Edge compatibility manifest; review additive migration; rehearse preservation, backup/restore and partial-deployment rollback on an isolated target.

**Evidence required:** exact app/DB/Edge hashes, migration diff, approved forward/rollback plan, successful verified restore, preservation proof, exact-candidate staging gate, signed change window, postflight and explicit release-owner approval. No production mutation is included here.

### Gate 8 — Operator, Saudi legal/privacy, IP, billing and support
**Status: BLOCKED; actual operator facts and qualified review required.** Verify contracting person/entity, commercial registration where applicable, official address/contact, price/currency/term/tax/refund/subscription rules and invoice/payment owner. Get qualified Saudi review of e-commerce disclosures, Terms, privacy/PDPL, transfer safeguards, retention/deletion, refunds, cancellation and complaints. Confirm actual providers/regions and data flows across DB, files, logs, backups, AI/Copilot, support and payment proofs. Generate SBOM, review licenses/notices and asset/contributor rights, and record trademark/name search. Keep STC Pay/manual payment status truthful; do not imply automatic activation. Assign role owners for support, privacy requests, incident response, restore and launch approval.

**Evidence required:** verified operator and price/terms matrix; counsel/privacy sign-off; approved live policy/version screenshots; data/provider/region/transfer inventory; tested data-subject request, retention/deletion and incident runbook; SBOM/license/asset register; invoice/payment/refund/renewal evidence; support/monitoring/restore runbooks; dated accountable-owner GO decision.

## Addendum — latest exact-head recheck, 27 October 2026

This addendum supersedes earlier candidate SHA/check-status details above where they conflict.

- **PR #215 staging candidate** advanced to `b00a7bcd8d89c86d239f7847467e31c30a7e0ffb`. Its latest visible exact-head checks remain queued (5 pending), and both live-deployment-smoke jobs are skipped. No candidate PASS is established.
- **PR #216 security candidate** originally failed the test and security-quality jobs for one shared regression-test defect: the dependency test filtered every line beginning with `streamlit`, so it mistakenly included the separate package `streamlit-folium`. Application compile completed and the test run reported 978 passed, 2 skipped, 1 failed; the failed assertion was in `tests/test_streamlit_security_config.py`. I corrected the package match on the same PR branch to require the exact `streamlit=` package spec. After correcting the selector to recognize package version operators while excluding `streamlit-folium`, the latest head is `5b3438b9a0f74cc1c7a29848e59989e7c15c456f`. The new exact-head checks are queued, not passed; hosted smoke remains skipped. Re-read the exact-head checks after completion.
- **PR #217 export candidate** remains at `231001c7b985ab34c110060df19e6c77fd708fa5`; at last check, 6 jobs were queued/in progress and 2 hosted-smoke jobs were skipped. No export artifact is accepted until the exact-head workflow finishes and all PDF pages / every PPTX slide are visually reviewed.
- **PR #211 evidence branch** now includes this disposition document (commit `8a68bb2155247cdc4715eb3f404c2b0c69ea2c32`). Its validation tests were queued and hosted smoke was skipped after this commit.

## Final recommendation

**NO-GO for production deployment or paid general availability today.** Keep beta/manual-payment boundaries and synthetic-only test data. Do not claim 100 verified tools, live SAP/Oracle connectivity, validated savings, legal compliance or current hosted staging acceptance without evidence.

Next: finish exact-head checks and visual artifact review for #217; finish exact-head validation of #215 and #216; rerun hosted smoke and authenticated staging acceptance on the exact accepted staging candidate; reconcile production schema/Edge compatibility and complete backup/restore rehearsal; and obtain operator plus qualified Saudi legal/privacy sign-off. Only the accountable release owner should record a dated GO after every applicable gate passes.

No production deployment, database migration, Edge Function deployment, billing change, public policy publication, or reserved-administrator login/mutation was performed for this assessment.
