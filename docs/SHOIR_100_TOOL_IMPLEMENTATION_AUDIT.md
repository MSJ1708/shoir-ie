# Shoir-IE 100-Tool Implementation Audit — Phase 1

**Source baseline:** `3a73ada0be2ea5e85903b9c8937f8a9387ee061d` (main, 2026-10-21)  
**Implementation branch:** `audit/shoir-100-tools-20261023`  
**Latest validated code-bearing revision:** `a76237f204ba2c6136c16d732c6e8fbc55367899`  
**Release decision for the full 100-tool scope:** **NO-GO — incomplete scope and hosted/authenticated verification blocked**

## Summary

The existing product already contains reusable services and modules for Excel import, quality/reliability, optimization, facility layout, simulation, persistence, reports and enterprise workflows. This phase reused the existing shell and the current Industrial Engineering Workbench; it did not add a new top-level navigation item for every tool.

This is a focused first implementation phase, **not completion of the full 100-tool prompt**. A catalog entry is not proof of a functional engineering method, and unit tests do not substitute for authenticated browser acceptance.

## Work performed

- Added `shoir_tool_registry.py` with stable IDs T001–T100, workbench grouping, target minimum tier, input/output contracts, current mapped route/source, evidence status and remaining gaps. Unknown IDs fail closed through the target gate.
- Added `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`, with exactly 100 tool rows and the required implementation/evidence columns, plus this audit report.
- Added a **collapsed** searchable/filterable tool directory within the established Workbench. It reports readiness and minimum tier; foundation-only tools are not shown as operational merely because they exist in the catalog.
- Implemented and exposed five focused deterministic methods in the existing Workbench: **T021** time-study standard time (mean, rating, and allowance defined as a share of standard time); **T023** takt/capacity calculator (consistent time units, implied capacity and capacity gap); **T066** one-dimensional cutting/bin-packing MILP (explicit per-piece kerf convention); **T075** forecast error threshold monitor (MAE/RMSE/bias, not an autonomous retraining detector); and **T085** balanced independent two-sample t-test sample-size planner (noncentral-t power, assumptions stated).
- Added independent hand-calculated/boundary tests for all five methods and an AppTest that launches and runs T021, T023 and T066 through the existing directory, and checks that T067 opens the existing “Multi-Objective Optimization” module through the normal selector when native permission allows it.
- Fixed the Workbench excellence-layer tier helper: Research Pack previously ranked after Enterprise Plus and therefore could inherit Enterprise Plus-only modules. The helper and its regression test now enforce the add-on rule required by the master prompt. An older contradictory assertion that expected Research Pack to grant Enterprise Plus was updated to the required policy.
- Focused results store the inputs used with the result, call the existing per-user `workspace_persistence.py` service for non-guest users, and display distinct managed/local/session/failure/uncertain save states. An input snapshot mismatch warns that the result is stale. Workspace writes are not called fully durable unless the managed backend is configured and authenticated reload tests pass.
- The five target actions now require both an authenticated non-guest session and the target-tier permission check before calculation. A guest-denial AppTest was added; the fresh CI workflow for this last access-control change is not yet complete.
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

These counts are conservative source-audit classifications. They are not a tool success rate, do not mean that every target method has been implemented, and do not mean that all 47 mapped capabilities meet their complete acceptance criteria. All 100 authenticated end-to-end browser statuses remain unverified in the matrix. The five focused methods (T021, T023, T066, T075 and T085) remain `IMPLEMENTED_NEEDS_VALIDATION`, not `VERIFIED_WORKING`. The new persistence service call path is covered by an isolated local-database test, but authenticated managed-backend save/reload/re-login and workspace-isolation acceptance remains open.

## Entitlement and routing boundaries

- The registry delegates target-tier checks to `shoir_tier_capabilities.tier_allows`; unknown target IDs are denied.
- Research Pack inherits ordinary capabilities through Enterprise and Research-only capabilities. It does **not** grant Enterprise Plus, and Enterprise Plus does **not** grant Research-only access.
- The legacy Workbench layer’s Research Pack / Enterprise Plus comparison was corrected and covered by regression tests.
- The new directory only launches the focused methods that use the T001–T100 runtime gate, or a mapped legacy module when both the target gate and the original module’s native gate allow access. Exact unmapped routes remain informational rather than being guessed or force-routed.
- This phase has **not** reconciled every legacy permission list and every Copilot, API, direct-action, connector, and export path to one runtime source of truth. That remains a release blocker for the full task.

## Verification evidence

The current code-bearing revision verified by the completed automated/local checks is `a76237f204ba2c6136c16d732c6e8fbc55367899`. Verified results:

- Full test workflow [39979010804](https://github.com/MSJ1708/shoir-ie/actions/runs/39979010804): `python -m pytest -q tests` **660 passed, 2 skipped, 28 warnings**. This includes the T021 DataFrame/input round-trip test and guest-denial Workbench AppTest.
- Platform tests [39979011334](https://github.com/MSJ1708/shoir-ie/actions/runs/39979011334): **passed**.
- Engine regression [39979011150](https://github.com/MSJ1708/shoir-ie/actions/runs/39979011150): **6 passed, 1 warning**.
- Security/quality workflow [39979010930](https://github.com/MSJ1708/shoir-ie/actions/runs/39979010930): **passed**, including compile, regression tests, dependency audit and secret-pattern guard.
- Validation/local smoke [39979010782](https://github.com/MSJ1708/shoir-ie/actions/runs/39979010782): **passed** — compilation, full regression tests, required-module parse checks, application import smoke (**54 statements**), local Streamlit startup, and Chromium browser smoke at desktop and mobile widths.
- Local runtime smoke evidence artifact: `shoir-ie-local-runtime-smoke`, artifact ID `12513530314`, SHA-256 digest `62e84c29a295780bde16207b56f36c0a239314b46fcf431379308dd74c6fce2f`. [Download artifact ZIP](https://api.github.com/repos/MSJ1708/shoir-ie/actions/artifacts/12513530314/zip).
- The hosted public-site smoke job in [39979010782](https://github.com/MSJ1708/shoir-ie/actions/runs/39979010782) was still running when this section was updated. The most recent completed public-site smoke, [39977967700](https://github.com/MSJ1708/shoir-ie/actions/runs/39977967700), **failed**: the public Streamlit endpoint returned HTTP 200, but rendered “This app has gone to sleep due to inactivity” instead of the Shoir-IE frame. It showed no uncaught JavaScript errors, but the app frame was not located and a 404 resource was logged. This is an availability/hosted-rendering failure, not a pass.

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

**NO-GO for merging this as completion of the requested 100-tool implementation or for declaring Shoir-IE fully verified/workforce-ready.** Revision `a76237f204ba2c6136c16d732c6e8fbc55367899` passed the full 660-test suite, platform, engine-regression, security/quality, compile/import, and local desktop/mobile smoke gates. The hosted public-site smoke remains an external release blocker until it can locate the actual app instead of a sleeping-page message. The branch provides an auditable 100-target matrix, five focused methods, a corrected Research Pack/Enterprise Plus boundary, authenticated execution gating, and improved workspace serialization/persistence coverage. It does not deliver 100 fully implemented/verified tools or authenticated per-tier end-to-end acceptance. The remaining work above is required before the full master prompt can be marked done.
