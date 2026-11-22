# Shoir-IE staging backup export setup and acceptance

**Status:** encrypted export and isolated restore workflows are implemented on the PR branch; **T099 remains NOT ACCEPTED** until owner infrastructure setup is completed and both workflows actually pass against a real R2 backup.

This guide is for the staging project only:

- Project: `shoir-ie-staging-2026-10-19`
- Project reference: `hfhrosthswcybccepmak`
- Database region: Frankfurt / `eu-central-1`
- Storage source: the staging project's S3-compatible Storage endpoint

Never point this procedure at production project `gcsamrdaeraxieaagsta`. Never place credentials in chat, source code, issues, PR comments, workflow inputs or artifacts.

## 1. What the workflow does

The GitHub Actions workflows are:

- `.github/workflows/staging-backup-recovery.yml` — encrypted staging export to R2
- `.github/workflows/staging-restore-rehearsal.yml` — authenticated restore into an ephemeral local Supabase stack

Both require the protected GitHub Environment named `staging-recovery`. To preserve production `main`, each workflow is triggered by a deliberate change to a separate marker path on `staging-e2e-20261019`: `.github/backup-triggers/staging-recovery.txt` for export and `.github/restore-triggers/staging-recovery.txt` for restore. Each workflow becomes available after it has been merged into staging. Neither trigger file should be added to `main`.

When all required environment secrets are configured, it:

1. Verifies the PostgreSQL URL is for the exact staging database (direct Supabase host, or a Supabase session-pooler host with username `postgres.hfhrosthswcybccepmak`) and requires TLS.
2. Exports database roles, the `public` and `shoir_internal` schemas and their data.
3. Exports Storage bucket/object metadata and Storage policies separately.
4. Encrypts the database bundle using an `age` public recipient before upload.
5. Copies **every** staging Storage bucket's object bytes to an off-Supabase S3-compatible destination through an encrypted `rclone crypt` remote.
6. Checks the remote Storage copy against the live source and checks the uploaded encrypted database archive.
7. Records application-table row counts inside the encrypted database bundle and uploads only a redacted manifest and archive checksum to the short-retention GitHub artifact. Raw database data, Storage object bytes and encryption material are not uploaded as GitHub artifacts.

The export contains the Shoir-IE application database schemas `public` and `shoir_internal`, including the **custom Shoir-IE accounts, password hashes, application sessions, pending credentials, workspace state, organizations and memberships**. These are the application's login and persistence records; they are not stored in Supabase GoTrue `auth.users`. The export also does not include Supabase-managed schemas: Supabase CLI `db dump` excludes schemas such as `auth` and `storage`; Storage bucket/object metadata and object bytes are therefore copied separately.

A read-only staging inventory on 2026-11-22 found 9 custom account rows, 1 custom application session row, 8 pending-credential rows, 4 workspace-state rows, 11 organizations, 12 organization memberships and 4 organization workspaces. The same inventory found zero rows in every Supabase `auth` data table (including `auth.users`, identities, sessions, refresh tokens, MFA, OAuth, SSO and WebAuthn); the only populated Auth table was `auth.schema_migrations` (84 platform migration records). The export workflow checks every non-`schema_migrations` Auth table and fails if any row exists. It records `auth_data_exported: false`, `auth_non_migration_rows: 0`, and the Auth schema-migration count in the manifest, but does not export or restore platform-managed migration history. The restore verifier refuses to continue unless those exact Auth-scope assertions are present.

The backup can therefore preserve the existing **Shoir custom account store** in the application database dump while using a clean, freshly initialized Supabase GoTrue/Auth service in the local target. It cannot restore Supabase GoTrue users if those appear later; if any Supabase Auth user, identity, MFA or other Auth data is added in future, the workflow stops and a compatible encrypted Auth-data export/restore must be implemented before another backup is accepted. A successful upload alone is still not disaster-recovery proof. T099 stays **NOT ACCEPTED** until the Auth guard passes at backup time, the isolated restore steps in section 7 pass, and RPO/RTO are measured.

## 2. Select an off-project destination

