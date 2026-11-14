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


## Additional CORS recheck — 2026-11-06

A read-only inspection of the deployed production persistence Edge Function v9 found a response header hard-coded as `Access-Control-Allow-Origin: *`. The deployed staging v13 helper uses an explicit allowlist, but its previous source allowlist included production and staging hosts together. The candidate now binds allowed origins to the exact Supabase project ref: production permits only `https://shoir-ie-app.streamlit.app`; staging permits the configured staging Streamlit hosts and local development origins; an unknown project fails closed; origin-less server-to-server requests remain supported and still require session/action authentication. Cross-environment CORS regression tests were added.

Dedicated Edge Function verification [run #42251683171](https://github.com/MSJ1708/shoir-ie/actions/runs/42251683171) on SHA `cf806aad170916f7e1003a3ef92ffbda2195899c` passed: Deno format checked 3 files, Deno type-check passed, and the security test suite reported **13 passed, 0 failed**. This source fix is not deployed. Production remains on v9 and continues to return wildcard CORS until a reviewed coordinated production rollout is explicitly approved. Do not treat this as a production remediation already applied.

## Live exact-head recheck — 2026-11-07

Source baseline under review: `bb08df77b8b3f7f3eb14159f852d757e33834188`. The six workflows triggered for this source baseline were still queued at the latest check; none is a completed pass or failure:

| Workflow | Run | Last observed state |
|---|---:|---|
| Shoir-IE validation | 42408321586 | queued |
| Clean PostgreSQL migration-history replay | 42408321582 | queued |
| Edge Function verification | 42408321617 | queued |
| Excel Intelligence | 42408321580 | queued |
| Subscription transaction integration | 42408321585 | queued |
| Production v9 security-backport verification | 42408321591 | queued |

The hosted live-smoke sub-job in the validation workflow was skipped. The local desktop/mobile Streamlit smoke in CI is not authenticated staging acceptance. The current tool connection cannot dispatch the protected authenticated-release workflow; no bypass or customer/admin account was used. Earlier run IDs and earlier SHA results are historical only. The next valid evidence is the completed run output, job logs, skip/warning report and generated artifacts for the final exact candidate SHA.

## Latest exact source/test commit check — 2026-11-07 19:58 UTC

Functional source changes were last reviewed at `bb08df77b8b3f7f3eb14159f852d757e33834188`. The latest test and regression-assertion commit is `e19550222e6175d1d454b1169dc3a009185d1eea`.

Workflows started for `e19550222e6175d1d454b1169dc3a009185d1eea`:

| Workflow | Run | Last observed state |
|---|---:|---|
| Shoir-IE validation | 42408718226 | queued |
| Clean PostgreSQL migration-history replay | 42408718288 | queued |
| Edge Function verification | 42408718193 | queued |
| Excel Intelligence | 42408718217 | queued |
| Subscription transaction integration | 42408718177 | queued |
| Production v9 compatibility security backport | 42408718191 | queued |
| Engine Regression | 42408714750 | queued |

GitHub also created duplicate validation and migration-replay runs `42408714711` and `42408714679` for the same head because of the workflow event triggers; these were queued as well. The validation workflow's `live-deployment-smoke` job was skipped. There is no exact-head pass or failure to report yet. These states are time-bounded and must be refreshed before deployment.
