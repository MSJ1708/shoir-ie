# Module entitlement policy coverage audit

## Purpose

The shared tier policy in `shoir_tier_capabilities.py` provides `MODULE_REQUIREMENTS` for a subset of module names. A module name absent from that mapping has no explicit policy in this particular map. That absence must not be interpreted automatically as proof that the feature is free, permitted, or protected elsewhere.

The helper `audit_module_entitlement_coverage(catalog_names)` provides a machine-readable report for an observed module catalogue. It deduplicates labels, counts entries with a recognized explicit tier, lists unmapped module names, and separately reports mappings that name an unknown tier.

## Interpretation

- `COMPLETE` means every name in the supplied catalogue has a recognized entry in `MODULE_REQUIREMENTS`.
- `INCOMPLETE` means one or more names are unmapped or have an invalid tier value.
- `EMPTY` means no catalogue names were supplied. It is not a pass.
- `coverage_percent` measures explicit mapping coverage only. It is not a measure of authorization correctness, test coverage, security, or production readiness.
- This is an audit-only helper. It intentionally does not alter runtime access decisions; changing implicit/unmapped behavior before the actual catalogue and intended free-tier rules are reconciled could break existing users.

## Current source finding

The current source inventory is **96 unique module names**, derived by merging the 56 unique entries in the app.py `MODULE_CATALOG` literal with the 42 names in `industrial_platform.PLATFORM_CATALOG` and applying the same de-duplication used by the app. The six cumulative app subscription lists also resolve to exactly 96 unique names. This supersedes the earlier reported count of 85 for the current source revision; it does not claim all 96 workflows are fully implemented or end-to-end verified. Before this branch, 41 app-tier names had no explicit row in the shared `MODULE_REQUIREMENTS` map, and three shared minimum tiers conflicted with the runtime app subscription lists. This branch maps the missing names, aligns those minimum tiers, and adds tests that fail on policy drift or catalog/menu count divergence.

## Required follow-through

1. Continue from the 96-name catalogue/feature set and inventory every independently routed or dynamically registered workflow outside these two catalog sources. A matching source-level name count is not proof that all 96 module renderers work.
2. Review every unmapped name. Record an explicit minimum tier, or deliberately declare the capability as intentionally available without a paid-tier gate in the canonical policy model.
3. Test allow and deny paths for each mapped capability, including server-side direct-action/route checks. Hiding a module card is not sufficient authorization.
4. Keep Research Pack add-on access separate from Enterprise Plus, and preserve negative tests for both directions.
5. Do not mark the module/tier release matrix complete until the real registry is audited and the relevant tests pass.

This report does not claim that every module has been inventoried or authenticated-browser verified. The existing release-verification matrix remains the source of truth for outstanding end-to-end checks.


## Machine-readable module inventory

See [`MODULE_TIER_INVENTORY.csv`](MODULE_TIER_INVENTORY.csv) for the full 96-name source-level inventory, the currently declared minimum subscription tier, which app tier list first introduces each name, the catalog source(s), and the authenticated-browser status. Every row intentionally remains `UNVERIFIED` for authenticated module walkthroughs until the per-module browser and functional matrix is actually completed. The regression suite checks that this inventory stays synchronized with the source catalog and tier lists.
