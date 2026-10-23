# Shoir-IE 100-Tool Implementation Report

## Release decision: NO-GO for claiming all 100 targets operational

This is an additive implementation tranche for the existing Shoir-IE app. It retains the current shell, established Workbench, public Explore Modules buying experience, legacy module IDs/routes, account and billing behavior. The new Engineering Tool Library is a separate, authenticated sector grouped into the ten requested workbenches; it does not replace the established navigation.

No target is marked `VERIFIED_WORKING`. The grouped library now wires 20 distinct target IDs into 21 limited-validation method paths (T066 offers both bin packing and a separate cutting-stock MILP). Authenticated browser matrix, persistence/relogin, route/action/API/export enforcement, and full specialist validation remain release gates.

## Implemented in this tranche

- Stable canonical IDs `T001`–`T100`, ten workbench groups, minimum target tier, candidate route, purpose, input/output contract, status and remaining gap.
- `shoir_100_tool_registry.py`: fail-closed target access for unknown tools/tier labels, a separate readiness gate, stable-ID lookup, metadata audit and acceptance-state fields.
- `shoir_tier_capabilities.py`: additive exports for target policy. Existing subscription routes, prices and legacy module contracts are not silently re-tiered.
- `pages/Engineering_Tool_Library.py`: authenticated tool explorer, filters, detail contracts and a hand-off only to legacy Workbench routes available under the logged-in user's actual tier. The page makes clear that target status does not certify a legacy route.
- `pages/Engineering_Tool_Library.py` and `shoir_100_tool_engines.py` expose **nine limited-validation method paths** in the grouped library:
  - **T021 — Time Study and Standard Time:** observed mean/median, rating-adjusted normal time, explicit allowance convention and standard time.
  - **T023 — Takt Time and Capacity:** theoretical takt/capacity and capacity gap; the caller must supply compatible units and the same production period.
  - **T026 — OEE and Loss Analysis:** availability, performance, quality, OEE and a sequential loss decomposition; plant-specific definitions still need review.
  - **T032 — Process Capability:** Cp/Cpk/Pp/Ppk with subgroup assumptions and variation warnings.
  - **T055 — Inventory Policy:** EOQ, safety stock and reorder point under explicit input/service assumptions.
  - **T066 — Cutting Stock and Bin Packing:** supported scope is one-dimensional First-Fit Decreasing; it validates positive finite capacities/sizes and integer quantities, returns item assignments/bin accounting/utilization, and does not claim minimum-bin optimality. Cutting-stock pattern generation and multi-dimensional packing are not implemented.
  - **T076 — Process Mining:** directly-follows transition counts, activity counts, case traces, elapsed case durations and inter-event waits from a validated event log; timestamps are normalized to UTC and optional reference trace comparison is exact-sequence only. It is not full Petri-net/token-replay conformance.
  - **T078 — Carbon Emissions:** activity data multiplied by a user-supplied, sourced/versioned factor with scope and provenance disclosure; this is not an audited emissions statement.
  - **T081 — Engineering Economics:** discounted cash-flow NPV/IRR and simple payback under stated timing/currency assumptions.
- The 20 wired target IDs show method/assumptions/warnings, stale-result labeling and CSV summaries/tables where the method emits structured outputs. Bad inputs preserve the last successful session result. The new Tool Library's validation-mode results are session-only; durable project persistence is not claimed. Synthetic example inputs must remain labelled synthetic and are not evidence of industrial savings.
- `tests/test_shoir_100_tool_engines.py`: hand-calculated/golden fixtures for the seven calculator paths and deterministic packing/process-mining fixtures, invalid/boundary input tests, non-mutation, timezone-aware process durations, directly-follows counts, source/factor checks and CSV parse/read-back assertions. Registry metadata now links each numerical target to its actual fixture test.
- `shoir_copilot_orchestrator.py`: governed decision staging now fails closed if the enterprise approval/access-control module cannot be imported; `tests/test_shoir_copilot_orchestrator.py` contains a regression test for that case.
- `tests/test_shoir_100_tool_registry.py`: 100 sequential stable IDs, required metadata, all 100 × six plan/package entitlement outcomes, fail-closed unknowns, Research Pack vs Enterprise Plus, display label identity and readiness rules.
- `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`: 100 data rows and all 19 requested fields.
- This report documents scope and limitations without marketing foundation-only tools as complete.

## Current status counts

Generated from the matrix after wiring the additional methods: 56 `IMPLEMENTED_NEEDS_VALIDATION`, 38 `FOUNDATION_ONLY`, 0 `MISSING`, 6 `EXTERNAL_CONFIGURATION_REQUIRED`, 0 `VERIFIED_WORKING` and 0 `BLOCKED`.

