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
