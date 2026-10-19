-- Approve/decline subscription requests atomically. Serialize decisions on the
-- request row so two administrators/actions cannot race to overwrite the final state.
CREATE OR REPLACE FUNCTION public.shoir_finalize_subscription_request(
    p_request_id bigint,
    p_decision text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $function$
DECLARE
    request_row public.shoir_subscription_requests%ROWTYPE;
    account_row public.shoir_accounts%ROWTYPE;
    pending_row public.shoir_pending_credentials%ROWTYPE;
    decision_at timestamptz := clock_timestamp();
    next_expiry timestamptz;
    next_password_hash text;
    next_tier text;
    next_email text;
    next_username text;
BEGIN
    IF p_decision IS NULL OR p_decision NOT IN ('Approved', 'Declined') THEN
        RAISE EXCEPTION 'Invalid subscription request decision.'
            USING ERRCODE = '22023';
    END IF;

    SELECT *
      INTO request_row
      FROM public.shoir_subscription_requests
     WHERE id = p_request_id
     FOR UPDATE;

    IF NOT FOUND OR request_row.status IS DISTINCT FROM 'Pending' THEN
        RAISE EXCEPTION 'Pending request not found or already processed.'
            USING ERRCODE = 'P0002';
    END IF;

    IF p_decision = 'Declined' THEN
        UPDATE public.shoir_subscription_requests
           SET status = 'Declined',
               updated_at = decision_at
         WHERE id = request_row.id
           AND status = 'Pending';

        IF NOT FOUND THEN
            RAISE EXCEPTION 'Pending request not found or already processed.'
                USING ERRCODE = 'P0002';
        END IF;

        RETURN jsonb_build_object(
            'ok', true,
            'request_id', request_row.id,
            'status', 'Declined'
        );
    END IF;

    SELECT *
      INTO account_row
      FROM public.shoir_accounts
     WHERE username_lc = request_row.username_lc
     FOR UPDATE;

    SELECT *
      INTO pending_row
      FROM public.shoir_pending_credentials
     WHERE username_lc = request_row.username_lc
     FOR UPDATE;

    next_password_hash := COALESCE(account_row.password_hash, pending_row.password_hash);
    IF next_password_hash IS NULL OR next_password_hash = '' THEN
        RAISE EXCEPTION 'Pending registration credentials are missing.'
            USING ERRCODE = 'P0001';
    END IF;

    next_username := COALESCE(account_row.username, request_row.username);
    next_tier := COALESCE(NULLIF(request_row.tier, ''), account_row.tier, 'Starter Tier ($29)');
    next_email := COALESCE(NULLIF(request_row.email, ''), account_row.email, '');

    IF request_row.request_type = 'Renewal'
       AND account_row.username_lc IS NOT NULL THEN
        next_expiry := GREATEST(
            decision_at,
            COALESCE(account_row.subscription_expires_at, decision_at)
        ) + INTERVAL '30 days';
    ELSE
        next_expiry := decision_at + INTERVAL '30 days';
    END IF;

    -- This upsert preserves the existing account identity, credentials, role,
    -- creation time and profile. Only requested tier/expiry and renewal metadata
    -- are updated for an existing subscriber.
    INSERT INTO public.shoir_accounts AS current_account (
        username,
        username_lc,
        password_hash,
        role,
        tier,
        email,
        created_at,
        subscription_expires_at,
        linkedin,
        github,
        about_me,
        affiliate_code,
        active,
        updated_at
    ) VALUES (
        next_username,
        request_row.username_lc,
        next_password_hash,
        COALESCE(account_row.role, 'User'),
        next_tier,
        next_email,
        COALESCE(account_row.created_at, decision_at),
        next_expiry,
        account_row.linkedin,
        account_row.github,
        account_row.about_me,
        account_row.affiliate_code,
        true,
        decision_at
    )
    ON CONFLICT (username_lc) DO UPDATE SET
        username = current_account.username,
        password_hash = current_account.password_hash,
        role = current_account.role,
        tier = EXCLUDED.tier,
        email = EXCLUDED.email,
        created_at = current_account.created_at,
        subscription_expires_at = EXCLUDED.subscription_expires_at,
        linkedin = current_account.linkedin,
        github = current_account.github,
        about_me = current_account.about_me,
        affiliate_code = current_account.affiliate_code,
        active = true,
        updated_at = EXCLUDED.updated_at;

    UPDATE public.shoir_subscription_requests
       SET status = 'Approved',
           approved_at = decision_at,
           updated_at = decision_at
     WHERE id = request_row.id
       AND status = 'Pending';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pending request not found or already processed.'
            USING ERRCODE = 'P0002';
    END IF;

    RETURN jsonb_build_object(
        'ok', true,
        'username', next_username,
        'expires_at', next_expiry,
        'tier', next_tier,
        'email', next_email,
        'request_id', request_row.id,
        'status', 'Approved'
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_finalize_subscription_request(bigint, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_finalize_subscription_request(bigint, text)
    TO service_role;


-- New registration is also a single transaction: one normalized username can
-- have only one active account or pending New request, and its credentials and
-- payment reference are recorded together with the private proof reference.
CREATE OR REPLACE FUNCTION public.shoir_create_registration_request(
    p_username text,
    p_username_lc text,
    p_password_hash text,
    p_email text,
    p_tier text,
    p_payment_method text,
    p_transaction_id text,
    p_screenshot_path text
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $function$
DECLARE
    request_id bigint;
    normalized_username text := lower(btrim(p_username));
    now_at timestamptz := clock_timestamp();
BEGIN
    IF p_username IS NULL OR btrim(p_username) !~ '^[A-Za-z0-9._-]{3,32}$'
       OR p_username_lc IS DISTINCT FROM normalized_username THEN
        RAISE EXCEPTION 'Invalid registration username.'
            USING ERRCODE = '22023';
    END IF;

    IF p_password_hash IS NULL
       OR p_password_hash !~ '^[0-9a-f]{32}\$[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Registration credentials are invalid.'
            USING ERRCODE = '22023';
    END IF;

    IF p_email IS NULL
       OR length(btrim(p_email)) > 254
       OR btrim(p_email) !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' THEN
        RAISE EXCEPTION 'Invalid registration email address.'
            USING ERRCODE = '22023';
    END IF;

    IF p_tier NOT IN (
        'Starter Tier ($29)',
        'Mid-Tier Pro ($79)',
        'Professional Tier ($129)',
        'Enterprise Tier ($199)',
        'Enterprise Plus Tier ($399)',
        'Research Pack ($30 add-on)'
    ) THEN
        RAISE EXCEPTION 'Invalid subscription tier.'
            USING ERRCODE = '22023';
    END IF;

    IF p_payment_method IS DISTINCT FROM 'STC Pay (QR)' THEN
        RAISE EXCEPTION 'Unsupported registration payment method.'
            USING ERRCODE = '22023';
    END IF;

    IF p_screenshot_path IS NULL
       OR p_screenshot_path NOT LIKE 'storage://subscription-payment-proofs/renewals/%' THEN
        RAISE EXCEPTION 'A privately stored payment proof is required.'
            USING ERRCODE = '22023';
    END IF;

    -- Serialize registration attempts for the same normalized username, even
    -- when no account row exists yet.
    PERFORM pg_advisory_xact_lock(
        hashtextextended('shoir-registration:' || normalized_username, 0)
    );

    IF EXISTS (
        SELECT 1 FROM public.shoir_accounts
        WHERE username_lc = normalized_username
    ) OR EXISTS (
        SELECT 1 FROM public.shoir_subscription_requests
        WHERE username_lc = normalized_username
          AND request_type = 'New'
          AND status = 'Pending'
    ) THEN
        RAISE EXCEPTION 'Registration request could not be submitted. Sign in if you have an account or contact support.'
            USING ERRCODE = 'P0002';
    END IF;

    INSERT INTO public.shoir_pending_credentials (
        username_lc, username, password_hash, email, updated_at
    ) VALUES (
        normalized_username, btrim(p_username), p_password_hash,
        btrim(p_email), now_at
    )
    ON CONFLICT (username_lc) DO UPDATE SET
        username = EXCLUDED.username,
        password_hash = EXCLUDED.password_hash,
        email = EXCLUDED.email,
        updated_at = EXCLUDED.updated_at;

    INSERT INTO public.shoir_subscription_requests (
        username, username_lc, email, tier, request_type, payment_method,
        transaction_id, screenshot_path, status, requested_at, updated_at
    ) VALUES (
        btrim(p_username), normalized_username, btrim(p_email), p_tier,
        'New', p_payment_method, NULLIF(btrim(p_transaction_id), ''),
        p_screenshot_path, 'Pending', now_at, now_at
    )
    RETURNING id INTO request_id;

    RETURN jsonb_build_object(
        'ok', true,
        'request_id', request_id,
        'status', 'Pending'
    );
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_create_registration_request(text, text, text, text, text, text, text, text)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_create_registration_request(text, text, text, text, text, text, text, text)
    TO service_role;
