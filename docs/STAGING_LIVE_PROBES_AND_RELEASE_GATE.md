# Staging live release probes

This change adds live checks to the existing staging release path. These checks use no credentials for CORS and only dedicated `shoir-e2e-*` identities for the authenticated gate.

## CORS probe

`scripts/live_cors_probe.py` refuses any endpoint except the staging `shoir-persistence` function and any origin except the configured staging app host. It verifies:

- an approved preflight returns HTTP 204 and exactly the approved origin;
- a hostile-origin preflight returns HTTP 403 with no allow-origin response header;
- a preflight without an Origin does not fabricate an allow-origin header;
- a hostile-origin POST is rejected before action parsing and emits no CORS allow-origin header.

The probe uses the GitHub Actions runner because the local execution environment cannot resolve the Supabase hostname. Network/DNS failures fail the probe rather than being reported as PASS.

## Workflow activation

The hosted public smoke now runs for pull requests targeting staging, staging pushes, and explicit dispatches on staging, as well as the existing main/audit cases. Staging runs use `SHOIR_E2E_APP_URL` and validate it through `scripts/staging_e2e_guard.py` before any browser navigation.

The staged authenticated release gate already supports a one-shot push marker: `[run-authenticated-gate]`. This PR intentionally uses that marker in its title. Merge it only after review, and preserve the marker in the merge commit message (merge commit or squash merge). The gate must fail closed if any test secret or dedicated disposable test identity is missing.

## Boundaries

This does not change production, mutate database records, run migrations, or constitute production authorization. The production function remains on its separate compatibility and approval gate. GitHub branch-rule enforcement also requires an authorized administrator because the current connection cannot read/write detailed branch protection.
