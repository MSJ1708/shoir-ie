// Shoir-IE Excel Intelligence Office.js task pane.
//
// This add-in intentionally performs local workbook inspection only. It does
// not POST workbook contents to an arbitrary host. A server transfer path must
// not be enabled until an authenticated Shoir-IE API and consent flow exist.

Office.onReady((info) => {
  const inspectButton = document.getElementById("inspectSelection");
  const copyButton = document.getElementById("copySelection");
  const status = document.getElementById("status");
  const preview = document.getElementById("preview");

  if (!info || info.host !== Office.HostType.Excel) {
    status.textContent = "Open this task pane inside Excel to inspect a workbook.";
    inspectButton.disabled = true;
    copyButton.disabled = true;
    return;
  }

  let latestPayload = null;

  async function selectedRangePayload() {
    return Excel.run(async (context) => {
      const worksheets = context.workbook.worksheets;
      worksheets.load("items/name");
      const workbookProperties = context.workbook.properties;
      workbookProperties.load("title");

      const range = context.workbook.getSelectedRange();
      range.load(["address", "rowCount", "columnCount"]);
      await context.sync();

      const cellCount = Number(range.rowCount) * Number(range.columnCount);
      if (!Number.isSafeInteger(cellCount) || cellCount < 1 || cellCount > 10000) {
        throw new Error("Select a range containing between 1 and 10,000 cells.");
      }

      range.load(["values", "formulas", "numberFormat"]);
      await context.sync();

      const formulas = range.formulas || [];
      const formulaCellCount = formulas.reduce(
        (count, row) => count + row.filter(
          (value) => typeof value === "string" && value.startsWith("=")
        ).length,
        0
      );

      return {
        source: "Excel selection",
        capturedAt: new Date().toISOString(),
        workbookTitle: workbookProperties.title || "",
        worksheets: worksheets.items.map((sheet) => sheet.name),
        selection: {
          address: range.address,
          rows: range.rowCount,
          columns: range.columnCount,
          values: range.values,
          formulas,
          formulaCellCount,
          numberFormats: range.numberFormat
        },
        transferMode: "LOCAL_ONLY"
      };
    });
  }

  async function inspect() {
    try {
      status.textContent = "Reading the selected range locally…";
      latestPayload = await selectedRangePayload();
      preview.textContent = JSON.stringify(latestPayload, null, 2);
      status.textContent =
        "Inspection complete. " +
        latestPayload.selection.rows + " row(s) × " +
        latestPayload.selection.columns + " column(s). No data was sent to a server.";
      return latestPayload;
    } catch (error) {
      latestPayload = null;
      preview.textContent = "No inspection result is available.";
      status.textContent = "Could not inspect the selection: " +
        (error && error.message ? error.message : "Unknown Excel error");
      throw error;
    }
  }

  inspectButton.addEventListener("click", () => {
    inspect().catch(() => {});
  });

  copyButton.addEventListener("click", async () => {
    try {
      const payload = latestPayload || await inspect();
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      status.textContent = "Selection copied to the clipboard. Nothing was transmitted to a server.";
    } catch (error) {
      status.textContent = "Could not copy the selection: " +
        (error && error.message ? error.message : "Clipboard access unavailable");
    }
  });
});
