-- Renewal-only sessions let an authenticated expired user submit a renewal request
-- without granting workspace access. Existing sessions default to workspace scope.
ALTER TABLE public.shoir_sessions
    ADD COLUMN IF NOT EXISTS scope text NOT NULL DEFAULT 'workspace';

-- The administrator's only subscription change is its tier entitlement. Preserve
-- the account identity, role, credentials, and long-dated expiry.
UPDATE public.shoir_accounts
SET tier = 'Enterprise Plus Tier ($399)',
    updated_at = NOW()
WHERE username_lc = 'sho'
  AND role = 'Enterprise Admin'
  AND tier IS DISTINCT FROM 'Enterprise Plus Tier ($399)';
