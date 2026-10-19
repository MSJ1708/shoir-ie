# Supabase migration source recovery and replay gate

## Why this exists

The production migration ledger contains 13 applied versions, but the Git repository previously tracked only a subset of their corresponding SQL files. This made a clean versioned replay impossible from the repository alone and hid drift until the release review.

Seven non-data-seeding migration statements have now been recovered verbatim from the production project's `supabase_migrations.schema_migrations.statements` ledger and restored under their recorded version/name. No customer table rows or account records were exported.

The historical `20260925093748_seed_shoir_admin_account` statement contained a static password hash for the protected administrator. That credential-bearing SQL is deliberately **not** copied into Git. The source file keeps the version as a documented no-op for fresh non-production replays. Initial administrator provisioning must be done separately through an approved, one-time secure bootstrap process. This does not change the already-applied production migration or mutate the existing master administrator.

## Automated checks

`tests/test_migration_source_inventory.py` checks the tracked version sequence and guards against embedding the static administrator hash.

`tests/test_full_migration_history_postgres.py` runs against the disposable local PostgreSQL integration service only. It creates and drops a separate `shoir_migration_replay_test` database, bootstraps minimal local Supabase Storage compatibility tables, applies every tracked migration in timestamp order, checks key tables/columns, RLS, private payment bucket and privileged RPC grants, and exercises registration/approval using synthetic records.

This is a clean replay in local PostgreSQL with minimal Storage compatibility shims. It is materially stronger than testing only the newest migration on a hand-built schema, but it is **not** a production-matched Supabase staging branch and does not exercise hosted Edge deployment, Supabase Auth/Storage service behavior, upgrade from a live production backup, or production rollback.

## Production boundary

Do not deploy the recovered source, the atomic subscription migration, or a new Edge Function solely because the local replay passes. Before rollout:
1. replay on an authorized isolated staging Supabase environment that matches production;
2. verify the exact migration history, RPC signatures, policies/grants and matching Edge Function;
3. test backup/recovery and authenticated flows with distinct `shoir-e2e-*` accounts;
4. verify staging and hosted app revisions;
5. obtain explicit production rollout authorization.

The protected administrator is never recreated, reset, or used by these tests.
