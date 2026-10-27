# Shoir-IE release manifest and rollback template

**Status:** TEMPLATE — fill and review for a specific candidate before any deployment. Do not treat blank fields as completed evidence.

> **Current evidence note — 27 October 2026:** staging baseline `76419a9842f88292f94d706ca9b20bab63c45550` passed general validation ([40480842355](https://github.com/MSJ1708/shoir-ie/actions/runs/40480842355)) and authenticated staging gate ([40480842338](https://github.com/MSJ1708/shoir-ie/actions/runs/40480842338)). These checks apply only to the pre-#207/#208 candidate. This template remains NOT APPROVED and must be completed against the final exact commit before any deployment. Production changes and migrations remain on hold.



## Latest live parity note — 27 October 2026

This is a **current recheck observation, not release approval**. The production `shoir-persistence` Edge Function is v8 (source SHA-256 `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`) and its login handler still contains the master-admin tier/`updated_at` auto-repair update. Staging is v10 (source SHA-256 `5605d40e61feac6d010e7e1097565a7090bdf3325c862cc09de32af650b5a232`) and its source has the read-only canonical-admin invariant check. A read-only query observed the reserved admin row matching the required role, tier, active state and 2099-01-01 UTC expiry in both projects; this does not make production v8 safe or parity-complete.

Production migration history currently ends at `20261019140600_atomic_subscription_request_decisions`. Staging records three extra migrations for beta legal/referral, approval guard and refund-policy version refresh; production lacks the legal-acceptance columns and `public.shoir_referrals` table. The older referral migration is documented as rewriting affiliate codes and `updated_at` values, so **do not replay it against production**. Do not deploy staging v10 to production until a reviewed, schema-compatible function/migration manifest and an isolated production-shaped forward/recovery/restore rehearsal have passed.

The tool integration candidate PR #208 is not yet a release candidate accepted by the release gate: its head is two commits behind current staging, exact-head validation was queued at recheck, and live deployment smoke was skipped. The exact final release SHA, successful authenticated staging gate, backup/restore evidence, reviewed branch protection/status-check requirements, legal/privacy approvals and accountable release-owner authorization must be attached before this template can be marked approved. See the dated evidence in `PAID_READINESS_GATE.md`.

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



## Historical deployment snapshot — 26 October 2026 (not a 27 October release manifest)

| Field | Verified value/status |
|---|---|
| Current `main` SHA | `72e498d892b9eb088d34be940fc1f6d97b482c1a`. |
| Staging source branch | `staging-e2e-20261019` at `8b36e3737705867019b9cf29e603cfc37e7911e6` at the recorded inspection. Verify again before a future rollout. |
| Current audit PR head | Read the latest head directly on [PR #192](https://github.com/MSJ1708/shoir-ie/pull/192); this documentation branch is not the application release candidate. |
| Production Streamlit branch / commit / entry point | **NOT VERIFIED** — connected tools cannot read Streamlit Cloud settings. Public main hosted smoke fails. |
| Staging app entry point / exact deployed commit | **NOT VERIFIED** for the hosted URL. The branch SHA above is Git source evidence only. Current staging hosted smoke and authenticated gate are skipped, not passed. |
| Production Supabase | `gcsamrdaeraxieaagsta`, `eu-central-1`, 14 applied migrations ending `20261019140600_atomic_subscription_request_decisions`. |
| Staging Supabase | `hfhrosthswcybccepmak`, `eu-central-1`, 17 applied migration records including legal/referral and refund-policy acceptance changes. |
| `shoir-persistence` | Active version 8 in both projects, but source hashes differ: production `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`; staging `b25d2c22d33baa4daef2b63d27375dcdfac57bb58cfc5e577882882436a0d0d0`. |
| Main branch protection | **FAIL** — `protected=false`, no repository rulesets. Protection endpoint is not writable through the current connected integration. |
| Tool acceptance scope | No tool is currently `VERIFIED_WORKING` in the main 100-tool matrix (89 need validation, 9 foundation-only, 2 require external configuration). No paid-pilot subset is evidenced. |
| Owner approval / restore evidence | **NOT RECEIVED / NOT VERIFIED**. No production mutation authorized or performed. |

### Explicit stop condition

**Do not execute a production deployment from this snapshot.** The app/DB/Edge source mismatch, failed production hosted smoke, skipped staging authenticated gate, unprotected main, unverified backup/restore, and open legal/privacy/calculation gates are blockers. A future manifest must be created for a newly selected candidate SHA after review; it must list exact migrations, function hashes, feature scope, configuration names/presence, successful exact-SHA checks, restore evidence, abort conditions, rollback references and written owner approval.

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
