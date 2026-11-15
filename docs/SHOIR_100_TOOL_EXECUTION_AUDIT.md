# Canonical T001–T100 execution-route audit

**Revision:** 2026-11-15  
**Scope:** Source-level route and evidence inventory for the canonical 100-tool registry.  
**Important:** This is not a passing test report or hosted acceptance certificate.

## Summary

| Audit dimension | Count | Meaning |
|---|---:|---|
| Canonical registry entries | 100 | Stable T001–T100 metadata rows |
| Dedicated focused Workbench method branches | 78 | The selected tool ID enters a dedicated method/form dispatch path |
| Mapped legacy-module launch only | 22 | The directory can open the declared existing module/route, but the selected canonical ID has no dedicated focused method branch |
| IDs with no declared mapped route | 0 | All current rows declare an existing module or route |
| Verified working | 0 | No tool is promoted to verified by this static audit |
| External configuration required | 4 | T096–T099 still depend on real service/configuration and acceptance |

The 22 mapped-module-only IDs are:

`T001, T003, T004, T005, T008, T011, T012, T013, T014, T020, T053, T057, T064, T065, T073, T086, T088, T090, T091, T092, T093, T095`.

The directory's **Open mapped Workbench module** action is a navigation route. It is not proof that the selected canonical ID is carried through the target module's calculation, permission check, persistence, export or audit path. The mapped legacy module must enforce its own native server-side entitlement and authorization rules. These 22 IDs therefore remain a concrete canonical-ID wiring/acceptance gap, even though the corresponding legacy module route is declared.

## What the audit checks

The executable audit is `scripts/audit_shoir_100_tool_execution.py`. It:

1. Imports the canonical registry and verifies exactly T001–T100 in stable order.
2. Reads the 100-row implementation CSV and verifies a one-to-one ID match and readiness-status agreement.
3. Parses the Workbench AST to find dedicated `selected_tool["tool_id"] == ...` and `in {...}` dispatch branches.
4. Scans test sources for T-ID references. A source reference count is not interpreted as a passing test.
5. Classifies every row as `FOCUSED_METHOD_DISPATCH`, `MAPPED_LEGACY_MODULE_LAUNCH`, or `NO_DECLARED_EXECUTION_ROUTE`.
6. Carries the matrix's unit/integration/browser evidence fields and remaining-gap text into the per-tool report.

Run from the repository root:

```bash
python scripts/audit_shoir_100_tool_execution.py > shoir_100_tool_execution_audit.json
pytest -q tests/test_shoir_100_tool_execution_audit.py
```

## Acceptance criteria still required per tool

A dedicated branch or mapped module does not mean a tool is accepted. Each ID still needs its real input-to-output journey verified, including:

- correct engineering method, units, dimensional consistency, assumptions and boundary handling;
- invalid, missing, extreme and adversarial inputs;
- authenticated role/tier checks at the execution boundary;
- saved input/result provenance and fresh-session reload;
- scenario/model/dataset invalidation where applicable;
- charts, workbook handoff and correct XLSX/PDF/PPTX/CSV export;
- exact-head automated tests and authenticated browser acceptance;
- independent industrial-engineering review for methods used in operational decisions.

No tool is labelled `VERIFIED_WORKING` on the strength of a catalog row, a mapped route, a test name, or synthetic fixture alone.

## Release status

The 100-tool matrix currently records 96 `IMPLEMENTED_NEEDS_VALIDATION`, four `EXTERNAL_CONFIGURATION_REQUIRED` (T096–T099), and zero `VERIFIED_WORKING`. The status matrix remains a readiness claim to be tested, not a certification. The latest candidate must pass its complete required CI on its exact head, followed by authenticated staging/browser/export acceptance. Keep PR #232 draft, BETA active and production NO-GO.