T066 and T076 have explicit limited-scope specialist implementations; T021, T023, T026, T032, T055, T078 and T081 are also exposed through deterministic validation-mode calculators. All nine remain `IMPLEMENTED_NEEDS_VALIDATION`, not `VERIFIED_WORKING`, because authenticated end-to-end, persistence, route/action enforcement and export acceptance are incomplete. The other rows remain conservative source-triage statuses, and a matching legacy route is only a reuse candidate, not a verified specialist engine.

## Entitlement and access

The six target-package rules are covered by an exhaustive 600-outcome truth-table test: ordinary tiers are cumulative; Research Pack inherits through Enterprise and its research-only targets but not Enterprise Plus; Enterprise Plus does not inherit Research Pack-only targets; unknown tier/tool values deny access.

The legacy fail-open helpers were also corrected: shared tier normalization recognizes exact, explicit plan aliases (including existing price-suffixed labels) and returns `UNRESOLVED` for unknown labels; unknown current/required tiers deny access; `available_modules` no longer treats an unmapped module as free; and Copilot policy is populated from the canonical target IDs and names. The `industrial_platform` and `industrial_platform_excellence` tier gates now delegate to the shared policy. Regression tests were added for these behaviors.

**Remaining limitation:** these changes centralize the primary module and Copilot gates, but stable target IDs are not yet wired into every individual legacy direct route/action, API/plugin, connector or export call site. Those paths still require path-by-path positive/negative tests, particularly for hidden direct access. Prices, renewal rules and customer records were not changed.

## Verification status

- Four initial CI workflows passed on an earlier registry-only revision: application tests, platform tests, engine regression, and security/quality. See links in the PR Checks tab: [PR #177](https://github.com/MSJ1708/shoir-ie/pull/177).
- A later workflow set was queued while the branch was changing; it predates the latest engine additions. Do **not** interpret those earlier successes as proof of the newest revision.
- A subsequent full-suite candidate recorded **1 failed, 595 passed, 2 skipped, 19 warnings**. The failure was an alias authorization path still looking up only IDs/canonical names; the resolver has now been corrected and the full matrix is rerunning on a newer SHA. Do not treat the failed run as a pass; only the latest green result can support merge.
- The local container could not clone the repository through its network path, so no local full-repo test execution is claimed.
- No authenticated hosted browser walkthrough has been completed. `browser_test` remains `UNVERIFIED` for all 100 targets; the hosted live-deployment smoke was skipped.
- Export tests for engine output tables cover CSV serialization and pandas read-back; the new Tool Library also provides per-table and summary CSV download controls. The latest Streamlit AppTest exercises visible method forms and cutting-stock action, but the hosted download behavior, durable persistence, and existing shared XLSX/PDF/PPTX round trips remain unverified.
- Existing facility-layout source already includes department CRUD, complete From-To and SLP matrices, empty REL handling, heatmap data conversion, route alternatives and four-sheet XLSX export; focused tests exist. The full authenticated user workflow still needs to be run on staging. Enterprise Integration diagnostics, real workbook-to-decision, cross-account isolation and configured connectors also remain outstanding.

## Release-critical work remaining

1. Confirm all validation, test, platform, engine-regression and security/quality workflows pass on the same final PR head; fix failures and rerun before merge.
2. Perform authenticated staging browser coverage for the new Tool Library and its twenty-one method paths across twenty canonical target IDs on the correct tiers, then add the remaining module matrix with disposable accounts.
3. P0: verify Facility Layout/SLP department CRUD → From-To → relationship matrix/heatmap → flow-distance/handling cost → persisted alternative → parsed workbook export.
4. Verify multi-sheet workbook import → profile/map/clean → save/version → bottleneck/capacity study → scenario comparison → chart → exported file reopening and value/lineage checks.
5. Wire target-ID checks into actual legacy route/action/Copilot/API/export enforcement and add direct-call deny/allow tests without breaking current customer entitlements.
6. Add trusted hand-calculated or reference fixtures for each numerical specialist method. Keep unimplemented scope labeled foundation-only instead of substituting generic approximations.
7. Verify workspace isolation/persistence with two disposable users, and test configured integrations only on authorized staging endpoints. Metadata-only or unconfigured adapters remain `NOT CONNECTED`.
8. Verify current deployed SHA, Supabase schema/RPC compatibility and rollback/recovery separately; no production deployment or database change was performed in this tranche.

## Final recommendation

**NO-GO** for describing all 100 target capabilities as complete, fully working, workforce-ready or production-verified. The additive library and twenty-one focused method paths are a concrete implementation tranche, but current evidence does not satisfy the full completion gate in the master prompt.
