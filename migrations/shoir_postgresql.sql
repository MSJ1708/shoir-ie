-- Shoir-IE durable account storage (PostgreSQL / Supabase)
-- Run once against the Supabase/PostgreSQL database used by Streamlit Cloud.

CREATE TABLE IF NOT EXISTS shoir_accounts (
    username TEXT PRIMARY KEY,
    username_lc TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT,
    tier TEXT,
    email TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    subscription_expires_at TIMESTAMPTZ NOT NULL,
    linkedin TEXT,
    github TEXT,
    about_me TEXT,
    affiliate_code TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_shoir_accounts_expiry ON shoir_accounts(subscription_expires_at);

CREATE TABLE IF NOT EXISTS shoir_subscription_requests (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    username_lc TEXT NOT NULL,
    email TEXT,
    tier TEXT,
    request_type TEXT NOT NULL DEFAULT 'New',
    payment_method TEXT,
    transaction_id TEXT,
    screenshot_path TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_shoir_requests_status ON shoir_subscription_requests(status, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_shoir_requests_user ON shoir_subscription_requests(username_lc, requested_at DESC);


-- Industrial OS platform-owned durable repository.
CREATE TABLE IF NOT EXISTS shoir_platform_meta (
    key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shoir_platform_records (
    record_id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL DEFAULT 'default',
    record_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_key, record_type, entity_key)
);
CREATE INDEX IF NOT EXISTS idx_shoir_records_type ON shoir_platform_records(workspace_key, record_type);
CREATE INDEX IF NOT EXISTS idx_shoir_records_hash ON shoir_platform_records(content_hash);

CREATE TABLE IF NOT EXISTS shoir_platform_events (
    event_id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL DEFAULT 'default',
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    entity_key TEXT,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_shoir_events ON shoir_platform_events(workspace_key, event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS shoir_platform_jobs (
    job_id TEXT PRIMARY KEY,
    workspace_key TEXT NOT NULL DEFAULT 'default',
    module TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 50,
    payload_json JSONB NOT NULL,
    result_json JSONB,
    worker_id TEXT,
    claimed_at TIMESTAMPTZ,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_shoir_jobs_queue ON shoir_platform_jobs(workspace_key,status,priority DESC,available_at,created_at);
