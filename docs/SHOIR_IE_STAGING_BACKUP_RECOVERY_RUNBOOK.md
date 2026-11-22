# Shoir-IE staging backup export setup and acceptance

**Status:** export workflow prepared; **T099 remains NOT ACCEPTED** until a real isolated restore succeeds and RPO/RTO are measured.

This guide is for the staging project only:

- Project: `shoir-ie-staging-2026-10-19`
- Project reference: `hfhrosthswcybccepmak`
- Database region: Frankfurt / `eu-central-1`
- Storage source: the staging project's S3-compatible Storage endpoint

Never point this procedure at production project `gcsamrdaeraxieaagsta`. Never place credentials in chat, source code, issues, PR comments, workflow inputs or artifacts.

## 1. What the workflow does

The GitHub Actions workflow is:

`.github/workflows/staging-backup-recovery.yml`

It requires the protected GitHub Environment named `staging-recovery`. To preserve the production `main` branch, the supported owner-trigger for the staging-only workflow is a deliberate change to `.github/backup-triggers/staging-recovery.txt` on `staging-e2e-20261019`. That `push` trigger is available once the workflow file has been merged into the staging branch. The optional `workflow_dispatch` trigger is only exposed by GitHub when the workflow file also exists on the repository default branch; this runbook does not authorize adding it to `main`.

When all required environment secrets are configured, it:

1. Verifies the PostgreSQL URL is for the exact staging database (direct Supabase host, or a Supabase session-pooler host with username `postgres.hfhrosthswcybccepmak`) and requires TLS.
2. Exports database roles, the `public` and `shoir_internal` schemas and their data.
3. Exports Storage bucket/object metadata and Storage policies separately.
4. Encrypts the database bundle using an `age` public recipient before upload.
5. Copies **every** staging Storage bucket's object bytes to an off-Supabase S3-compatible destination through an encrypted `rclone crypt` remote.
6. Checks the remote Storage copy against the live source and checks the uploaded encrypted database archive.
7. Uploads only a redacted manifest and archive checksum to the short-retention GitHub artifact. Raw database data, Storage object bytes and encryption material are not uploaded as GitHub artifacts.

The workflow does **not** yet restore the database or Storage into a separate Supabase project. There is also a material scope gap: Supabase CLI `db dump` excludes Supabase-managed schemas such as `auth` and `storage`; this workflow explicitly dumps only `public` and `shoir_internal`. Storage metadata and object bytes are copied separately, but **Auth user records are not exported**. The current bundle therefore does not preserve `auth.users`, `auth.identities`, password hashes, or MFA/authentication records. It cannot prove recovery of existing Shoir-IE sign-in identities.

A successful run would prove only that the encrypted custom-database bundle and Storage objects were uploaded and checked against their source. It does not prove full application disaster recovery. T099 stays **NOT ACCEPTED** until the Auth data scope is resolved through a compatible, encrypted export/restore method, the isolated restore steps in section 7 pass, and RPO/RTO are measured. Do not treat newly created test users on the restore target as proof that existing user identities were recovered.

## 2. Select an off-project destination

Choose an S3-compatible provider that is separate from the Supabase staging project and preferably a separate account/failure domain. Supported examples include AWS S3 or Cloudflare R2.

Create a private bucket dedicated to Shoir-IE staging recovery. Do not use a public bucket. Enable the provider's encryption-at-rest and access logging where available. Set an owner-approved retention/lifecycle policy and protect backups from accidental overwrite/deletion. Confirm the bucket is in a region and legal jurisdiction approved by the data owner.

Create credentials restricted to this recovery bucket. The workflow needs list/read/write access to its recovery prefix; it does not intentionally delete backups. Do not use a root account or a general administrator key.

Record the provider's HTTPS S3 endpoint and region. For Cloudflare R2, the endpoint is the account's R2 endpoint and the region is normally `auto`. For AWS S3, use the endpoint/region supplied by AWS. Do not guess or copy a placeholder literally.

## 3. Create the encryption material

On a trusted computer, install the official `age` utility and generate a key pair:

```bash
age-keygen -o shoir-staging-backup-identity.txt
```

The command writes a private identity file and prints an `age1...` public recipient. Keep the private identity file offline/in an approved secret manager with a recovery copy held by the authorized recovery owner. The backup workflow only needs the **public recipient**; never put the private identity into the export workflow or source code.

