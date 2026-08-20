#!/usr/bin/env python3
"""TEMPORARY probe: capture ALL Stories API responses for a username over ~40s.

Goal: determine whether the first response is empty and a later one is full
(polling / slow-loading pattern that would explain E-FDL-001 misfires).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
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
OUTPUT_DIR = Path(__file__).resolve().parent / "debug_output" / "live_probe"


def now() -> float:
    return time.time()


def main() -> None:
    username = "kolbarama"
    responses: list[dict[str, Any]] = []
    requests_seen: list[dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
        page = context.new_page()

        def on_request(req):
            if STORIES_API_PATH in req.url and req.method == "POST":
                requests_seen.append({"t": now(), "url": req.url})

        def on_response(resp):
            if STORIES_API_PATH in resp.url and resp.request.method == "POST":
                try:
                    body = resp.json()
                except Exception:
                    body = None
                result = body.get("result") if isinstance(body, dict) else None
                responses.append({
                    "t": now(),
                    "status": resp.status,
                    "result_len": len(result) if isinstance(result, list) else ("NOT_LIST:" + type(result).__name__ if result is not None else "NONE"),
                    "top_keys": list(body.keys()) if isinstance(body, dict) else None,
                })

        page.on("request", on_request)
        page.on("response", on_response)

        page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#search-form-input", state="visible", timeout=15000)
        page.evaluate("() => { const s=['.fc-dialog-overlay','.fc-consent-root','.overlay','.modal','.cookie-banner','.fc__dialog','.fc-cookie-banner','[role=dialog]']; s.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove())); }")
        page.fill("#search-form-input", username)
        page.click("#searchFormButton", force=True, timeout=15000)
        time.sleep(2.5)
        page.evaluate("() => { const s=['.fc-dialog-overlay','.fc-consent-root','.overlay','.modal','.cookie-banner','.fc__dialog','.fc-cookie-banner','[role=dialog]']; s.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove())); }")
        page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
        clicked = page.evaluate(
            """
            () => {
                const buttons = Array.from(document.querySelectorAll('button.tabs-component__button'));
                for (const button of buttons) {
                    if (button.innerText && button.innerText.toLowerCase().includes('stories')) {
                        button.scrollIntoView(); button.click(); return true;
                    }
                }
                return false;
            }
            """
        )
        t0 = now()
        for _ in range(50):
            time.sleep(1)
        browser.close()

    t0_first = requests_seen[0]["t"] if requests_seen else None
    out = {
        "username": username,
        "stories_tab_clicked": clicked,
        "request_count": len(requests_seen),
        "response_count": len(responses),
        "t_relative_s": [round(r["t"] - t0, 1) for r in responses] if t0 else [],
        "responses": responses,
    }
    dest = OUTPUT_DIR / "kolbarama_all_responses.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()