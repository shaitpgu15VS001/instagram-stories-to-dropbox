"""Manual media-download proof for the verified FastDL Stories flow.

This is a temporary, diagnostic-only script under scripts/. It intentionally reuses
and isolates the already-verified browser interaction without modifying the
production downloader or any workflow/state logic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USERNAME = "israel_bidur"
STORIES_API_URL = "https://api-wh.fastdl.app/api/v1/instagram/stories"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
OUT_ROOT = Path(__file__).resolve().parent / "debug_output" / "fastdl_media_test"


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


def extract_media_candidates(payload: Any) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if isinstance(payload, dict):
        items = []
        for key in ("result", "stories", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
            if isinstance(value, dict):
                nested = value.get("result")
                if isinstance(nested, list):
                    items = nested
                    break
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ("image_versions2", "video_versions", "media"):
                val = item.get(key)
                if isinstance(val, dict):
                    for inner_key in ("candidates", "versions"):
                        if isinstance(val.get(inner_key), list):
                            for entry in val[inner_key]:
                                if isinstance(entry, dict):
                                    url = entry.get("url")
                                    if url:
                                        candidates.append({
                                            "url": url,
                                            "source": key,
                                            "story_index": items.index(item),
                                            "entry": entry,
                                        })
            for key in ("url", "url_downloadable", "url_wrapped"):
                v = item.get(key)
                if isinstance(v, str) and v.startswith("http"):
                    candidates.append({"url": v, "source": f"item.{key}", "story_index": items.index(item), "entry": item})
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            if isinstance(item, dict):
                for key in ("image_versions2", "video_versions"):
                    val = item.get(key)
                    if isinstance(val, dict):
                        for inner in val.get("candidates", []):
                            url = inner.get("url")
                            if url:
                                candidates.append({"url": url, "source": key, "story_index": idx, "entry": inner})
    dedup = []
    seen = set()
    for item in candidates:
        url = item["url"]
        if url not in seen:
            seen.add(url)
            dedup.append(item)
    return dedup


def infer_extension(url: str, content_type: Optional[str]) -> str:
    parsed = urlparse(url)
    suffix = os.path.splitext(parsed.path)[1].lower()
    if suffix:
        return suffix
    if content_type:
        mapping = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "video/mp4": ".mp4",
            "video/quicktime": ".mov",
            "application/octet-stream": ".bin",
        }
        return mapping.get(content_type.lower(), "")
    return ""


def safe_filename_from_url(url: str, fallback: str = "media") -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path) or fallback
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name or fallback


def write_download_result(base_dir: Path, label: str, resp: Any, body: bytes, url: str) -> Dict[str, Any]:
    base_dir.mkdir(parents=True, exist_ok=True)
    final_name = safe_filename_from_url(url, fallback=f"{label}_download")
    ext = infer_extension(url, resp.headers.get("content-type") if resp else None)
    if ext and not final_name.lower().endswith(tuple(ext.lower() for ext in [ext])):
        final_name = f"{Path(final_name).stem}{ext}"
    path = base_dir / final_name
    path.write_bytes(body)
    headers = getattr(resp, "headers", {})
    return {
        "label": label,
        "url": url,
        "status": getattr(resp, "status_code", None),
        "final_url": getattr(resp, "url", url),
        "content_type": headers.get("content-type"),
        "content_length": headers.get("content-length"),
        "downloaded_bytes": len(body),
        "exists": path.exists(),
        "non_empty": path.exists() and path.stat().st_size > 0,
        "file_path": str(path),
        "extension": ext,
        "is_likely_media": bool(headers.get("content-type", "").startswith(("image/", "video/"))) or url.lower().endswith((".jpg", ".jpeg", ".png", ".mp4", ".webp")),
    }


def test_browser_context_download(context, url: str, out_dir: Path) -> Dict[str, Any]:
    try:
        response = context.request.get(url, timeout=30000, headers={"Referer": "https://fastdl.app/"})
        body = response.body()
        result = write_download_result(out_dir, "browser_context", response, body, url)
        result["method"] = "browser_context"
        return result
    except Exception as exc:
        return {
            "label": "browser_context",
            "method": "browser_context",
            "url": url,
            "status": None,
            "final_url": url,
            "error": f"{type(exc).__name__}: {exc}",
            "downloaded_bytes": 0,
            "exists": False,
            "non_empty": False,
            "is_likely_media": False,
        }


def test_direct_http_download(url: str, out_dir: Path) -> Dict[str, Any]:
    try:
        resp = requests.get(url, timeout=30, allow_redirects=True)
        body = resp.content
        result = write_download_result(out_dir, "direct_http", resp, body, url)
        result["method"] = "direct_http"
        return result
    except Exception as exc:
        return {
            "label": "direct_http",
            "method": "direct_http",
            "url": url,
            "status": None,
            "final_url": url,
            "error": f"{type(exc).__name__}: {exc}",
            "downloaded_bytes": 0,
            "exists": False,
            "non_empty": False,
            "is_likely_media": False,
        }


def run_probe(run_id: int) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "run_id": run_id,
        "viewer_url": VIEWER_URL,
        "username": USERNAME,
        "stories_api_url": STORIES_API_URL,
        "success": False,
        "stories_request": None,
        "stories_response": None,
        "stories_summary": None,
        "selected_media_url": None,
        "browser_context_download": None,
        "direct_http_download": None,
        "notes": [],
        "artifacts": [],
    }
    out_dir = OUT_ROOT / f"run{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    result["artifacts"].append(str(out_dir))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        observed_requests: List[Dict[str, Any]] = []
        observed_responses: List[Dict[str, Any]] = []

        def capture_request(request):
            if request.url.startswith(STORIES_API_URL):
                observed_requests.append({
                    "method": request.method,
                    "url": request.url,
                    "headers": dict(request.headers),
                    "post_data": request.post_data,
                    "resource_type": request.resource_type,
                    "frame_url": request.frame.url if request.frame else None,
                })
                result["stories_request"] = observed_requests[-1]

        def capture_response(response):
            if response.url.startswith(STORIES_API_URL):
                body_text = ""
                try:
                    body_text = response.text()
                except Exception as exc:
                    body_text = f"TEXT_READ_ERROR: {type(exc).__name__}: {exc}"

                summary = {
                    "url": response.url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "content_type": response.headers.get("content-type"),
                    "body_text": body_text if isinstance(body_text, str) else str(body_text),
                    "body_text_sample": body_text[:6000] if isinstance(body_text, str) else body_text,
                }
                observed_responses.append(summary)
                result["stories_response"] = summary
                try:
                    parsed = json.loads(body_text)
                    result["stories_summary"] = {
                        "story_count": 0,
                        "result_keys": list(parsed.keys()) if isinstance(parsed, dict) else [],
                        "json_parsed": True,
                        "media_url_count": 0,
                    }
                    if isinstance(parsed, dict):
                        result_list = []
                        for key in ("result", "stories", "items", "data"):
                            value = parsed.get(key)
                            if isinstance(value, list):
                                result_list = value
                                break
                            if isinstance(value, dict):
                                nested = value.get("result")
                                if isinstance(nested, list):
                                    result_list = nested
                                    break
                        if isinstance(result_list, list):
                            result["stories_summary"]["story_count"] = len(result_list)
                            media_candidates = extract_media_candidates(parsed)
                            result["stories_summary"]["media_url_count"] = len(media_candidates)
                            result["stories_summary"]["sample_media_urls"] = [c["url"] for c in media_candidates[:10]]
                    elif isinstance(parsed, list):
                        result["stories_summary"]["story_count"] = len(parsed)
                        media_candidates = extract_media_candidates(parsed)
                        result["stories_summary"]["media_url_count"] = len(media_candidates)
                        result["stories_summary"]["sample_media_urls"] = [c["url"] for c in media_candidates[:10]]
                except Exception as exc:
                    result["stories_summary"] = {"json_parsed": False, "error": str(exc)}

        page.on("request", capture_request)
        page.on("response", capture_response)

        page.goto(VIEWER_URL, wait_until="domcontentloaded")
        page.wait_for_selector("#search-form-input", state="visible", timeout=30000)
        clean_popups(page)
        time.sleep(1)
        page.wait_for_selector("#search-form-input", state="visible", timeout=30000)
        assert set_search_input_value(page, "#search-form-input", USERNAME)
        page.click("#searchFormButton", force=True, timeout=30000)
        time.sleep(2.5)
        clean_popups(page)
        time.sleep(1)
        page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
        stories_clicked = click_stories_tab(page)
        result["notes"].append(f"stories_click_result={stories_clicked}")
        time.sleep(2)

        try:
            page.wait_for_selector(".media-content--story", timeout=20000, state="visible")
            result["notes"].append("media-content--story visible")
        except Exception:
            result["notes"].append("media-content--story not visible within timeout")

        try:
            page.wait_for_selector(".media-content__meta-time", timeout=20000, state="visible")
            result["notes"].append("media-content__meta-time visible")
        except Exception:
            result["notes"].append("media-content__meta-time not visible within timeout")

        deadline = time.time() + 40
        while time.time() < deadline and not result["stories_response"]:
            time.sleep(0.5)

        if not result["stories_response"]:
            raise RuntimeError("Stories API response was not captured")

        result["success"] = True
        result["notes"].append("Stories API captured via browser")

        full_body = result["stories_response"].get("body_text")
        if not full_body:
            raise RuntimeError("Stories response body was empty")

        media_candidates = extract_media_candidates(json.loads(full_body))
        if not media_candidates:
            parsed = json.loads(full_body)
            media_candidates = extract_media_candidates(parsed)

        if not media_candidates:
            raise RuntimeError("No media URLs were found in the captured Stories JSON")

        selected = media_candidates[0]["url"]
        result["selected_media_url"] = selected
        result["notes"].append(f"Selected media URL from first story: {selected[:200]}")

        browser_context_result = test_browser_context_download(context, selected, out_dir)
        direct_http_result = test_direct_http_download(selected, out_dir)
        result["browser_context_download"] = browser_context_result
        result["direct_http_download"] = direct_http_result

        result["artifacts"].append(str(out_dir / "browser_context_download.json"))
        result["artifacts"].append(str(out_dir / "direct_http_download.json"))
        (out_dir / "browser_context_download.json").write_text(json.dumps(browser_context_result, indent=2, ensure_ascii=False), encoding="utf-8")
        (out_dir / "direct_http_download.json").write_text(json.dumps(direct_http_result, indent=2, ensure_ascii=False), encoding="utf-8")

        media_json_path = out_dir / "stories_response.json"
        media_json_path.write_text(json.dumps({
            "stories_request": result["stories_request"],
            "stories_response": result["stories_response"],
            "stories_summary": result["stories_summary"],
            "selected_media_url": selected,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        result["artifacts"].append(str(media_json_path))

        summary = {
            "run_id": run_id,
            "success": result["success"],
            "stories_api_captured": bool(result["stories_request"] and result["stories_response"]),
            "story_count": result["stories_summary"].get("story_count") if result["stories_summary"] else None,
            "media_url_count": result["stories_summary"].get("media_url_count") if result["stories_summary"] else None,
            "selected_media_url": selected,
            "browser_context_status": browser_context_result.get("status"),
            "browser_context_downloaded_bytes": browser_context_result.get("downloaded_bytes"),
            "direct_http_status": direct_http_result.get("status"),
            "direct_http_downloaded_bytes": direct_http_result.get("downloaded_bytes"),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        browser.close()

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify a real FastDL Stories media URL can be downloaded")
    parser.add_argument("--run-id", type=int, default=1)
    args = parser.parse_args()
    run_probe(args.run_id)
