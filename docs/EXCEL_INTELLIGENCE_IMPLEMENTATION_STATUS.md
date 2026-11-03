# Excel Intelligence — Staging implementation status

**Feature:** Excel Intelligence  
**Branch:** `feat/excel-intelligence-workbench-data-20261103`  
**Target:** `staging-e2e-20261019`  
**Production status:** Not deployed. No production migrations or data changes.

## Implemented in this change

- Added **Workbench → Data → Excel Intelligence** using the existing Workbench `MODULE_MATRIX` and module renderer. No separate navigation system or duplicate application was introduced.
- Registered the feature only in the Workbench Data module matrix; it is deliberately not added as a 97th item to the fixed 96-module subscription catalogue.
- Reused the existing safe Excel ingestion/runtime for workbook import, multi-sheet processing, cleaned-table review, quality flags, field intelligence, provenance, and explicit export.
- Added an optional, bounded source-formula scan for XLSX/XLSM: it verifies the original upload hash, caps inspection at two million used-range cells and the inventory at 10,000 formula rows, and exports source formula text as inert evidence in a separate `FORMULA INVENTORY` sheet. Formulas are not executed or copied into cleaned data.
- Added a bounded OOXML package scan for formulas, macros, charts, pivots, named ranges, external links, images, data validations and conditional formatting. When unsupported source features are detected, the UI warns the user and disables data-focused export until the user explicitly acknowledges the preservation risk; the original upload remains unchanged.
- Added OOXML ZIP preflight checks before workbook parsing: 75 MB upload limit, 512 MB total expanded-package limit, 256 MB per-member limit, 10,000-member limit, 500:1 maximum compression ratio, encrypted-member rejection, duplicate-path rejection and archive path-traversal rejection.
- Kept the existing Starter **Excel Data Cleaning & Import** module and its access policy intact.
- Added server-side entitlement enforcement for the new premium module. Default minimum tier: **Enterprise**. The operator may configure `SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER` to one of the six existing package names. Invalid values fail closed to **Enterprise Plus**.
- Replaced the read-only Office.js scaffold with a local-only, deterministic task planner and an explicit operation allow-list. It inspects a selection of up to 10,000 cells, fingerprints the selected workbook data, and proposes supported operations before execution. The default task-pane preview is a bounded metadata summary rather than a full 10,000-cell JSON render; full JSON is copied only after explicit user action. Re-inspection and instruction changes invalidate prior plans. It does not send workbook contents to any server or external AI model. A compact local change fingerprint is used only for stale-plan detection and is not an authentication or authorization control.
- Added copy-first Office.js execution: after explicit approval, the add-in creates a uniquely named `Shoir-IE Results` worksheet, copies the selected values/formulas/number formats, and applies supported edits only to that new worksheet. The selected source worksheet is not written to. Current write operations are trimming text constants (while skipping formula-like strings after trimming), adding SUM/AVERAGE summary formulas, and creating a column chart; read-only inspection reports missing cells, duplicate data rows, formula-error values and formula counts. Plans warn that formulas referencing cells outside a copied selection may need review on the results worksheet.
- Added an approval-first Copilot tab. It binds the plan to the current instruction, worksheet and data fingerprint, and separately fingerprints the exact plan shown for approval. It re-builds and verifies that plan at execution; enforces authentication and the configurable tier again; runs the existing deterministic Copilot orchestrator against a copy; checks source preservation; and exports a separate analysis workbook plus evidence ZIP.
- Kept Shoir-IE's fixed 96-module subscription inventory intact; Excel Intelligence is a separately governed Workbench Data capability with its own server-side entitlement policy. Added regression tests for navigation, routing, tier policy, Copilot approval/source preservation and the add-in's local-only data boundary.

## Not yet complete — Stage 1 remains open

This change does **not** establish that the full Excel Intelligence specification has passed Stage 1. The following items remain blocked or unverified:

- No authenticated Shoir-IE workbook API is deployed. The former `POST /api/workbook/import` endpoint was documentation only.
- The Office add-in manifest still contains `YOUR-SHOIR-IE-HOST` placeholders and has not been hosted/sideloaded in the staging Excel desktop or web clients.
- No task-pane Shoir-IE sign-in or validated token exchange exists. The existing browser `remote_session_token` is a broad, long-lived workspace session and must not be copied into Excel. A future bridge must mint and validate a separate short-lived Excel-scoped token, bind it to the user and entitlement, and revoke/expire it independently.
- The current persistence Edge Function response helper emits wildcard CORS. A workbook-data API must not be enabled for Excel under that policy; it needs an explicit allowlist for the actual Office task-pane origins, bounded request parsing, consent, and negative cross-user tests before any workbook transfer is activated.
- The current Copilot uses the existing deterministic intent classifier and analysis engine. External generative-model/LLM task authoring is not configured and is not claimed.
- The Office add-in can now create a results worksheet and apply the limited approved local operations listed above. It can prepare a separate compressed OOXML copy of the current workbook and expose a download link on hosts that support the Office CompressedFile requirement set (Excel desktop for Windows/Mac); it validates the complete slice length and caps exports at 100 MB. The host matrix has not been runtime-tested, so Excel desktop/web parity is not claimed. The local add-in still does not create PivotTables or provide a dedicated add-in-to-Shoir-IE authenticated workflow. The selected source worksheet remains unchanged by the current write path.
- The in-app upload runtime cleans and profiles data but does not yet deliver every Stage 1 operation (formula generation, chart creation, and full preservation of all advanced workbook features).
- No authenticated browser test has proved the exact menu selection under each supported account/tier.
- No Office desktop/web compatibility acceptance has been run. In-app table previews are now bounded to protect Streamlit rendering, with a text fallback when the interactive table renderer fails; regression tests cover this path but do not replace hosted browser/Excel acceptance.

## Required staging configuration before enabling server transfer

The API host, identity/token validation, allowed origins, maximum payload limits, explicit data-transfer notice/consent, per-user/workspace checks, rate limits, audit events, retention policy, and cross-tenant denial tests must be implemented and deployed in staging before the add-in is allowed to upload workbook data.

## Acceptance status

- Workbench Data registration and route: **IMPLEMENTED_NEEDS_VALIDATION**
- Server-side tier gate: **IMPLEMENTED_NEEDS_VALIDATION**
- Local Office.js inspection and deterministic planner: **IMPLEMENTED_NEEDS_VALIDATION**
- Copy-first, approval-gated local operations (text trim, SUM/AVERAGE, column chart): **IMPLEMENTED_NEEDS_VALIDATION**
- Local separate workbook-copy preparation/download link on hosts reporting CompressedFile support (100 MB cap and full-slice validation): **IMPLEMENTED_NEEDS_VALIDATION**
- Full Stage 1 Excel Intelligence: **BLOCKED / NOT VERIFIED**
- Stages 2–4: **NOT STARTED**

No production deployment, production migration, live customer data mutation, or release-readiness claim is included.
