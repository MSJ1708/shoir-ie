# Shoir-IE release manifest and rollback template

**Status:** TEMPLATE — fill and review for a specific candidate before any deployment. Do not treat blank fields as completed evidence.

## Release identity

| Field | Required value |
|---|---|
| Release/candidate label | NOT SET |
| Source branch and exact commit SHA | NOT SET |
| Release PR and required approvals | NOT SET |
| Python/runtime and dependency lockfile SHA | NOT SET |
| Streamlit application name, entry point and configured branch | NOT VERIFIED |
| Supabase project reference (identifier only; never credentials) | NOT VERIFIED |
| Migration files included and verified current on target | NOT VERIFIED |
| Deployed Edge Function names/versions and source SHAs | NOT VERIFIED |
| Required configuration/secret names present (presence only) | NOT VERIFIED |
| Feature flags and included pilot tool IDs | NOT SET |
| Policy versions / consent versions | NOT SET |
| Accountable owner approval and timestamp | NOT RECEIVED |

## Preflight checklist

- [ ] Main branch protection and required checks are enabled and verified.
- [ ] All included PRs are reviewed, non-duplicate changes reconciled, and review threads resolved.
- [ ] Full CI and exact-candidate regression/security tests are green; skipped jobs are listed separately.
- [ ] Authenticated staging acceptance passed for the exact candidate SHA with disposable accounts and synthetic data.
- [ ] Two-user tenant isolation and direct route/action/API/Copilot/export denial checks passed.
- [ ] Current DB migration history, RPC definitions and deployed Edge versions were checked against source.
- [ ] Staging and production config names/presence checked without printing or copying secret values.
- [ ] Backup/recovery target identified; restore test completed and evidence linked.
- [ ] Data exports, consent, save/reload/re-login, expiry/revocation and browser tests passed.
- [ ] Legal, privacy, operator identity, calculation, payment, tax and support gates for the exact pilot scope are closed.
- [ ] Non-destructive preflight passed and explicit owner authorization is attached.

## Deployment sequence

Document the reviewed sequence for app, schema and Edge changes. Prefer backward-compatible expand/contract changes. State which old app version can run against each schema version, how consent enforcement remains compatible, and what should happen if the sequence stops after any step. Do not run a production deployment from this template without separate written authorization.

| Step | Action | Preconditions | Verification | Abort / rollback |
|---|---|---|---|---|
| 1 | NOT SET | NOT SET | NOT SET | NOT SET |
| 2 | NOT SET | NOT SET | NOT SET | NOT SET |
| 3 | NOT SET | NOT SET | NOT SET | NOT SET |

## Postflight checklist

- [ ] Deployed app SHA, entry point, migration set, RPCs and Edge versions verified.
- [ ] Public startup/health smoke passed against the intended deployment.
- [ ] Synthetic disposable-account login, consent and core included workflow passed.
- [ ] Save/reload/re-login and actual XLSX/PDF/PPTX/ZIP open/parse checks passed where in scope.
- [ ] Tier denial, expired/revoked session and tenant isolation remain correct.
- [ ] No secret values or personal/customer data leaked to logs or artifacts.
- [ ] Monitoring and alert routing observed; support/on-call role notified.
- [ ] Release evidence and unresolved limitations published to the internal release record.

## Rollback plan

**Rollback trigger:** NOT SET. Include a measurable threshold and accountable decision-maker.

**Rollback command/steps:** NOT SET. Include exact ref/version changes; never guess a rollback command during an incident.

**Database compatibility/recovery:** NOT SET. A code rollback does not automatically reverse data/schema changes. Provide forward-fix or restore strategy and prove backup recoverability.

**Edge Function compatibility/recovery:** NOT SET. Record version pin/rollback procedures, environment compatibility, and tests.

**Customer/data communication:** NOT SET. Identify support and privacy escalation roles and approved notice process.

**Owner authorization:** NOT RECEIVED.

## Incident and approval record

| Role | Responsible person/team | Evidence / contact | Status |
|---|---|---|---|
| Release owner | NOT NAMED | NOT PROVIDED | BLOCKED |
| Application operator | NOT VERIFIED | NOT PROVIDED | BLOCKED |
| Database/Edge owner | NOT VERIFIED | NOT PROVIDED | BLOCKED |
| Security reviewer | NOT NAMED | NOT PROVIDED | BLOCKED |
| Privacy/legal reviewer | NOT NAMED | NOT PROVIDED | BLOCKED |
| Customer support/on-call | NOT NAMED | NOT PROVIDED | BLOCKED |
