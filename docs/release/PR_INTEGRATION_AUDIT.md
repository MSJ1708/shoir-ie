# Shoir-IE PR Integration Audit

**Audit captured:** 26 October 2026, using live GitHub metadata  
**Repository:** [MSJ1708/shoir-ie](https://github.com/MSJ1708/shoir-ie)  
**Initial baseline:** main at SHA 72e498d892b9eb088d34be940fc1f6d97b482c1a; superseded by the current recheck below.  
**Decision:** **NO-GO** for production release and paid launch on current evidence.

This report is an evidence snapshot and recommended disposition, not a claim that PRs were merged or blocked checks passed. Mainline already includes PR #183. All 14 open PRs below are still drafts.

## Executive findings

The main 100-target matrix has exactly 100 rows, with the following current status distribution:

| Matrix status | Count |
|---|---:|
| IMPLEMENTED_NEEDS_VALIDATION | 98 |
| FOUNDATION_ONLY | 0 |
| EXTERNAL_CONFIGURATION_REQUIRED | 2 |
| VERIFIED_WORKING | 0 |

A catalog of 100 entries is not evidence of 100 operational tools. Preserve the current shell and grouped Workbench; port unique methods, not competing registry foundations.

Current critical blockers:
1. Main is unprotected: GitHub reports protection disabled, required status contexts empty, and no rulesets.
2. On exact main SHA 72e498d892b9eb088d34be940fc1f6d97b482c1a, the unit/platform test job, engine regression, transaction contract, Edge Function verification, and security-quality checks pass, but the hosted public app smoke **fails**. The hosted app displays a startup compatibility error saying durable_account_store is missing edge_referral_summary. That function exists in the checked-in source at main (durable_account_store.py around line 628). This indicates a deployed-source/entry-point mismatch, not proof the source function is absent.
3. Staging validation passes on SHA 8b36e3737705867019b9cf29e603cfc37e7911e6, but authenticated release gate and hosted smoke are skipped, not passed.
4. PR #191 initially failed two Workbench AppTests. Latest head aa28683435b39fa45574da88e510728ae7a59b98 now passes validation and platform suites (each 930 passed, 2 skipped, 71 warnings), engine regression and security/quality. Top-level import and local runtime/browser checks passed in the validation workflow. Hosted live-deployment smoke remains skipped and authenticated staging acceptance has not run. The 71 warnings include Pandas future/deprecation and PuLP deprecation notices; they were not suppressed.

## 1. Verified baseline

| Item | State | Evidence |
|---|---|---|
| Repository/default branch | MSJ1708/shoir-ie; main | GitHub repository metadata |
| Main SHA | 72e498d892b9eb088d34be940fc1f6d97b482c1a; merge includes PR #183 | https://github.com/MSJ1708/shoir-ie/commit/72e498d892b9eb088d34be940fc1f6d97b482c1a |
| Main protection | protected=false; required contexts empty | https://api.github.com/repos/MSJ1708/shoir-ie/branches/main |
| Rulesets | Empty | https://api.github.com/repos/MSJ1708/shoir-ie/rulesets |
| Staging branch | staging-e2e-20261019 at 8b36e3737705867019b9cf29e603cfc37e7911e6 | https://github.com/MSJ1708/shoir-ie/tree/staging-e2e-20261019 |
| Main validation | test job PASS; hosted smoke FAIL | https://github.com/MSJ1708/shoir-ie/actions/runs/40273481812 |
| Main engine regression | PASS | https://github.com/MSJ1708/shoir-ie/actions/runs/40273481622 |
| Transaction contract | PASS | https://github.com/MSJ1708/shoir-ie/actions/runs/40273481653 |
| Edge Function verification | PASS | https://github.com/MSJ1708/shoir-ie/actions/runs/40273481518 |
| Security and quality | PASS | https://github.com/MSJ1708/shoir-ie/actions/runs/40273481507 |
| Staging validation | PASS for this workflow's test job | https://github.com/MSJ1708/shoir-ie/actions/runs/40273588613 |
| Staging authenticated release gate | SKIPPED / NOT RUN | https://github.com/MSJ1708/shoir-ie/actions/runs/40273588637 |
| Production or database mutation by this audit | None | Read-only baseline work; no production deployment, migration, payment or account operation was invoked |

The available GitHub integration cannot inspect the Streamlit Cloud configuration panel or enumerate the live Supabase migration and deployed Edge Function state. Therefore it does not certify the production/staging URL-to-branch binding, entry point, secret presence, database project, migration history or deployed function versions.

## 2. Open PR inventory and disposition

Every PR below is currently open and marked draft in live GitHub metadata. The metadata showed zero inline review comments and no requested reviewers. Approval state was not independently established for every PR; draft status alone is enough to prevent merging now. Check outcomes refer to the listed head SHA, not a hypothetical rebase. SKIPPED is not PASS.

| PR | Base → head (head SHA) | Merge state / exact-head checks | Unique scope and risk | Recommended disposition |
|---|---|---|---|---|
| [#170](https://github.com/MSJ1708/shoir-ie/pull/170) | main (base 3a73ada0…) ← legal-beta-referral-readiness-2026-10-21 (690ddc8e…) | DIRTY; test, Edge, engine, transaction, security PASS; hosted smoke SKIPPED | Versioned beta consent and neutral referral attribution; needs coordinated app/schema/Edge rollout and legal facts/review | Keep as a separate legal stream. Reconcile base and preserve unique consent/referral changes; stage only after exact-head checks. Do not represent implementation as legal clearance. |
| [#172](https://github.com/MSJ1708/shoir-ie/pull/172) | main (base c7bb3fcf…) ← audit/shoir-100-tools-20261023 (a4a8663b…) | DIRTY; test and security-quality FAIL; engine PASS; hosted smoke PASS on its run | Large 166-commit audit/tool stack; overlaps #183 and parent stack for #182 | Fix failures and port unique methods/changes only. Do not merge wholesale. Compare exact commit/file diffs with main first. |
| [#173](https://github.com/MSJ1708/shoir-ie/pull/173) | main (base 3a73ada0…) ← feat/100-tool-engineering-workbench-20261023 (39365314…) | DIRTY; test, engine and security PASS; hosted smoke SKIPPED | Earlier manifest, grouped Workbench and entitlement foundation; competes with #183/#174/#175/#178 | Supersede only after diff audit. Port any missing unique deny-path tests or engine changes; account for every unique change before closure. |
| [#174](https://github.com/MSJ1708/shoir-ie/pull/174) | main (base 3a73ada0…) ← feature/shoir-100-tool-hub-20261023 (149484e9…) | DIRTY; test, engine and security PASS; hosted smoke SKIPPED | Grouped hub and guarded calculators; duplicate foundation risk | Compare UI/method changes against main; port unique useful changes and keep one registry foundation. |
| [#175](https://github.com/MSJ1708/shoir-ie/pull/175) | main (base 3a73ada0…) ← feat/100-tool-workbench-and-closed-entitlements-2026-10-23 (6a3b2be6…) | DIRTY; test, engine and security PASS; hosted smoke SKIPPED | Alternative library and fail-closed tier policy | Verify six-tier policy and distinct Research Pack access in main; port missing negative tests and supersede only after an explicit unique-change inventory. |
| [#178](https://github.com/MSJ1708/shoir-ie/pull/178) | main (base c7bb3fcf…) ← feat/shoir-100-tool-implementation-2026-10-23 (e7397c74…) | DIRTY; test, engine and security PASS; hosted smoke SKIPPED | 71-file registry/matrix/engine stack, overlaps #183 and method waves | Use as a comparison source, not direct merge. Port missing methods, checks and documentation after ID-by-ID comparison. |
| [#179](https://github.com/MSJ1708/shoir-ie/pull/179) | main (base c7bb3fcf…) ← feat/100-tool-readiness-foundations-2026-10-24 (43bff782…) | DIRTY; test, engine and security PASS; hosted smoke SKIPPED | Fail-closed access foundations and unit converter; likely overlaps current registry/tier code | Verify main's direct denial behavior; port any missing converter or negative tests, then supersede only when unique changes are recorded. |
| [#180](https://github.com/MSJ1708/shoir-ie/pull/180) | main (base c7bb3fcf…) ← feature/shoir-100-completion-20261024 (5a12581d…) | DIRTY; test, engine and security PASS; hosted smoke SKIPPED | Eight focused methods T013/T017/T018/T019/T034/T070/T082/T084 | Port unique engines only; verify stable tool IDs, method/reference tests and tier gate without replacing current registry code. |
| [#181](https://github.com/MSJ1708/shoir-ie/pull/181) | main (base c7bb3fcf…) ← feat/shoir-100-tool-methods-wave-2026-10-24 (7723e28b…) | DIRTY; test, engine and security PASS; hosted smoke SKIPPED | Expanded method wave; overlapping foundations | Port unique methods after file-level comparison; reconcile IDs, tier minimums and method tests. |
| [#182](https://github.com/MSJ1708/shoir-ie/pull/182) | audit/shoir-100-tools-20261023 (base 0d4f4865…) ← audit/shoir-100-tool-continuation-20261025 (9ecfb9ed…) | DIRTY; test FAIL; hosted smoke PASS; no further exact-head checks returned in the check-run set | Nine tool workflows, stacked on #172 | Capture/fix exact test failure and port unique methods onto a main-based integration path; do not keep this dependency chain. |
| [#184](https://github.com/MSJ1708/shoir-ie/pull/184) | feat/shoir-100-tools-integration-20261025 (base a312da52…) ← feat/shoir-t044-rcm-current-base-20261025 (7af10bd0…) | DIRTY; test, engine and security PASS; hosted smoke SKIPPED | T044 limited RCM review register plus responsive smoke fixes | Reconcile stack and port the T044 workflow and responsive fixes; verify human review status, entitlement, persistence and browser behavior. |
| [#188](https://github.com/MSJ1708/shoir-ie/pull/188) | feat/shoir-100-tools-integration-20261025 (base c84565ba…) ← agent/shoir-100-rnle-ergonomics-20261025 (e8db67bd…) | DIRTY; test PASS; hosted smoke SKIPPED; no further checks returned for the current head | T046 single-task RNLE screening; requires scope boundaries and qualified review | Port only after formula/reference/boundary/domain review; retain the human-review warning, then run tier and browser checks. |
| [#189](https://github.com/MSJ1708/shoir-ie/pull/189) | staging-e2e-20261019 (base 19678321…) ← agent/shoir-100-release-gates-verify-20261025 (49f46bcf…) | DIRTY; validation, engine, platform, security, transaction and Edge PASS on that head; hosted smoke SKIPPED | Large staging/release stack, not a safe mainline merge | Keep staging-specific. The staging branch has since advanced; run authenticated gate on the exact final staging candidate and verify parity. Never merge this large stack blindly to main. |
| [#191](https://github.com/MSJ1708/shoir-ie/pull/191) | main (base 72e498d8…) ← feat/shoir-100-t006-recovery-20261026 (latest aa286834…) | prior head c1e6f657… had two AppTest failures; intermediate 28449466… resolved T020 but exposed a T006 Streamlit form-submission issue. On latest head aa28683435b39fa45574da88e510728ae7a59b98, validation, platform, engine and security/quality PASS; hosted smoke is SKIPPED and authenticated acceptance is NOT RUN. After retargeting to main, GitHub reports mergeable=true / clean; this is not release approval | T006 snapshot recovery, T020 dataset lineage and T039 status reconciliation | Keep draft for human review. Normal tool flows isolate persistence in AppTest; explicit negative tests assert failed-save rollback; all available exact-head automated workflows are green. Hosted smoke/authenticated staging proof remain outstanding. |

## 2A. Direct base/head comparisons (not just PR title or total historical commits)

GitHub compare results were obtained for the live head refs. Ahead/behind figures are relative to the named base, and file-level evidence below reflects the current comparison, not lifetime PR statistics.

| PR | Compare result | Residual file-level evidence / implication |
|---|---|---|
| #170 vs main | diverged; 47 ahead / 334 behind | 17 files differ, including app.py, durable_account_store.py, the persistence Edge Function, PostgreSQL SQL, two legal migrations, beta-referral tests and legal/privacy docs. High schema + Edge compatibility risk. |
| #172 vs main | diverged; 6 ahead / 174 behind | Only 3 residual files differ: one Workbench line, three tier-capability lines, and three target-engine-test lines. Review/fix these residual changes rather than treating the historical 166-commit chain as a requirement to merge. |
| #173 vs main | diverged; 49 ahead / 334 behind | Adds a competing shoir_100_tool_registry.py and shoir_100_tool_workbench.py, plus its matrix/report and tier changes. It is an alternative foundation, not a safe wholesale merge. |
| #174 vs main | diverged; 44 ahead / 334 behind | Adds shoir_100_tool_hub.py (782 lines), alternative matrix/report, tier-capability and facility-layout changes and dedicated tests. Review uniquely useful workflows; avoid adding a second competing hub. |
| #175 vs main | diverged; 20 ahead / 334 behind | Adds separate shoir_100_tool_registry.py (477 lines), shoir_100_tool_engines.py (289 lines), matrix/report and tests. Competes with the current registry. |
| #178 vs main | diverged; 268 ahead / 330 behind | Wide multi-engine stack and new pages/Engineering_Tool_Library.py (2,369 lines); changes Workbench, Copilot, Excel Studio, facility layout, persistence, tier rules and many engine/test modules. High regression/layout/access risk; port per-target, not wholesale. |
| #179 vs main | diverged; 33 ahead / 330 behind | Adds alternate registry, unit converter (190 lines), basic calculator (264 lines), facility-flow logic and deny-path tests. Compare each method against mainline equivalents. |
| #180 vs main | diverged; 36 ahead / 220 behind | Changes Workbench (+352 lines), shoir_target_engines.py (+1,287), registry and tests. Candidate for unique engine/test ports after method-by-method comparison. |
| #181 vs main | diverged; 82 ahead / 330 behind | Adds shoir_100_tool_methods.py (1,622 lines), shoir_100_tool_ui.py (625 lines), alternate registry/calculator/converter files and tests. Overlaps #179 and other foundations; split unique methods from alternative UI/registry. |
| #182 vs main | diverged; 69 ahead / 174 behind | Changes target engines (+1,168 lines), Workbench (+338), matrix/report, registry and workspace persistence. Stacked on #172 and has a failing test; port unique changes after fixing it from a main-based branch. |
| #184 vs main | diverged; 35 ahead / 101 behind | Changes three workflows, app.py (+47 lines), smoke script (+82), Workbench, target engines (+149) and tests. Protect CI semantics; review smoke assertions/workflow changes carefully. |
| #188 vs main | diverged; 39 ahead / 85 behind | Adds shoir_ergonomics.py (299 lines) and tests; modifies Workbench (+270), registry, tiers and matrix. T046 is distinct but requires domain/reference validation. |
| #189 vs staging | diverged; 317 ahead / 89 behind | Large staging stack. The diff removes 14 lines from authenticated-release-gate.yml, deletes staging credential-recovery/password-reset helpers and related tests, and changes account-provisioning/authenticated gate scripts. Do not merge without security review of every removal and exact staging acceptance. |
| #191 vs main | diverged; 47 ahead / 5 behind | Changes Workbench (+335 lines), target engines (+361), Workbench tests (+157), registry and implementation reports. It includes unique T006/T020/T039 work but must be reviewed as a multi-file feature, not merely a test-only change. |

These comparisons explain why historical commit counts and mergeable state alone do not define integration work. The right unit is the current base/head diff plus tests and dependencies. They also show #189 removes staging recovery code; a passing local test suite is not sufficient to accept those deletions.

### PR inventory count

- Functional/release-feature drafts captured in the original inventory: 14; the separate audit PR #192 adds a documentation-only draft.
- Open non-drafts in the original functional inventory: 0.
- PR #191 was retargeted from the old feature-integration base to main after compare confirmed its old base SHA is a parent of main. The current diff is 47 commits ahead / 5 behind across 11 files; GitHub reports mergeable=true / clean. PR #191 remains draft and was not merged.
- No feature PR was closed or merged by this audit.

## 3. Canonical integration and dependency graph

Main already merges PR #183. Its merge parents are c7bb3fcff54b6ce5de1ef0df2010fe3ef8029e9f and 800b86b77fea2148eed056bd37a24c4886f0e308; the latter is the base SHA reported by #191. Use current main as the release baseline, not old PR branch names or descriptions.

Recommended order:

1. Establish branch protection with required review, conversation resolution and exact CI checks. This requires repository-setting authority not exposed by the available operations; the current protection state remains a blocker.
2. Keep one canonical registry and policy in shoir_tool_registry.py, shoir_tier_capabilities.py, existing Workbench routes and the implementation matrix. Verify unique ordered IDs T001–T100; unknown tier, tool, unmapped route or protected action must deny. Keep Research Pack distinct from Enterprise Plus.
3. Compare #178 and overlapping #172/#173/#174/#175/#179/#180/#181 against main by commit and file; port only missing unique changes. Port #182 after removing its dependency on #172. Review/port #184 T044, #188 T046 and #191 T006/T020/T039 as small changes on the canonical mainline after their checks pass.
4. Keep #170's legal/consent work separately reviewed with schema + Edge + app compatibility. Keep #189 staging-specific and never merge its large stack wholesale to main.
5. Open a single release-candidate PR after unique changes pass exact-head CI, review, and authenticated staging checks.

## 4. Readiness gates

| Gate | Status | What closes it |
|---|---|---|
| PR audit | PARTIAL | Review full unique diffs/commits and record accepted/rejected items and replacement SHAs; no change may be silently lost |
| Branch protection | FAIL | Enable required review/status rules and prove them with a fresh settings/API read |
| Registry structure | PASS for row count only | Current matrix has 100 lines of tool data plus one header; verify uniqueness/order in CI |
| Tool operational evidence | FAIL | Current matrix count: 89 needs validation, 9 foundation only, 2 external configuration, 0 verified-working |
| Main automated CI | PARTIAL | Core tests, engine, transaction contract, Edge and security pass; hosted smoke fails |
| Production deployment parity | FAIL / BLOCKED | Verify actual Streamlit branch, commit and entry point plus deployed source; authorized rollout only with compatibility plan and rollback |
| Staging checks | PARTIAL | Validation passed; authenticated release gate and hosted smoke skipped |
| Authenticated acceptance | NOT RUN | Dedicated shoir-e2e-* account configuration and expected host; run manual authenticated gate on exact final candidate SHA; never use master admin |
| Tenant isolation / RLS / RPC | NOT established for candidate | Two-user server/database read/write/export denial, route/action denial, stale-session tests on matching deployed services |
| Imports/exports | NOT established for every advertised tool | Real XLSX/PDF/PPTX/ZIP download, reopen/parse and verify content, numbers, labels, warnings and provenance |
| Legal operator + Saudi review | BLOCKED | Confirm real contracting entity, registration and address; counsel review; never publish placeholders |
| PDPL operations | BLOCKED | Actual provider/region/data inventory, legal basis/purposes, transfers, retention/deletion, data-subject requests and incident process |
| IP/SBOM/licences | INCOMPLETE / BLOCKED | Candidate-specific SBOM; dependency, source-history and asset ownership/licence review; trademark risk evidence |
| Billing/tax/support | NOT READY | Provider eligibility and sandbox state transitions; manual payment, refund/cancel/renewal, invoice/tax review, support/escalation and recovery runbooks |
| Production rollout | NOT authorized | Backup/restore proof, migration + Edge version plan, pre/postflight, rollback and accountable-owner approval |

## 5. Changes actually made

- Read-only live repository, PR, check-run, branch-protection/ruleset and workflow inspection.
- Confirmed the 100-row current matrix and counted status categories as above.
- Matched production smoke error text against current main source. No production deployment or schema fix was attempted.
- Committed test-only updates to PR #191, latest head aa28683435b39fa45574da88e510728ae7a59b98. Normal T006/T020 AppTest flows mock the persistence boundary so they do not depend on a live session token; explicit negative tests verify failed-save rollback; Streamlit form input and submit are sent in the same event. Exact-head workflows PASS: [validation — 930 passed, 2 skipped, 71 warnings](https://github.com/MSJ1708/shoir-ie/actions/runs/40280196434), [platform tests — 930 passed, 2 skipped, 71 warnings](https://github.com/MSJ1708/shoir-ie/actions/runs/40280196567), [engine regression](https://github.com/MSJ1708/shoir-ie/actions/runs/40280196702), [security/quality](https://github.com/MSJ1708/shoir-ie/actions/runs/40280196723). The hosted smoke was skipped; authenticated release gate was not run.
- Prepared a 100-row tool acceptance matrix template, PDPL data inventory template, release/rollback manifest, counsel-review-only copies of six PR #170 legal draft/checklist files, an engineering calculation disclaimer draft and attribution-only referral rules. Legal drafts are not in public app policy paths and are not approved.
- PR #191 was retargeted to main but remains a draft; no feature PR was merged or closed. No production deployment, schema/Edge deployment, payment operation, account action or branch-protection change occurred.

## 6. Exact next steps

1. Keep #191 draft for owner/reviewer review. Validation, platform, engine and security/quality workflows pass on aa28683435b39fa45574da88e510728ae7a59b98; do not merge while hosted smoke is skipped and authenticated staging acceptance is outstanding.
2. Build the commit/file-level unique-change map; port accepted changes into one current-main-based integration path and retest affected files.
3. Verify the live production Streamlit configuration and mismatch without touching production; prepare an approved compatibility plan only after source, schema and Edge versions are agreed.
4. Configure branch protection, then run authenticated staging gate, direct-action/tier denials, cross-workspace isolation, save/reload/re-login and real artifact round trips on the exact candidate SHA.
5. Close operator identity, Saudi legal, privacy/PDPL, IP/SBOM, payment, tax, support and recovery gates; independently validate the limited paid-pilot tool subset.

**Final decision: NO-GO.** Zero tools are marked VERIFIED_WORKING in the current matrix, production smoke fails, authenticated staging acceptance is skipped, main is unprotected, and legal/commercial gates remain open. A limited paid-pilot decision can be considered only after a precisely listed tool subset passes independent acceptance and its applicable legal, privacy, security and support gates are complete.

## 7. Fresh production/staging Supabase parity evidence — read-only snapshot, 26 October 2026

**Inspection method:** Supabase project metadata, migration list, deployed Edge Function metadata/source, security advisors, and read-only SELECTs against `information_schema.role_table_grants` and `pg_policies`. No table rows were read; no schema, migration, function, account, payment, or project settings were changed.

### Project and database state

| Signal | Production | Staging | Release implication |
|---|---|---|---|
| Supabase project | `gcsamrdaeraxieaagsta` (`shoir-ie-production`) | `hfhrosthswcybccepmak` (`shoir-ie-staging-2026-10-19`) | Refs verified from the connected Supabase project list. |
| Reported region | `eu-central-1` | `eu-central-1` | Runtime database region is confirmed; this does not itself establish legal transfer compliance or identify every app/AI/email/analytics processor or its region. |
| Database engine/version | PostgreSQL 17; `17.6.1.166` | PostgreSQL 17; `17.11.0.003` | The database engine versions differ. |
| Applied migrations | 14; latest `20261019140600_atomic_subscription_request_decisions` | 17; includes that same migration plus three later legal/consent-policy migration records | Schema/policy parity is **FAIL / BLOCKED**. Staging records `20261021130000_shoir_beta_legal_referrals`, `20261022110000_enforce_beta_legal_acceptance`, and version `20261025164602` named `20261023130000_refresh_refund_policy_acceptance_version`; production does not report these migrations. Reconcile the third record's applied version/name with the checked-in migration inventory before any release. |
| `shoir-persistence` Edge Function | ACTIVE, version 8, `verify_jwt=false`, deployed-source SHA-256 `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d` | ACTIVE, version 8, `verify_jwt=false`, deployed-source SHA-256 `b25d2c22d33baa4daef2b63d27375dcdfac57bb58cfc5e577882882436a0d0d0` | Same version number does **not** mean same source. The deployed hashes differ; source parity is **FAIL / BLOCKED**. |
| Referral flow in deployed function source | Referral-handler code is absent from the deployed production `index.ts` returned by the management API | Referral-handler code is present in the deployed staging `index.ts` | Production's deployed Edge source is behind/ different from staging and current repository source. The production app's hosted smoke also fails with a missing `durable_account_store.edge_referral_summary` attribute, while the inspected current main source contains that method. Together these are direct parity indicators, not a reason to hot-deploy without a compatibility plan. |

### Access-control metadata observed

- `public.shoir_referrals` exists in staging and was not returned in the production public-table inventory. On staging it has RLS enabled, no row policies, and the read-only grant query returned no direct table grants to `anon` or `authenticated`; grants were shown for `postgres` and `service_role`. The Supabase security advisor emits one INFO lint, `rls_enabled_no_policy`, for this table. This is consistent with a server-only table **only if** all access stays on authenticated, reviewed service paths; it is not a substitute for direct-call, RPC, and tenant-isolation testing.
- The inspected `shoir_accounts` and `shoir_workspace_states` tables have RLS enabled. The returned `anon`/`authenticated` policies are deny-all (`USING false`, `WITH CHECK false`), and the query found no direct table grants to those roles. These are positive metadata observations, not proof that all Edge Function actions, service-role paths, object references, session expiry, or exported data are isolated.
- Both Edge Functions are configured with platform `verify_jwt=false`; the source inspected contains custom session validation such as `getSession` and admin-session checks. Because platform JWT verification is disabled, every public action must be proven to apply the correct custom session, role, entitlement, and ownership checks. Do not infer either safety or exploitability from this flag alone.
- The production security advisor returned no security lints at this inspection; staging returned the one informational RLS/no-policy finding above. A clean advisor list does not establish application-level tenant isolation.

### Release actions now required

1. **BLOCKED — platform owner:** verify the actual Streamlit Cloud branch, commit, entry point, and secret/configuration *presence* for each production/staging URL. The connected GitHub/Supabase tools cannot read Streamlit Cloud deployment settings.
2. **BLOCKED — platform owner:** reconcile the deployed production application source with the reviewed repository commit and the deployed Edge source. Treat app + database migrations + Edge Function as one compatibility bundle; do not redeploy only one component.
3. **BLOCKED — release/security reviewer:** prove custom session expiry/revocation, role/entitlement gates, direct Edge action denial, two-user workspace isolation, and private referral/payment-proof access on the deployed staging services.
4. **BLOCKED — owner approval:** before any production mutation, record a database backup and restore proof, exact candidate SHA/migration/Edge hashes, a backwards-compatible rollout order, postflight checks, and rollback plan, then obtain explicit authorization. No production migration or function/app deployment was performed in this inspection.
5. **BLOCKED — owner + qualified Saudi privacy/legal review:** incorporate the confirmed `eu-central-1` database region into the factual data-flow map, then verify Streamlit and all enabled processors/regions/contracts, transfer paths, retention, deletion, legal bases, and customer disclosures. A region observation is not a legal-compliance conclusion.
6. **Upcoming compatibility check:** current Supabase official changelog describes a public-schema Data/GraphQL API exposure-default change being enforced for all projects on **30 October 2026**. Before adding/exposing tables, confirm the actual Data API settings, explicit grants, and RLS policy model against current Supabase guidance; do not broaden grants merely to make a client request work. Source: https://supabase.com/changelog?types=breaking-change

### Current hosted-check evidence rechecked

- Main exact-SHA validation run [40273481812](https://github.com/MSJ1708/shoir-ie/actions/runs/40273481812): unit/platform test job **PASS**; `live-deployment-smoke` **FAIL** at “Test hosted entry-screen rendering at desktop and mobile widths.”
- Staging exact-branch validation run [40273588613](https://github.com/MSJ1708/shoir-ie/actions/runs/40273588613): test job **PASS**; `live-deployment-smoke` **SKIPPED**.
- Staging authenticated release gate [40273588637](https://github.com/MSJ1708/shoir-ie/actions/runs/40273588637): job **SKIPPED**, therefore **NOT RUN**, not PASS.
- PR #192's documentation checks passed on the preceding audit head `30371aff367f16460100ca88cdaa18418d08d103`; this document update creates a new commit, so that earlier check result is not evidence for the new head. Verify all required workflows on the new exact head before treating the updated audit PR as validated.

**Impact on decision:** deployment parity remains **FAIL / BLOCKED**; authenticated staging feature acceptance remains **NOT RUN**; overall production and paid-pilot decision remains **NO-GO**. No production database, Edge Function, application deployment, billing, or account was mutated by this inspection.

## 8. Fresh direct-content reconciliation of PR #170 — 26 October 2026

The current PR #170 branch `legal-beta-referral-readiness-2026-10-21` is **47 commits ahead / 334 behind** current `main`, based on common ancestor `3a73ada0be2ea5e85903b9c8937f8a9387ee061d`. The ordinary compare is therefore not an inventory of unique current changes: paths touched on both sides since the old common ancestor can appear in the compare even when their present file contents match.

A direct file-content comparison found the following files identical between current main and PR #170: `docs/COOKIE_POLICY.md`, `docs/PRIVACY_POLICY.md`, `docs/TERMS_AND_CONDITIONS.md`, `docs/THIRD_PARTY_LICENSE_REVIEW.md`, `durable_account_store.py`, `migrations/shoir_postgresql.sql`, `supabase/migrations/20261021130000_shoir_beta_legal_referrals.sql`, `supabase/migrations/20261022110000_enforce_beta_legal_acceptance.sql`, and `tests/test_beta_legal_referrals.py`. The repository's current main already contains the core code and focused test for versioned consent and attribution; these do not need to be wholesale reintroduced from an old stack.

Current main is newer in several material places:

- Main `docs/REFUND_POLICY.md` is version `2026-10-23-v2`; PR #170 still has `2026-10-21-v1`.
- Main `app.py` and `supabase/functions/shoir-persistence/index.ts` have the refund-policy v2 constants and additional current code. The PR #170 versions still reflect v1, and its Edge source does not include the subsequent v2 change.
- Main contains `supabase/migrations/20261023130000_refresh_refund_policy_acceptance_version.sql`, which is absent from PR #170's migration list, and main's migration-history/source-inventory tests assert the v2 policy. The stale branch's corresponding fixture/assertions still use v1.
- Main's `docs/LEGAL_RISK_REGISTER.md` and `README.md` differ from the PR branch and must be preserved/reconciled rather than reverted to the older branch version.
- `docs/COMMERCIAL_LAUNCH_CHECKLIST.md` is present on #170 but absent from current main. A review-only copy is already preserved in this audit PR as `docs/release/legal-drafts/SAUDI_COMMERCIAL_REVIEW_CHECKLIST.md`; it remains an unapproved draft.

**Disposition refinement for #170:** do not merge or cherry-pick the old branch wholesale. Keep it open/draft until a reviewer explicitly approves a small, current-main-based change. The checklist's unique content is preserved in the audit PR; any remaining README/app/Edge differences must be reviewed against current main and the v2 consent contract. Production still lacks the later applied migrations in its live history and the deployed production Edge hash differs from staging, so repository presence alone does not resolve deployment parity. No PR was merged or closed by this reconciliation.



## Current recheck — 26 October 2026

The following current snapshot supersedes the older baseline/counts in this historical audit. Current `main` is `267be8889c310d90141c047d8aadd42c942423fb`; its 100-row tool matrix contains 98 `IMPLEMENTED_NEEDS_VALIDATION`, 2 `EXTERNAL_CONFIGURATION_REQUIRED`, and 0 `VERIFIED_WORKING`.

### Exact-main checks

- Validation [40291784799](https://github.com/MSJ1708/shoir-ie/actions/runs/40291784799): PASS.
- Engine regression [40291784823](https://github.com/MSJ1708/shoir-ie/actions/runs/40291784823): PASS.
- Security/quality [40291784836](https://github.com/MSJ1708/shoir-ie/actions/runs/40291784836): PASS.
- Hosted smoke failed on the merged PR #193 commit in [run 40290645125](https://github.com/MSJ1708/shoir-ie/actions/runs/40290645125); a fresh hosted check of the currently deployed source remains required.
- Staging validation [40273588613](https://github.com/MSJ1708/shoir-ie/actions/runs/40273588613) passed at `8b36e3737705867019b9cf29e603cfc37e7911e6`; authenticated gate [40273588637](https://github.com/MSJ1708/shoir-ie/actions/runs/40273588637) was skipped / NOT RUN.
- The current GitHub integration could not read main branch protection (403); the repository administrator must verify the saved rule configuration.
- PR #193 is merged. PR #195, [secure read-only REST verification for T096](https://github.com/MSJ1708/shoir-ie/pull/195), is still a draft on `feat/t096-rest-readonly-adapter-20261026`. At head `678d1db7df73c3db71a6c355bbf58741a8a36a70`, engine regression had passed; validation, platform, tests and security/quality were still in progress at the last check. This is not merge or release approval.
- The current open-PR search returned 16 PRs: #192, #195, #191, #182, #172, #184, #173, #181, #174, #188, #178, #189, #179, #180, #175 and #170. Each requires a current per-PR diff, base/head, conflict and exact-head-check review; this inventory is not a merge recommendation.
- Root [Commercial Launch Checklist](../COMMERCIAL_LAUNCH_CHECKLIST.md) contains current gate statuses and explicit external actions.

No production deployment, database migration or branch-protection change was performed by this audit. Overall decision remains **NO-GO**.
