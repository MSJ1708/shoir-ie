#!/usr/bin/env python3
"""Authenticated browser rendering matrix for the complete source module inventory.

This is a route/default-state smoke test, not proof of calculation correctness.
It uses two dedicated, disposable accounts: Enterprise Plus for the base-tier
catalog and Research Pack for the separate research add-on entries. It never
uses the protected administrator identity and never submits forms or uploads
industrial data.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from staging_e2e_guard import validate_app_from_env

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs" / "MODULE_TIER_INVENTORY.csv"
REPORT = Path(os.environ.get("SHOIR_E2E_MODULE_REPORT", "artifacts/authenticated-release-gate/module-matrix-report.json"))
URL = os.environ.get("SHOIR_E2E_APP_URL", "").strip()
PREFIX = "shoir-e2e-"
EXPECTED_TIERS = {
    "Starter", "Mid-Tier Pro", "Professional", "Enterprise",
    "Enterprise Plus", "Research Pack",
}
FATAL_MARKERS = (
    "traceback (most recent call last)",
    "application runtime could not be loaded",
    "modulenotfounderror",
    "importerror:",
    "nameerror:",
    "unboundlocalerror:",
    "operationalerror:",
    "module renderer is not available",
    "module is not available",
    "coming soon",
)
APP_MARKERS = (
    "Sign In to Your Workspace",
    "Welcome to Shoir-IE, ",
    "Welcome to Shoir-IE Workspace",
)
MODULE_SEARCH = re.compile(r"Search modules, datasets, runs, decisions", re.I)
ACTIVE_MODULE_SELECTOR = '[data-testid="shoir-active-module"]'


def read_inventory() -> list[dict[str, str]]:
    with INVENTORY.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"module_name", "minimum_tier", "authenticated_browser_status"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Module inventory is missing columns: {sorted(missing)}")
        rows = list(reader)
    names = [row["module_name"].strip() for row in rows]
    if not rows or any(not name for name in names):
        raise ValueError("Module inventory is empty or includes a blank name.")
    if len(names) != len(set(names)):
        raise ValueError("Module inventory includes duplicate module names.")
    unknown = sorted({row["minimum_tier"].strip() for row in rows}.difference(EXPECTED_TIERS))
    if unknown:
        raise ValueError(f"Module inventory includes unsupported tiers: {unknown}")
    return rows


def require_test_account(username_key: str, password_key: str) -> tuple[str, str]:
    username = os.environ.get(username_key, "").strip()
    password = os.environ.get(password_key, "")
    if not username.casefold().startswith(PREFIX) or not password:
        raise ValueError(
            f"{username_key} and {password_key} must be configured for dedicated {PREFIX}* test identities."
        )
    return username, password


def find_app_frame(page):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        for frame in list(page.frames):
            try:
                body = frame.locator("body").inner_text(timeout=800)
            except Exception:
                continue
            if any(marker.casefold() in body.casefold() for marker in APP_MARKERS):
                return frame
        page.wait_for_timeout(400)
    return None


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


def active_module_confirmed(main_text: str, module_name: str) -> bool:
    """Only accept an explicit active-module label, not a mention in search results."""
    marker = re.compile(
        r"Active module:\s*" + re.escape(module_name) + r"(?=\s|·|$)",
        re.IGNORECASE,
    )
    return bool(marker.search(main_text))


def fill_signin_credentials(frame, username: str, password: str) -> None:
    """Fill visible Streamlit sign-in inputs without relying on label association.

    Streamlit's generated labels are not consistently connected to native inputs
    via accessible-name metadata. Select only visible text/password inputs, fail
    closed unless each is unique, and never guess at hidden registration controls.
    """
    # Streamlit reruns after switching tabs. Wait for the selected tab's
    # controls to finish rendering before counting them; an immediate count()
    # can observe zero inputs during the rerun even though the controls appear
    # moments later.
    frame.get_by_role("button", name=re.compile(r"^Sign In$", re.I)).wait_for(
        state="visible", timeout=10_000
    )
    username_inputs = frame.locator("input[type='text']:visible")
    password_inputs = frame.locator("input[type='password']:visible")
    try:
        username_inputs.first.wait_for(state="visible", timeout=10_000)
        password_inputs.first.wait_for(state="visible", timeout=10_000)
    except PlaywrightError as exc:
        raise RuntimeError(
            "Sign-in inputs did not finish rendering after selecting the Sign In tab."
        ) from exc
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


def login_test_account(page, account_class: str, username: str, password: str) -> Any:
    response = page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
    if response is None or response.status != 200:
        raise RuntimeError(f"{account_class}: public app navigation did not return HTTP 200.")
    frame = find_app_frame(page)
    if frame is None:
        raise RuntimeError(f"{account_class}: sign-in application frame was not found; test credentials were not submitted.")
    initial_body = frame.locator("body").inner_text(timeout=8_000)
    if "STAGING TEST ENVIRONMENT" not in initial_body:
        raise RuntimeError(f"{account_class}: staging marker is missing; refusing to submit credentials to a possibly production-backed app.")
    frame.get_by_role("tab", name=re.compile("Sign In", re.I)).click(timeout=10_000)
    fill_signin_credentials(frame, username, password)
    frame.get_by_role("button", name=re.compile("^Sign In$", re.I)).click(timeout=10_000)
    frame.get_by_role("button", name="Lock / Logout Workspace").first.wait_for(timeout=60_000)
    marker_deadline = time.monotonic() + 10
    active_label = ""
    while time.monotonic() < marker_deadline:
        active_label = read_active_module_label(frame)
        if re.match(r"^\s*Active module:\s*.+$", active_label, re.I):
            break
        page.wait_for_timeout(250)
    if not re.match(r"^\s*Active module:\s*.+$", active_label, re.I):
        raise RuntimeError(
            "Staging app is missing the candidate shell active-module marker; deploy the updated "
            "staging-e2e-20261019 branch before running the authenticated release gate."
        )
    return frame


def route_module(page, frame, module_name: str, account_class: str) -> dict[str, Any]:
    case: dict[str, Any] = {
        "case_id": f"MODULE-ROUTE-{account_class.upper()}",
        "module_name": module_name,
        "account_class": account_class,
        "status": "FAIL",
        "method": "authenticated global module search → Open module",
        "main_text_length": 0,
        "horizontal_overflow": None,
        "fatal_markers": [],
        "failure_reason": "",
    }
    try:
        search = frame.get_by_placeholder(MODULE_SEARCH)
        open_button = None
        last_click_error = None
        for attempt in range(2):
            if active_module_confirmed(read_active_module_label(frame), module_name):
                break
            search.fill(module_name, timeout=10_000)
            # The live input explicitly says "Press Enter to apply". Streamlit's
            # search state is not committed by fill() alone.
            search.press("Enter", timeout=10_000)
            open_button = frame.get_by_role(
                "button",
                name=re.compile(r"^Open\s*[·•]\s*" + re.escape(module_name) + r"$", re.I),
            )
            open_button.wait_for(state="visible", timeout=12_000)
            open_button.scroll_into_view_if_needed(timeout=5_000)
            try:
                open_button.click(timeout=15_000)
                last_click_error = None
                break
            except PlaywrightError as exc:
                # Streamlit may rerun while the click is being acknowledged.
                # Accept only if the shell actually switched to this exact route;
                # otherwise retry once and preserve a hard failure if it did not.
                if active_module_confirmed(read_active_module_label(frame), module_name):
                    last_click_error = None
                    break
                last_click_error = exc
                if attempt == 0:
                    page.wait_for_timeout(500)
        if last_click_error is not None:
            raise last_click_error

        main = frame.get_by_role("main")
        deadline = time.monotonic() + 45
        main_text = ""
        active_text = ""
        while time.monotonic() < deadline:
            try:
                main_text = main.inner_text(timeout=1_500)
            except Exception:
                main_text = ""
            try:
                active_text = read_active_module_label(frame)
            except Exception:
                active_text = ""
            if active_module_confirmed(active_text, module_name):
                break
            page.wait_for_timeout(350)

        case["main_text_length"] = len(main_text)
        case["active_module_label"] = active_text[:160]
        folded = main_text.casefold()
        case["fatal_markers"] = [marker for marker in FATAL_MARKERS if marker in folded]
        case["active_module_confirmed"] = active_module_confirmed(active_text, module_name)
        if not case["active_module_confirmed"]:
            raise AssertionError(
                "The explicit shell active-module marker did not confirm the requested module; "
                "a search result or unrelated module is not sufficient."
            )
        if len(main_text.strip()) < 40:
            raise AssertionError("Main content is effectively blank after module navigation.")
        if case["fatal_markers"]:
            raise AssertionError("Fatal startup/renderer/placeholder marker found in module content.")

        dimensions = frame.evaluate(
            """() => ({
              innerWidth: window.innerWidth,
              documentScrollWidth: document.documentElement.scrollWidth,
              bodyScrollWidth: document.body ? document.body.scrollWidth : 0
            })"""
        )
        case["horizontal_overflow"] = (
            dimensions["documentScrollWidth"] > dimensions["innerWidth"] + 8
            or dimensions["bodyScrollWidth"] > dimensions["innerWidth"] + 8
        )
        case["frame_dimensions"] = dimensions
        if case["horizontal_overflow"]:
            raise AssertionError("Module frame has horizontal overflow.")
        case["status"] = "PASS"
    except Exception as exc:
        case["failure_reason"] = f"{type(exc).__name__}: {str(exc)[:240]}"
        try:
            screenshot_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", module_name).strip("_")[:70]
            image_path = REPORT.parent / f"module-failure-{account_class}-{screenshot_name}.png"
            page.screenshot(path=str(image_path), full_page=True, timeout=10_000)
            case["screenshot"] = str(image_path)
        except Exception:
            pass
    return case


def run_account(browser, account_class: str, username: str, password: str, rows: list[dict[str, str]], cases: list[dict[str, Any]]) -> None:
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=False)
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(type(error).__name__))
    frame = None
    try:
        frame = login_test_account(page, account_class, username, password)
        page.screenshot(path=str(REPORT.parent / f"module-matrix-{account_class}-home.png"), full_page=True)
        body = frame.locator("body").inner_text(timeout=8_000)
        expected_tier = "Enterprise Plus" if account_class == "enterprise_plus" else "Research Pack"
        if expected_tier.casefold() not in body.casefold():
            cases.append({
                "case_id": f"MODULE-TIER-{account_class.upper()}",
                "module_name": None,
                "account_class": account_class,
                "status": "FAIL",
                "failure_reason": f"Authenticated shell did not show the expected {expected_tier} entitlement badge.",
            })
            return

        for row in rows:
            module_name = row["module_name"].strip()
            cases.append(route_module(page, frame, module_name, account_class))
        if page_errors:
            cases.append({
                "case_id": f"MODULE-JS-{account_class.upper()}",
                "module_name": None,
                "account_class": account_class,
                "status": "FAIL",
                "failure_reason": f"{len(page_errors)} uncaught browser exception(s) occurred during module traversal.",
                "exception_types": sorted(set(page_errors)),
            })
    except Exception as exc:
        cases.append({
            "case_id": f"MODULE-ACCOUNT-{account_class.upper()}",
            "module_name": None,
            "account_class": account_class,
            "status": "FAIL",
            "failure_reason": f"{type(exc).__name__}: {str(exc)[:240]}",
        })
    finally:
        if frame is not None:
            try:
                visible_logout_button(frame).click(timeout=15_000)
                try:
                    frame.get_by_text(
                        re.compile(r"Sign In to Your Workspace", re.I)
                    ).wait_for(state="visible", timeout=25_000)
                except Exception as exc:
                    current_body = frame.locator("body").inner_text(timeout=5_000).casefold()
                    if "server logout could not revoke this session" in current_body:
                        raise RuntimeError(
                            "Application refused logout because server-side session revocation failed."
                        ) from exc
                    if "lock / logout workspace" in current_body:
                        raise RuntimeError(
                            "Logout click left the authenticated workspace visible; the app did not clear its session."
                        ) from exc
                    raise RuntimeError(
                        "Logout did not return to the sign-in surface; inspect the saved evidence for the deployed app state."
                    ) from exc
                signed_out_body = frame.locator("body").inner_text(timeout=8_000)
                sign_in_visible = "Sign In to Your Workspace" in signed_out_body
                logout_control_visible = "Lock / Logout Workspace" in signed_out_body
                active_module_visible = bool(
                    re.search(r"Active module:\s*\S", signed_out_body, re.I)
                )
                if not sign_in_visible or logout_control_visible or active_module_visible:
                    raise AssertionError(
                        "Logout did not replace the authenticated shell with sign-in "
                        f"(sign_in_visible={sign_in_visible}, "
                        f"logout_control_visible={logout_control_visible}, "
                        f"active_module_visible={active_module_visible})."
                    )
            except Exception as exc:
                cases.append({
                    "case_id": f"MODULE-LOGOUT-{account_class.upper()}",
                    "module_name": None,
                    "account_class": account_class,
                    "status": "FAIL",
                    "failure_reason": f"{type(exc).__name__}: {str(exc)[:240]}",
                })
        context.close()


def main() -> int:
    global URL
    try:
        URL = validate_app_from_env()
    except ValueError as exc:
        print(f"[FAIL] Staging safety preflight: {exc}", file=sys.stderr)
        return 2

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": URL,
        "scope": "authenticated module route/default-state rendering; not calculation or full data I/O acceptance",
        "overall": "FAIL",
        "module_inventory_count": 0,
        "module_route_cases": 0,
        "cases": [],
    }
    try:
        rows = read_inventory()
        report["module_inventory_count"] = len(rows)
        base_rows = [row for row in rows if row["minimum_tier"].strip() != "Research Pack"]
        research_rows = [row for row in rows if row["minimum_tier"].strip() == "Research Pack"]
        if len(base_rows) + len(research_rows) != len(rows):
            raise ValueError("Inventory partition did not account for every module.")
        report["base_tier_account_case_count"] = len(base_rows)
        report["research_addon_account_case_count"] = len(research_rows)
        plus_user, plus_pass = require_test_account("SHOIR_E2E_MODULE_USERNAME", "SHOIR_E2E_MODULE_PASSWORD")
        research_user, research_pass = require_test_account("SHOIR_E2E_RESEARCH_MODULE_USERNAME", "SHOIR_E2E_RESEARCH_MODULE_PASSWORD")
        all_test_usernames = [
            os.environ.get(name, "").strip().casefold()
            for name in (
                "SHOIR_E2E_ACTIVE_USERNAME",
                "SHOIR_E2E_SECOND_USERNAME",
                "SHOIR_E2E_STARTER_USERNAME",
                "SHOIR_E2E_EXPIRED_USERNAME",
                "SHOIR_E2E_MODULE_USERNAME",
                "SHOIR_E2E_RESEARCH_MODULE_USERNAME",
            )
            if os.environ.get(name, "").strip()
        ]
        if len(all_test_usernames) != len(set(all_test_usernames)):
            raise ValueError("Backend and module-matrix test accounts must be distinct; reuse of an account is refused.")
        if plus_user.casefold() == research_user.casefold():
            raise ValueError("Enterprise Plus and Research Pack module test accounts must be distinct.")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                run_account(browser, "enterprise_plus", plus_user, plus_pass, base_rows, report["cases"])
                run_account(browser, "research_pack", research_user, research_pass, research_rows, report["cases"])
            finally:
                browser.close()
    except Exception as exc:
        report["preflight_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"

    report["module_route_cases"] = sum(case.get("module_name") is not None for case in report["cases"])
    expected = report.get("module_inventory_count", 0)
    seen = [case["module_name"] for case in report["cases"] if case.get("module_name") is not None]
    unique_seen = set(seen)
    report["missing_modules"] = sorted(
        {row["module_name"] for row in locals().get("rows", [])}.difference(unique_seen)
    )
    passed_routes = sum(case.get("status") == "PASS" and case.get("module_name") is not None for case in report["cases"])
    report["passed_module_routes"] = passed_routes
    report["failed_module_routes"] = sum(case.get("status") == "FAIL" and case.get("module_name") is not None for case in report["cases"])
    report["failed_non_route_cases"] = [
        {
            "case_id": case.get("case_id"),
            "account_class": case.get("account_class"),
            "failure_reason": case.get("failure_reason", ""),
        }
        for case in report["cases"]
        if case.get("status") == "FAIL" and case.get("module_name") is None
    ]
    report["failed_route_cases"] = [
        {
            "module_name": case.get("module_name"),
            "account_class": case.get("account_class"),
            "failure_reason": case.get("failure_reason", ""),
            "active_module_label": case.get("active_module_label", ""),
        }
        for case in report["cases"]
        if case.get("status") == "FAIL" and case.get("module_name") is not None
    ]
    report["overall"] = (
        "PASS"
        if expected > 0
        and len(seen) == expected
        and len(unique_seen) == expected
        and passed_routes == expected
        and all(case["status"] == "PASS" for case in report["cases"])
        and not report.get("preflight_error")
        else "FAIL"
    )
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "overall": report["overall"],
        "module_inventory_count": report["module_inventory_count"],
        "module_route_cases": report["module_route_cases"],
        "passed_module_routes": report["passed_module_routes"],
        "failed_module_routes": report["failed_module_routes"],
        "preflight_error": report.get("preflight_error"),
        "missing_modules": report.get("missing_modules"),
        "failed_non_route_cases": report.get("failed_non_route_cases"),
        "failed_route_cases": report.get("failed_route_cases"),
    }, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
