# Shoir-IE 100-Tool Implementation Matrix — source-audited baseline

**Registry:** `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv` is the authoritative, stable-ID registry and the source read by the grouped 100-Tool Engineering Hub. It contains exactly 100 target tools, IDs T001–T100, categorized into the 10 workbenches from the approved master prompt.

## Scope and evidence boundary

This report is a source-based gap assessment against the default-branch source reviewed before this changeset. It is not an authenticated browser sign-off. Every row keeps browser acceptance as **UNVERIFIED** until a plan-matched disposable account is used to execute the full tool flow. No item is marked `VERIFIED_WORKING` based on a catalog entry, unit tests, or source inspection alone.

The baseline catalogs reviewed before this branch contained 96 unique module names across `app.py` and `industrial_platform.PLATFORM_CATALOG`. This changeset adds `100-Tool Engineering Hub`, bringing the current module catalog and tier inventory to 97 names. Those module names are distinct from the 100 target capabilities in the tool-level matrix. The source contains concrete reusable helpers for workbook import/alignment, data quality, line balance, OEE, SPC, process capability, gauge R&R, DOE, regression/ANOVA, FMEA, Weibull, forecasting, finite scheduling, MRP, linear/robust/multi-objective optimization, queue simulation, scenarios, economics, exports, workspace roles and decision transitions. These are reusable foundations, not proof each target workflow satisfies every required acceptance criterion.

## Status meanings

- `VERIFIED_WORKING`: implementation and all applicable authenticated end-to-end checks passed for the tested revision.
- `IMPLEMENTED_NEEDS_VALIDATION`: concrete calculation/action exists, but one or more required golden fixtures, integration paths, authenticated browser checks, persistence, or exports remain incomplete.
- `FOUNDATION_ONLY`: related module, UI, generic helper, or partial method exists but the promised specialist behavior is incomplete.
- `MISSING`: no adequate dedicated implementation was identified in the reviewed module catalogs/helpers.
- `EXTERNAL_CONFIGURATION_REQUIRED`: relevant module/adapter surface exists, but a real authorized deployment, endpoint, credentials, and live staging contract have not been verified.
- `BLOCKED`: implementation/verification cannot proceed due to a documented external limitation. No row was placed here solely to hide missing implementation.

## Current gap distribution

- `VERIFIED_WORKING`: 0 tools
- `IMPLEMENTED_NEEDS_VALIDATION`: 48 tools
- `FOUNDATION_ONLY`: 42 tools
- `MISSING`: 8 tools
- `EXTERNAL_CONFIGURATION_REQUIRED`: 2 tools
- `BLOCKED`: 0 tools

## Implemented in this changeset

The grouped Workbench hub is available as a single Starter-level module in the existing navigation rather than as 100 new top-level items. It reads the canonical matrix and uses explicit per-tool target-tier checks. Unmapped names and unknown tier strings are denied by the shared availability/access policy, including Copilot capability metadata. The grouped Workbench hub now has deterministic calculators for T021 time study/standard time, T022 work sampling with Wilson confidence interval, T023 takt/capacity, T026 OEE, T032 process capability with Pp/Ppk separated from optional within-sigma Cp/Cpk, T034 single-sampling plan search against AQL/LTPD producer/consumer risks using a binomial approximation, T040 scrap/rework/inspection cost reconciliation, T042 MTBF/MTTR, T055 EOQ/reorder point, T078 user-factor carbon emissions, T081 conventional cash-flow NPV/IRR/simple payback, T084 normalized weighted portfolio scoring, and T085 a normal-approximation equal two-group sample-size planner. Tests cover their golden cases and key invalid boundaries. T065 is updated to reflect the existing persisted Facility Layout/SLP workflow and new flow-distance calculation with optional user-supplied handling cost rate. T076 is mapped to the existing process-mining implementation in the Industrial Operating System, where it remains Enterprise-routed and needs authenticated tests. T027, T030 and T079 are classified as FOUNDATION_ONLY: their related registries/workflows do not yet meet the full VSM, A3 action/evidence, or measured water/waste balance acceptance targets. These use user-entered values, show definitions/limitations, and do not claim plant connectivity or achieved savings. Their status stays `IMPLEMENTED_NEEDS_VALIDATION` until their dedicated automated tests pass and browser/persistence/export acceptance is complete.

## Prioritized remaining work

1. P0: run the changed branch's CI; close calculation fixtures; verify the hub and existing routes render on authenticated plan-matched accounts; specifically test Excel import/export and Facility Layout/SLP with all departments and From-To cells.
2. P0: check all six package states across cards, direct route/action, Copilot and exports. Unknown tier strings and unmapped module names must not authorize access. Research Pack and Enterprise Plus remain distinct.
3. P1: finish the specialist engines marked `FOUNDATION_ONLY` or `MISSING`, beginning with value-stream mapping, 5S/A3/CAPA/8D, acceptance sampling, safety/hazard registers, cutting stock, process mining, sample-size planning and water/waste balance.
4. P1: close lineage/stale-result invalidation and import → analysis → scenario → export round trips, reopening generated XLSX/PDF/PPTX/ZIP files with parsers.
5. P2/P3: configure and verify real enterprise integrations, API scopes, identity controls, cross-tenant isolation, backups and restore. Metadata-only adapters must remain NOT CONNECTED.

## Release decision

**NO-GO for production / workforce-critical use at this stage.** The source and unit checks can establish deterministic behavior for the new calculators, but this work does not itself prove all 100 tools, live integrations, authenticated persistence, complete exports, Saudi legal/PDPL readiness or the currently deployed app revision. Do not deploy migrations or alter production data as part of this changeset.
