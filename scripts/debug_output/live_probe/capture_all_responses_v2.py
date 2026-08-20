#!/usr/bin/env python3
"""TEMPORARY probe v2: capture ALL Stories API responses over ~60s + DOM state.

More tolerant of the Stories tab: if the tabs don't appear, log what IS on the
page and keep listening for API responses anyway (a story request may still be
fired automatically after profile load).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
OUTPUT_DIR = Path(__file__).resolve().parent
USERNAME = "kolbarama"


def main() -> None:
    responses: list[dict[str, Any]] = []
    requests_seen: list[dict[str, Any]] = []
    dom_log: list[dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = context.new_page()
        t_start = time.time()

        def on_request(req):
            if STORIES_API_PATH in req.url and req.method == "POST":
                requests_seen.append({"t_rel": round(time.time() - t_start, 2), "url": req.url})

        def on_response(resp):
            if STORIES_API_PATH in resp.url and resp.request.method == "POST":
                try:
                    body = resp.json()
                except Exception:
                    body = None
                result = body.get("result") if isinstance(body, dict) else None
                responses.append({
                    "t_rel": round(time.time() - t_start, 2),
                    "status": resp.status,
                    "result_len": len(result) if isinstance(result, list) else ("NOT_LIST:" + type(result).__name__ if result is not None else "NONE"),
                    "top_keys": list(body.keys()) if isinstance(body, dict) else None,
                })

        def snap(phase: str):
            obs = page.evaluate(
                """
                () => {
                    const tabs = Array.from(document.querySelectorAll('button.tabs-component__button')).map(b => b.innerText.trim());
                    const items = document.querySelectorAll('.profile-media-list__item').length;
                    const spinner = !!document.querySelector('.spinner, .loader, .loader-component, [class*="load"]');
                    const dots = !!document.querySelector('[class*="dot"], [class*="three"], [class*="loading"]');
                    const allButtons = Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => t.length && t.length < 40).slice(0, 20);
                    const url = location.href;
                    const hasProfile = !!document.querySelector('.user-info, [class*="user-info"]');
                    return {tabs, items, spinner, dots, allButtons, url, hasProfile};
                }
                """
            )
            dom_log.append({"t_rel": round(time.time() - t_start, 2), "phase": phase, **obs})

        page.on("request", on_request)
        page.on("response", on_response)

        page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#search-form-input", state="visible", timeout=15000)
        snap("input_ready")
        page.evaluate("() => { const s=['.fc-dialog-overlay','.fc-consent-root','.overlay','.modal','.cookie-banner','.fc__dialog','.fc-cookie-banner','[role=dialog]']; s.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove())); }")
        page.fill("#search-form-input", USERNAME)
        page.click("#searchFormButton", force=True, timeout=15000)
        snap("after_search_click")
        time.sleep(2.5)
        snap("after_sleep_2.5")
        page.evaluate("() => { const s=['.fc-dialog-overlay','.fc-consent-root','.overlay','.modal','.cookie-banner','.fc__dialog','.fc-cookie-banner','[role=dialog]']; s.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove())); }")

        # Tolerantly look for the Stories tab; if missing, poll DOM for a while.
        clicked = False
        for _ in range(40):
            try:
                clicked = page.evaluate(
                    """
                    () => {
                        const buttons = Array.from(document.querySelectorAll('button.tabs-component__button'));
                        for (const button of buttons) {
                            if (button.innerText && button.innerText.toLowerCase().includes('stor')) {
                                button.scrollIntoView(); button.click(); return true;
                            }
                        }
                        return false;
                    }
                    """
                )
            except Exception:
                clicked = False
            if clicked:
                break
            time.sleep(0.5)
        snap("after_tab_attempt")

        for i in range(30):
            time.sleep(1)
            if i % 5 == 4:
                snap(f"poll_{i+1}")

        browser.close()

    out = {
        "username": USERNAME,
        "stories_tab_clicked": clicked,
        "request_count": len(requests_seen),
        "response_count": len(responses),
        "requests": requests_seen,
        "responses": responses,
        "dom_log": dom_log,
    }
    dest = OUTPUT_DIR / "kolbarama_v2.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"stories_tab_clicked": clicked, "requests": requests_seen, "responses": responses}, ensure_ascii=False, indent=2))
    print("DOM:", json.dumps(dom_log, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()