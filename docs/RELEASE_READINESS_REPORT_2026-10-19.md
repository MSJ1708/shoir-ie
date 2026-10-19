# Shoir-IE Release Readiness Report — 2026-10-19

## Decision

**NO-GO for workforce production use at this verification point.** This is an evidence-based release decision, not a claim that the entire product is broken. The current public Streamlit deployment failed a fresh entry-screen browser check with Streamlit's redacted `ImportError` page. The deployed Streamlit revision and exact exception are not available from the public page and must be established from Streamlit Cloud runtime logs.

Do not invite workers to depend on the live app until the startup error is diagnosed and the authenticated release gates below pass. Do not deploy the unmerged changes in PR [#145](https://github.com/MSJ1708/shoir-ie/pull/145) until its migration has been validated in an isolated database and the release sequence is approved.

## Revisions and environment

- Repository: [MSJ1708/shoir-ie](https://github.com/MSJ1708/shoir-ie)
- Baseline `main` revision examined: `6bc1f0bf5aca1ff7c09a87565c736f88cc291210`
- Candidate branch: `fix/pending-renewal-decline-guard-2026-10-19`
- Latest implementation-code revision with a full passing CI set: `b7c9da43d0c3c51aa5fb94b71c6fe3f0844afadc`. Subsequent commits on the same PR update the readiness report and matrix; they do not change application code.
- Candidate PR: [#145 — Guard subscription decline transitions](https://github.com/MSJ1708/shoir-ie/pull/145). Open, **not merged**, **not deployed**.
- Public application: https://shoir-ie-app.streamlit.app/
- Supabase project: `shoir-ie-production`, ref `gcsamrdaeraxieaagsta`
- Deployed persistence Edge Function when inspected: `shoir-persistence`, active version 8.
- The actual Streamlit Cloud deployed commit SHA could not be established from the public endpoint or GitHub connector; treat it as **unverified**.

## What was directly checked

| Area | Result | Scope and evidence |
|---|---|---|
| Python/Streamlit tests on candidate | **PASS** | [Candidate test run](https://github.com/MSJ1708/shoir-ie/actions/runs/39269059922): 482 passed, 2 warnings. This is CI against the candidate source, not a live worker session. |
| Engine regression | **PASS** | [Candidate engine run](https://github.com/MSJ1708/shoir-ie/actions/runs/39269060088). |
| Platform tests | **PASS** | [Candidate platform run](https://github.com/MSJ1708/shoir-ie/actions/runs/39269059883). |
| Security and quality gates | **PASS** | [Candidate security/quality run](https://github.com/MSJ1708/shoir-ie/actions/runs/39269059989). Automated scanning is not independent penetration testing. |
| Edge Function formatting/type-check | **PASS** | [Candidate Edge Function run](https://github.com/MSJ1708/shoir-ie/actions/runs/39269059985). |
| Consolidated source validation | **PASS** | [Candidate validation run](https://github.com/MSJ1708/shoir-ie/actions/runs/39269059886). Its live-smoke job was skipped on this fix branch. |
| Production Supabase health | **PASS — read-only inspection** | Connected project reported active/healthy; deployed `shoir-persistence` version 8. |
| Login-throttle migration and grants | **PASS — read-only inspection** | Current production migration history includes the server-side throttle migration. `anon`/ordinary `authenticated` roles cannot execute the throttle RPC; `service_role` can. |
| Public access to protected account/workspace tables | **PASS — read-only inspection** | Direct table privilege checks for `anon` and `authenticated` returned denied for the reviewed protected tables; RLS and server-only policies were inspected. This is not a complete tenant-isolation assessment of all objects. |
| Private payment proof storage | **PASS — configuration inspected** | Bucket is private, 512 KiB limit and PNG/JPEG/PDF MIME allowlist; direct client access is restricted by storage policy. Actual new registration and renewal round-trips are not end-to-end verified. |
| Master administrator invariant | **PASS — read-only record check** | Existing record is active, still has role `Enterprise Admin`, tier `Enterprise Plus Tier ($399)` and long-dated expiry `2099-01-01 UTC`. No password, identity, role, expiry or workspace change was performed. No admin account was used for automated tests. |
| Supabase security advisor | **No findings returned** | Advisor output only; not a security certification. |
| Supabase performance advisor | **17 informational unused-index findings** | Informational tuning work; review against actual query plans before dropping indexes. |

## Critical live failure

The most recent public browser smoke **failed** at [run 39238591641, attempt 3](https://github.com/MSJ1708/shoir-ie/actions/runs/39238591641). The hosted page text showed Streamlit's redacted `ImportError` error page; the application frame could not be located, so the desktop/mobile public-tab checks could not proceed. Evidence artifact from latest failed attempt: [live smoke screenshots and report](https://github.com/MSJ1708/shoir-ie/actions/runs/39238591641/artifacts/12194522007). Earlier attempts in the same run also failed with the same redacted ImportError.

This overrides the earlier smoke pass recorded in older versions of the matrix. The exact ImportError is **unknown** from public evidence. Do not guess at the root cause. The owner must inspect Streamlit Cloud → Manage app → runtime logs, record the actual deployed commit/dependency environment, fix the underlying error, and rerun the public desktop/mobile smoke on that build.

## Candidate repairs in PR #145

The branch includes these changes, and the source/CI checks above pass:

1. Registration helper calls `register_request` and duplicate preflight uses `account_exists`; the original Edge dispatcher did not expose those actions. The candidate adds server-side handlers and a transactional database request function. Payment proof bytes are validated and uploaded to private storage rather than relying on a local file path.
2. Registration validates the allowed username format, password length, email, tier, payment method, proof type/size/content and duplicate policy. Durable persistence is performed before creating the local pending-payment cache entry; failed remote submission removes the temporary local file.
3. The public account-existence preflight no longer discloses whether a username exists; the serialized server-side registration function enforces the duplicate rule and returns a generic conflict.
4. Administrator approval and decline are routed through a row-locked PostgreSQL decision function. It accepts only `Pending` requests, performs account/request changes in one transaction for approval, rejects already-processed requests, and grants function execution only to `service_role`.
5. Regression contracts were added around the transaction boundary, identity preservation and proof handling.

**Deployment boundary:** the new migration `20261019140600_atomic_subscription_request_decisions.sql` has **not** been applied to production. The Edge Function in the PR expects the new RPCs, so deploying only the function or merging the branch without running and validating the migration first is unsafe. Validate the migration and RPC privileges in an isolated staging database before considering any production deployment. The connected project inspected during this audit was production; no isolated test database was available for executing the migration.

## Critical open release gates

| Gate | Status | Exact closure evidence required |
|---|---|---|
| Public hosted app startup | **BLOCKED** | Streamlit runtime ImportError resolved; deployed SHA and dependency state recorded; fresh public desktop/mobile browser test passes with no app error screen. |
| Authenticated login, expired-session renewal, logout revocation | **UNVERIFIED** | Run the documented [Authenticated Release Gate](AUTHENTICATED_RELEASE_GATE.md) with protected GitHub Actions secrets and disposable, non-admin `shoir-e2e-*` identities; review redacted evidence. The workflow has not been run in the available evidence. |
| Subscription registration, proof storage, approval, decline and renewal restoration | **PARTIAL / CANDIDATE ONLY** | Execute valid/invalid lifecycle tests in staging, including concurrency and duplicate attempts; review stored request/account state before/after; ensure no production/customer request is touched. |
| Migration validation and rollout | **BLOCKED** | Execute migration on isolated staging database, verify schema/signatures/grants/rollback procedure, then deploy migration and Edge Function in the approved sequence. |
| 96-module rendering and calculation matrix | **UNVERIFIED** | The repository inventory contains 96 distinct names, but all `authenticated_browser_status` values remain `UNVERIFIED`. Execute per-module valid/empty/malformed/tier-denial tests, record actual outputs/screenshots/commit SHA, and verify expected engineering calculations. |
| Six tier-package entitlement enforcement | **PARTIAL** | Static inventory and source checks exist. Verify allowed and denied access through UI, direct module invocation, API/export actions and saved/deep-linked routes using test accounts for every package. |
| Excel/CSV import and Excel/PDF/PowerPoint output | **UNVERIFIED** | Import synthetic valid and malformed workbooks; run actual file round-trips; reopen generated files and compare sheets, rows, formulas, units, chart and report content. |
| Authenticated owner/tenant isolation across all objects | **PARTIAL** | Current RLS/grant checks pass for reviewed tables, and some research-owner contract tests pass. Run cross-account direct-ID read/write/export denial against the full protected-object matrix and verify the denied operation did not change stored data. |
| Backups and disaster recovery | **UNVERIFIED** | Document RPO/RTO; restore an approved backup in an isolated environment; verify records, owner relationships, authentication config and application compatibility. |
| Load, resilience and operational monitoring | **UNVERIFIED** | Run representative concurrent-user, upload, chart/calculation, storage outage/retry and recovery tests; record response times, error rate and resource bounds. |
| Independent security review / legal readiness | **NOT DONE** | Arrange authorized independent penetration testing and obtain owner/legal decisions about Saudi/international privacy, retention, data residency, hosting and customer contracts. Automated CI or a clean Supabase advisor does not satisfy this gate. |

## Safe release sequence

1. Diagnose the live Streamlit ImportError from its private runtime logs; make the public app healthy and record the actual deployed SHA.
2. Validate PR #145's migration in an isolated staging database and update any failing tests without weakening the Deno or authorization gates.
3. Configure the authenticated workflow only with dedicated, disposable test identities and protected GitHub Actions secrets. Never use the master administrator or real customers.
4. Run authenticated registration/renewal/session/workspace-isolation tests in staging. Verify cleanup and state restoration.
5. Complete the 96-module tier, calculation, rendering and actual import/export round-trip matrix, with evidence at the tested SHA.
6. Complete backup restore, monitoring, performance/recovery and independent security/privacy actions appropriate to the intended customers.
7. Only after the critical gates pass, review and merge the PR, apply approved additive migrations, deploy the Edge Function and Streamlit revision in the correct order, then repeat authenticated live smoke against the intended deployed build.
8. Update this report and the verification matrix with run URLs, build IDs, timestamps and actual observed outcomes.

## Final assessment

This audit verified meaningful source and backend safeguards and obtained passing automated CI for the PR candidate. It also exposed gaps that CI alone does not cover and a failed live application smoke test. Therefore **Shoir-IE is not yet verified as ready for workers or approved for production release**. The release decision stays blocked until the live startup failure is fixed and the critical authenticated, migration, module and data-round-trip evidence is captured.
