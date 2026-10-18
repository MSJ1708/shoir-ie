# Subscription, Module and Security Release Verification Matrix

Updated: 2026-10-18

This matrix is the release gate for the subscription renewal, account, module, import/export, and enterprise-access work. A row is complete only when the stated evidence exists. Source edits and static tests are not evidence of a successful authenticated browser journey.

## Verification status key

- **Implemented / source-reviewed** — code path exists; behavior may still require runtime proof.
- **Automated** — covered by a passing CI or local test result associated with the commit under review.
- **Browser verified** — completed against the hosted application using an authorized account; record date, account class, build, steps and observed outcome.
- **Blocked** — a dependency prevents a trustworthy test; document the dependency and do not mark the release definition of done complete.

## Account, subscription and session matrix

| ID | Scenario | Expected result | Minimum evidence |
|---|---|---|---|
| AUTH-01 | Valid non-admin login before expiry | Authenticate and open the entitled workspace | Browser recording/checklist + session result |
| AUTH-02 | Invalid password | No session; useful generic error; rate limit remains effective | Automated + browser |
| AUTH-03 | Expired subscription with correct credentials | No workspace access; renewal-only screen opens | Automated + browser |
| AUTH-04 | Renewal-only token attempts workspace load/save | Server denies both operations | Edge regression test |
| AUTH-05 | Renewal-only token submits own renewal request | Request becomes Pending; cannot read another workspace or administer accounts | Edge regression test + browser |
| AUTH-06 | Renewal request without reference or receipt | Client refuses submission and explains what is missing | Automated + browser |
| AUTH-07 | Active subscriber submits renewal | Pending request appears in administrator request queue | Browser check with test account |
| AUTH-08 | Administrator approves renewal | Existing account is updated; expiry is extended from the later of now/current expiry; data remains associated with same user | Database before/after + browser |
| AUTH-09 | Administrator declines renewal | Access is not extended and request status is Declined | Database + browser |
| AUTH-10 | Subscription reaches expiry while session is open | Workspace operations stop server-side; user can re-enter renewal-only flow | Edge regression + browser |
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
