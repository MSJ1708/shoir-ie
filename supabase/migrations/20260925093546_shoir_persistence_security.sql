CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS shoir_pending_credentials (
    username_lc TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS shoir_sessions (
    token_hash TEXT PRIMARY KEY,
    username_lc TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shoir_sessions_user ON shoir_sessions(username_lc);
CREATE INDEX IF NOT EXISTS idx_shoir_sessions_expiry ON shoir_sessions(expires_at);

ALTER TABLE shoir_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_subscription_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_workspace_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_pending_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_sessions ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION shoir_cleanup_sessions()
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$ DELETE FROM shoir_sessions WHERE expires_at <= NOW(); $$;
