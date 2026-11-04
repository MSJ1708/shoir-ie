# Shoir-IE Master Readiness Audit

**Review date:** 2026-11-04  
**Scope:** repository and authorised staging environment only  
**Release decision:** NO-GO for production and paid customer launch  
**Production mutation performed by this review:** none

## 1. Verified repository baseline

| Item | Observed value |
|---|---|
| Repository | MSJ1708/shoir-ie |
| Default branch | main |
| main SHA at review | `2ef44057f84162389d39998e922b505dcfe4d3e9` |
| Staging branch | `staging-e2e-20261019` |
| Staging SHA at review | `f00da78a01e2ecf07fe263ddf570cbc1e075ac31` |
| Staging branch protection | GitHub reports protected |
| main vs staging | Diverged; staging is 107 commits ahead and 412 behind |
| Review branch | `audit/ultimate-master-readiness-2026-11-04` (based on the staging SHA above) |

The staging branch is not a safe merge candidate for main. Do not merge or rebase these branches as part of this audit. Review the existing open pull requests and reconcile their intended scope before creating overlapping implementation work.

## 2. Staging infrastructure

The connected Supabase project list identifies:

- Staging: `hfhrosthswcybccepmak`, project name `shoir-ie-staging-2026-10-19`, ACTIVE_HEALTHY, EU Central, PostgreSQL 17.11.0.003.
- Production: `gcsamrdaeraxieaagsta`, project name `shoir-ie-production`, ACTIVE_HEALTHY, EU Central, PostgreSQL 17.6.1.166.

Only staging was queried for database schema, migration ledger, Edge Function and protected-admin verification. No production database query or mutation was performed by this review.

The staging `shoir-persistence` Edge Function is ACTIVE at version 12. Its deployed `index.ts` and `security.ts` were retrieved and byte-compared with the staging branch source; both matched exactly. Function SHA-256 reported by Supabase: `111064715f699640edd319c06e4b2f32c57ff3b02231fe19d9870e20959f95e1`.

The dedicated staging entry point is `staging_app.py`; it sets `SHOIR_ENVIRONMENT=staging` and invokes the shared `app.py`. The actual hosted staging Streamlit hostname and authenticated browser deployment were not verified in this review.

## 3. CI and acceptance evidence

