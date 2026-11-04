# Shoir-IE Staging Acceptance Record

**Snapshot date:** 2026-11-04  
**Staging branch candidate:** `f00da78a01e2ecf07fe263ddf570cbc1e075ac31`  
**Staging Supabase project:** `hfhrosthswcybccepmak`  
**Staging Edge Function:** `shoir-persistence` v12

## 1. Automated source validation

[GitHub Actions run 41716603183](https://github.com/MSJ1708/shoir-ie/actions/runs/41716603183) completed successfully for the exact staging SHA.

| Validation item | Result |
|---|---|
| Python dependency installation | PASS |
| Python compileall | PASS |
| Repository pytest suite | PASS |
| Deno Edge Function type check | PASS |
| Edge Function security tests | PASS |
| Synthetic PDF/PPTX generation and render | PASS |
| Required module parsing | PASS |
| Application import smoke | PASS |
| Local Streamlit startup | PASS |
| Local desktop/mobile browser smoke | PASS |
| Hosted Streamlit smoke in this staging run | SKIPPED |
| Authenticated staging release gate | SKIPPED |

These results prove the CI steps above only. They do not establish authenticated hosted app acceptance, every module workflow, production compatibility, or a full recovery drill.

## 2. Supabase staging observations

- Project status: ACTIVE_HEALTHY.
- PostgreSQL: 17.11.0.003, EU Central.
- Edge Function version: 12 ACTIVE.
- Deployed Edge Function source: exact byte match for branch `index.ts` and `security.ts`.
- Migration ledger: 17 entries; latest version `20261025164602`.
- Repository migration `20261026110000_safe_beta_legal_referrals.sql` is not recorded in the current live staging ledger.
- The live `shoir_internal` tables have RLS disabled; anon/authenticated schema/table privileges were not found in the checked privilege paths. See the security review before changing any policies.

No database migration, Edge Function deployment or storage/auth setting change was made in this audit pass.

## 3. Protected administrator verification

Read-only staging aggregate result: one exact protected-admin invariant match and exactly one active Enterprise Admin. No admin record was modified and the administrator was not used as a test account.

## 4. Required authenticated gate

The current workflow is available through manual `workflow_dispatch` or the exact opt-in commit marker `[run-authenticated-gate]` on the staging branch. Its preflight must run before credentials are entered.

Required test identities are unique disposable `shoir-e2e-*` accounts for active, secondary, Starter, expired, module, Research Pack module and inactive cases. Do not create duplicate accounts or reuse the protected admin, production identities or customers.

Required secrets/variables and exact setup are documented in [AUTHENTICATED_RELEASE_GATE.md](AUTHENTICATED_RELEASE_GATE.md). The exact staging Streamlit URL and expected hostname must be supplied by the staging app owner; do not substitute the production app.

The authenticated run must retain redacted output for:
- exact staging build/hostname marker;
- login/logout and session revocation;
- expired/inactive and role/tier denials;
- cross-account workspace isolation and save/relogin restore;
- all 96 module route states in authorised tiers;
- Excel Intelligence route, entry-time entitlement and approved Copilot plan;
- registration/policy acceptance;
- real PDF/PPTX/XLSX exports and file round trips.

## 5. Release-blocking acceptance gaps

- Fresh authenticated hosted staging run not evidenced.
- Hosted build marker and staging hostname not verified.
- Migration ledger/source reconciliation incomplete.
- Internal-schema RLS/role-use assessment incomplete.
- Cross-tenant file, search, export and AI negative acceptance incomplete.
- Engineering reference validation is not complete for every important method.
- Backup restore rehearsal not evidenced.
- External identity, Office host and customer connector configurations are not established.

**Staging acceptance status:** NOT COMPLETE.  
**Release decision:** NO-GO.
