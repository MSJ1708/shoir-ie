# Durable Shoir-IE accounts

Shoir-IE uses managed PostgreSQL (Supabase works) as the authoritative account store when [database].url, SUPABASE_DB_URL, or DATABASE_URL is configured.

In Streamlit Cloud, add:

```toml
[database]
url = "postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres?sslmode=require"
```

Apply migrations/shoir_postgresql.sql once to that database.

The application then migrates local-only accounts, hydrates durable accounts after restarts, preserves passwords/profiles/workspaces, records an explicit subscription expiry timestamp, blocks paid accounts after 30 days, preserves expired accounts rather than deleting them, and supports renewal requests that add another 30 days after administrator approval.

The master admin sho is exempt from the paid subscription expiry rule.

Accounts that were already lost from a previous non-persistent deployment cannot be reconstructed by code alone unless a backup exists.
