#!/usr/bin/env python3
"""
חקירה בלבד - ללא שינוי production
בדיקה: האם request_failed=true עם net::ERR_FAILED הוא transient שניתן להתאושש ממנו ב-retry

- משתמש ב-flow הנוכחי לאחר תיקון E-FDL-002 (35s timeout + requestfailed listener)
- עבור כל ERR_FAILED: המתן 4 שניות, בצע retry יחיד באותו flow, תעד האם התקבל 200
"""
import time
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
STORIES_API_TIMEOUT_MS = 35000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

OUTPUT_DIR = Path(__file__).resolve().parent

def probe_user_with_err_failed_retry(username: str, round_id: int, user_idx: int):
    """
    Returns dict with:
    - initial: {request_seen, response_seen, request_failed, failure_reason, status, dt, items, response_status}
    - retry: {attempted, success, dt, items, request_failed2, response_status, latency}
    """
    result = {
        "username": username,
        "round_id": round_id,
        "user_idx": user_idx,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "initial": {},
        "retry": {"attempted": False},
        "final_status": None,
    }

    request_seen = {"value": False, "method": None, "url": None}
    response_seen = {"value": False, "status": None, "url": None, "content_type": None}
    request_failed = {"value": False, "failure": None, "url": None}
    listener_attached = False
    t0 = time.time()

    def elapsed():
        return round(time.time() - t0, 2)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900}, locale="en-US")
            page = context.new_page()
            page.set_default_timeout(10000)

            def on_request(req):
                nonlocal listener_attached
                listener_attached = True
                if STORIES_API_PATH in req.url and req.method == "POST":
                    request_seen["value"] = True
                    request_seen["method"] = req.method
                    request_seen["url"] = req.url

            def on_response(resp):
                nonlocal listener_attached
                listener_attached = True
                if STORIES_API_PATH in resp.url and resp.request.method == "POST":
                    response_seen["value"] = True
                    response_seen["status"] = resp.status
                    response_seen["url"] = resp.url
                    response_seen["content_type"] = resp.headers.get("content-type") or resp.headers.get("Content-Type")

            def on_failed(req):
                nonlocal listener_attached
                listener_attached = True
                if STORIES_API_PATH in req.url and req.method == "POST":
                    request_failed["value"] = True
                    request_failed["failure"] = str(req.failure) if req.failure else "unknown"
                    request_failed["url"] = req.url

            page.on("request", on_request)
            page.on("response", on_response)
            page.on("requestfailed", on_failed)

            # --- Flow identical to src/fastdl_api.py ---
            page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay','.modal','.cookie-banner'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            page.fill("#search-form-input", username)
            page.click("#searchFormButton", force=True, timeout=10000)
            time.sleep(2.5)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay','.modal','.cookie-banner'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            try:
                page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
            except PlaywrightTimeout as e:
                result["initial"] = {
                    "request_seen": request_seen["value"],
                    "response_seen": response_seen["value"],
                    "request_failed": request_failed["value"],
                    "failure_reason": request_failed["failure"],
                    "status": "TAB_TIMEOUT",
                    "exception": f"Tab Timeout: {e}",
                    "dt": elapsed(),
                }
                result["final_status"] = "TAB_TIMEOUT"
                return result

            # --- Initial Stories API attempt ---
            initial_start = time.time()
            initial_resp = None
            initial_exc = None
            try:
                with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method == "POST", timeout=STORIES_API_TIMEOUT_MS) as resp_info:
                    clicked = page.evaluate("""()=>{
                        const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                        for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                        return false;
                    }""")
                    if not clicked:
                        pass
                initial_resp = resp_info.value
            except PlaywrightTimeout as e:
                initial_exc = e
            except Exception as e:
                initial_exc = e

            # Record initial state immediately after first attempt (before retry)
            # Need to capture response if available
            initial_dt = round(time.time() - initial_start, 2)
            if initial_resp is not None:
                try:
                    body = initial_resp.json()
                    from urllib.parse import urlparse, parse_qs
                    # Use same parse as src
                    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
                    from src.fastdl_api import FastDLStoriesAPI
                    items = FastDLStoriesAPI.parse_stories(body)
                    items_len = len(items) if items is not None else None
                    # items None means parse failed -> not NO_ACTIVE
                    if items is not None:
                        status = "SUCCESS_EMPTY" if len(items)==0 else "SUCCESS"
                    else:
                        status = "PARSE_NONE"
                except Exception as ex:
                    items_len = None
                    status = f"PARSE_ERROR:{ex}"
                result["initial"] = {
                    "request_seen": request_seen["value"],
                    "response_seen": response_seen["value"],
                    "request_failed": request_failed["value"],
                    "failure_reason": request_failed["failure"],
                    "status": status,
                    "response_status": getattr(initial_resp, 'status', None),
                    "items": items_len,
                    "dt": initial_dt,
                    "elapsed_total": elapsed(),
                }
                result["final_status"] = status
                return result
            else:
                # initial failed - determine type
                if request_failed["value"]:
                    ini_status = "ERR_FAILED"
                elif request_seen["value"] and not response_seen["value"]:
                    ini_status = "TIMEOUT_AFTER_REQUEST"
                elif not request_seen["value"]:
                    ini_status = "TIMEOUT_BEFORE_REQUEST"
                else:
                    ini_status = f"TIMEOUT_OTHER:{type(initial_exc).__name__ if initial_exc else 'unknown'}"

                result["initial"] = {
                    "request_seen": request_seen["value"],
                    "response_seen": response_seen["value"],
                    "request_failed": request_failed["value"],
                    "failure_reason": request_failed["failure"],
                    "status": ini_status,
                    "exception": str(initial_exc)[:400] if initial_exc else None,
                    "dt": initial_dt,
                    "elapsed_total": elapsed(),
                }

                # --- Decide if we should retry (probe only, not production) ---
                # Per task: for every ERR_FAILED, wait 3-5s and retry once
                if request_failed["value"] and "ERR_FAILED" in str(request_failed["failure"]):
                    result["retry"]["attempted"] = True
                    result["retry"]["wait_seconds"] = 4
                    print(f"  [{username}] ERR_FAILED detected ({request_failed['failure']}) -> retry in 4s", flush=True)
                    time.sleep(4)
                    page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay','.modal'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
                    # Reset per-retry tracking but keep original seen for comparison
                    # Create fresh tracking for retry
                    retry_request_seen = {"value": False}
                    retry_response_seen = {"value": False, "status": None}
                    retry_failed = {"value": False, "failure": None}
                    # Attach temporary listeners for retry window (or reuse same dicts but clear)
                    # We will reuse same dicts but snapshot before retry, then clear failed flag to detect second failure
                    # Clear for clean detection of second attempt's failed
                    prev_failed = request_failed["value"]
                    request_failed["value"] = False
                    request_failed["failure"] = None
                    response_seen["value"] = False  # reset to detect new response

                    retry_start = time.time()
                    retry_resp = None
                    retry_exc = None
                    try:
                        with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method == "POST", timeout=STORIES_API_TIMEOUT_MS) as resp_info2:
                            clicked2 = page.evaluate("""()=>{
                                const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                                for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                                return false;
                            }""")
                        retry_resp = resp_info2.value
                    except PlaywrightTimeout as e:
                        retry_exc = e
                    except Exception as e:
                        retry_exc = e

                    retry_dt = round(time.time() - retry_start, 2)
                    if retry_resp is not None:
                        try:
                            body2 = retry_resp.json()
                            sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
                            from src.fastdl_api import FastDLStoriesAPI
                            items2 = FastDLStoriesAPI.parse_stories(body2)
                            items_len2 = len(items2) if items2 is not None else None
                            if items2 is not None:
                                retry_status = "SUCCESS_EMPTY" if len(items2)==0 else "SUCCESS"
                            else:
                                retry_status = "PARSE_NONE"
                        except Exception as ex:
                            items_len2 = None
                            retry_status = f"PARSE_ERROR:{ex}"
                        result["retry"].update({
                            "status": retry_status,
                            "response_status": getattr(retry_resp, 'status', None),
                            "items": items_len2,
                            "dt": retry_dt,
                            "request_seen": request_seen["value"],
                            "response_seen": response_seen["value"],
                            "request_failed": request_failed["value"],
                            "failure_reason": request_failed["failure"],
                            "latency_retry": retry_dt,
                        })
                        # Determine final
                        if retry_status.startswith("SUCCESS"):
                            result["final_status"] = f"RETRY_SUCCESS ({retry_status})"
                        else:
                            result["final_status"] = f"RETRY_{retry_status}"
                        print(f"  [{username}] RETRY -> {retry_status} dt={retry_dt}s items={items_len2} failed={request_failed['value']}", flush=True)
                    else:
                        if request_failed["value"]:
                            retry_status = "ERR_FAILED"
                        elif request_seen["value"] and not response_seen["value"]:
                            retry_status = "TIMEOUT_AFTER_REQUEST"
                        elif not request_seen["value"]:
                            retry_status = "TIMEOUT_BEFORE_REQUEST"
                        else:
                            retry_status = f"TIMEOUT:{type(retry_exc).__name__}"
                        result["retry"].update({
                            "status": retry_status,
                            "request_seen": request_seen["value"],
                            "response_seen": response_seen["value"],
                            "request_failed": request_failed["value"],
                            "failure_reason": request_failed["failure"],
                            "exception": str(retry_exc)[:400] if retry_exc else None,
                            "dt": retry_dt,
                        })
                        result["final_status"] = f"RETRY_{retry_status}"
                        print(f"  [{username}] RETRY -> {retry_status} failed={request_failed['value']} reason={request_failed['failure']}", flush=True)
                else:
                    # Not ERR_FAILED -> no retry per task (but log)
                    result["final_status"] = ini_status
                    if ini_status == "TIMEOUT_AFTER_REQUEST":
                        # For comparison, we could also test retry on timeout_after_request, but task says only ERR_FAILED
                        pass

                return result

        finally:
            try:
                browser.close()
            except:
                pass

