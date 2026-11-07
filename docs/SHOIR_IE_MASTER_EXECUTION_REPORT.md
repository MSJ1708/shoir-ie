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

The current CSV contains 100 targets: **0 VERIFIED_WORKING, 88 IMPLEMENTED_NEEDS_VALIDATION, 10 FOUNDATION_ONLY, 2 EXTERNAL_CONFIGURATION_REQUIRED**. Foundation-only: T006, T039, T044, T046, T060, T074, T080, T094, T097, T099. External: T096 and T098.

## Main incomplete areas

- Organisation migration is source-only; staging has zero org tables and deployed v13 Edge Function has no org/membership/invitation actions.
- Dataset versioning is partially present but raw XLSX retention, resumable uploads, orphan cleanup, downstream stale invalidation and hosted lifecycle acceptance remain open.
- Digital Thread needs managed save/reload/lineage and organisation-scope acceptance.
- T096 is a mapping adapter with injected transport, not a live SAP/Oracle connection.
- T098 is a draft OIDC/audit implementation with no configured identity provider/MFA tenant.
- Visual, RTL and authenticated browser acceptance is incomplete.
- Qualified engineering review, PDPL/legal review, SBOM/licence clearance, backup restore rehearsal and production rollout approval are open.

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