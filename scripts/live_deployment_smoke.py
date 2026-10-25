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
import time
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
APP_READY_MARKERS = (
    "Welcome to Shoir-IE Workspace",
    "Sign In to Your Workspace",
    "Get Subscription Ticket & Register",
    "Industrial Control Center",
)
SLEEP_PAGE_MARKERS = (
    "this app has gone to sleep due to inactivity",
    "would you like to wake it back up",
)
WAKE_BUTTON = re.compile(r"yes, get this app back up", re.I)


def _visible_text_across_frames(page) -> str:
    """Collect visible body text from the host and all same-origin accessible frames."""
    chunks = []
    for frame in list(page.frames):
        try:
            chunks.append(frame.locator("body").inner_text(timeout=1_000))
        except Exception:
            continue
    return "\n".join(chunks)


def _tab_bar_layout(app_frame) -> dict:
    """Capture tab-list and tab-label geometry so clipped mobile labels fail smoke."""
    tab_list = app_frame.locator('div[data-testid="stTabs"] [data-baseweb="tab-list"]').first
    if tab_list.count() == 0:
        raise AssertionError("Streamlit public tab list was not found.")
    return tab_list.evaluate(
        """element => {
            const listRect = element.getBoundingClientRect();
            const tabs = Array.from(element.querySelectorAll('button[role="tab"]')).map(button => {
                const rect = button.getBoundingClientRect();
                const label = button.querySelector('[data-testid="stMarkdownContainer"]') || button;
                const labelRect = label.getBoundingClientRect();
                return {
                    label: (button.innerText || button.textContent || '').trim(),
                    left: rect.left,
                    right: rect.right,
                    top: rect.top,
                    bottom: rect.bottom,
                    clientWidth: button.clientWidth,
                    scrollWidth: button.scrollWidth,
                    clientHeight: button.clientHeight,
                    scrollHeight: button.scrollHeight,
                    labelLeft: labelRect.left,
                    labelRight: labelRect.right,
                    labelClientWidth: label.clientWidth,
                    labelScrollWidth: label.scrollWidth,
                    labelClientHeight: label.clientHeight,
                    labelScrollHeight: label.scrollHeight,
                    whiteSpace: getComputedStyle(button).whiteSpace,
                    labelWhiteSpace: getComputedStyle(label).whiteSpace
                };
            });
            return {
                viewportWidth: window.innerWidth,
                listLeft: listRect.left,
                listRight: listRect.right,
                listWidth: listRect.width,
                clientWidth: element.clientWidth,
                scrollWidth: element.scrollWidth,
                scrollLeft: element.scrollLeft,
                tabCount: tabs.length,
                tabs
            };
        }"""
    )


def _validate_tab_bar_layout(layout: dict, viewport_width: int) -> None:
    """Fail on a horizontally scrollable tab strip or clipped/overflowing labels."""
    if layout.get("tabCount", 0) < 3:
        raise AssertionError(f"Expected all three public tabs to render: {layout}")
    if layout["scrollWidth"] > layout["clientWidth"] + 2:
        raise AssertionError(f"Public tab list requires horizontal scrolling: {layout}")
    for tab in layout["tabs"]:
        if tab["left"] < layout["listLeft"] - 2 or tab["right"] > layout["listRight"] + 2:
            raise AssertionError(f"Public tab falls outside its tab-list bounds: {tab}")
        if tab["scrollWidth"] > tab["clientWidth"] + 2:
            raise AssertionError(f"Public tab label is horizontally clipped: {tab}")
        if tab["scrollHeight"] > tab["clientHeight"] + 2:
            raise AssertionError(f"Public tab label is vertically clipped: {tab}")
        if tab["labelClientWidth"] <= 0 or tab["labelClientHeight"] <= 0:
            raise AssertionError(f"Public tab label has no visible layout box: {tab}")
        if tab["labelScrollWidth"] > tab["labelClientWidth"] + 2:
            raise AssertionError(f"Inner public tab label is horizontally clipped: {tab}")
        if tab["labelScrollHeight"] > tab["labelClientHeight"] + 2:
            raise AssertionError(f"Inner public tab label is vertically clipped: {tab}")
        if tab["labelLeft"] < tab["left"] - 2 or tab["labelRight"] > tab["right"] + 2:
            raise AssertionError(f"Public tab label extends beyond its button: {tab}")
        if tab["labelRight"] > layout["listRight"] + 2:
            raise AssertionError(f"Public tab label extends beyond the visible tab-list: {tab}")
    if viewport_width <= 600 and any(
        tab["whiteSpace"] == "nowrap" or tab["labelWhiteSpace"] == "nowrap"
        for tab in layout["tabs"]
    ):
        raise AssertionError(f"Mobile tab labels are configured not to wrap: {layout}")


