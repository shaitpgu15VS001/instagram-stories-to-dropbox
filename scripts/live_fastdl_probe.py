import json
import os
import socket
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests
from curl_cffi import requests as curl_requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from src.story_downloader import StoryDownloader

USERS = ["israel_bidur", "erevtov"]
OUTPUT_ROOT = Path("tmp_live_fastdl_probe")


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def detect_media_type(url: str, kind: Optional[str] = None) -> str:
    k = (kind or "").lower()
    u = (url or "").lower()
    if "video" in k or ".mp4" in u or ".mov" in u:
        return "video"
    if "image" in k or ".jpg" in u or ".jpeg" in u or ".png" in u or ".webp" in u:
        return "image"
    return "unknown"


def summarize_url(url: str) -> Dict[str, Any]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    uri = None
    if "uri" in qs:
        uri = qs["uri"][0]
    return {
        "scheme": parsed.scheme,
        "hostname": parsed.hostname,
        "port": parsed.port,
        "path": parsed.path,
        "query_keys": sorted(qs.keys()),
        "query": parsed.query,
        "uri": uri,
        "full_url": url,
    }


def http_metrics_for_response(resp) -> Dict[str, Any]:
    headers = resp.headers or {}
    return {
        "status": getattr(resp, "status_code", None),
        "content_type": headers.get("content-type") or headers.get("Content-Type"),
        "content_length": headers.get("content-length") or headers.get("Content-Length"),
        "final_url": getattr(resp, "url", None),
        "headers": dict(headers),
    }


