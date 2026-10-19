
CREATE TABLE IF NOT EXISTS public.shoir_platform_jobs (
    job_id text PRIMARY KEY,
    workspace_key text NOT NULL DEFAULT 'default',
    module text NOT NULL,
    status text NOT NULL DEFAULT 'QUEUED'
        CHECK (status IN ('QUEUED','CLAIMED','RUNNING','COMPLETED','FAILED','CANCELLED')),
    priority integer NOT NULL DEFAULT 50,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    worker_id text,
    progress double precision NOT NULL DEFAULT 0 CHECK (progress >= 0 AND progress <= 1),
    available_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shoir_platform_jobs_claim
    ON public.shoir_platform_jobs(workspace_key, status, priority DESC, available_at ASC);
CREATE INDEX IF NOT EXISTS idx_shoir_platform_jobs_updated
    ON public.shoir_platform_jobs(workspace_key, updated_at DESC);
ALTER TABLE public.shoir_platform_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.shoir_platform_jobs FROM anon, authenticated;
