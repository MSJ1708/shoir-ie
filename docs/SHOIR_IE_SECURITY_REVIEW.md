# Shoir-IE Security Review — Staging Snapshot

**Review date:** 2026-11-04  
**Environment:** Supabase staging project `hfhrosthswcybccepmak` only  
**Production changes:** none

## 1. Protected administrator

A staging-only aggregate query found exactly one active Enterprise Admin and exactly one row matching the required reserved administrator invariant (identity, role, Enterprise Plus tier, active state and expiry `2099-01-01T00:00:00Z`). The Edge Function source includes `hasCanonicalMasterAdminInvariant`; the historical seed migration is a no-op.

No protected administrator credentials or full profile data were selected. The account was not used for testing and was not modified.

## 2. Custom session and Edge Function

Staging `shoir-persistence` is ACTIVE at version 12. Deployed `index.ts` and `security.ts` byte-match the staging branch source. The function uses a server-side service-role client and custom opaque sessions; verify session scope, expiry, revocation, username binding, role/tier checks, request bounds, rate limits and every action's permission independently.

A version match proves deployed source parity; it does not prove the hosted Streamlit app has deployed the same candidate or that all user flows pass.

## 3. Public database tables

The 12 observed public tables have RLS enabled. The referrals table has no RLS policy, but repository migration `20261026110000_safe_beta_legal_referrals.sql` explicitly revokes all privileges from PUBLIC, anon and authenticated and grants service_role access. Preserve this server-only boundary and test it with actual roles.

## 4. Internal schema RLS finding

Supabase table inspection identified 12 `shoir_internal` tables with RLS disabled:

- artifacts
- twin_assets
- twin_snapshots
- twin_scenarios
- connector_health
- jobs
- collaboration
- knowledge
- monitoring_rules
- monitoring_events
- report_provenance
- security

The Supabase table inspection raised a critical RLS-disabled advisory before remediation. The staging-only migration now enables RLS on all 12 tables. Read-only follow-up checks showed:
- anon: no USAGE privilege on `shoir_internal`;
- authenticated: no USAGE privilege on `shoir_internal`;
- anon: no SELECT privilege on the checked `shoir_internal.artifacts` table;
- authenticated: no SELECT privilege on the checked table;
- the SQL session did not return a value for `pgrst.db_schemas`, so API schema exposure was not established.

The staging-only hardening migration enabled RLS without policies, kept FORCE RLS disabled, and made no grant changes. This intentionally denies access to future non-owner roles until table-specific least-privilege policies are designed. It does not remove the need to review service-role callers and confirm Data API exposed schemas. The tables have no RLS policies today. The observed row count was zero at the time of metadata inspection.

### Applied staging hardening

Migration `20261104183132_enable_shoir_internal_rls_20261104` was applied to staging only. Verification confirms all 12 tables now have RLS enabled, FORCE RLS disabled, zero policies and zero rows. The migration did not change grants or application data. This is intentionally deny-by-default for any future non-owner/non-BYPASSRLS role.

This is a containment step, not a complete multi-tenant policy model. Before introducing any non-owner connector, worker or API role, define table-specific least-privilege policies with workspace predicates and test authorised and denied operations. Do not add broad `TO authenticated USING (true)` policies.

## 5. Other security observations

- Staging and production use different Supabase project references and PostgreSQL versions.
- The staging E2E guard rejects the known production project and production Streamlit host, and requires a dedicated staging host and publishable key.
- The authenticated gate requires disposable `shoir-e2e-*` accounts; the protected administrator must never be a test identity.
- The current staging CORS/Origin allowlist includes multiple Streamlit hosts. Confirm the exact staging hostname and remove obsolete origins only after checking deployed callers and current app configuration.
- Existing code has file upload size/type controls and formula-injection protections; test the full upload, export and cross-tenant download paths.
- Do not expose service-role keys, session tokens, database connection strings or raw diagnostics in browser state, logs or exports.

## 6. Required security tests

1. Cross-user and cross-workspace read/write denial.
2. Expired, inactive, revoked and replayed session denial.
3. Role escalation and protected-admin mutation denial.
4. Cross-tenant file/export/search access denial.
5. AI tool permission and approval-gate denial.
6. Unsupported/malformed and resource-exhausting file rejection.
7. CORS/host allowlist, bounded request and rate-limit tests.
8. Internal-schema role/grant/policy tests.
9. Storage access and signed URL expiry tests.
10. Staging backup restore and audit evidence review.

**Security status:** implemented controls exist, but enterprise security acceptance is not complete. Production remains NO-GO.
