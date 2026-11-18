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


## Exact-head technical recheck — 2026-11-18

Candidate branch: feat/shoir-ie-release-hardening-20261105; previous exact head inspected: b43571cacdfa791d1417ca73ee10e572028f61f2; PR #232 remains draft and targets staging-e2e-20261019.

### Completed component checks on that head

- Engine Regression [#43929726907](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726907): **521 passed, 0 failed**.
- Edge Function [#43929726898](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726898): **14 passed, 0 failed**.
- Clean PostgreSQL migration replay [#43929726989](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726989): **2 passed** on a disposable local PostgreSQL 17 database; this is not a hosted Supabase replay.
- PostgreSQL transaction contract [#43929726919](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726919): success.
- Production-v9 security backport [#43929726914](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726914): **5 passed, 0 failed**.
- Excel Intelligence [#43929726920](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726920): **38 Python tests and 9 Node planner tests passed**. The manifest check correctly warns that the Office add-in is an unhosted template, not an installable deployment.
- Security/quality [#43929726900](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726900): dependency audit reported no known vulnerabilities.

### Full validation did not pass

The full workflow [#43929726913](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726913) was cancelled at the 120-minute job limit. Its pytest output reached about 40% and displayed three failure markers before cancellation; it produced no JUnit report or final traceback, so the failing test names and total failure/skip counts are **unknown**. Do not call this a passing or fully diagnosed run.

After the regression process was cancelled, independent steps still completed successfully: active and production-v9 Deno format/type/security validation, dependency audit, hard-coded credential-pattern guard, synthetic PDF/PPTX render step, application import smoke (57 top-level statements), and local Playwright public-entry smoke at desktop/tablet/mobile sizes. The in-workflow PostgreSQL/Node steps were skipped by their default success condition; the separate PostgreSQL/Edge/Excel workflows listed above are separate evidence, not a substitute for the complete validation job.

### CI corrections now added to the candidate

The full-validation workflow now uses four-worker file-isolated pytest execution; a 10-minute per-test timeout with verbose names; serial execution of the two shared-PostgreSQL test modules to avoid role/database races; separate JUnit XML reports; independent PostgreSQL and Node/Excel checks that still run after regression failures; a 180-minute outer job limit; and Node 24 with actions/setup-node v7. These workflow changes are **not** a passing test result. The new exact-head run must complete and its JUnit reports must be inspected before this is marked green. The per-test timeout may expose further defects, which must be fixed rather than waived.