Use the owner's Cloudflare account and create the dedicated **private Cloudflare R2 bucket `shoir-ie-staging-recovery`**. The workflow rejects any other bucket name, requires the endpoint to end in `.r2.cloudflarestorage.com`, and requires R2 region `auto`.

Create a private bucket dedicated to Shoir-IE staging recovery. Do not use a public bucket. Enable the provider's encryption-at-rest and access logging where available. Set an owner-approved retention/lifecycle policy and protect backups from accidental overwrite/deletion. Confirm the bucket is in a region and legal jurisdiction approved by the data owner.

Create an R2 API token with **Object Read & Write** permission and apply it to **only** `shoir-ie-staging-recovery`. The workflow needs list/read/write access to its recovery prefix; it does not intentionally delete backups. Do not use an account-wide administrative key.

Record the account's HTTPS R2 endpoint from the Cloudflare dashboard and use region `auto`. Do not guess or copy a placeholder literally.

## 3. Create the encryption material

On a trusted computer, install the official `age` utility and generate **two independent age key pairs**:

```bash
age-keygen -o shoir-staging-offline-identity.txt
age-keygen -o shoir-staging-restore-runner-identity.txt
```

Each command writes a private identity file and prints a different `age1...` public recipient.

- **Offline recovery key:** keep `shoir-staging-offline-identity.txt` and its private identity on encrypted offline media under the recovery owner's custody. Make a second offline copy in a separate secure location. Its private key must never be uploaded to GitHub, R2, source control, workflow artifacts, or chat. The export workflow receives only this key's public recipient.
- **Restore-runner key:** the second key is a distinct automation identity used only by the protected isolated-restore workflow. Its public recipient is used by the export workflow; its private identity is stored as the protected Environment secret `SHOIR_BACKUP_AGE_RESTORE_IDENTITY`. This key is separate from the offline master recovery key and can be rotated/revoked without losing the offline recovery path.

The export encrypts each database archive for **both recipients**. This gives the recovery owner an offline decrypt path independent of GitHub, while allowing the ephemeral restore runner to decrypt its own copy. Never substitute the offline private identity for the restore-runner identity.

Generate two different random rclone crypt passwords (at least 32 characters each). Store them in the protected Environment and keep independent secure recovery copies under the authorized recovery owner's custody. They are needed to decrypt Storage objects later. Do not use a human password or reuse another service's password.

## 4. Configure the staging source credentials

### Database connection

In Supabase Dashboard for the staging project only, open **Database → Connect** and obtain either:

- the direct database connection URI (host `db.hfhrosthswcybccepmak.supabase.co`, username `postgres`), or
- the **Session Pooler** connection URI (host ending `.pooler.supabase.com`, username `postgres.hfhrosthswcybccepmak`).

Use the database named `postgres` and ensure the URI includes `sslmode=require`. The connection URI contains the database password: treat the entire URI as a secret. If the free project's direct host is unreachable from GitHub-hosted runners, use the Session Pooler URI shown by the Supabase dashboard. Do not use the Transaction Pooler for this dump.

### Storage S3 access

In the staging project, open **Storage → Configuration → S3** (the menu may be shown as **Storage → S3 Configuration**). Enable the S3 protocol if it is not already enabled, then generate an access-key pair.

**Important:** Supabase S3 access keys provide full operations across Storage buckets and bypass Storage RLS. They are high-privilege server credentials. Store them only as the GitHub Environment secrets listed below. Never use them in the Streamlit app or a browser.

## 5. Configure the protected GitHub Environment

In GitHub repository `MSJ1708/shoir-ie`:

1. Open **Settings → Environments** and create `staging-recovery`.
2. Add at least one required reviewer (an authorized repository administrator/recovery owner) before deployments are allowed.
3. Restrict deployment branches to **only** `staging-e2e-20261019`. Do not allow feature branches, `main`, or production-release branches for this staging backup job.
4. Add these as **Environment secrets**, not repository-wide secrets:

