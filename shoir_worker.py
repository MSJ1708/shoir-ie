"""Shoir-IE distributed worker.

Runs persisted platform jobs claimed from the PostgreSQL queue. The worker is
deliberately small: business calculations stay in specialist Python callables;
this process owns claim -> execute -> verify -> complete/fail.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import time
from typing import Any, Mapping

from shoir_platform_core import (
    claim_distributed_job,
    reap_stale_jobs,
    digest,
    engine_error_payload,
    update_distributed_job,
)


def _invoke(payload: Mapping[str, Any]) -> Any:
    path = str(payload.get("callable_path") or "")
    if ":" not in path:
        raise ValueError("Queued job is missing callable_path module:function.")
    module_name, function_name = path.split(":", 1)
    module = importlib.import_module(module_name)
    fn = getattr(module, function_name, None)
    if not callable(fn):
        raise ValueError(f"Queued job target is not callable: {path}")
    kwargs = dict(payload.get("kwargs") or {})
    return fn(**kwargs)


def worker_once(*, worker_id: str, workspace: str = "default") -> dict[str, Any] | None:
    reap_stale_jobs(workspace=workspace)
    job = claim_distributed_job(worker_id, workspace=workspace)
    if not job:
        return None

    job_id = str(job["job_id"])
    payload = dict(job.get("payload") or {})
    module = str(job.get("module") or "Worker")
    try:
        update_distributed_job(job_id, status="RUNNING", worker_id=worker_id, progress=0.1, workspace=workspace)
        started = time.perf_counter()
        result = _invoke(payload)
        duration_ms = (time.perf_counter() - started) * 1000.0
        update_distributed_job(
            job_id,
            status="COMPLETED",
            worker_id=worker_id,
            progress=1.0,
            result={"result_hash": digest(result), "duration_ms": round(duration_ms, 2)},
            workspace=workspace,
        )
        return {"job_id": job_id, "status": "COMPLETED", "result_hash": digest(result), "duration_ms": round(duration_ms, 2)}
    except Exception as exc:
        attempts = int(job.get("attempts") or 1)
        max_attempts = int(job.get("max_attempts") or 3)
        terminal = attempts >= max_attempts
        update_distributed_job(
            job_id,
            status="FAILED" if terminal else "QUEUED",
            worker_id=worker_id,
            progress=1.0 if terminal else 0.0,
            error=engine_error_payload(module, exc),
            workspace=workspace,
        )
        return {"job_id": job_id, "status": "FAILED" if terminal else "REQUEUED", "attempts": attempts, "max_attempts": max_attempts, "error_type": type(exc).__name__, "error": str(exc)}


def run_worker(
    *,
    worker_id: str | None = None,
    workspace: str = "default",
    poll_seconds: float = 2.0,
    once: bool = False,
) -> None:
    wid = str(worker_id or os.getenv("SHOIR_WORKER_ID") or f"worker-{os.getpid()}")
    while True:
        result = worker_once(worker_id=wid, workspace=workspace)
        if once:
            return
        if result is None:
            time.sleep(max(0.1, float(poll_seconds)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Shoir-IE distributed platform worker")
    parser.add_argument("--workspace", default="default")
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    run_worker(
        worker_id=args.worker_id or None,
        workspace=args.workspace,
        poll_seconds=args.poll_seconds,
        once=args.once,
    )


if __name__ == "__main__":
    main()
