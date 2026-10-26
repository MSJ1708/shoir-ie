# Production database / Edge Function change plan — 26 October 2026

**Status: PREPARATION ONLY.** Target production project gcsamrdaeraxieaagsta. Candidate staging project hfhrosthswcybccepmak. No production changes performed or authorized. BETA remains enabled.

## Current blockers

1. Production shoir-persistence is active version 8, bundle SHA 410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d; staging is active version 9, SHA 0551d88aceeca45ede2b890e874a75f542df670d2f2332a0878f23b5cc0b187e.
2. Production lacks staging beta/legal/referral migration records, shoir_referrals, terms acceptance/version columns and legal acceptance trigger.
3. The staging refund-policy migration ledger records version 20261025164602 with name 20261023130000_refresh_refund_policy_acceptance_version. This discrepancy must be reconciled.
4. The current staging authenticated gate was skipped; exact Streamlit Cloud running SHA and staging configuration are not verified.
5. Branch protection, independent review, T096 live endpoint, T098 real identity provider, per-tool launch validation, legal/commercial signoff and recovery evidence remain incomplete.

## Before any production mutation

1. Freeze the exact reviewed source SHA and list exact workflow runs/checks.
2. Independently verify target production project ref through the authorized dashboard and project details.
3. Capture redacted read-only inventory of migration ledger, actual tables/columns, triggers, constraints, indexes, policies, grants, functions, storage and aggregate counts.
4. Read canonical SQL for each required migration and compare preconditions/postconditions against actual schema. Resolve history version/name mismatch without rewriting history or blindly rerunning.
5. Determine impact on existing accounts and pending subscription approvals. Do not silently accept revised terms on behalf of existing users.
6. Verify backup/PITR retention, restore point, named recovery owner and documented procedure. Run a restoration rehearsal only in staging/isolated environment.
7. Review RLS, grants, transaction semantics, function contracts and compatibility. No broad client policies or authorization bypasses.
8. Prepare reviewed forward migration only for demonstrated differences; include idempotent prechecks, data integrity assertions, backward compatibility, negative tests and forward recovery.
9. Obtain independent source/schema review, security sign-off, business/legal approval, backup/recovery acknowledgement, change window, named owner and explicit release authorization.
10. If any condition is absent, stop before the first production write.

## Staging rehearsal requirements

- Reconcile schema and ledger in staging first.
- Run migration/policy tests and the current authenticated E2E gate.
- Test legal acceptance, atomic approval, session/throttle and negative cross-account operations with disposable synthetic users.
- Verify staged function SHA/source and application branch/entrypoint/deployed SHA after restart.
- Verify app/function/schema backward compatibility during the planned rollout window.
- Preserve redacted evidence and cleanup dedicated test sessions/data.

## Candidate deployment order (conditional; must be finalized by reviewer)

1. Freeze and approve candidate SHA and migration checksums.
2. Apply reviewed additive schema changes only if needed, in dependency order.
3. Independently verify applied migration history and actual DDL/triggers/grants.
4. Deploy the exact reviewed Edge Function bundle only after confirming its required secrets, contract compatibility and safe failure paths.
5. Verify function version/source hash and success/denial behavior.
6. Deploy the matched app revision and verify the deployed SHA and correct configuration.
7. Keep a compatibility window; do not perform destructive cleanup until the reviewed plan says it is safe.

This is not authorization to execute these steps. The final migration/function order depends on source and schema review.

## Post-deployment verification if authorized

- Check application health, exact running SHA, migration ledger, schema contracts, function hash/version, logs and advisor findings.
- Run synthetic test-account login/logout/re-login, session expiry, entitlements, representative module, persistence and legal acceptance tests.
- Check direct cross-account/workspace denial and safe failures using approved fixtures.
- Confirm aggregate master-admin invariant without selecting identifiers.
- Review sanitized logs for critical errors or leaked secrets.
- Confirm backup/recovery and monitoring remain available.
- Compare results to the captured baseline and document any deviations.
- Keep BETA unless the separate GO decision and explicit BETA-removal approval are recorded.

## Required authorization record

Include approver role/identity, UTC timestamp, target ref, exact SHA, migration paths/checksums, function hash, backup/restore evidence, change window, on-call/recovery owner, abort conditions, forward-recovery/rollback strategy, monitoring and post-deploy tests.

**Current status: BLOCKED. Production remains unchanged.**

## Additional preflight discovered in source review

Migration 20261021130000_shoir_beta_legal_referrals.sql changes existing affiliate_code values for NULL/blank and legacy AFF-...-15 rows and for case-insensitive duplicates, updates updated_at, and adds a unique index. Do not classify this as only additive. Compute redacted aggregate affected-row counts and review consequences for existing referral links before production authorization. The terms acceptance field defaults to false, which must not be changed to imply that any user accepted a new version.

A current SQL catalog query confirmed the legal-acceptance trigger exists on staging and not in production. The deployed staging trigger function compares refund_policy_version against 2026-10-23-v2. Reconcile this contract with the current Edge Function before any migration/function rollout.

Platform watch: Supabase says new explicit-grant behavior for Data API table exposure applies to all existing projects on 30 October 2026; audit any required direct Data API access without granting client roles broad access (source: https://github.com/orgs/supabase/discussions/45329). Older CBC-mode TLS 1.2 cipher suites are scheduled for removal from project HTTP APIs on 10 November 2026 at the earliest; confirm supported modern TLS clients and monitor the notice (source: https://supabase.com/changelog/cbc-tls-ciphers-deprecated).