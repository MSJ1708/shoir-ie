
create schema if not exists shoir_internal;

create table if not exists shoir_internal.artifacts (
  artifact_id text primary key,
  workspace_id text not null,
  artifact_type text not null,
  name text not null,
  payload_json text not null,
  content_hash text,
  owner text,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
create index if not exists idx_shoir_internal_artifacts_ws on shoir_internal.artifacts(workspace_id, artifact_type, updated_at desc);

create table if not exists shoir_internal.twin_assets (
  workspace_id text not null,
  asset_id text not null,
  state_json text not null,
  source text,
  updated_at timestamptz not null,
  primary key(workspace_id, asset_id)
);
create table if not exists shoir_internal.twin_snapshots (
  snapshot_id text primary key,
  workspace_id text not null,
  scenario_name text not null,
  state_json text not null,
  created_by text,
  created_at timestamptz not null
);
create table if not exists shoir_internal.twin_scenarios (
  scenario_id text primary key,
  workspace_id text not null,
  name text not null,
  parent_name text,
  parameters_json text not null,
  notes text,
  created_by text,
  created_at timestamptz not null,
  unique(workspace_id, name)
);

create table if not exists shoir_internal.connector_health (
  connector_id text primary key,
  workspace_id text not null,
  name text not null,
  system_type text not null,
  protocol text not null,
  endpoint text,
  status text not null,
  latency_ms double precision,
  detail text,
  checked_at timestamptz not null,
  checked_by text
);
create index if not exists idx_shoir_internal_connector_ws on shoir_internal.connector_health(workspace_id, checked_at desc);

create table if not exists shoir_internal.jobs (
  job_id text primary key,
  workspace_id text not null,
  module text not null,
  job_type text not null,
  status text not null,
  progress double precision not null default 0,
  message text,
  payload_json text,
  result_json text,
  attempts integer not null default 0,
  cancel_requested boolean not null default false,
  pause_requested boolean not null default false,
  created_at timestamptz not null,
  started_at timestamptz,
  finished_at timestamptz,
  updated_at timestamptz not null
);
create index if not exists idx_shoir_internal_jobs_ws on shoir_internal.jobs(workspace_id, updated_at desc);

create table if not exists shoir_internal.collaboration (
  item_id text primary key,
  workspace_id text not null,
  item_type text not null,
  subject text,
  body text,
  actor text not null,
  assignee text,
  reviewer text,
  status text not null default 'Open',
  created_at timestamptz not null,
  updated_at timestamptz not null
);
create index if not exists idx_shoir_internal_collab_ws on shoir_internal.collaboration(workspace_id, updated_at desc);

create table if not exists shoir_internal.knowledge (
  doc_id text primary key,
  workspace_id text not null,
  name text not null,
  content text not null,
  source_type text,
  tags_json text,
  sha256 text not null,
  created_by text,
  created_at timestamptz not null,
  updated_at timestamptz not null
);
create index if not exists idx_shoir_internal_knowledge_ws on shoir_internal.knowledge(workspace_id, updated_at desc);

create table if not exists shoir_internal.monitoring_rules (
  rule_id text primary key,
  workspace_id text not null,
  name text not null,
  metric text not null,
  operator text not null,
  threshold double precision not null,
  severity text not null,
  enabled boolean not null default true,
  created_at timestamptz not null
);
create table if not exists shoir_internal.monitoring_events (
  event_id text primary key,
  workspace_id text not null,
  rule_id text,
  asset_id text,
  metric text not null,
  value double precision not null,
  status text not null,
  message text,
  created_at timestamptz not null
);

create table if not exists shoir_internal.report_provenance (
  report_id text primary key,
  workspace_id text not null,
  module text not null,
  format text not null,
  filename text not null,
  source_hash text,
  figure_hashes_json text,
  artifact_ids_json text,
  created_by text,
  created_at timestamptz not null
);

create table if not exists shoir_internal.security (
  workspace_id text primary key,
  require_mfa boolean not null default false,
  oidc_provider text,
  oidc_enabled boolean not null default false,
  retention_days integer not null default 365,
  updated_by text,
  updated_at timestamptz not null
);

revoke all on schema shoir_internal from anon, authenticated;
revoke all on all tables in schema shoir_internal from anon, authenticated;
