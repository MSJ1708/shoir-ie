# Shoir-IE adoption layer

The adoption layer is designed to reduce the amount of platform-specific knowledge a new engineer needs before producing useful work.

## Product layers

1. **Industrial Workbook** — editable multi-sheet workbook surface with undo/redo, Excel import/export, formulas, units, validation and saved workbooks.
2. **Excel interoperability** — preserves the existing \`shoir_upgrade.py\` import/export path and adds an Office.js bridge scaffold under \`excel_addin/\`.
3. **Industrial Formula Engine** — safe AST-based formulas, references, cross-sheet references, selected functions, circular-reference detection and formula audit.
4. **Industrial Query** — repeatable selection, rename, filter, cleaning, calculation, grouping and sorting steps.
5. **Instant Analyze** — first-use profile, health checks, recommendations and a generated analytical view.
6. **Template Marketplace** — built-in industrial templates plus a workspace-scoped persistent template library.
7. **Copilot direct editing** — transparent deterministic edits for common workbook transformations; analytical Copilot actions still use the existing governed orchestration/approval path.
8. **Semantic / ontology layer** — reuses the Digital Thread canonical vocabulary instead of creating a parallel ontology.
9. **Analytical runtime** — interactive/vectorized/large-table profiles plus chunked CSV profiling and query execution primitives.
10. **Developer SDK** — workbook extension contract integrated with the existing plugin registry.
11. **Product shell** — responsive workbook UI for browser use with keyboard-friendly controls and a documented path for desktop/mobile packaging.
12. **Education/community** — in-product Learn & Extend guidance and repository-based extension/documentation workflow.

## Trust boundary

No feature in this layer invents connectivity, external data, production readiness or performance claims. The Excel add-in is explicitly a bridge scaffold until a deployed Shoir-IE API host is configured. High-performance execution is currently an in-memory/vectorized/chunked foundation, not a distributed compute cluster.
