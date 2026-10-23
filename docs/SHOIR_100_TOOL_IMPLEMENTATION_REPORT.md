# Shoir-IE 100-Tool Implementation Report

## Release decision: NO-GO for claiming all targets operational

This tranche establishes a stable, auditable registry for the 100 target capabilities while preserving the existing application shell and legacy routes. It does **not** claim that every target is implemented or verified. No target is marked `VERIFIED_WORKING`: authenticated end-to-end verification and method-specific evidence are outstanding.

## Added foundations

- Stable IDs `T001`–`T100`, grouped into the ten requested workbenches, with target tier, candidate legacy route, implementation-status classification, stated method, input/output contract, source files and next gap.
- Strict lookup by canonical ID or exact canonical name; changing a presentation label cannot mutate the canonical policy.
- Fail-closed target access decision for unknown IDs, unrecognized tiers and invalid policy.
- Separate target execution-readiness gate: entitlement alone does not make an unverified target executable.
- An implementation matrix with all 19 required fields, one row per target.
- Automated checks for the 100 IDs and the full six-package truth table.

## Current known status counts

The counts are generated from the current matrix and protected by the registry test: 46 `IMPLEMENTED_NEEDS_VALIDATION`, 46 `FOUNDATION_ONLY`, 2 `MISSING`, 6 `EXTERNAL_CONFIGURATION_REQUIRED`, 0 `VERIFIED_WORKING` and 0 `BLOCKED`. A status of `IMPLEMENTED_NEEDS_VALIDATION` means an existing route is a candidate for reuse, not that its specialist target behavior passed acceptance.

## Entitlement and layout safety

Research Pack inherits Starter, Mid-Tier Pro, Professional and Enterprise-level target capabilities plus Research Pack-only targets; it never implies Enterprise Plus. Enterprise Plus does not receive Research Pack-only targets. Legacy module names, billing prices and their access contracts are not changed in this tranche. No broad redesign, production deployment, schema change or customer-data mutation is included.

## Release-critical work remaining

1. P0: complete authenticated Facility Layout/SLP, multi-sheet workbook, shared export and Enterprise Integration diagnostic workflows.
2. Integrate the target execution guard at real route/action/Copilot/API/export callers with both allow/deny tests. This registry by itself does not prove legacy enforcement.
3. Add independent golden fixtures for every numerical method; do not call a metadata card a calculation engine.
4. Run the authenticated per-target browser matrix with disposable tier accounts, persistence/reload, direct-denial, desktop/mobile and Arabic/RTL checks; upload redacted evidence.
5. Live-test integrations only at authorized staging endpoints. Metadata-only/unconfigured adapters remain `NOT CONNECTED`.
6. Record exact CI run IDs and commit SHA after the new revision has been tested.

## Source-triage limitation

Existing-route names are candidate reuse paths gathered from the current module/catalog code. A matching name is not proof of specialist behavior. See `docs/SHOIR_100_TOOL_IMPLEMENTATION_MATRIX.csv` for individual gaps and required evidence.
