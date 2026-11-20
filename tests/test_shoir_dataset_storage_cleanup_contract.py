"""Static regression contracts for managed dataset object lifecycle ordering."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDGE = ROOT / "supabase" / "functions" / "shoir-persistence" / "index.ts"


def dataset_finalize_source() -> str:
    source = EDGE.read_text(encoding="utf-8")
    start = source.index('if (action === "dataset_version_finalize")')
    end = source.index('if (action === "dataset_version_register")', start)
    return source[start:end]


def test_dataset_metadata_is_registered_before_temporary_upload_is_removed():
    source = dataset_finalize_source()
    rpc = source.index('supabase.rpc(\n        "shoir_platform_register_dataset_version_with_storage"')
    registration = source.index("const registration = Array.isArray(data)", rpc)
    temp_cleanup = source.index("const { error: tempRemoveError } = await bucket.remove([uploadPath])", registration)

    assert rpc < registration < temp_cleanup
    assert "temporary_cleanup_pending: temporaryCleanupPending" in source
    lease_acquire = source.index('"shoir_dataset_storage_lease_acquire"')
    storage_read = source.index(".download(uploadPath)")
    lease_release = source.index('"shoir_dataset_storage_lease_release"')
    release_finally = source.index("} finally {", lease_release)
    assert lease_acquire < storage_read < lease_release < release_finally
    assert 'p_lease_operation: "finalize"' in source
    assert "p_lease_seconds: 300" in source


def test_new_content_addressed_object_is_deleted_only_after_two_successful_no_reference_checks():
    source = dataset_finalize_source()
    assert "let createdFinalObject = false;" in source
    assert "createdFinalObject = true;" in source
    assert "if (createdFinalObject)" in source

    record_query = source.index('supabase.from("shoir_platform_records")')
    event_query = source.index('supabase.from("shoir_platform_events")')
    record_refs = source.index("recordRefs.error || eventRefs.error")
    no_references = source.index(
        "(recordRefs.data || []).length === 0 &&\n              (eventRefs.data || []).length === 0"
    )
    delete_object = source.index("await bucket.remove([\n                storageKey,\n              ])")

    assert record_query < event_query < record_refs < no_references < delete_object
    assert '.contains("payload_json", { storage_key: storageKey })' in source
    assert "uncertain reference check must never turn into a destructive" in source


def test_metadata_rpc_failure_keeps_uncertain_object_and_cleans_only_temp_upload():
    source = dataset_finalize_source()
    rpc_error = source.index("if (error) {", source.index("shoir_platform_register_dataset_version_with_storage"))
    reference_checks = source.index("const [recordRefs, eventRefs]", rpc_error)
    temp_cleanup = source.index("await bucket.remove([uploadPath])", reference_checks)
    throw_original_error = source.index("throw error;", temp_cleanup)

    assert rpc_error < reference_checks < temp_cleanup < throw_original_error
    assert "reference checks were unavailable, so the immutable object was retained" in source
    assert "the immutable object was retained because reference status was uncertain" in source


def test_temporary_object_cleanup_failure_does_not_report_registered_version_as_failed():
    source = dataset_finalize_source()
    registration = source.index("const registration = Array.isArray(data)")
    cleanup_flag = source.index("let temporaryCleanupPending = false;", registration)
    response = source.index("return sendResponse({", cleanup_flag)

    assert "temporaryCleanupPending = Boolean(tempRemoveError)" in source
    assert "temporaryCleanupPending = true" in source
    assert response > cleanup_flag
    assert "ok: true" in source[response:response + 250]



def dataset_storage_sweep_source() -> str:
    source = EDGE.read_text(encoding="utf-8")
    start = source.index('if (action === "dataset_storage_sweep_session")')
    end = source.index('if (action === "dataset_download_url")', start)
    return source[start:end]


def test_dataset_storage_sweep_is_workspace_scoped_authenticated_and_manage_gated():
    source = dataset_storage_sweep_source()
    assert "getSession(" in source
    assert "datasetEntitlementDenialForRequest(" in source
    assert "resolveManagedWorkspaceKey(" in source
    assert 'body,\n        "manage",' in source
    assert "body.confirm_delete !== true" in source
    assert "const MINIMUM_AGE_HOURS = 48;" in source
    assert "const MAX_DIRECTORIES = 200;" in source
    assert "const MAX_OBJECTS = 500;" in source
    assert "const MAX_REFERENCE_CHECKS = 100;" in source
    assert "const MAX_DELETES_PER_RUN = 50;" in source
    assert "no objects were deleted" in source


def test_dataset_storage_sweep_requires_a_dataset_lease_and_both_ledgers_before_delete():
    source = dataset_storage_sweep_source()
    lease_acquire = source.index('"shoir_dataset_storage_lease_acquire"')
    record_query = source.index('supabase.from("shoir_platform_records")')
    event_query = source.index('supabase.from("shoir_platform_events")')
    uncertain_check = source.index("if (recordRefs.error || eventRefs.error)")
    referenced_check = source.index("(eventRefs.data || []).length > 0")
    audit_intent = source.index('event_type: eventPrefix + "_delete_intent"')
    remove_object = source.index("await bucket.remove([")
    completion_event = source.index('event_type: eventPrefix + "_object_deleted"')
    lease_release = source.index('"shoir_dataset_storage_lease_release"')
    assert lease_acquire < record_query < event_query < uncertain_check
    assert referenced_check < audit_intent < remove_object < completion_event < lease_release
    assert "record_and_event_ledgers_confirmed_unreferenced: true" in source
    assert "lifecycle_lease_held: true" in source
    assert 'candidate.kind === "temporary"' in source
    assert 'candidate.kind === "immutable"' in source
    assert "leaseBusyCount" in source
    assert "leaseAcquisitionFailures" in source
    assert "leaseReleaseFailures" in source


def test_dataset_storage_lifecycle_migration_is_server_only_and_expiring():
    migration = (
        ROOT / "supabase" / "migrations" /
        "20261120115000_shoir_dataset_storage_lifecycle_leases.sql"
    ).read_text(encoding="utf-8")
    normalized = " ".join(migration.casefold().split())
    assert "create table public.shoir_dataset_storage_lifecycle_leases" in normalized
    assert "primary key (workspace_key, dataset_id)" in normalized
    assert "enable row level security" in normalized
    assert "revoke all on table public.shoir_dataset_storage_lifecycle_leases from public, anon, authenticated, service_role" in normalized
    assert "security definer" in normalized
    assert "set search_path = pg_catalog, public" in normalized
    assert "where current_lease.expires_at <= clock_timestamp()" in normalized
    assert "p_lease_seconds not between 30 and 600" in normalized
    assert "lease_token = p_lease_token" in normalized
    assert "grant execute on function public.shoir_dataset_storage_lease_acquire" in normalized
    assert "grant execute on function public.shoir_dataset_storage_lease_release" in normalized
    assert "to service_role" in normalized


def test_dataset_storage_maintenance_is_staging_only_and_has_separate_confirmation():
    store_source = (ROOT / "durable_account_store.py").read_text(encoding="utf-8")
    workbench_source = (ROOT / "pages" / "Industrial_Engineering_Workbench.py").read_text(encoding="utf-8")
    assert '"dataset_storage_sweep_session"' in store_source
    helper_start = store_source.index("def edge_sweep_dataset_storage(")
    helper_end = store_source.index("def edge_upload_and_register_dataset_version(", helper_start)
    helper = store_source[helper_start:helper_end]
    assert 'APP_ENVIRONMENT' in helper and '"staging"' in helper
    assert '_edge_call("dataset_storage_sweep_session"' in helper
    assert 'confirm_delete: bool = False' in helper
    assert "Preview old unreferenced dataset objects" in workbench_source
    assert "Delete confirmed orphan dataset objects" in workbench_source
    assert "disabled=not confirm_sweep" in workbench_source