def run_batch(round_id, usernames, gap_s=2):
    print(f"\n=== ROUND {round_id} batch {usernames} ===", flush=True)
    batch_results = []
    for idx, u in enumerate(usernames):
        print(f"\n-- Round {round_id} User {idx+1}/{len(usernames)}: @{u} --", flush=True)
        res = probe_user_with_err_failed_retry(u, round_id, idx)
        print(f"  Initial: {res['initial'].get('status')} request_seen={res['initial'].get('request_seen')} response_seen={res['initial'].get('response_seen')} request_failed={res['initial'].get('request_failed')} reason={res['initial'].get('failure_reason')} dt={res['initial'].get('dt')} items={res['initial'].get('items')}", flush=True)
        if res["retry"]["attempted"]:
            print(f"  Retry: {res['retry'].get('status')} dt={res['retry'].get('dt')} items={res['retry'].get('items')} request_failed={res['retry'].get('request_failed')} reason={res['retry'].get('failure_reason')}", flush=True)
        print(f"  Final: {res['final_status']}", flush=True)
        batch_results.append(res)
        if idx < len(usernames)-1:
            time.sleep(gap_s)
    return batch_results

def main():
    # Users with Stories to induce ERR_FAILED (as seen in probe_post_fix)
    users_with_stories = ["israel_bidur", "erevtov", "mizrahitpage", "kolbarama"]
    # Also test the reported failing order
    reported_order = ["kolbarama", "mizrahitpage", "glglz"]

    all_results = []
    # Do 4 rounds with mixed users to increase chance of ERR_FAILED
    # Round 1-2: with stories users
    for rnd in [1,2]:
        batch = run_batch(rnd, users_with_stories, gap_s=2)
        all_results.extend(batch)
        time.sleep(3)

    # Round 3: reported order
    batch3 = run_batch(3, reported_order, gap_s=2)
    all_results.extend(batch3)
    time.sleep(3)

    # Round 4: repeat with stories to see throttling effect of retries
    batch4 = run_batch(4, users_with_stories, gap_s=2)
    all_results.extend(batch4)

    # Save
    out_path = OUTPUT_DIR / "probe_err_failed_retry_results.json"
    out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path} with {len(all_results)} probes", flush=True)

    # Summary for quick view
    err_failed_count = sum(1 for r in all_results if r["initial"].get("request_failed"))
    retry_attempted = sum(1 for r in all_results if r["retry"]["attempted"])
    retry_success = sum(1 for r in all_results if r["retry"]["attempted"] and r["retry"].get("status","").startswith("SUCCESS"))
    retry_failed = retry_attempted - retry_success
    print("\n=== QUICK SUMMARY ===", flush=True)
    print(f"ERR_FAILED observed: {err_failed_count}/{len(all_results)}", flush=True)
    print(f"Retry attempted: {retry_attempted}", flush=True)
    print(f"Retry SUCCESS: {retry_success}", flush=True)
    print(f"Retry still ERR_FAILED/TIMEOUT: {retry_failed}", flush=True)
    for r in all_results:
        if r["initial"].get("request_failed"):
            print(f"  {r['username']} r{r['round_id']} -> initial ERR_FAILED ({r['initial'].get('failure_reason')}) -> retry {r['retry'].get('status')} final {r['final_status']}", flush=True)

if __name__ == "__main__":
    main()
