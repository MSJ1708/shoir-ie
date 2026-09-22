# Shoir-IE durable accounts and 30-day subscriptions

Shoir-IE now supports a managed PostgreSQL database (including Supabase) as the authoritative account store.

## Streamlit Cloud configuration

In the app's **Secrets** settings, add the Supabase PostgreSQL connection string under one of these forms:

```toml
[database]
url = "postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres?sslmode=require"
```

or:

```toml
SUPABASE_DB_URL = "postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres?sslmode=require"
```

Do not commit the connection string to GitHub.

Then apply `migrations/shoir_postgresql.sql` to the same database once. The application will also create the required schema automatically when it first connects.

## What this fixes

The local SQLite file remains a development/cache layer, but the managed PostgreSQL database becomes the source of truth when configured. Account creation/approval, subscription expiry, renewal requests, and account metadata survive Streamlit app restarts and rebuilds.

Paid accounts expire exactly 30 days after activation/renewal. Expiration blocks login but does not delete the account or workspace. A renewal request can then be submitted and approved, extending the subscription by another 30 days.

The master administrator account is exempt from the paid subscription expiry rule.

## Important recovery limitation

Accounts that were already lost from a non-persistent Streamlit/SQLite deployment cannot be reconstructed from this code alone unless a copy exists in a backup or other database. Once the managed database is connected, newly created/approved accounts are durable across refreshes and app restarts.
