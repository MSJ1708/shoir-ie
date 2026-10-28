# Production persistence security hotfix candidate

**Status: DRAFT / NOT DEPLOYED. Production remains HOLD.** This is a candidate for independent review and an explicitly approved change window; it is not release authorization.

## Fresh live target — October 28, 2026

A live Supabase Management API read returned:

- Function: `shoir-persistence`
- Project: production `gcsamrdaeraxieaagsta`
- Active version: **9**
- Active source SHA-256: `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740`
- Observed production behavior: the response helper still emits `Access-Control-Allow-Origin: *`; it now advertises `POST, OPTIONS`, but does not enforce exact browser origins or emit `Vary: Origin`.
- The active production-v9 function uses `req.json()` and no effective byte limit was established in the source snapshot. This candidate **replaces** that parser with a streamed, bounded UTF-8 JSON-object reader capped at 12 MiB; exact behavior remains subject to the pending candidate tests.

The candidate source `index.ts` was refreshed from that exact v9 payload and then modified for CORS, protected-administrator login handling, bounded request parsing, and safe error responses. The folder name `production-hotfix-v8` is historical; it must not be interpreted as the active function version. This branch does not deploy any code.

## Narrow source changes in this candidate

1. **Exact production origin policy.** Only `https://shoir-ie-app.streamlit.app` is an approved browser origin. An unapproved Origin is rejected before JSON/action handling with HTTP 403 and no `Access-Control-Allow-Origin`.
2. **Preflight/method handling.** Approved `OPTIONS` receives HTTP 204; the API action handler accepts POST only and returns 405 for other methods. Responses include the reviewed request headers, `POST, OPTIONS`, and `Vary: Origin`.
3. **No fabricated origin.** Origin-free callers can still use the API's POST path, but receive no `Access-Control-Allow-Origin`; authentication/authorization remains enforced by each action.
4. **Protected administrator fails closed.** If an account matches either protected marker (reserved username or Enterprise Admin role) but does not meet the complete expected username, role, active status, Enterprise Plus tier and exact expiry invariant, login returns a generic 503 and creates no session. No login-time tier or `updated_at` mutation remains.
5. **Bounded request parsing and safe errors.** The candidate uses the existing reviewed 12 MiB streamed JSON-body limit, validates JSON object shape and UTF-8, returns HTTP 400/413 for malformed or oversized input, and uses an allowlisted public error mapper so infrastructure details are not returned to callers.
6. **Schema scope.** This candidate was rebuilt from the active production v9 function, which contains no referral-table or legal-acceptance-column references. It does not require the missing `shoir_referrals` table or the six production-missing legal fields. It does not run a database migration.

The reserved administrator is never used as a test identity and this change does not change its stored values.

## Provenance and test boundary

- Active source baseline: production version 9, SHA-256 `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740`.
- Candidate commit in the hotfix branch: see this PR's current head; verify the exact head and artifact links directly in GitHub.
- The candidate has contract tests that reject wildcard CORS, require the exact origin policy and 204 preflight, check that login-time admin repair is absent, verify the unique active-admin invariant, exercise bounded JSON parsing and safe error redaction, and confirm that this source does not depend on the missing production schema.
- Helper tests cover exact approved origin, unapproved origins including both staging hosts and localhost, origin-free server calls, `Vary: Origin`, the method allowlist, and valid/invalid admin invariant values.

Any previous green result belongs to a previous source revision and does not substitute for fresh exact-head checks. The live-deployment-smoke job on ordinary feature/draft PRs is configured to be skipped; that result is not a pass.

## Required before deployment

1. Finish exact-head CI for this updated candidate; investigate any failure and treat skipped hosted smoke as open.
2. Obtain independent security review of the full candidate diff against the recorded production v9 SHA and a fresh pre-deployment reread of the active version/hash.
3. Confirm account invariant and action permissions using disposable non-admin identities only; never log in as the reserved administrator.
4. Confirm a usable backup/PITR restore point, isolated restore result, named recovery owner, and reviewed forward-recovery/abort plan.
5. Obtain written release-owner approval naming this exact source hash, target project, time window and recovery procedure.
6. Only after authorization, deploy the reviewed artifact and immediately run real HTTP probes for approved and unapproved Origins, `OPTIONS`, POST, error responses, and origin-free server-to-server requests. Confirm normal login/logout/workspace operations with disposable accounts and independently verify authentication/authorization remains enforced.

**Do not deploy the full staging persistence function or apply production schema migrations as part of this hotfix. Do not deploy from a green unit-test result alone. Production deployment remains unauthorized.**
