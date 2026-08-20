#!/usr/bin/env python3
"""TEMPORARY investigation probe (not part of production flow).

Replicates the EXACT production flow from src/fastdl_api.py
(_fetch_stories_with_playwright) for several usernames, captures full
request/response bodies for the Stories API, a per-step timeline, and DOM
observations (loading indicator vs story items vs empty state).

Purpose: determine what the FastDL Stories API actually returns for accounts
that failed with E-FDL-001 ("API response parsed to no usable stories").
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
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
OUTPUT_DIR = Path(__file__).resolve().parent / "debug_output" / "live_probe"

USERNAMES = ["kolbarama", "israel_bidur", "erevtov"]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def redact_post_data(data: Optional[str]) -> Optional[str]:
    """Redact values that look like signed tokens while keeping shape."""
    if not data:
        return data
    try:
        obj = json.loads(data)
    except Exception:
        return data
    if isinstance(obj, dict):
        for key in ("_s", "ts", "_ts", "_tsc", "_sv", "token", "signature"):
            if key in obj and isinstance(obj[key], str) and len(obj[key]) > 12:
                obj[key] = "<redacted>"
    return json.dumps(obj)


def summarize_response_body(body: Any) -> Dict[str, Any]:
    """Produce a small structural summary plus truncated sensitive content."""
    if isinstance(body, list):
        return {"type": "list", "len": len(body)}
    if isinstance(body, dict):
        keys = list(body.keys())
        summary: Dict[str, Any] = {"type": "dict", "keys": keys}
        for key in keys:
            val = body[key]
            if isinstance(val, list):
                summary[key] = {"type": "list", "len": len(val)}
            elif isinstance(val, dict):
                summary[key] = {"type": "dict", "keys": list(val.keys())}
            elif val is None:
                summary[key] = None
            else:
                summary[key] = {"type": type(val).__name__, "sample": str(val)[:80]}
        return summary
    if body is None:
        return {"type": "null"}
    return {"type": type(body).__name__, "sample": str(body)[:200]}


def run_for_user(username: str, page, browser) -> Dict[str, Any]:
    trace: Dict[str, Any] = {
        "username": username,
        "started_at": utc_now(),
        "steps": [],
        "stories_request": None,
        "stories_response": None,
        "response_summary": None,
        "dom_observations": [],
        "stories_tab_clicked": None,
        "final_url": None,
        "error": None,
    }

    request_seen = {"value": False, "method": None, "url": None, "post_data": None}
    response_seen = {"value": False, "status": None, "url": None, "content_type": None, "body": None}

    def on_request(req):
        if STORIES_API_PATH in req.url:
            if req.method == "POST" and not request_seen["value"]:
                request_seen["value"] = True
                request_seen["method"] = req.method
                request_seen["url"] = req.url
                request_seen["post_data"] = redact_post_data(req.post_data)
                trace["steps"].append({"ts": utc_now(), "event": "request", "detail": "stories POST seen"})
            elif STORIES_API_PATH in req.url:
                trace["steps"].append({"ts": utc_now(), "event": "request_other", "detail": req.method})

    def on_response(resp):
        if STORIES_API_PATH in resp.url:
            if resp.request.method == "POST":
                response_seen["value"] = True
                response_seen["status"] = resp.status
                response_seen["url"] = resp.url
                response_seen["content_type"] = resp.headers.get("content-type") or resp.headers.get("Content-Type")
                try:
                    body = resp.json()
                except Exception:
                    try:
                        text = resp.text()
                        body = {"_raw_text_sample": text[:200]}
                    except Exception as exc:
                        body = {"_read_error": str(exc)}
                response_seen["body"] = body
                trace["steps"].append({
                    "ts": utc_now(),
                    "event": "response",
                    "status": resp.status,
                    "content_type": response_seen["content_type"],
                })

    def on_requestfailed(req):
        if STORIES_API_PATH in req.url:
            trace["steps"].append({"ts": utc_now(), "event": "requestfailed", "detail": req.method})

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("requestfailed", on_requestfailed)

    try:
        trace["steps"].append({"ts": utc_now(), "event": "goto"})
        page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#search-form-input", state="visible", timeout=15000)
        trace["steps"].append({"ts": utc_now(), "event": "search_input_ready"})

        page.evaluate(
            """
            () => {
                const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
            }
            """
        )
        page.fill("#search-form-input", username)
        trace["steps"].append({"ts": utc_now(), "event": "filled_username"})

        page.click("#searchFormButton", force=True, timeout=15000)
        trace["steps"].append({"ts": utc_now(), "event": "search_clicked"})

        time.sleep(2.5)
        page.evaluate(
            """
            () => {
                const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
            }
            """
        )
        page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
        trace["steps"].append({"ts": utc_now(), "event": "stories_tab_visible"})

        stories_tab_clicked = page.evaluate(
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
        trace["stories_tab_clicked"] = stories_tab_clicked
        trace["steps"].append({"ts": utc_now(), "event": "stories_tab_clicked", "result": stories_tab_clicked})

        # Observe DOM every 500ms for up to 25s
        deadline = time.time() + 25
        while time.time() < deadline:
            obs = page.evaluate(
                """
                () => {
                    const spinner = document.querySelector('.spinner, .loader, .loading, [class*="spin"], [class*="load"], [class*="dots"]');
                    const items = document.querySelectorAll('.profile-media-list__item');
                    const empty = document.querySelector('.empty, .empty-state, [class*="empty"], [class*="no-result"], [class*="not-found"]');
                    const bodyText = document.body ? document.body.innerText.slice(0, 300) : '';
                    return {
                        spinner: spinner ? (spinner.className || spinner.tagName) : null,
                        item_count: items.length,
                        empty: empty ? (empty.className || empty.tagName) : null,
                        has_story_items: items.length > 0,
                        body_sample: bodyText,
                    };
                }
                """
            )
            trace["dom_observations"].append({
                "ts": utc_now(),
                "delta_s": round(time.time() - (time.time() - 25), 1),
                **obs,
            })
            if obs["item_count"] > 0 and not obs["spinner"]:
                time.sleep(1.0)
                break
            time.sleep(0.5)

        trace["final_url"] = page.url
    except Exception as exc:
        trace["error"] = f"{type(exc).__name__}: {exc}"
        trace["steps"].append({"ts": utc_now(), "event": "exception", "detail": str(exc)})

    trace["stories_request"] = request_seen if request_seen["value"] else None
    if response_seen["value"]:
        trace["stories_response"] = {
            "status": response_seen["status"],
            "url": response_seen["url"],
            "content_type": response_seen["content_type"],
        }
        trace["response_summary"] = summarize_response_body(response_seen["body"])
    trace["finished_at"] = utc_now()
    return trace


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {"users": [], "generated_at": datetime.now(timezone.utc).isoformat()}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = context.new_page()
        for username in USERNAMES:
            print(f"=== probing {username} ===", flush=True)
            trace = run_for_user(username, page, browser)
            report["users"].append(trace)
            page.goto("about:blank")
            summary = {
                "username": username,
                "request_seen": bool(trace["stories_request"]),
                "response_seen": bool(trace["stories_response"]),
                "response_status": trace["stories_response"]["status"] if trace["stories_response"] else None,
                "response_content_type": trace["stories_response"]["content_type"] if trace["stories_response"] else None,
                "items_observed": max(o["item_count"] for o in trace["dom_observations"]) if trace["dom_observations"] else 0,
                "spinner_observed": any(o["spinner"] for o in trace["dom_observations"]),
                "empty_observed": any(o["empty"] for o in trace["dom_observations"]),
                "error": trace["error"],
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        browser.close()

    out = OUTPUT_DIR / "live_probe_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote report to {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())