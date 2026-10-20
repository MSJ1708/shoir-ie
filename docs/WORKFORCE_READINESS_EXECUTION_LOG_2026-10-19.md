# Shoir-IE Workforce Readiness Execution Log — 2026-10-19

## Release decision

**NO-GO.** This execution log is a scoped snapshot of read-only repository and Supabase inspections. It is not a production-readiness certification and does not replace the canonical release report or verification matrix.

## Verified in this inspection

- Repository: `MSJ1708/shoir-ie`, default branch `main`.
- PR #158 is merged. It adds an independent entitlement truth table for 96 inventory modules across Starter, Mid-Tier Pro, Professional, Enterprise, Enterprise Plus, and Research Pack. This is source-level entitlement coverage, not direct-operation authorization or calculation verification.
- Supabase production project `shoir-ie-production` is reported `ACTIVE_HEALTHY`.
- Production `shoir-persistence` is active at version 8, fingerprint `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`.
- Supabase staging project `shoir-ie-staging-2026-10-19` is reported `ACTIVE_HEALTHY`. Its migration ledger contains 14 entries, including an imported login-throttle migration and the atomic subscription-decision migration.
- Production migration ledger has 13 entries. It records login throttling as `20261019124815 server_side_login_rate_limits` and does not contain `20261019140600 atomic_subscription_request_decisions`.
- Read-only catalog inspection found no production functions named `shoir_create_registration_request` or `shoir_finalize_subscription_request`; staging contains both.
- Supabase security advisors returned no lints in the inspected production and staging snapshots. This is not a penetration test or a full security certification.
- No production migration or Edge Function deployment was performed during this inspection.

## Critical blockers

1. **Production schema/function compatibility:** The production Edge Function/source contract requires atomic registration and subscription-decision RPCs absent from production. Do not deploy the new Edge Function alone.
2. **Migration history reconciliation:** Production's login-throttle migration version differs from the repository filename; staging uses imported timestamped ledger entries. Compare exact migration SQL and schema, then use a reviewed supported reconciliation or forward-only corrective migration. Do not manually pretend versions are equivalent.
3. **HTTP end-to-end acceptance:** A staging SQL/RPC presence check is not proof that the deployed HTTP handler, secrets, authentication, error handling, and storage work together. Direct HTTP probing could not be performed from this execution environment because outbound DNS/network access was unavailable.
4. **Authenticated account lifecycle:** No successful current authenticated release-gate run with dedicated disposable `shoir-e2e-*` accounts and protected Actions secrets was established.
5. **Tenant isolation and tier enforcement:** Direct API attempts across distinct valid sessions, resource types, exports, and tiers remain unverified end to end.
6. **96-module acceptance:** The merged entitlement truth-table test is not a completed authenticated browser matrix or independent engineering calculation validation.
7. **Imports, exports, persistence and recovery:** Real workbook/report round trips, save/logout/re-login/restart, backup restore, and rollback drills remain unverified.
8. **Deployment identity and governance:** Exact Streamlit-served SHA, enforced required-check policy, final security/operations sign-off, and current complete evidence matrix remain unverified.

## Required next sequence

1. Freeze a reviewed release candidate SHA and require all relevant checks on that exact SHA.
2. Compare production and repository login-throttle migration SQL, signatures, grants and policies. Reconcile through reviewed migration tooling; replay the full sequence on a clean isolated database.
3. Confirm staging is isolated and has no customer data. Provision dedicated disposable accounts through the supported lifecycle, using secrets stored only in GitHub Actions.
4. Run the deployed staging Edge Function HTTP suite for login, invalid login, registration validation, duplicate registration, tier/payment validation, renewals, approve/decline, logout, throttling, private proof upload/review, and concurrent decisions. Preserve redacted evidence.
5. Run the authenticated lifecycle and cross-tenant isolation gates.
6. Run the 96-module browser matrix for the appropriate Enterprise Plus and Research Pack accounts. Add independent calculation fixtures and chart/data assertions for each applicable module.
7. Test XLSX/CSV import, Excel/CSV/PDF/PowerPoint exports and reopen/round-trip parity; verify persistence across new sessions and app restart.
8. Test migration upgrade/failure recovery, backup restoration and function rollback in non-production.
9. Verify the actual deployed Streamlit revision and rerun public and authenticated smoke tests against that revision.
10. Update the canonical release report and verification matrix with exact SHA, run links, environment, timestamps and artifacts. Keep any unrun or blocked case explicitly marked.
11. Only after all critical gates pass, obtain explicit engineering, security and operations approval for a controlled production migration followed by the matching Edge Function deployment. Verify production immediately afterward.

## Safety boundary

- Do not use the protected production administrator or customer accounts for tests.
- Do not apply the atomic subscription migration to production as a test.
- Do not deploy the Edge Function independently of its database dependency.
- Do not mark source-level checks, SQL-only tests, or anonymous shell checks as authenticated workforce acceptance.
- Do not claim independent security certification without an actual independent assessment.

## Status

This document records verified observations and outstanding work. **It does not declare Shoir-IE workforce-ready.** The release remains on hold until the critical blockers and the definition-of-done evidence are closed.
