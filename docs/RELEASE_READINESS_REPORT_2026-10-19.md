# Shoir-IE Release Readiness Report — 2026-10-19

## Current release decision

**NO-GO — Shoir-IE is not yet verified as workforce-ready for real industrial data or production use.**

This report reflects the current repository head and a read-only check of the connected Supabase production project. It supersedes earlier point-in-time statements in this file that describe PR #145 as unmerged or treat an older browser-smoke failure as the latest deployment result.

- **Repository `main`:** [`e4dea7729568447f6fcb9c1de45e19c02a31dd46`](https://github.com/MSJ1708/shoir-ie/commit/e4dea7729568447f6fcb9c1de45e19c02a31dd46)
- **Latest merged smoke-harness change:** [PR #152](https://github.com/MSJ1708/shoir-ie/pull/152)
- **Hosted-smoke trigger repair:** [PR #153](https://github.com/MSJ1708/shoir-ie/pull/153) is open and must not be treated as merged or deployed.
- **Production application revision:** UNVERIFIED. The public endpoint alone does not identify the Streamlit Cloud Git SHA.
- **Production database migration state:** the atomic subscription-decision migration is NOT applied.
- **Protected master administrator:** verified through a read-only production query; invariant unchanged.

The principal blockers are a deployed Edge Function/source mismatch, no available isolated staging branch for full migration replay, no authenticated release-gate evidence, incomplete per-module acceptance, and no hosted smoke pass established for the exact final release/deployment revision.

## Evidence collected for this assessment

### Current GitHub checks

| Gate | Outcome | Evidence and scope |
|---|---|---|
| Python validation and local runtime smoke | **PASS for the run; hosted job skipped** | [Validation run 39291301552](https://github.com/MSJ1708/shoir-ie/actions/runs/39291301552): compilation, regression tests, required-module parsing, top-level import smoke, local Streamlit startup, and local desktop/mobile smoke completed successfully. The separate `live-deployment-smoke` job concluded `skipped`. |
| Security and quality | **PASS for automated checks** | [Run 39291301605](https://github.com/MSJ1708/shoir-ie/actions/runs/39291301605): compilation, regression tests, dependency audit and secret-pattern guard completed successfully. This is not an independent penetration test or certification. |
| Engine regression | **PASS for the run** | [Run 39291301735](https://github.com/MSJ1708/shoir-ie/actions/runs/39291301735). This does not replace independent calculation reference cases or module-specific end-to-end acceptance. |
| Earlier anonymous hosted smoke | **PASS on an earlier candidate only** | [Run 39287236351](https://github.com/MSJ1708/shoir-ie/actions/runs/39287236351) passed desktop/mobile registration and public module-explorer checks on an earlier commit. It is not evidence that the final `main` revision is deployed or served. |
| Hosted smoke after merge | **NOT VERIFIED for the final revision** | The post-merge validation above skipped its hosted-smoke job. PR #153 proposes running this anonymous, read-only smoke on `main` pushes and enabling manual dispatch. A shell smoke will still not establish the deployed Git SHA by itself. |

### Production Supabase — read-only inspection

| Check | Observed result | Release meaning |
|---|---|---|
| Project health | `shoir-ie-production` reports `ACTIVE_HEALTHY`; PostgreSQL 17.6.1.166 | Health alone is not evidence of migration compatibility or account-flow correctness. |
| Active persistence Edge Function | `shoir-persistence`, version 8; reported source fingerprint `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d` | Deployed code does not match all current source-level release requirements. |
| Registration / atomic decisions | Current `main` Edge Function source contains `account_exists`, `register_request` and the subscription-finalization RPC path. The deployed version 8 source retrieved from production does **not** expose those actions; it still contains the older separate account/request approval writes. | **CRITICAL BLOCKER:** do not deploy the new Edge Function independently of its database migration. |
| Production migration history | Includes `20261019124815 server_side_login_rate_limits`; does not include `20261019140600_atomic_subscription_request_decisions` | The candidate atomic-decision migration has not been applied to production. The login-throttle repository filename/version discrepancy also needs reconciliation before future migration rollout. |
| Existing staging/development branches | None returned by the current Supabase branch listing | Full production-matched staging replay is **BLOCKED**. No paid branch/project was created as part of this audit. |
| Master administrator invariant | Read-only result: active `true`; role `Enterprise Admin`; tier `Enterprise Plus Tier ($399)`; expiry `2099-01-01 00:00:00+00` | **PASS.** No password, identity, role, workspace, tier, expiry, or account data was modified. No admin account was used for testing. |
| Production mutation boundary | No migration or Edge Function deployment was performed during this audit | Production remains on the observed version 8 function and listed migration history. |

### Module inventory and actual workforce acceptance

The source-level entitlement audit and machine-readable inventory identify **96 unique module names**. This is a canonical source inventory count only; it does not establish that all module renderers, calculations, authorization paths, exports, or persistence functions work.

The inventory file `docs/MODULE_TIER_INVENTORY.csv` records `authenticated_browser_status=UNVERIFIED` for every listed module. Therefore:

- **96-module authenticated browser matrix:** NOT RUN / OPEN.
- **Independent calculation reference-case matrix:** NOT established as complete.
- **Real XLSX/CSV import and export round trips:** NOT established as complete.
- **PDF/PowerPoint reopen-and-content verification:** NOT established as complete.
- **Tier-by-tier allowed and denied direct-operation tests:** NOT established as complete.
- **Cross-user persistence and tenant-isolation acceptance:** NOT established as complete.

The public shell smoke covers only the anonymous entry surface, registration fields, and public explorer sections. It is not a substitute for these gates.

### Account lifecycle and authenticated release gate

**BLOCKED / NOT VERIFIED.** No successful current run of the documented [Authenticated Release Gate](AUTHENTICATED_RELEASE_GATE.md) with dedicated disposable `shoir-e2e-*` accounts and protected CI secrets was established by this audit.

Static tests and source inspection do not prove live authentication, expiry/renewal behavior, private payment-proof access, administrator review, logout revocation, workspace save/re-login/restore, or denied cross-tenant requests. Do not use the protected administrator or real customer accounts to fill this gap.

### Staging migration and recovery

**BLOCKED.** The migration `supabase/migrations/20261019140600_atomic_subscription_request_decisions.sql` exists in source, but production migration history does not record it and the connected project has no existing development branch. The isolated PostgreSQL transaction test is not a full migration-history replay against a production-matched staging schema.

Before any production rollout, the authorized owner must make an isolated staging environment available and approve any associated cost. Then replay the complete migration history, validate RPC signatures/grants and transaction/concurrency cases, validate the matching Edge Function, and document/test recovery. Only after those gates pass may the production migration/function deployment sequence be considered. **Do not deploy the new function alone or apply this migration to production as a test.**

## Release gate matrix

| Required gate | Status | Evidence needed to close |
|---|---|---|
| Current `main` and latest CI baseline | **PARTIAL PASS** | Re-read exact SHA and all required checks at final go/no-go; ensure no pending, failed, skipped-without-approval, or stale required check remains. |
| Public hosted desktop/mobile entry screen | **PARTIAL / STALE FOR FINAL REVISION** | Run the hosted smoke after deployment of the intended candidate; record observed build identity where the platform exposes it. |
| Startup and local browser smoke | **PASS for latest recorded validation run** | Preserve run artifact and rerun on later code revisions. |
| All 96 modules and legacy routes | **OPEN** | Execute every inventory case with real outputs and evidence on the reviewed SHA. |
| Calculation correctness | **OPEN** | Independently computed reference fixtures, edge cases, units, reproducibility and provenance checks. |
| Tier/role enforcement and tenant isolation | **OPEN** | Authenticated positive and negative tests at the authoritative operation boundary, including cross-user identifiers and exports. |
| Registration, login, expiry, renewal, approve/decline, logout and restoration | **BLOCKED / NOT VERIFIED** | Run authenticated gate using authorized disposable accounts and redacted artifacts. |
| Production-matched staging migration replay | **BLOCKED** | Authorized isolated staging environment, full replay/upgrade validation, concurrency and recovery proof. |
| Deployed Edge Function compatibility | **FAIL / MATERIAL DRIFT** | Deploy only after staging replay and release approval; then verify deployed source/actions match the reviewed main SHA and migration. |
| File import/export integrity and persistence | **OPEN** | Reopen generated files and verify contents; prove save/reload after logout/login and restart. |
| Security posture | **PARTIAL PASS** | Automated checks pass, but full boundary review, authenticated negative tests, residual-risk disposition and independent security validation appropriate to customer scope remain incomplete. |
| Backup, restore, monitoring and rollback | **OPEN** | Evidence-backed, usable procedures tested in a non-production environment. |
| Workforce handover and production approval | **OPEN** | Complete release package, accepted risks, support ownership and formal production authorization. |

## Immediate go/no-go conditions

1. Keep the release **NO-GO** until the deployed Edge Function and database schema are compatible.
2. Review PR #153 and require its CI results before merge. Its purpose is to prevent post-merge hosted smoke from silently skipping; it is not an application-feature fix.
3. Obtain explicit authorization for any paid staging environment if no existing authorized non-production environment is available.
4. Run full migration replay, transaction/concurrency tests, authenticated release gate, tenant-isolation matrix, module matrix, and import/export/persistence round trips.
5. Verify the actual Streamlit-served revision and repeat public smoke after the intended deployment.
6. Publish the final evidence matrix with exact SHA, environment, timestamps, run URLs and outcomes. A blocked or unrun case must remain `BLOCKED` or `NOT RUN`, never `PASS`.

## Final assessment

**The current candidate is not workforce-ready for the defined scope.** Compilation, regression, engine checks, dependency scanning and local desktop/mobile runtime smoke passed in the listed CI runs. However, the production persistence Edge Function is behind the current source contract, its required atomic-decision migration is absent from production migration history, no staging branch is available for replay, the hosted smoke was skipped on the latest recorded post-merge validation, and authenticated workforce/module acceptance remains unverified.

No protected administrator or customer record was modified during this assessment. No production migration, Edge Function deployment, paid staging resource or production rollout was initiated.
