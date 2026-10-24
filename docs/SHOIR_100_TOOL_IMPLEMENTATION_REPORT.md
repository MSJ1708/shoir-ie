# Shoir-IE 100-tool implementation matrix — initial source crosswalk

**Review basis:** target catalog supplied in the implementation prompt; repository `main` at `c7bb3fcff54b6ce5de1ef0df2010fe3ef8029e9f`; implementation branch `feat/100-tool-readiness-foundations-2026-10-24`. Current branch commits add fail-closed entitlement discovery, fail-closed Copilot decision staging, and the first complete T016 converter implementation/UI/tests.

## Status definitions

- `VERIFIED_WORKING`: implemented and all applicable automated and authenticated end-to-end acceptance checks passed on the tested revision.
- `IMPLEMENTED_NEEDS_VALIDATION`: a real implementation/candidate engine exists, but the target-specific acceptance or end-to-end evidence is incomplete.
- `FOUNDATION_ONLY`: a related module/helper exists, but the full specialist behavior in the target acceptance has not been established.
- `MISSING`: no adequate implementation exists.
- `EXTERNAL_CONFIGURATION_REQUIRED`: a relevant function/adapter surface exists but depends on configured endpoints, credentials, or deployment not verified here.
- `BLOCKED`: testing/implementation is blocked by a documented external or environment limitation.

## Initial classification counts

- `IMPLEMENTED_NEEDS_VALIDATION`: 61
- `FOUNDATION_ONLY`: 34
- `EXTERNAL_CONFIGURATION_REQUIRED`: 5

No entry is marked `VERIFIED_WORKING`. The CSV includes one row for each stable tool ID T001–T100 and all required matrix columns. It distinguishes candidate existing routes from a verified implementation; a candidate mapping is not proof that the target acceptance contract is met.

## Important scope and evidence limitations

The Workbench also now contains embedded Starter-level implementations for T021 Time Study and Standard Time, T022 Work Sampling Analyzer, and T023 Takt Time and Capacity Calculator. These use explicit formulas, unit assumptions, warnings and invalid-input checks, with independent golden/boundary cases in `tests/test_shoir_ie_basic_calculators.py`; authenticated browser validation remains open.

The compact **Capability Status Center** is now reachable inside the existing Engineering Validation Center in the Workbench; it exposes filters across all T001–T100 entries without adding a new top-level navigation item. Its UI itself is classified as `IMPLEMENTED_NEEDS_VALIDATION` until authenticated UI checks validate the counts and filters.

This is the first target-to-source crosswalk, not the final acceptance matrix specified in the prompt. The repository is being inspected through the GitHub connector because a complete local checkout is not available in this execution environment. The code-level CI checks are available, but there are no disposable authenticated browser credentials in this task context, so all target browser rows remain `UNVERIFIED`. Several route mappings are explicitly labelled as candidates, and the remaining-gap column calls out the missing specialist validation instead of treating a broad module catalog or a generic playbook as a complete engine.

The T016 Unit and Currency Converter is newly implemented in this branch as a deterministic calculator inside the existing Starter-level Engineering Validation Center. Physical conversions use stated built-in conversion factors. Cross-currency conversion requires a user-entered positive rate, effective date, and source; no live exchange rate is fetched or invented. Its result includes method/provenance and is marked stale in the UI if its inputs change. Golden and invalid-input tests are in `tests/test_shoir_unit_converter.py`; their CI result must be read from the run associated with the final branch SHA before marking the engine as validated.

## Reusable source areas identified

- Workspace/data/persistence: `app.py`, `durable_account_store.py`, `shoir_enterprise_layer.py`.
- Existing Excel import/cleaning: `shoir_excel_runtime.py`, `shoir_excel_studio.py`.
- Engineering methods and validation helpers: `industrial_platform.py`, `industrial_platform_excellence.py`.
- Copilot workflow/orchestration: `shoir_copilot_orchestrator.py`.
- Tier/menu policy: `shoir_tier_capabilities.py` and the inventory tests.
- Workbench integration: `pages/Industrial_Engineering_Workbench.py`.

