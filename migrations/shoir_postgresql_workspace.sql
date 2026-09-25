-- Add durable per-user workspace storage.
-- Run once if the original account migration was already applied.

CREATE TABLE IF NOT EXISTS shoir_workspace_states (
    username_lc TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shoir_workspace_updated
    ON shoir_workspace_states(updated_at DESC);
