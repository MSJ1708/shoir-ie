# Production persistence Edge Function v9 security backport

This directory is a narrowly scoped compatibility hotfix for the currently deployed production Edge Function v9.

## Exact baseline

- Project: `gcsamrdaeraxieaagsta`
- Deployed function: `shoir-persistence`, v9
- Source SHA-256 at preparation: `d284858f4819a6034ef11309105db36ebac4088a7782aba8d605438d407c5740`
- Existing `verify_jwt`: `false` (retained; action-level opaque session validation remains in the handler)
- Production database schema is intentionally not changed by this hotfix.

## Changes

- Replace wildcard CORS with an exact project-bound allowlist for `https://shoir-ie-app.streamlit.app`.
- Enforce a 12 MiB streamed JSON request limit and an 8 MiB validated workspace-state limit before accepting data.
- Reject other browser origins before request dispatch; preserve origin-less server-to-server calls, which continue to require valid application sessions.
- Keep CORS preflight responses explicit and allow Supabase retry/trace request headers.
- Stop login from rewriting the reserved `sho` administrator tier or `updated_at`. Check the full invariant and fail closed for manual review if it drifts.

## Safety and deployment state

This is source and CI evidence only. It has **not** been deployed to production. Deploy only after exact-head formatting, type-check and regression tests pass, the current deployed v9 source is re-read, and the release owner approves a short-lived production Edge Function replacement. Do not deploy the newer staging v13 source to production: production schema compatibility has not been established.