## Next implementation order

1. Complete call-path enforcement for canonical module IDs at every direct route/action/export/API entry point and run positive/negative tests against each plan.
2. Complete target-level golden tests and acceptance coverage for the exact calculation methods, starting with facility layout, Excel multi-sheet import/cleaning, OEE, Cpk, Gage R&R, scheduling/optimization, reliability, forecasting, and exports.
3. Finish the authenticated 100-target browser matrix with disposable accounts across the six plan/package states, including save/reload, denied direct access, valid/invalid inputs, narrow viewports, and RTL.
4. Configure and test only authorized staging connectors; never infer LIVE status from metadata or mocks.
5. Update `implementation_status` only after evidence exists, attach redacted artifacts, and rerun all CI jobs before a release decision.

**Release decision: NO-GO for workforce/paid production at this checkpoint.** The focused branch changes are under test/review. The full 100-tool acceptance matrix, authenticated route/action/export matrix, live integrations and production rollout checks are not complete.


## Continuation tranche — 24 October 2026

The additive continuation branch feat/shoir-100-tool-methods-wave-2026-10-24 adds eight deterministic methods and places them inside the existing Workbench areas. It does not add eight top-level navigation links or redesign the shell.

- **T013 Data Quality Profiler (Starter):** missingness, duplicate rows, types, numeric summaries and IQR review flags; read-only behavior.
- **T017 Data Join and Merge Studio (Mid-Tier Pro):** staged CSV right-hand table, explicit keys/join type/cardinality, null-key rejection, row reconciliation, and blocked many-to-many joins unless explicitly confirmed.
- **T018 Time-Series Data Processor (Mid-Tier Pro):** timestamp parsing/UTC normalization, chosen output timezone, stable sorting, invalid/duplicate timestamps, gap screening and optional declared resampling.
- **T019 Synthetic Industrial Data Generator (Starter):** seeded, reproducible synthetic operational rows; data is visibly labelled SYNTHETIC and replacing the active session dataset requires explicit confirmation.
- **T034 Acceptance Sampling Planner (Professional):** operating-characteristic probabilities for a user-specified large-lot single-sample binomial approximation, with producer/consumer risk labels. It does not claim standards certification or finite-lot correction.
- **T070 Queueing and Service-System Analyzer (Professional):** analytical steady-state M/M/1 metrics and stability guard; it is not a discrete-event simulator.
- **T082 Industrial Costing and Variance Analyzer (Mid-Tier Pro):** actual versus standard/plan component reconciliation in a declared currency, with favorable/unfavorable variance labeling.
- **T084 Engineering Project Portfolio Scorer (Professional):** visible criteria, normalized weights, min-max normalized ratings, rankings and limited one-weight-at-a-time sensitivity.

New implementation paths:
- shoir_100_tool_methods.py
- shoir_100_tool_ui.py
- tests/test_shoir_100_tool_methods.py
- Additive call sites in pages/Industrial_Engineering_Workbench.py
- Updated target records in shoir_100_tool_registry.py and docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv

The shared target execution helper rechecks canonical T001–T100 IDs, requires a non-guest actor and recognized package label, and applies the target registry's tier requirement. This does not prove that all legacy direct routes, APIs, Copilot calls or export routes have been independently audited for every bypass.

The eight targets remain IMPLEMENTED_NEEDS_VALIDATION, not VERIFIED_WORKING. Their results are session-scoped in this tranche; durable workspace persistence/re-login, cross-workspace isolation, authenticated desktop/mobile browser walkthrough, and full import/export artifact round trips remain unverified. The current matrix counts are 47 IMPLEMENTED_NEEDS_VALIDATION, 48 FOUNDATION_ONLY, 5 EXTERNAL_CONFIGURATION_REQUIRED, and 0 VERIFIED_WORKING. No claim is made that all 100 requested tools are complete.


