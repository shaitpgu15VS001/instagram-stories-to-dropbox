#!/usr/bin/env python3
"""Probe E-FDL-002: reproduce exact production flow with millisecond timeline.

Mimics src/fastdl_api.py:_fetch_stories_with_playwright but with:
- perf_counter timeline for every stage
- simultaneous on_request/on_response + expect_response double-tracking
- measures request->response delta
- tests multiple usernames sequentially (rate-limit probe)
- redacts sensitive payloads

This probe is TEMPORARY and not part of production.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
OUTPUT_DIR = Path(__file__).resolve().parent

# Usernames to test: mix of known-empty (kolbarama) and known-with-stories (israel_bidur etc)
# plus the reported failing ones (mizrahitpage, glglz) if reachable
USERNAMES = [
    "kolbarama",       # known empty - should return [] quickly
    "mizrahitpage",    # reported failing but should have stories
    "glglz",           # reported failing but should have stories
    "israel_bidur",    # known with stories - control
    "erevtov",         # known with stories - control
]


def redact(obj: Any) -> Any:
    if isinstance(obj, str):
        try:
            d = json.loads(obj)
            if isinstance(d, dict):
                for k in ("_s", "_ts", "_tsc", "ts", "_sv", "token", "sig", "signature"):
                    if k in d and isinstance(d[k], str) and len(d[k]) > 10:
                        d[k] = "<redacted>"
                return json.dumps(d)
        except Exception:
            return obj[:200]
    return obj


def probe_user(username: str, idx: int, total: int) -> Dict[str, Any]:
    """Run exact production flow for one username with detailed timeline."""
    result: Dict[str, Any] = {
        "username": username,
        "seq": f"{idx}/{total}",
        "timeline": [],
        "request_events": [],
        "response_events": [],
        "requestfailed_events": [],
        "expect_response_outcome": None,
        "listener_request_seen": False,
        "listener_response_seen": False,
        "predicates_matched": 0,
        "status": None,
        "error": None,
        "view_url_after": None,
    }

    def now() -> float:
        return time.perf_counter()

    t0 = now()

    def mark(event: str, **extra):
        result["timeline"].append({
            "t_rel_ms": round((now() - t0) * 1000, 1),
            "event": event,
            **extra,
        })

    request_seen = {"value": False, "method": None, "url": None, "t": None}
    response_seen = {"value": False, "status": None, "url": None, "t": None, "ct": None}
    listener_attached = False
    search_click_started = False
    search_click_completed = False
    all_requests: List[Dict] = []
    all_responses: List[Dict] = []
    all_failed: List[Dict] = []

    timeout = 10  # production default

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
            page = context.new_page()
            page.set_default_timeout(timeout * 1000)

            def on_request(req):
                nonlocal listener_attached
                listener_attached = True
                t = round((now() - t0) * 1000, 1)
                if STORIES_API_PATH in req.url and req.method == "POST":
                    request_seen["value"] = True
                    request_seen["method"] = req.method
                    request_seen["url"] = req.url
                    request_seen["t"] = t
                    result["listener_request_seen"] = True
                # log all STORIES_API_PATH reqs regardless of method
                if STORIES_API_PATH in req.url:
                    all_requests.append({
                        "t_rel_ms": t,
                        "method": req.method,
                        "url": req.url,
                        "resource_type": req.resource_type,
                        "post_data_redacted": redact(req.post_data) if req.post_data else None,
                    })
                    mark("on_request STORIES", method=req.method, t_ms=t)
                result["request_events"].append({"t": t, "method": req.method, "url": req.url})

            def on_response(resp):
                nonlocal listener_attached
                listener_attached = True
                t = round((now() - t0) * 1000, 1)
                if STORIES_API_PATH in resp.url and resp.request.method == "POST":
                    response_seen["value"] = True
                    response_seen["status"] = resp.status
                    response_seen["url"] = resp.url
                    response_seen["t"] = t
                    try:
                        response_seen["ct"] = resp.headers.get("content-type") or resp.headers.get("Content-Type")
                    except Exception:
                        response_seen["ct"] = None
                    result["listener_response_seen"] = True
                if STORIES_API_PATH in resp.url:
                    try:
                        ct = resp.headers.get("content-type") or resp.headers.get("Content-Type")
                    except Exception:
                        ct = None
                    # try to get body sample without blocking too long
                    body_info = None
                    try:
                        txt = resp.text()
                        body_info = txt[:300] if txt else None
                    except Exception:
                        body_info = None
                    all_responses.append({
                        "t_rel_ms": t,
                        "status": resp.status,
                        "url": resp.url,
                        "request_method": resp.request.method,
                        "content_type": ct,
                        "body_sample": body_info,
                    })
                    mark("on_response STORIES", status=resp.status, t_ms=t)
                result["response_events"].append({"t": t, "status": resp.status, "url": resp.url})

            def on_failed(req):
                t = round((now() - t0) * 1000, 1)
                if STORIES_API_PATH in req.url:
                    all_failed.append({"t_rel_ms": t, "method": req.method, "url": req.url, "failure": req.failure})
                    mark("requestfailed STORIES", failure=str(req.failure))

            page.on("request", on_request)
            page.on("response", on_response)
            page.on("requestfailed", on_failed)
            listener_attached = True

            mark("page.goto start")
            page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=timeout * 1000)
            mark("page.goto done", url=page.url)

            page.wait_for_selector("#search-form-input", state="visible", timeout=timeout * 1000)
            mark("search_input visible")

            page.evaluate("""() => {
                const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
            }""")
            mark("overlay cleanup 1 done")

            page.fill("#search-form-input", username)
            mark("fill done")

            search_click_started = True
            mark("search_click start")
            try:
                page.click("#searchFormButton", force=True, timeout=timeout * 1000)
                search_click_completed = True
                mark("search_click done")
            except Exception as exc:
                mark("search_click FAILED", error=str(exc))
                raise

            time.sleep(2.5)
            mark("post-search sleep done")

            page.evaluate("""() => {
                const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
                selectors.forEach(sel => document.querySelectorAll(sel).forEach(el => el.remove()));
            }""")
            mark("overlay cleanup 2 done")

            # Wait for Stories tab - production uses 30000 hard-coded
            mark("wait_for_stories_tab start")
            try:
                page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
                mark("wait_for_stories_tab done")
            except PlaywrightTimeout as e:
                mark("wait_for_stories_tab TIMEOUT", error=str(e))
                result["error"] = f"stories_tab_timeout: {e}"
                result["status"] = "TAB_NOT_FOUND"
                return result

            # Now the critical expect_response block - production timeout 20000
            mark("response_waiter create start")
            expect_t0 = now()
            try:
                with page.expect_response(
                    lambda response: STORIES_API_PATH in response.url and response.request.method == "POST",
                    timeout=20000,
                ) as response_info:
                    mark("click_stories_tab start")
                    stories_tab_clicked = page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('button.tabs-component__button'));
                        for (const button of buttons) {
                            if (button.innerText && button.innerText.toLowerCase().includes('stories')) {
                                button.scrollIntoView();
                                button.click();
                                return true;
                            }
                        }
                        return false;
                    }""")
                    mark("click_stories_tab done", clicked=stories_tab_clicked)
                    if not stories_tab_clicked:
                        mark("stories_tab_not_found")
                mark("response_waiter create done", elapsed_ms=round((now()-expect_t0)*1000,1))
            except PlaywrightTimeout as e:
                mark("expect_response TIMEOUT 20000ms", error=str(e), elapsed_ms=round((now()-expect_t0)*1000,1))
                result["expect_response_outcome"] = "TIMEOUT"
                result["error"] = f"Timeout 20000ms exceeded while waiting for event 'response': {e}"
                result["status"] = "TIMEOUT"
                # still collect diagnostics like production does
                result["diagnostic"] = {
                    "LISTENER_ATTACHED": listener_attached,
                    "SEARCH_CLICK_STARTED": search_click_started,
                    "SEARCH_CLICK_COMPLETED": search_click_completed,
                    "STORIES_API_REQUEST_SEEN": request_seen["value"],
                    "STORIES_API_RESPONSE_SEEN": response_seen["value"],
                    "STORIES_API_REQUEST_METHOD": request_seen["method"],
                    "STORIES_API_REQUEST_URL": request_seen["url"],
                    "STORIES_API_RESPONSE_STATUS": response_seen["status"],
                    "STORIES_API_RESPONSE_CT": response_seen["ct"],
                    "PAGE_URL_AFTER_SEARCH": page.url,
                    "all_requests": all_requests,
                    "all_responses": all_responses,
                    "all_failed": all_failed,
                    "request_seen_t": request_seen["t"],
                    "response_seen_t": response_seen["t"],
                }
                result["timeline_summary"] = result["timeline"]
                return result
            except Exception as e:
                mark("expect_response OTHER ERROR", error=str(e))
                result["error"] = f"{type(e).__name__}: {e}"
                result["status"] = "ERROR"
                return result

            # If we reached here, expect_response succeeded
            result["view_url_after"] = page.url
            result["diagnostic"] = {
                "LISTENER_ATTACHED": listener_attached,
                "SEARCH_CLICK_STARTED": search_click_started,
                "SEARCH_CLICK_COMPLETED": search_click_completed,
                "STORIES_API_REQUEST_SEEN": request_seen["value"],
                "STORIES_API_RESPONSE_SEEN": response_seen["value"],
                "all_requests": all_requests,
                "all_responses": all_responses,
                "all_failed": all_failed,
                "request_seen_t": request_seen["t"],
                "response_seen_t": response_seen["t"],
            }

            # Now access response_info.value like production does
            mark("wait_for_response start (access value)")
            try:
                response = response_info.value
                mark("wait_for_response done", status=response.status, url=response.url)
                result["expect_response_outcome"] = "SUCCESS"
                result["response_status"] = response.status
                result["response_url"] = response.url
                try:
                    ct = response.headers.get("content-type") or response.headers.get("Content-Type")
                except Exception:
                    ct = None
                result["response_content_type"] = ct
                try:
                    body = response.json()
                except Exception as je:
                    result["status"] = "JSON_PARSE_FAIL"
                    result["error"] = str(je)
                    try:
                        body_text = response.text()
                        result["body_text_sample"] = body_text[:500]
                    except Exception:
                        pass
                    return result
                # Parse like FastDLStoriesAPI (local import resilient)
                try:
                    from src.fastdl_api import FastDLStoriesAPI
                except ModuleNotFoundError:
                    import sys
                    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
                    from src.fastdl_api import FastDLStoriesAPI
                items = FastDLStoriesAPI.parse_stories(body)
                if items is None:
                    result["status"] = "PARSE_NONE"
                    result["error"] = "parse returned None"
                    result["body_keys"] = list(body.keys()) if isinstance(body, dict) else str(type(body))
                    return result
                result["status"] = "SUCCESS"
                result["items_count"] = len(items)
                result["body_keys"] = list(body.keys()) if isinstance(body, dict) else None
                # Measure request->response delta
                if request_seen["t"] is not None and response_seen["t"] is not None:
                    result["request_to_response_ms"] = round(response_seen["t"] - request_seen["t"], 1)
                # Also measure click->response
                click_ms = next((e["t_rel_ms"] for e in result["timeline"] if e["event"] == "click_stories_tab done"), None)
                resp_ms = response_seen["t"]
                if click_ms is not None and resp_ms is not None:
                    result["click_to_response_ms"] = round(resp_ms - click_ms, 1)

                return result
            except Exception as exc:
                mark("wait_for_response value FAILED", error=str(exc))
                result["expect_response_outcome"] = "VALUE_ERROR"
                result["error"] = f"{type(exc).__name__}: {exc}"
                result["status"] = "VALUE_ERROR"
                return result

        except PlaywrightTimeout as exc:
            mark("PLAYWRIGHT_TIMEOUT outer", error=str(exc))
            result["error"] = f"PlaywrightTimeout: {exc}"
            result["status"] = "TIMEOUT_OUTER"
            result["diagnostic"] = {
                "LISTENER_ATTACHED": listener_attached,
                "SEARCH_CLICK_STARTED": search_click_started,
                "SEARCH_CLICK_COMPLETED": search_click_completed,
                "STORIES_API_REQUEST_SEEN": request_seen["value"],
                "STORIES_API_RESPONSE_SEEN": response_seen["value"],
                "all_requests": all_requests,
                "all_responses": all_responses,
                "all_failed": all_failed,
            }
            return result
        except Exception as exc:
            mark("GENERAL_ERROR", error=str(exc))
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["status"] = "ERROR"
            return result
        finally:
            try:
                browser.close()
            except Exception:
                pass

    result["all_requests"] = all_requests
    result["all_responses"] = all_responses
    return result


