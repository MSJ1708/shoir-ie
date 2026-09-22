-- Shoir-IE durable account storage (PostgreSQL / Supabase)
-- Run this once in your managed PostgreSQL database.
-- Do NOT put database credentials in GitHub.

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

CREATE INDEX IF NOT EXISTS idx_shoir_accounts_expiry
    ON shoir_accounts(subscription_expires_at);

CREATE INDEX IF NOT EXISTS idx_shoir_accounts_email
    ON shoir_accounts(email);

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

CREATE INDEX IF NOT EXISTS idx_shoir_requests_status
    ON shoir_subscription_requests(status, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_shoir_requests_user
    ON shoir_subscription_requests(username_lc, requested_at DESC);
