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

- `IMPLEMENTED_NEEDS_VALIDATION`: 39
- `FOUNDATION_ONLY`: 56
- `EXTERNAL_CONFIGURATION_REQUIRED`: 5

No entry is marked `VERIFIED_WORKING`. The CSV includes one row for each stable tool ID T001–T100 and all required matrix columns. It distinguishes candidate existing routes from a verified implementation; a candidate mapping is not proof that the target acceptance contract is met.

## Important scope and evidence limitations

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
