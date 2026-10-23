# Shoir-IE 100-Tool Implementation Audit — Phase 1

**Source baseline:** `3a73ada0be2ea5e85903b9c8937f8a9387ee061d` (main, 2026-10-21)  
**Implementation branch:** `audit/shoir-100-tools-20261023`  
**Last historical revision with a completed broad green suite before the latest tranche:** `a76237f204ba2c6136c16d732c6e8fbc55367899`  
**Release decision for the full 100-tool scope:** **NO-GO — incomplete scope and hosted/authenticated verification blocked**

## Summary

The existing product already contains reusable services and modules for Excel import, quality/reliability, optimization, facility layout, simulation, persistence, reports and enterprise workflows. This phase reused the existing shell and the current Industrial Engineering Workbench; it did not add a new top-level navigation item for every tool.

This is a focused first implementation phase, **not completion of the full 100-tool prompt**. A catalog entry is not proof of a functional engineering method, and unit tests do not substitute for authenticated browser acceptance.

## Work performed

- Added `shoir_tool_registry.py` with stable IDs T001–T100, workbench grouping, target minimum tier, input/output contracts, current mapped route/source, evidence status and remaining gaps. Unknown IDs fail closed through the target gate.
- Added `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`, with exactly 100 tool rows and the required implementation/evidence columns, plus this audit report.
- Added a **collapsed** searchable/filterable tool directory within the established Workbench. It reports readiness and minimum tier; foundation-only tools are not shown as operational merely because they exist in the catalog.
- Added focused deterministic methods to the existing Workbench without adding top-level navigation clutter. The current focused set is **T021** time study, **T022** work sampling, **T023** takt/capacity, **T026** OEE, **T028** Pareto/5-Why, **T029** 5S audit, **T030** Kaizen/A3, **T032** Cp/Cpk/Pp/Ppk, **T055** classical inventory policy, **T066** one-dimensional cutting stock, **T075** forecast drift thresholds, **T078** activity-factor carbon estimation, **T081** NPV/IRR/simple payback, and **T085** independent two-sample t-test sample size. The five new methods added in this tranche are T026, T032, T055, T078 and T081; all remain validation-required and do not imply verified live plant integrations.
- Added independent hand-calculated/boundary tests for the five latest methods, plus a Workbench AppTest that exercises their controls, dispatch, structured outputs and KPI rendering. Existing tests separately cover T021/T022/T023/T028/T029/T030/T066/T075/T085. These are automated/local tests, not a substitute for authenticated hosted browser checks.
- Fixed the Workbench excellence-layer tier helper: Research Pack previously ranked after Enterprise Plus and therefore could inherit Enterprise Plus-only modules. The helper and its regression test now enforce the add-on rule required by the master prompt. An older contradictory assertion that expected Research Pack to grant Enterprise Plus was updated to the required policy.
- Focused results store the inputs used with the result, call the existing per-user `workspace_persistence.py` service for non-guest users, and display distinct managed/local/session/failure/uncertain save states. An input snapshot mismatch warns that the result is stale. Workspace writes are not called fully durable unless the managed backend is configured and authenticated reload tests pass.
- The 14 focused target actions require both an authenticated non-guest session and the target-tier permission check before calculation. The Workbench now defaults an absent tier to Starter rather than silently defaulting to Enterprise Plus. Guest-denial regression coverage remains in place.
- Updated `workspace_persistence.py` to retain DataFrame column dtypes during save/load round trips (with a recoverable warning if an unsupported dtype cannot be restored); added an isolated T021 result/input round-trip test that confirms another user cannot read that result.

## Static target status counts

| Status | Count |
|---|---:|
| `IMPLEMENTED_NEEDS_VALIDATION` | 47 |
| `FOUNDATION_ONLY` | 51 |
| `EXTERNAL_CONFIGURATION_REQUIRED` | 2 |
| `MISSING` | 0 |
| `VERIFIED_WORKING` | 0 |
| **Total** | **100** |

These counts are conservative source-audit classifications. They are not a tool success rate, do not mean that every target method has been implemented, and do not mean that all 47 mapped capabilities meet their complete acceptance criteria. All 100 authenticated end-to-end browser statuses remain unverified in the matrix. The 14 focused methods listed above remain `IMPLEMENTED_NEEDS_VALIDATION`, not `VERIFIED_WORKING`, because hosted authenticated end-to-end acceptance has not been established. Local persistence/service tests do not prove managed-backend save/reload/re-login or workspace isolation across real authenticated sessions.

## Entitlement and routing boundaries

- The registry delegates target-tier checks to `shoir_tier_capabilities.tier_allows`; unknown target IDs are denied.
- Research Pack inherits ordinary capabilities through Enterprise and Research-only capabilities. It does **not** grant Enterprise Plus, and Enterprise Plus does **not** grant Research-only access.
- The legacy Workbench layer’s Research Pack / Enterprise Plus comparison was corrected and covered by regression tests.
- The new directory only launches the focused methods that use the T001–T100 runtime gate, or a mapped legacy module when both the target gate and the original module’s native gate allow access. Exact unmapped routes remain informational rather than being guessed or force-routed.
- This phase has **not** reconciled every legacy permission list and every Copilot, API, direct-action, connector, and export path to one runtime source of truth. That remains a release blocker for the full task.

## Verification evidence

The latest completed broad green baseline available before the five new deterministic methods was `a76237f204ba2c6136c16d732c6e8fbc55367899`. The later candidate branch adds new calculations, UI actions and tests; its separate CI results must be reviewed before this candidate is considered green. Historical results for that baseline:

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

**NO-GO for merging this as completion of the requested 100-tool implementation or for declaring Shoir-IE fully verified/workforce-ready.** Revision `a76237f204ba2c6136c16d732c6e8fbc55367899` passed the full 660-test suite, platform, engine-regression, security/quality, compile/import, and local desktop/mobile smoke gates. The hosted public-site smoke failed at desktop and mobile because the endpoint served a sleeping-app page instead of Shoir-IE. The branch provides an auditable 100-target matrix, 14 focused Workbench methods (including five added in the latest tranche), a corrected Research Pack/Enterprise Plus boundary, authenticated execution gating and improved workspace serialization/persistence coverage. It does not deliver 100 fully implemented/verified tools or authenticated per-tier end-to-end acceptance. The remaining work above is required before the full master prompt can be marked done.
