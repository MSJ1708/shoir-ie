# Shoir-IE Known Limitations — 2026-11-04

This register records limitations confirmed or not yet ruled out by the current source and staging review. It is not a claim that every possible defect has been found.

## Release and environment

- The staging branch and main branch are heavily diverged (107 ahead / 412 behind). Do not merge them without a separate branch reconciliation.
- Latest automated staging validation passed, but its hosted smoke and authenticated release gate were skipped.
- The actual hosted staging Streamlit hostname/build was not verified.
- The Supabase migration ledger does not fully match the repository migration files; the safe referral migration in the repository is not recorded in the live staging ledger.
- No staging backup restore rehearsal was evidenced.

## Catalogue and feature state

- The existing 100-tool matrix has 87 entries marked IMPLEMENTED_NEEDS_VALIDATION, 11 FOUNDATION_ONLY and 2 EXTERNAL_CONFIGURATION_REQUIRED.
- No entry in that legacy matrix is represented as a fresh authenticated hosted route acceptance by the latest CI run.
- The fixed subscription catalogue contains 96 module routes. Excel Intelligence is a separate Workbench Data capability and must not be counted as a new subscription module.
- The additional capability inventory is not yet fully traced from every proposal to UI route, backend, database, entitlement and test.

## Engineering integrity

- Each high-value engineering method still requires independent reference fixtures and documented assumptions; global CI success alone is not method certification.
- RCM, digital-twin calibration, disruption simulation, supply-chain network planning, Undo/Redo, dataset lineage, CAPA, KPI alerts, API/plugin tooling and recovery centre remain foundation-level in the tool matrix.
- A complete end-to-end workflow from recommendation to independently verified outcome is not yet demonstrated across workspaces.
- The Digital Thread's current ID derivation includes display name and source; display-name rename can change the derived ID. Do not claim rename-stable canonical identity until backward-compatible alias/mapping is implemented and tested.

## Excel Intelligence

- Workbench Data registration and in-app workflow exist in source, but authenticated hosted app acceptance remains open.
- Full Stage 1 Excel specification is not complete; Stages 2–4 are not started per the existing implementation status.
- Office add-in manifest still has host placeholders; no verified installable Office add-in deployment or desktop/web host matrix is established.
- Office add-in planner is local-only. An authenticated workbook transfer API and separate short-lived Excel-scoped identity token are not established.
- Supported formula and OOXML limitations must remain visible; original workbook preservation and approval gates must not be weakened.
- Do not claim full Excel compatibility or full workbook-to-Shoir-IE conversion.

## Copilot and external connectors

- Current in-app Copilot uses a deterministic intent classifier and deterministic analysis engine. External LLM task authoring is not configured in the reviewed Excel status.
- Real SAP/Oracle, MES, CMMS, IoT and plant telemetry connectivity has not been established by this review.
- T096 Integration Management and T098 Enterprise Identity/Audit require external configuration and verified tests.
- Connector metadata or a healthy-looking local UI is not evidence of a live data feed.

## Security and enterprise

- Twelve `shoir_internal` tables have RLS disabled. Follow-up anon/authenticated privilege checks did not show USAGE or SELECT for the checked paths; Data API schema exposure and all application callers still need review.
- `public.shoir_referrals` has RLS enabled and no policy, with server-only grants defined in the migration. Preserve and test that boundary.
- Cross-tenant persistence, storage, search, export and AI-tool denial needs current authenticated hosted evidence.
- SSO/MFA provider activation, legal clearance, customer support ownership and commercial readiness are not established here.
