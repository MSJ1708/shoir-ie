# Shoir-IE Release Decision — 2026-11-04

**Decision: NO-GO for production deployment and paid customer launch.**  
**Scope:** current staging candidate `f00da78a01e2ecf07fe263ddf570cbc1e075ac31` and staging Supabase `hfhrosthswcybccepmak`.  
**Production mutation:** none.

## Gate assessment

| Gate | Assessment | Evidence / missing condition |
|---|---|---|
| A — Application integrity | PARTIAL | Python compile, full pytest, import smoke and local desktop/mobile browser smoke passed. Hosted staging smoke and authenticated module routes were skipped. |
| B — Data integrity | NOT PASSED | Staging migration ledger/source mismatch remains; tenant isolation and real persistence round-trip are not freshly verified on the current hosted build. |
| C — Engineering integrity | PARTIAL | Regression suite passed. Independent reference/units/assumptions checks are not complete for every critical method, solver and simulation workflow. |
| D — AI and Excel integrity | NOT PASSED | Excel feature source and Edge v12 are present, but hosted app path and Office hosts are not accepted; full Stage 1 is open; Copilot permissions require fresh authenticated workflow evidence. |
| E — Enterprise security | NOT PASSED | Protected admin invariant passes aggregate check; internal schema RLS/access review and tenant/file/AI security acceptance remain incomplete. |
| F — Commercial readiness | NOT PASSED | Saudi legal/privacy/commercial review and support/business identity requirements remain open. |
| G — Operational readiness | NOT PASSED | Backup configuration/restore rehearsal, operational monitoring and recovery evidence are not established. |
| H — Staging acceptance | NOT PASSED | Authenticated gate skipped; staging app hostname/build and 96-module browser matrix not evidenced. |

## Positive evidence

- Current staging branch is reachable and separately identified from main.
- Latest staging CI run 41716603183 passed all steps in its main test job, including pytest, Deno type/security checks, synthetic PDF/PPTX rendering and local runtime smoke.
- Staging Supabase project is ACTIVE_HEALTHY.
- Staging Edge Function is ACTIVE at v12; deployed source files byte-match the staging branch.
- Protected administrator invariant has exactly one aggregate match and exactly one active Enterprise Admin.
- Existing feature catalogue and broad module/test foundations are present.

## Mandatory blockers

1. Authenticated hosted staging acceptance is not complete.
2. Current staging database migration ledger and repository source files require deliberate reconciliation.
3. Internal-schema RLS-disabled tables require completed access-path and policy review.
4. Cross-tenant database, storage, search, export and AI execution tests need current evidence.
5. Engineering reference cases and model validation remain incomplete across the required methods.
6. Excel full Stage 1 and actual Office host deployment/compatibility remain open.
7. Restore rehearsal and operational recovery evidence are missing.
8. External identity/ERP configuration and qualified commercial/legal reviews remain outstanding.

## Decision rule

Do not remove BETA, enable paid access, merge to main, deploy the application to production, deploy a production Edge Function or execute production database migrations under this decision.

Re-assess only after each mandatory gate has exact-build evidence and all unresolved blockers are either closed or formally bounded without bypassing security, data-integrity, legal or safety acceptance.

**Release status remains NO-GO.**
