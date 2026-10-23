# Module entitlement policy coverage audit

## Purpose

The shared tier policy in `shoir_tier_capabilities.py` defines explicit minimum tiers for the current 97-name app catalog and subscription feature set. A name discovered outside that set and absent from `MODULE_REQUIREMENTS` remains unresolved; its absence must not be interpreted automatically as proof that the feature is free, permitted, or protected elsewhere.

The helper `audit_module_entitlement_coverage(catalog_names)` provides a machine-readable report for an observed module catalogue. It deduplicates labels, counts entries with a recognized explicit tier, lists unmapped module names, and separately reports mappings that name an unknown tier.

## Interpretation

- `COMPLETE` means every name in the supplied catalogue has a recognized entry in `MODULE_REQUIREMENTS`.
- `INCOMPLETE` means one or more names are unmapped or have an invalid tier value.
- `EMPTY` means no catalogue names were supplied. It is not a pass.
- `coverage_percent` measures explicit mapping coverage only. It is not a measure of authorization correctness, test coverage, security, or production readiness.
- This is an audit-only helper. It intentionally does not alter runtime access decisions; changing implicit/unmapped behavior before the actual catalogue and intended free-tier rules are reconciled could break existing users.

## Current source finding

The feature branch now contains **97 unique module names**, derived by merging the 56 unique entries in the app.py `MODULE_CATALOG` literal with the 43 names in `industrial_platform.PLATFORM_CATALOG` and applying the app's de-duplication rule. The six cumulative app subscription lists also resolve to exactly 97 unique names after adding the Starter-level `100-Tool Engineering Hub`. Before the hub was added, the baseline contained 96 module names; this update does not claim all 97 workflows are fully implemented or end-to-end verified. The source policy audit maps explicit minimum tiers for the newly added hub and adds regression checks to keep menus, catalogues and tier policies aligned.

## Required follow-through

1. Continue from the 97-name catalogue/feature set and inventory every independently routed or dynamically registered workflow outside these two catalog sources. A matching source-level name count is not proof that all 97 module renderers work.
2. For any additional or dynamically routed name discovered outside the current 97-name source inventory, record an explicit minimum tier or deliberately declare in the canonical policy model why it is not paid-tier gated.
3. Test allow and deny paths for each mapped capability, including server-side direct-action/route checks. Hiding a module card is not sufficient authorization.
4. Keep Research Pack add-on access separate from Enterprise Plus, and preserve negative tests for both directions.
5. Do not mark the module/tier release matrix complete until the real registry is audited and the relevant tests pass.

The 97 names are confirmed source catalog and subscription-feature declarations, not proof that every renderer, calculation, import/export, persistence path, or protected action works. Inventory any routes outside those declarations, and use the existing release-verification matrix as the source of truth for outstanding end-to-end checks.


## Machine-readable module inventory

See [`MODULE_TIER_INVENTORY.csv`](MODULE_TIER_INVENTORY.csv) for the full 97-name source-level inventory, the currently declared minimum subscription tier, which app tier list first introduces each name, the catalog source(s), and the authenticated-browser status. Every row intentionally remains `UNVERIFIED` for authenticated module walkthroughs until the per-module browser and functional matrix is actually completed. The regression suite checks that this inventory stays synchronized with the source catalog and tier lists.


## Current feature-branch delta (2026-10-23)

The branch adds the Starter-level `100-Tool Engineering Hub` as one grouped destination rather than 100 new top-level navigation items. The module catalog and entitlement inventory therefore contain **97 distinct module names** on this branch. This is separate from the new 100-row tool-level target matrix in `SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv`. The hub's catalogue status is not authenticated evidence: the new inventory row and every other row remain `UNVERIFIED` for browser execution until the authenticated route matrix runs against this exact revision.
