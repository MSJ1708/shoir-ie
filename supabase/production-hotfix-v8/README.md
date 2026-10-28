# Production persistence security hotfix candidate

**Status: DRAFT / NOT DEPLOYED. Production remains HOLD.** This artifact is a review candidate, not production release authorization.

## Current live target recheck — October 28, 2026

A fresh Supabase read returned the active production function as:

- Function: `shoir-persistence`
- Active version: **9**
- Current deployed source SHA-256: `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740`
- Current behavior visible in deployed source: `Access-Control-Allow-Methods: POST, OPTIONS` is now present, but the response helper still returns `Access-Control-Allow-Origin: *`. The live source does not implement the exact browser-origin allowlist or `Vary: Origin` policy.

Earlier evidence in this branch was captured from production v8, SHA-256 `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`, before the method-header hotfix. The source folder name `production-hotfix-v8` records that historical origin; it must not be mistaken for the current deployed version.

The current v9 source and this candidate were compared at the action-contract level on October 28. The action-name inventory, table references, RPC references, and helper-function names match. This structural comparison is not a substitute for independent review of the complete source diff against the latest live hash. Re-read and freeze the exact source again immediately before any proposed deployment; if the live hash changes, repeat the comparison and tests.

## Proposed narrow behavior correction

- Replace wildcard CORS with the exact production browser origin `https://shoir-ie-app.streamlit.app`.
- Return HTTP 403 for an unapproved browser `Origin` before action handling.
- Return HTTP 204 for an approved `OPTIONS` preflight.
- Advertise `POST, OPTIONS`, the currently intended request headers, and `Vary: Origin`.
- For requests without `Origin`, do not fabricate an `Access-Control-Allow-Origin` value; continue to apply action-level authentication and authorization to server-to-server requests.
- Remove login-time mutation of the reserved administrator's tier, expiry, and `updated_at`. Check the complete invariant read-only; if it has drifted, fail closed with a generic 503 and issue no session.

The candidate does not reference `shoir_referrals` or the six legal-acceptance columns absent from production, and does not require a schema migration. Keep staging-only origins out of the production allowlist unless the accountable owner explicitly authorizes them.

## Verification recorded so far

The prior candidate head `7573e7d6723da60f910dac43813910d4cdf997c3` reported passing `test`, `edge-function`, `engine-regression`, and `security-quality` checks. The hosted `live-deployment-smoke` job was **skipped**, not passed. Any source or documentation commit must have its exact-head CI rerun and verified before those results are relied on for the updated head.

The historical live production probe found wildcard CORS for approved, unapproved, and omitted Origin requests. This remains an open production blocker until a reviewed candidate is deployed with authorization and fresh live HTTP probes demonstrate the intended behavior.

## Required before release

1. Independent security review of the exact candidate diff against the freshly retrieved production v9 source hash.
2. Confirmation that the reviewed SQL/function contract and all database dependencies are compatible; this candidate must not be used as a reason to deploy staging v11 or run database migrations.
3. Approved backup/PITR reference, isolated restore/recovery evidence, named recovery owner, and a reviewed stop/forward-recovery plan.
4. Explicit release-owner approval for the exact function source hash, project, change window, and rollback/recovery procedure.
5. Post-deployment live probes for approved and rejected Origins, successful `OPTIONS`, the intended `POST`, errors, and origin-free server-to-server behavior, plus authentication checks using disposable non-admin identities.

**Never log in as or mutate the reserved administrator to test this change. Do not merge or deploy based on a green unit-test run alone.**