def _wake_if_sleeping(page, *, timeout_seconds: int = 150) -> dict:
    """Detect and wake an idle Streamlit app without masking a failed startup."""
    # The public sleeping interstitial can load shortly after DOMContentLoaded;
    # poll for it instead of checking only once before the host frame hydrates.
    detection_deadline = time.monotonic() + 20
    body = ""
    folded = ""
    while time.monotonic() < detection_deadline:
        body = _visible_text_across_frames(page)
        folded = body.casefold()
        if any(marker in folded for marker in SLEEP_PAGE_MARKERS):
            break
        if any(marker.casefold() in folded for marker in APP_READY_MARKERS):
            return {"sleep_screen_seen": False, "wake_clicked": False, "wake_result": "APP_ALREADY_READY"}
        page.wait_for_timeout(500)
    else:
        return {
            "sleep_screen_seen": False,
            "wake_clicked": False,
            "wake_result": "SLEEP_SCREEN_NOT_SEEN_DURING_DETECTION",
        }

    clicked = False
    click_errors = []
    for locator in (
        page.get_by_role("button", name=WAKE_BUTTON),
        page.get_by_text(WAKE_BUTTON),
    ):
        try:
            locator.first.click(timeout=5_000)
            clicked = True
            break
        except Exception as exc:
            click_errors.append(type(exc).__name__)
    if not clicked:
        raise RuntimeError(
            "Streamlit displayed its sleep screen, but the wake control could not be clicked. "
            f"Attempts: {', '.join(click_errors)}"
        )

    deadline = time.monotonic() + max(10, int(timeout_seconds))
    while time.monotonic() < deadline:
        page.wait_for_timeout(1_000)
        body = _visible_text_across_frames(page)
        folded = body.casefold()
        if any(marker.casefold() in folded for marker in APP_READY_MARKERS):
            return {
                "sleep_screen_seen": True,
                "wake_clicked": True,
                "wake_result": "APP_READY_AFTER_WAKE",
            }
        if not any(marker in folded for marker in SLEEP_PAGE_MARKERS) and body.strip():
            # Let the regular readiness loop decide whether this is the app or
            # a transient shell; only record that the sleep interstitial cleared.
            return {
                "sleep_screen_seen": True,
                "wake_clicked": True,
                "wake_result": "SLEEP_SCREEN_CLEARED",
            }
    raise RuntimeError(
        f"Streamlit app did not wake into an accessible page within {timeout_seconds} seconds."
    )
