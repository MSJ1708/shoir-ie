// Shoir-IE Excel Intelligence Office.js task pane.
//
// The add-in plans and executes a small, explicit allow-list of local Excel
// operations. Workbook contents are never uploaded to Shoir-IE or another AI
// service by this task pane. Workbook edits require separate user approval.

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
    planView.textContent = JSON.stringify(plan, null, 2);
    const hasWriteActions = Boolean(plan && plan.requiresWriteApproval);
    approvalLabel.hidden = !hasWriteActions;
    approval.checked = false;
    runButton.disabled = !plan || !Array.isArray(plan.operations) || plan.operations.length === 0;
    runButton.textContent = hasWriteActions ? "Approve and run local edits" : "Run read-only inspection";
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
      latestPlan = window.ShoirExcelPlanner.buildPlan(instruction.value, latestPayload);
      setPlan(latestPlan);
      preview.textContent = JSON.stringify(latestPayload, null, 2);
      showStatus(
        latestPlan.requiresWriteApproval
          ? "Plan ready. Review each operation; edits have not been made."
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

  async function executePlan() {
    if (!latestPlan) throw new Error("Build and review a task plan first.");
    if (latestPlan.requiresWriteApproval && !approval.checked) {
      throw new Error("Explicit workbook-edit approval is required.");
    }

    showStatus(
      latestPlan.requiresWriteApproval
        ? "Rechecking the selected data and preflighting approved local edits…"
        : "Running read-only inspection…"
    );

    const result = await Excel.run(async (context) => {
      const range = context.workbook.getSelectedRange();
      const worksheet = range.worksheet;
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
        workbookTitle: latestPayload ? latestPayload.workbookTitle : "",
        worksheets: latestPayload ? latestPayload.worksheets : [],
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
      const preflight = [];
      const maxRows = 1048576;

      // Preflight every destination before queuing any write operation.
      for (const operation of operations) {
        if (operation.type === "add_summary_formulas") {
          const targetRowIndex = range.rowIndex + range.rowCount;
          if (targetRowIndex >= maxRows) {
            throw new Error("There is no row below the selected range for summary formulas.");
          }
          const target = worksheet.getRangeByIndexes(
            targetRowIndex, range.columnIndex, 1, range.columnCount
          );
          target.load(["values", "formulas"]);
          preflight.push({ operation, target });
        } else if (operation.type === "create_column_chart") {
          const chartTopRow = range.rowIndex + range.rowCount + 1;
          if (chartTopRow + 15 >= maxRows || range.columnIndex + 7 >= 16384) {
            throw new Error("There is not enough worksheet space to position the requested chart.");
          }
          preflight.push({ operation });
        } else if (operation.type === "trim_text") {
          preflight.push({ operation });
        } else {
          throw new Error("The plan contains an operation that is not in the local execution allow-list.");
        }
      }

      if (preflight.some(item => item.target)) await context.sync();

      for (const item of preflight) {
        if (!item.target) continue;
        const occupied = item.target.values.some((row, rowIndex) =>
          row.some((value, columnIndex) => {
            const formula = item.target.formulas[rowIndex] && item.target.formulas[rowIndex][columnIndex];
            return (value !== null && value !== undefined && value !== "") ||
              (typeof formula === "string" && formula.startsWith("="));
          })
        );
        if (occupied) {
          throw new Error("The row directly below the selected range is not empty. No workbook edits were applied.");
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

        if (operation.type === "trim_text") {
          let changed = 0;
          const values = range.values || [];
          const formulas = range.formulas || [];
          for (let rowIndex = 0; rowIndex < values.length; rowIndex += 1) {
            for (let columnIndex = 0; columnIndex < values[rowIndex].length; columnIndex += 1) {
              const value = values[rowIndex][columnIndex];
              const formula = formulas[rowIndex] && formulas[rowIndex][columnIndex];
              if (typeof value === "string" &&
                  !(typeof formula === "string" && formula.startsWith("=")) &&
                  value !== value.trim()) {
                range.getCell(rowIndex, columnIndex).values = [[value.trim()]];
                changed += 1;
              }
            }
          }
          completed.push({
            operation: operation.title,
            status: "Completed",
            cellsChanged: changed
          });
          continue;
        }

        if (operation.type === "add_summary_formulas") {
          const targetRowIndex = range.rowIndex + range.rowCount;
          const target = worksheet.getRangeByIndexes(
            targetRowIndex, range.columnIndex, 1, range.columnCount
          );
          const formulaRow = new Array(range.columnCount).fill("");
          formulaRow[0] = operation.aggregate === "average" ? "AVERAGE" : "TOTAL";
          target.values = [formulaRow];

          const firstDataRow = range.rowIndex + 2;
          const lastDataRow = range.rowIndex + range.rowCount;
          const formulasAdded = [];
          for (const columnIndex of operation.columnIndexes) {
            if (!Number.isInteger(columnIndex) || columnIndex <= 0 || columnIndex >= range.columnCount) {
              throw new Error("The formula plan contains an invalid column reference.");
            }
            const column = columnName(range.columnIndex + columnIndex);
            const functionName = operation.aggregate === "average" ? "AVERAGE" : "SUM";
            const formula = "=" + functionName + "(" + column + firstDataRow + ":" +
              column + lastDataRow + ")";
            target.getCell(0, columnIndex).formulas = [[formula]];
            formulasAdded.push({ column: column, formula: formula });
          }
          completed.push({
            operation: operation.title,
            status: "Completed",
            destination: "Row " + (targetRowIndex + 1),
            formulas: formulasAdded
          });
          continue;
        }

        if (operation.type === "create_column_chart") {
          const chart = worksheet.charts.add(
            Excel.ChartType.columnClustered,
            range,
            Excel.ChartSeriesBy.auto
          );
          chart.title.text = "Shoir-IE Excel Intelligence — " + worksheet.name;
          chart.title.visible = true;
          const chartTopRow = range.rowIndex + range.rowCount + 1;
          chart.setPosition(
            columnName(range.columnIndex) + (chartTopRow + 1),
            columnName(range.columnIndex + 7) + (chartTopRow + 15)
          );
          completed.push({
            operation: operation.title,
            status: "Completed",
            chartType: "columnClustered",
            position: columnName(range.columnIndex) + (chartTopRow + 1)
          });
          continue;
        }

        throw new Error("Unsupported operation encountered. No arbitrary code execution is available.");
      }

      await context.sync();
      return {
        status: "Completed",
        mode: operations.length ? "USER_APPROVED_LOCAL_EDIT" : "READ_ONLY",
        completedAt: new Date().toISOString(),
        workbookTitle: currentPayload.workbookTitle,
        sheetName: currentPayload.sheetName,
        selectionAddress: currentPayload.selection.address,
        completedOperations: completed,
        transferMode: "LOCAL_ONLY"
      };
    });

    latestPayload = null;
    latestPlan = null;
    setPlan(null);
    planView.textContent = "The plan has been executed. Build a fresh plan before another task.";
    preview.textContent = JSON.stringify(result, null, 2);
    showStatus(
      result.mode === "READ_ONLY"
        ? "Read-only inspection completed. No workbook cells were changed and no data was transmitted."
        : "Approved local operations completed. The active workbook was modified; save or discard the workbook in Excel."
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
