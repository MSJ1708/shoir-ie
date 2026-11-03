# Shoir-IE Excel Intelligence — Office.js task pane

This directory contains a real Microsoft Office JavaScript (Office.js) task-pane scaffold.

## Current behavior

- Opens as an Excel task pane when the manifest is hosted and sideloaded in a supported Excel environment.
- Reads the workbook title, worksheet names and currently selected range through Office.js.
- Reads selected values, formula strings, formula-cell count and number formats.
- Limits a single selected range to 10,000 cells.
- Displays a local JSON preview and can copy that preview to the clipboard.
- Does not transmit workbook contents to a server.

## Deliberate security boundary

The earlier configurable-host POST bridge has been removed. The repository does not currently provide a deployed, authenticated `POST /api/workbook/import` service or an established add-in identity/token validation flow. Sending workbook data to an arbitrary host without those controls would be unsafe.

The task pane currently **does not POST workbook contents to a server**. It therefore remains **LOCAL_ONLY** until all of the following are implemented and tested:

1. A deployed HTTPS Shoir-IE workbook API.
2. Authentication that validates a real Shoir-IE user/session for every request.
3. Server-side subscription and workspace authorization.
4. CSRF/origin and request-size controls appropriate to the chosen authentication model.
5. Explicit user notice/consent before workbook data leaves Excel.
6. Tenant-isolation, audit, and negative authorization tests.

## Manifest hosting

`manifest.xml` intentionally retains `YOUR-SHOIR-IE-HOST` placeholders. Replace these only with an approved HTTPS **staging** host after the task-pane assets are actually deployed there. Do not submit the placeholder manifest to users or represent the add-in as production-ready.

## Not yet implemented

Natural-language AI execution, user sign-in inside the task pane, authenticated workbook upload, formula/chart mutation, workbook output generation from the add-in, and desktop/web compatibility acceptance are not verified. The in-app Workbench route reuses Shoir-IE's existing safe Excel processing engine; it does not make these Office add-in capabilities available by implication.