def main():
    out_path = OUTPUT_DIR / "probe_e_fdl_002_results.json"
    summary_path = OUTPUT_DIR / "probe_e_fdl_002_summary.json"

    all_results = []
    start_all = time.perf_counter()

    for idx, username in enumerate(USERNAMES, 1):
        print(f"\n{'='*60}")
        print(f"Probing {idx}/{len(USERNAMES)}: @{username}")
        print(f"{'='*60}")
        res = probe_user(username, idx, len(USERNAMES))
        all_results.append(res)

        # Print compact diagnostic
        diag = res.get("diagnostic", {})
        print(f"  status: {res.get('status')}")
        print(f"  expect_response: {res.get('expect_response_outcome')}")
        print(f"  LISTENER_ATTACHED={diag.get('LISTENER_ATTACHED')} REQUEST_SEEN={diag.get('STORIES_API_REQUEST_SEEN')} RESPONSE_SEEN={diag.get('STORIES_API_RESPONSE_SEEN')}")
        print(f"  requests: {len(diag.get('all_requests',[]))} responses: {len(diag.get('all_responses',[]))} failed: {len(diag.get('all_failed',[]))}")
        if res.get("items_count") is not None:
            print(f"  items_count: {res.get('items_count')}")
        if res.get("request_to_response_ms") is not None:
            print(f"  request->response: {res.get('request_to_response_ms')}ms")
        if res.get("click_to_response_ms") is not None:
            print(f"  click->response: {res.get('click_to_response_ms')}ms")
        if res.get("error"):
            print(f"  error: {res.get('error')[:300]}")

        # Timeline snippet
        print("  timeline:")
        for ev in res.get("timeline", []):
            print(f"    T+{ev['t_rel_ms']:7.1f}ms {ev['event']} { {k:v for k,v in ev.items() if k not in ('t_rel_ms','event')} }")

        # Inter-user delay like production (2-3s) - use 3s deterministically
        if idx < len(USERNAMES):
            delay = 3
            print(f"  waiting {delay}s before next user...")
            time.sleep(delay)

    total_ms = round((time.perf_counter() - start_all)*1000,1)
    print(f"\n{'='*60}")
    print(f"ALL DONE total {total_ms}ms")
    print(f"{'='*60}")

    # Write full results
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_ms": total_ms,
        "usernames": USERNAMES,
        "results": all_results,
    }
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote full results to {out_path}")

    # Write summary
    summary = []
    for r in all_results:
        summary.append({
            "username": r["username"],
            "status": r["status"],
            "expect_response": r.get("expect_response_outcome"),
            "request_seen": r.get("diagnostic", {}).get("STORIES_API_REQUEST_SEEN"),
            "response_seen": r.get("diagnostic", {}).get("STORIES_API_RESPONSE_SEEN"),
            "requests": len(r.get("diagnostic", {}).get("all_requests", [])),
            "responses": len(r.get("diagnostic", {}).get("all_responses", [])),
            "items": r.get("items_count"),
            "click_to_resp_ms": r.get("click_to_response_ms"),
            "req_to_resp_ms": r.get("request_to_response_ms"),
            "error": (r.get("error") or "")[:200],
        })
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote summary to {summary_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
