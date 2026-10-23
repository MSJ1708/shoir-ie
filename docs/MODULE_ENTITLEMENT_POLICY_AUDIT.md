# Module entitlement policy coverage audit

## Purpose

The shared tier policy in `shoir_tier_capabilities.py` defines explicit minimum tiers for the current 96-name app catalog and subscription feature set. A name discovered outside that set and absent from `MODULE_REQUIREMENTS` remains unresolved; its absence must not be interpreted automatically as proof that the feature is free, permitted, or protected elsewhere.

The helper `audit_module_entitlement_coverage(catalog_names)` provides a machine-readable report for an observed module catalogue. It deduplicates labels, counts entries with a recognized explicit tier, lists unmapped module names, and separately reports mappings that name an unknown tier.

## Interpretation

- `COMPLETE` means every name in the supplied catalogue has a recognized entry in `MODULE_REQUIREMENTS`.
- `INCOMPLETE` means one or more names are unmapped or have an invalid tier value.
- `EMPTY` means no catalogue names were supplied. It is not a pass.
- `coverage_percent` measures explicit mapping coverage only. It is not a measure of authorization correctness, test coverage, security, or production readiness.
- `audit_module_entitlement_coverage` remains an audit helper; runtime access is enforced separately. On the 100-tool implementation branch, `available_modules()` now excludes names without a recognized explicit requirement, and `tier_allows()` returns false for unknown/empty tier labels. This is a deliberate fail-closed security behavior change; any legitimate module missing from `MODULE_REQUIREMENTS` will disappear from accessible module lists until its policy is explicitly added.

## Current source finding

The current source inventory is **96 unique module names**, derived by merging the 56 unique entries in the app.py `MODULE_CATALOG` literal with the 42 names in `industrial_platform.PLATFORM_CATALOG` and applying the same de-duplication used by the app. The six cumulative app subscription lists also resolve to exactly 96 unique names. This supersedes the earlier reported count of 85 for the current source revision; it does not claim all 96 workflows are fully implemented or end-to-end verified. Before this branch, 41 app-tier names had no explicit row in the shared `MODULE_REQUIREMENTS` map, and three shared minimum tiers conflicted with the runtime app subscription lists. This branch maps the missing names, aligns those minimum tiers, and adds tests that fail on policy drift or catalog/menu count divergence.

## Required follow-through

1. Continue from the 96-name catalogue/feature set and inventory every independently routed or dynamically registered workflow outside these two catalog sources. A matching source-level name count is not proof that all 96 module renderers work.
2. For any additional or dynamically routed name discovered outside the current 96-name source inventory, record an explicit minimum tier or deliberately declare in the canonical policy model why it is not paid-tier gated.
3. Test allow and deny paths for each mapped capability, including server-side direct-action/route checks. Hiding a module card is not sufficient authorization.
4. Keep Research Pack add-on access separate from Enterprise Plus, and preserve negative tests for both directions.
5. Do not mark the module/tier release matrix complete until the real registry is audited and the relevant tests pass.

The 96 names are confirmed source catalog and subscription-feature declarations, not proof that every renderer, calculation, import/export, persistence path, or protected action works. Inventory any routes outside those declarations, and use the existing release-verification matrix as the source of truth for outstanding end-to-end checks.


## Machine-readable module inventory

See [`MODULE_TIER_INVENTORY.csv`](MODULE_TIER_INVENTORY.csv) for the full 96-name source-level inventory, the currently declared minimum subscription tier, which app tier list first introduces each name, the catalog source(s), and the authenticated-browser status. Every row intentionally remains `UNVERIFIED` for authenticated module walkthroughs until the per-module browser and functional matrix is actually completed. The regression suite checks that this inventory stays synchronized with the source catalog and tier lists.


## 100-tool implementation branch update (2026-10-23)

The additive target catalog and grouped library are in `shoir_100_tool_registry.py`, `shoir_100_tool_workbench.py`, and `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`. The library is embedded inside the existing Core IE Tools screen rather than creating 100 top-level navigation items. It does not claim each existing related route meets its specialist acceptance criteria.

Six deterministic quick methods are provided for data profiling, unit/dated user-supplied currency conversion, reproducible synthetic data generation, standard-time calculation, Wilson work-sampling intervals, and takt/capacity. Other target IDs do not produce a success-shaped placeholder; the calculation dispatcher raises a clear not-implemented error when no supported engine is declared.

The policy update also tightens the independent `industrial_platform.tier_allows()` implementation. Research Pack continues to inherit through Enterprise and research tools only; it does not imply Enterprise Plus. Enterprise Plus does not imply Research Pack.

See `docs/SHOIR_100_TOOL_IMPLEMENTATION_REPORT.md` for status counts and the current release decision. Authenticated browser status remains `UNVERIFIED` for the new tool matrix until each workflow is actually exercised with a disposable authenticated account. This branch is not a production release approval.
