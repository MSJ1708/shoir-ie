# T099 — Data Governance and Backup Recovery Acceptance

**Acceptance status:** `EXTERNAL_CONFIGURATION_REQUIRED`  
**Release status:** **NOT ACCEPTED / NOT VERIFIED**  
**Scope:** Staging restore rehearsal and infrastructure recovery evidence. This record does not authorize a production restore, migration or destructive test.

## 1. Implemented boundary (do not overstate)

The application contains an owner-scoped personal workspace export/restore path with integrity and account-ownership checks. That capability is not a database backup, PITR service, organization-wide disaster-recovery system, encrypted off-project backup, or proof that a Supabase project can be restored.

A locally generated checksum detects accidental changes; it is not encryption, a digital signature, or proof of authenticity.

## 2. Infrastructure prerequisites

- Confirm the actual Supabase plan and project configuration support the selected backup/PITR schedule and retention. Do not infer capability from a plan name or assume it is enabled.
- Record database backup frequency, retention, PITR availability/window, and the operational owner who can request recovery.
- Create an encrypted, access-controlled off-project backup/export copy with separate credentials and documented key rotation/recovery. Test that the recovery team can access it without relying on the primary project.
- Back up and inventory Supabase Storage object bodies independently. Supabase database backups do not include the actual Storage API object bytes; restoring database metadata alone does not restore files. See the [Supabase backup documentation](https://supabase.com/docs/guides/platform/backups).
- Securely inventory configuration that is not contained in a database backup: Edge Function secrets, external provider credentials, OAuth/IdP configuration, DNS/TLS, Streamlit settings, webhook configuration and other operational dependencies.
- Define and approve recovery point objective (RPO), recovery time objective (RTO), retention, legal hold, deletion and incident-notification procedures.

## 3. Required acceptance cases

| Area | Required evidence |
|---|---|
| Backup availability | Timestamped proof of the configured scheduled backup/PITR capability, retention window and recovery point. |
| Off-project copy | Encrypted copy in a separate failure domain; access controls and restore-key custody documented. |
| Isolated restore | Restore into a disposable, isolated staging project that cannot write to production or contact production integrations. |
| Database integrity | Migration/schema versions, critical table counts, constraints, RLS, grants, RPC permissions and representative row checks match the chosen recovery point. |
| Storage integrity | Independently restore object bytes; compare expected object count, paths, size and SHA-256 checksums with the restore manifest. |
| Auth/configuration | Verify required auth identities/configuration and restore operational secrets from the approved secret manager without exposing values in logs. |
| Application recovery | Point a staging app at the isolated restored project and test login, entitlement, workspace, dataset, Digital Thread and export workflows. |
| Tenant isolation | Confirm a restored user/org cannot access another user's or tenant's files, rows or artifacts. |
| RPO/RTO | Measure actual elapsed recovery time and data-loss interval; compare to the approved objectives. |
| Failure handling | Exercise a failed/partial restore, document rollback/isolation, escalation and retry without touching production. |
| Data governance | Verify retention, deletion, legal hold, backup expiry and evidence redaction handling. |

## 4. Evidence bundle

Attach:
1. Supabase project identifier and plan/configuration evidence (no secrets).
2. Backup/PITR configuration, recovery point timestamp and retention proof.
3. Encrypted off-project backup object metadata, checksum and access-control evidence.
4. Storage object backup manifest and separate object-restore checksum report.
5. Isolated restore project identifier, restore logs, start/end timestamps and operator.
6. Schema/migration/grant/RLS/RPC verification report and representative integrity checks.
7. App-level staging smoke results against the restored project.
8. Measured RPO/RTO, exceptions, rollback evidence and remediation record.
9. Independent infrastructure/security reviewer sign-off.

Do not attach secret values, raw customer records, unredacted logs or production access tokens.

## 5. Pass/fail rule

T099 may move to `VERIFIED_WORKING` only after a complete, repeatable isolated restore proves the database **and** Storage object recovery path, the restored staging application passes the required workflows, access isolation is preserved, RPO/RTO are measured against approved objectives, and an independent reviewer signs the evidence.

A dashboard showing that backups exist, a personal workspace JSON export, or a successful database-only restore is insufficient. Until the full evidence bundle exists, retain `EXTERNAL_CONFIGURATION_REQUIRED` and block any claim of disaster-recovery readiness.

## 6. Safe execution order

1. Confirm plan, backup/PITR configuration and retention in the Supabase Dashboard.
2. Agree RPO/RTO, legal retention/deletion and the recovery operator.
3. Configure encrypted off-project database backups and independent Storage object backups.
4. Capture secrets/configuration in the approved secret manager (never in the backup evidence bundle).
5. Provision an isolated disposable restore target with no production write path.
6. Restore database and Storage objects; verify schema, grants, RLS, RPC access and checksums.
7. Point a disposable staging app to the restore and run recovery smoke tests.
8. Measure RPO/RTO, record exceptions and obtain independent review.
9. Repeat after material schema, storage or deployment changes.

**Never test recovery by deleting, pausing, resetting or overwriting the production project.**
