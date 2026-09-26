# Shoir-IE Excel interoperability bridge

This directory contains the Office Add-in scaffold for the Industrial Workbook layer.

## What is implemented

The task pane can read the currently selected Excel range with Office.js, show a clear connection state, save a Shoir-IE API host per browser profile, copy the selection as JSON, and POST the selected range to:

`POST /api/workbook/import`

## Deployment boundary

The repository does **not** claim that the API endpoint above is already deployed. The add-in becomes a live two-way bridge only when a Shoir-IE deployment exposes that endpoint behind HTTPS and the host is entered in the task pane.

The manifest therefore uses `https://YOUR-SHOIR-IE-HOST/` placeholders rather than pretending there is a production host.

## Install

1. Host `taskpane.html` and `taskpane.js` on the same HTTPS origin.
2. Replace the placeholder SourceLocation and IconUrl values in `manifest.xml`.
3. Sideload the manifest into Excel using Microsoft's Office Add-ins flow.
4. Enter the deployed API host in the task pane.
5. Select an Excel range and send it to Shoir-IE.

The main Shoir-IE application remains the authoritative engineering workbook, formula, query, semantic, visualization and decision workflow.
