-- Source/replay-complete form of the staging RLS hardening migration.
-- Staging preflight (2026-11-04) confirmed all 12 tables already existed and
-- were empty. CREATE TABLE IF NOT EXISTS records the pre-existing runtime DDL
-- here so a clean local migration replay is self-contained; these statements
-- were no-ops for the already-provisioned staging tables.
CREATE SCHEMA IF NOT EXISTS shoir_internal;

CREATE TABLE IF NOT EXISTS shoir_internal.artifacts (
    artifact_id text PRIMARY KEY, workspace_id text NOT NULL, artifact_type text NOT NULL,
    name text NOT NULL, payload_json text NOT NULL, content_hash text, owner text,
    created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shoir_internal_artifacts_ws
    ON shoir_internal.artifacts(workspace_id, artifact_type, updated_at DESC);

CREATE TABLE IF NOT EXISTS shoir_internal.twin_assets (
    workspace_id text NOT NULL, asset_id text NOT NULL, state_json text NOT NULL,
    source text, updated_at timestamptz NOT NULL, PRIMARY KEY(workspace_id, asset_id)
);

CREATE TABLE IF NOT EXISTS shoir_internal.twin_snapshots (
    snapshot_id text PRIMARY KEY, workspace_id text NOT NULL, scenario_name text NOT NULL,
    state_json text NOT NULL, created_by text, created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS shoir_internal.twin_scenarios (
    scenario_id text PRIMARY KEY, workspace_id text NOT NULL, name text NOT NULL,
    parent_name text, parameters_json text NOT NULL, notes text, created_by text,
    created_at timestamptz NOT NULL, UNIQUE(workspace_id, name)
);

CREATE TABLE IF NOT EXISTS shoir_internal.connector_health (
    connector_id text PRIMARY KEY, workspace_id text NOT NULL, name text NOT NULL,
    system_type text NOT NULL, protocol text NOT NULL, endpoint text, status text NOT NULL,
    latency_ms double precision, detail text, checked_at timestamptz NOT NULL,
    checked_by text, secret_ref text
);
CREATE INDEX IF NOT EXISTS idx_shoir_internal_connector_ws
    ON shoir_internal.connector_health(workspace_id, checked_at DESC);

CREATE TABLE IF NOT EXISTS shoir_internal.jobs (
    job_id text PRIMARY KEY, workspace_id text NOT NULL, module text NOT NULL,
    job_type text NOT NULL, status text NOT NULL, progress double precision NOT NULL DEFAULT 0,
    message text, payload_json text, result_json text, attempts integer NOT NULL DEFAULT 0,
    cancel_requested boolean NOT NULL DEFAULT false, pause_requested boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL, started_at timestamptz, finished_at timestamptz,
    updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shoir_internal_jobs_ws
    ON shoir_internal.jobs(workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS shoir_internal.collaboration (
    item_id text PRIMARY KEY, workspace_id text NOT NULL, item_type text NOT NULL,
    subject text, body text, actor text NOT NULL, assignee text, reviewer text,
    status text NOT NULL DEFAULT 'Open', created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shoir_internal_collab_ws
    ON shoir_internal.collaboration(workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS shoir_internal.knowledge (
    doc_id text PRIMARY KEY, workspace_id text NOT NULL, name text NOT NULL,
    content text NOT NULL, source_type text, tags_json text, sha256 text NOT NULL,
    created_by text, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shoir_internal_knowledge_ws
    ON shoir_internal.knowledge(workspace_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS shoir_internal.monitoring_rules (
    rule_id text PRIMARY KEY, workspace_id text NOT NULL, name text NOT NULL,
    metric text NOT NULL, operator text NOT NULL, threshold double precision NOT NULL,
    severity text NOT NULL, enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS shoir_internal.monitoring_events (
    event_id text PRIMARY KEY, workspace_id text NOT NULL, rule_id text,
    asset_id text, metric text NOT NULL, value double precision NOT NULL, status text NOT NULL,
    message text, created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS shoir_internal.report_provenance (
    report_id text PRIMARY KEY, workspace_id text NOT NULL, module text NOT NULL,
    format text NOT NULL, filename text NOT NULL, source_hash text,
    figure_hashes_json text, artifact_ids_json text, created_by text,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS shoir_internal.security (
    workspace_id text PRIMARY KEY, require_mfa boolean NOT NULL DEFAULT false,
    oidc_provider text, oidc_enabled boolean NOT NULL DEFAULT false,
    retention_days integer NOT NULL DEFAULT 365, updated_by text, updated_at timestamptz NOT NULL
);

-- Canonical Digital Thread tables were created by the enterprise DDL on
-- deployments that provisioned the original runtime schema; they are not part
-- of the 12-table preflight below and are deliberately not granted by this file.

-- Defense-in-depth for tables in the private Shoir-IE internal schema.
--
-- Precondition verified on staging project hfhrosthswcybccepmak (2026-11-04):
-- * every table is owned by postgres;
-- * all 12 tables are empty;
-- * postgres is BYPASSRLS and remains the object owner;
-- * no schema/table grants exist for anon, authenticated, service_role,
--   authenticator, PUBLIC or any other non-owner role.
--
-- Enable RLS with no policies. This intentionally keeps access closed to any
-- future non-owner/non-BYPASSRLS role until a table-specific least-privilege
-- access model has been reviewed and tested. Do not add broad USING (true)
-- policies. Do not FORCE ROW LEVEL SECURITY: existing owner/service operations
-- must remain available through their privileged server-side connection.
--
-- This migration creates no grants, policies, rows, or changes to application
-- data. It only enables RLS on the existing internal tables.

REVOKE ALL ON SCHEMA shoir_internal FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA shoir_internal FROM PUBLIC, anon, authenticated;

ALTER TABLE shoir_internal.artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.twin_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.twin_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.twin_scenarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.connector_health ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.collaboration ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.monitoring_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.monitoring_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.report_provenance ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.security ENABLE ROW LEVEL SECURITY;

COMMENT ON SCHEMA shoir_internal IS
  'Private Shoir-IE internal schema. Access is restricted to explicitly privileged server-side database roles; table RLS is enabled and no application-role policies are granted by default.';
