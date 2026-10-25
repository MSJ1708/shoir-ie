-- Guard the authoritative subscription decision path against direct or stale
-- Edge callers that attempt to approve a new registration without all current
-- policy acknowledgements. This is intentionally a trigger so every UPDATE
-- path is covered, not just one API endpoint.
BEGIN;

CREATE OR REPLACE FUNCTION public.shoir_require_legal_acceptance_before_approval()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $function$
BEGIN
    IF NEW.status = 'Approved'
       AND OLD.status IS DISTINCT FROM 'Approved'
       AND NEW.request_type = 'New'
       AND (
          NEW.terms_accepted IS DISTINCT FROM TRUE
          OR NEW.terms_version IS DISTINCT FROM '2026-10-21-beta-v1'
          OR NEW.privacy_policy_version IS DISTINCT FROM '2026-10-21-v1'
          OR NEW.refund_policy_version IS DISTINCT FROM '2026-10-21-v1'
          OR NEW.cookie_policy_version IS DISTINCT FROM '2026-10-21-v1'
          OR NEW.accepted_at IS NULL
       ) THEN
        RAISE EXCEPTION 'Registration cannot be approved until current beta terms and policy acknowledgement are recorded.'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$function$;

REVOKE ALL ON FUNCTION public.shoir_require_legal_acceptance_before_approval()
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.shoir_require_legal_acceptance_before_approval()
    TO service_role;

DROP TRIGGER IF EXISTS shoir_require_legal_acceptance_before_approval
    ON public.shoir_subscription_requests;

CREATE TRIGGER shoir_require_legal_acceptance_before_approval
BEFORE UPDATE OF status ON public.shoir_subscription_requests
FOR EACH ROW
EXECUTE FUNCTION public.shoir_require_legal_acceptance_before_approval();

COMMIT;
