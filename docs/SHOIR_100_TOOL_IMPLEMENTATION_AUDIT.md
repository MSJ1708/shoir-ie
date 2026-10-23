# Shoir-IE 100-Tool Implementation Audit — Phase 1

**Source baseline:** `3a73ada0be2ea5e85903b9c8937f8a9387ee061d` (main, 2026-10-21)  
**Implementation branch:** `audit/shoir-100-tools-20261023`  
**Latest branch head:** `a76237f204ba2c6136c16d732c6e8fbc55367899`  
**Last completed full-test code revision:** `9a1a61c330a70bc9efa22af0c24acc3d839cd8bd`  
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

The last completed full-suite code revision tested by GitHub Actions is `9a1a61c330a70bc9efa22af0c24acc3d839cd8bd`. The subsequent authenticated-execution guard and guest-denial regression were added afterward; CI workflows for the latest branch head `a76237f204ba2c6136c16d732c6e8fbc55367899` are running, so the results below must not be represented as validation of that final access-control change. Results observed for revision `9a1a61c330a70bc9efa22af0c24acc3d839cd8bd`:

- Full test workflow [39977967543](https://github.com/MSJ1708/shoir-ie/actions/runs/39977967543): `python -m pytest -q tests` **659 passed, 2 skipped, 28 warnings**.
- Platform tests [39977967664](https://github.com/MSJ1708/shoir-ie/actions/runs/39977967664): **passed**.
- Engine regression [39977967572](https://github.com/MSJ1708/shoir-ie/actions/runs/39977967572): **6 passed, 1 warning**.
- Security/quality workflow [39977967603](https://github.com/MSJ1708/shoir-ie/actions/runs/39977967603): **passed**, including compile, regression tests, dependency audit and secret-pattern guard.
- Validation job [39977967700](https://github.com/MSJ1708/shoir-ie/actions/runs/39977967700): compilation, regression tests, required-module parse checks, and top-level application import smoke (**54 statements**) passed. The final local Chromium desktop/mobile smoke was still in progress at the time this section was updated; do not treat it as a pass until its job and artifact are complete.
- Hosted public-site smoke in [39977967700](https://github.com/MSJ1708/shoir-ie/actions/runs/39977967700): **failed**. The public Streamlit endpoint returned HTTP 200, but its rendered text was the Streamlit “This app has gone to sleep due to inactivity” screen; the Shoir-IE application frame could not be located. The browser recorded no uncaught JavaScript errors, but it did record a failed 404 resource. This is an availability/hosted-rendering failure, not a pass.
- A test on the preceding revision caught a strict DataFrame round-trip dtype mismatch in the new persistence test; dtype metadata restoration was added after that failure. The current full test suite above passes the corrected test.

No authenticated per-tier module walkthrough was run, and the matrix accurately marks all 100 browser-acceptance fields unverified. Local test success does not establish hosted application availability, real connector state, managed persistence configuration or the full six-package authorization matrix.

## Remaining release blockers

1. Finish the missing/partial specialist methods and independently validate every numerical engine with hand-checked or trusted fixtures, including invalid and boundary conditions.
2. Bind and verify every target ID through its actual route/action; reconcile all legacy registries, tier enforcement points, Copilot, direct links, API/plugin and export access.
3. Test the full six-package truth table across real module card, action, route, API, Copilot and export paths, including expired/inactive access and cross-workspace denial.
4. Run authenticated browser walkthroughs for each advertised capability and each plan/package; validate empty state, valid/invalid data, charts, stale result behavior, save/reload/re-login, exports, mobile layout and Arabic/RTL.
5. Execute and record the complete workbook → validated dataset → analysis → scenario → decision → real export workflow, plus the facility layout From-To/SLP persistence/export workflow, with parsed files and non-sensitive evidence.
6. Wake/restore the hosted app through its normal owner/provider controls, rerun the deployment smoke, and run the authorized staging release gate. Finish/record the current local desktop/mobile browser smoke and attach its artifact if it passes. No production data, administrator account, billing or live deployment was changed by this branch.

## Release recommendation

**NO-GO for merging this as completion of the requested 100-tool implementation or for declaring Shoir-IE fully verified/workforce-ready.** On revision `9a1a61c330a70bc9efa22af0c24acc3d839cd8bd`, the full, platform, engine-regression and security/quality workflows passed. The local desktop/mobile smoke for that run remains incomplete, and the hosted public-site smoke failed because the deployed app was asleep. The current branch adds an authentication check and guest-denial test after that tested revision; its workflows are pending, so that change remains unverified until CI finishes. The branch provides a reviewable registry/gap matrix, five focused specialist methods, improved per-user result persistence handling and DataFrame type-preservation coverage; it does not deliver 100 verified tools or authenticated end-to-end acceptance. The remaining work above is required before the full master prompt can be marked done.
