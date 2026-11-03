(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.ShoirExcelPlanner = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const MAX_CELLS = 10000;
  const ERROR_VALUES = new Set(["#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!"]);

  function requireSelection(payload) {
    const selection = payload && payload.selection;
    if (!selection || !Array.isArray(selection.values) || !Array.isArray(selection.formulas)) {
      throw new TypeError("Inspect a valid Excel range before building a task plan.");
    }
    const rowCount = Number(selection.rows);
    const columnCount = Number(selection.columns);
    if (!Number.isSafeInteger(rowCount) || !Number.isSafeInteger(columnCount) ||
        rowCount < 1 || columnCount < 1 || rowCount * columnCount > MAX_CELLS) {
      throw new RangeError("Select a range containing between 1 and 10,000 cells.");
    }
    if (selection.values.length !== rowCount || selection.formulas.length !== rowCount ||
        selection.values.some(row => !Array.isArray(row) || row.length !== columnCount) ||
        selection.formulas.some(row => !Array.isArray(row) || row.length !== columnCount)) {
      throw new TypeError("The selected range dimensions do not match the inspected values.");
    }
    return selection;
  }

  function fingerprint(payload) {
    const selection = requireSelection(payload);
    const serialized = JSON.stringify({
      workbookTitle: String(payload.workbookTitle || ""),
      sheetName: String(payload.sheetName || ""),
      worksheets: Array.isArray(payload.worksheets) ? payload.worksheets : [],
      address: String(selection.address || ""),
      rows: selection.rows,
      columns: selection.columns,
      values: selection.values,
      formulas: selection.formulas,
      numberFormats: selection.numberFormats || []
    });

    // Compact, deterministic client-side change detector. This is not a
    // cryptographic digest, authentication token, or authorization control.
    let hashA = 0x811c9dc5;
    let hashB = 0x9e3779b9;
    for (let index = 0; index < serialized.length; index += 1) {
      const code = serialized.charCodeAt(index);
      hashA = Math.imul(hashA ^ code, 0x01000193);
      hashB = Math.imul(hashB ^ (code + index), 0x85ebca6b);
    }
    return "LOCAL-" +
      (hashA >>> 0).toString(16).padStart(8, "0") +
      (hashB >>> 0).toString(16).padStart(8, "0");
  }

  function numericColumnIndexes(selection) {
    const indexes = [];
    for (let column = 0; column < Number(selection.columns); column += 1) {
      // Office.js values contain the calculated cell result. Do not classify a
      // formula returning text/error as numeric merely because a formula exists.
      const data = selection.values.slice(1).map(row => row[column]);
      const hasNumericValue = data.some(value => typeof value === "number" && Number.isFinite(value));
      if (hasNumericValue) indexes.push(column);
    }
    return indexes;
  }

  function inspectSelection(payload) {
    const selection = requireSelection(payload);
    const values = selection.values;
    const rowCount = Number(selection.rows);
    const columnCount = Number(selection.columns);
    let missingCells = 0;
    let formulaErrors = 0;
    let formulaCells = 0;
    let textCells = 0;
    let unsafeTrimCells = 0;

    for (let row = 0; row < rowCount; row += 1) {
      for (let column = 0; column < columnCount; column += 1) {
        const value = values[row][column];
        const formula = selection.formulas[row][column];
        if (typeof formula === "string" && formula.startsWith("=")) formulaCells += 1;
        if (value === null || value === undefined || value === "") missingCells += 1;
        if (typeof value === "string" && ERROR_VALUES.has(value.toUpperCase())) formulaErrors += 1;
        if (typeof value === "string" && value.length > 0 &&
            !(typeof formula === "string" && formula.startsWith("="))) {
          textCells += 1;
          if (value !== value.trim() && /^[=+\-@]/.test(value.trim())) unsafeTrimCells += 1;
        }
      }
    }

    const seen = new Set();
    let duplicateRows = 0;
    values.slice(1).forEach(row => {
      const key = JSON.stringify(row);
      if (seen.has(key)) duplicateRows += 1;
      else seen.add(key);
    });

    const header = values[0].map((value, index) =>
      String(value === null || value === undefined || value === "" ? "Column " + (index + 1) : value)
    );
    return {
      assumption: "The first selected row is treated as the header row for planning.",
      rows: Math.max(0, rowCount - 1),
      columns: columnCount,
      missingCells,
      duplicateRows,
      formulaErrors,
      formulaCells,
      textCells,
      unsafeTrimCells,
      numericColumns: numericColumnIndexes(selection).map(index => ({
        index,
        header: header[index]
      })),
      headers: header
    };
  }

  function buildPlan(prompt, payload) {
    const instruction = String(prompt || "").trim();
    if (!instruction) throw new TypeError("Enter an Excel task before building a plan.");

    const selection = requireSelection(payload);
    const profile = inspectSelection(payload);
    const normalized = instruction.toLowerCase();
    const operations = [{
      id: "inspect_selection",
      type: "inspect",
      title: "Inspect the selected range",
      description: "Calculate a local data-quality summary without changing workbook cells.",
      requiresWriteApproval: false
    }];
    const warnings = [];
    const numericIndexes = profile.numericColumns.map(column => column.index);
    if (profile.formulaCells > 0) {
      warnings.push(
        profile.formulaCells + " formula cell(s) were found. Excel will copy formulas with native relative-reference adjustment; " +
        "references outside the selected range may not resolve to the same cells on the results worksheet. Review formula results before relying on them."
      );
    }

    if (/\b(trim|whitespace|extra spaces|clean text|standardi[sz]e whitespace)\b/.test(normalized)) {
      if (profile.textCells > 0) {
        operations.push({
          id: "trim_text",
          type: "trim_text",
          title: "Trim leading and trailing spaces",
          description: "Trim text constants in the selected range. Formula cells are left unchanged.",
          requiresWriteApproval: true
        });
      } else {
        warnings.push("No text constants were found to trim in the selected range.");
      }
      if (profile.unsafeTrimCells > 0) {
        warnings.push(
          profile.unsafeTrimCells + " text cell(s) would start with an Excel formula marker after trimming. " +
          "Those values will be left unchanged to prevent formula injection."
        );
      }
    }

    if (/\b(total|sum|subtotal|average|avg|mean)\b/.test(normalized)) {
      const aggregate = /\b(average|avg|mean)\b/.test(normalized) ? "average" : "sum";
      const targetTerms = ["cost", "profit", "revenue", "sales", "quantity", "demand", "output", "throughput"];
      const requestedTerms = targetTerms.filter(term => normalized.includes(term));
      let targetIndexes = numericIndexes;
      if (requestedTerms.length) {
        targetIndexes = numericIndexes.filter(index =>
          requestedTerms.some(term => profile.headers[index].toLowerCase().includes(term))
        );
        if (!targetIndexes.length) {
          warnings.push(
            "No numeric column header matched the requested measure (" +
            requestedTerms.join(", ") + "). No formula was added."
          );
        }
      }
      if (selection.rows < 2) {
        warnings.push("A header row and at least one data row are required to add a summary formula.");
      } else if (!targetIndexes.filter(index => index !== 0).length) {
        warnings.push("No eligible numeric measure column was found after reserving the first column for the TOTAL label.");
      } else if (!requestedTerms.length || targetIndexes.length) {
        operations.push({
          id: "add_summary_formulas",
          type: "add_summary_formulas",
          aggregate,
          columnIndexes: targetIndexes.filter(index => index !== 0),
          title: aggregate === "average" ? "Add AVERAGE formulas" : "Add SUM formulas",
          description: "Write formulas in the first blank row below the copied range on the new results worksheet.",
          requiresWriteApproval: true
        });
      }
    }

    if (/\b(chart|graph|visuali[sz]e|dashboard)\b/.test(normalized)) {
      if (selection.rows >= 2 && selection.columns >= 2 && numericIndexes.length > 0) {
        operations.push({
          id: "create_column_chart",
          type: "create_column_chart",
          title: "Create a column chart",
          description: "Create a chart from the copied range on the new results worksheet.",
          requiresWriteApproval: true
        });
      } else {
        warnings.push("A chart needs a header row, at least one data row, and at least one numeric column.");
      }
    }

    if (/\b(remove duplicates|delete|clear|overwrite|pivot(table)?|macro|vba|solver|optim(ize|ization)|forecast|predict)\b/.test(normalized)) {
      warnings.push(
        "The request also contains an operation that this local add-in does not support. " +
        "No deletion, PivotTable, macro, solver, forecasting or prediction action will be executed."
      );
    }

    if (operations.length > 1) {
      operations.splice(1, 0, {
        id: "copy_selection_to_results",
        type: "copy_selection_to_results",
        title: "Create a separate results worksheet",
        description: "Copy the selected range to a new Shoir-IE Results worksheet. The source worksheet remains unchanged.",
        requiresWriteApproval: true
      });
    }

    if (operations.length === 1) {
      warnings.push(
        "No supported write operation was detected. The plan can still run a read-only inspection. " +
        "Supported local edits: copy to a results worksheet, trim text, add SUM/AVERAGE formulas, and create a column chart."
      );
    }

    return {
      instruction,
      workbookTitle: String(payload.workbookTitle || ""),
      sheetName: String(payload.sheetName || ""),
      selectionAddress: String(selection.address || ""),
      dataFingerprint: fingerprint(payload),
      profile,
      operations,
      warnings,
      requiresWriteApproval: operations.some(operation => operation.requiresWriteApproval),
      planner: "Shoir-IE local deterministic operation planner",
      externalModelUsed: false
    };
  }

  return {
    MAX_CELLS,
    buildPlan,
    fingerprint,
    inspectSelection,
    numericColumnIndexes,
    requireSelection
  };
});
