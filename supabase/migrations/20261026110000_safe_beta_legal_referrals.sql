-- SAFE REPLACEMENT: legal acceptance + referral attribution schema.
-- This preserves every existing affiliate_code and updated_at value.
-- RELEASE GATE: main also tracks legacy migrations 20261021130000, 20261022110000,
-- and 20261023130000. A production db push WITHOUT prior, reviewed migration-ledger
-- reconciliation would execute those older files and is prohibited. Follow
-- docs/REFERRAL_MIGRATION_RECOVERY_PLAN.md; prove the isolated rehearsal and obtain
-- explicit owner approval before any migration runner is used against production.
-- Safe replacement schema migration for beta legal acceptance and referral attribution.
-- IMPORTANT: The earlier 20261021130000_shoir_beta_legal_referrals.sql migration
-- has already run in staging and contains data-rewriting UPDATE statements. For a
-- fresh environment, do NOT execute that historical file as part of production
-- rollout. Follow the reviewed migration manifest: reconcile migration history
-- under an approved maintenance window, then apply this additive migration.
-- This migration deliberately preserves all existing affiliate_code and updated_at
-- values. It does not generate rewards, discounts, commissions, or payment entitlements.

BEGIN;

ALTER TABLE public.shoir_subscription_requests
    ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS terms_version TEXT,
    ADD COLUMN IF NOT EXISTS privacy_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS refund_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS cookie_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS public.shoir_referrals (
    id BIGSERIAL PRIMARY KEY,
    referrer_username_lc TEXT NOT NULL
        REFERENCES public.shoir_accounts(username_lc) ON DELETE RESTRICT,
    -- The referred account may not exist until a pending registration is approved.
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
    ON public.shoir_referrals(referrer_username_lc, status);
CREATE INDEX IF NOT EXISTS idx_shoir_referrals_created_at
    ON public.shoir_referrals(created_at DESC);

-- Enforce case-insensitive uniqueness for populated codes without rewriting
-- existing identifiers or timestamps. The partial predicate intentionally ignores
-- null/blank legacy rows. If duplicates appear after preflight, this index creation
-- fails transactionally rather than silently rewriting account data.
CREATE UNIQUE INDEX IF NOT EXISTS idx_shoir_accounts_affiliate_code_trimmed_unique
    ON public.shoir_accounts (LOWER(BTRIM(affiliate_code)))
    WHERE affiliate_code IS NOT NULL AND BTRIM(affiliate_code) <> '';

ALTER TABLE public.shoir_referrals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.shoir_referrals FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.shoir_referrals TO service_role;
REVOKE ALL ON SEQUENCE public.shoir_referrals_id_seq FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE public.shoir_referrals_id_seq TO service_role;

COMMIT;