| Secret | Contents |
|---|---|
| `SHOIR_STAGING_DB_URL` | Staging PostgreSQL connection URI with `sslmode=require` |
| `SHOIR_STAGING_STORAGE_S3_ACCESS_KEY_ID` | Staging Supabase Storage S3 access key ID |
| `SHOIR_STAGING_STORAGE_S3_SECRET_ACCESS_KEY` | Staging Supabase Storage S3 secret key |
| `SHOIR_RECOVERY_S3_ENDPOINT` | HTTPS endpoint of the separate recovery provider |
| `SHOIR_RECOVERY_S3_REGION` | Exactly `auto` for Cloudflare R2 |
| `SHOIR_RECOVERY_S3_BUCKET` | Exactly `shoir-ie-staging-recovery` |
| `SHOIR_RECOVERY_S3_ACCESS_KEY_ID` | Restricted destination key ID |
| `SHOIR_RECOVERY_S3_SECRET_ACCESS_KEY` | Restricted destination secret |
| `SHOIR_BACKUP_AGE_RECIPIENT` | Public `age1...` recipient from the offline recovery key; public value only |
| `SHOIR_BACKUP_AGE_RESTORE_RECIPIENT` | Public `age1...` recipient from the distinct restore-runner key |
| `SHOIR_BACKUP_RCLONE_CRYPT_PASSWORD` | First random rclone crypt password |
| `SHOIR_BACKUP_RCLONE_CRYPT_PASSWORD2` | Different second random rclone crypt password |
| `SHOIR_BACKUP_AGE_RESTORE_IDENTITY` | Private identity for the separate restore-runner key only; **never** put the offline recovery identity here |

Do not add a Supabase service-role API key as a secret for the export workflow. The export uses the DB URL and dedicated Storage S3 credentials; its source target is hard-pinned to staging. The local restore workflow generates its own temporary local service-role key from the ephemeral Supabase stack.

## 6. Run one staging backup export

After the environment secrets and bucket have been configured, and after PR #236 has been merged into `staging-e2e-20261019`:

1. Create or update a file named `.github/backup-triggers/staging-recovery.txt` in a small pull request targeting **only** `staging-e2e-20261019`. Put a unique UTC timestamp and change reference in the file. Do not change this marker on `main`.
2. Merge that trigger PR only after the active staging ruleset is satisfied. The resulting push to the staging branch, which changes this exact marker path, launches **Staging Encrypted Backup Export**. This is intentionally explicit and auditable; ordinary staging pushes do not start a backup.
3. In the Actions run, verify the event is `push`, the branch is `staging-e2e-20261019`, and the job references the protected `staging-recovery` Environment. Approve the Environment gate as the authorized recovery operator.
4. Wait for the workflow to complete. A failed or cancelled run is not a backup. If configuration validation fails, fix the named missing/invalid setting and create a new marker change through a staging-only PR; do not rerun by changing production.
5. Inspect the redacted `backup-manifest.json` and archive SHA-256 artifact. Confirm the expected bucket count and Storage object metadata count (re-inventory at run time; the previous point-in-time inventory found two private buckets and one payment-proof object).
6. In the off-project provider console, confirm the encrypted database archive and encrypted Storage prefix exist. Do not open or download the raw payment-proof object into chat or a public artifact.

The backup destination uses a unique run prefix `shoir-ie/staging/<workflow-run-id>-<attempt>`; do not overwrite a previous recovery point. The encrypted database archive can be decrypted using either the owner's offline recovery private identity or the separate restore-runner identity. The workflow's GitHub artifact is only short-retention evidence, not the backup itself.

## 7. Isolated local Supabase restore rehearsal

The second workflow is `.github/workflows/staging-restore-rehearsal.yml`. It uses a **fresh ephemeral local Supabase stack on a GitHub-hosted runner**; it does not create a third hosted Supabase project, does not connect to the live staging or production database, and does not incur a new Supabase project charge. The restore utility explicitly rejects any database URL other than `127.0.0.1`/`localhost:54322` and any API URL other than `127.0.0.1`/`localhost:54321`.

After a real backup export has succeeded and its run prefix has been confirmed in R2:

