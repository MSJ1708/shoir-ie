# Shoir-IE Master Execution Report

Assessment date: 2026-11-06  
Evidence baseline SHA: `bd76f8450c20e18aa74d9b70d0945e735aa2b804`  
Candidate: PR [#232](https://github.com/MSJ1708/shoir-ie/pull/232), branch `feat/shoir-ie-release-hardening-20261105`, base `staging-e2e-20261019`.  
Decision: **NO-GO — RELEASE NOT AUTHORISED**.

## Executive outcome

The ultimate master prompt is **not fully implemented or accepted**. Code exists for some major workstreams, but multiple mandatory integration, hosted acceptance, external provider, legal and independent review gates remain open.

The latest completed full-suite run inspected, [#42192850295](https://github.com/MSJ1708/shoir-ie/actions/runs/42192850295), ran on `fdede2716a648b031c0ed4cd6b1650e072bb0e27` and reported **979 passed, 2 failed, 3 skipped, 5 subtests passed**. The two failures were an AppTest cold-start timeout and an SQLite DDL rollback fixture that did not explicitly start a transaction. Test corrections are now on the candidate SHA `bd76f8450c20e18aa74d9b70d0945e735aa2b804`; a new full-suite run is still in progress, so those corrections are not yet marked VERIFIED.

## Repository state

| Item | Value |
|---|---|
| `main` | `2ef44057f84162389d39998e922b505dcfe4d3e9` (protected) |
| `staging-e2e-20261019` | `f00da78a01e2ecf07fe263ddf570cbc1e075ac31` (protected) |
| PR #232 head | `bd76f8450c20e18aa74d9b70d0945e735aa2b804` (draft, open) |
| PR #232 base | `staging-e2e-20261019` |
| Open PRs | 34 |
| Current full validation | [#42244270608](https://github.com/MSJ1708/shoir-ie/actions/runs/42244270608), in progress at last inspection |

Supporting workflows on `bd76f8450c20e18aa74d9b70d0945e735aa2b804`: [Edge #42244270607](https://github.com/MSJ1708/shoir-ie/actions/runs/42244270607), [Excel #42244270603](https://github.com/MSJ1708/shoir-ie/actions/runs/42244270603), [Engine Regression #42244259986](https://github.com/MSJ1708/shoir-ie/actions/runs/42244259986), and [Subscription Transaction #42244270744](https://github.com/MSJ1708/shoir-ie/actions/runs/42244270744) were successful. Component passes are not full release acceptance.

## Live Supabase comparison

| State | Staging | Production |
|---|---:|---:|
| Project | `hfhrosthswcybccepmak` | `gcsamrdaeraxieaagsta` |
| DB version | PostgreSQL 17.11 | PostgreSQL 17.6 |
| Applied migrations | 23 | 14 |
| Persistence Edge Function | v13 | v9 |
| Legal-acceptance columns | Present | Missing |
| 12 `shoir_internal` tables RLS | Enabled | Disabled |
| Organisation tables from 20261106120000 | 0 | 0 |

Production `shoir_internal` also has no schema USAGE and no direct table SELECT/INSERT grants for browser roles in the inspected grants, so this evidence does not show direct browser access. Production is nevertheless behind staging in RLS posture and schema/function parity and must be reviewed before deployment.

Aggregate-only administrator checks returned exactly one matching reserved Enterprise Administrator in each project: role Enterprise Admin, Enterprise Plus Tier ($399), active and expiry 2099-01-01T00:00:00Z. No administrator account was used for testing or changed.

## 100-tool matrix

The current canonical CSV contains 100 targets: **96 IMPLEMENTED_NEEDS_VALIDATION, 4 EXTERNAL_CONFIGURATION_REQUIRED (T096–T099), and 0 VERIFIED_WORKING**. No target is promoted to verified from source presence, a synthetic fixture or local AppTest alone.

## Main incomplete areas

- Organization/shared workspace schema, membership lifecycle and authenticated Owner/Admin/Engineer/Approver/Viewer acceptance still require a reviewed staging deployment and disposable multi-user tests.
- Dataset versioning now has resumable TUS upload, lease/fencing-protected finalization, a manual reference-aware orphan sweep, and Industrial Intelligence stale-dependency invalidation in source. The two lifecycle/fencing migrations remain candidate-only; hosted TUS/fresh-session/tenant/export acceptance and raw-workbook preservation remain open.
- Digital Thread has version-aware dependency/stale-node foundations; managed save/reload/re-login, rename preservation, organization-scope and exact-version browser acceptance remain open.
- T096 requires a selected real ERP/provider, vendor-specific adapter work, authorized sandbox and read-only credential.
- T097 requires an approved hosted API domain/gateway and an externally consumed, versioned SDK; it is not configuration-only.
- T098 requires a real non-production OIDC/MFA provider, deployed staging audit store and positive/negative hosted tests.
- T099 requires database and Storage-byte backup/restore evidence, an isolated restore rehearsal and measured RPO/RTO.
- Visual/RTL and authenticated browser acceptance, qualified Industrial Engineering/security/infrastructure reviews, Saudi privacy/legal review, SBOM/licence/asset clearance and production approval remain open.


Detailed evidence is in the acceptance reports in this directory. This report records the observed state; it does not claim completion from source code alone.


## Additional CORS recheck — 2026-11-06

A read-only inspection of the deployed production persistence Edge Function v9 found a response header hard-coded as `Access-Control-Allow-Origin: *`. The deployed staging v13 helper uses an explicit allowlist, but its previous source allowlist included production and staging hosts together. The candidate now binds allowed origins to the exact Supabase project ref: production permits only `https://shoir-ie-app.streamlit.app`; staging permits the configured staging Streamlit hosts and local development origins; an unknown project fails closed; origin-less server-to-server requests remain supported and still require session/action authentication. Cross-environment CORS regression tests were added.

Dedicated Edge Function verification [run #42251683171](https://github.com/MSJ1708/shoir-ie/actions/runs/42251683171) on SHA `cf806aad170916f7e1003a3ef92ffbda2195899c` passed: Deno format checked 3 files, Deno type-check passed, and the security test suite reported **13 passed, 0 failed**. This source fix is not deployed. Production remains on v9 and continues to return wildcard CORS until a reviewed coordinated production rollout is explicitly approved. Do not treat this as a production remediation already applied.

## Live recheck — 2026-11-07 (supersedes earlier baseline where different)

Functional source baseline reviewed: `bb08df77b8b3f7f3eb14159f852d757e33834188`. This is a status/documentation correction; it does not claim the application or Edge Function has been deployed.

- Staging Supabase `hfhrosthswcybccepmak` is ACTIVE_HEALTHY, PostgreSQL 17.11, with 24 migration versions through `20261107120637`. The base organization migration is applied: five organization tables exist, RLS is enabled, and the checked organization RPCs are service-role-only. There are 9 personal organizations/9 owner memberships, but 0 team workspaces, 0 invitations and 0 organization audit events.
- Staging `shoir-persistence` is v14. Its deployed `index.ts` is behind the reviewed candidate source, which contains organization suspend/restore, close and shared-workspace revision-state handlers. Its deployed `security.ts` matches the candidate.
- The candidate has three new organisation migrations not yet applied: `20261107150000`, `20261107153000`, `20261107160000`. The last includes seven account-reference FK indexes plus the shared-state updater index. No staging migration or function deployment has been made in this recheck.
- Migration ledger comparison is aligned for all currently applied versions. The staging refund-policy v2 SQL recorded as `20261025164602` exactly matches the repository source; the candidate source/tests now use that recorded version. Four local-only migration versions remain: safe idempotent referral replacement `20261026110000` and the three organization migrations.
- Production remains at migration `20261019140600` and Edge v9. It was not changed.
- Matrix status is 100 canonical tools: 96 `IMPLEMENTED_NEEDS_VALIDATION`, 4 `EXTERNAL_CONFIGURATION_REQUIRED` (T096–T099), 0 `VERIFIED_WORKING`.
- Exact-head workflows for the source baseline above were queued at the last inspection: validation `42408321586`, migration replay `42408321582`, Edge `42408321617`, Excel `42408321580`, subscription `42408321585`, production-v9 backport `42408321591`. None is recorded as passed. The hosted smoke job was skipped; authenticated staging acceptance is still outstanding.

Release status remains **NO-GO**. Source implementation and automated tests are not equivalent to hosted authenticated acceptance, independent engineering review, legal review or disaster-recovery evidence. Keep BETA and do not deploy production.

## Live technical status recheck — 2026-11-18

The latest inspected PR #232 head was b43571cacdfa791d1417ca73ee10e572028f61f2, still open/draft against staging-e2e-20261019. Component evidence on that head: Engine Regression 521 passed; Edge Function 14 passed; clean local PostgreSQL 17 migration replay 2 passed; PostgreSQL transaction contract passed; production-v9 backport 5 passed; Excel Intelligence 38 Python and 9 Node planner tests passed; dependency audit found no known vulnerabilities.

The full validation run [#43929726913](https://github.com/MSJ1708/shoir-ie/actions/runs/43929726913) was cancelled at the 120-minute timeout around 40% pytest progress. Three test failure markers appeared before cancellation, but no JUnit report or final traceback was generated. It is not a passing full-suite result. Independent Deno format/type/security, dependency, credential-pattern, synthetic export render, application import and local responsive public-entry smoke steps completed. The new CI revision splits the main suite into four file-isolated workers, retains the two shared-PostgreSQL tests in a serial step, adds a per-test timeout/verbose diagnostics, and ensures independent checks are not skipped after a regression failure. The rerun must still pass.

The canonical 100-tool source matrix remains 96 IMPLEMENTED_NEEDS_VALIDATION, 4 EXTERNAL_CONFIGURATION_REQUIRED (T096–T099) and 0 VERIFIED_WORKING. Staging has 24 applied migration versions through 20261107120637 and persistence v14; production has 14 versions through 20261019140600 and persistence v10. Five organization tables and six legal-acceptance columns exist in staging but not production; internal-schema RLS is enabled in staging and disabled in production. No migration/function/app deployment was performed. Production cutover remains blocked pending a safe tested migration-history reconciliation (the historical legal/referral migration rewrites account affiliate codes and updated_at), recovery evidence, exact-head CI, independent review and authenticated staging acceptance.

Detailed technical evidence and the next hand-off steps are in docs/SHOIR_IE_TECHNICAL_HANDOFF_20261118.md. Keep BETA / NO-GO.


## Repository engineering refresh — 2026-11-20

PR #232 now contains the two dataset lifecycle lease/fencing migrations, the matching Edge Function, the T020 operator sweep, retirement of metadata-only dataset registration, and the T028/T041/T054/T063/T075/T085 Workbench changes. The T063 solver now uses PuLP `COIN_CMD`; the T028 AppTest imports `json` for its saved fishbone-input assertion.

The current candidate has not yet completed all exact-head CI. One earlier Engine Regression run found four failures (two T063 tests and two related T028/T063 Workbench tests); those known causes were corrected and the exact-head replacement must pass. Another candidate's Edge format-only failure was corrected and the new Edge check passed. Do not treat those prior passes as current-head acceptance.

Read-only Supabase inventory still reports staging Edge v14 and production Edge v10. The connected migration-history query could not authenticate, so the live migration ledger requires authorized operator verification. No staging/production migration, Edge deployment, secret change or PR merge has been performed.
