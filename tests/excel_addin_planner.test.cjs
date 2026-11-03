"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const planner = require("../excel_addin/planner.js");

function payload(values, formulas = null) {
  const rows = values.length;
  const columns = values[0].length;
  return {
    workbookTitle: "Factory data",
    sheetName: "Production",
    worksheets: ["Production", "Downtime"],
    selection: {
      address: "Production!A1:C4",
      rows,
      columns,
      values,
      formulas: formulas || values.map(row => row.map(() => null)),
      numberFormats: values.map(row => row.map(() => "General"))
    }
  };
}

test("builds an approval-gated plan for cleaning, totals and charts", () => {
  const source = payload([
    ["Line", "Operating Cost", "Output"],
    [" A ", 50, 100],
    ["B", 60, 120],
    ["C", 70, 110]
  ]);
  const plan = planner.buildPlan(
    "Trim whitespace, calculate total cost and create a chart",
    source
  );

  assert.equal(plan.externalModelUsed, false);
  assert.equal(plan.requiresWriteApproval, true);
  assert.deepEqual(
    plan.operations.map(operation => operation.type),
    ["inspect", "copy_selection_to_results", "trim_text", "add_summary_formulas", "create_column_chart"]
  );
  assert.deepEqual(plan.operations[3].columnIndexes, [1]);
  assert.equal(plan.profile.rows, 3);
  assert.equal(plan.profile.numericColumns.length, 2);
});

test("read-only inspection reports blanks, duplicate rows and formula errors", () => {
  const source = payload([
    ["ID", "Value"],
    ["A", 10],
    ["A", 10],
    ["B", "#DIV/0!"],
    ["C", ""]
  ]);
  const report = planner.inspectSelection(source);
  assert.equal(report.rows, 4);
  assert.equal(report.duplicateRows, 1);
  assert.equal(report.formulaErrors, 1);
  assert.ok(report.missingCells >= 1);
  const plan = planner.buildPlan("Identify missing values and duplicates", source);
  assert.equal(plan.requiresWriteApproval, false);
  assert.deepEqual(plan.operations.map(operation => operation.type), ["inspect"]);
});

test("rejects selections exceeding the documented 10,000-cell limit", () => {
  const values = Array.from({length: 101}, () => Array(100).fill(1));
  const source = payload(values);
  assert.throws(() => planner.buildPlan("Inspect this data", source), /10,000 cells/);
});

test("a change to the selected values invalidates the reviewed plan fingerprint", () => {
  const source = payload([["Line", "Cost"], ["A", 10]]);
  const changed = payload([["Line", "Cost"], ["A", 11]]);
  const plan = planner.buildPlan("Calculate total cost", source);
  assert.notEqual(plan.dataFingerprint, planner.fingerprint(changed));
});

test("unsupported destructive tasks are warned about and never become executable operations", () => {
  const source = payload([["Line", "Cost"], ["A", 10]]);
  const plan = planner.buildPlan("Remove duplicates and create a PivotTable", source);
  assert.equal(plan.operations.length, 1);
  assert.ok(plan.warnings.some(warning => warning.includes("does not support")));
});

test("text trimming flags values that would become executable formula-like input", () => {
  const source = payload([
    ["Reference", "Comment"],
    ["A-01", "  =HYPERLINK(\"https://invalid.example\",\"open\")"],
    ["A-02", "  ordinary text  "]
  ]);
  const profile = planner.inspectSelection(source);
  assert.equal(profile.unsafeTrimCells, 1);
  const plan = planner.buildPlan("Trim extra spaces", source);
  assert.ok(plan.warnings.some(warning => warning.includes("prevent formula injection")));
});

test("local plan fingerprint is compact and does not retain source cell content", () => {
  const source = payload([["Line", "Cost"], ["Confidential-Order-42", 1234]]);
  const plan = planner.buildPlan("Inspect this data", source);
  assert.match(plan.dataFingerprint, /^LOCAL-[0-9a-f]{16}$/);
  assert.equal(plan.dataFingerprint.includes("Confidential-Order-42"), false);
});

test("does not classify a text-returning formula as a numeric measure", () => {
  const source = payload(
    [["Line", "Status"], ["A", "Ready"]],
    [[null, null], [null, '=IF(A2="A","Ready","Other")']]
  );
  const profile = planner.inspectSelection(source);
  assert.deepEqual(profile.numericColumns, []);
  const plan = planner.buildPlan("Calculate total status", source);
  assert.equal(plan.operations.some(operation => operation.type === "add_summary_formulas"), false);
});
