"""Guard required CI contexts using parsed GitHub Actions workflow structure."""
from pathlib import Path
import re
import shlex

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys instead of hiding them."""


def _construct_unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"Duplicate YAML mapping key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_workflow(path: Path):
    document = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return document


def _workflow_events(document):
    # PyYAML's YAML 1.1 resolver treats the unquoted GitHub Actions key "on"
    # as boolean True. Support both representations without string slicing.
    events = document.get("on", document.get(True, {}))
    if not isinstance(events, dict):
        raise ValueError("Workflow triggers must be a mapping")
    return events


def _workflow_jobs(document):
    jobs = document.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError("Workflow must define a jobs mapping")
    return jobs


def _job_context(job_id, job):
    return str(job.get("name") or job_id)


def _find_unique_job_context(jobs, context):
    matches = [
        (job_id, job)
        for job_id, job in jobs.items()
        if isinstance(job, dict) and _job_context(job_id, job) == context
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one job context {context!r}; found {len(matches)}"
        )
    return matches[0]


def test_required_job_lookup_rejects_missing_renamed_and_duplicate_contexts():
    with pytest.raises(ValueError, match="found 0"):
        _find_unique_job_context({}, "edge-function")
    with pytest.raises(ValueError, match="found 0"):
        _find_unique_job_context({"edge-function-renamed": {}}, "edge-function")
    with pytest.raises(ValueError, match="found 2"):
        _find_unique_job_context(
            {"edge-function": {}, "another-job": {"name": "edge-function"}},
            "edge-function",
        )


def test_edge_function_required_check_is_not_path_skipped_for_main_or_staging_prs():
    workflow = _load_workflow(ROOT / ".github" / "workflows" / "edge-function-check.yml")
    events = _workflow_events(workflow)
    pull_request = events.get("pull_request")
    assert isinstance(pull_request, dict)
    branches = set(pull_request.get("branches", []))
    assert {"main", "staging-e2e-20261019"}.issubset(branches)
    assert "paths" not in pull_request

    jobs = _workflow_jobs(workflow)
    _, edge_job = _find_unique_job_context(jobs, "edge-function")
    assert edge_job.get("runs-on"), "The required Edge Function job must have a runner"


def test_edge_function_workflow_covers_database_migration_rehearsal_paths():
    workflow = _load_workflow(ROOT / ".github" / "workflows" / "edge-function-check.yml")
    events = _workflow_events(workflow)
    push = events.get("push")
    assert isinstance(push, dict)
    paths = set(push.get("paths", []))
    assert {
        "supabase/functions/**",
        "supabase/production-hotfix-v8/**",
        "supabase/migrations/**",
        "tests/test_migration_source_inventory.py",
        "tests/test_full_migration_history_postgres.py",
    }.issubset(paths)


def test_required_test_context_is_unique_across_workflows():
    matches = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        workflow = _load_workflow(path)
        jobs = _workflow_jobs(workflow)
        for job_id, job in jobs.items():
            if isinstance(job, dict) and _job_context(job_id, job) == "test":
                matches.append(path.name)
    assert matches == ["shoir-validation.yml"], (
        "The protected ruleset requires the check context 'test'; it must be emitted "
        f"by exactly one workflow, found {matches}."
    )


def test_authenticated_gate_requires_inactive_denial_and_login_throttle_inputs():
    workflow = _load_workflow(
        ROOT / ".github" / "workflows" / "authenticated-release-gate.yml"
    )
    jobs = _workflow_jobs(workflow)
    _, job = _find_unique_job_context(jobs, "authenticated-release-gate")
    environment = job.get("env", {})
    required_names = {
        "SHOIR_E2E_ACTIVE_EXPECTED_TIER",
        "SHOIR_E2E_INACTIVE_USERNAME",
        "SHOIR_E2E_INACTIVE_PASSWORD",
        "SHOIR_E2E_VERIFY_LOGIN_THROTTLE",
    }
    assert required_names.issubset(environment)

    steps = job.get("steps", [])
    preflight = next(
        (step for step in steps if isinstance(step, dict) and step.get("id") == "staging_preflight"),
        None,
    )
    assert preflight is not None, "Authenticated gate must retain the dedicated-account preflight"
    run = preflight.get("run", "")
    assert isinstance(run, str)

    required_match = re.search(r"(?m)^\s*required=\(([^)]*)\)", run)
    assert required_match, "Preflight must declare mandatory environment inputs"
    required = set(shlex.split(required_match.group(1)))
    assert required_names.issubset(required)

    identities_match = re.search(r"(?m)^\s*identities=\(([^)]*)\)", run)
    assert identities_match, "Preflight must enumerate disposable test identities"
    identities = shlex.split(identities_match.group(1))
    expected_identities = {
        "SHOIR_E2E_ACTIVE_USERNAME",
        "SHOIR_E2E_SECOND_USERNAME",
        "SHOIR_E2E_STARTER_USERNAME",
        "SHOIR_E2E_EXPIRED_USERNAME",
        "SHOIR_E2E_MODULE_USERNAME",
        "SHOIR_E2E_RESEARCH_MODULE_USERNAME",
        "SHOIR_E2E_INACTIVE_USERNAME",
    }
    assert set(identities) == expected_identities
    assert len(identities) == len(set(identities)), "Test identities must be distinct"
    assert 'for name in "${identities[@]}"' in run
    assert "shoir-e2e-*" in run
    assert "sort -fu" in run
    assert "All authenticated release-gate identities must be distinct." in run
    assert 'if [[ "${SHOIR_E2E_VERIFY_LOGIN_THROTTLE,,}" != "true" ]]' in run


def test_validation_workflow_emits_test_once_per_release_pr_head():
    workflow = _load_workflow(ROOT / ".github" / "workflows" / "shoir-validation.yml")
    events = _workflow_events(workflow)
    for event_name in ("push", "pull_request"):
        event = events.get(event_name)
        assert isinstance(event, dict)
        assert {"main", "staging-e2e-20261019"}.issubset(
            set(event.get("branches", []))
        )
        assert "paths" not in event

    jobs = _workflow_jobs(workflow)
    _find_unique_job_context(jobs, "test")


def test_authenticated_backend_gate_does_not_skip_inactive_or_throttle_checks():
    script = (ROOT / "scripts" / "authenticated_release_gate.py").read_text(
        encoding="utf-8"
    )
    assert 'require_env("SHOIR_E2E_INACTIVE_USERNAME")' in script
    assert 'require_env("SHOIR_E2E_INACTIVE_PASSWORD")' in script
    assert 'require_env("SHOIR_E2E_VERIFY_LOGIN_THROTTLE")' in script
    assert "login_throttle_blocks_excess_attempts" in script
    assert "inactive_account_denied" in script
    assert '"Skipped: set the GitHub Actions variable SHOIR_E2E_VERIFY_LOGIN_THROTTLE' not in script
    assert '"Skipped: configure a dedicated inactive test account' not in script
    assert "inactive_user.casefold()" in script
    assert '("inactive", inactive_user, inactive_token)' in script