## Additional implementation tranche — 24 October 2026

A second additive tranche expands the implementation with seven focused methods and corrects the inventory for three existing calculators:

- **T021 Time Study and Standard Time**, **T022 Work Sampling Analyzer**, **T023 Takt Time and Capacity Calculator** now reflect the existing engine/UI/test implementation in their target-matrix classifications. Their browser status is still unverified.
- **T024 Production Line Balancer:** precedence-aware largest-eligible-task heuristic with cycle-time fit, station assignments, idle time, efficiency, theoretical lower-bound stations, and a clear non-optimality caveat.
- **T028 Root-Cause Analysis Toolkit:** aggregated Pareto ranking, cumulative shares, optional exactly-five-step why chain and a proposed action/owner/due date. Causal claims are not inferred.
- **T029 5S and Workplace Audit:** structured 0–5 checklist scoring by area and category with evidence, owner, action and due-date fields.
- **T030 Kaizen/A3 Improvement Manager:** baseline, target, countermeasure, owner, due date, optional post-change measurement and evidence reference. Actual-plus-evidence remains PENDING_REVIEW; the tool does not auto-verify economic benefit.
- **T040 Quality Cost and Defect Analyzer:** scrap, rework and inspection cost decomposition under a declared currency.
- **T055 Inventory Policy Optimizer:** EOQ and demand-only safety stock/reorder-point calculations with assumptions disclosed.
- **T056 ABC/XYZ Inventory Analyzer:** value-based ABC segmentation and coefficient-of-variation XYZ classes across selected periods, with explicit thresholds.

The implementation is grouped in the existing Engineering Validation Center Workbench section to avoid adding a new primary navigation sector. Each target action uses the canonical target-ID tier gate. These records/results currently use session-scoped state; persistent audited 5S/A3 workflows and cross-workspace ownership are not implied.

The current source matrix contains 61 IMPLEMENTED_NEEDS_VALIDATION, 34 FOUNDATION_ONLY, and 5 EXTERNAL_CONFIGURATION_REQUIRED target rows. No target is marked VERIFIED_WORKING. Full CI must pass on the final head, and authenticated browser, persistence, access-bypass and export round-trip acceptance remains required before a production go decision.


## Third implementation tranche — methods surfaced inside existing Workbench (24 October 2026)

The latest additive tranche integrates additional specialist calculations into existing Workbench sections:

- **T025 Bottleneck and Constraint Analyzer:** ranks estimated station capacity using cycle time, available hours and downtime, while explicitly naming the output a bottleneck candidate.
- **T026 OEE and Loss Analysis:** reports availability, performance, quality and OEE using a shared production-time/count scope; an inconsistent performance result above 100% is not silently capped.
- **T041 Weibull Reliability Analyzer:** fits a two-parameter Weibull to positive, complete, uncensored failure times and reports B10/B50/B90. Censoring is not claimed as supported.
- **T042 MTBF and MTTR Analyzer:** uses explicit completed uptime/repair intervals in hours and records the interval availability metric.
- **T066 Cutting Stock and Bin Packing:** uses a one-dimensional first-fit-decreasing heuristic with kerf and reconciled stock/waste metrics, not a global-optimality claim.
- **T075 Forecast and Model Drift Monitor:** compares paired actual/prediction observations using bias, MAE, RMSE and MAPE with an explicit zero-actual handling rule.
- **T085 Statistical Power and Sample-Size Planner:** a stated normal approximation for two independent equally allocated group means; clustered, attrition, unequal-variance and multiple-comparison corrections are not implied.

Golden/boundary tests were added for these methods. Their corresponding matrix entries remain IMPLEMENTED_NEEDS_VALIDATION; browser acceptance, durable persistence and export/access path verification remain open. The implementation-count change reflects actual method additions and does not convert a registry entry into evidence of a fully verified tool.
