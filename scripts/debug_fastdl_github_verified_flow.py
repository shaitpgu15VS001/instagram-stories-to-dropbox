#!/usr/bin/env python3
"""Diagnostic-only verification of the proven FastDL browser flow.

This script intentionally mirrors the already-validated flow used by
`debug_fastdl_verified_flow_capture.py`, but adds richer logging and artifact
capture for GitHub Actions diagnosis. It does not perform any production logic,
state changes, uploads, or media downloads.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_URL = "https://api-wh.fastdl.app/api/v1/instagram/stories"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "debug_output" / "fastdl_github_verified_flow"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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

    urls: List[str] = []
    if isinstance(result, list):
        urls = recursive_extract_http_urls(result)

    return {
        "story_count": story_count,
        "json_keys": list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
        "media_url_count": len(urls),
        "sample_media_urls": urls[:10],
    }


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def run_probe(username: str, output_root: Path) -> int:
    run_dir = output_root / f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    run_dir.mkdir(parents=True, exist_ok=True)

    trace: Dict[str, Any] = {
        "run_started_at": utc_now(),
        "viewer_url": VIEWER_URL,
        "username": username,
        "stories_api_url": STORIES_API_URL,
        "environment": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python_implementation": platform.python_implementation(),
            "playwright_version": None,
            "chromium_version": None,
            "user_agent": USER_AGENT,
            "browser_args": ["--no-sandbox", "--disable-dev-shm-usage"],
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
        },
        "page_events": [],
        "page_errors": [],
        "console_messages": [],
        "relevant_requests": [],
        "relevant_responses": [],
        "requestfailed": [],
        "stories_request": None,
        "stories_response": None,
        "stories_summary": None,
        "input_status": {},
        "action_status": {},
        "success": False,
        "failure_reason": None,
        "notes": [],
        "timings": [],
    }

    step_started = time.perf_counter()
    with sync_playwright() as p:
        import playwright
        trace["environment"]["playwright_version"] = getattr(playwright, "__version__", None)

        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        trace["environment"]["chromium_version"] = browser.version

        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        def note_stage(name: str, **payload: Any) -> None:
            trace["timings"].append({"stage": name, "ts": utc_now(), **payload})

        def on_request(req):
            url = req.url
            if "fastdl.app" in url or "api-wh.fastdl.app" in url or "/api/v1/instagram/stories" in url:
                item = {
                    "method": req.method,
                    "url": url,
                    "resource_type": req.resource_type,
                    "headers": dict(req.headers),
                    "post_data": req.post_data,
                    "frame_url": req.frame.url if req.frame else None,
                    "ts": utc_now(),
                }
                trace["relevant_requests"].append(item)
                if url.startswith(STORIES_API_URL):
                    trace["stories_request"] = item

        def on_response(resp):
            url = resp.url
            if "fastdl.app" in url or "api-wh.fastdl.app" in url or "/api/v1/instagram/stories" in url:
                item = {
                    "url": url,
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "content_type": resp.headers.get("content-type") or resp.headers.get("Content-Type"),
                    "request_method": resp.request.method,
                    "request_url": resp.request.url,
                    "ts": utc_now(),
                }
                trace["relevant_responses"].append(item)
                if url.startswith(STORIES_API_URL):
                    trace["stories_response"] = item
                    try:
                        body_text = resp.text()
                        item["body_text_sample"] = body_text[:5000] if isinstance(body_text, str) else body_text
                        trace["stories_response"]["body_text_sample"] = item["body_text_sample"]
                        parsed = json.loads(body_text)
                        trace["stories_summary"] = summarize_story_payload(parsed)
                        trace["stories_summary"]["json_parsed"] = True
                    except Exception as exc:  # pragma: no cover - diagnostic-only
                        trace["stories_summary"] = {"json_parsed": False, "error": str(exc)}
                        trace["stories_response"]["body_text_sample"] = "JSON_PARSE_ERROR"

        def on_requestfailed(req):
            url = req.url
            if "fastdl.app" in url or "api-wh.fastdl.app" in url or "/api/v1/instagram/stories" in url:
                trace["requestfailed"].append({
                    "url": url,
                    "method": req.method,
                    "failure": req.failure,
                    "ts": utc_now(),
                })

        page.on("console", lambda msg: trace["console_messages"].append({
            "type": msg.type,
            "text": msg.text,
            "location": msg.location,
            "ts": utc_now(),
        }))
        page.on("pageerror", lambda exc: trace["page_errors"].append({
            "message": str(exc),
            "ts": utc_now(),
        }))
        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_requestfailed)

        page.on("framenavigated", lambda frame: trace["page_events"].append({
            "kind": "framenavigated",
            "url": frame.url,
            "is_main": frame == page.main_frame,
            "ts": utc_now(),
        }))
        page.on("domcontentloaded", lambda: trace["page_events"].append({
            "kind": "domcontentloaded",
            "url": page.url,
            "ts": utc_now(),
        }))

        note_stage("page.goto_start")
        page.goto(VIEWER_URL, wait_until="domcontentloaded")
        trace["input_status"]["page_url_before_search"] = page.url
        note_stage("page.goto_done", url=page.url)

        trace["input_status"]["input_found"] = page.locator("#search-form-input").count() > 0
        if trace["input_status"]["input_found"]:
            clean_popups(page)
            page.wait_for_timeout(1000)
            trace["input_status"]["input_filled"] = set_search_input_value(page, "#search-form-input", username)
        else:
            trace["input_status"]["input_filled"] = False

        trace["action_status"]["search_click_started"] = False
        trace["action_status"]["search_click_completed"] = False
        trace["action_status"]["stories_tab_found"] = False
        trace["action_status"]["stories_tab_clicked"] = False
        trace["action_status"]["stories_response_seen"] = False

        try:
            note_stage("search_click_start")
            trace["action_status"]["search_click_started"] = True
            page.click("#searchFormButton", force=True, timeout=30000)
            trace["action_status"]["search_click_completed"] = True
            note_stage("search_click_done")
        except Exception as exc:  # pragma: no cover - diagnostic-only
            trace["failure_reason"] = f"search_click_failed:{type(exc).__name__}:{exc}"
            trace["notes"].append(f"search_click_failed={type(exc).__name__}: {exc}")
            raise

        page.wait_for_timeout(2500)
        clean_popups(page)
        page.wait_for_timeout(1000)
        trace["input_status"]["page_url_after_search"] = page.url

        try:
            page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
            trace["action_status"]["stories_tab_found"] = True
            trace["notes"].append("stories_tab_found=True")
        except Exception as exc:  # pragma: no cover - diagnostic-only
            trace["notes"].append(f"stories_tab_not_found={type(exc).__name__}: {exc}")
            trace["failure_reason"] = f"stories_tab_missing:{type(exc).__name__}:{exc}"

        if trace["action_status"]["stories_tab_found"]:
            trace["action_status"]["stories_tab_clicked"] = click_stories_tab(page)
            trace["notes"].append(f"stories_tab_clicked={trace['action_status']['stories_tab_clicked']}")

        try:
            page.wait_for_selector(".media-content--story", timeout=20000, state="visible")
            trace["notes"].append("media-content--story visible")
        except Exception as exc:  # pragma: no cover - diagnostic-only
            trace["notes"].append(f"media-content--story missing={type(exc).__name__}: {exc}")

        deadline = time.time() + 40
        while time.time() < deadline and not trace["stories_response"]:
            time.sleep(0.5)

        if trace["stories_response"]:
            trace["action_status"]["stories_response_seen"] = True
            trace["notes"].append(f"stories_response_status={trace['stories_response'].get('status')}")
        else:
            trace["failure_reason"] = "stories_response_not_seen"
            trace["notes"].append("stories_response_not_seen=true")

        if trace["stories_summary"] and trace["stories_summary"].get("json_parsed") is True:
            trace["success"] = True
            trace["notes"].append(f"story_count={trace['stories_summary'].get('story_count')}")
            trace["notes"].append(f"media_url_count={trace['stories_summary'].get('media_url_count')}")
        else:
            trace["success"] = False

        summary = {
            "success": trace["success"],
            "failure_reason": trace["failure_reason"],
            "viewer_url": VIEWER_URL,
            "username": username,
            "page_url_before_search": trace["input_status"].get("page_url_before_search"),
            "page_url_after_search": trace["input_status"].get("page_url_after_search"),
            "input_found": trace["input_status"].get("input_found"),
            "input_filled": trace["input_status"].get("input_filled"),
            "search_click_started": trace["action_status"].get("search_click_started"),
            "search_click_completed": trace["action_status"].get("search_click_completed"),
            "stories_tab_found": trace["action_status"].get("stories_tab_found"),
            "stories_tab_clicked": trace["action_status"].get("stories_tab_clicked"),
            "stories_response_seen": trace["action_status"].get("stories_response_seen"),
            "request_count": len(trace["relevant_requests"]),
            "response_count": len(trace["relevant_responses"]),
            "requestfailed_count": len(trace["requestfailed"]),
            "stories_api_request_seen": bool(trace["stories_request"]),
            "stories_api_response_seen": bool(trace["stories_response"]),
            "api_http_status": trace["stories_response"].get("status") if trace["stories_response"] else None,
            "api_content_type": trace["stories_response"].get("content_type") if trace["stories_response"] else None,
            "json_parsed": bool(trace["stories_summary"] and trace["stories_summary"].get("json_parsed")),
            "story_count": trace["stories_summary"].get("story_count") if trace["stories_summary"] else None,
            "media_url_count": trace["stories_summary"].get("media_url_count") if trace["stories_summary"] else None,
            "browser_user_agent": trace["environment"].get("user_agent"),
            "browser_version": trace["environment"].get("chromium_version"),
            "playwright_version": trace["environment"].get("playwright_version"),
            "platform": trace["environment"].get("platform"),
            "python_version": trace["environment"].get("python_version"),
            "run_dir": str(run_dir),
        }

        write_json(run_dir / "summary.json", summary)
        write_json(run_dir / "request_metadata.json", trace["relevant_requests"])
        write_json(run_dir / "response_metadata.json", trace["relevant_responses"])
        write_json(run_dir / "requestfailed.json", trace["requestfailed"])
        write_json(run_dir / "page_errors.json", trace["page_errors"])
        write_json(run_dir / "console_messages.json", trace["console_messages"])
        write_json(run_dir / "page_events.json", trace["page_events"])
        write_json(run_dir / "run_trace.json", trace)

        if trace["stories_response"] and trace["stories_summary"] and trace["stories_summary"].get("json_parsed"):
            stories_payload = None
            try:
                body_text = trace["stories_response"].get("body_text_sample")
                if isinstance(body_text, str) and body_text != "JSON_PARSE_ERROR":
                    stories_payload = json.loads(body_text)
            except Exception:
                stories_payload = None
            if stories_payload is not None:
                write_json(run_dir / "stories_response.json", stories_payload)

        browser.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["success"] else 1


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostic-only verification of the proven FastDL Stories flow")
    parser.add_argument("--username", default="israel_bidur", help="Instagram username to search")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for output artifacts")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run_probe(args.username, Path(args.output_dir))


if __name__ == "__main__":
    sys.exit(main())
