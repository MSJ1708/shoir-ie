# Shoir-IE 100-Tool Implementation Audit — Phase 1

**Source baseline:** `3a73ada0be2ea5e85903b9c8937f8a9387ee061d` (main, 2026-10-21)  
**Implementation branch:** `feature/shoir-100-completion-20261024` (draft PR [#180](https://github.com/MSJ1708/shoir-ie/pull/180))  
**Last historical revision with a completed broad green suite before the current five-method tranche:** `97c8f8bbbdc7b3eacf4f4a8990e10131e43b156e`  
**Release decision for the full 100-tool scope:** **NO-GO — incomplete scope and hosted/authenticated verification blocked**

## Summary

The existing product already contains reusable services and modules for Excel import, quality/reliability, optimization, facility layout, simulation, persistence, reports and enterprise workflows. This phase reused the existing shell and the current Industrial Engineering Workbench; it did not add a new top-level navigation item for every tool.

This is a focused first implementation phase, **not completion of the full 100-tool prompt**. A catalog entry is not proof of a functional engineering method, and unit tests do not substitute for authenticated browser acceptance.

## Work performed

- Added `shoir_tool_registry.py` with stable IDs T001–T100, workbench grouping, target minimum tier, input/output contracts, current mapped route/source, evidence status and remaining gaps. Unknown IDs fail closed through the target gate.
- Added `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`, with exactly 100 tool rows and the required implementation/evidence columns, plus this audit report.
- Added a **collapsed** searchable/filterable tool directory within the established Workbench. It reports readiness and minimum tier; foundation-only tools are not shown as operational merely because they exist in the catalog.
- Added focused deterministic methods to the existing Workbench without adding top-level navigation clutter. The current focused Workbench set contains **27 deterministic methods**: **T013** data quality profiling; **T016** unit/currency conversion (fixed physical factors or dated user-supplied exchange rate); **T017** safe table joins; **T018** timestamp-aware time-series processing; **T019** reproducible synthetic data generation; **T021** time study; **T022** work sampling; **T023** takt/capacity; **T026** OEE; **T028** Pareto/5-Why; **T029** 5S audit; **T030** Kaizen/A3; **T031** Individuals/Moving-Range SPC; **T032** Cp/Cpk/Pp/Ppk; **T034** binomial acceptance-sampling planning; **T040** scoped quality-cost analysis; **T042** MTBF/MTTR; **T055** classical inventory policy; **T056** ABC/XYZ classification; **T066** one-dimensional cutting stock; **T070** M/M/1 queue analysis; **T075** forecast-drift thresholds; **T078** activity-factor carbon estimation; **T081** NPV/IRR/simple payback; **T082** cost variance reconciliation; **T084** weighted project portfolio scoring; and **T085** independent two-sample t-test sample size. Eight of these methods were newly integrated or made executable in the current tranche. All remain validation-required; none imply verified live plant integrations.
- Added independent hand-calculated/boundary tests for focused engineering methods, including source-preservation and cardinality checks for data profiling/joins, timezone/resampling cases, reproducible synthetic data, sampling operating characteristics, M/M/1 queue boundaries, costing reconciliation and weighted portfolio ranking. These numerical fixtures are separate from static registry tests and do not substitute for authenticated hosted browser checks.
- Fixed the Workbench excellence-layer tier helper: Research Pack previously ranked after Enterprise Plus and therefore could inherit Enterprise Plus-only modules. The helper and its regression test now enforce the add-on rule required by the master prompt. An older contradictory assertion that expected Research Pack to grant Enterprise Plus was updated to the required policy.
- Focused results store the inputs used with the result, call the existing per-user `workspace_persistence.py` service for non-guest users, and display distinct managed/local/session/failure/uncertain save states. An input snapshot mismatch warns that the result is stale. Workspace writes are not called fully durable unless the managed backend is configured and authenticated reload tests pass.
- The 27 focused target actions require both an authenticated non-guest session and the target-tier permission check before calculation. The Workbench now defaults an absent tier to Starter rather than silently defaulting to Enterprise Plus. Guest-denial regression coverage remains in place.
- Updated `workspace_persistence.py` to retain DataFrame column dtypes during save/load round trips (with a recoverable warning if an unsupported dtype cannot be restored); added an isolated T021 result/input round-trip test that confirms another user cannot read that result.

## Static target status counts

| Status | Count |
|---|---:|
| `IMPLEMENTED_NEEDS_VALIDATION` | 60 |
| `FOUNDATION_ONLY` | 38 |
| `EXTERNAL_CONFIGURATION_REQUIRED` | 2 |
| `MISSING` | 0 |
| `VERIFIED_WORKING` | 0 |
| **Total** | **100** |

These counts are conservative source-audit classifications. They are not a tool success rate, do not mean that every target method has been implemented, and do not mean that all 49 mapped capabilities meet their complete acceptance criteria. All 100 authenticated end-to-end browser statuses remain unverified in the matrix. The 27 focused methods listed above remain `IMPLEMENTED_NEEDS_VALIDATION`, not `VERIFIED_WORKING`, because hosted authenticated end-to-end acceptance has not been established. Local persistence/service tests do not prove managed-backend save/reload/re-login or workspace isolation across real authenticated sessions.

## Entitlement and routing boundaries

- The registry delegates target-tier checks to `shoir_tier_capabilities.tier_allows`; unknown target IDs are denied.
- Research Pack inherits ordinary capabilities through Enterprise and Research-only capabilities. It does **not** grant Enterprise Plus, and Enterprise Plus does **not** grant Research-only access.
- The legacy Workbench layer’s Research Pack / Enterprise Plus comparison was corrected and covered by regression tests.
- The new directory only launches the focused methods that use the T001–T100 runtime gate, or a mapped legacy module when both the target gate and the original module’s native gate allow access. Exact unmapped routes remain informational rather than being guessed or force-routed.
- This phase has **not** reconciled every legacy permission list and every Copilot, API, direct-action, connector, and export path to one runtime source of truth. That remains a release blocker for the full task.

## Verification evidence

The latest historical broad green baseline before the current eight-method tranche was `97c8f8bbbdc7b3eacf4f4a8990e10131e43b156e` (687 passed, 2 skipped, 28 warnings). The current branch has added further engines, Workbench controls, tests and matrix updates after that baseline. CI runs for the latest PR revision have been created, but their state must be checked before merge; a prior green run is not proof for this candidate. Historical run links below refer to earlier tested revisions:

- Full test workflow [39979010804](https://github.com/MSJ1708/shoir-ie/actions/runs/39979010804): `python -m pytest -q tests` **660 passed, 2 skipped, 28 warnings**. This includes the T021 DataFrame/input round-trip test and guest-denial Workbench AppTest.
- Platform tests [39979011334](https://github.com/MSJ1708/shoir-ie/actions/runs/39979011334): **passed**.
- Engine regression [39979011150](https://github.com/MSJ1708/shoir-ie/actions/runs/39979011150): **6 passed, 1 warning**.
- Security/quality workflow [39979010930](https://github.com/MSJ1708/shoir-ie/actions/runs/39979010930): **passed**, including compile, regression tests, dependency audit and secret-pattern guard.
- Validation/local smoke [39979010782](https://github.com/MSJ1708/shoir-ie/actions/runs/39979010782): **passed** — compilation, full regression tests, required-module parse checks, application import smoke (**54 statements**), local Streamlit startup, and Chromium browser smoke at desktop and mobile widths.
- Local runtime smoke evidence artifact: `shoir-ie-local-runtime-smoke`, artifact ID `12513530314`, SHA-256 digest `62e84c29a295780bde16207b56f36c0a239314b46fcf431379308dd74c6fce2f`. [Download artifact ZIP](https://api.github.com/repos/MSJ1708/shoir-ie/actions/artifacts/12513530314/zip).
- Hosted public-site smoke in [39979010782](https://github.com/MSJ1708/shoir-ie/actions/runs/39979010782): **failed** at desktop and mobile sizes. The public Streamlit endpoint returned HTTP 200, but rendered “This app has gone to sleep due to inactivity” instead of the Shoir-IE frame. It showed no uncaught JavaScript errors, but the app frame was not located and failed resource responses were logged. This is an availability/hosted-rendering failure, not a pass. The redacted smoke artifact is `shoir-ie-live-deployment-smoke`, artifact ID `12511914558`, SHA-256 digest `4a1ee48a0780b3c7ad0899f871da23d756b83b384c712186f81ad0f748860373` ([ZIP](https://api.github.com/repos/MSJ1708/shoir-ie/actions/artifacts/12511914558/zip)).

Earlier, a strict DataFrame save/load test caught a dtype mismatch for integral-valued floating-point cells. Workspace serialization was updated to store column dtypes, and the current 660-test suite passes the corrected round-trip test.

No authenticated per-tier module walkthrough was run. The matrix accurately marks all 100 browser-acceptance fields unverified. Passing unit tests and local browser smoke do not establish that the hosted application is awake, each tool works under every subscription state, managed persistence is configured, or integrations are live.


## Remaining release blockers

1. Finish the missing/partial specialist methods and independently validate every numerical engine with hand-checked or trusted fixtures, including invalid and boundary conditions.
2. Bind and verify every target ID through its actual route/action; reconcile all legacy registries, tier enforcement points, Copilot, direct links, API/plugin and export access.
3. Test the full six-package truth table across real module card, action, route, API, Copilot and export paths, including expired/inactive access and cross-workspace denial.
4. Run authenticated browser walkthroughs for each advertised capability and each plan/package; validate empty state, valid/invalid data, charts, stale result behavior, save/reload/re-login, exports, mobile layout and Arabic/RTL.
5. Execute and record the complete workbook → validated dataset → analysis → scenario → decision → real export workflow, plus the facility layout From-To/SLP persistence/export workflow, with parsed files and non-sensitive evidence.
6. Wake/restore the hosted app through its normal owner/provider controls, rerun the deployment smoke, and run the authorized staging release gate. Finish/record the current local desktop/mobile browser smoke and attach its artifact if it passes. No production data, administrator account, billing or live deployment was changed by this branch.

## Release recommendation

**NO-GO for merging this as completion of the requested 100-tool implementation or for declaring Shoir-IE fully verified/workforce-ready.** Revision `a76237f204ba2c6136c16d732c6e8fbc55367899` passed the full 660-test suite, platform, engine-regression, security/quality, compile/import, and local desktop/mobile smoke gates. The hosted public-site smoke failed at desktop and mobile because the endpoint served a sleeping-app page instead of Shoir-IE. The branch provides an auditable 100-target matrix, 27 focused Workbench methods, a corrected Research Pack/Enterprise Plus boundary, authenticated execution gating and improved workspace serialization/persistence coverage. It does not deliver 100 fully implemented/verified tools or authenticated per-tier end-to-end acceptance. The remaining work above is required before the full master prompt can be marked done.

## Current feature branch delta — 24 October 2026

This section records the additional focused implementation present on branch `feature/shoir-100-completion-20261024`, with draft PR [#180](https://github.com/MSJ1708/shoir-ie/pull/180). The updated matrix has 100 unique target rows and current static statuses of 60 `IMPLEMENTED_NEEDS_VALIDATION`, 38 `FOUNDATION_ONLY`, 2 `EXTERNAL_CONFIGURATION_REQUIRED`, 0 `MISSING`, and 0 `VERIFIED_WORKING`.

The eight new or newly executable focused methods are:
- **T013** — non-destructive Data Quality Profiler.
- **T017** — safe table join/merge preview with key and unmatched-row diagnostics; many-to-many joins caused by duplicated null keys are rejected.
- **T018** — time-series parsing/local-timezone handling, sort, duplicate policy and optional resampling.
- **T019** — deterministic seed-based synthetic production data, labeled `SYNTHETIC`.
- **T034** — single-sample binomial AQL/LTPD risk planner; not a substitute for a required standard-specific sampling plan.
- **T070** — stable/unstable M/M/1 analytical queue metrics under explicit assumptions.
- **T082** — plan/standard/actual cost variance reconciliation.
- **T084** — transparent min-max weighted portfolio scoring with benefit/cost directions and subjective-weight warnings.

Added tests are in `tests/test_shoir_target_engines_extended.py`; the Workbench is extended in `pages/Industrial_Engineering_Workbench.py`; registry and matrix details are in `shoir_tool_registry.py` and `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`. The Workbench preserves the established shell, requires an authenticated non-guest user and a stable-ID tier permission before focused execution, displays structured outputs and exposes CSV downloads for result tables. It retains the prior successful in-session output after a failed rerun.

**Verification status for this delta:** automated GitHub workflow runs were triggered from PR updates, but no completed run was confirmed while preparing this note. The new code therefore remains `IMPLEMENTED_NEEDS_VALIDATION`. The new tranche has not been shown to pass the authenticated staging per-tier browser matrix, managed-backend save/reload/re-login checks, the full import→analysis→scenario→export journey, or live connector tests. Keep the PR in draft until CI and reviewer inspection are complete.
