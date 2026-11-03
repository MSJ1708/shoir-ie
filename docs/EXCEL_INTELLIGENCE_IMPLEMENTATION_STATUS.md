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
- Extended the fidelity scan to detect source Excel tables, AutoFilters, merged cells, hidden rows/columns and non-default cell/row/column styles; each detected feature is added to the unsupported-feature acknowledgement list. Malformed OOXML style attributes are treated as non-matches rather than trusted as integers.
- Added formula-injection neutralization to all CSV files in the workbook evidence ZIP (field intelligence, validation review, source metadata, CLEAN and RAW table CSVs). The guard works on export copies and leaves in-memory/source frames unchanged.
- Added a one-use UUID plan identifier to each in-app Copilot proposal. A server-side Streamlit session registry claims a plan before analysis and rejects replays or concurrent duplicate execution. Rebuilding even an identical request creates a fresh plan ID and a new approval requirement. The approved execution record (actor/workspace, UTC approval time, source/data/request/plan fingerprints and deterministic-engine marker) is included in the UI evidence manifest and a new copilot_approval.json file in the downloadable ZIP.
- Bound every Copilot proposal to its owner and workspace. Immediately before execution, Shoir-IE now revalidates the existing opaque workspace session token against the live account/session records through a read-only `session_entitlement` action in the staging persistence Edge Function source. The response is restricted to that user's username, tier, active status and expiry; inactive, expired, changed-tier, mismatched-user and unavailable-backend cases fail closed. The source is synced to the deployed staging v11 baseline plus this additive action; staging deployment of the new Edge Function action and its end-to-end call remain pending. This does not create an Office add-in token or permit workbook transfer.
- Added OOXML ZIP preflight checks before workbook parsing: 75 MB upload limit, 512 MB total expanded-package limit, 256 MB per-member limit, 10,000-member limit, 500:1 maximum compression ratio, encrypted-member rejection, duplicate-path rejection and archive path-traversal rejection.
- Kept the existing Starter **Excel Data Cleaning & Import** module and its access policy intact.
- Added server-side entitlement enforcement for the new premium module. Default minimum tier: **Enterprise**. The operator may configure `SHOIR_EXCEL_INTELLIGENCE_MINIMUM_TIER` to one of the six existing package names. Invalid values fail closed to **Enterprise Plus**.
- Replaced the read-only Office.js scaffold with a local-only, deterministic task planner and an explicit operation allow-list. It inspects a selection of up to 10,000 cells, fingerprints the selected workbook data, and proposes supported operations before execution. The default task-pane preview is a bounded metadata summary rather than a full 10,000-cell JSON render; full JSON is copied only after explicit user action. Selections are additionally capped at an estimated 8 MB serialized payload because cell count alone does not bound long text. Re-inspection and instruction changes invalidate prior plans. It does not send workbook contents to any server or external AI model. A compact local change fingerprint is used only for stale-plan detection and is not an authentication or authorization control.
- Added copy-first Office.js execution: after explicit approval, the add-in creates a uniquely named `Shoir-IE Results` worksheet, copies the selected values/formulas/number formats, and applies supported edits only to that new worksheet. The selected source worksheet is not written to. Current write operations are trimming text constants (while skipping formula-like strings after trimming), adding SUM/AVERAGE summary formulas, and creating a column chart; read-only inspection reports missing cells, duplicate data rows, formula-error values and formula counts. Plans warn that formulas referencing cells outside a copied selection may need review on the results worksheet.
- Added an approval-first Copilot tab. It binds the plan to the current instruction, worksheet and data fingerprint, and separately fingerprints the exact plan shown for approval. It re-builds and verifies that plan at execution; enforces authentication and the configurable tier again; runs the existing deterministic Copilot orchestrator against a copy; checks source preservation; and exports a separate analysis workbook plus evidence ZIP.
- Kept Shoir-IE's fixed 96-module subscription inventory intact; Excel Intelligence is a separately governed Workbench Data capability with its own server-side entitlement policy. Added regression tests for navigation, routing, tier policy, one-use Copilot approval/replay protection, approval evidence export, source preservation, OOXML fidelity metadata and formula-injection protection in CSV evidence exports, plus the add-in's local-only data boundary.
- Added [EXCEL_INTELLIGENCE_CAPABILITY_MATRIX.md](EXCEL_INTELLIGENCE_CAPABILITY_MATRIX.md) to state supported/limited/unavailable behavior for the workbook structures named in the release specification.

## Not yet complete — Stage 1 remains open

This change does **not** establish that the full Excel Intelligence specification has passed Stage 1. The following items remain blocked or unverified:

