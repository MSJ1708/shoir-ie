#!/usr/bin/env python3
"""Fast, fail-closed preflight for the candidate Shoir-IE staging build.

Waits once for the UI deployment to show the candidate marker. The module and
browser suites must not each spend many minutes rediscovering that the same
Streamlit deployment is stale.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from staging_e2e_guard import validate_app_from_env

EXPECTED_MARKER = "SHOIR-IE SHELL VERSION: 3.2"
WAIT_SECONDS = 90
POLL_SECONDS = 5
REPORT = Path(os.environ.get(
    "SHOIR_E2E_BUILD_REPORT",
    "artifacts/authenticated-release-gate/candidate-build-report.json",
))


def read_signin_surface(page):
    for frame in list(page.frames):
        try:
            body = frame.locator("body").inner_text(timeout=1_500)
        except Exception:
            continue
        if (
            "Sign In to Your Workspace" in body
            or "Welcome to Shoir-IE, " in body
            or "Welcome to Shoir-IE Workspace" in body
        ):
            return frame, body
    return None, ""


def shell_version(body: str) -> str:
    match = re.search(r"SHOIR-IE SHELL VERSION:\s*([^\s—·]+)", body)
    return match.group(1) if match else "not reported"


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    result = {
        "started_at_utc": started,
        "expected_marker": EXPECTED_MARKER,
        "overall": "FAIL",
        "observed_version": None,
        "staging_marker_present": False,
        "credentials_submitted": False,
    }
    try:
        target_url = validate_app_from_env()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                deadline = time.monotonic() + WAIT_SECONDS
                last_body = ""
                while True:
                    response = page.goto(
                        target_url,
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )
                    if response is None or response.status != 200:
                        raise RuntimeError(
                            "Staging app did not return HTTP 200 during candidate-build preflight."
                        )
                    frame, body = read_signin_surface(page)
                    if frame is None:
                        raise RuntimeError(
                            "Could not find the Shoir-IE sign-in surface; candidate build was not verified."
                        )
                    last_body = body
                    if "STAGING TEST ENVIRONMENT" not in body:
                        raise RuntimeError(
                            "Staging safety banner is absent; no credentials were submitted."
                        )
                    result["staging_marker_present"] = True
                    result["observed_version"] = shell_version(body)
                    if EXPECTED_MARKER in body:
                        result["overall"] = "PASS"
                        print(
                            f"[PASS] candidate_build: expected staging marker is visible "
                            f"(shell {result['observed_version']})."
                        )
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            f"Staging is marked safe but is serving shell version "
                            f"{result['observed_version']}; expected {EXPECTED_MARKER}. "
                            "The configured Streamlit app is not serving the current "
                            "staging-e2e-20261019 candidate. Check its branch, main file "
                            "path, latest commit, and Manage app → Reboot before rerunning."
                        )
                    print(
                        f"[WAIT] Candidate build not deployed yet; observed shell "
                        f"{result['observed_version']}. Checking again for up to "
                        f"{WAIT_SECONDS} seconds."
                    )
                    page.wait_for_timeout(POLL_SECONDS * 1000)
            finally:
                browser.close()
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        print(f"[FAIL] candidate_build: {result['error']}", file=sys.stderr)
    finally:
        result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        REPORT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
