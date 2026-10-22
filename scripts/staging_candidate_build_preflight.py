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
    """Wait briefly for Streamlit's iframe and widgets after the HTTP document loads."""
    deadline = time.monotonic() + 20
    last_body = ""
    while time.monotonic() < deadline:
        for frame in list(page.frames):
            try:
                body = frame.locator("body").inner_text(timeout=1_000)
            except Exception:
                continue
            if body.strip():
                last_body = body[:8_000]
            if (
                "Sign In to Your Workspace" in body
                or "Welcome to Shoir-IE, " in body
                or "Welcome to Shoir-IE Workspace" in body
            ):
                return frame, body
        page.wait_for_timeout(300)
    # Keep only an in-memory observation for coarse diagnostics. It is never
    # written verbatim to an artifact because a public error page can contain
    # implementation details.
    return None, last_body


def classify_missing_surface(body: str) -> str:
    """Return a low-risk diagnostic label without persisting arbitrary page text."""
    lowered = str(body or "").casefold()
    if "could not initialize its required account and persistence layer" in lowered:
        return "persistence_initialization_error"
    if "shoir-ie startup" in lowered or "application runtime could not be loaded" in lowered:
        return "application_startup_error"
    if "traceback" in lowered or "modulenotfounderror" in lowered or "importerror" in lowered:
        return "python_runtime_error"
    if not lowered.strip() or "please wait" in lowered or "running..." in lowered:
        return "blank_or_loading_ui"
    return "sign_in_surface_not_rendered"


def collect_surface_diagnostics(page) -> dict:
    """Capture coarse DOM facts only; never store raw page text or query strings."""
    details = {
        "title": "unavailable",
        "frame_count": 0,
        "iframe_count": 0,
        "top_body_chars": 0,
        "streamlit_root": False,
        "streamlit_iframe": False,
        "frame_summary": [],
    }
    try:
        details["title"] = str(page.title() or "")[:80]
    except Exception:
        pass
    try:
        details["frame_count"] = len(page.frames)
        details["iframe_count"] = int(page.locator("iframe").count())
    except Exception:
        pass
    try:
        details["top_body_chars"] = len(page.locator("body").inner_text(timeout=1_000))
    except Exception:
        pass
    try:
        details["streamlit_root"] = page.locator("[data-testid='stApp']").count() > 0
        details["streamlit_iframe"] = page.locator("iframe[title*='Streamlit']").count() > 0
    except Exception:
        pass
    for frame in list(page.frames)[:6]:
        entry = {"name": "", "host": "", "body_chars": 0, "signin_marker": False,
                 "staging_marker": False, "shell_marker": False, "startup_error": False}
        try:
            entry["name"] = str(frame.name or "")[:60]
        except Exception:
            pass
        try:
            from urllib.parse import urlsplit
            entry["host"] = str(urlsplit(frame.url).hostname or "")[:100]
        except Exception:
            pass
        try:
            text = frame.locator("body").inner_text(timeout=1_000)
            entry["body_chars"] = len(text)
            entry["signin_marker"] = any(marker in text for marker in (
                "Sign In to Your Workspace", "Welcome to Shoir-IE, ",
                "Welcome to Shoir-IE Workspace",
            ))
            entry["staging_marker"] = "STAGING TEST ENVIRONMENT" in text
            entry["shell_marker"] = "SHOIR-IE SHELL VERSION:" in text
            lowered = text.casefold()
            entry["startup_error"] = any(term in lowered for term in (
                "could not initialize its required account and persistence layer",
                "application runtime could not be loaded",
                "modulenotfounderror",
                "traceback",
            ))
        except Exception:
            pass
        details["frame_summary"].append(entry)
    return details


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
                        diagnostic = classify_missing_surface(body)
                        result["surface_diagnostic"] = diagnostic
                        result["dom_diagnostics"] = collect_surface_diagnostics(page)
                        print(
                            "[DIAGNOSTIC] sign-in surface not found: "
                            + json.dumps(result["dom_diagnostics"], sort_keys=True)
                            + f"; category={diagnostic}"
                        )
                        if diagnostic in {
                            "persistence_initialization_error",
                            "application_startup_error",
                            "python_runtime_error",
                        }:
                            raise RuntimeError(
                                "The staging app returned an application/runtime error instead of the sign-in surface "
                                f"({diagnostic}); candidate build was not verified and no credentials were submitted."
                            )
                        if time.monotonic() >= deadline:
                            raise RuntimeError(
                                "The staging app did not render the Shoir-IE sign-in surface within "
                                f"{WAIT_SECONDS} seconds ({diagnostic}); candidate build was not verified and "
                                "no credentials were submitted. Check Streamlit Cloud app logs and the deployed commit."
                            )
                        print(
                            "[WAIT] Staging returned HTTP 200 but the sign-in surface is not rendered yet "
                            f"({diagnostic}); retrying without submitting credentials."
                        )
                        page.wait_for_timeout(POLL_SECONDS * 1000)
                        continue
                    result["surface_diagnostic"] = "sign_in_surface_found"
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
