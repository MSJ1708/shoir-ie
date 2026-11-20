# Shoir-IE Master Failure Register

Assessment date: 2026-11-06. Evidence baseline: `bd76f8450c20e18aa74d9b70d0945e735aa2b804`.

## Individually recovered failures

| ID | Test | Exact failed run/SHA | Observed failure | Root cause | Correction | Retest |
|---|---|---|---|---|---|---|
| F-001 | `test_streamlit_application_starts_without_runtime_exception` | [#42192850295](https://github.com/MSJ1708/shoir-ie/actions/runs/42192850295), `fdede2716a648b031c0ed4cd6b1650e072bb0e27` | Streamlit AppTest exceeded 30-second timeout during cold startup. | The test timeout was too short for CI cold import; traceback was a timeout, not a proven application exception. | Run in disposable `tmp_path`; set bounded timeout to 120 seconds. | Pending exact-head full CI on `bd76f8450c20e18aa74d9b70d0945e735aa2b804`. |
| F-002 | `test_context_manager_rolls_back_and_closes_after_exception` | [#42192850295](https://github.com/MSJ1708/shoir-ie/actions/runs/42192850295), `fdede2716a648b031c0ed4cd6b1650e072bb0e27` | Test found `sample` table after exception. | Fixture expected transactional DDL rollback without explicit BEGIN; SQLite legacy mode does not necessarily start a transaction for DDL alone. | Add explicit `BEGIN` before CREATE TABLE/INSERT; preserve rollback and close assertions. | Pending exact-head full CI on `bd76f8450c20e18aa74d9b70d0945e735aa2b804`. |

## Historical “43 failures” reconciliation

A previous report stated 43 failures, 932 passes, 3 skips and 2 errors. The actual run ID, commit SHA, test names and full logs for that specific set were not found in the currently accessible evidence. It is marked **UNRECONCILED**, not assumed fixed. Do not merge this number with the two failures in the completed 979/2/3 result above.

## Skips and warnings

The completed run summary showed 3 skipped tests, but the inspected log did not expose a usable per-skip reason list. The updated validation workflow now requests JUnit XML and `pytest -ra`; its exact-head run is pending. No zero-skip or zero-warning claim is made.

The log included Streamlit bare-mode ScriptRunContext and LibreOffice javaldx warnings. They require classification; do not suppress them without evidence. ResourceWarnings are now configured as errors.

A failure closes only after its corrected test, affected test file/subsystem and full suite pass on the exact final SHA and the evidence is attached.


## F-003 — latest full-validation parallel regression failure (unreconciled pending exact-head retest)

| Field | Evidence |
|---|---|
| First observed head | `d1fdd47e12a0e1ef65e38413100c1e776092f8e8` |
| Workflow run | [Shoir-IE validation #44748076553](https://github.com/MSJ1708/shoir-ie/actions/runs/44748076553) |
| Job | `test` |
| Step | `Run parallel regression suite` |
| Observed state | Step completed with `failure`; serial Streamlit AppTest step continued afterwards. The engine-only run for the same SHA was cancelled by later candidate pushes. |
| Log evidence | The connected GitHub job-log download returned a BlobNotFound/404 response. No JUnit artifact was available while the job remained in progress; exact failing test names and traceback were therefore not recovered. |
| Root cause | **Unknown.** Do not assume it was only a stale static test or an infrastructure failure. |
| Retest candidate | `a5d117b8007eecf292b8b55f48ae2ab6d2244a49` |
| Exact-head validation | [#44750676974](https://github.com/MSJ1708/shoir-ie/actions/runs/44750676974), running at the time of this register update. |
| Closure rule | Obtain the new run's complete JUnit XML and job summary. Confirm the parallel regression step is green, review all failed/skipped/warning details, and rerun a corrected exact head if anything fails. Only then mark F-003 resolved. |

This record keeps the prior failure visible without assigning an unsupported root cause. The production release remains NO-GO until the current full suite and all other acceptance gates pass.


## F-004 — T063/T028 regression failures on the Engine Regression suite

| Field | Evidence |
|---|---|
| First observed head | `d9eae17a21673e0b49b53a9c27faa668a2dee587` |
| Workflow | [Engine Regression #44751546111](https://github.com/MSJ1708/shoir-ie/actions/runs/44751546111) |
| Job result | **4 failed, 537 passed** in the engine/platform acceptance selection. |
| Failures | `test_constrained_task_schedule_enforces_skills_precedence_and_resource_capacity`; `test_constrained_task_schedule_serializes_resource_and_reports_skill_infeasibility`; `test_workbench_selects_and_runs_work_sampling_and_pareto_tools`; `test_workbench_runs_weibull_spares_safety_slotting_assignment_and_energy_methods`. |
| Root causes | PuLP 3.3.2 raises a deprecation error for `PULP_CBC_CMD` and directs callers to `COIN_CMD`; the T028 AppTest asserted saved fishbone input using `json.loads` but the test module had no `json` import. The two T063 AppTests failed as a consequence of the solver error. |
| Corrections | T063 scheduler now instantiates `pulp.COIN_CMD`; `tests/test_shoir_100_tool_workbench.py` imports `json`. |
| Fix commits | `3c59ad80ef612841ebe827e8387d716e4dc491fa` (T063 solver); `fb2045bb871dd24d0b7e846af278c576800339cc` (T028 test import). |
| Retest | A subsequent exact-head run on SHA `1d6a0eabbc86b31b826af0e7a96e1588b671458f` was cancelled by later PR pushes before completion. The current candidate `cf05be0c1e95d7bcbe227b7ee0678e1c68491ca6` has a fresh Engine Regression [#44755607917](https://github.com/MSJ1708/shoir-ie/actions/runs/44755607917) running at this register update. |
| Closure rule | Inspect JUnit and confirm both T063 tests and both Workbench tests pass on the final exact HEAD. Re-run the complete suite after any correction; retain all skips/warnings for review. |

F-004 remains open until the exact final-head retest passes.

## F-005 — retired metadata-only dataset registration route

| Field | Evidence |
|---|---|
| First observed | Source review during PR #232 lease/fencing hardening, 2026-11-20. |
| Risk | `dataset_version_register` called the older metadata-only SQL RPC and could advance a dataset head without storing downloadable bytes, bypassing the supported upload/finalize flow. |
| Correction | Edge action now returns HTTP 410 after session/entitlement validation and instructs clients to use `dataset_upload_create` followed by `dataset_version_finalize`; the Python helper raises a migration error; the action was removed from the staging shared-action allowlist. A static regression contract prevents the old RPC/helper path from returning. |
| Fix commits | `97eedb0149ef86b9bd76cabd2fe5815dbd53760f`, `2756682dc05fbca45d3589197bc0bee30848559a`, `1d6a0eabbc86b31b826af0e7a96e1588b671458f`. |
| Retest | Edge formatting on the retired action was corrected in `cf05be0c1e95d7bcbe227b7ee0678e1c68491ca6`; [Edge verification #44755607682](https://github.com/MSJ1708/shoir-ie/actions/runs/44755607682) passed Deno formatting, type-checking, bounded request/security and OIDC tests. |
| Closure rule | Keep the HTTP 410/static contract and verify it in the final exact-head Edge/Python suite; do not restore the old route. |



## F-006 — security scans ran after a cancelled pre-checkout job (workflow guard defect)

| Field | Evidence |
|---|---|
| Workflow/run | [Shoir-IE validation #44755607737](https://github.com/MSJ1708/shoir-ie/actions/runs/44755607737), candidate head `cf05be0c1e95d7bcbe227b7ee0678e1c68491ca6`. |
| Job lifecycle | The disposable PostgreSQL service was still initializing. The job was cancelled before checkout; checkout, setup-python, dependency installation, compilation and test steps were skipped. |
| Misleading downstream steps | `pip-audit -r requirements.txt` still ran under `if: always()` and reported invalid requirements input because the repository had not been checked out. The hard-coded credential scan also ran and failed with `FileNotFoundError: app.py`. |
| Root cause | Missing `steps.checkout.outcome == 'success'` precondition on repository-file scans, combined with a cancelled pre-checkout job. This run does **not** establish a dependency vulnerability or credential leak. |
| Correction | Validation workflow now gives the initial checkout an explicit `id: checkout` and both repository-file scans run only when checkout succeeded. The subsequent browser-smoke checkout remains separate. Real scanner findings still fail the job normally. |
| Fix commit | Recorded by this workflow-guard correction commit; exact-head retest required. |
| Closure rule | Run validation on the corrected exact HEAD. Confirm checkout/dependency install pass, pip-audit parses the real requirements file, credential scan runs against present files and reports no obvious literal secrets, and all other test/export/viewport stages complete with inspectable artifacts. |

F-006 remains open until the corrected full validation passes.


## F-007 — cancelled validation runs continued expensive AppTest and browser stages

| Field | Evidence |
|---|---|
| Observed run | [Shoir-IE validation #44756017414](https://github.com/MSJ1708/shoir-ie/actions/runs/44756017414), candidate SHA `6b83b2a97823b400f6e38b67719e06334b95f2a3`. |
| Run behaviour | A newer PR push cancelled the parallel regression step, but the serial Streamlit AppTest stage continued under `if: always() && steps.compile.outcome == 'success'`. This held the single validation job in progress and left later exact-head validation runs queued. |
| Root cause | Heavy diagnostic steps used `always()` without `!cancelled()`; GitHub correctly cancelled the prior test step but downstream stages deliberately continued. |
| Correction | The validation workflow now guards expensive test, dependency, Deno, export-render, import-smoke and browser-smoke stages with `!cancelled()`. Artifact uploads and container cleanup remain unconditional to preserve evidence and release resources. |
| Fix commit | Recorded by the workflow cancellation-guard correction commit; exact-head retest required. |
| Closure rule | Confirm a cancelled superseded run does not start another long test/render/browser stage; confirm the new exact-head validation completes all stages normally and uploads JUnit/export/browser evidence. |

F-007 remains open until the workflow retest confirms cancellation propagation and exact-head full validation passes.