def record_probe_result(path: Path, payload: Dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_playwright_probe(url: str, timeout_ms: int = 60000):
    start = time.perf_counter()
    dns_start = time.perf_counter()
    result: Dict[str, Any] = {
        "transport": "playwright",
        "url": url,
        "start": iso_now(),
        "timeout_ms": timeout_ms,
        "success": False,
        "timeout": False,
        "exception": None,
        "status": None,
        "headers": {},
        "first_byte_ms": None,
        "bytes_received": 0,
        "body_complete": False,
        "total_duration_ms": None,
        "dns_ms": None,
        "connect_ms": None,
        "tls_ms": None,
        "response_headers_received": False,
        "body_started": False,
        "final_url": None,
    }
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36", viewport={"width": 1280, "height": 900}, locale="en-US")
            t0 = time.perf_counter()
            start_req = context.request.get(
                url,
                timeout=timeout_ms,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                    "Referer": "https://fastdl.app/",
                },
            )
            total = time.perf_counter() - start
            result["status"] = getattr(start_req, "status", None)
            result["headers"] = dict(getattr(start_req, "headers", {}) or {})
            result["final_url"] = getattr(start_req, "url", url)
            result["response_headers_received"] = True
            body = start_req.body()
            result["body_started"] = True
            result["bytes_received"] = len(body)
            result["body_complete"] = True
            result["success"] = True
            result["total_duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
            result["dns_ms"] = round((t0 - dns_start) * 1000, 2)
            return result
    except Exception as exc:
        result["exception"] = {"type": type(exc).__name__, "message": str(exc), "trace": traceback.format_exc()}
        result["timeout"] = "Timeout 60000ms exceeded" in str(exc) or isinstance(exc, PlaywrightTimeout)
        result["total_duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return result


def run_requests_probe(url: str, timeout_seconds: int = 60, use_curl_cffi: bool = False):
    start = time.perf_counter()
    result: Dict[str, Any] = {
        "transport": "curl_cffi" if use_curl_cffi else "requests",
        "url": url,
        "start": iso_now(),
        "timeout_seconds": timeout_seconds,
        "success": False,
        "timeout": False,
        "exception": None,
        "status": None,
        "headers": {},
        "first_byte_ms": None,
        "bytes_received": 0,
        "body_complete": False,
        "total_duration_ms": None,
        "response_headers_received": False,
        "body_started": False,
        "final_url": None,
    }
    try:
        client = curl_requests if use_curl_cffi else requests
        sess = client.Session() if hasattr(client, 'Session') else None
        if sess is None:
            resp = client.get(url, timeout=timeout_seconds, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        else:
            resp = sess.get(url, timeout=timeout_seconds, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True)
        result["status"] = getattr(resp, "status_code", None)
        result["headers"] = dict(getattr(resp, "headers", {}) or {})
        result["final_url"] = getattr(resp, "url", url)
        result["response_headers_received"] = True
        if hasattr(resp, 'iter_content'):
            total_bytes = 0
            chunk_count = 0
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    chunk_count += 1
                    total_bytes += len(chunk)
                    result["body_started"] = True
                    if result["first_byte_ms"] is None:
                        result["first_byte_ms"] = round((time.perf_counter() - start) * 1000, 2)
            result["bytes_received"] = total_bytes
            result["body_complete"] = chunk_count > 0
        else:
            content = resp.content
            result["bytes_received"] = len(content)
            result["body_complete"] = True
        result["success"] = result["status"] is not None and 200 <= int(result["status"]) < 400
        result["total_duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return result
    except Exception as exc:
        result["exception"] = {"type": type(exc).__name__, "message": str(exc), "trace": traceback.format_exc()}
        result["timeout"] = "timed out" in str(exc).lower() or "timeout" in str(exc).lower()
        result["total_duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return result


def compare_failed_and_working(failing_url: str, working_url: str):
    compare = {
        "failing_url": failing_url,
        "working_url": working_url,
        "failing": run_playwright_probe(failing_url),
        "working": run_playwright_probe(working_url),
    }
    try:
        compare["failing_requests"] = run_requests_probe(failing_url, timeout_seconds=60, use_curl_cffi=False)
    except Exception:
        compare["failing_requests"] = {"exception": traceback.format_exc()}
    try:
        compare["working_requests"] = run_requests_probe(working_url, timeout_seconds=60, use_curl_cffi=False)
    except Exception:
        compare["working_requests"] = {"exception": traceback.format_exc()}
    try:
        compare["failing_curl_cffi"] = run_requests_probe(failing_url, timeout_seconds=60, use_curl_cffi=True)
    except Exception:
        compare["failing_curl_cffi"] = {"exception": traceback.format_exc()}
    try:
        compare["working_curl_cffi"] = run_requests_probe(working_url, timeout_seconds=60, use_curl_cffi=True)
    except Exception:
        compare["working_curl_cffi"] = {"exception": traceback.format_exc()}
    return compare


def run_live_probe_for_user(username: str):
    output_dir = OUTPUT_ROOT / username
    output_dir.mkdir(parents=True, exist_ok=True)
    downloader = StoryDownloader(output_dir=str(output_dir))

    story_urls = None
    story_urls = downloader._fetch_story_urls(username)

    result = {
        "username": username,
        "timestamp_utc": iso_now(),
        "stories_found": 0,
        "stories_downloaded": 0,
        "stories_failed": 0,
        "bytes_total": 0,
        "duration_seconds_total": 0.0,
        "timeouts": 0,
        "retries": 0,
        "stories": [],
        "failed_urls": [],
        "api_items": None,
    }

    if story_urls is None:
        result["api_items"] = None
        result["stories_found"] = 0
        record_probe_result(output_dir / "probe_summary.json", result)
        return result

    result["stories_found"] = len(story_urls)
    for idx, story in enumerate(story_urls, 1):
        url = story.get("u")
        if not url:
            continue
        media_type = detect_media_type(url, story.get("kind"))
        rec = {
            "username": username,
            "story_index": idx,
            "media_type": media_type,
            "media_url": url,
            "summary": summarize_url(url),
            "start": iso_now(),
            "status": None,
            "content_type": None,
            "content_length": None,
            "http_status": None,
            "duration_ms": None,
            "bytes_received": 0,
            "success": False,
            "failure_type": None,
            "exception": None,
            "timeout": False,
            "headers_received": False,
            "body_started": False,
            "body_complete": False,
            "final_url": None,
        }

        start = time.perf_counter()
        try:
            media = downloader._download_media_via_browser_context(url, timeout_seconds=60)
            rec["status"] = "ok"
            rec["http_status"] = media.get("status")
            rec["content_type"] = media.get("content_type")
            rec["headers_received"] = True
            rec["bytes_received"] = len(media.get("content") or b"")
            rec["body_started"] = True
            rec["body_complete"] = True
            rec["final_url"] = media.get("final_url")
            rec["success"] = True
            result["stories_downloaded"] += 1
            result["bytes_total"] += rec["bytes_received"]
            filename = f"{username}_{idx}_{int(start * 1000)}_{media_type}"
            ext = ".mp4" if media_type == "video" else ".jpg"
            target = output_dir / f"{filename}{ext}"
            target.write_bytes(media.get("content") or b"")
        except Exception as exc:
            rec["status"] = "error"
            rec["failure_type"] = type(exc).__name__
            rec["exception"] = str(exc)
            rec["timeout"] = "Timeout 60000ms exceeded" in str(exc) or "timeout" in str(exc).lower()
            if rec["timeout"]:
                result["timeouts"] += 1
                rec["failed_url_detail"] = summarize_url(url)
                rec["failed_url_copyable"] = url
            rec["exception_full"] = traceback.format_exc()
            result["stories_failed"] += 1
            result["failed_urls"].append({
                "username": username,
                "story_index": idx,
                "media_type": media_type,
                "url": url,
                "exception": str(exc),
                "timeout": rec["timeout"],
            })
        finally:
            rec["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
            result["duration_seconds_total"] += rec["duration_ms"] / 1000.0
            rec["end"] = iso_now()
            result["stories"].append(rec)

    record_probe_result(output_dir / "probe_summary.json", result)
    return result


def main():
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    aggregate = {"run_started": iso_now(), "users": {}, "timeout_urls": []}
    for user in USERS:
        aggregate["users"][user] = run_live_probe_for_user(user)
        for item in aggregate["users"][user].get("failed_urls", []):
            if item.get("timeout"):
                aggregate["timeout_urls"].append(item)

    # If a timeout was observed, inspect the failing URL and one working URL from the same run.
    for user, report in aggregate["users"].items():
        failed = next((s for s in report["stories"] if s.get("timeout")), None)
        if not failed:
            continue
        failing_url = failed.get("media_url")
        working = next((s for s in report["stories"] if s.get("success") and s.get("media_type") == failed.get("media_type")), None)
        if not working:
            working = next((s for s in report["stories"] if s.get("success")), None)
        if failing_url and working:
            compare = compare_failed_and_working(failing_url, working.get("media_url"))
            (OUTPUT_ROOT / user).joinpath("timeout_comparison.json").write_text(json.dumps(compare, ensure_ascii=False, indent=2), encoding="utf-8")

    aggregate["run_completed"] = iso_now()
    record_probe_result(OUTPUT_ROOT / "aggregate_summary.json", aggregate)

    print(json.dumps({
        "run_started": aggregate["run_started"],
        "users": {u: {"stories_found": v["stories_found"], "stories_downloaded": v["stories_downloaded"], "stories_failed": v["stories_failed"], "bytes_total": v["bytes_total"], "timeouts": v["timeouts"]} for u, v in aggregate["users"].items()},
        "timeout_count": len(aggregate["timeout_urls"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