FATAL_TEXT_MARKERS = (
    "application runtime could not be loaded",
    "this app has encountered an error.",
    "importerror",
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
                        # Community Cloud sleeps after inactivity. Wake it through its
                        # public UI and then test the real app frame; do not classify a
                        # wake-screen HTTP 200 as a successful application render.
                        item["wake_check"] = _wake_if_sleeping(page)
                        # Streamlit can briefly render only its static header before the
                        # application body hydrates. Do not treat generic product/sidebar
                        # text as readiness: wait for a real sign-in/welcome surface, and
                        # require the same frame to expose it in consecutive polls.
                        item["page_title"] = page.title()
                        frame_records = []
                        rendered_bodies = []
                        app_frame = None
                        stable_frame_key = None
                        stable_observations = 0
                        readiness_deadline = time.monotonic() + 45
                        while time.monotonic() < readiness_deadline:
                            current_records = []
                            current_bodies = []
                            ready_candidates = []
                            fatal_marker_seen = False
                            for candidate_frame in list(page.frames):
                                try:
                                    candidate_body = candidate_frame.locator("body").inner_text(
                                        timeout=1_000
                                    )
                                except Exception as frame_error:
                                    current_records.append({
                                        "url": candidate_frame.url,
                                        "body_length": 0,
                                        "body_preview": "",
                                        "read_error": type(frame_error).__name__,
                                    })
                                    continue
                                if candidate_body:
                                    current_bodies.append(candidate_body)
                                folded_candidate_body = candidate_body.casefold()
                                if any(
                                    marker in folded_candidate_body
                                    for marker in FATAL_TEXT_MARKERS
                                ):
                                    fatal_marker_seen = True
                                if any(
                                    marker.casefold() in folded_candidate_body
                                    for marker in APP_READY_MARKERS
                                ):
                                    ready_candidates.append(candidate_frame)
                                current_records.append({
                                    "url": candidate_frame.url,
                                    "body_length": len(candidate_body),
                                    "body_preview": " ".join(candidate_body.split())[:300],
                                })
                            frame_records = current_records
                            rendered_bodies = current_bodies
                            if fatal_marker_seen:
                                break
                            candidate = ready_candidates[0] if ready_candidates else None
                            if candidate is not None:
                                candidate_key = (candidate.url, candidate.name)
                                if candidate_key == stable_frame_key:
                                    stable_observations += 1
                                else:
                                    stable_frame_key = candidate_key
                                    stable_observations = 1
                                if stable_observations >= 2:
                                    app_frame = candidate
                                    break
                            else:
                                stable_frame_key = None
                                stable_observations = 0
                            page.wait_for_timeout(500)
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
                                {
                                    "name": "subscription-registration-tab",
                                    "tab": re.compile(r"Get Ticket\s*&\s*Register", re.I),
                                    "marker": re.compile(r"Get Subscription Ticket\s*&\s*Register", re.I),
                                    "fields": [
                                        "Choose Subscription Tier",
                                        "Name / Username",
                                        "Email Address",
                                        "Password",
                                        "Activation / Ticket Code",
                                    ],
                                    "extra_markers": [re.compile(r"Legal & Privacy", re.I)],
                                },
                                {
                                    "name": "public-module-explorer-tab",
                                    "tab": re.compile(r"Explore the Modules", re.I),
                                    "marker": re.compile(r"Turn hard industrial decisions into clear next moves", re.I),
                                    "fields": [],
                                    "extra_markers": [
                                        re.compile(r"Venture Studio", re.I),
                                        re.compile(r"Why industrial teams are moving this way", re.I),
                                        re.compile(r"ShadowShift", re.I),
                                        re.compile(r"Enterprise Plus", re.I),
                                        re.compile(r"Research Pack", re.I),
                                    ],
                                },
                            ]
                            for scenario in scenarios:
                                check_name = scenario["name"]
                                check = {
                                    "name": check_name,
                                    "result": "FAIL",
                                    "failure_reason": "",
                                    "expected_fields": scenario["fields"],
                                    "missing_fields": [],
                                    "missing_extra_markers": [],
                                }
                                try:
                                    app_frame.get_by_role("tab", name=scenario["tab"]).click(timeout=8_000)
                                    app_frame.get_by_text(scenario["marker"]).wait_for(timeout=10_000)
                                    tab_layout = _tab_bar_layout(app_frame)
                                    check["tab_bar_layout"] = tab_layout
                                    _validate_tab_bar_layout(tab_layout, viewport["width"])
                                    # Tab clicks trigger a Streamlit websocket rerun. Wait for
                                    # the expected form controls/content to attach before asserting;
                                    # immediate locator.count() calls can race that rerun on mobile.
                                    field_locators = {
                                        field_label: app_frame.get_by_label(field_label)
                                        for field_label in scenario["fields"]
                                    }
                                    extra_locators = {
                                        extra_marker.pattern: app_frame.get_by_text(extra_marker)
                                        for extra_marker in scenario["extra_markers"]
                                    }
                                    readiness_deadline = time.monotonic() + 12
                                    while time.monotonic() < readiness_deadline:
                                        expected_locators = [
                                            *field_locators.values(),
                                            *extra_locators.values(),
                                        ]
                                        if all(locator.count() > 0 for locator in expected_locators):
                                            break
                                        page.wait_for_timeout(500)
                                    check["missing_fields"] = [
                                        field_label
                                        for field_label, locator in field_locators.items()
                                        if locator.count() == 0
                                    ]
                                    check["missing_extra_markers"] = [
                                        marker_pattern
                                        for marker_pattern, locator in extra_locators.items()
                                        if locator.count() == 0
                                    ]
                                    if check_name == "public-module-explorer-tab":
                                        plus_card_count = app_frame.locator("div.value-strip").filter(
                                            has_text=re.compile(r"Enterprise Plus", re.I)
                                        ).count()
                                        check["enterprise_plus_plan_card_count"] = plus_card_count
                                        if plus_card_count < 1:
                                            check["missing_extra_markers"].append("Enterprise Plus plan comparison card")
                                    if check["missing_fields"] or check["missing_extra_markers"]:
                                        raise AssertionError(
                                            "Missing fields/markers: "
                                            + ", ".join(check["missing_fields"] + check["missing_extra_markers"])
                                        )
                                    tab_text = app_frame.locator("body").inner_text(timeout=5_000)
                                    check["rendered_text_length"] = len(tab_text)
                                    check["rendered_text_preview"] = " ".join(tab_text.split())[:450]
                                    frame_dimensions = app_frame.evaluate(
                                        """() => ({
                                            innerWidth: window.innerWidth,
                                            documentScrollWidth: document.documentElement.scrollWidth,
                                            bodyScrollWidth: document.body ? document.body.scrollWidth : 0,
                                            innerHeight: window.innerHeight,
                                            documentScrollHeight: document.documentElement.scrollHeight
                                        })"""
                                    )
                                    check["app_frame_dimensions"] = frame_dimensions
                                    check["horizontal_overflow"] = (
                                        frame_dimensions["documentScrollWidth"] > frame_dimensions["innerWidth"] + 8
                                        or frame_dimensions["bodyScrollWidth"] > frame_dimensions["innerWidth"] + 8
                                    )
                                    if check["horizontal_overflow"]:
                                        raise AssertionError(
                                            f"App frame horizontal overflow at {label}: {frame_dimensions}"
                                        )
                                    screenshot_path = OUTPUT / f"{label}-{check_name}.png"
                                    page.screenshot(path=str(screenshot_path), full_page=True, timeout=30_000)
                                    check["screenshot"] = str(screenshot_path)
                                    if check_name == "public-module-explorer-tab":
                                        deep_marker = app_frame.get_by_text(
                                            re.compile(r"Venture Studio", re.I)
                                        ).first
                                        deep_marker.scroll_into_view_if_needed(timeout=8_000)
                                        if not deep_marker.is_visible():
                                            raise AssertionError("Venture Studio section is not visible when scrolled into view.")
                                        deep_screenshot = OUTPUT / f"{label}-public-module-explorer-venture-studio.png"
                                        page.screenshot(path=str(deep_screenshot), full_page=False, timeout=30_000)
                                        check["deep_section_marker"] = "Venture Studio"
                                        check["deep_section_screenshot"] = str(deep_screenshot)
                                        # Restore the top of the app frame for the next screenshot/check.
                                        app_frame.evaluate("window.scrollTo(0, 0)")
                                    check["result"] = "PASS"
                                except Exception as tab_error:
                                    check["failure_reason"] = (
                                        f"{type(tab_error).__name__}: {str(tab_error)[:300]}"
                                    )
                                    item["failure_reasons"].append(
                                        f"Public tab {check_name} did not render its expected content or fields."
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
                        item["host_dimensions"] = dimensions
                        item["app_frame_dimensions"] = (
                            app_frame.evaluate(
                                """() => ({
                                    innerWidth: window.innerWidth,
                                    documentScrollWidth: document.documentElement.scrollWidth,
                                    bodyScrollWidth: document.body ? document.body.scrollWidth : 0
                                })"""
                            )
                            if app_frame is not None
                            else None
                        )
                        host_overflow = (
                            dimensions["documentScrollWidth"] > dimensions["innerWidth"] + 8
                            or dimensions["bodyScrollWidth"] > dimensions["innerWidth"] + 8
                        )
                        frame_overflows = any(
                            bool(check.get("horizontal_overflow"))
                            for check in item.get("public_tab_checks", [])
                        )
                        item["horizontal_overflow"] = host_overflow or frame_overflows
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
