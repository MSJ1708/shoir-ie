
CREATE TABLE IF NOT EXISTS public.shoir_platform_meta (
    key text PRIMARY KEY,
    value_json jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.shoir_platform_records (
    record_id text PRIMARY KEY,
    workspace_key text NOT NULL DEFAULT 'default',
    record_type text NOT NULL,
    entity_key text NOT NULL,
    payload_json jsonb NOT NULL,
    content_hash text NOT NULL,
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_key, record_type, entity_key)
);

CREATE INDEX IF NOT EXISTS idx_shoir_platform_records_type
    ON public.shoir_platform_records(workspace_key, record_type, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_shoir_platform_records_hash
    ON public.shoir_platform_records(content_hash);

CREATE TABLE IF NOT EXISTS public.shoir_platform_events (
    event_id text PRIMARY KEY,
    workspace_key text NOT NULL DEFAULT 'default',
    event_type text NOT NULL,
    actor text NOT NULL DEFAULT 'system',
    entity_key text,
    payload_json jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shoir_platform_events
    ON public.shoir_platform_events(workspace_key, event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS public.shoir_platform_artifacts (
    artifact_id text PRIMARY KEY,
    workspace_key text NOT NULL DEFAULT 'default',
    artifact_type text NOT NULL,
    storage_key text NOT NULL,
    content_hash text NOT NULL,
    mime_type text,
    byte_size bigint NOT NULL DEFAULT 0 CHECK (byte_size >= 0),
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_key, artifact_type, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_shoir_platform_artifacts
    ON public.shoir_platform_artifacts(workspace_key, artifact_type, created_at DESC);

ALTER TABLE public.shoir_platform_meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shoir_platform_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shoir_platform_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shoir_platform_artifacts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.shoir_platform_meta FROM anon, authenticated;
REVOKE ALL ON TABLE public.shoir_platform_records FROM anon, authenticated;
REVOKE ALL ON TABLE public.shoir_platform_events FROM anon, authenticated;
REVOKE ALL ON TABLE public.shoir_platform_artifacts FROM anon, authenticated;
