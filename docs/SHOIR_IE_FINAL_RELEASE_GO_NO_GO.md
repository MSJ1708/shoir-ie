# Shoir-IE Final Release GO / NO-GO

Assessment date: 2026-11-06. Evidence baseline: `bd76f8450c20e18aa74d9b70d0945e735aa2b804`.  
Decision: **NO-GO — RELEASE NOT AUTHORISED**.

| Mandatory gate | Current evidence | Decision |
|---|---|---|
| Full suite exact SHA | Latest run #42244270608 still in progress; prior completed run had 2 failed, 3 skipped | BLOCKED |
| Historical 43 failures | Exact run/test inventory not recovered | BLOCKED |
| Zero unexplained skips/warnings | Current JUnit -ra result pending | BLOCKED |
| SQLite lifecycle | Test corrections committed; current suite retest pending; additional concurrency/WAL coverage required | IN PROGRESS |
| Organisation lifecycle | Migration source-only; staging has zero organisation tables; Edge has no organisation actions | FAIL |
| Dataset lifecycle | Partial staging support; resumable upload/orphan cleanup/downstream invalidation/hosted E2E open | IN PROGRESS |
| Digital Thread | Canonical identity foundation; managed org lineage acceptance open | IN PROGRESS |
| T096 | No live SAP/Oracle transport or sandbox evidence; 22 cases NOT RUN | BLOCKED |
| T098 | Draft PR #223; no configured IdP/MFA hosted test | BLOCKED |
| Security and DB parity | Stage v13/23 migrations; prod v9/14; production legal columns absent and internal RLS off | BLOCKED |
| Visual/RTL acceptance | Full 25-screen, 3-viewport authenticated evidence not established | BLOCKED |
| Export | Synthetic PDF/PPTX parser/render evidence; full authenticated XLSX/PDF/PPTX flow open | IN PROGRESS |
| Engineering calculations | 0 verified, 88 need validation, 10 foundation-only, 2 external | BLOCKED |
| PDPL/legal/operator | Verified operator identity and qualified sign-off absent | BLOCKED |
| Third-party provenance | SBOM/licence/assets/ownership/trademark evidence incomplete | BLOCKED |
| Backup/restore | PITR and restore rehearsal not verified | BLOCKED |
| Independent review | Final security/privacy/engineering sign-offs absent | BLOCKED |
| Production rollout approval | No explicit authorised coordinated deployment | BLOCKED |

## Completion sequence

