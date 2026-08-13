"""Manual Playwright reproduction of the previously successful FastDL browser flow.

This script is intentionally diagnostic-only and isolated to scripts/.
It reproduces the verified browser interaction that previously triggered the
Stories API request and records the request/response details to disk.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USERNAME = "israel_bidur"
STORIES_API_URL = "https://api-wh.fastdl.app/api/v1/instagram/stories"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
OUTPUT_DIR = Path(__file__).resolve().parent


def clean_popups(page) -> None:
    page.evaluate(
        """
        () => {
            const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
            for (const selector of selectors) {
                document.querySelectorAll(selector).forEach(el => el.remove());
            }
            document.querySelectorAll('button, input').forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.pointerEvents === 'none' && el.closest('.fc-consent-root')) {
                    el.closest('.fc-consent-root')?.remove();
                }
            });
        }
        """
    )


def click_stories_tab(page) -> bool:
    return page.evaluate(
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


def set_search_input_value(page, selector: str, value: str) -> bool:
    return page.evaluate(
        """
        (data) => {
            const input = document.querySelector(data.sel);
            if (!input) return false;
            input.focus();
            input.value = data.val;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return input.value === data.val;
        }
        """,
        {"sel": selector, "val": value},
    )


def recursive_extract_http_urls(node: Any, seen: Optional[set[str]] = None) -> List[str]:
    if seen is None:
        seen = set()
    out: List[str] = []
    if isinstance(node, dict):
        for value in node.values():
            out.extend(recursive_extract_http_urls(value, seen))
    elif isinstance(node, list):
        for value in node:
            out.extend(recursive_extract_http_urls(value, seen))
    elif isinstance(node, str):
        if node.startswith("http://") or node.startswith("https://"):
            if node not in seen:
                seen.add(node)
                out.append(node)
    return out


def summarize_story_payload(payload: Any) -> Dict[str, Any]:
    story_count = 0
    result = None
    if isinstance(payload, dict):
        for key in ("result", "stories", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                result = value
                story_count = len(value)
                break
            if isinstance(value, dict):
                nested = value.get("result")
                if isinstance(nested, list):
                    result = nested
                    story_count = len(nested)
                    break
    elif isinstance(payload, list):
        result = payload
        story_count = len(payload)

    urls = []
    if isinstance(result, list):
        urls = recursive_extract_http_urls(result)

    return {
        "story_count": story_count,
        "json_keys": list(payload.keys()) if isinstance(payload, dict) else (type(payload).__name__),
        "media_url_count": len(urls),
        "media_urls": urls[:25],
    }


def run_probe(run_id: int) -> Dict[str, Any]:
    artifact = OUTPUT_DIR / f"debug_fastdl_verified_flow_capture_run{run_id}.json"
    trace = {
        "run_id": run_id,
        "viewer_url": VIEWER_URL,
        "username": USERNAME,
        "stories_api_url": STORIES_API_URL,
        "page_events": [],
        "requests": [],
        "responses": [],
        "requestfailed": [],
        "requestfinished": [],
        "stories_request": None,
        "stories_response": None,
        "stories_summary": None,
        "success": False,
        "notes": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        def record_page_event(kind: str, payload: Dict[str, Any]) -> None:
            trace["page_events"].append({"kind": kind, "payload": payload, "ts": time.time()})

        page.on("framenavigated", lambda frame: record_page_event("framenavigated", {"url": frame.url, "is_main": frame == page.main_frame}))
        page.on("domcontentloaded", lambda: record_page_event("domcontentloaded", {"url": page.url}))
        page.on("load", lambda: record_page_event("load", {"url": page.url}))

        def handle_request(request):
            url = request.url
            if "fastdl.app" in url or "api-wh.fastdl.app" in url or "/api/v1/instagram/stories" in url:
                item = {
                    "method": request.method,
                    "url": url,
                    "resource_type": request.resource_type,
                    "headers": dict(request.headers),
                    "post_data": request.post_data,
                    "frame_url": request.frame.url if request.frame else None,
                }
                trace["requests"].append(item)
                if url.startswith(STORIES_API_URL):
                    trace["stories_request"] = item

        def handle_response(response):
            url = response.url
            if "fastdl.app" in url or "api-wh.fastdl.app" in url or "/api/v1/instagram/stories" in url:
                item = {
                    "url": url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "content_type": response.headers.get("content-type"),
                    "request_method": response.request.method,
                    "request_url": response.request.url,
                    "timing": {
                        "start": response.request.timing.get("startTime") if response.request and response.request.timing else None,
                    },
                }
                trace["responses"].append(item)
                if url.startswith(STORIES_API_URL):
                    try:
                        body_text = response.text()
                    except Exception as exc:
                        body_text = f"TEXT_READ_ERROR: {type(exc).__name__}: {exc}"
                    item["body_text_sample"] = body_text[:4000] if isinstance(body_text, str) else body_text
                    trace["stories_response"] = item
                    try:
                        parsed = json.loads(body_text)
                        trace["stories_summary"] = summarize_story_payload(parsed)
                        trace["stories_summary"]["json_parsed"] = True
                    except Exception as exc:
                        trace["stories_summary"] = {"json_parsed": False, "error": str(exc)}

        def handle_requestfailed(request):
            if "fastdl.app" in request.url or "api-wh.fastdl.app" in request.url or "/api/v1/instagram/stories" in request.url:
                trace["requestfailed"].append({
                    "url": request.url,
                    "method": request.method,
                    "failure": getattr(request, "failure", None),
                })

        def handle_requestfinished(request):
            if "fastdl.app" in request.url or "api-wh.fastdl.app" in request.url or "/api/v1/instagram/stories" in request.url:
                response = request.response()
                trace["requestfinished"].append({
                    "url": request.url,
                    "method": request.method,
                    "response_status": response.status if response else None,
                })

        page.on("request", handle_request)
        page.on("response", handle_response)
        page.on("requestfailed", handle_requestfailed)
        page.on("requestfinished", handle_requestfinished)

        page.goto(VIEWER_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#search-form-input", state="visible", timeout=30000)
        clean_popups(page)
        page.wait_for_timeout(1000)
        page.wait_for_selector("#search-form-input", state="visible", timeout=30000)
        record_page_event("before_search", {"url": page.url})

        fill_ok = set_search_input_value(page, "#search-form-input", USERNAME)
        record_page_event("search_input", {"filled": fill_ok, "selector": "#search-form-input", "value": USERNAME})

        page.click("#searchFormButton", force=True, timeout=30000)
        page.wait_for_timeout(2500)
        clean_popups(page)
        page.wait_for_timeout(1000)

        try:
            page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
        except Exception:
            trace["notes"].append("tabs-component__button did not appear within timeout")

        record_page_event("before_stories_click", {"url": page.url})
        stories_clicked = click_stories_tab(page)
        trace["notes"].append(f"stories_click_result={stories_clicked}")
        page.wait_for_timeout(2000)

        try:
            page.wait_for_selector(".media-content--story", timeout=20000, state="visible")
            trace["notes"].append("media-content--story visible")
        except Exception:
            trace["notes"].append("media-content--story not visible within timeout")

        try:
            page.wait_for_selector(".media-content__meta-time", timeout=20000, state="visible")
            trace["notes"].append("media-content__meta-time visible")
        except Exception:
            trace["notes"].append("media-content__meta-time not visible within timeout")

        deadline = time.time() + 40
        while time.time() < deadline and not trace["stories_response"]:
            time.sleep(0.5)

        if trace["stories_response"]:
            trace["success"] = True
            status = trace["stories_response"].get("status")
            trace["notes"].append(f"stories_status={status}")

        artifact.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "run_id": run_id,
            "success": trace["success"],
            "stories_request_captured": bool(trace["stories_request"]),
            "stories_response_captured": bool(trace["stories_response"]),
            "http_status": trace["stories_response"].get("status") if trace["stories_response"] else None,
            "story_count": trace["stories_summary"].get("story_count") if trace["stories_summary"] else None,
            "json_parsed": trace["stories_summary"].get("json_parsed") if trace["stories_summary"] else None,
            "media_url_count": trace["stories_summary"].get("media_url_count") if trace["stories_summary"] else None,
            "artifact": str(artifact),
        }, ensure_ascii=False, indent=2))

        browser.close()

    return trace


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reproduce the proven FastDL browser flow and capture the Stories API")
    parser.add_argument("--run-id", type=int, default=1)
    args = parser.parse_args()
    run_probe(args.run_id)
