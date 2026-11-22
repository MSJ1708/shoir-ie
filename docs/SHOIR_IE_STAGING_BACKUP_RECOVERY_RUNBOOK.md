# Shoir-IE staging backup export setup and acceptance

**Status:** export workflow prepared; **T099 remains NOT ACCEPTED** until a real isolated restore succeeds and RPO/RTO are measured.

This guide is for the staging project only:

- Project: `shoir-ie-staging-2026-10-19`
- Project reference: `hfhrosthswcybccepmak`
- Database region: Frankfurt / `eu-central-1`
- Storage source: the staging project's S3-compatible Storage endpoint

Never point this procedure at production project `gcsamrdaeraxieaagsta`. Never place credentials in chat, source code, issues, PR comments, workflow inputs or artifacts.

## 1. What the workflow does

The manual GitHub Actions workflow is:

`.github/workflows/staging-backup-recovery.yml`

It is deliberately **manual only** and requires the protected GitHub Environment named `staging-recovery`.

When all required environment secrets are configured, it:

1. Verifies the PostgreSQL URL is for the exact staging database (direct Supabase host, or a Supabase session-pooler host with username `postgres.hfhrosthswcybccepmak`) and requires TLS.
2. Exports database roles, the `public` and `shoir_internal` schemas and their data.
3. Exports Storage bucket/object metadata and Storage policies separately.
4. Encrypts the database bundle using an `age` public recipient before upload.
5. Copies **every** staging Storage bucket's object bytes to an off-Supabase S3-compatible destination through an encrypted `rclone crypt` remote.
6. Checks the remote Storage copy against the live source and checks the uploaded encrypted database archive.
7. Uploads only a redacted manifest and archive checksum to the short-retention GitHub artifact. Raw database data, Storage object bytes and encryption material are not uploaded as GitHub artifacts.

The workflow does **not** yet restore the database or Storage into a separate Supabase project. A successful run proves that the encrypted backup was uploaded and checked against its source; it does not prove disaster recovery. T099 stays unaccepted until the isolated restore steps in section 7 pass.

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
3. Restrict deployment branches to the reviewed staging backup workflow branch and, after approval/merge, the dedicated staging branch only. Do not allow `main` or production-release branches for this staging backup job.
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

After the environment has been configured and independently reviewed:

1. Open **Actions → Staging Encrypted Backup Export**.
2. Choose the reviewed staging backup workflow branch, then select **Run workflow** once.
3. Confirm the environment approval request in GitHub as an authorized recovery operator.
4. Wait for the workflow to complete. A failed or cancelled run is not a backup.
5. Inspect the redacted `backup-manifest.json` and archive SHA-256 artifact. Confirm the expected bucket count and Storage object metadata count (the current live inventory has two private buckets and one payment-proof object).
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
7. Point a disposable Streamlit instance at the isolated restore and test login, workspace load/save, dataset download, private payment-proof access and exports.
8. Record recovery start/end time, recovery point timestamp, achieved RPO/RTO, failures and rollback. Obtain independent infrastructure/security approval.

The current workflow does **not** perform this isolated restore automatically. Do not claim T099 accepted until the complete test is documented and independently reviewed. Do not create a new Supabase project or incur a charge without the owner's explicit approval.

## 8. Current staging baseline and outstanding owner decisions

The last read-only inventory measured a roughly 14 MB PostgreSQL database. It found two private buckets: `shoir-industrial-datasets` (0 objects) and `subscription-payment-proofs` (one JPEG object, 26,844 bytes according to object metadata). This is a point-in-time inventory, not the backup itself; re-inventory when the backup actually runs.

The following still require owner decisions or provider access:

- choose the off-project S3-compatible provider/account, region and retention;
- generate the destination credentials and encryption keys and store them in the `staging-recovery` GitHub Environment;
- authorize an isolated restore target and its cost, if any;
- approve measurable RPO/RTO targets and the recovery operator.

No backup has been run by this guide. No project, plan, schema, secret, bucket, account, or production resource has been changed by writing this procedure.
