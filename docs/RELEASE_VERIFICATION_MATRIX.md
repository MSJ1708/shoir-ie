# Subscription, Module and Security Release Verification Matrix

Updated: 2026-10-19

This matrix is the release gate for the subscription renewal, account, module, import/export, and enterprise-access work. A row is complete only when the stated evidence exists. Source edits and static tests are not evidence of a successful authenticated browser journey.

## Verification status key

- **Implemented / source-reviewed** — code path exists; behavior may still require runtime proof.
- **Automated** — covered by a passing CI or local test result associated with the commit under review.
- **Browser verified** — completed against the hosted application using an authorized account; record date, account class, build, steps and observed outcome.
- **Blocked** — a dependency prevents a trustworthy test; document the dependency and do not mark the release definition of done complete.

## Latest repair and deployment update — 2026-10-19

This section supersedes the earlier commit/version references below for the Edge dispatcher repair only. The latest verified repository commit is `9572feef9b970f1c2fc0029d963af327aed83b6b` (PR #144 merged). Production Supabase project `shoir-ie-production` reports `shoir-persistence` active at version 8 after deploying the source from that commit.

| Check | Status | Evidence / boundary |
|---|---|---|
| Edge dispatcher syntax repair | **PASS — source re-read after deployment** | The malformed `retu  if(action===\"login\")` boundary is absent from deployed version 8; request parsing and action dispatch are within one try/catch. |
| Deno formatting and type check | **PASS — post-merge CI** | [Edge Function verification run](https://github.com/MSJ1708/shoir-ie/actions/runs/39261811432) passed after adding `deno fmt --check` and `deno check`. |
| Python suite | **PASS — repair candidate CI** | [Full test run](https://github.com/MSJ1708/shoir-ie/actions/runs/39261564956) passed after source-contract tests were made whitespace/trailing-comma tolerant. |
| Engine regression | **PASS — post-merge CI** | [Engine regression run](https://github.com/MSJ1708/shoir-ie/actions/runs/39261811469). |
| Security and quality | **PASS — post-merge CI** | [Security/quality run](https://github.com/MSJ1708/shoir-ie/actions/runs/39261811435). This is not an independent penetration test. |
| Consolidated validation | **PASS — post-merge CI** | [Validation run](https://github.com/MSJ1708/shoir-ie/actions/runs/39261811353). The authenticated live workflow is separate and has not been demonstrated by this run. |
| Login throttling migration | **PASS — production migration history inspected** | `server_side_login_rate_limits` is recorded in the production migration history. |
| Throttle permissions | **PASS — live privilege query** | `anon` and `authenticated` lack SELECT on `shoir_login_throttle` and EXECUTE on the throttle RPC; `service_role` retains EXECUTE. No synthetic throttle rows were created during this inspection. |
| Master administrator invariant | **PASS — live record read after deployment** | Existing record remains active, role `Enterprise Admin`, tier `Enterprise Plus Tier ($399)`, expiry `2099-01-01 UTC`. No password, identity, role or workspace mutation was performed. |
| Authenticated sign-in/renewal/workspace isolation | **OPEN — not end-to-end verified** | Requires the manually dispatched authenticated workflow with dedicated `shoir-e2e-*` accounts and protected GitHub Actions secrets. |
| Full 96-module browser matrix and real file round trips | **OPEN — not established by this repair** | Must be completed against the deployed app, with module-specific outputs, entitlement denials and reopened output artifacts recorded. |
| Streamlit deployed revision | **UNVERIFIED** | The Edge Function deployment does not prove which Git revision Streamlit Cloud is serving. Confirm the live application build and run authenticated browser verification. |

## Current verification record — 2026-10-19

This record reflects the 2026-10-19 release-readiness consolidation. Current `main` is `2ec8002e19550031b177eb03ed680458b432edbb`, after PRs [#135](https://github.com/MSJ1708/shoir-ie/pull/135) through [#140](https://github.com/MSJ1708/shoir-ie/pull/140) were merged. The merged implementation changes passed their applicable CI workflows on the reviewed implementation revisions; PR #135's last follow-up was documentation-only. Consolidated-main validation, engine regression and security/quality all passed. This audit branch's five CI workflows also passed, including a fresh anonymous desktop/mobile browser smoke at the live URL. None of these results proves authenticated sign-in, renewal, private workspace isolation or module-by-module end-to-end correctness.

| Area | Current status | Evidence / boundary |
|---|---|---|
| Compile and regression suite | **PASS — consolidated `main` and audit PR** | Current `main` validation passed at [run 39238423936](https://github.com/MSJ1708/shoir-ie/actions/runs/39238423936). The audit branch's compile/full-regression validation passed at [run 39238591641](https://github.com/MSJ1708/shoir-ie/actions/runs/39238591641). |
| Engine regression | **PASS — consolidated `main` and audit PR** | Current `main` passed at [run 39238424017](https://github.com/MSJ1708/shoir-ie/actions/runs/39238424017); the audit branch passed at [run 39238591708](https://github.com/MSJ1708/shoir-ie/actions/runs/39238591708). |
| Security and quality checks | **PASS — consolidated `main` and audit PR** | Current `main` passed at [run 39238424016](https://github.com/MSJ1708/shoir-ie/actions/runs/39238424016); audit PR security/quality passed at [run 39238591616](https://github.com/MSJ1708/shoir-ie/actions/runs/39238591616), including dependency audit and secret-pattern guard. This is not a penetration test or independent certification. |
| Public hosted entry screen | **PASS — fresh anonymous browser smoke on 2026-10-19** | [Audit validation run 39238591641](https://github.com/MSJ1708/shoir-ie/actions/runs/39238591641) passed against `https://shoir-ie-app.streamlit.app/`: HTTP 200, app marker found, registration and Explore Modules public tabs passed at desktop (1440×1000) and mobile (390×844), no fatal marker, uncaught JavaScript error or horizontal overflow. [Screenshot/report artifact](https://github.com/MSJ1708/shoir-ie/actions/runs/39238591641/artifacts/12180461428). The report also captured nonfatal 404 responses for an external Heap script and Streamlit `/api/v2/user/details`; these were not smoke blockers, but remain diagnostics to triage rather than claiming a zero-network-error result. This remains unauthenticated. |
| Subscription backend deployment | **PASS — deployed configuration checked; endpoint walkthrough pending** | Supabase `shoir-persistence` is deployed at version 7. `shoir_sessions.scope` exists, is NOT NULL and defaults to `workspace`; the private payment-proof bucket and restrictive storage policy are configured. The Edge Function also rejects renewal requests for the protected `sho` administrator. Repository tests assert source contracts, but an authenticated walkthrough is still required to verify deployed login, renewal, upload, signed-link and workspace endpoints end to end. |
| Admin tier | **PASS — record checked** | Existing admin record is active, retains role `Enterprise Admin` and long-dated expiry `2099-01-01 UTC`, and now has tier `Enterprise Plus Tier ($399)`. No password or account recreation was performed. |
| Renewal payment review | **Implemented / backend configured; end-to-end pending** | Transaction reference is validated server-side. The private `subscription-payment-proofs` bucket is provisioned with a 512 KiB limit and PNG/JPG/PDF allowlist; `storage.objects` also has a restrictive policy denying direct `anon`/`authenticated` access to that bucket, even if another permissive storage policy is added. Edge v6 uploads there and returns five-minute URLs only to an admin session. Verify upload/review with an authorized test account before calling the flow end-to-end passed. |
| Core account/workspace RLS | **PASS — policy inspected** | `shoir_accounts`, `shoir_pending_credentials`, `shoir_sessions`, `shoir_subscription_requests` and `shoir_workspace_states` have server-only policies with `USING false` and `WITH CHECK false` for `anon`/`authenticated`. The service-role Edge Function is the designed persistence boundary. |
| Authenticated sign-in, expiry, renewal and restoration | **BLOCKED — not browser verified** | This run had no authorized test credential or already-authenticated browser session available to exercise the private account journey. The public smoke deliberately does not sign in. Do not claim these cases passed from static checks alone. |
| Module-by-module rendering, imports/downloads, persistence after restart, roles/tiers and tenant isolation | **OPEN — not fully browser verified** | The matrix below is the acceptance checklist. A public shell smoke is not evidence for these private workflows. |
| Platform-table security advisor | **PASS — deny-by-default policies applied** | All five public platform tables now have explicit `FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)` policies. Security advisor returns no lints; direct table-grant query returns no privileges for `anon`/`authenticated`. Trusted service-role Edge operations are unchanged. |

| Merged safeguards — module policy and workspace evidence | **PASS — automated PR coverage** | PRs #135–#140 now merge module entitlement synchronization, owner-scoped Excellence Hub and investor artifact history, research protocol/run ownership, project autosave/decision-spec ownership, and defensive ShadowShift evidence normalization. See the linked PRs above. These are source-level regression results, not end-to-end tenant-isolation certification. |

**Release decision:** automated and public-shell checks passed, but **the full definition of done remains OPEN** until authorized authenticated browser tests and the remaining module/import/export/persistence/security matrix rows are recorded with evidence.

## Authenticated end-to-end test runner

The manual, secrets-backed test runner and its account-safety requirements are documented in [AUTHENTICATED_RELEASE_GATE.md](AUTHENTICATED_RELEASE_GATE.md). Do not use the master administrator or customer accounts. Results remain **unverified until a maintainer runs the workflow against the intended deployed build**.

## Account, subscription and session matrix

| ID | Scenario | Expected result | Minimum evidence |
|---|---|---|---|
| AUTH-01 | Valid non-admin login before expiry | Authenticate and open the entitled workspace | Browser recording/checklist + session result |
| AUTH-02 | Invalid password | No session; useful generic error; rate limit remains effective | Automated + browser |
| AUTH-03 | Expired subscription with correct credentials | No workspace access; renewal-only screen opens | Automated + browser |
| AUTH-04 | Renewal-only token attempts workspace load/save | Server denies both operations | Deployed Edge API integration test + authenticated browser |
| AUTH-05 | Renewal-only token submits own renewal request | Request becomes Pending; cannot read another workspace or administer accounts | Deployed Edge API integration test + authenticated browser |
| AUTH-06 | Renewal request without transaction reference | Client refuses submission and explains that a reference is required; receipt upload alone is not treated as durable payment evidence | Automated + browser |
| AUTH-07 | Active subscriber submits renewal | Pending request appears in administrator request queue | Browser check with test account |
| AUTH-08 | Administrator approves renewal | Existing account is updated; expiry is extended from the later of now/current expiry; data remains associated with same user | Database before/after + browser |
| AUTH-09 | Administrator declines renewal | Access is not extended and request status is Declined | Database + browser |
| AUTH-10 | Subscription reaches expiry while session is open | 60-second countdown fragment forces a full logout/rerun at zero, saves best-effort state, clears the prior session, and explains that the user must sign in again with the same account to open renewal-only flow | Automated source/CI + authenticated browser still required |
| AUTH-11 | Renewal token expires | Renewal submission fails safely; user can return to sign-in | Automated + browser |
| AUTH-12 | Admin account login | Role remains Enterprise Admin; tier is Enterprise Plus; long-dated expiry remains intact | Database + authorized browser |
| AUTH-13 | New login after approved renewal | Full workspace returns with prior profile and saved workspace | Browser reload/re-login evidence |

## Module rendering and navigation matrix

Test every current catalog item and legacy route that remains reachable, not only the highlighted flagship modules.

| Area | Required checks |
|---|---|
| Home / Workbench / navigation | No blank surfaces, stuck spinners, stale selection, or unintended fall-through; welcome and user/tier context are correct |
| Explore Modules | Search/category/tier filters work; each visible card has understandable benefits and examples; all six plan/add-on entries display |
| Industrial Workbook | Open/create/import/edit/calculate/export/re-import round trip; formulas, sheet names and values remain coherent |
| Excel Cleaning & Import | Single- and multi-sheet imports, duplicate columns, oversized or malformed files, empty input, formula-injection strings and working downloadable outputs |
| Facility Layout & Warehousing | Department list, from-to flows, SLP rankings/heatmaps, layout comparisons, invalid and missing flow data |
| Production Bottleneck & Capacity Recovery | Constraints and unit consistency; scenario changes invalidate stale results; evidence includes source assumptions; export works |
| Enterprise Integration & Collaboration | Module renders, connector validation/health gives actionable errors, and unsupported/unconfigured connectors are never shown as live |
| Optimization / Simulation / Forecasting | Feasibility, solver failure, missing data, reproducibility, scenario isolation and sensible diagnostics |
| Quality / Reliability / Maintenance | Invalid subgroup/sample data, units, boundaries and missing measurements are handled without a crash |
| ShadowShift | Observed interruption and recovery are distinct; projections and scenario stress are labeled estimates; evidence export round-trips |
| Venture Studio | Customer/pilot/evidence/ROI chain persists; unverified claims are not promoted to verified outcomes |
| Executive Report Center | PDF/PPT/Excel opens, is readable, includes the intended scope and does not fabricate metrics |
| Every remaining module | Render with sample data, empty state, malformed data and a permitted plan; check export and safe error handling |

## Import, export and persistence matrix

- Upload a valid workbook with multiple sheets; verify detected sheets, row counts and download buttons.
- Upload a malformed, unsupported, duplicate-column, oversized and formula-injection input; the prior valid dataset must not be silently replaced.
- Download every claimed output format; reopen it and verify sheet names, row counts, formulas-as-intended, encoding and data values.
- Change a workspace field, reload the page, sign out/in, then repeat after app restart.
- Verify workspace states, research records, payment request metadata, profile attributes and report artifacts stay associated with the same normalized account.
- Verify save/load errors remain visible and actionable; do not silently claim durability if the managed backend fails.

## Authentication abuse protection

Server-side login rate limiting is being added in the same reviewed release series. It requires migration `20261019123300_server_side_login_rate_limits.sql` to be applied before deploying the Edge Function revision that calls it. The throttle table and RPC deny `anon`/`authenticated` access and grant the RPC only to `service_role`. Verify this order and the live behavior before marking AUTH-02 complete.

## Role, tier and tenant isolation matrix

- Admin account is Enterprise Plus and retains Enterprise Admin role.
- Non-admin users cannot navigate to or invoke admin actions directly.
- Every listed plan is tested for allowed and denied modules (not merely hidden navigation).
- Renewal-only sessions cannot call any workspace read/write endpoint or administrator operation.
- One user cannot load, overwrite, export or enumerate another user's workspace state, studies, artifacts, receipts or reports.
- Confirm inactive accounts, expired sessions and expired subscriptions are denied server-side.
- Confirm session tokens are not printed in logs or exposed in UI; password hashes and service-role secrets never appear in client-visible responses.
- Review RLS policies and service-role-only database operations before sensitive customer data is used.

## Release evidence record

For each run, retain commit SHA, CI workflow URL, environment/build, timestamp, account class (never password), scenario, expected outcome, actual outcome, artifact or screenshot reference, and linked issue for each failure. Redact emails, receipts, tokens, personal data and production datasets.

**Definition of done:** every required automated job passes; the hosted browser walkthroughs pass using authorized test accounts; all relevant module, export, persistence, role, tier and security cases have evidence; high-severity findings are resolved; and remaining limitations are explicitly accepted. Do not use “fully verified” when a browser pass or a required matrix row is still blocked.
