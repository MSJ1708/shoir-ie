# Shoir-IE release gate matrix and handover — 26 October 2026

**Decision: NO-GO. Keep BETA visible. Production unchanged.**  
**Baseline:** main 267be8889c310d90141c047d8aadd42c942423fb; staging-e2e-20261019 8b36e3737705867019b9cf29e603cfc37e7911e6.

## Mandatory gates

| Gate | Status | Evidence / next action |
|---|---|---|
| Source control | FAIL / BLOCKED | Main branch API says protected=false; visible rulesets empty; protection details unavailable. Repo admin must configure and verify rules. |
| Independent review | BLOCKED | #196/#197 have no review submissions; open PRs were drafts at snapshot. |
| Staging host / deployed SHA / startup | BLOCKED | Source entrypoint/guard inspected; Streamlit Cloud config and running revision not verifiable here. |
| CI on exact candidate | PARTIAL | Specific SHAs have green runs, but this documentation update creates a new SHA; rerun exact-head checks. |
| Hosted smoke | PARTIAL | Prior public smoke passed on some runs; other runs failed or skipped. Current deployed revision not proven. |
| Authenticated E2E | BLOCKED | Current staging SHA run 40273588637 was SKIPPED. Last actual dispatch run 39613907604 failed on stale SHA due to two module-logout assertions. |
| Identity and tenancy | PARTIAL / BLOCKED | Old backend lifecycle/isolation passed; current login, expiry, revoked-session, cross-user and cross-workspace behavior needs current run. |
| Persistence | NOT RUN on current candidate | Test save/reload/re-login/restore and cleanup using synthetic users. |
| Staging Supabase | PARTIAL | Function v9 and current schema inventoried; migration history mismatch and runtime acceptance unresolved. |
| Production Supabase | FAIL | Function v8 and missing legal/referral schema/migrations. Do not deploy pending reviewed change plan/authorization. |
| T096 | PARTIAL / BLOCKED live endpoint | Generic REST code/mocked tests exist in PR #195; no actual endpoint/token test. |
| T098 | BLOCKED | No provider-backed OIDC, enforced MFA or durable audit proof. |
| 100-tool claims | FAIL for full operational claim | 100 unique IDs/names; 98 need validation, 2 external configuration required, 0 verified-working. Narrow claims to the evidence-backed subset. |
| Workbook/Excel/export | PARTIAL | Earlier browser check passed shell/Excel and no uncaught JS error; current hosted persistence/export and mobile/desktop evidence incomplete. |
| Legal/privacy/commercial | BLOCKED | Entity, professional review, PDPL/data transfer, tax/payment/invoicing, refund/referral and public claims require accountable decisions. |
| Operations/recovery | NOT VERIFIED | Backup restore, alerts/monitoring, incident response, on-call ownership and rollback rehearsal evidence absent. |
| Production authorization | BLOCKED | No authorized change window/owner record; production unchanged. |
| BETA removal | NO-GO | Do not remove until all applicable gates and explicit release-owner approval. |

## Actions in priority order

1. **Repository administrator:** Configure main protection, independent approval, stale-review dismissal, conversation resolution, correct current checks and force-push/deletion/direct-write restrictions. Verify settings after save.
2. **GitHub Actions administrator:** Verify required staging secrets/variables and synthetic shoir-e2e-* user fixtures without disclosing values. From Actions UI, select authenticated-release-gate, branch staging-e2e-20261019, then Run workflow. Keep only staging URL/key.
3. **Streamlit Cloud owner:** Verify staging URL, repository, staging branch, staging_app.py entry point, environment secrets, exact required banner and running SHA. Capture sanitized evidence.
4. **QA/release operator:** Run the current authenticated gate. Require non-skipped passing backend lifecycle/isolation, 96-module render matrix, browser/workbook/logout and artifacts. Fix defects rather than bypassing tests.
5. **Independent reviewers:** Review #196 startup patch, #197 evidence update and #195 connector changes separately. Rerun exact-head checks and obtain approval before merge.
6. **Supabase owner:** Reconcile migration ledger mismatch; verify actual DDL/policies/triggers; test backup recovery in isolation; prepare reviewed migration/function deployment order.
7. **T096 owner:** Provide authorized staging endpoint/schema and least-privilege secret; execute real success and negative tests.
8. **Identity/security owner:** Select provider and test tenant, implement OIDC/MFA/durable audit, verify positive/negative cases or keep T098 blocked.
9. **Tool QA owner:** Run each selected launch module against independent expected results, tier checks, persistence, exports and workspace boundaries; update matrix only when evidence supports it.
10. **Saudi legal/privacy counsel and business owner:** Establish contracting identity/privacy contact; approve terms, calculation disclaimer, PDPL/cross-border processing, referral/refund, data retention and marketing language.
11. **Qualified tax/payment owner:** Determine VAT/e-invoicing obligations and test server-verified payment, renewal, cancellation, refund and entitlement revocation if offered.
12. **Operations owner:** Verify monitoring, alerts, incident plan, backup restore and rollback rehearsal.
13. **Accountable release owner:** Approve a defined, evidence-backed GO scope; deploy only the exact approved candidate and remove BETA only after production smoke and post-release checks.

## Evidence links

- Main: https://github.com/MSJ1708/shoir-ie/commit/267be8889c310d90141c047d8aadd42c942423fb
- Staging: https://github.com/MSJ1708/shoir-ie/commit/8b36e3737705867019b9cf29e603cfc37e7911e6
- PR #195: https://github.com/MSJ1708/shoir-ie/pull/195
- PR #196: https://github.com/MSJ1708/shoir-ie/pull/196
- PR #197: https://github.com/MSJ1708/shoir-ie/pull/197
- Staging validation run 40273588613: https://github.com/MSJ1708/shoir-ie/actions/runs/40273588613
- Current staging authenticated job (SKIPPED) 40273588637: https://github.com/MSJ1708/shoir-ie/actions/runs/40273588637
- Older failed authenticated gate 39613907604: https://github.com/MSJ1708/shoir-ie/actions/runs/39613907604

## Handover summary

The key immediate unblocker is a real, current-candidate authenticated staging run after the hosted app and Actions fixtures are confirmed. That passing run alone would not authorize production: branch protection/review, schema/function compatibility, a reviewed launch module subset, T096/T098 external evidence, legal/commercial approval, and operational recovery proof remain release gates.