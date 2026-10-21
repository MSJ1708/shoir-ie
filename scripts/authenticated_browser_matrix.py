#!/usr/bin/env python3
"""Authenticated Streamlit shell/module smoke using a dedicated non-admin test user."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from staging_e2e_guard import validate_app_from_env

REPORT = Path(os.environ.get("SHOIR_E2E_UI_REPORT", "artifacts/authenticated-release-gate/browser-report.json"))
PREFIX = "shoir-e2e-"
CANDIDATE_BUILD_MARKER = "SHOIR-IE SHELL VERSION: 3.2"
URL = os.environ.get("SHOIR_E2E_APP_URL", "").strip()
ACTIVE_MODULE_SELECTOR = '[data-testid="shoir-active-module"]'


def fill_signin_credentials(frame, username: str, password: str) -> None:
    """Fill visible Streamlit sign-in inputs without relying on label association.

    Streamlit's generated labels are not consistently connected to native inputs
    via accessible-name metadata. Select only visible text/password inputs, fail
    closed unless each is unique, and never guess at hidden registration controls.
    """
    # Streamlit re-runs after switching tabs. Wait for the visible controls
    # instead of counting immediately during a transient render.
    username_inputs = frame.locator("input[type='text']:visible")
    password_inputs = frame.locator("input[type='password']:visible")
    username_inputs.first.wait_for(state="visible", timeout=10_000)
    password_inputs.first.wait_for(state="visible", timeout=10_000)
    username_count = username_inputs.count()
    password_count = password_inputs.count()
    if username_count != 1:
        raise RuntimeError(
            f"Expected exactly one visible text input on Sign In tab; found {username_count}."
        )
    if password_count != 1:
        raise RuntimeError(
            f"Expected exactly one visible password input on Sign In tab; found {password_count}."
        )
    username_inputs.first.fill(username)
    password_inputs.first.fill(password)


def read_active_module_label(frame) -> str:
    """Read the visible active-route label without depending on custom HTML attributes."""
    candidates = (
        frame.locator(ACTIVE_MODULE_SELECTOR),
        frame.get_by_text(re.compile(r"^\s*Active module:\s*.+$", re.I)),
    )
    for candidate in candidates:
        try:
            if candidate.count() and candidate.first.is_visible():
                label = candidate.first.inner_text(timeout=1_000).strip()
                if label:
                    return label
        except Exception:
            continue
    return ""


def visible_logout_button(frame):
    """Expand Streamlit's real sidebar control before attempting workspace logout."""
    sidebar = frame.locator('section[data-testid="stSidebar"]')
    try:
        if sidebar.is_visible() and sidebar.get_attribute("aria-expanded") != "false":
            button = frame.get_by_role("button", name="Lock / Logout Workspace").first
            button.wait_for(state="visible", timeout=2_000)
            button.scroll_into_view_if_needed(timeout=5_000)
            return button
    except Exception:
        pass

    for selector in (
        '[data-testid="stSidebarCollapsedControl"]',
        'button[data-testid="stSidebarCollapseButton"]',
    ):
        toggle = frame.locator(selector)
        try:
            if toggle.count() and toggle.first.is_visible():
                toggle.first.click(timeout=5_000)
                break
        except Exception:
            continue

    sidebar.wait_for(state="visible", timeout=10_000)
    button = frame.get_by_role("button", name="Lock / Logout Workspace").first
    button.wait_for(state="visible", timeout=10_000)
    button.scroll_into_view_if_needed(timeout=5_000)
    return button


def take_evidence_screenshot(page, path: Path) -> None:
    """Capture viewport evidence without letting a long page fail functional tests."""
    try:
        page.screenshot(path=str(path), full_page=False, timeout=10_000)
    except Exception as exc:
        print(f"[WARN] Evidence screenshot skipped ({type(exc).__name__}); functional checks remain authoritative.")