1. Finish [validation run #42244270608](https://github.com/MSJ1708/shoir-ie/actions/runs/42244270608) and duplicate #42244259985; inspect JUnit, resolve all failures/skips/warnings, then rerun full suite on exact SHA.
2. Review/replay organisation migration in clean PostgreSQL 17, apply to staging after approval, add session-derived Edge actions and wire existing team workspace UI. Test three disposable users, roles, invitations, ownership transfer, removals and cross-tenant denial.
3. Finish dataset orphan cleanup, retention/deletion, downstream invalidation and hosted historical version/hash tests; preserve raw XLSX separately through Excel Intelligence.
4. Integrate Digital Thread managed identity/lineage and prove save/reload/re-login, rename preservation, exact version references and stale dependent outputs.
5. Complete T096 secure provider-aware GET transport and obtain real SAP/Oracle non-production tenants and scoped credentials.
6. Complete T098 independent review, staging IdP configuration, real MFA semantics and hosted positive/negative/replay/audit tests.
7. Complete authenticated visual and export acceptance, including 1440/768/390, RTL where supported, all charts, workbook round-trip and PDF/PPTX rendered-page review.
8. Validate all marketed calculations against independent reference cases and qualified IE review; resolve 10 foundation-only targets or keep them honestly unavailable.
9. Obtain verified operator details, working support/refund process, PDPL/privacy review, SBOM/licence/asset clearance and engineering sign-offs.
10. Reconcile staging/production schema and Edge Function, inspect CORS/RLS/grants, verify backup/PITR, rehearse restore and prepare one coordinated rollback-capable production bundle.
11. Obtain independent review against exact final SHA and explicit production rollout approval.

No production migration, Edge Function deployment, app deployment or customer-data mutation was performed. The protected administrator aggregate invariant was verified in both environments and was not modified.

**NO-GO — RELEASE NOT AUTHORISED.** Change this decision only when every mandatory gate is PASS and the required approval evidence is attached.


## Additional CORS recheck — 2026-11-06

A read-only inspection of the deployed production persistence Edge Function v9 found a response header hard-coded as `Access-Control-Allow-Origin: *`. The deployed staging v13 helper uses an explicit allowlist, but its previous source allowlist included production and staging hosts together. The candidate now binds allowed origins to the exact Supabase project ref: production permits only `https://shoir-ie-app.streamlit.app`; staging permits the configured staging Streamlit hosts and local development origins; an unknown project fails closed; origin-less server-to-server requests remain supported and still require session/action authentication. Cross-environment CORS regression tests were added.

Dedicated Edge Function verification [run #42251683171](https://github.com/MSJ1708/shoir-ie/actions/runs/42251683171) on SHA `cf806aad170916f7e1003a3ef92ffbda2195899c` passed: Deno format checked 3 files, Deno type-check passed, and the security test suite reported **13 passed, 0 failed**. This source fix is not deployed. Production remains on v9 and continues to return wildcard CORS until a reviewed coordinated production rollout is explicitly approved. Do not treat this as a production remediation already applied.

## Live release recheck — 2026-11-07

The earlier sections in this report contain historical staging/CI details. The verified current source baseline is `bb08df77b8b3f7f3eb14159f852d757e33834188`; use this addendum wherever earlier values differ.

- Staging now has the base organisation migration `20261107120637` applied (24 remote versions in total), five RLS-enabled organization tables and service-role-only organization RPCs. The backfill is 9 personal organizations and 9 owner memberships; there are still no team workspaces, invitations or organization audit events.
- Staging persistence is v14. Its deployed Edge `index.ts` is not yet the candidate version. The candidate has organization suspend/restore, close and revision-checked shared workspace handlers, plus pending migrations `20261107150000`, `20261107153000` and `20261107160000`.
- The refund-policy source is now aligned to staging's actual recorded version `20261025164602` after exact SQL comparison. The remaining local-only migration versions are `20261026110000` and the three organization migrations; the safe referral migration is idempotent and has an equivalent staging application recorded as `20261105101231`.
- Current 100-tool matrix: 96 implemented-needs-validation, 4 external-configuration-required (T096–T099), 0 verified-working.
- The six exact-source workflows (validation `42408321586`, replay `42408321582`, Edge `42408321617`, Excel `42408321580`, subscription `42408321585`, production-v9 backport `42408321591`) were queued at the last inspection. None is a pass. Hosted authenticated E2E, module acceptance and the authenticated live smoke remain unverified.
- Production remains untouched: migration ledger `20261019140600`, persistence Edge v9. No legal columns or organization tables were applied to production.

**Decision remains NO-GO.** Do not apply the pending staging migrations or deploy the new staging Edge Function until clean migration replay and exact-head CI pass and a staging backup/rollback point is confirmed. Do not deploy production. Keep BETA.

## Live execution recheck — 2026-11-09

This addendum supersedes any older environment/version statements above where they conflict. Read-only verification was performed against the connected GitHub and Supabase projects.

### Exact candidate and CI

- PR #232 remains **open and draft**, targeting `staging-e2e-20261019`.
- Candidate HEAD observed: `4ac0dcddd46efa42fa6c0bc80f59958195ecf430`.
- Clean PostgreSQL 17 migration-history replay: run [#42629230716](https://github.com/MSJ1708/shoir-ie/actions/runs/42629230716) — **SUCCESS**.
- Candidate Edge Function verification: run [#42629230535](https://github.com/MSJ1708/shoir-ie/actions/runs/42629230535) — **SUCCESS**.
- Production-compatible security backport verification: run [#42629230440](https://github.com/MSJ1708/shoir-ie/actions/runs/42629230440) — **SUCCESS**.
- Subscription transaction integration: run [#42629230405](https://github.com/MSJ1708/shoir-ie/actions/runs/42629230405) — **SUCCESS**.
- Excel Intelligence: run [#42629230399](https://github.com/MSJ1708/shoir-ie/actions/runs/42629230399) — **SUCCESS**.
- Main validation: run [#42629230631](https://github.com/MSJ1708/shoir-ie/actions/runs/42629230631) was still running its regression-test step at inspection. Its separate `live-deployment-smoke` job was **SKIPPED**, not passed.
- No exact-head full validation pass is claimed until that run finishes and its reports are inspected.

### Current staging facts

- Project: `hfhrosthswcybccepmak`; PostgreSQL 17.11; `ACTIVE_HEALTHY`.
- Remote migration ledger: 24 versions, ending at `20261107120637`.
- Persistence Edge Function: active v14; deployed source hash `c4befd44dadd08d6e451026bdbc0039a6613c6505715d4e7c20f3ae5a20fa500`.
- The three candidate migrations `20261107150000`, `20261107153000` and `20261107160000` remain unapplied.
- The Performance Advisor still reports six unindexed organization foreign keys. Migration `20261107160000` contains the covering indexes for those references, the complete organization-owner FK and the shared-state updater FK. This is a known, unremediated staging finding until the migration is safely applied and the Advisor is rechecked.
- Security and Health Advisors returned no lints. The Performance Advisor also reports unused indexes; those are informational and must not be dropped without workload evidence.
- Live read-only counts: 9 organizations, 0 team workspaces, 0 invitations and 0 organization audit events. This does not prove team-collaboration acceptance.
- The seven named disposable staging identities (`shoir-e2e-active`, `second`, `starter`, `expired`, `module`, `research`, `inactive`) already exist with the expected broad tier/active/expiry categories. An additional `shoir-e2e-staging-001` identity also exists. Do not provision duplicates. Credentials and GitHub Actions secret values were not read or exposed.

### Current production facts

- Project: `gcsamrdaeraxieaagsta`; PostgreSQL 17.6; `ACTIVE_HEALTHY`.
- Remote migration ledger: 14 versions, ending at `20261019140600`.
- Persistence Edge Function: active v10; deployed source hash `4708c87c43ca805536bb1c5decc0205527f400f06496d25a002a6d29d0898d0f`.
- Security and Health Advisors returned no lints; Performance Advisor reports unused indexes only.
- Production schema remains behind staging and does not have the staging legal-acceptance/organization changes. No production DDL, Edge deployment, Streamlit deployment or customer/account mutation was performed.

### Protected administrator invariant

Read-only queries in both projects returned exactly one `sho` row with role `Enterprise Admin`, tier `Enterprise Plus Tier ($399)`, active `true`, and expiry `2099-01-01T00:00:00Z`. It was not used for testing or modified.

### Release decision and next safe action

**NO-GO — RELEASE NOT AUTHORISED.**

The exact-head clean migration replay and five focused integration/verification workflows have passed, but the full regression workflow remains in progress, hosted authenticated staging acceptance has not been run, and the three organization migrations are not deployed. The connected controls do not provide a database backup/PITR snapshot inspection or GitHub workflow-dispatch action. Therefore no migration or new staging Edge deployment is being performed without a separately confirmed staging recovery point and the required authenticated acceptance path.

Next sequence: finish and inspect exact-head validation; verify an actual recoverable staging backup/restore point; apply the three migrations in timestamp order to staging only; recheck schema, grants, RLS and Performance Advisor; deploy the exact candidate Edge source to staging and verify its version/hash; run the authenticated gate with the existing disposable accounts and configured Actions secrets; then complete browser, engineering, dataset/Digital Thread, export, integration and legal acceptance. Keep PR #232 draft and keep BETA. Do not deploy or migrate production.
