# Shoir-IE Excel Intelligence — Office.js task pane

This is the Microsoft Office JavaScript (Office.js) task-pane client for Shoir-IE Excel Intelligence. It is a real add-in scaffold, not an imitation of Excel embedded in a web page.

## Implemented local workflow

1. Open the add-in task pane in Excel.
2. Select a range containing no more than 10,000 cells.
3. Inspect the selected range locally. The profile reports missing cells, duplicate data rows, formula-error values, text cells and numeric columns.
4. Enter a natural-language instruction and build a deterministic, reviewable task plan.
5. Run read-only inspection without changing workbook cells, or explicitly approve creation of a separate results worksheet.
6. In Excel desktop, prepare a separate copy of the current workbook containing the results worksheet, then select the download link that appears.

The first selected row is treated as the header row for planning. This assumption appears in the plan. If formulas are present, the plan warns that formulas are copied with Excel's relative-reference behavior and may depend on cells outside the selected range; users must review those formula results on the results worksheet.

The current local operation allow-list is intentionally small:

- **Copy selection to results:** create a uniquely named Shoir-IE Results worksheet and copy the selected values, formulas and number formats. The selected source worksheet is not written to.
- **Trim text:** trim leading/trailing whitespace in text constants on the new results worksheet. Cells containing formulas are left unchanged, and text that would become formula-like after trimming is skipped and counted to prevent formula injection.
- **SUM / AVERAGE formulas:** add a summary row below the copied range on the results worksheet. The current first column is reserved for the TOTAL/AVERAGE label.
- **Column chart:** create a column chart from the copied range and position it below the selection.

Unsupported requests, including deletion/removal of duplicates, PivotTables, macros/VBA, solver/optimization, forecasting and prediction, are warned about and not executed by this local add-in. Workbook text is treated only as data; it is never interpreted as instructions or code.

## Approval and workbook preservation

Read-only inspection is the default and does not modify workbook cells. Every operation that writes to the workbook is displayed before execution and requires a separate approval checkbox.

Approved operations add a new worksheet in the active workbook. They do not modify the selected source worksheet. If a results sheet with the default name already exists, the add-in creates a new uniquely named results sheet instead of overwriting an existing sheet.

**Save a backup before approving edits.** The add-in adds a worksheet to the active workbook; the selected source worksheet remains unchanged. On Excel desktop hosts that support the Office CompressedFile requirement set, the add-in prepares a separate OOXML copy of the current workbook and exposes a download link for an explicit user click. The download is capped at 100 MB, verifies that all file slices were received, and preserves the current .xlsx or .xlsm extension. The source workbook in the Excel session remains open and is not replaced by the downloaded copy.

The manifest requests ReadWriteDocument because approved operations create and write to a results worksheet. Excel's normal add-in permission consent applies. The code still restricts edits to its explicit operation allow-list.

## Data transfer boundary

The task pane is LOCAL_ONLY. It does not upload workbook contents, send them to a configurable host, or call an external AI provider. Its planner is deterministic rule-based code, not an LLM. The compact local change fingerprint is used only to invalidate a stale plan; it is not a cryptographic digest, authentication token, or authorization control. The displayed plan does not duplicate the selected cell values.

A deployed authenticated Shoir-IE workbook API and a separate short-lived add-in identity/token exchange do not currently exist. The browser remote_session_token must not be copied into the add-in. Do not enable workbook transfer until user authentication, server-side tier/workspace checks, explicit data-transfer consent, origin/request bounds, audit/retention policy and cross-tenant denial tests are implemented.

## Manifest hosting and validation

manifest.xml intentionally retains YOUR-SHOIR-IE-HOST placeholders. Replace them only with an approved HTTPS staging host after the task-pane assets are actually deployed there. Do not submit the placeholder manifest to users or represent the add-in as hosted or ready for sideloading.

The repository CI validates manifest XML, JavaScript syntax and deterministic planner unit tests. That does not prove Excel desktop/web runtime compatibility. Microsoft documents that compressed workbook export is supported in Excel desktop for Windows/Mac but not Excel for the web. The download control is feature-detected and disabled where the host does not support it. Sideloading, Office desktop/web acceptance and authenticated server transfer remain unimplemented or unverified.

## Remaining Stage 1 work

- Host the task-pane assets and replace manifest placeholders on staging.
- Sideload and test on the supported Excel desktop and web clients.
- Establish a dedicated, short-lived Shoir-IE add-in authentication flow.
- Implement and deploy an authenticated workbook API only after security review.
- Validate compressed workbook-copy downloads on supported Excel desktop hosts and verify that the original source worksheet is preserved.
- Document the Excel for the web export limitation and provide a separate supported web export strategy before claiming parity.
- Expand the controlled operation registry and add acceptance tests for every added operation.
- Complete end-to-end testing with dedicated synthetic accounts only.

The in-app Workbench route separately reuses Shoir-IE's safe Excel processing engine and can generate separate analysis workbooks/evidence exports. This does not imply that the Office add-in can currently upload workbooks or generate a separate output file.
