# Production v8 security hotfix candidate

**Status: DRAFT / NOT DEPLOYED.** This source is based on the live production `shoir-persistence` v8 payload retrieved on 2026-10-28. Its purpose is to make the minimum compatible correction available for independent review while production schema rollout remains on hold.

## Exact scope

- Replace wildcard CORS with exact approved-origin handling, HTTP 403 for unapproved Origin values, HTTP 204 for allowed OPTIONS preflight, and no fabricated `Access-Control-Allow-Origin` header when Origin is absent.
- Remove login-time tier/`updated_at` mutation of the reserved `sho` administrator. If the canonical invariant is wrong, return a generic HTTP 503 and do not issue a session.
- Preserve the v8 handler's existing database action set. This candidate does not reference `shoir_referrals` or the six legal-acceptance columns missing in production.

## Provenance and verification required

The source snapshot was read from production function v8. Current deployed source hash at time of capture: `410e22f7af0be8f3ec74bae5a15aec70f8b6a807a540e98a2c5143f4e6b8790d`. The candidate must be reviewed against the live v8 source and type-checked/tested before any use. A successful local/CI test does not prove deployment.

## Prohibited until explicitly authorized

Do not deploy this function based on the existence of this folder or a green workflow alone. Require independent security review, release-owner approval for this exact source hash/target, approved recovery reference, and confirmation that the current production deployment hash has not changed since the source was captured. After an approved deployment, repeat real OPTIONS probes against production and verify login/session behavior with disposable non-admin identities only. Never log in as or mutate the protected `sho` account.
