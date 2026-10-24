# Shoir-IE 100-tool integration report

**Work branch:** \`audit/shoir-100-tools-20261023\`  
**Scope:** two focused implementation tranches within the 100-tool target catalog  
**Status:** implementation extended; mandatory full verification remains open

## What this branch now contains

The existing application shell and Workbench layout are retained. The 100-tool directory remains a progressive-disclosure expander inside the existing Workbench rather than becoming 100 top-level navigation items. The target matrix remains the source of truth for target IDs, minimum target tiers, mapped legacy routes, evidence and known gaps.

Seventeen additional calculation-backed methods are now wired to the existing Workbench's focused-method runner, stable target IDs, account gate, tier gate, result rendering and existing workspace-save path:

| Tool ID | Workbench method | Method boundary |
|---|---|---|
| T024 | Production Line Balancer | Stable topological order and greedy sequential station packing; a feasible heuristic, not a global optimum proof |
| T025 | Bottleneck and Constraint Analyzer | User-entered process capacity compared with demand on a shared period basis; not causal proof |
| T027 | Value Stream Mapping Studio | First-pass queue/lead-time estimate from WIP, flow rate, cycle time, uptime, batch and changeover assumptions |
| T038 | FMEA Manager | Severity × Occurrence × Detection ranking, with high severity surfaced independently of RPN |
| T070 | Queuing and Service-System Analyzer | Stable single-server M/M/1 analytical model only |
| T082 | Industrial Costing and Variance Analyzer | Direct-material price, usage and total variance with reconciliation |
| T083 | Evidence-Based ROI Tracker | Baseline/post-change cost arithmetic; always requires human evidence verification |
| T043 | Preventive Maintenance Planner | Interval-based due dates and overdue flags; not a resource/downtime optimizer |
| T047 | Job Safety and Hazard Register | Severity × likelihood screen with distinct residual scores; requires qualified safety review |
| T054 | Material Requirements Planner | One-level BOM netting and lot multiple; no recursive BOM explosion |
| T084 | Engineering Project Portfolio Scorer | Explicit weighted, direction-aware normalization; weight sensitivity not yet included |
| T017 | Data Join and Merge Studio | Explicit join key/cardinality diagnostics and duplicate-key policy |
| T018 | Time-Series Data Processor | UTC timestamp normalization, gap/duplicate detection and optional numeric resampling |
| T019 | Synthetic Industrial Data Generator | Seeded, reproducible data clearly marked SYNTHETIC |
| T034 | Acceptance Sampling Planner | Single-sample binomial plan and stated producer/consumer risk probabilities |
| T076 | Process Mining Analyzer | Event-log variants, directly-follows transitions and case durations |
| T079 | Water and Waste Efficiency Analyzer | Per-process flow balance; totals only when periods/units are comparable |

The seventeen additional focused methods have deterministic input validation and structured outputs. The specialist calculation functions are in \`shoir_target_engines.py\`. The Workbench form/execution path is in \`pages/Industrial_Engineering_Workbench.py\`. Independent golden/boundary tests are in \`tests/test_shoir_target_engines.py\`. The central target registry and its execution/persistence metadata are in \`shoir_tool_registry.py\`.

## Numerical and safety contracts

- T024 checks unique task IDs, positive task durations, known predecessor IDs, precedence cycles and cycle-time feasibility. The result explicitly says it is a heuristic.
- T025 requires named unique process capacities and demand to use the same period, units and product mix.
- T027 exposes the WIP/flow-rate relation and the effect of uptime and changeover amortized over batch size; it calls the lead-time result an estimate.
- T038 validates integer 1–10 scores. Its risk bands are expressly conventions, not a universal FMEA standard. Severity 9–10 remains visible regardless of RPN.
- T070 rejects arrival rates that meet or exceed service capacity and discloses M/M/1's Poisson/exponential/single-server assumptions.
- T082 reconciles total variance to price variance plus usage variance; positive means adverse and negative means favorable under the documented convention.
- T083 does not self-certify savings: results always use \`REQUIRES_HUMAN_VERIFICATION\`; an evidence reference or verifier name alone is not proof.

These methods consume user-entered values; prefilled examples are synthetic/illustrative and do not represent plant measurements, measured savings or live connectors.

## Current catalog evidence snapshot

The matrix has 100 unique ordered IDs, T001–T100. Its present statuses are:

| Status | Count |
|---|---:|
| \`VERIFIED_WORKING\` | 0 |
| \`IMPLEMENTED_NEEDS_VALIDATION\` | 57 |
| \`FOUNDATION_ONLY\` | 41 |
| \`MISSING\` | 0 |
| \`EXTERNAL_CONFIGURATION_REQUIRED\` | 2 |
| \`BLOCKED\` | 0 |

A \`FOUNDATION_ONLY\` item is not a completed tool. Zero \`MISSING\` rows means the target capability is mapped in the catalog; it does **not** mean that 100 specialist workflows have been completed. No target is marked \`VERIFIED_WORKING\` on source-mapping or unit-test claims alone.

## Required verification before calling this tranche done

1. Run the repository's complete validation workflow against the final branch head; resolve every test, import, compile, or security-quality regression.
2. Run the focused engine tests added for the seventeen methods, together with existing engine and registry tests.
3. Complete authenticated browser tests for entitled and denied tiers, valid/invalid inputs, result refresh/staleness and persistence after reload/re-login.
4. Confirm all seventeen methods are accessible from the target directory and cannot be run as a guest or through an unauthorized target ID.
5. Validate actual export outputs and downstream workflow compatibility where the UI exposes exports.
6. Run the workbook-to-decision, facility-layout and persistence/isolation end-to-end workflows using synthetic fixtures and dedicated disposable test accounts.
7. Continue implementation of the remaining foundation-only capabilities rather than treating this tranche as proof that all 100 targets are complete.

## Release position

**Not a production/workforce-readiness approval.** This tranche adds deterministic methods and tests, but authenticated browser evidence, full test results on the final commit, broader tool coverage, deployment parity and relevant live production smoke checks remain release gates. Keep the 100-tool matrix and release claims aligned with the evidence actually produced by CI and authenticated tests.
