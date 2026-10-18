-- These platform repository tables are accessed through the trusted Edge Function.
-- The public API roles must not read or write them directly.
CREATE POLICY server_only_shoir_platform_artifacts
ON public.shoir_platform_artifacts
FOR ALL TO anon, authenticated
USING (false) WITH CHECK (false);

CREATE POLICY server_only_shoir_platform_events
ON public.shoir_platform_events
FOR ALL TO anon, authenticated
USING (false) WITH CHECK (false);

CREATE POLICY server_only_shoir_platform_jobs
ON public.shoir_platform_jobs
FOR ALL TO anon, authenticated
USING (false) WITH CHECK (false);

CREATE POLICY server_only_shoir_platform_meta
ON public.shoir_platform_meta
FOR ALL TO anon, authenticated
USING (false) WITH CHECK (false);

CREATE POLICY server_only_shoir_platform_records
ON public.shoir_platform_records
FOR ALL TO anon, authenticated
USING (false) WITH CHECK (false);
