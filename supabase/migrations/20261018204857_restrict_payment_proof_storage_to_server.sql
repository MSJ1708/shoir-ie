-- Storage table grants exist for API roles, so keep the payment-proof bucket
-- inaccessible even if a permissive policy is later added for another bucket.
-- The service-role Edge Function can upload and sign URLs; it bypasses these RLS
-- restrictions. Never grant direct end-user access to payment receipts.
CREATE POLICY private_subscription_payment_proofs_only_server
ON storage.objects
AS RESTRICTIVE
FOR ALL TO anon, authenticated
USING (bucket_id <> 'subscription-payment-proofs')
WITH CHECK (bucket_id <> 'subscription-payment-proofs');
