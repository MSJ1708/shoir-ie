from pathlib import Path

import re


ROOT = Path(__file__).resolve().parents[1]

GOVERNED_FILES = [
    "shoir_platform_core.py",
    "shoir_app_runtime.py",
    "industrial_platform.py",
    "shoir_industrial_os.py",
    "shoir_universal_platform_kernel.py",
    "shoir_enterprise_layer.py",
    "industrial_experience.py",
    "durable_account_store.py",
    "workspace_persistence.py",
    "shoir_160.py",
]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_app_entrypoint_remains_thin():
    app = read("app.py")
    assert len(app) < 1000
    assert "import shoir_app_runtime" in app


def test_shared_repository_owns_sqlite_connection_policy():
    repository = read("shoir_repository.py")
    assert "sqlite3.connect(" in repository
    assert "PRAGMA foreign_keys=ON" in repository
    for name in GOVERNED_FILES:
        source = read(name)
        assert "sqlite3.connect(" not in source, f"{name} bypasses the repository adapter"


def test_touched_platform_files_have_no_silent_broad_exception_passes():
    pattern = re.compile(r"except\s+Exception\s*:\s*\n\s*pass")
    offenders = [name for name in GOVERNED_FILES if pattern.search(read(name))]
    assert not offenders, f"Silent exception swallowing remains: {offenders}"


def test_platform_kernel_declares_full_workflow_contract():
    core = read("shoir_platform_core.py")
    expected = [
        '"DATA"', '"VALIDATE"', '"MAP"', '"MODEL"', '"RUN"', '"VISUALIZE"',
        '"COMPARE"', '"EXPLAIN"', '"DECIDE"', '"EXPORT"', '"VERIFY"',
    ]
    for stage in expected:
        assert stage in core


def test_capability_inventory_is_present():
    source = read("shoir_160.py")
    assert "FEATURES_160" in source
    assert len(re.findall(r'"id"\s*:', source)) >= 160


def test_distributed_job_queue_schema_and_atomic_claim_are_present():
    core = read("shoir_platform_core.py")
    assert "shoir_platform_jobs" in core
    assert "FOR UPDATE SKIP LOCKED" in core
    assert "enqueue_distributed_job" in core
    assert "update_distributed_job" in core


def test_report_pack_variants_are_present():
    from shoir_completion_engine import REPORT_PROFILES
    assert set(REPORT_PROFILES) >= {
        "Executive Pack", "Engineering Pack", "Audit Pack", "Research Pack"
    }
