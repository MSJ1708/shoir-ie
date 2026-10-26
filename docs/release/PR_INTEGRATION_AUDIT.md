# Shoir-IE PR Integration Audit

**Audit captured:** 26 October 2026, using live GitHub metadata  
**Repository:** [MSJ1708/shoir-ie](https://github.com/MSJ1708/shoir-ie)  
**Baseline:** main at SHA 72e498d892b9eb088d34be940fc1f6d97b482c1a  
**Decision:** **NO-GO** for production release and paid launch on current evidence.

This report is an evidence snapshot and recommended disposition, not a claim that PRs were merged or blocked checks passed. Mainline already includes PR #183. All 14 open PRs below are still drafts.

## Executive findings

The main 100-target matrix has exactly 100 rows, with the following current status distribution:

| Matrix status | Count |
|---|---:|
| IMPLEMENTED_NEEDS_VALIDATION | 89 |
| FOUNDATION_ONLY | 9 |
| EXTERNAL_CONFIGURATION_REQUIRED | 2 |
| VERIFIED_WORKING | 0 |

A catalog of 100 entries is not evidence of 100 operational tools. Preserve the current shell and grouped Workbench; port unique methods, not competing registry foundations.

Current critical blockers:
1. Main is unprotected: GitHub reports protection disabled, required status contexts empty, and no rulesets.
2. On exact main SHA 72e498d892b9eb088d34be940fc1f6d97b482c1a, the unit/platform test job, engine regression, transaction contract, Edge Function verification, and security-quality checks pass, but the hosted public app smoke **fails**. The hosted app displays a startup compatibility error saying durable_account_store is missing edge_referral_summary. That function exists in the checked-in source at main (durable_account_store.py around line 628). This indicates a deployed-source/entry-point mismatch, not proof the source function is absent.
3. Staging validation passes on SHA 8b36e3737705867019b9cf29e603cfc37e7911e6, but authenticated release gate and hosted smoke are skipped, not passed.
4. PR #191 previously failed the T006 and T020 AppTests (2 failed, 928 passed, 2 skipped). A test-isolation fix is committed at aa28683435b39fa45574da88e510728ae7a59b98; CI was in progress at the time of capture.

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
| [#191](https://github.com/MSJ1708/shoir-ie/pull/191) | feat/shoir-100-tools-integration-20261025 (base 800b86b7…) ← feat/shoir-100-t006-recovery-20261026 (latest aa286834…) | Mergeable=true/state=unstable; prior head c1e6f657… had two AppTest failures. Checks on 28449466… were IN PROGRESS at capture | T006 snapshot recovery, T020 dataset lineage and T039 status reconciliation | Fix first. Tests now mock persistence for normal tool-flow checks without using a live backend and assert failed-save rollback. Require green checks on 28449466… before port/review. |

### PR inventory count

- Open drafts: 14
- Open non-drafts: 0
- No PR closure, merge or retarget was performed by this audit.

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
- Committed a focused test-only update on PR #191 at aa28683435b39fa45574da88e510728ae7a59b98. Normal T006/T020 method-flow assertions mock the workspace save operation so synthetic AppTest state cannot depend on a remote session token; explicit assertions cover failed-save rollback. Checks were in progress when recorded; not yet PASS.
- Created this documentation-only branch from the exact main baseline. No branch protection change, production mutation, database/Edge deployment, payment operation, account action, PR merge or PR closure occurred.

## 6. Exact next steps

1. Inspect all checks on #191 commit aa28683435b39fa45574da88e510728ae7a59b98; fix underlying failures if any.
2. Build the commit/file-level unique-change map; port fixes into one current-main-based integration path and retest affected files.
3. Verify the live production Streamlit configuration and mismatch without touching production; prepare an approved compatibility deployment plan only after source, schema and Edge versions are agreed.
4. Configure branch protection, then run authenticated staging gate, direct-action/tier denials, cross-workspace isolation, save/reload/re-login and real artifact round trips on the exact candidate SHA.
5. Close operator identity, Saudi legal, privacy/PDPL, IP/SBOM, payment, tax, support and recovery gates; independently validate the limited paid-pilot tool subset.

**Final decision: NO-GO.** Zero tools are marked VERIFIED_WORKING in the current matrix, production smoke fails, authenticated staging acceptance is skipped, main is unprotected, and legal/commercial gates remain open. A limited paid-pilot decision can be considered only after a precisely listed tool subset passes independent acceptance and its applicable legal, privacy, security and support gates are complete.
