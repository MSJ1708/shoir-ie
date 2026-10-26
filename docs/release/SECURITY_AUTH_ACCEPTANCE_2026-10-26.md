# Security and authorization acceptance — 26 October 2026

**Mode:** Read-only snapshot. No accounts or permissions changed.

## Results

| Control | Status | Evidence / limitation |
|---|---|---|
| Master-admin invariant | VERIFIED PASS for this snapshot | Aggregate read-only query in staging and production found exactly one Enterprise Admin and one exact role/tier/active/expiry match in each environment. |
| Data minimization during admin check | VERIFIED PASS | No username, email, password hash, token or other identity field was selected. |
| RLS on inspected public shoir_* tables | PARTIAL | RLS enabled; server-only policies and no explicit anon/authenticated/PUBLIC table grants were reported for inspected relations. |
| Staging referrals advisor finding | REVIEW REQUIRED | RLS on, no policies; no client grants reported. Confirm server-only intent; no access policy changes made. |
| Current-candidate cross-account/workspace denial | NOT RUN | Requires authenticated E2E on current staging candidate. |
| Current login/session expiry/logout/revocation | NOT RUN | Older run does not prove current candidate. |
| All server-side tier/entitlement paths | PARTIAL | Focused checks exist; all direct API/Copilot/export/restore/other-path denials remain unproven end to end. |
| Current authenticated gate | SKIPPED | Run 40273588637 on staging SHA 8b36e3737705867019b9cf29e603cfc37e7911e6. |
| Previous authenticated gate | FAIL on stale SHA | Run 39613907604 on 3c91c83db17724f415e7fb92d83ed338d9eb5a9a: backend lifecycle/isolation passed and 96/96 routes passed; two logout-settlement assertions failed. |
| Main branch protections | FAIL / ACTION REQUIRED | API field protected=false, visible rulesets empty; detailed endpoint unavailable (403). |

## Staging guard

The checked-in E2E guard validates HTTPS and the exact approved staging Edge Function URL/project ref, hostname-only staging host variable, and publishable or anon key. It refuses a production Streamlit hostname and service-role/secret keys. This is source-level guard evidence, not confirmation that all live GitHub secrets/variables exist or are correctly scoped.

## Acceptance steps remaining

1. Authorized operator dispatches the current staging gate after checking required secrets/variables and disposable shoir-e2e-* users.
2. Prove login/logout/re-login, expiry/inactive accounts, tier boundaries, renewal-only behavior, invalid/revoked sessions and rate limiting if enabled.
3. Attempt direct cross-account and cross-workspace reads/writes through supported API/database paths, not only hidden UI controls.
4. Verify save/reload/re-login/restore and synthetic test-data cleanup.
5. Inspect redacted artifacts and sanitized application/function logs.
6. Verify server-only tables remain inaccessible to anon/authenticated roles.
7. Require a real, non-skipped passing run on the exact candidate or a correctly identified descendant.
8. Have a repository admin configure and verify main protection and required checks.

**Release decision:** auth/tenancy remains BLOCKED until current-candidate E2E evidence exists. The aggregate admin invariant is true for this snapshot only and must be checked again after any authorized production release changes.

## Additional SQL function privilege check

A read-only pg_proc/ACL query on both environments found the inspected shoir_* functions have EXECUTE grants for postgres and service_role only. has_function_privilege was false for anon and authenticated for shoir_check_login_throttle, shoir_cleanup_sessions, shoir_create_registration_request and shoir_finalize_subscription_request. The staging-only legal acceptance trigger function was also executable by service_role but not anon/authenticated. shoir_cleanup_sessions is SECURITY DEFINER, so preserve the reviewed EXECUTE restriction and do not expose it through a public RPC. This is a snapshot, not a substitute for post-migration checks.