1. Create or update `.github/restore-triggers/staging-recovery.txt` through a separate PR targeting only `staging-e2e-20261019`. The file must contain the exact backup prefix, for example `backup_prefix=shoir-ie/staging/123456789-1`. Replace the example with the actual successful backup run ID and attempt; never guess it.
2. Merge that trigger PR only after the active staging ruleset is satisfied. The staging push to this exact file launches **Staging Encrypted Backup Restore Rehearsal**. Confirm its branch, event and protected Environment before approving the Environment gate.
3. The workflow downloads the encrypted database archive and encrypted Storage tree from the exact R2 prefix, verifies the downloaded SHA-256 checksum against both the checksum file and backup manifest, and decrypts within the ephemeral runner using only `SHOIR_BACKUP_AGE_RESTORE_IDENTITY`. The separate offline private recovery identity is never exposed to the runner. It checks the encrypted migration ledger against the checked-out repository before restoring roles/schema/data into a clean local PostgreSQL 17 stack. The current staging database ledger contains 24 applied migrations; a missing, extra, duplicate or incorrectly named migration causes the rehearsal to fail.
4. It restores bucket metadata and policies, uploads each decrypted Storage object to local Supabase Storage, then downloads each object again and compares SHA-256 and byte length. It compares every application table's restored row count and the database security contract (RLS-enabled tables, policies, constraints, functions/procedures and table/routine grants) with the source-time measurements in the encrypted bundle.
5. It creates a synthetic local GoTrue/Auth user, signs it in, deletes it, and confirms no test GoTrue user remains. Separately, it creates a random synthetic **Shoir-IE custom account** in the restored `public.shoir_accounts` table using the same PBKDF2-SHA256 password-hash format, then calls the actual `shoir-persistence` Edge Function served by the local Supabase stack. It verifies custom account login, live session entitlement, workspace save, workspace load and JSON round-trip, logout revocation, denial of the revoked token, and removal of all synthetic account/session/workspace/pending-credential/login-throttle rows. No real or protected Shoir-IE account is used or modified.
6. The restore timer starts at the beginning of the GitHub Actions job, before archive download, decryption, local-stack startup or import. The workflow emits redacted evidence JSON containing the restore contract, hash-verification totals, migration-ledger match, custom login/workspace/logout results, cleanup status, measured RPO and end-to-end verified-restore RTO; uploads that evidence artifact; and destroys the ephemeral local Supabase stack and local Edge Function process. It never uploads the decrypted database, object bytes, age identity, passwords, bearer tokens or service-role key.

This workflow is implemented but **has not yet run against a real R2 backup**. A successful local rehearsal would demonstrate recovery of the exported custom Shoir-IE application database/account store, the tested custom session/workspace path, Storage contents and local Supabase Auth service availability. It is not a complete hosted-project clone and does not recover Supabase-managed settings or any future nonempty GoTrue/Auth user data; it must not be described more broadly.

T099 remains **NOT ACCEPTED** until the owner configures the R2 bucket/token and protected Environment secrets, the export workflow passes, this exact-prefix isolated restore workflow passes, RPO/RTO are recorded, and the recovery evidence is reviewed.

## 8. Current staging baseline and outstanding owner actions

The latest read-only inventory measured a roughly 14 MB PostgreSQL database, 29 application tables, two private Storage buckets, one Storage object and one Storage policy. The single object was 26,844 bytes according to source metadata. This is a point-in-time inventory, not the backup itself; re-inventory when the backup actually runs.

The following still require owner actions or account permissions:

- create the private Cloudflare R2 bucket `shoir-ie-staging-recovery` and a bucket-scoped Object Read & Write token;
- add the 12 protected export/restore configuration values to GitHub Environment `staging-recovery`, including the two public age recipients and the separate restore-runner private identity; keep the offline private recovery identity completely outside GitHub;
- make the authorized staging-only ruleset change or obtain the real independent approval required by the active ruleset;
- merge the reviewed PR to staging, create the export marker after setup, verify the actual backup, then create the restore marker using that exact run prefix;
- review the measured RPO/RTO and restore evidence.

No R2 bucket, Cloudflare token, GitHub Environment secret, ruleset, staging deployment, backup or restore run has been created by this runbook work. Production `main` and the production Supabase project remain outside scope.
