# Production Bottleneck & Capacity Recovery Study

## Purpose

This study is a first connected production workflow in Shoir-IE. It validates production-event data, calculates line-level baseline metrics, estimates a user-defined downtime-recovery scenario, and exports the results with input/result hashes. It is designed to complement existing ERP/MES workflows; it does not require a production-system connection.

## Access and input

The module is listed under **Production** in Explore Modules and is available from the **Mid-Tier Pro** tier onward.

CSV import is optional. The module starts with clearly labeled synthetic demonstration data, and the user can edit the table directly. CSV uploads are limited to 10 MiB, 100,000 rows, and 100 columns; oversized files are rejected without replacing the current study. Imported CSVs must contain these columns:

| Column | Meaning | Unit / rule |
|---|---|---|
| `Line` | Production line or comparable group | Non-empty label |
| `PlannedMin` | Planned production time | Minutes; greater than zero |
| `DowntimeMin` | Downtime within the planned interval | Minutes; between zero and planned time |
| `IdealCycleSec` | Ideal cycle time for the corresponding output | Seconds per unit; greater than zero |
| `TotalCount` | Total output | Non-negative count |
| `GoodCount` | Good output | Non-negative count, no greater than total output |

Each row should describe one consistent line and reporting interval. If cycle time or product mix changes within an interval, split the data into separate rows where appropriate. The module reports invalid numeric values instead of silently converting them to zero.

## Calculation definitions

For each line, values are aggregated from its validated rows:

- Runtime (minutes) = Planned minutes − Downtime minutes.
- Availability (%) = Runtime / Planned minutes × 100.
- Performance (%) = Sum(Total count × Ideal cycle seconds) / (Runtime minutes × 60) × 100.
- Quality (%) = Good count / Total count × 100, when total output is greater than zero.
- OEE (%) = Availability × Performance × Quality / 10,000.
- Theoretical capacity (units) = Sum(Planned minutes × 60 / Ideal cycle seconds).
- Capacity at target OEE = Theoretical capacity × 0.85. The 85% is an explicitly labeled planning reference in this study, not a universal industry benchmark.

Performance is not silently capped at 100%. A result above 100% is a diagnostic that may indicate cycle-time unit errors, product-mix issues, or inaccurate source data. When total output is zero, quality and OEE are shown as unavailable rather than fabricated as zero.

## Downtime-recovery scenario

The user selects a downtime-reduction fraction from 0% to 100%. The calculation estimates additional good units using recovered downtime and the observed row-level performance and quality rates. The output is labeled **Simulated** and the exact fraction is recorded in the evidence manifest and result hash. If the user changes the fraction after running a study, the displayed results are invalidated and the study must be run again.

This is a what-if calculation, not a forecast, guarantee, or proof that the assumed downtime reduction is feasible. Actual outcomes depend on causes of downtime, staffing, material availability, product mix, setup constraints, demand, and other factors not represented by the calculation.

## Evidence and export

The Excel export contains baseline metrics, the simulated recovery scenario, a compact evidence manifest (including the exact scenario fraction), and the assumptions. The manifest records the formula version, source name/type, input SHA-256, result SHA-256, row/line counts, and result classifications. Untrusted imported strings are written as text rather than executable spreadsheet formulas or automatic hyperlinks.

Hashes support integrity checks and reproducibility comparisons. They do **not** establish that the source data is accurate, that a result has been independently verified, or that a simulated benefit was realized. No customer data is persisted by this calculation service.

## Current boundaries

- CSV input only in this workflow; Excel workbooks can be cleaned in Shoir-IE's existing Excel module and then exported to CSV.
- No live SAP, ERP, MES, PLC, or machine-control connection is implemented by this workflow.
- No optimization solver or discrete-event simulation is invoked. The recovery estimate is a bounded arithmetic scenario based on observed rates.
- No independent verification or realized financial savings are claimed.
- Browser-level rendering, hosted-app behavior, and complete repository CI must be verified separately from the calculation unit tests.
