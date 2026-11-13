# Shoir-IE Digital Thread Acceptance

Assessment date: 2026-11-13. Status: **canonical identity foundation and candidate rename workflow implemented; managed lineage acceptance pending**.

## Current candidate implementation

The release-hardening candidate now includes:

- Immutable identity-key support for Digital Thread nodes and canonical entities, with explicit business-key discovery for supported source tables.
- Alias history and duplicate/ambiguous identity rejection in the canonical identity layer.
- A user-facing node rename workflow that retains the existing canonical node ID and connected edges.
- A display-name override retained when the same immutable source identity is synchronized again.
- A workspace rename-history record and a managed-save path that requires the authenticated actor to match the active account and a configured durable backend. If the managed save cannot be confirmed, the UI restores the prior node state in the current session.
- Unit tests for stable IDs, alias retention, duplicate source/name rejection, edge preservation, display override on subsequent sync, actor/guest denial and managed-save failure.

These changes are part of the open draft PR #232 candidate branch. They are source and test implementation, not proof of a hosted save/reload/re-login flow. The rename history is ordinary editable workspace metadata and is **not** an append-only or tamper-proof enterprise audit log.

## Remaining acceptance requirements

- Exact-candidate CI must pass after the rename implementation and its tests are added; queued or earlier-SHA checks do not count.
- Independent code/security review and required PR approval remain outstanding.
- Hosted staging create/rename/reload/re-login must prove the same canonical ID, prior aliases, rename history and connected relationships survive a new authenticated session.
- A fresh workspace sync after rename must retain the user's display-name override and preserve current/historical relationships.
- Dataset version changes must mark dependent model/run/scenario/decision/outcome records stale while preserving historical references and exports.
- Organization/tenant-level scope is not yet deployed or accepted. Current managed platform data foundations must not be described as company-wide collaboration.
- Cross-workspace and cross-organization access denial must be tested with multiple disposable identities.
- Workforce content remains aggregate-only; do not include employee names or personal identifiers in Digital Thread records.
- Rename history must remain clearly distinguished from immutable security audit evidence.

## Safe execution order

1. Run exact-head Python tests, engine regression, security-quality, migration replay and Edge Function checks on PR #232.
2. Obtain an independent review and resolve every review conversation before considering a staging merge.
3. After a verified staging backup/restore path exists, deploy the reviewed candidate to staging only.
4. Run authenticated disposable-account Digital Thread create → rename → sync → save → logout → re-login → restore checks.
5. Verify identity continuity, alias retention, graph edge continuity, duplicate/ambiguous failure behavior and cross-workspace/org denial.
6. Change a dataset version and prove dependent outputs become stale without rewriting historical evidence.
7. Attach redacted exact-SHA browser traces and reviewer sign-off.

Until all hosted and independent evidence is attached, retain **NOT ACCEPTED / NOT VERIFIED** for managed Digital Thread lineage and tenant sharing.