Latest staging validation run: [41716603183](https://github.com/MSJ1708/shoir-ie/actions/runs/41716603183), commit `f00da78a01e2ecf07fe263ddf570cbc1e075ac31`, completed successfully on 2026-11-03.

The successful job included dependency installation, Python compilation, the repository pytest suite, Deno type checking, persistence Edge Function security tests, synthetic PDF/PPTX rendering, application import smoke testing, local Streamlit startup and local desktop/mobile browser smoke.

Two distinct hosted checks did not run:

- The workflow's hosted `live-deployment-smoke` job was skipped on the staging branch.
- Authenticated release gate run [41716603380](https://github.com/MSJ1708/shoir-ie/actions/runs/41716603380) was skipped. The workflow is intentionally opt-in through manual dispatch or an explicit commit marker and requires configured staging URLs and disposable `shoir-e2e-*` accounts.

A successful local CI run is not proof of authenticated hosted staging acceptance.

## 4. Existing feature inventory

The current repository already contains a substantial feature catalogue and test suite. Do not create duplicate module IDs or replace the existing catalogue.

The existing `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv` contains 100 unique canonical IDs with no duplicates. Its current status counts are:

| Existing matrix status | Count |
|---|---:|
| IMPLEMENTED_NEEDS_VALIDATION | 87 |
| FOUNDATION_ONLY | 11 |
| EXTERNAL_CONFIGURATION_REQUIRED | 2 |
| **Total** | **100** |

The 11 foundation-only and two externally dependent entries are listed in the feature completion matrix. These counts are inventory counts, not verified-workflow counts. The existing 96-module subscription catalogue remains separate from the Workbench Data Excel Intelligence capability; do not create a 97th subscription-catalogue entry for it.

## 5. Staging database findings

The staging migration ledger currently contains 17 entries. The last recorded version is `20261025164602`, named `20261023130000_refresh_refund_policy_acceptance_version`.

The repository contains `20261026110000_safe_beta_legal_referrals.sql`, but this migration is not present in the staging ledger returned by Supabase. The historical `20261021130000` migration has already been applied in staging and its source file contains account-field updates. Do not replay that historical migration or manufacture migration history entries. Reconcile the database ledger and repository files with a reviewed manifest and a staging-only rehearsal before any schema change.

All 12 tables listed in the staging public schema had RLS enabled. `public.shoir_referrals` had no RLS policies; its repository migration explicitly revokes access from PUBLIC, anon and authenticated and grants the service role, so this appears intentionally server-only and must be verified against the deployed function path rather than patched blindly.

The staging `shoir_internal` schema contains 12 tables with RLS disabled: `artifacts`, `twin_assets`, `twin_snapshots`, `twin_scenarios`, `connector_health`, `jobs`, `collaboration`, `knowledge`, `monitoring_rules`, `monitoring_events`, `report_provenance`, and `security`. The Supabase table inspection surfaced a critical RLS-disabled advisory. Follow-up privilege checks found no schema USAGE or table SELECT privilege for `anon` or `authenticated` on the checked internal schema/table. The database session returned no value for `pgrst.db_schemas`, so the Data API exposed-schema configuration was not established by that query. Treat this as an important defense-in-depth and configuration-verification issue; do not assert current public exposure without confirming API schema exposure and every caller.

The internal tables showed zero rows at the time of metadata inspection. Do not interpret this as proof that they are unused or safe to remove.

## 6. Protected administrator invariant

A read-only aggregate query on staging returned:

- Exact protected-admin invariant matches: 1.
- Active Enterprise Admin accounts: 1.

The source helper `hasCanonicalMasterAdminInvariant` checks the reserved identity, Enterprise Admin role, Enterprise Plus tier, active state and exact UTC expiry. The historical seed migration is now a no-op and does not create or reset the account.

The protected administrator was not used for testing, impersonation or routine verification. No administrator data was changed.

## 7. Product architecture evidence

The repository contains:

- Streamlit application shell and Industrial Engineering Workbench.
- Industrial Control Center / command-centre entry point.
- A 96-module subscription catalogue and 100-tool implementation matrix.
- Engineering, optimization, forecasting, quality, layout, resilience and research modules.
- Excel Intelligence runtime, studio, Workbench route and Office add-in source scaffold.
- A Digital Thread module.
- Copilot orchestrator, typed tool registry and Trust Center.
- Enterprise operations/services, persistence, workspace RBAC and Supabase Edge Function.
- Database migrations, CI workflows and an extensive pytest suite.

These source files establish implementation foundations, not complete customer-ready workflows. The Digital Thread's current `stable_id(node_type, name, source)` derives IDs from the display name; a rename can therefore produce a different derived ID. A rename-safe identity contract needs a backward-compatible design and migration tests before claiming canonical identity stability.

## 8. Mandatory outstanding gates

1. Fresh authenticated hosted staging test on the exact current application and Edge Function pair.
2. Confirm the actual staging Streamlit hostname and staging-only app secrets; verify the banner before entering any credentials.
3. Run the authenticated backend lifecycle, workspace isolation and 96-module browser matrix using disposable E2E identities.
4. Reconcile staging migration ledger and repository migration files without replaying historical data-rewriting SQL.
5. Review `shoir_internal` RLS-disabled tables, schema exposure and all connection roles; design least-privilege policies before any DDL.
6. Verify cross-tenant data, file, export and AI-tool access through real authorised and denied requests.
7. Rehearse database and storage restore in an authorised isolated environment.
8. Independently validate critical engineering calculations, units, optimizer status and simulation assumptions.
9. Complete Office desktop/web host tests and any required Excel add-in authentication/transfer architecture.
10. Complete commercial, Saudi privacy and legal reviews with qualified professionals.

## 9. Review conclusion

The staging source has strong automated regression evidence and a meaningful set of engineering and enterprise foundations. It does not yet have the authenticated hosted staging proof, fully reconciled migration evidence, complete tenant/security acceptance, restore rehearsal or commercial clearance required by the user's release gates.

**Current decision: NO-GO.** Keep BETA status and production deployment hold in place.
