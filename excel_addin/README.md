# Shoir-IE Excel Intelligence — Office.js task pane

This is the Microsoft Office JavaScript (Office.js) task-pane client for Shoir-IE Excel Intelligence. It is a real add-in scaffold, not an imitation of Excel embedded in a web page.

## Implemented local workflow

1. Open the add-in task pane in Excel.
2. Select a range containing no more than 10,000 cells.
3. Inspect the selected range locally. The profile reports missing cells, duplicate data rows, formula-error values, text cells, and numeric columns.
4. Enter a natural-language instruction and build a deterministic, reviewable task plan.
5. Run read-only inspection without changing workbook cells, or explicitly approve the proposed local edits.

The current local operation allow-list is intentionally small:

- **Trim text:** trim leading/trailing whitespace in text constants in the selected range. Cells containing formulas are not overwritten.
- **SUM / AVERAGE formulas:** add a summary row immediately below the selected range. Formula generation uses the selected range coordinates and detected numeric columns. If the destination row is occupied, execution stops before edits are queued.
- **Column chart:** create a column chart from the selected range and position it below the selection.

The first selected row is treated as the header row for local planning. The user-facing plan states this assumption. Unsupported requests, including deletion/removal of duplicates, PivotTables, macros/VBA, solver/optimization and prediction/forecasting, are not executed. Workbook text is treated only as data; it is never interpreted as instructions or code.

## Approval and workbook preservation

Read-only inspection is the default and does not modify workbook cells. Every write operation is displayed before execution and requires a separate approval checkbox. The add-in modifies the active workbook only after that approval.

**Save a backup or open a duplicate workbook before approving edits.** The add-in cannot verify that the user is working on a duplicate. The current task pane does not create or download a separate workbook copy.

The manifest requests `ReadWriteDocument` because approved operations write to the active workbook. This is broader than the former read-only scaffold and must be shown to the user through Excel's normal add-in permission consent. The code still restricts edits to its explicit operation allow-list.

## Data transfer boundary

The task pane is **LOCAL_ONLY**. It does not upload workbook contents, send them to a configurable host, or call an external AI provider. Its planner is deterministic rule-based code, not an LLM.

A deployed authenticated Shoir-IE workbook API and a separate short-lived add-in identity/token exchange do not currently exist. The browser `remote_session_token` must not be copied into the add-in. Do not enable workbook transfer until user authentication, server-side tier/workspace checks, explicit data-transfer consent, origin/request bounds, audit/retention policy and cross-tenant denial tests are implemented.

## Manifest hosting and validation

`manifest.xml` intentionally retains `YOUR-SHOIR-IE-HOST` placeholders. Replace them only with an approved HTTPS **staging** host after the task-pane assets are actually deployed there. Do not submit the placeholder manifest to users or represent the add-in as hosted or ready for sideloading.

The repository CI validates XML, JavaScript syntax and deterministic planner unit tests. That does not prove Excel desktop/web runtime compatibility. Sideloading, Office desktop/web acceptance, authenticated server transfer, and a generated separate workbook from the add-in remain unimplemented or unverified.

## Remaining Stage 1 work

- Host the task-pane assets and replace manifest placeholders on staging.
- Sideload and test on the supported Excel desktop and web clients.
- Establish a dedicated, short-lived Shoir-IE add-in authentication flow.
- Implement and deploy an authenticated workbook API only after security review.
- Add a separate output workbook workflow to the add-in, without silently modifying the source.
- Expand the controlled operation registry and add acceptance tests for each supported operation.
- Complete end-to-end testing with dedicated synthetic accounts only.

The in-app Workbench route separately reuses Shoir-IE's safe Excel processing engine and can generate separate analysis workbooks/evidence exports. This does not imply that the Office add-in can currently upload or generate a separate workbook.
