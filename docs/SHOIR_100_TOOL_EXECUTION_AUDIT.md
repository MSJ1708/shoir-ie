# Canonical T001–T100 execution-route audit

**Revision:** 2026-11-16  
**Scope:** Source-level route and evidence inventory for the canonical 100-tool registry.  
**Important:** This is not a passing test report or hosted acceptance certificate.

## Summary

| Audit dimension | Count | Meaning |
|---|---:|---|
| Canonical registry entries | 100 | Stable T001–T100 metadata rows |
| Dedicated focused Workbench method branches | 100 | All canonical IDs have a dedicated ID-bound Workbench dispatch path |
| Mapped legacy-module launch only | 0 | No canonical ID relies only on a mapped legacy-module launch |
| IDs with no declared mapped route | 0 | All current rows declare an existing module or route |
| Verified working | 0 | No tool is promoted to verified by this static audit |
| External configuration required | 4 | T096–T099 still depend on real service/configuration and acceptance |

The nine formerly mapped-only IDs now enter dedicated canonical dispatch handlers: T001, T003, T008, T053, T057, T064, T088, T090 and T093. Each handler rechecks the canonical tier gate and uses the existing authenticated actor and per-user workspace persistence callbacks. T053, T057 and T064 disclose their bounded heuristic assumptions; T088 marks source syntax as unverified; T090 formats supplied content only; T093 validates a typed workflow plan without executing downstream tools.

This is a source-level route implementation result, not a claim that the tools are verified working. Browser acceptance, fresh-session managed persistence, role/tier matrices, export inspection and independent engineering review remain required. A dedicated route is not an acceptance certificate.

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
