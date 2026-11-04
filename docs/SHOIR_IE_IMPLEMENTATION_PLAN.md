# Shoir-IE Implementation Plan — Evidence-First Staging Sequence

**Review date:** 2026-11-04  
**Target:** authorised staging branch/environment only  
**Production:** out of scope and unchanged

This plan is an execution order, not a claim that planned work is complete. The existing tool IDs, module catalogue and navigation should be preserved.

## Phase 0 — Baseline and branch safety

- [x] Confirm repository and default branch.
- [x] Confirm named staging branch and exact commit.
- [x] Confirm staging and production Supabase project identities from the connected project list.
- [x] Inspect the staging schema, migration ledger, Edge Function version and security/performance advisors.
- [x] Verify protected administrator invariant through an aggregate read-only query.
- [x] Inspect current CI and authenticated release-gate triggers.
- [ ] Complete a full source-to-route-to-test mapping for every Workbench module.
- [ ] Inspect all open PRs and reconcile overlapping implementation branches.
- [ ] Confirm branch rules, required checks and administrator enforcement with repository settings owner.

## Phase 1 — Release-critical security and data integrity

1. Obtain a fresh authenticated staging run on the exact deployed build, using only disposable `shoir-e2e-*` identities.
2. Confirm the staging banner and hostname before submitting credentials.
3. Reconcile the 17-entry staging migration ledger against repository migration source. Specifically account for version `20261025164602` and repository migration `20261026110000_safe_beta_legal_referrals.sql`.
4. Review the 12 RLS-disabled `shoir_internal` tables: Data API schema exposure, schema/table grants, owner/worker connection roles, all query paths and least-privilege policies. Do not enable RLS without a tested policy/access plan.
5. Re-test cross-account and cross-workspace access, sessions, role/tier gates, exports and file access.
6. Complete a staging backup and isolated restore rehearsal with measured RPO/RTO evidence.
7. Verify no CORS/host/Edge allowlist mismatch exists for the actual staging app hostname.
8. Keep the protected administrator read-only and excluded from all test matrices.

## Phase 2 — Shared engineering foundations

- Design immutable canonical IDs independent of display names; add backward-compatible rename and alias mapping.
- Consolidate master data and asset identity only after existing schemas and module ownership are mapped.
- Define one versioned unit and conversion library with dimensional checks.
- Standardise calculation/run evidence records across engineering modules.
- Define dataset immutability, version history and downstream invalidation.
- Verify organisation/project scope on every persistence, storage, search and background-job path.
- Standardise approval and audit transitions.

## Phase 3 — Original engineering areas

Work through the existing nine engineering areas and shared Excel/Copilot capabilities. For each feature, trace the UI entry, calculation engine, persisted data, entitlement, unit/reference tests, negative cases and authenticated hosted workflow.

Priority order:
1. manufacturing/capacity;
2. supply-chain/inventory;
3. quality;
4. facility layout/material flow;
5. project controls/cost;
6. workforce scheduling;
7. reliability/maintenance;
8. energy/resource efficiency;
9. simulation/decision intelligence;
10. Excel Intelligence;
11. Copilot.

Do not promote partial methods into complete modules. Preserve existing known calculation behaviour until reference-tested replacement behaviour is accepted.

## Phase 4 — Cross-workspace decision lifecycle

Connect baseline, data source, calculation, scenario, recommendation, decision, approval, implementation action and measured outcome. Keep estimated, simulated, forecast and measured benefits separate. Add a repeatable verification method before claiming realised savings.

## Phase 5 — Operational workflows

Audit and integrate work orders, CAPA, engineering change, shutdown/turnaround, traceability, laboratory testing, procurement, competency, spare parts, environmental records and resilience through existing shared services. Add only workflows with real persistence, authorisation, audit and tests.

## Phase 6 — Advanced engineering capabilities

Validate Operations Research methods and solver status; add process mining, logistics, calibrated twin levels, real-time monitoring and 3D only when required inputs and external sources are available. Prefer accurate 2D layouts over decorative 3D.

## Phase 7 — Enterprise and commercial readiness

Complete SSO/MFA provider setup where available, API/webhook security, notifications, report scheduling, accessible Arabic/RTL workflows, onboarding and role/entitlement tests. Obtain qualified legal/security review for Saudi privacy, consumer and commercial requirements.

## Phase 8 — Staging acceptance and release assessment

Run every required user journey and negative test on the exact hosted staging SHA. Retain redacted evidence. Reopen and inspect every exported file. Verify persistence across reload/re-login and run tenant isolation tests. A successful general CI suite alone is insufficient.

**Current gate:** Phase 0 baseline evidence is materially established; Phase 1 remains open. Release remains NO-GO.
