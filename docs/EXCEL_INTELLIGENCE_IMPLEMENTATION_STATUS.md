# Excel Intelligence — Staging implementation status

**Feature:** Excel Intelligence  
**Branch:** `feat/excel-intelligence-workbench-data-20261103`  
**Target:** `staging-e2e-20261019`  
**Production status:** Not deployed. No production migrations or data changes.

## Implemented in this change

- Added **Workbench → Data → Excel Intelligence** using the existing Workbench `MODULE_MATRIX` and module renderer. No separate navigation system or duplicate application was introduced.
- Added an entry to the shared platform catalog under the `Data Platform` category, so the existing application-shell grouping can route it to **Data**.
- Reused the existing safe Excel ingestion/runtime for workbook import, multi-sheet processing, cleaned-table review, quality flags, field intelligence, provenance, and explicit export.
- Kept the existing Starter **Excel Data Cleaning & Import** module and its access policy intact.
- Added server-side entitlement enforcement for the new premium module. Default minimum tier: **Enterprise**. The operator may configure `SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER` to one of the six existing package names. Invalid values fail closed to **Enterprise Plus**.
- Removed the prior Office add-in behavior that POSTed a selected range to any manually configured host without authentication. The Office.js task pane now performs local-only sheet/selection inspection, limits a selected range to 10,000 cells, and supports clipboard export.
- Kept Shoir-IE's fixed 96-module subscription inventory intact; Excel Intelligence is a separately governed Workbench Data capability with its own server-side entitlement policy. Added regression tests for navigation, routing, tier policy, and the add-in's local-only data boundary.

## Not yet complete — Stage 1 remains open

This change does **not** establish that the full Excel Intelligence specification has passed Stage 1. The following items remain blocked or unverified:

- No authenticated Shoir-IE workbook API is deployed. The former `POST /api/workbook/import` endpoint was documentation only.
- The Office add-in manifest still contains `YOUR-SHOIR-IE-HOST` placeholders and has not been hosted/sideloaded in the staging Excel desktop or web clients.
- No task-pane Shoir-IE sign-in or validated token exchange exists.
- Natural-language AI planning and controlled task execution are not implemented in this increment.
- The Office add-in does not write formulas, create charts/PivotTables, or return an output workbook.
- The in-app upload runtime cleans and profiles data but does not yet deliver every Stage 1 operation (formula generation, chart creation, and full preservation of all advanced workbook features).
- No authenticated browser test has proved the exact menu selection under each supported account/tier.
- No Office desktop/web compatibility acceptance has been run.

## Required staging configuration before enabling server transfer

The API host, identity/token validation, allowed origins, maximum payload limits, explicit data-transfer notice/consent, per-user/workspace checks, rate limits, audit events, retention policy, and cross-tenant denial tests must be implemented and deployed in staging before the add-in is allowed to upload workbook data.

## Acceptance status

- Workbench Data registration and route: **IMPLEMENTED_NEEDS_VALIDATION**
- Server-side tier gate: **IMPLEMENTED_NEEDS_VALIDATION**
- Local Office.js selected-range inspector: **IMPLEMENTED_NEEDS_VALIDATION**
- Full Stage 1 Excel Intelligence: **BLOCKED / NOT VERIFIED**
- Stages 2–4: **NOT STARTED**

No production deployment, production migration, live customer data mutation, or release-readiness claim is included.
