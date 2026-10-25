-- Shoir-IE beta legal-acceptance record and referral attribution.
-- Referral codes record attribution only; this migration does not create rewards,
-- discounts, commissions or payment entitlements.
BEGIN;

ALTER TABLE public.shoir_subscription_requests
    ADD COLUMN IF NOT EXISTS terms_accepted BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS terms_version TEXT,
    ADD COLUMN IF NOT EXISTS privacy_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS refund_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS cookie_policy_version TEXT,
    ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;

-- Replace the old visible "AFF-...-15" codes that implied an inactive,
-- unimplemented discount with neutral referral identifiers.
UPDATE public.shoir_accounts
   SET affiliate_code = 'SHR-' ||
       UPPER(SUBSTRING(REPLACE(gen_random_uuid()::text, '-', '') FROM 1 FOR 10)),
       updated_at = NOW()
 WHERE affiliate_code IS NULL
    OR BTRIM(affiliate_code) = ''
    OR affiliate_code ILIKE 'AFF-%-15';

-- Repair any pre-existing case-insensitive duplicates before enforcing uniqueness.
WITH ranked AS (
    SELECT username_lc,
           ROW_NUMBER() OVER (
               PARTITION BY LOWER(affiliate_code)
               ORDER BY created_at, username_lc
           ) AS duplicate_rank
      FROM public.shoir_accounts
     WHERE affiliate_code IS NOT NULL AND BTRIM(affiliate_code) <> ''
)
UPDATE public.shoir_accounts AS account
   SET affiliate_code = 'SHR-' ||
       UPPER(SUBSTRING(REPLACE(gen_random_uuid()::text, '-', '') FROM 1 FOR 10)),
       updated_at = NOW()
  FROM ranked
 WHERE ranked.username_lc = account.username_lc
   AND ranked.duplicate_rank > 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_shoir_accounts_affiliate_code_unique
    ON public.shoir_accounts (LOWER(affiliate_code))
    WHERE affiliate_code IS NOT NULL AND BTRIM(affiliate_code) <> '';

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

ALTER TABLE public.shoir_referrals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.shoir_referrals FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.shoir_referrals TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.shoir_referrals_id_seq TO service_role;

COMMIT;
