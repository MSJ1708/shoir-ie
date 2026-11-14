-- Explicit deny policies for private staging tables with RLS enabled.
-- These policies apply only to browser roles and never grant table/schema access.
-- Existing service-side access remains governed by explicit grants and its
-- database role's RLS posture. No permissive application policy is introduced.
CREATE POLICY shoir_referrals_deny_browser_roles
    ON public.shoir_referrals
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_artifacts_deny_browser_roles
    ON shoir_internal.artifacts
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_twin_assets_deny_browser_roles
    ON shoir_internal.twin_assets
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_twin_snapshots_deny_browser_roles
    ON shoir_internal.twin_snapshots
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_twin_scenarios_deny_browser_roles
    ON shoir_internal.twin_scenarios
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_connector_health_deny_browser_roles
    ON shoir_internal.connector_health
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_jobs_deny_browser_roles
    ON shoir_internal.jobs
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_collaboration_deny_browser_roles
    ON shoir_internal.collaboration
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_knowledge_deny_browser_roles
    ON shoir_internal.knowledge
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_monitoring_rules_deny_browser_roles
    ON shoir_internal.monitoring_rules
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_monitoring_events_deny_browser_roles
    ON shoir_internal.monitoring_events
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_report_provenance_deny_browser_roles
    ON shoir_internal.report_provenance
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

CREATE POLICY shoir_internal_security_deny_browser_roles
    ON shoir_internal.security
    FOR ALL TO anon, authenticated
    USING (false)
    WITH CHECK (false);

