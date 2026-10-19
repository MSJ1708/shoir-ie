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

The source-defined `industrial_platform.PLATFORM_CATALOG` currently contains 42 distinct module entries. Before this follow-up, 28 of those entries had no explicit row in the shared `MODULE_REQUIREMENTS` map; this branch adds those declared minimum tiers. A regression test now checks that every catalog entry has an explicit matching shared policy. This is a source-level catalog count, not proof that all legacy routes and other module surfaces in the application have been reconciled with the separate reported total of 85 modules.

## Required follow-through

1. Continue from `PLATFORM_CATALOG` and inventory every additional module route/catalog outside it. Do not assume the 42-entry catalog is the whole app or silently replace the reported 85-module claim.
2. Review every unmapped name. Record an explicit minimum tier, or deliberately declare the capability as intentionally available without a paid-tier gate in the canonical policy model.
3. Test allow and deny paths for each mapped capability, including server-side direct-action/route checks. Hiding a module card is not sufficient authorization.
4. Keep Research Pack add-on access separate from Enterprise Plus, and preserve negative tests for both directions.
5. Do not mark the module/tier release matrix complete until the real registry is audited and the relevant tests pass.

This report does not claim that every module has been inventoried or authenticated-browser verified. The existing release-verification matrix remains the source of truth for outstanding end-to-end checks.
