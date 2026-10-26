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

-- Do not enforce global affiliate-code uniqueness until a separate read-only
-- duplicate audit and explicitly approved remediation are complete. Preserve all
-- existing codes and timestamps in the meantime.
CREATE INDEX IF NOT EXISTS idx_shoir_accounts_affiliate_code_lookup
    ON public.shoir_accounts(LOWER(affiliate_code))
    WHERE affiliate_code IS NOT NULL AND BTRIM(affiliate_code) <> '';

ALTER TABLE public.shoir_referrals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.shoir_referrals FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.shoir_referrals TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.shoir_referrals_id_seq TO service_role;

COMMIT;
