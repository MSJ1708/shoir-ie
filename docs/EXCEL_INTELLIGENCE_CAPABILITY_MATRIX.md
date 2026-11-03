# Excel Intelligence — Workbook Capability Matrix

**Scope:** Shoir-IE's in-app workbook ingestion/export engine and the separate local-only Office.js task pane.
**Matrix status:** Code-audited on the feature branch. This is not a claim of hosted staging acceptance or Microsoft Excel client certification.

## Status definitions

- **Fully supported and tested** — the named behavior is covered by an automated test and the implementation supports it end-to-end within the stated scope.
- **Supported with limitations** — a bounded subset is implemented, or the source feature is detected but not faithfully preserved.
- **Not yet supported** — no accepted implementation/test exists for the capability.
- **Unsupported by design** — the feature is deliberately rejected or not executed for safety.

## Workbook capability matrix

| Capability | Status | Current behavior and user-visible limitation |
|---|---|---|
| Multiple worksheets | Fully supported and tested | XLSX/XLSM sheet values are imported separately, selectable, profiled and represented as separate CLEAN/RAW data sheets in the generated workbook. Original worksheet layout is not reproduced. |
| Formulas | Supported with limitations | OOXML formula cells are counted during package inspection. An explicit, hash-bound formula scan can archive formula text as inert evidence (bounded to 2,000,000 scanned cells and 10,000 inventory rows). Formulas are not recalculated by Shoir-IE and are not restored as executable formulas in the in-app cleaned workbook. |
| Formula references / dependency graph | Not yet supported | No formula dependency graph, external reference resolution or formula translation is performed. Formula references can change meaning when data is copied elsewhere; the task pane warns about possible out-of-selection references. |
| Cell formatting / number formats | Supported with limitations | Source styles are detected when a non-default style is used and trigger the fidelity acknowledgement. The governed output applies a new Shoir-IE presentation style; source colors, fonts, borders, number formats and layout are not guaranteed to be retained. |
| Charts | Supported with limitations | Source charts are detected and require acknowledgement. The in-app output can generate new charts from suitable numeric data; original chart definitions, layouts and references are not preserved. Office.js chart creation exists in the local task pane but has not passed live Excel-host acceptance. |
| Named ranges | Supported with limitations | Defined names are detected and trigger the fidelity acknowledgement. They are not mapped or recreated in the governed output. |
| Excel tables | Supported with limitations | Source table parts are detected and trigger the fidelity acknowledgement. The generated output builds new clean-data tables; original table names, structured references, styles and relationships are not guaranteed to survive. |
| PivotTables / pivot caches | Supported with limitations | Pivot structures are detected and trigger the fidelity acknowledgement. Pivot caches and interactive PivotTable behavior are not preserved or refreshed. |
| Filters / AutoFilter | Supported with limitations | Source AutoFilter metadata is detected and triggers acknowledgement. The output may add a basic filter to a CLEAN data table; original filter criteria and view state are not retained. |
| Data validation | Supported with limitations | Validation metadata is detected and triggers acknowledgement. Rules, dropdown sources and input messages are not reproduced in the data-focused output. |
| Conditional formatting | Supported with limitations | Conditional-formatting metadata is detected and triggers acknowledgement. Rules and visual behavior are not reproduced; the output uses new, documented formatting. |
| Merged cells | Supported with limitations | Merged-cell ranges are detected and trigger acknowledgement. The governed tabular output does not reconstruct merged layout. |
| Hidden rows | Supported with limitations | Hidden-row metadata is detected and triggers acknowledgement. Hidden state is not retained in the cleaned data view. |
| Hidden columns | Supported with limitations | Hidden-column metadata is detected and triggers acknowledgement. Hidden state is not retained in the cleaned data view. |
| External links | Supported with limitations | External-link parts are detected and trigger acknowledgement. Links are not followed, refreshed or recreated. |
| Macros / VBA | Supported with limitations | VBA presence is detected and triggers acknowledgement. Macros are never executed and are not included in the governed XLSX output; macro-enabled workbook fidelity is not promised. |
| Encrypted / password-protected workbooks | Unsupported by design | Password entry/decryption is not implemented. Encrypted or non-readable packages are rejected; users must provide an authorised, unencrypted copy. |
| Large workbooks | Supported with limitations | Uploads are limited to 75 MB; OOXML expansion is bounded (512 MB total, 256 MB per member, 10,000 members and a 500:1 member compression ratio). Formula inspection, previews, JSON and chart rendering have separate limits. Files outside the bounds are rejected or have the relevant optional inspection skipped. |
| Compressed OOXML export in Office.js | Not yet supported | The task pane feature-detects the Office CompressedFile requirement and caps a local download at 100 MB. Desktop/web host installation and export compatibility have not been accepted in live client tests. |
| In-app generated XLSX export | Fully supported and tested | Shoir-IE creates a new XLSX using XlsxWriter with formula/URL string auto-conversion disabled and writes untrusted cell text as strings. This is a data-focused output, not a bit-for-bit copy of the source workbook. |
| CSV evidence exports | Supported with limitations | Exported CSV text is formula-escaped in the evidence package. This deliberately prefixes formula-like text with an apostrophe; it does not alter the original in-memory source DataFrame. |

## Safety and provenance notes

1. The uploaded source is not overwritten. Cleaning and analysis operate on separate in-memory tables and generated output files.
2. The generated XLSX and evidence ZIP are data-focused derivatives. The evidence ZIP contains reconstructed raw/clean table values and provenance metadata; it is **not** a byte-for-byte archive of the uploaded OOXML package.
3. Before an export that contains detected fidelity risks, the user must acknowledge the displayed warning. The list of detected features is not proof that every possible Excel extension has been recognized.
4. Formula inventory records formula text as inert evidence. It does not calculate formulas, evaluate macros, resolve external links or guarantee cached values are current.
5. The Office.js task pane runs locally and does not upload workbook data. Its code is not the same thing as a hosted, centrally authenticated Shoir-IE add-in deployment.

## Acceptance still required

- Execute the fidelity scanner tests after the latest feature-branch changes.
- Verify actual in-app upload, cleaning, analysis, exports and entitlement behavior on the deployed staging application.
- Configure a verified HTTPS add-in hosting origin, serve all task-pane assets and icon, generate a manifest with real URLs, and validate its installation.
- Install and exercise the add-in in supported Excel desktop and Excel for the web clients before claiming compatibility.
- Do not enable remote workbook transfer; there is no accepted dedicated add-in token/API/CORS/tenant-isolation security bridge in this release.
