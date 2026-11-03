// Shoir-IE Excel Intelligence Office.js task pane.
//
// The add-in plans and executes a small, explicit allow-list of local Excel
// operations. Workbook contents are never uploaded to Shoir-IE or another AI
// service by this task pane. Any write creates a separate results worksheet
// and requires explicit user approval; the selected source worksheet is not edited.

Office.onReady((info) => {
  const inspectButton = document.getElementById("inspectSelection");
  const copyButton = document.getElementById("copySelection");
  const planButton = document.getElementById("buildPlan");
  const runButton = document.getElementById("runPlan");
  const approval = document.getElementById("approveWorkbookEdits");
  const approvalLabel = document.getElementById("approvalLabel");
  const instruction = document.getElementById("instruction");
  const status = document.getElementById("status");
  const preview = document.getElementById("preview");
  const planView = document.getElementById("planView");

  if (!info || info.host !== Office.HostType.Excel) {
    status.textContent = "Open this task pane inside Excel to inspect a workbook.";
    [inspectButton, copyButton, planButton, runButton, approval].forEach(control => {
      control.disabled = true;
    });
    return;
  }

  if (!window.ShoirExcelPlanner) {
    status.textContent = "The local task planner did not load. Reload the add-in and try again.";
    [inspectButton, copyButton, planButton, runButton, approval].forEach(control => {
      control.disabled = true;
    });
    return;
  }

  let latestPayload = null;
  let latestPlan = null;

  function showStatus(message) {
    status.textContent = message;
  }

  function setPlan(plan) {
    latestPlan = plan;
    planView.textContent = plan ? JSON.stringify(plan, null, 2) : "No task plan has been prepared.";
    const hasWriteActions = Boolean(plan && plan.requiresWriteApproval);
    approvalLabel.hidden = !hasWriteActions;
    approval.checked = false;
    runButton.disabled = !plan || !Array.isArray(plan.operations) || plan.operations.length === 0;
    runButton.textContent = hasWriteActions ? "Approve and create results worksheet" : "Run read-only inspection";
  }

  async function selectedRangePayload() {
    return Excel.run(async (context) => {
      const worksheets = context.workbook.worksheets;
      worksheets.load("items/name");
      const workbookProperties = context.workbook.properties;
      workbookProperties.load("title");

      const range = context.workbook.getSelectedRange();
      const worksheet = range.worksheet;
      worksheet.load("name");
      range.load(["address", "rowIndex", "columnIndex", "rowCount", "columnCount"]);
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
        sheetName: worksheet.name || "",
        selection: {
          address: range.address,
          rowIndex: range.rowIndex,
          columnIndex: range.columnIndex,
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
      showStatus("Reading the selected range locally…");
      latestPayload = await selectedRangePayload();
      preview.textContent = JSON.stringify(latestPayload, null, 2);
      showStatus(
        "Inspection complete. " +
        latestPayload.selection.rows + " row(s) × " +
        latestPayload.selection.columns + " column(s). No data was sent to a server."
      );
      return latestPayload;
    } catch (error) {
      latestPayload = null;
      preview.textContent = "No inspection result is available.";
      showStatus("Could not inspect the selection: " +
        (error && error.message ? error.message : "Unknown Excel error"));
      throw error;
    }
  }

  async function buildPlan() {
    try {
      showStatus("Inspecting the selected range and preparing a deterministic plan…");
      latestPayload = await selectedRangePayload();
      const plan = window.ShoirExcelPlanner.buildPlan(instruction.value, latestPayload);
      setPlan(plan);
      preview.textContent = JSON.stringify(latestPayload, null, 2);
      showStatus(
        plan.requiresWriteApproval
          ? "Plan ready. Review the operations and approve creation of a separate results worksheet."
          : "Read-only plan ready. No workbook changes are proposed."
      );
    } catch (error) {
      setPlan(null);
      showStatus("Could not prepare a plan: " +
        (error && error.message ? error.message : "Unknown Excel error"));
    }
  }

  function columnName(zeroBasedIndex) {
    let number = zeroBasedIndex + 1;
    let result = "";
    while (number > 0) {
      const remainder = (number - 1) % 26;
      result = String.fromCharCode(65 + remainder) + result;
      number = Math.floor((number - 1) / 26);
    }
    return result;
  }

  function uniqueResultsSheetName(existingNames) {
    const used = new Set(existingNames.map(name => String(name).toLocaleLowerCase()));
    const base = "Shoir-IE Results";
    if (!used.has(base.toLocaleLowerCase())) return base;
    for (let suffix = 2; suffix < 10000; suffix += 1) {
      const candidate = base + " (" + suffix + ")";
      if (!used.has(candidate.toLocaleLowerCase())) return candidate;
    }
    throw new Error("A unique Shoir-IE Results worksheet name could not be allocated.");
  }

  async function executePlan() {
    if (!latestPlan) throw new Error("Build and review a task plan first.");
    if (latestPlan.requiresWriteApproval && !approval.checked) {
      throw new Error("Explicit approval is required before creating or editing a results worksheet.");
    }

    showStatus(
      latestPlan.requiresWriteApproval
        ? "Rechecking the selected data and preparing a separate results worksheet…"
        : "Running read-only inspection…"
    );

    const result = await Excel.run(async (context) => {
      const range = context.workbook.getSelectedRange();
      const worksheet = range.worksheet;
      const workbookProperties = context.workbook.properties;
      const worksheets = context.workbook.worksheets;
      workbookProperties.load("title");
      worksheets.load("items/name");
      range.load(["address", "rowIndex", "columnIndex", "rowCount", "columnCount"]);
      worksheet.load("name");
      await context.sync();

      const cellCount = Number(range.rowCount) * Number(range.columnCount);
      if (!Number.isSafeInteger(cellCount) || cellCount < 1 || cellCount > 10000) {
        throw new Error("The selected range is outside the 10,000-cell safety limit.");
      }

      range.load(["values", "formulas", "numberFormat"]);
      await context.sync();

      const currentPayload = {
        workbookTitle: workbookProperties.title || "",
        worksheets: worksheets.items.map(sheet => sheet.name),
        sheetName: worksheet.name || "",
        selection: {
          address: range.address,
          rowIndex: range.rowIndex,
          columnIndex: range.columnIndex,
          rows: range.rowCount,
          columns: range.columnCount,
          values: range.values,
          formulas: range.formulas || [],
          numberFormats: range.numberFormat || []
        }
      };

      const currentPlan = window.ShoirExcelPlanner.buildPlan(instruction.value, currentPayload);
      if (currentPlan.dataFingerprint !== latestPlan.dataFingerprint ||
          JSON.stringify(currentPlan.operations) !== JSON.stringify(latestPlan.operations)) {
        throw new Error("The selected workbook data or instruction changed. Rebuild and review the plan.");
      }
      if (currentPlan.sheetName !== latestPlan.sheetName ||
          currentPlan.selectionAddress !== latestPlan.selectionAddress) {
        throw new Error("The active worksheet or selected range changed. Rebuild the plan.");
      }

      const operations = currentPlan.operations.filter(operation => operation.requiresWriteApproval);
      const allowedTypes = new Set([
        "copy_selection_to_results",
        "trim_text",
        "add_summary_formulas",
        "create_column_chart"
      ]);
      for (const operation of operations) {
        if (!allowedTypes.has(operation.type)) {
          throw new Error("The plan contains an operation that is not in the local execution allow-list.");
        }
      }

      if (range.rowIndex + range.rowCount > 1048576 ||
          range.columnIndex + range.columnCount > 16384) {
        throw new Error("The selected range is outside Excel worksheet bounds.");
      }

      const resultSheetName = operations.length
        ? uniqueResultsSheetName(worksheets.items.map(sheet => sheet.name))
        : null;
      let resultSheet = null;
      let outputRange = null;

      if (operations.length) {
        // Copy the selected region to a fresh sheet. The source worksheet is never
        // assigned to and remains unchanged by all following operations.
        resultSheet = worksheets.add(resultSheetName);
        outputRange = resultSheet.getRangeByIndexes(0, 0, range.rowCount, range.columnCount);
        outputRange.values = range.values;
        outputRange.numberFormat = range.numberFormat;

        const formulas = range.formulas || [];
        for (let rowIndex = 0; rowIndex < formulas.length; rowIndex += 1) {
          for (let columnIndex = 0; columnIndex < formulas[rowIndex].length; columnIndex += 1) {
            const formula = formulas[rowIndex][columnIndex];
            if (typeof formula === "string" && formula.startsWith("=")) {
              outputRange.getCell(rowIndex, columnIndex).formulas = [[formula]];
            }
          }
        }
      }

      const completed = [];
      const profile = currentPlan.profile;

      for (const operation of currentPlan.operations) {
        if (operation.type === "inspect") {
          completed.push({
            operation: operation.title,
            status: "Completed",
            rows: profile.rows,
            columns: profile.columns,
            missingCells: profile.missingCells,
            duplicateRows: profile.duplicateRows,
            formulaErrors: profile.formulaErrors
          });
          continue;
        }

        if (operation.type === "copy_selection_to_results") {
          completed.push({
            operation: operation.title,
            status: "Completed",
            destinationWorksheet: resultSheetName,
            sourceWorksheet: currentPayload.sheetName,
            sourceRange: currentPayload.selection.address
          });
          continue;
        }

        if (!outputRange || !resultSheet) {
          throw new Error("A results worksheet is required for the requested local edit.");
        }

        if (operation.type === "trim_text") {
          let changed = 0;
          const values = currentPayload.selection.values || [];
          const formulas = currentPayload.selection.formulas || [];
          for (let rowIndex = 0; rowIndex < values.length; rowIndex += 1) {
            for (let columnIndex = 0; columnIndex < values[rowIndex].length; columnIndex += 1) {
              const value = values[rowIndex][columnIndex];
              const formula = formulas[rowIndex] && formulas[rowIndex][columnIndex];
              if (typeof value === "string" &&
                  !(typeof formula === "string" && formula.startsWith("=")) &&
                  value !== value.trim()) {
                outputRange.getCell(rowIndex, columnIndex).values = [[value.trim()]];
                changed += 1;
              }
            }
          }
          completed.push({
            operation: operation.title,
            status: "Completed",
            destinationWorksheet: resultSheetName,
            cellsChanged: changed
          });
          continue;
        }

        if (operation.type === "add_summary_formulas") {
          const formulaRowIndex = range.rowCount;
          const target = resultSheet.getRangeByIndexes(
            formulaRowIndex, 0, 1, range.columnCount
          );
          const formulaRow = new Array(range.columnCount).fill("");
          formulaRow[0] = operation.aggregate === "average" ? "AVERAGE" : "TOTAL";
          target.values = [formulaRow];

          const firstDataRow = 2;
          const lastDataRow = range.rowCount;
          const formulasAdded = [];
          for (const columnIndex of operation.columnIndexes) {
            if (!Number.isInteger(columnIndex) || columnIndex <= 0 || columnIndex >= range.columnCount) {
              throw new Error("The formula plan contains an invalid column reference.");
            }
            const column = columnName(columnIndex);
            const functionName = operation.aggregate === "average" ? "AVERAGE" : "SUM";
            const formula = "=" + functionName + "(" + column + firstDataRow + ":" +
              column + lastDataRow + ")";
            target.getCell(0, columnIndex).formulas = [[formula]];
            formulasAdded.push({ column: column, formula: formula });
          }
          completed.push({
            operation: operation.title,
            status: "Completed",
            destinationWorksheet: resultSheetName,
            destinationRow: formulaRowIndex + 1,
            formulas: formulasAdded
          });
          continue;
        }

        if (operation.type === "create_column_chart") {
          const chart = resultSheet.charts.add(
            Excel.ChartType.columnClustered,
            outputRange,
            Excel.ChartSeriesBy.auto
          );
          chart.title.text = "Shoir-IE Excel Intelligence — " + resultSheetName;
          chart.title.visible = true;
          const chartTopRow = range.rowCount + 2;
          chart.setPosition(
            "A" + (chartTopRow + 1),
            "H" + (chartTopRow + 15)
          );
          completed.push({
            operation: operation.title,
            status: "Completed",
            destinationWorksheet: resultSheetName,
            chartType: "columnClustered",
            position: "A" + (chartTopRow + 1)
          });
          continue;
        }

        throw new Error("Unsupported operation encountered. No arbitrary code execution is available.");
      }

      await context.sync();
      return {
        status: "Completed",
        mode: operations.length ? "USER_APPROVED_RESULTS_SHEET" : "READ_ONLY",
        completedAt: new Date().toISOString(),
        workbookTitle: currentPayload.workbookTitle,
        sourceWorksheet: currentPayload.sheetName,
        sourceRange: currentPayload.selection.address,
        resultsWorksheet: resultSheetName,
        sourceWorksheetPreserved: true,
        completedOperations: completed,
        transferMode: "LOCAL_ONLY"
      };
    });

    latestPayload = null;
    setPlan(null);
    preview.textContent = JSON.stringify(result, null, 2);
    showStatus(
      result.mode === "READ_ONLY"
        ? "Read-only inspection completed. No workbook cells were changed and no data was transmitted."
        : "Approved operations completed on the new worksheet “" + result.resultsWorksheet +
          "”. The selected source worksheet remains unchanged. Save the workbook in Excel to keep the results."
    );
  }

  inspectButton.addEventListener("click", () => {
    inspect().catch(() => {});
  });

  copyButton.addEventListener("click", async () => {
    try {
      const payload = latestPayload || await inspect();
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
      showStatus("Selection copied to the clipboard. Nothing was transmitted to a server.");
    } catch (error) {
      showStatus("Could not copy the selection: " +
        (error && error.message ? error.message : "Clipboard access unavailable"));
    }
  });

  planButton.addEventListener("click", () => {
    buildPlan().catch(() => {});
  });

  runButton.addEventListener("click", () => {
    executePlan().catch(error => {
      showStatus("Execution stopped: " +
        (error && error.message ? error.message : "Unknown Excel error"));
    });
  });
});