- No authenticated Shoir-IE workbook-data transfer API is deployed. The new staging-source `session_entitlement` action is read-only account/entitlement verification only; it does not accept, store, or process workbook contents.
- The Office add-in manifest still contains `YOUR-SHOIR-IE-HOST` placeholders and has not been hosted/sideloaded in the staging Excel desktop or web clients. The referenced icon asset is also not present in the repository, and no verified staging hostname/static-host configuration is available in this change; therefore no installable manifest or add-in deployment is claimed.
- No task-pane Shoir-IE sign-in or validated token exchange exists. The existing browser `remote_session_token` is a broad, long-lived workspace session and must not be copied into Excel. A future bridge must mint and validate a separate short-lived Excel-scoped token, bind it to the user and entitlement, and revoke/expire it independently.
- The current staging persistence Edge Function has a browser-origin allowlist and bounded JSON request parser (v11 baseline verified). This is not an Office add-in origin allowlist and does not enable workbook transfer. A workbook-data API still needs explicit approved Office origins, a dedicated short-lived add-in identity/token exchange, explicit user consent, per-user/tenant authorisation, rate limits, audit/retention controls, deletion rules and negative cross-user/tenant tests before any workbook transfer is activated.
- The current Copilot uses the existing deterministic intent classifier and analysis engine. External generative-model/LLM task authoring is not configured and is not claimed.
- The Office add-in can now create a results worksheet and apply the limited approved local operations listed above. It can prepare a separate compressed OOXML copy of the current workbook and expose a download link only when the active host reports the Office CompressedFile requirement set; it validates the complete slice length and caps exports at 100 MB. The host matrix has not been runtime-tested, so support on any particular Excel client and desktop/web parity are not claimed. The local add-in still does not create PivotTables or provide a dedicated add-in-to-Shoir-IE authenticated workflow. The selected source worksheet remains unchanged by the current write path.
- The in-app upload runtime cleans and profiles data but does not yet deliver every Stage 1 operation (formula generation, chart creation, and full preservation of all advanced workbook features).
- No authenticated browser test has proved the exact menu selection under each supported account/tier.
- No Office desktop/web compatibility acceptance has been run. In-app table previews are bounded to protect Streamlit rendering, normalize mixed/nested object cells and duplicate headers in a display-only copy, and fall back to text when the interactive table renderer raises an exception. Copilot evidence JSON previews are also capped and fall back to formatted text when the interactive JSON tree fails; oversized charts are not sent to the browser, and complete evidence remains downloadable. Large review registers are bounded before DataFrame creation. Regression tests cover these paths but do not replace hosted browser/Excel acceptance.

## Required staging configuration before enabling server transfer

The API host, identity/token validation, allowed origins, maximum payload limits, explicit data-transfer notice/consent, per-user/workspace checks, rate limits, audit events, retention policy, and cross-tenant denial tests must be implemented and deployed in staging before the add-in is allowed to upload workbook data.

## Acceptance status

- Workbench Data registration and route: **IMPLEMENTED_NEEDS_VALIDATION**
- Safe bounded/Arrow-compatible Streamlit Excel table rendering, bounded Copilot evidence JSON and Plotly chart-size/failure handling: **IMPLEMENTED_NEEDS_VALIDATION**
- Server-side tier gate: **IMPLEMENTED_NEEDS_VALIDATION**
- Live account/session revalidation before Copilot execution: **IMPLEMENTED_NEEDS_VALIDATION — STAGING EDGE FUNCTION ACTION NOT YET DEPLOYED**
- Local Office.js inspection, bounded 8 MB selection payload and metadata summary, and deterministic planner with stale-plan/double-submit protection: **IMPLEMENTED_NEEDS_VALIDATION**
- In-app Copilot one-use plan IDs, replay prevention and downloadable approval evidence: **IMPLEMENTED_NEEDS_VALIDATION**
- Expanded OOXML fidelity warnings and formula-safe CSV evidence export: **IMPLEMENTED_NEEDS_VALIDATION**
- Copy-first, approval-gated local operations (text trim, SUM/AVERAGE, column chart): **IMPLEMENTED_NEEDS_VALIDATION**
- Local separate workbook-copy preparation/download link on hosts reporting CompressedFile support (100 MB cap and full-slice validation): **IMPLEMENTED_NEEDS_VALIDATION**
- Full Stage 1 Excel Intelligence: **BLOCKED / NOT VERIFIED**
- Stages 2–4: **NOT STARTED**

No production deployment, production migration, live customer data mutation, or release-readiness claim is included.
