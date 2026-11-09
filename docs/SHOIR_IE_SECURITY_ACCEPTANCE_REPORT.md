# Shoir-IE Security Acceptance Report

Assessment date: 2026-11-06. Status: **partial evidence; production parity and independent review open**.

## Live project comparison

| Control | Staging | Production |
|---|---|---|
| Supabase | `hfhrosthswcybccepmak` | `gcsamrdaeraxieaagsta` |
| Persistence Edge Function | v13 | v9 |
| Applied migrations | 23 | 14 |
| Legal consent columns | Present | Missing |
| 12 internal tables RLS | Enabled | Disabled |
| `shoir_internal` browser schema USAGE | Denied | Denied |
| Direct browser SELECT/INSERT on internal tables | Denied | Denied |

Staging has RLS and explicit browser-role deny policies on all 12 internal tables. Production currently lacks RLS on those tables, but read-only privilege queries found no `USAGE` for anon/authenticated on the schema and no direct SELECT/INSERT grants on the tables. This is a production defence-in-depth/parity blocker, not evidence of direct public browser access.

Both staging and production aggregate administrator queries returned exactly one row matching role Enterprise Admin, tier Enterprise Plus Tier ($399), active and expiry 2099-01-01T00:00:00Z. No administrator was used for testing or modified.

Open security work: deployed Edge Function/app/schema version parity; production legal column migration; reviewed RLS hardening; end-to-end session/tenant/data/file/export denial; complete CORS/SSRF/TLS/secret inventory; OIDC/MFA provider acceptance; independent security review; backup/restore rehearsal.

Complete by comparing exact deployed source hashes, testing approved and hostile CORS origins, reviewing all SECURITY DEFINER ownership/search_path/grants/actor parameters, proving account and organisation boundaries with disposable users, preparing reviewed production parity migration and obtaining independent sign-off. Do not deploy production as part of this work.


## Additional CORS recheck — 2026-11-06

A read-only inspection of the deployed production persistence Edge Function v9 found a response header hard-coded as `Access-Control-Allow-Origin: *`. The deployed staging v13 helper uses an explicit allowlist, but its previous source allowlist included production and staging hosts together. The candidate now binds allowed origins to the exact Supabase project ref: production permits only `https://shoir-ie-app.streamlit.app`; staging permits the configured staging Streamlit hosts and local development origins; an unknown project fails closed; origin-less server-to-server requests remain supported and still require session/action authentication. Cross-environment CORS regression tests were added.

Dedicated Edge Function verification [run #42251683171](https://github.com/MSJ1708/shoir-ie/actions/runs/42251683171) on SHA `cf806aad170916f7e1003a3ef92ffbda2195899c` passed: Deno format checked 3 files, Deno type-check passed, and the security test suite reported **13 passed, 0 failed**. This source fix is not deployed. Production remains on v9 and continues to return wildcard CORS until a reviewed coordinated production rollout is explicitly approved. Do not treat this as a production remediation already applied.

**CORS release blocker:** Production's wildcard CORS is a P0 deployment blocker. Deploy only through the coordinated, reviewed release bundle after staging and rollback gates; do not hot-deploy from this candidate.

## Current security position — 2026-11-07

- Staging organization tables exist (base migration `20261107120637`), RLS is enabled, and the checked 11 organization RPCs are callable only by `service_role`. Anon/authenticated have no direct SELECT on those tables. This is schema-level evidence, not hosted browser/tenant acceptance.
- Staging Edge Function is v14; the deployed `index.ts` is behind the candidate source and lacks the candidate's suspend/restore, close and shared-workspace revision handlers. Candidate deployment is pending CI, migration replay and backup/rollback checks.
- Staging advisors currently report no security or health lints; the Performance Advisor reports six unindexed organization foreign keys. Catalog inspection also found the organisation owner FK lacked a full index. Candidate migration `20261107160000` now adds the seven supporting account-reference indexes plus a shared-state index; it is not yet applied.
- Production remains on v9 with wildcard CORS. The candidate v9-compatible security backport is un-deployed; production is untouched and remains a release blocker.
- The protected Enterprise Admin aggregate invariant is preserved; that account was not used for tests or modified.

No authenticated staging role/tenant acceptance, OIDC/MFA provider acceptance, full production CORS remediations, backup/restore rehearsal or independent security sign-off is claimed. Continue NO-GO.

## Live security recheck — 2026-11-09

This addendum supersedes prior version statements where they conflict. Both Supabase projects were inspected read-only through the connected project interface.

| Control | Staging | Production |
|---|---|---|
| Project ref | `hfhrosthswcybccepmak` | `gcsamrdaeraxieaagsta` |
| PostgreSQL | 17.11 | 17.6 |
| Applied migrations | 24; latest `20261107120637` | 14; latest `20261019140600` |
| Persistence Edge Function | v14; SHA-256 `c4befd44dadd08d6e451026bdbc0039a6613c6505715d4e7c20f3ae5a20fa500` | v10; SHA-256 `4708c87c43ca805536bb1c5decc0205527f400f06496d25a002a6d29d0898d0f` |
| Security Advisor | No lints | No lints |
| Health Advisor | No lints | No lints |

### Production CORS correction status

The deployed production v10 source was read directly from Supabase. Its deployed `security.ts`:

- does not emit wildcard `Access-Control-Allow-Origin: *`;
- adds `Access-Control-Allow-Origin` only when the supplied origin is permitted for the exact Supabase project reference;
- sets `Vary: Origin`;
- limits browser API methods to POST, with OPTIONS handled at the HTTP boundary;
- keeps origin-less server-to-server requests possible, while session/action authentication remains required in the request handler.

The v10 deployed function hash is the value in the table above. This corrects the older statements in this report that production remains on v9 with wildcard CORS. The v9-compatible security-backport workflow also passed on candidate SHA `4ac0dcddd46efa42fa6c0bc80f59958195ecf430` (run [#42629230440](https://github.com/MSJ1708/shoir-ie/actions/runs/42629230440)). A separate live browser-origin/HTTP probe was not performed in this inspection, so source and deployment-hash verification must not be described as a completed external HTTP acceptance test.

### Staging organisation hardening status

Staging has the base organization schema, RLS-enabled organization tables and service-role-only organization RPCs. The three candidate organization migrations remain unapplied:

- `20261107150000_shoir_organization_close.sql`
- `20261107153000_shoir_organization_member_suspend_restore.sql`
- `20261107160000_shoir_organization_workspace_state.sql`

The current staging Performance Advisor reports six unindexed organization foreign keys. The last migration adds covering indexes for those foreign keys plus the organization owner and shared-state updater references. This finding remains open until the migration is applied safely and the Advisor is rechecked. Security/Health Advisors report no lints. The unused-index notices are informational; no index was removed.

The candidate Edge source contains session-authenticated handlers for member suspend/restore, organization close and optimistic shared-workspace load/save. The currently deployed staging v14 source does not contain those candidate handlers; do not declare them live before deploying and hashing the exact candidate after the matching migrations are applied.

### Protected identity and change boundary

Read-only queries in both projects returned exactly one protected `sho` account with the required role, tier, active status and 2099 expiry. It was not used for testing or modified. No production migrations, Edge deployment, application deployment, customer-data mutation or administrator mutation occurred during this recheck.

**Security release position: staging integration and hosted acceptance remain open; production remains NO-GO.** Production v10 CORS/method hardening is deployed, but production schema parity, legal acceptance columns, organization capabilities, backup/restore evidence, authenticated cross-tenant tests, provider-backed OIDC/MFA, independent review and coordinated release approval remain outstanding.
