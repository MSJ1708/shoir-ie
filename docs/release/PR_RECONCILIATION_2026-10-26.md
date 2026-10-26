# Pull request and dependency reconciliation — 26 October 2026

Snapshot: GitHub open PR API for MSJ1708/shoir-ie. The 18 open PRs below were all returned as drafts. No PR should be merged merely to reduce backlog. Obtain independent review and verify exact-head checks first.

| PR | Head / purpose | Classification | Rationale / next action |
|---|---|---|---|
| #197 | docs/release-evidence-2026-10-26, 87bf544db432e0b4ec966ebec6d0b162b1501b38 | UPDATE | Add the audit artifacts and reconcile stale check notes; rerun exact-head checks; obtain independent review. |
| #196 | fix/staging-referral-optional-20261026, 7c0219385fe33bcb68b963b23dfac9a9c0fb886c | BLOCKED | Narrow staging-only referral compatibility fix; validation test succeeded, live smoke skipped. Full checks, review and hosted E2E still needed. |
| #195 | feat/t096-rest-readonly-adapter-20261026, 26d5e4f2a6569223976eff4fe43db83b0967d2e2 | UPDATE | Focused REST adapter, mocked tests and explicit T098 non-operational status; reported exact-head CI passed. No live endpoint or T098 provider proof. |
| #192 | agent/pr-integration-release-audit-20261026, e83405b68a77c3b2673258bd782391b981da4f49 | UPDATE | Stale/diverged base; reconcile with this newer evidence package and rerun checks. Legal drafts remain unapproved. |
| #191 | feat/shoir-100-t006-recovery-20261026, aa28683435b39fa45574da88e510728ae7a59b98 | UPDATE | Stale/non-mergeable base was reported; review conflicts and dependencies before refresh. |
| #189 | agent/shoir-100-release-gates-verify-20261025, 49f46bcf3d1bbdf4794a7c11a9287895232d0b29 | UPDATE | Old staging base predates PR #190 and current staging head. Retain only unique value after comparing changed files and tests. |
| #188 | agent/shoir-100-rnle-ergonomics-20261025, e8db67bd1ff24780109f0cf070e6735bb9041a56 | BLOCKED | Stacked on tools integration; reconcile dependencies and independent engineering fixture requirements. |
| #184 | feat/shoir-t044-rcm-current-base-20261025, 7af10bd003b0f11ebc4aa28d6eb2013cfedcd22d | BLOCKED | Stacked base; inspect overlap with #188/#182/#172 before rebasing. |
| #182 | audit/shoir-100-tool-continuation-20261025, 9ecfb9ed19e6f6d1c1c5b24f1272dc21366f05ba | BLOCKED | Stacked on the #172 base; reconcile once with #172 before updating. |
| #181 | feat/shoir-100-tool-methods-wave-2026-10-24, 7723e28b4eca6bbc389c6d2a80e041d6a35dbc44 | BLOCKED | Overlaps other workbench/tool PRs; preserve canonical IDs and evaluate unique code/permissions. |
| #180 | feature/shoir-100-completion-20261024, 5a12581d526fd4171d5d1ade8868bdd5636b07cf | BLOCKED | Overlaps #178/#179/#173/#174/#175/#181; select one reviewed integration sequence, no bulk merge. |
| #179 | feat/100-tool-readiness-foundations-2026-10-24, 43bff782e4c3cbae000270e23410d85671612b34 | BLOCKED | Verify denial tests and all server-side execution paths; UI hiding alone is not authorization. |
| #178 | feat/shoir-100-tool-implementation-2026-10-23, e7397c740d7fabca583e39a3c19ade986073b30e | BLOCKED | Compare registry and matrix with competing branches before choosing canonical foundation. |
| #175 | feat/100-tool-workbench-and-closed-entitlements-2026-10-23, 6a3b2be6698c3e0940ac960f4680ea15f8ad674b | BLOCKED | Overlapping tool library/entitlement work; review tier boundaries and security. |
| #174 | feature/shoir-100-tool-hub-20261023, 149484e91cfd4022db2f0faf573a9e22eaeaab86 | BLOCKED | Overlaps workbench navigation; compare route and design changes with #173/#175. |
| #173 | feat/100-tool-engineering-workbench-20261023, 3936531493d29af86eff6deddd3bf75b76dc34aa | BLOCKED | Compare shared access/renderer changes with #174/#175/#178/#179 before selecting one base. |
| #172 | audit/shoir-100-tools-20261023, a4a8663b8e3af7aff4c9ed3d6648ce9821573b11 | BLOCKED | Dependency/base for #182 and related tool branches; choose one reviewed integration chain. |
| #170 | legal-beta-referral-readiness-2026-10-21, 690ddc8ea4c9e1545014f0f0dadce160aef25c5b | BLOCKED | Review legal text and staging/prod migration drift; keep draft pending counsel and schema-history review. |

## Classification meanings

- UPDATE: the branch has a clear, scoped next edit or documentation reconciliation that can be prepared safely; it is not a merge approval.
- BLOCKED: full-diff/dependency review, a base conflict, external configuration, hosted evidence, independent review or release gating must be resolved before safely advancing the PR.
- No PR is classified MERGE, SPLIT or CLOSE_AS_SUPERSEDED from title/base metadata alone. Full diff and dependency review is required before choosing one of those actions. No PR was closed or merged by this execution.

## Confirmed related merges

- PR #194 was reported merged to main at 267be8889c310d90141c047d8aadd42c942423fb and makes referral summary optional at startup while keeping essential auth/persistence exports fail-closed.
- PR #190 was reported merged to staging at 8b36e3737705867019b9cf29e603cfc37e7911e6.
- PR #196 is a staging-only backport and is not a production release.

## Relevant workflow facts

- #196 head 7c0219385fe33bcb68b963b23dfac9a9c0fb886c: validation run 40303682913 reported test success and live-deployment-smoke skipped; push validation run 40303680055 succeeded.
- #195 head 26d5e4f2a6569223976eff4fe43db83b0967d2e2: prior exact-head evidence lists validation 40298783424, tests 40298783902, platform tests 40298783416, engine regression 40298783672 and security/quality 40298783645 as successful. Recheck before merge.
- #197 head 87bf544db432e0b4ec966ebec6d0b162b1501b38 had successful validation 40304635611, platform 40304635662, engine 40304635679, tests 40304635703 and security-quality 40304635715; those checks must be rerun after this documentation change.
- No review submissions were returned for #196 or #197. This work is not an independent review.

## Source-control control

Main reports protected=false and the visible rulesets API returns an empty array. Detailed protection endpoint returns 403. Have an authorized repository admin configure and independently verify rules before merging. Do not disable required security checks or use self-approval.