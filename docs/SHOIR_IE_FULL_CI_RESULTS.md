# Shoir-IE Full CI Results

Assessment date: 2026-11-06. Candidate SHA: `bd76f8450c20e18aa74d9b70d0945e735aa2b804`.

## Current candidate workflows

| Workflow | Run | Status |
|---|---|---|
| Validation | [#42244270608](https://github.com/MSJ1708/shoir-ie/actions/runs/42244270608) | In progress at last inspection |
| Duplicate validation | [#42244259985](https://github.com/MSJ1708/shoir-ie/actions/runs/42244259985) | In progress at last inspection |
| Edge Function | [#42244270607](https://github.com/MSJ1708/shoir-ie/actions/runs/42244270607) | Success |
| Excel Intelligence | [#42244270603](https://github.com/MSJ1708/shoir-ie/actions/runs/42244270603) | Success |
| Engine Regression | [#42244259986](https://github.com/MSJ1708/shoir-ie/actions/runs/42244259986) | Success |
| Subscription Transaction | [#42244270744](https://github.com/MSJ1708/shoir-ie/actions/runs/42244270744) | Success |

The current full suite had not completed when this report was prepared; therefore current pass/fail/error/skip/warning totals are unknown and no exact-head full-suite pass is claimed.

## Last completed full-suite result

Run [#42192850295](https://github.com/MSJ1708/shoir-ie/actions/runs/42192850295), SHA `fdede2716a648b031c0ed4cd6b1650e072bb0e27`: **979 passed, 2 failed, 3 skipped, 5 subtests passed**, 3683.27 seconds. See `SHOIR_IE_MASTER_FAILURE_REGISTER.md`.

## CI improvements on candidate

`.github/workflows/shoir-validation.yml` now sets a 120-minute job timeout; emits JUnit XML; runs pytest with `-ra`; treats ResourceWarning, DeprecationWarning and FutureWarning as errors; and continues independent checks when their prerequisites pass, even after an unrelated test failure. These are observability/control improvements, not test results.

## Artifacts

Earlier synthetic PDF/PPTX artifact: [`shoir-ie-report-export-validation`, artifact 13498317249](https://github.com/MSJ1708/shoir-ie/actions/runs/42192850295/artifacts/13498317249).

## Required finalization

Inspect current JUnit XML after completion; reconcile every skip and warning; fix every current failure; rerun affected suites and the full suite on the resulting SHA; verify migration replay, Deno, exports, browser screenshots and authenticated staging acceptance. Do not treat skipped live smoke or component workflows as authenticated release acceptance.
