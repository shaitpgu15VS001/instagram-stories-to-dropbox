"""Temporary GitHub Actions compatibility probe for the verified FastDL browser flow.

This script intentionally stays outside production code and reuses the same browser
sequence that has already been proven to work locally. The purpose is to evaluate
whether that browser-based flow is stable enough in principle for a GitHub Actions
runner without changing the workflow or the production implementation.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USERNAME = "israel_bidur"
STORIES_API_URL = "https://api-wh.fastdl.app/api/v1/instagram/stories"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
OUT_DIR = Path(__file__).resolve().parent / "debug_output" / "github_compatibility"


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


def extract_media_candidates(payload: Any) -> List[str]:
    urls: List[str] = []
    seen = set()
    if isinstance(payload, dict):
        for key in ("result", "stories", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                urls.extend(recursive_extract_http_urls(value, seen))
            elif isinstance(value, dict):
                nested = value.get("result")
                if isinstance(nested, list):
                    urls.extend(recursive_extract_http_urls(nested, seen))
    elif isinstance(payload, list):
        urls.extend(recursive_extract_http_urls(payload, seen))
    return urls


def mime_from_magic(path: Path) -> str:
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as f:
            head = f.read(16)
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if head.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
            return "image/gif"
        if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
            return "image/webp"
        if head.startswith(b"\x00\x00\x00\x18ftyp") or head.startswith(b"\x00\x00\x00\x20ftyp"):
            return "video/mp4"
    return ""


def run_one(run_id: int, out_dir: Path) -> Dict[str, Any]:
    start = time.time()
    run_dir = out_dir / f"run{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    trace: Dict[str, Any] = {
        "run_id": run_id,
        "started_at": utc_now(),
        "viewer_url": VIEWER_URL,
        "username": USERNAME,
        "test_name": "debug_fastdl_github_compatibility",
        "environment": {
            "python_version": os.sys.version.split()[0],
            "playwright_module_loaded": True,
            "headless": True,
            "user_agent": USER_AGENT,
            "browser_args": ["--no-sandbox", "--disable-dev-shm-usage"],
        },
        "steps": [],
        "stories_request": None,
        "stories_response": None,
        "stories_summary": None,
        "download": None,
        "success": False,
        "notes": [],
        "artifacts": [],
    }

    with sync_playwright() as p:
        launch_started = time.time()
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        trace["steps"].append({"name": "browser_launch", "duration_seconds": round(time.time() - launch_started, 3)})

        context_started = time.time()
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        trace["steps"].append({"name": "context_create", "duration_seconds": round(time.time() - context_started, 3)})

        page = context.new_page()
        page.set_default_timeout(60000)

        def capture_request(request):
            if request.url.startswith(STORIES_API_URL):
                trace["stories_request"] = {
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                    "headers": dict(request.headers),
                    "post_data": request.post_data,
                    "frame_url": request.frame.url if request.frame else None,
                }
                trace["steps"].append({"name": "stories_request_seen", "ts": utc_now()})

        def capture_response(response):
            if response.url.startswith(STORIES_API_URL):
                body_text = ""
                try:
                    body_text = response.text()
                except Exception as exc:
                    body_text = f"TEXT_ERROR: {type(exc).__name__}: {exc}"
                payload = {
                    "url": response.url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "content_type": response.headers.get("content-type"),
                    "body_text": body_text,
                    "body_text_sample": body_text[:5000] if isinstance(body_text, str) else body_text,
                }
                trace["stories_response"] = payload
                trace["steps"].append({"name": "stories_response_seen", "status": response.status, "ts": utc_now()})
                try:
                    parsed = json.loads(body_text)
                    media_urls = extract_media_candidates(parsed)
                    trace["stories_summary"] = {
                        "json_parsed": True,
                        "story_count": len(parsed.get("result", [])) if isinstance(parsed, dict) and isinstance(parsed.get("result"), list) else 0,
                        "media_url_count": len(media_urls),
                        "sample_media_urls": media_urls[:10],
                    }
                except Exception as exc:
                    trace["stories_summary"] = {"json_parsed": False, "error": str(exc)}

        page.on("request", capture_request)
        page.on("response", capture_response)

        nav_started = time.time()
        page.goto(VIEWER_URL, wait_until="domcontentloaded")
        trace["steps"].append({"name": "viewer_open", "duration_seconds": round(time.time() - nav_started, 3)})

        page.wait_for_selector("#search-form-input", state="visible", timeout=30000)
        clean_popups(page)
        page.wait_for_timeout(1000)
        page.wait_for_selector("#search-form-input", state="visible", timeout=30000)
        set_search_input_value(page, "#search-form-input", USERNAME)
        trace["steps"].append({"name": "username_entered", "value": USERNAME, "ts": utc_now()})

        search_started = time.time()
        page.click("#searchFormButton", force=True, timeout=30000)
        trace["steps"].append({"name": "search_click", "duration_seconds": round(time.time() - search_started, 3)})
        page.wait_for_timeout(2500)
        clean_popups(page)
        time.sleep(1)

        stories_tab_started = time.time()
        page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
        clicked = click_stories_tab(page)
        trace["steps"].append({"name": "stories_tab_click", "clicked": clicked, "duration_seconds": round(time.time() - stories_tab_started, 3), "ts": utc_now()})
        page.wait_for_timeout(2000)

        try:
            page.wait_for_selector(".media-content--story", timeout=20000, state="visible")
            trace["notes"].append("media-content--story visible")
        except Exception:
            trace["notes"].append("media-content--story not visible within timeout")

        deadline = time.time() + 40
        while time.time() < deadline and not trace["stories_response"]:
            time.sleep(0.5)

        if trace["stories_response"] is None:
            raise RuntimeError("Stories response was not observed in time")

        payload_text = trace["stories_response"].get("body_text")
        if not isinstance(payload_text, str) or not payload_text.strip():
            raise RuntimeError("Stories response body empty")

        parsed = json.loads(payload_text)
        media_urls = extract_media_candidates(parsed)
        if not media_urls:
            raise RuntimeError("No media URLs extracted from Stories JSON")

        selected_url = media_urls[0]
        trace["selected_media_url"] = selected_url
        trace["notes"].append(f"selected_media_url={selected_url[:200]}")

        out_file = run_dir / "browser_download.jpg"
        response = context.request.get(selected_url, timeout=30000)
        content = response.body()
        out_file.write_bytes(content)
        media_type = response.headers.get("content-type", "")
        trace["download"] = {
            "method": "browser_context",
            "status": response.status,
            "content_type": media_type,
            "content_length": response.headers.get("content-length"),
            "downloaded_bytes": len(content),
            "file_exists": out_file.exists(),
            "non_empty": out_file.exists() and out_file.stat().st_size > 0,
            "extension": out_file.suffix,
            "magic_mime": mime_from_magic(out_file),
            "final_url": response.url,
        }
        trace["success"] = bool(
            trace["stories_response"] and
            trace["stories_summary"] and
            trace["stories_summary"].get("json_parsed") and
            out_file.exists() and out_file.stat().st_size > 0
        )

        run_dir.joinpath("stories_response.json").write_text(json.dumps({
            "stories_request": trace["stories_request"],
            "stories_response": trace["stories_response"],
            "stories_summary": trace["stories_summary"],
            "selected_media_url": selected_url,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        run_dir.joinpath("browser_download_meta.json").write_text(json.dumps(trace["download"], ensure_ascii=False, indent=2), encoding="utf-8")
        run_dir.joinpath("trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
        trace["artifacts"] = [
            str(run_dir / "stories_response.json"),
            str(run_dir / "browser_download_meta.json"),
            str(run_dir / "trace.json"),
            str(out_file),
        ]

        browser.close()

    elapsed = round(time.time() - start, 3)
    trace["elapsed_seconds"] = elapsed
    trace["finished_at"] = utc_now()
    run_dir.joinpath("trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "run_id": run_id,
        "success": trace["success"],
        "elapsed_seconds": trace["elapsed_seconds"],
        "stories_api_captured": bool(trace["stories_request"] and trace["stories_response"]),
        "json_parsed": bool(trace["stories_summary"] and trace["stories_summary"].get("json_parsed")),
        "story_count": trace["stories_summary"].get("story_count") if trace["stories_summary"] else None,
        "media_url_count": trace["stories_summary"].get("media_url_count") if trace["stories_summary"] else None,
        "downloaded_bytes": trace["download"].get("downloaded_bytes") if trace["download"] else None,
        "content_type": trace["download"].get("content_type") if trace["download"] else None,
        "file_exists": trace["download"].get("file_exists") if trace["download"] else None,
        "artifact_dir": str(run_dir),
    }, ensure_ascii=False, indent=2))
    return trace


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for run_id in (1, 2):
        run_one(run_id, OUT_DIR)
