-- Persistent server-side login attempt limits for the custom Edge authentication endpoint.
-- Bucket keys are HMAC'd by the Edge Function with its server secret, so this
-- table does not store usernames or client IP addresses in clear text.
CREATE TABLE IF NOT EXISTS public.shoir_login_throttle (
    key_hash text PRIMARY KEY CHECK (length(key_hash) = 64),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    window_started_at timestamptz NOT NULL DEFAULT now(),
    blocked_until timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shoir_login_throttle_updated_at
    ON public.shoir_login_throttle (updated_at);
ALTER TABLE public.shoir_login_throttle ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS shoir_login_throttle_server_only ON public.shoir_login_throttle;
CREATE POLICY shoir_login_throttle_server_only
    ON public.shoir_login_throttle FOR ALL TO anon, authenticated
    USING (false) WITH CHECK (false);
REVOKE ALL ON TABLE public.shoir_login_throttle FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.shoir_login_throttle TO service_role;

CREATE OR REPLACE FUNCTION public.shoir_check_login_throttle(
    p_key_hash text,
    p_mode text,
    p_max_attempts integer,
    p_window_seconds integer,
    p_block_seconds integer
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_row public.shoir_login_throttle%ROWTYPE;
    v_now timestamptz := clock_timestamp();
    v_attempts integer;
    v_blocked_until timestamptz;
BEGIN
    IF p_key_hash IS NULL OR length(p_key_hash) <> 64 THEN
        RAISE EXCEPTION 'Invalid login throttle key';
    END IF;
    IF p_mode NOT IN ('attempt', 'clear') THEN
        RAISE EXCEPTION 'Invalid login throttle operation';
    END IF;
    IF p_max_attempts < 1 OR p_max_attempts > 1000
       OR p_window_seconds < 1 OR p_window_seconds > 86400
       OR p_block_seconds < 1 OR p_block_seconds > 86400 THEN
        RAISE EXCEPTION 'Invalid login throttle policy';
    END IF;

    -- Serialize concurrent attempts for this bucket. This makes the attempt
    -- counter atomic even when several login requests arrive at once.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_key_hash, 0));

    -- Bound table growth without forcing a cleanup scan on every login.
    -- The HMAC key is server-generated, so callers cannot choose cleanup frequency.
    IF get_byte(decode(p_key_hash, 'hex'), 0) = 0 THEN
        DELETE FROM public.shoir_login_throttle
        WHERE updated_at < v_now - interval '7 days';
    END IF;

    SELECT * INTO v_row
    FROM public.shoir_login_throttle
    WHERE key_hash = p_key_hash
    FOR UPDATE;

    IF p_mode = 'clear' THEN
        DELETE FROM public.shoir_login_throttle WHERE key_hash = p_key_hash;
        RETURN jsonb_build_object('blocked', false, 'attempts', 0);
    END IF;

    IF NOT FOUND THEN
        INSERT INTO public.shoir_login_throttle
            (key_hash, attempts, window_started_at, blocked_until, updated_at)
        VALUES (p_key_hash, 1, v_now, NULL, v_now);
        RETURN jsonb_build_object('blocked', false, 'attempts', 1);
    END IF;

    IF v_row.blocked_until IS NOT NULL AND v_row.blocked_until > v_now THEN
        RETURN jsonb_build_object(
            'blocked', true, 'attempts', v_row.attempts,
            'retry_after_seconds', greatest(1, ceil(extract(epoch FROM (v_row.blocked_until - v_now)))::integer)
        );
    END IF;

    IF v_row.window_started_at + make_interval(secs => p_window_seconds) <= v_now THEN
        v_row.attempts := 0;
        v_row.window_started_at := v_now;
        v_row.blocked_until := NULL;
    END IF;

    IF v_row.attempts >= p_max_attempts THEN
        v_blocked_until := v_now + make_interval(secs => p_block_seconds);
        UPDATE public.shoir_login_throttle
        SET blocked_until = v_blocked_until, updated_at = v_now
        WHERE key_hash = p_key_hash;
        RETURN jsonb_build_object(
            'blocked', true, 'attempts', v_row.attempts,
            'retry_after_seconds', p_block_seconds
        );
    END IF;

    v_attempts := v_row.attempts + 1;
    UPDATE public.shoir_login_throttle
    SET attempts = v_attempts, window_started_at = v_row.window_started_at,
        blocked_until = NULL, updated_at = v_now
    WHERE key_hash = p_key_hash;

    RETURN jsonb_build_object('blocked', false, 'attempts', v_attempts);
END;
$function$;

-- PUBLIC/anon/authenticated must not invoke the throttle function directly.
REVOKE EXECUTE ON FUNCTION public.shoir_check_login_throttle(text, text, integer, integer, integer)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_check_login_throttle(text, text, integer, integer, integer)
    TO service_role;