Generate two different random rclone crypt passwords (at least 32 characters each). Keep them in the same approved secret manager as the recovery identity, with separate access control. These passwords are needed to decrypt Storage objects later. Do not use a human password or reuse another service's password.

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
| `SHOIR_RECOVERY_S3_REGION` | Provider region |
| `SHOIR_RECOVERY_S3_BUCKET` | Private destination bucket name |
| `SHOIR_RECOVERY_S3_ACCESS_KEY_ID` | Restricted destination key ID |
| `SHOIR_RECOVERY_S3_SECRET_ACCESS_KEY` | Restricted destination secret |
| `SHOIR_BACKUP_AGE_RECIPIENT` | The public `age1...` recipient only |
| `SHOIR_BACKUP_RCLONE_CRYPT_PASSWORD` | First random rclone crypt password |
| `SHOIR_BACKUP_RCLONE_CRYPT_PASSWORD2` | Different second random rclone crypt password |

Do not add a Supabase service-role API key. The workflow uses the DB URL and dedicated Storage S3 credentials; its target check is hard-pinned to the staging database.

## 6. Run one staging backup export

After the environment secrets and bucket have been configured, and after PR #236 has been merged into `staging-e2e-20261019`:

1. Create or update a file named `.github/backup-triggers/staging-recovery.txt` in a small pull request targeting **only** `staging-e2e-20261019`. Put a unique UTC timestamp and change reference in the file. Do not change this marker on `main`.
2. Merge that trigger PR only after the active staging ruleset is satisfied. The resulting push to the staging branch, which changes this exact marker path, launches **Staging Encrypted Backup Export**. This is intentionally explicit and auditable; ordinary staging pushes do not start a backup.
3. In the Actions run, verify the event is `push`, the branch is `staging-e2e-20261019`, and the job references the protected `staging-recovery` Environment. Approve the Environment gate as the authorized recovery operator.
4. Wait for the workflow to complete. A failed or cancelled run is not a backup. If configuration validation fails, fix the named missing/invalid setting and create a new marker change through a staging-only PR; do not rerun by changing production.
5. Inspect the redacted `backup-manifest.json` and archive SHA-256 artifact. Confirm the expected bucket count and Storage object metadata count (re-inventory at run time; the previous point-in-time inventory found two private buckets and one payment-proof object).
6. In the off-project provider console, confirm the encrypted database archive and encrypted Storage prefix exist. Do not open or download the raw payment-proof object into chat or a public artifact.

The backup destination should have a unique run prefix; do not overwrite a previous recovery point. The workflow's GitHub artifact is only short-retention evidence, not the backup itself.

## 7. Required isolated restore before T099 can pass

The restore operator must provision a **separate disposable Supabase project** or a supported isolated Supabase restore target. It must not be the production or live staging project and must have no production integration credentials.

The restore procedure must:

1. Retrieve the encrypted database bundle and encrypted Storage prefix from the off-project destination.
2. Verify the database archive SHA-256 before decrypting it with the offline `age` identity.
3. Restore roles, schema and data into the isolated target using the matching PostgreSQL/Supabase versions; reconcile Supabase-managed schemas and Storage bucket/object metadata using supported Supabase restore methods, not unsupported direct filesystem edits.
4. Decrypt the Storage prefix using the rclone crypt passwords and restore all bucket contents into the isolated Storage service.
5. Compare bucket/object counts, paths, file sizes and SHA-256 hashes against the source-time manifest. Verify private bucket policies and object access.
6. Verify migration versions, table counts, constraints, RLS, grants, RPC execute rights, critical subscription/account/workspace rows and tenant isolation.
7. Before claiming identity recovery, implement and validate a separate encrypted Auth-data export/restoration path compatible with the source and target Supabase Auth versions. Preserve required user/identity records while invalidating old sessions and refresh tokens. Until that exists, only create fresh synthetic disposable users in the isolated target; a successful fresh-user login is not proof that the source Auth users were restored.
8. Point a disposable Streamlit instance at the isolated restore and test fresh-user login, workspace load/save, dataset download, private payment-proof access and exports. Test existing-account recovery only after the Auth records have been restored through the supported path.
9. Record recovery start/end time, recovery point timestamp, achieved RPO/RTO, failures and rollback. Obtain independent infrastructure/security approval.

The current workflow does **not** perform this isolated restore automatically. Do not claim T099 accepted until the complete test is documented and independently reviewed. Do not create a new Supabase project or incur a charge without the owner's explicit approval.

## 8. Current staging baseline and outstanding owner decisions

The last read-only inventory measured a roughly 14 MB PostgreSQL database. It found two private buckets: `shoir-industrial-datasets` (0 objects) and `subscription-payment-proofs` (one JPEG object, 26,844 bytes according to object metadata). This is a point-in-time inventory, not the backup itself; re-inventory when the backup actually runs.

The following still require owner decisions or provider access:

- choose the off-project S3-compatible provider/account, region and retention;
- generate the destination credentials and encryption keys and store them in the `staging-recovery` GitHub Environment;
- authorize an isolated restore target and its cost, if any;
- approve measurable RPO/RTO targets and the recovery operator.

No backup has been run by this guide. No project, plan, schema, secret, bucket, account, or production resource has been changed by writing this procedure.
