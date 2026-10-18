"""Headless browser smoke test for the public Shoir-IE Streamlit entry screen.

This deliberately uses no account credentials and never mutates production data.
It verifies only the unauthenticated entry surface; authenticated module flows
remain a separate acceptance test that requires authorized test credentials.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


URL = os.environ.get("SHOIR_LIVE_URL", "https://shoir-ie-app.streamlit.app/")
OUTPUT = Path("artifacts/live-deployment-smoke")
VIEWPORTS = (
    ("desktop", {"width": 1440, "height": 1000}),
    ("mobile", {"width": 390, "height": 844}),
)
APP_MARKERS = (
    "Shoir-IE",
    "Welcome to Shoir-IE Workspace",
    "Sign In to Your Workspace",
    "Industrial Engineering Workbench",
    "Industrial Control Center",
)
FATAL_TEXT_MARKERS = (
    "application runtime could not be loaded",
    "modulenotfounderror",
    "nameerror:",
    "traceback (most recent call last)",
    "internal server error",
    "operationalerror:",
)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "target": URL,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall": "FAIL",
        "scope": "public unauthenticated entry screen only",
        "authenticated_module_checks": "NOT RUN: no authorized test credentials supplied to CI",
        "viewports": [],
    }
    overall_ok = True

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for label, viewport in VIEWPORTS:
                    page = browser.new_page(viewport=viewport)
                    page_errors: list[str] = []
                    console_errors: list[str] = []
                    failed_http_responses: list[dict] = []
                    page.on("pageerror", lambda error: page_errors.append(str(error)))
                    page.on(
                        "console",
                        lambda message: console_errors.append(message.text[:500])
                        if message.type == "error" and len(console_errors) < 20
                        else None,
                    )

                    def record_failed_response(response):
                        if response.status >= 400 and len(failed_http_responses) < 50:
                            failed_http_responses.append({
                                "status": response.status,
                                "url": response.url,
                                "resource_type": response.request.resource_type,
                            })

                    page.on("response", record_failed_response)
                    item = {
                        "viewport": label,
                        "width": viewport["width"],
                        "height": viewport["height"],
                        "http_status": None,
                        "page_title": "",
                        "app_marker_found": False,
                        "fatal_error_marker_found": False,
                        "uncaught_javascript_errors": page_errors,
                        "console_errors_sample": console_errors,
                        "horizontal_overflow": None,
                        "screenshot": str(OUTPUT / f"{label}.png"),
                        "result": "FAIL",
                        "failure_reasons": [],
                    }
                    try:
                        response = page.goto(
                            URL, wait_until="domcontentloaded", timeout=90_000
                        )
                        item["http_status"] = response.status if response else None
                        # Streamlit renders its app after the initial HTML response.
                        page.wait_for_timeout(8_000)
                        item["page_title"] = page.title()
                        # Streamlit-hosted applications may render their
                        # app surface in a child frame. Inspect every accessible
                        # frame rather than only the outer hosting document.
                        frame_records = []
                        rendered_bodies = []
                        app_frame = None
                        for frame in page.frames:
                            try:
                                frame_body = frame.locator("body").inner_text(timeout=5_000)
                            except Exception as frame_error:
                                frame_records.append({
                                    "url": frame.url,
                                    "body_length": 0,
                                    "body_preview": "",
                                    "read_error": type(frame_error).__name__,
                                })
                                continue
                            if frame_body:
                                rendered_bodies.append(frame_body)
                            if (
                                "welcome to shoir-ie workspace" in frame_body.casefold()
                                or "shoir-ie industrial engineering command center" in frame_body.casefold()
                            ):
                                app_frame = frame
                            frame_records.append({
                                "url": frame.url,
                                "body_length": len(frame_body),
                                "body_preview": " ".join(frame_body.split())[:300],
                            })
                        body = "\n".join(rendered_bodies)
                        folded_body = body.casefold()
                        item["frames"] = frame_records
                        item["rendered_text_length"] = len(body)
                        item["rendered_text_preview"] = " ".join(body.split())[:500]
                        item["app_marker_found"] = any(
                            marker.casefold() in folded_body for marker in APP_MARKERS
                        )
                        item["fatal_error_marker_found"] = any(
                            marker in folded_body for marker in FATAL_TEXT_MARKERS
                        )

                        # Exercise public tabs only; do not sign in, submit forms,
                        # register accounts or write production data.
                        tab_checks = []
                        if app_frame is not None:
                            scenarios = [
                                (
                                    "subscription-registration-tab",
                                    re.compile(r"Get Ticket\s*&\s*Register", re.I),
                                    re.compile(r"Get Subscription Ticket\s*&\s*Register", re.I),
                                ),
                                (
                                    "public-module-explorer-tab",
                                    re.compile(r"Explore the Modules", re.I),
                                    re.compile(r"Turn hard industrial decisions into clear next moves", re.I),
                                ),
                            ]
                            for check_name, tab_name, content_marker in scenarios:
                                check = {"name": check_name, "result": "FAIL", "failure_reason": ""}
                                try:
                                    app_frame.get_by_role("tab", name=tab_name).click(timeout=8_000)
                                    app_frame.get_by_text(content_marker).wait_for(timeout=10_000)
                                    check["result"] = "PASS"
                                except Exception as tab_error:
                                    check["failure_reason"] = (
                                        f"{type(tab_error).__name__}: {str(tab_error)[:300]}"
                                    )
                                    item["failure_reasons"].append(
                                        f"Public tab {check_name} did not render its expected content."
                                    )
                                tab_checks.append(check)
                            try:
                                app_frame.get_by_role(
                                    "tab", name=re.compile(r"Sign In", re.I)
                                ).click(timeout=5_000)
                            except Exception:
                                pass
                        else:
                            item["failure_reasons"].append(
                                "Could not locate the Streamlit frame containing the public app."
                            )
                            tab_checks.append({
                                "name": "public-tabs",
                                "result": "FAIL",
                                "failure_reason": "Shoir-IE application frame not located.",
                            })
                        item["public_tab_checks"] = tab_checks
                        dimensions = page.evaluate(
                            """() => ({
                                innerWidth: window.innerWidth,
                                documentScrollWidth: document.documentElement.scrollWidth,
                                bodyScrollWidth: document.body ? document.body.scrollWidth : 0
                            })"""
                        )
                        item["dimensions"] = dimensions
                        item["horizontal_overflow"] = (
                            dimensions["documentScrollWidth"] > dimensions["innerWidth"] + 8
                            or dimensions["bodyScrollWidth"] > dimensions["innerWidth"] + 8
                        )
                        page.screenshot(
                            path=item["screenshot"], full_page=True, timeout=30_000
                        )

                        if response is None:
                            item["failure_reasons"].append("Navigation returned no HTTP response.")
                        elif response.status < 200 or response.status >= 400:
                            item["failure_reasons"].append(
                                f"Unexpected HTTP status {response.status}."
                            )
                        if not item["app_marker_found"]:
                            item["failure_reasons"].append(
                                "Expected Shoir-IE application text was not rendered."
                            )
                        if item["fatal_error_marker_found"]:
                            item["failure_reasons"].append(
                                "A known startup/runtime error marker appeared in page text."
                            )
                        if page_errors:
                            item["failure_reasons"].append(
                                f"{len(page_errors)} uncaught browser exception(s) occurred."
                            )
                        if item["horizontal_overflow"]:
                            item["failure_reasons"].append(
                                "The page content exceeds the viewport width."
                            )
                    except (PlaywrightError, Exception) as error:
                        item["failure_reasons"].append(
                            f"Browser navigation or rendering failed: {type(error).__name__}: {error}"
                        )
                        try:
                            page.screenshot(
                                path=item["screenshot"], full_page=True, timeout=10_000
                            )
                        except Exception:
                            pass
                    item["failed_http_responses"] = failed_http_responses
                    item["result"] = "PASS" if not item["failure_reasons"] else "FAIL"
                    overall_ok = overall_ok and item["result"] == "PASS"
                    report["viewports"].append(item)
                    page.close()
            finally:
                browser.close()
    except Exception as error:
        overall_ok = False
        report["browser_setup_error"] = f"{type(error).__name__}: {error}"

    report["overall"] = "PASS" if overall_ok else "FAIL"
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report_path = OUTPUT / "result.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
