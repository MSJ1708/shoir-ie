# Shoir-IE Security Acceptance Report

Assessment date: 2026-11-06. Status: **partial evidence; production parity and independent review open**.

## Live project comparison

| Control | Staging | Production |
|---|---|---|
| Supabase | `hfhrosthswcybccepmak` | `gcsamrdaeraxieaagsta` |
| Persistence Edge Function | v13 | v9 |
| Applied migrations | 23 | 14 |
| Legal consent columns | Present | Missing |
| 12 internal tables RLS | Enabled | Disabled |
| `shoir_internal` browser schema USAGE | Denied | Denied |
| Direct browser SELECT/INSERT on internal tables | Denied | Denied |

Staging has RLS and explicit browser-role deny policies on all 12 internal tables. Production currently lacks RLS on those tables, but read-only privilege queries found no `USAGE` for anon/authenticated on the schema and no direct SELECT/INSERT grants on the tables. This is a production defence-in-depth/parity blocker, not evidence of direct public browser access.

Both staging and production aggregate administrator queries returned exactly one row matching role Enterprise Admin, tier Enterprise Plus Tier ($399), active and expiry 2099-01-01T00:00:00Z. No administrator was used for testing or modified.

Open security work: deployed Edge Function/app/schema version parity; production legal column migration; reviewed RLS hardening; end-to-end session/tenant/data/file/export denial; complete CORS/SSRF/TLS/secret inventory; OIDC/MFA provider acceptance; independent security review; backup/restore rehearsal.

Complete by comparing exact deployed source hashes, testing approved and hostile CORS origins, reviewing all SECURITY DEFINER ownership/search_path/grants/actor parameters, proving account and organisation boundaries with disposable users, preparing reviewed production parity migration and obtaining independent sign-off. Do not deploy production as part of this work.
