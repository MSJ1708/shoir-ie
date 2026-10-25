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


-- Beta legal-consent and referral attribution additions (2026-10-21).
ALTER TABLE shoir_subscription_requests
    ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS terms_version TEXT,
    ADD COLUMN IF NOT EXISTS privacy_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS refund_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS cookie_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;

UPDATE shoir_accounts
   SET affiliate_code = 'SHR-' ||
       UPPER(SUBSTRING(REPLACE(gen_random_uuid()::text, '-', '') FROM 1 FOR 10)),
       updated_at = NOW()
 WHERE affiliate_code IS NULL
    OR BTRIM(affiliate_code) = ''
    OR affiliate_code ILIKE 'AFF-%-15';

WITH ranked AS (
    SELECT username_lc,
           ROW_NUMBER() OVER (
               PARTITION BY LOWER(affiliate_code)
               ORDER BY created_at, username_lc
           ) AS duplicate_rank
      FROM shoir_accounts
     WHERE affiliate_code IS NOT NULL AND BTRIM(affiliate_code) <> ''
)
UPDATE shoir_accounts AS account
   SET affiliate_code = 'SHR-' ||
       UPPER(SUBSTRING(REPLACE(gen_random_uuid()::text, '-', '') FROM 1 FOR 10)),
       updated_at = NOW()
  FROM ranked
 WHERE ranked.username_lc = account.username_lc
   AND ranked.duplicate_rank > 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_shoir_accounts_affiliate_code_unique
    ON shoir_accounts (LOWER(affiliate_code))
    WHERE affiliate_code IS NOT NULL AND BTRIM(affiliate_code) <> '';

CREATE TABLE IF NOT EXISTS shoir_referrals (
    id BIGSERIAL PRIMARY KEY,
    referrer_username_lc TEXT NOT NULL
        REFERENCES shoir_accounts(username_lc) ON DELETE RESTRICT,
    referred_username_lc TEXT NOT NULL UNIQUE,
    referral_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending', 'Qualified', 'Declined')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    qualified_at TIMESTAMPTZ,
    CONSTRAINT shoir_referrals_no_self_referral
        CHECK (referrer_username_lc <> referred_username_lc)
);
CREATE INDEX IF NOT EXISTS idx_shoir_referrals_referrer_status
    ON shoir_referrals(referrer_username_lc, status);
