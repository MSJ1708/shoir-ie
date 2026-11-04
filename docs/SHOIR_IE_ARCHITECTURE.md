# Shoir-IE Architecture — Current State and Target Boundaries

**Review date:** 2026-11-04  
**Scope:** evidence-backed staging-branch source review

## 1. Current application shape

Shoir-IE is a Python/Streamlit application. The principal application entry point is `app.py`; `staging_app.py` is the staging entry point, forces `SHOIR_ENVIRONMENT=staging` and invokes the shared application.

Relevant user-facing structure includes the Industrial Engineering Workbench, Industrial Platform Command Center and existing dashboard/Industrial Control Center surfaces. The application already groups a large set of tools behind a shared navigation model. Continue to extend those contexts instead of adding one top-level page per proposed capability.

The repository currently distinguishes:

- 96 subscription-catalogue modules.
- 100 canonical tool entries in `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`.
- Excel Intelligence as a separately governed Workbench Data capability, not an extra subscription-catalogue module.

These inventories are different by design and should not be conflated.

## 2. Application and engineering modules

Observed code boundaries include:

| Responsibility | Source examples |
|---|---|
| Application shell / navigation | `app.py`, `shoir_application_shell.py` |
| Engineering Workbench | `pages/Industrial_Engineering_Workbench.py` |
| Command Center | `pages/Industrial_Platform_Command_Center.py` |
| Manufacturing/capacity | `shoir_capacity_recovery.py`, `shoir_target_engines.py` |
| Facility layout | `shoir_facility_layout.py` |
| Forecasting / optimization / simulation | `shoir_forecasting.py`, `shoir_optimization.py`, `aegis_sim.py`, `shoir_resilience_suite.py` |
| Digital Thread | `shoir_digital_thread.py` |
| Copilot and tool governance | `shoir_copilot_orchestrator.py`, `shoir_tool_registry.py`, `shoir_tool_trust_center.py` |
| Excel Intelligence | `shoir_excel_foundation.py`, `shoir_excel_runtime.py`, `shoir_excel_studio.py` |
| Enterprise services / operations | `shoir_enterprise_layer.py`, `shoir_enterprise_services.py`, `shoir_enterprise_ops.py` |
| Workspace access and persistence | `durable_account_store.py`, `workspace_persistence.py`, `shoir_workspace_rbac.py` |
| Supabase persistence boundary | `supabase/functions/shoir-persistence/index.ts`, `security.ts` |

This is a source map, not proof that every mapped surface is feature-complete or accessible on the hosted app.

## 3. Persistence and identity

The staging application uses a custom account/session persistence boundary through the Supabase Edge Function. Staging's deployed `shoir-persistence` function is version 12 and its deployed `index.ts` and `security.ts` match the current staging branch files byte-for-byte.

The Edge Function uses the Supabase service-role key server-side. Browser access is mediated by custom opaque sessions and action-specific validation; `verify_jwt=false` is configured for the function, so acceptance must focus on the custom session lifecycle, action scopes, revocation, rate limits, and denial paths rather than assuming Supabase Auth JWT is the app's session.

The repository also contains local SQLite/development support and an optional direct PostgreSQL path in enterprise services. Do not configure these paths against production or bypass the Edge persistence boundary in staging.

## 4. Shared platform data

The staging database has a public persistence schema with account/session/workspace tables and platform records, events, artifacts and jobs. All 12 currently listed public tables have RLS enabled. The referrals table is deliberately server-only in the repository migration (no anon/authenticated grants; service-role access).

The staging database also has a `shoir_internal` schema with internal artifact, twin, connector, job, collaboration, knowledge, monitoring, report-provenance and security tables. The 12 observed internal tables currently have RLS disabled. Read-only privilege checks found no schema USAGE or table SELECT privilege for anon/authenticated on the checked internal schema/table. Data API exposure settings were not established by the SQL session. Review actual callers, schema exposure and grants before changing policies.

## 5. Digital Thread identity constraint

The current Digital Thread helper derives IDs using node type, display name and source. As a result, a display-name change can alter the derived identifier. This does not meet the requested rename-independent canonical identity contract.

A safe correction requires:
- a canonical immutable identity key distinct from display name;
- an alias/rename operation that updates display fields without changing canonical ID;
- an explicit source-key strategy for imported records;
- collision and duplicate detection;
- backward-compatible mapping for existing IDs and saved workspaces;
- tests for rename, re-import, collision, ownership and restore.

Do not simply change the hash algorithm or regenerate existing IDs; that could orphan downstream references.

## 6. Standard execution/evidence boundary

The target shared workflow remains:

`IMPORT → VALIDATE → MAP → MODEL → RUN → VISUALIZE → COMPARE → EXPLAIN → DECIDE → EXPORT → VERIFY`

The existing code contains evidence manifests, calculation/run metadata and export mechanisms in several modules. A unified calculation/evidence contract must be validated across workspaces before the platform describes all results as reproducible or auditable.

Each execution should bind to immutable source/version identifiers, method/version, units, assumptions, actor/tenant, timestamps, status, warnings, output and relevant approval. Do not allow a downstream stage to display success if a required upstream stage failed.

## 7. Current target architecture principles

1. Keep one shared user/organisation/site/facility/asset identity layer.
2. Keep engineering-domain calculations in domain modules but centralise unit, provenance, version and execution services.
3. Keep all authorisation in backend services; client visibility is not an access control.
4. Use read-only external connectors first; no implicit calls during application imports.
5. Keep synthetic, imported, manual and connected data distinguishable at every display/export boundary.
6. Keep Excel original files immutable and transformations copy-first with preview/approval.
7. Keep Copilot tools typed, scoped, audited and approval-gated; never execute arbitrary AI-generated code or SQL.
8. Preserve the existing visual identity and workbench navigation.

## 8. Related source documentation

- `SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`
- `EXCEL_INTELLIGENCE_IMPLEMENTATION_STATUS.md`
- `EXCEL_INTELLIGENCE_CAPABILITY_MATRIX.md`
- `SHOIR_SECURITY_THREAT_MODEL.md`
- `AUTHENTICATED_RELEASE_GATE.md`
- `INDUSTRIAL_ENGINEERING_OS.md`
- `integrations/ERP_CONNECTOR_ARCHITECTURE.md`
