-- Defense-in-depth for tables in the private Shoir-IE internal schema.
--
-- Precondition verified on staging project hfhrosthswcybccepmak (2026-11-04):
-- * every table is owned by postgres;
-- * all 12 tables are empty;
-- * postgres is BYPASSRLS and remains the object owner;
-- * no schema/table grants exist for anon, authenticated, service_role,
--   authenticator, PUBLIC or any other non-owner role.
--
-- Enable RLS with no policies. This intentionally keeps access closed to any
-- future non-owner/non-BYPASSRLS role until a table-specific least-privilege
-- access model has been reviewed and tested. Do not add broad USING (true)
-- policies. Do not FORCE ROW LEVEL SECURITY: existing owner/service operations
-- must remain available through their privileged server-side connection.
--
-- This migration creates no grants, policies, rows, or changes to application
-- data. It only enables RLS on the existing internal tables.

ALTER TABLE shoir_internal.artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.twin_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.twin_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.twin_scenarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.connector_health ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.collaboration ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.monitoring_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.monitoring_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.report_provenance ENABLE ROW LEVEL SECURITY;
ALTER TABLE shoir_internal.security ENABLE ROW LEVEL SECURITY;

COMMENT ON SCHEMA shoir_internal IS
  'Private Shoir-IE internal schema. Access is restricted to explicitly privileged server-side database roles; table RLS is enabled and no application-role policies are granted by default.';
