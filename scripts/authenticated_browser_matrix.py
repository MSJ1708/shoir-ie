#!/usr/bin/env python3
"""Authenticated Streamlit shell/module smoke using a dedicated non-admin test user."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

from staging_e2e_guard import validate_app_from_env

REPORT = Path(os.environ.get("SHOIR_E2E_UI_REPORT", "artifacts/authenticated-release-gate/browser-report.json"))
PREFIX = "shoir-e2e-"
URL = os.environ.get("SHOIR_E2E_APP_URL", "").strip()


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

            step = "select sign-in tab"
            signin_tab = app_frame.get_by_role("tab", name=re.compile("Sign In", re.I))
            signin_tab.click(timeout=10_000)
            step = "locate and fill sign-in inputs"
            fill_signin_credentials(app_frame, username, password)
            step = "submit sign-in credentials"
            app_frame.get_by_role("button", name=re.compile("^Sign In$", re.I)).click(timeout=10_000)
            step = "wait for authenticated workspace"
            app_frame.get_by_role("button", name="Lock / Logout Workspace").first.wait_for(timeout=60_000)
            step = "verify authenticated home"
            logged_body = app_frame.locator("body").inner_text(timeout=8000)
            check("authenticated_workspace_renders", username.casefold() in logged_body.casefold()
                  and "SHOIR-IE" in logged_body,
                  "Authenticated shell rendered for the dedicated test identity.")
            page.screenshot(path=str(REPORT.parent / "authenticated-home.png"), full_page=True)

            # The home action selects the canonical Excel module route without changing saved data.
            open_excel = app_frame.get_by_role("button", name=re.compile("Open Excel Intelligence", re.I))
            if open_excel.count():
                open_excel.first.click(timeout=10_000)
            else:
                search = app_frame.get_by_placeholder(re.compile("Excel, forecasting, quality, MILP", re.I))
                search.fill("Excel Data Cleaning & Import")
                app_frame.get_by_role("button", name=re.compile("Open.*Excel Data Cleaning", re.I)).first.click(timeout=10_000)
            app_frame.get_by_text(re.compile("Excel Data Cleaning & Import", re.I)).first.wait_for(timeout=45_000)
            module_body = app_frame.locator("body").inner_text(timeout=8000)
            check("excel_module_renders", "Excel Data Cleaning & Import".casefold() in module_body.casefold()
                  and "Traceback (most recent call last)" not in module_body,
                  "Excel module route rendered without a visible traceback.")
            page.screenshot(path=str(REPORT.parent / "authenticated-excel-module.png"), full_page=True)

            # Exercise the sidebar logout action first. It used to set a shell surface
            # that the entrypoint did not process.
            app_frame.get_by_role("button", name="Lock / Logout Workspace").first.click(timeout=10_000)
            app_frame.get_by_role("tab", name=re.compile("Sign In", re.I)).wait_for(timeout=45_000)
            signed_out_body = app_frame.locator("body").inner_text(timeout=8000)
            check("sidebar_logout_returns_to_signin",
                  "Sign In to Your Workspace" in signed_out_body and "shoir-e2e-" not in signed_out_body.casefold(),
                  "Sidebar logout returned to the unauthenticated sign-in screen.")
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