def main() -> int:
    try:
        target_url = validate_app_from_env()
    except ValueError as exc:
        print(f"[FAIL] Staging safety preflight: {exc}", file=sys.stderr)
        return 2

    username = os.environ.get("SHOIR_E2E_ACTIVE_USERNAME", "").strip()
    password = os.environ.get("SHOIR_E2E_ACTIVE_PASSWORD", "")
    if not username.casefold().startswith(PREFIX) or not password:
        print(f"Active browser test credentials are required, and username must start with {PREFIX!r}.", file=sys.stderr)
        return 2

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []

    def check(name: str, passed: bool, detail: str) -> None:
        cases.append({"case": name, "status": "PASS" if passed else "FAIL", "detail": detail})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {detail}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page = context.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(type(error).__name__))
        step = "load public application"
        try:
            response = page.goto(target_url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(8000)
            step = "find sign-in application frame"
            frames = list(page.frames)
            app_frame = None
            for frame in frames:
                try:
                    text = frame.locator("body").inner_text(timeout=4000)
                except Exception:
                    continue
                if "Sign In to Your Workspace" in text or "Welcome to Shoir-IE, " in text:
                    app_frame = frame
                    break
            check("public_shell_loads", response is not None and response.status == 200 and app_frame is not None,
                  "Public application frame and sign-in surface found." if app_frame else "App frame/sign-in surface not found.")
            if app_frame is None:
                raise RuntimeError("App frame/sign-in surface not found; refusing to enter test credentials.")
            step = "verify staging environment marker"
            initial_body = app_frame.locator("body").inner_text(timeout=8_000)
            is_staging = "STAGING TEST ENVIRONMENT" in initial_body
            check("staging_environment_marker", is_staging,
                  "App declared staging before credentials were entered." if is_staging else "Staging marker is missing; credentials were not submitted.")
            if not is_staging:
                raise RuntimeError("Staging marker missing; refusing to submit test credentials to a possibly production-backed app.")

            if CANDIDATE_BUILD_MARKER not in initial_body:
                version_match = re.search(r"SHOIR-IE SHELL VERSION:\s*([^\s—·]+)", initial_body)
                observed_version = version_match.group(1) if version_match else "not reported"
                raise RuntimeError(
                    f"Staging app serves shell version {observed_version}; expected "
                    f"{CANDIDATE_BUILD_MARKER}. The candidate preflight must pass before credentials are submitted."
                )

            check("candidate_shell_build", True, f"Candidate marker {CANDIDATE_BUILD_MARKER!r} is visible before sign-in.")
            step = "select sign-in tab"
            signin_tab = app_frame.get_by_role("tab", name=re.compile("Sign In", re.I))
            signin_tab.click(timeout=10_000)
            step = "locate and fill sign-in inputs"
            fill_signin_credentials(app_frame, username, password)
            step = "submit sign-in credentials"
            app_frame.get_by_role("button", name=re.compile("^Sign In$", re.I)).click(timeout=10_000)
            step = "wait for authenticated workspace"
            app_frame.get_by_role("button", name="Lock / Logout Workspace").first.wait_for(timeout=60_000)
            step = "verify candidate shell build marker"
            marker_deadline = time.monotonic() + 10
            active_module_text = ""
            while time.monotonic() < marker_deadline:
                active_module_text = read_active_module_label(app_frame)
                if re.match(r"^\s*Active module:\s*.+$", active_module_text, re.I):
                    break
                page.wait_for_timeout(250)
            if not re.match(r"^\s*Active module:\s*.+$", active_module_text, re.I):
                raise RuntimeError(
                    "Staging app does not contain the candidate shell marker; deploy branch "
                    "staging-e2e-20261019 before rerunning this gate."
                )
            step = "verify authenticated home"
            logged_body = app_frame.locator("body").inner_text(timeout=8000)
            check("authenticated_workspace_renders", username.casefold() in logged_body.casefold()
                  and "SHOIR-IE" in logged_body,
                  "Authenticated shell rendered for the dedicated test identity.")
            take_evidence_screenshot(page, REPORT.parent / "authenticated-home.png")

            # Navigate to the specific Excel Data Cleaning & Import module via
            # the global module search. The UI requires Enter to apply searches;
            # the generic "Open Excel Intelligence" home CTA is not a reliable
            # assertion that this exact module route was opened.
            step = "search for Excel Data Cleaning & Import module"
            search = app_frame.get_by_placeholder(
                re.compile("Search modules, datasets, runs, decisions", re.I)
            )
            search.fill("Excel Data Cleaning & Import", timeout=10_000)
            search.press("Enter", timeout=10_000)
            open_excel = app_frame.get_by_role(
                "button",
                name=re.compile(r"^Open\s*[·•]\s*Excel Data Cleaning & Import$", re.I),
            )
            step = "open Excel Data Cleaning & Import module"
            open_excel.wait_for(state="visible", timeout=20_000)
            open_excel.click(timeout=10_000)
            step = "verify Excel Data Cleaning & Import is the active module"
            active_excel = re.compile(
                r"Active module:\s*Excel Data Cleaning & Import(?=\s|·|$)", re.I
            )
            active_module_text = ""
            active_deadline = time.monotonic() + 45
            while time.monotonic() < active_deadline:
                try:
                    active_module_text = read_active_module_label(app_frame)
                except Exception:
                    active_module_text = ""
                if active_excel.search(active_module_text):
                    break
                page.wait_for_timeout(350)
            main_body = app_frame.get_by_role("main").inner_text(timeout=8_000)
            excel_is_active = bool(active_excel.search(active_module_text))
            check(
                "excel_module_renders",
                excel_is_active and "Traceback (most recent call last)" not in main_body,
                "Explicit shell marker confirms Excel Data Cleaning & Import."
                if excel_is_active else
                f"Excel search result did not navigate; active shell marker was {active_module_text[:120]!r}.",
            )
            take_evidence_screenshot(page, REPORT.parent / "authenticated-excel-module.png")

            # Verify genuine sign-out by waiting for the public sign-in heading.
            step = "click sidebar logout"
            visible_logout_button(app_frame).click(timeout=15_000)
            step = "verify unauthenticated sign-in after logout"
            try:
                app_frame.get_by_text(
                    re.compile(r"Sign In to Your Workspace", re.I)
                ).first.wait_for(state="visible", timeout=45_000)
            except Exception as exc:
                visible_body = app_frame.locator("body").inner_text(timeout=5_000).casefold()
                if "server logout could not revoke this session" in visible_body:
                    raise RuntimeError("App refused logout because server-side session revocation failed.") from exc
                if "lock / logout workspace" in visible_body:
                    raise RuntimeError("Logout click left the authenticated workspace visible.") from exc
                raise RuntimeError("Logout did not return to the sign-in screen; inspect staging deployment/evidence.") from exc
            signed_out_body = app_frame.locator("body").inner_text(timeout=8_000)
            signed_out = (
                "Sign In to Your Workspace" in signed_out_body
                and username.casefold() not in signed_out_body.casefold()
                and "Lock / Logout Workspace" not in signed_out_body
            )
            check(
                "sidebar_logout_returns_to_signin",
                signed_out,
                "Logout returned to the unauthenticated sign-in screen."
                if signed_out else "Sign-in heading or cleared-session indicators were missing.",
            )
        except Exception as exc:
            # Keep diagnostics safe: never print credentials, response bodies, or input values.
            detail = f"Browser step '{step}' failed ({type(exc).__name__})."
            if step == "wait for authenticated workspace" and app_frame is not None:
                try:
                    visible_body = app_frame.locator("body").inner_text(timeout=3_000).casefold()
                    if "invalid username or password" in visible_body:
                        detail = (
                            "Sign-in was submitted, but the staging app remained unauthenticated and displayed "
                            "its generic credential/authentication rejection. Verify the disposable account/password "
                            "and the Streamlit staging Supabase configuration."
                        )
                    elif "too many failed sign-in attempts" in visible_body:
                        detail = (
                            "The staging app's login-throttle message appeared. Do not keep retrying; verify the "
                            "dedicated test account and clear/wait out the test limiter through the approved process."
                        )
                except Exception:
                    pass
            check("browser_walkthrough", False, detail)
        finally:
            check("no_uncaught_javascript_errors", not page_errors,
                  "No uncaught JavaScript errors." if not page_errors else f"{len(page_errors)} uncaught JavaScript error(s).")
            try:
                browser.close()
            except Exception:
                pass

    REPORT.write_text(json.dumps({
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": URL,
        "account_class": "dedicated non-admin e2e account",
        "overall": "PASS" if all(c["status"] == "PASS" for c in cases) else "FAIL",
        "cases": cases,
    }, indent=2), encoding="utf-8")
    return 0 if all(c["status"] == "PASS" for c in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
