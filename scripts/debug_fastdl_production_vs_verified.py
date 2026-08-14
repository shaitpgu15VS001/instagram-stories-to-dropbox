#!/usr/bin/env python3
"""Debug script to compare production flow vs verified diagnostic flow.

This script replicates the exact production code path from src/fastdl_api.py
and src/story_downloader.py to identify where the divergence occurs.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_URL = "https://api-wh.fastdl.app/api/v1/instagram/stories"
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
OUTPUT_DIR = Path(__file__).resolve().parent / "debug_output" / "fastdl_production_vs_verified"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_production_flow(username: str, output_dir: Path) -> Dict[str, Any]:
    """Replicate the exact production flow from src/fastdl_api.py"""
    run_dir = output_dir / f"production_flow_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    trace: Dict[str, Any] = {
        "flow": "production_path",
        "run_started_at": utc_now(),
        "username": username,
        "viewer_url": VIEWER_URL,
        "stories_api_url": STORIES_API_URL,
        "browser_config": {
            "user_agent": USER_AGENT,
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
            "launch_args": ["--no-sandbox", "--disable-dev-shm-usage"],
        },
        "steps": [],
        "events": {
            "requests": [],
            "responses": [],
            "requestfailed": [],
        },
        "stories_request": None,
        "stories_response": None,
        "success": False,
        "failure_stage": None,
        "failure_reason": None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = context.new_page()
        page.set_default_timeout(60000)

        request_seen = {"value": False, "method": None, "url": None}
        response_seen = {"value": False, "status": None, "url": None, "content_type": None}

        def on_request(req):
            if STORIES_API_PATH in req.url:
                trace["events"]["requests"].append({
                    "method": req.method,
                    "url": req.url,
                    "ts": utc_now(),
                })
                if req.method == "POST":
                    request_seen["value"] = True
                    request_seen["method"] = req.method
                    request_seen["url"] = req.url
                    trace["stories_request"] = {
                        "method": req.method,
                        "url": req.url,
                        "ts": utc_now(),
                    }

        def on_response(resp):
            if STORIES_API_PATH in resp.url:
                trace["events"]["responses"].append({
                    "status": resp.status,
                    "url": resp.url,
                    "content_type": resp.headers.get("content-type"),
                    "ts": utc_now(),
                })
                if resp.request.method == "POST":
                    response_seen["value"] = True
                    response_seen["status"] = resp.status
                    response_seen["url"] = resp.url
                    response_seen["content_type"] = resp.headers.get("content-type") or resp.headers.get("Content-Type")
                    trace["stories_response"] = {
                        "status": resp.status,
                        "url": resp.url,
                        "content_type": response_seen["content_type"],
                        "ts": utc_now(),
                    }

        def on_requestfailed(req):
            if STORIES_API_PATH in req.url:
                trace["events"]["requestfailed"].append({
                    "url": req.url,
                    "method": req.method,
                    "ts": utc_now(),
                })

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_requestfailed)

        try:
            trace["steps"].append({"stage": "page.goto", "ts": utc_now()})
            page.goto(VIEWER_URL, wait_until="domcontentloaded")
            trace["steps"].append({"stage": "page.goto_done", "url": page.url, "ts": utc_now()})

            trace["steps"].append({"stage": "wait_for_search_input", "ts": utc_now()})
            page.wait_for_selector("#search-form-input", state="visible", timeout=30000)
            trace["steps"].append({"stage": "search_input_found", "ts": utc_now()})

            trace["steps"].append({"stage": "popup_cleanup_start", "ts": utc_now()})
            page.evaluate(
                """
                () => {
                    const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                    selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
                }
                """
            )
            trace["steps"].append({"stage": "popup_cleanup_done", "ts": utc_now()})

            trace["steps"].append({"stage": "page.fill_start", "ts": utc_now()})
            page.fill("#search-form-input", username)
            trace["steps"].append({"stage": "page.fill_done", "value_filled": username, "ts": utc_now()})

            trace["steps"].append({"stage": "expect_response_setup", "ts": utc_now()})
            # This is the PRODUCTION flow: using page.expect_response
            with page.expect_response(
                lambda response: STORIES_API_PATH in response.url and response.request.method == "POST",
                timeout=20000,
            ) as response_info:
                trace["steps"].append({"stage": "page.click_start", "ts": utc_now()})
                page.click("#searchFormButton", force=True, timeout=30000)
                trace["steps"].append({"stage": "page.click_done", "ts": utc_now(), "url_after_click": page.url})

                trace["steps"].append({"stage": "waiting_for_expect_response", "ts": utc_now()})
                try:
                    response = response_info.value
                    trace["steps"].append({"stage": "expect_response_succeeded", "status": response.status, "ts": utc_now()})
                    trace["stories_response"]["response_object"] = {
                        "status": response.status,
                        "url": response.url,
                    }
                    trace["success"] = True
                except Exception as exc:
                    trace["failure_stage"] = "expect_response_timeout"
                    trace["failure_reason"] = f"{type(exc).__name__}: {exc}"
                    trace["steps"].append({"stage": "expect_response_failed", "exception": str(exc), "ts": utc_now()})
                    raise

        except Exception as exc:
            trace["failure_stage"] = trace["failure_stage"] or "unknown"
            trace["failure_reason"] = trace["failure_reason"] or f"{type(exc).__name__}: {exc}"
            trace["steps"].append({"stage": "exception_caught", "exception": str(exc), "ts": utc_now()})

        finally:
            browser.close()

    trace["request_seen"] = request_seen
    trace["response_seen"] = response_seen
    trace["run_dir"] = str(run_dir)
    (run_dir / "production_flow_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    return trace


def run_verified_diagnostic_flow(username: str, output_dir: Path) -> Dict[str, Any]:
    """Replicate the working diagnostic flow from debug_fastdl_github_verified_flow.py"""
    run_dir = output_dir / f"diagnostic_flow_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    trace: Dict[str, Any] = {
        "flow": "diagnostic_path",
        "run_started_at": utc_now(),
        "username": username,
        "viewer_url": VIEWER_URL,
        "stories_api_url": STORIES_API_URL,
        "browser_config": {
            "user_agent": USER_AGENT,
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
            "launch_args": ["--no-sandbox", "--disable-dev-shm-usage"],
        },
        "steps": [],
        "events": {
            "requests": [],
            "responses": [],
            "requestfailed": [],
        },
        "stories_request": None,
        "stories_response": None,
        "success": False,
        "failure_stage": None,
        "failure_reason": None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = context.new_page()
        page.set_default_timeout(60000)

        def on_request(req):
            if STORIES_API_PATH in req.url:
                trace["events"]["requests"].append({
                    "method": req.method,
                    "url": req.url,
                    "ts": utc_now(),
                })
                if req.method == "POST":
                    trace["stories_request"] = {
                        "method": req.method,
                        "url": req.url,
                        "ts": utc_now(),
                    }

        def on_response(resp):
            if STORIES_API_PATH in resp.url:
                trace["events"]["responses"].append({
                    "status": resp.status,
                    "url": resp.url,
                    "content_type": resp.headers.get("content-type"),
                    "ts": utc_now(),
                })
                if resp.request.method == "POST":
                    trace["stories_response"] = {
                        "status": resp.status,
                        "url": resp.url,
                        "content_type": resp.headers.get("content-type") or resp.headers.get("Content-Type"),
                        "ts": utc_now(),
                    }

        def on_requestfailed(req):
            if STORIES_API_PATH in req.url:
                trace["events"]["requestfailed"].append({
                    "url": req.url,
                    "method": req.method,
                    "ts": utc_now(),
                })

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_requestfailed)

        try:
            trace["steps"].append({"stage": "page.goto", "ts": utc_now()})
            page.goto(VIEWER_URL, wait_until="domcontentloaded")
            trace["steps"].append({"stage": "page.goto_done", "url": page.url, "ts": utc_now()})

            trace["steps"].append({"stage": "wait_for_search_input", "ts": utc_now()})
            page.wait_for_selector("#search-form-input", state="visible", timeout=30000)
            trace["steps"].append({"stage": "search_input_found", "ts": utc_now()})

            trace["steps"].append({"stage": "popup_cleanup_start", "ts": utc_now()})
            page.evaluate(
                """
                () => {
                    const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                    selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
                }
                """
            )
            trace["steps"].append({"stage": "popup_cleanup_done", "ts": utc_now()})

            trace["steps"].append({"stage": "page.fill_start", "ts": utc_now()})
            page.fill("#search-form-input", username)
            trace["steps"].append({"stage": "page.fill_done", "value_filled": username, "ts": utc_now()})

            trace["steps"].append({"stage": "page.click_start", "ts": utc_now()})
            page.click("#searchFormButton", force=True, timeout=30000)
            trace["steps"].append({"stage": "page.click_done", "ts": utc_now(), "url_after_click": page.url})

            trace["steps"].append({"stage": "post_search_wait_2500ms", "ts": utc_now()})
            page.wait_for_timeout(2500)

            trace["steps"].append({"stage": "second_popup_cleanup", "ts": utc_now()})
            page.evaluate(
                """
                () => {
                    const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                    selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
                }
                """
            )
            page.wait_for_timeout(1000)
            trace["steps"].append({"stage": "second_popup_cleanup_done", "ts": utc_now()})

            trace["steps"].append({"stage": "wait_for_stories_tab", "ts": utc_now()})
            page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
            trace["steps"].append({"stage": "stories_tab_found", "ts": utc_now()})

            trace["steps"].append({"stage": "click_stories_tab", "ts": utc_now()})
            click_result = page.evaluate(
                """
                () => {
                    const buttons = Array.from(document.querySelectorAll('button.tabs-component__button'));
                    for (const button of buttons) {
                        if (button.innerText && button.innerText.toLowerCase().includes('stories')) {
                            button.scrollIntoView();
                            button.click();
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
            trace["steps"].append({"stage": "click_stories_tab_done", "result": click_result, "ts": utc_now()})

            trace["steps"].append({"stage": "manual_wait_for_response", "ts": utc_now()})
            deadline = time.time() + 40
            while time.time() < deadline and not trace["stories_response"]:
                time.sleep(0.5)

            if trace["stories_response"]:
                trace["steps"].append({"stage": "stories_response_received", "status": trace["stories_response"].get("status"), "ts": utc_now()})
                trace["success"] = True
            else:
                trace["failure_stage"] = "manual_response_timeout"
                trace["failure_reason"] = "no response within 40 second deadline"
                trace["steps"].append({"stage": "manual_response_timeout", "ts": utc_now()})

        except Exception as exc:
            trace["failure_stage"] = trace["failure_stage"] or "unknown"
            trace["failure_reason"] = trace["failure_reason"] or f"{type(exc).__name__}: {exc}"
            trace["steps"].append({"stage": "exception_caught", "exception": str(exc), "ts": utc_now()})

        finally:
            browser.close()

    trace["run_dir"] = str(run_dir)
    (run_dir / "diagnostic_flow_trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    return trace


def main():
    output_root = OUTPUT_DIR
    output_root.mkdir(parents=True, exist_ok=True)

    username = "israel_bidur"

    print("=" * 80)
    print("PRODUCTION FLOW (from src/fastdl_api.py)")
    print("=" * 80)
    prod_trace = run_production_flow(username, output_root)
    prod_summary = {
        "flow": "production",
        "success": prod_trace["success"],
        "failure_stage": prod_trace["failure_stage"],
        "failure_reason": prod_trace["failure_reason"],
        "stories_request_seen": bool(prod_trace["stories_request"]),
        "stories_response_seen": bool(prod_trace["stories_response"]),
        "api_status": prod_trace["stories_response"].get("status") if prod_trace["stories_response"] else None,
        "request_events_count": len(prod_trace["events"]["requests"]),
        "response_events_count": len(prod_trace["events"]["responses"]),
        "run_dir": prod_trace["run_dir"],
    }
    print(json.dumps(prod_summary, indent=2))

    print("\n" + "=" * 80)
    print("DIAGNOSTIC FLOW (from debug_fastdl_github_verified_flow.py)")
    print("=" * 80)
    diag_trace = run_verified_diagnostic_flow(username, output_root)
    diag_summary = {
        "flow": "diagnostic",
        "success": diag_trace["success"],
        "failure_stage": diag_trace["failure_stage"],
        "failure_reason": diag_trace["failure_reason"],
        "stories_request_seen": bool(diag_trace["stories_request"]),
        "stories_response_seen": bool(diag_trace["stories_response"]),
        "api_status": diag_trace["stories_response"].get("status") if diag_trace["stories_response"] else None,
        "request_events_count": len(diag_trace["events"]["requests"]),
        "response_events_count": len(diag_trace["events"]["responses"]),
        "run_dir": diag_trace["run_dir"],
    }
    print(json.dumps(diag_summary, indent=2))

    print("\n" + "=" * 80)
    print("COMPARISON SUMMARY")
    print("=" * 80)
    comparison = {
        "production_success": prod_summary["success"],
        "diagnostic_success": diag_summary["success"],
        "production_failure": prod_summary["failure_stage"],
        "diagnostic_failure": diag_summary["failure_stage"],
        "key_difference": {
            "production_path": "Uses page.expect_response(), no Stories tab click, no manual wait loop",
            "diagnostic_path": "Uses manual response listener, clicks Stories tab, manual wait loop with 40s deadline",
        },
        "critical_observation": "If production fails but diagnostic succeeds, the difference is likely the Stories tab click",
    }
    print(json.dumps(comparison, indent=2))
    (output_root / "comparison_summary.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if (prod_trace["success"] and diag_trace["success"]) else 1


if __name__ == "__main__":
    sys.exit(main())
