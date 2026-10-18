-- Payment proof files may contain personal or financial information.
-- Keep the bucket private and restrict it to the formats and size supported
-- by the renewal UI. The service-role Edge Function manages uploads and
-- returns short-lived signed URLs only after administrator authorization.
INSERT INTO storage.buckets
  (id, name, public, file_size_limit, allowed_mime_types)
VALUES
  ('subscription-payment-proofs', 'subscription-payment-proofs', false, 524288,
   ARRAY['image/png', 'image/jpeg', 'application/pdf'])
ON CONFLICT (id) DO UPDATE
SET public = false,
    file_size_limit = 524288,
    allowed_mime_types = ARRAY['image/png', 'image/jpeg', 'application/pdf'];
