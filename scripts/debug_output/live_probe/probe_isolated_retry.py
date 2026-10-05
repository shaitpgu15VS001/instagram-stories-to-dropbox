#!/usr/bin/env python3
"""
חקירה בלבד - בידוד retry עבור request_seen=true, response_seen=false, request_failed=false
- ללא שינוי production
- מנסה לשחזר באופן אמין, עד 30 ניסיונות כלליים, עוצר כשיש 20 retries או כשלא ניתן
- עבור כל ניסיון שמפעיל retry מתעד: זמן request ראשון, requestfailed, זמן timeout, זמן תחילת retry, request שני, response שני, requestfailed שני, זמן כולל, Stories/result
- לא מחשיב ERR_FAILED כהצלחה
"""
import time, json, sys
from pathlib import Path
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
STORIES_API_TIMEOUT_MS = 35000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUTPUT_DIR = Path(__file__).resolve().parent

USERS = ["israel_bidur", "erevtov", "mizrahitpage", "kolbarama", "glglz"]

def probe_once(username, seq):
    t0 = time.time()
    def now_ms(): return round((time.time()-t0)*1000)
    request_seen = {"value": False, "t": None, "method": None, "url": None}
    response_seen = {"value": False, "t": None, "status": None}
    request_failed = {"value": False, "t": None, "failure": None}
    # retry tracking
    retry_request_seen = {"value": False, "t": None}
    retry_response_seen = {"value": False, "t": None, "status": None}
    retry_failed = {"value": False, "t": None, "failure": None}

    first_request_t = None
    first_timeout_t = None
    retry_start_t = None
    second_request_t = None
    second_response_t = None
    total_dt = None
    items_after_retry = None
    final_status = None

    result = {
        "seq": seq,
        "username": username,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "first": {},
        "retry": {"triggered": False},
        "isolated_retry": False, # true only when request_seen && !response_seen && !request_failed
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        try:
            ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
            page = ctx.new_page()
            page.set_default_timeout(10000)

            def on_req(r):
                if STORIES_API_PATH in r.url and r.method=="POST":
                    if not request_seen["value"]:
                        request_seen["value"]=True
                        request_seen["t"]=now_ms()
                        request_seen["method"]=r.method
                        request_seen["url"]=r.url
                    # track retry request separately if after retry_start
                    if result["retry"]["triggered"] and not retry_request_seen["value"]:
                        retry_request_seen["value"]=True
                        retry_request_seen["t"]=now_ms()

            def on_resp(r):
                if STORIES_API_PATH in r.url and r.request.method=="POST":
                    if not response_seen["value"]:
                        response_seen["value"]=True
                        response_seen["t"]=now_ms()
                        response_seen["status"]=r.status
                    if result["retry"]["triggered"] and not retry_response_seen["value"]:
                        # second response after retry
                        # we need to differentiate: if retry triggered, this is second response
                        # but on_resp will fire for both; we capture second as retry
                        # To avoid capturing first response as retry, we check if retry already started and first response already seen false
                        # Simpler: if retry triggered and retry_response not yet, capture
                        pass

            def on_fail(r):
                if STORIES_API_PATH in r.url and r.method=="POST":
                    if not request_failed["value"]:
                        request_failed["value"]=True
                        request_failed["t"]=now_ms()
                        request_failed["failure"]=str(r.failure)
                    if result["retry"]["triggered"] and not retry_failed["value"]:
                        retry_failed["value"]=True
                        retry_failed["t"]=now_ms()
                        retry_failed["failure"]=str(r.failure)

            page.on("request", on_req)
            page.on("response", lambda r: (
                on_resp(r),
                # also capture retry response separately via time
                (retry_response_seen.update({"value": True, "t": now_ms(), "status": r.status}) if result["retry"]["triggered"] and STORIES_API_PATH in r.url and r.request.method=="POST" and not retry_response_seen["value"] else None)
            ))
            page.on("requestfailed", on_fail)

            try:
                page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=10000)
                page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
                page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
                page.fill("#search-form-input", username)
                page.click("#searchFormButton", force=True, timeout=10000)
                time.sleep(2.5)
                page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            except PlaywrightTimeout as e:
                result["first"] = {
                    "request_seen": request_seen["value"],
                    "response_seen": response_seen["value"],
                    "request_failed": request_failed["value"],
                    "failure": request_failed["failure"],
                    "status": "GOTO_TIMEOUT",
                    "exception": str(e)[:400],
                    "first_request_t": request_seen["t"],
                    "first_timeout_t": now_ms(),
                    "total_ms": now_ms(),
                }
                result["final_status"] = "GOTO_TIMEOUT"
                return result
            except Exception as e:
                result["first"] = {"status": f"EXC_GOTO:{e}", "total_ms": now_ms()}
                result["final_status"] = result["first"]["status"]
                return result
            try:
                page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
            except PlaywrightTimeout as e:
                result["first"] = {
                    "request_seen": request_seen["value"],
                    "response_seen": response_seen["value"],
                    "request_failed": request_failed["value"],
                    "failure": request_failed["failure"],
                    "status": "TAB_TIMEOUT",
                    "first_request_t": request_seen["t"],
                    "first_timeout_t": now_ms(),
                    "total_ms": now_ms(),
                }
                result["final_status"] = "TAB_TIMEOUT"
                return result

            # First Stories attempt
            first_request_t = None
            first_timeout_t = None
            retry_start_t = None
            second_request_t = None
            second_response_t = None

            try:
                with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=STORIES_API_TIMEOUT_MS) as info:
                    if request_seen["value"]:
                        first_request_t = request_seen["t"]
                    # click
                    page.evaluate("""()=>{
                        const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                        for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                        return false;
                    }""")
                    # capture request time if not yet
                    # wait for expect to resolve
                resp = info.value
                # success
                body = resp.json()
                sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
                from src.fastdl_api import FastDLStoriesAPI
                items = FastDLStoriesAPI.parse_stories(body)
                items_len = len(items) if items is not None else None
                status = "SUCCESS_EMPTY" if items_len==0 else "SUCCESS" if items_len is not None else "PARSE_NONE"
                result["first"] = {
                    "request_seen": request_seen["value"],
                    "response_seen": response_seen["value"],
                    "request_failed": request_failed["value"],
                    "failure": request_failed["failure"],
                    "status": status,
                    "response_status": resp.status,
                    "items": items_len,
                    "first_request_t": request_seen["t"],
                    "first_response_t": response_seen["t"],
                    "total_ms": now_ms(),
                }
                result["final_status"] = status
                return result
            except PlaywrightTimeout as e:
                first_timeout_t = now_ms()
                # record first attempt state
                is_isolated = request_seen["value"] and not response_seen["value"] and not request_failed["value"]
                result["first"] = {
                    "request_seen": request_seen["value"],
                    "response_seen": response_seen["value"],
                    "request_failed": request_failed["value"],
                    "failure": request_failed["failure"],
                    "status": "TIMEOUT_AFTER_REQUEST" if is_isolated else ("ERR_FAILED" if request_failed["value"] else "TIMEOUT_BEFORE_REQUEST" if not request_seen["value"] else "TIMEOUT_OTHER"),
                    "first_request_t": request_seen["t"],
                    "first_timeout_t": first_timeout_t,
                    "total_ms": now_ms(),
                }
                result["isolated_retry"] = is_isolated
                if not is_isolated:
                    result["final_status"] = result["first"]["status"]
                    # Do not trigger retry for ERR_FAILED per isolation requirement
                    return result
                # Isolated case -> trigger retry
                result["retry"]["triggered"] = True
                retry_start_t = now_ms()
                time.sleep(3)
                page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
                # reset for second attempt tracking
                # we keep request_seen true but need to capture second request/response
                # clear retry trackers
                retry_request_seen["value"]=False
                retry_response_seen["value"]=False
                retry_failed["value"]=False
                # Need to capture second request time separately: we will use on_req to set retry_request_seen
                second_start = time.time()
                try:
                    with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=STORIES_API_TIMEOUT_MS) as info2:
                        page.evaluate("""()=>{
                            const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                            for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                            return false;
                        }""")
                    resp2 = info2.value
                    second_response_t = now_ms()
                    body2 = resp2.json()
                    from src.fastdl_api import FastDLStoriesAPI
                    items2 = FastDLStoriesAPI.parse_stories(body2)
                    items_len2 = len(items2) if items2 is not None else None
                    retry_status = "SUCCESS_EMPTY" if items_len2==0 else "SUCCESS" if items_len2 is not None else "PARSE_NONE"
                    result["retry"].update({
                        "retry_start_t": retry_start_t,
                        "second_request_t": retry_request_seen["t"],
                        "second_response_t": retry_response_seen["t"] or second_response_t,
                        "second_request_failed": retry_failed["value"],
                        "second_failure": retry_failed["failure"],
                        "second_response_status": retry_response_seen["status"] or resp2.status,
                        "items": items_len2,
                        "status": retry_status,
                        "total_ms": now_ms(),
                        "latency_retry": round(time.time()-second_start,2),
                    })
                    # Also update first retry fields for report
                    result["first"]["retry_start_t"] = retry_start_t
                    result["retry"]["total_ms"] = now_ms()
                    items_after_retry = items_len2
                    final_status = f"RETRY_{retry_status}"
                    result["final_status"] = final_status
                    return result
                except PlaywrightTimeout as e2:
                    second_timeout = now_ms()
                    # Determine second failure type
                    if retry_failed["value"]:
                        retry_stat = "ERR_FAILED"
                    elif retry_request_seen["value"] and not retry_response_seen["value"]:
                        retry_stat = "TIMEOUT_AFTER_REQUEST"
                    elif not retry_request_seen["value"]:
                        retry_stat = "TIMEOUT_BEFORE_REQUEST"
                    else:
                        retry_stat = "TIMEOUT_OTHER"
                    result["retry"].update({
                        "retry_start_t": retry_start_t,
                        "second_request_t": retry_request_seen["t"],
                        "second_response_t": retry_response_seen["t"],
                        "second_request_failed": retry_failed["value"],
                        "second_failure": retry_failed["failure"],
                        "status": retry_stat,
                        "exception": str(e2)[:300],
                        "total_ms": now_ms(),
                    })
                    result["final_status"] = f"RETRY_{retry_stat}"
                    return result
                except Exception as e2:
                    result["retry"].update({"status": f"EXC:{e2}", "total_ms": now_ms()})
                    result["final_status"] = result["retry"]["status"]
                    return result
            except Exception as e:
                result["first"] = {"status": f"EXC:{e}", "total_ms": now_ms()}
                result["final_status"] = result["first"]["status"]
                return result
        finally:
            try: browser.close()
            except: pass

def main():
    # Try to get at least 10 isolated retries, but cap at 20 total probes to avoid overload
    target_isolated = 10
    max_total = 20
    results = []
    isolated_count = 0
    total = 0
    user_idx = 0
    print(f"Starting isolated retry probe: target {target_isolated} isolated retries, max {max_total} total", flush=True)
    while total < max_total and isolated_count < target_isolated:
        username = USERS[user_idx % len(USERS)]
        user_idx += 1
        total += 1
        print(f"\n--- Probe {total}/{max_total} @{username} (isolated so far {isolated_count}/{target_isolated}) ---", flush=True)
        r = probe_once(username, total)
        results.append(r)
        print(f"  first: {r['first'].get('status')} req_seen={r['first'].get('request_seen')} resp_seen={r['first'].get('response_seen')} failed={r['first'].get('request_failed')} t_req={r['first'].get('first_request_t')} t_timeout={r['first'].get('first_timeout_t')}", flush=True)
        if r["retry"]["triggered"]:
            isolated_count += 1
            print(f"  RETRY triggered -> {r['retry'].get('status')} second_req={r['retry'].get('second_request_t')} second_resp={r['retry'].get('second_response_t')} failed2={r['retry'].get('second_request_failed')} items={r['retry'].get('items')} total={r['retry'].get('total_ms')}", flush=True)
        else:
            if r.get("isolated_retry"):
                print(f"  isolated but not retried? {r}", flush=True)
            else:
                print(f"  no retry (not isolated case) final={r.get('final_status')}", flush=True)
        # gap 3s between probes to avoid hammering
        time.sleep(3)
        # early exit if we see many successes and no isolated cases after 20 probes, we can analyze
        if total >= 12 and isolated_count == 0:
            print("  No isolated cases after 12 probes, continuing but will analyze artifacts", flush=True)

    # Save
    out = OUTPUT_DIR / "probe_isolated_retry_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out} total={total} isolated_triggered={isolated_count}", flush=True)

    # Analyze previous artifacts as fallback
    print("\n=== ANALYZE PREVIOUS ARTIFACTS ===", flush=True)
    import pathlib
    base = pathlib.Path(r"C:\Users\user-01\Downloads\Construction-apps\Construction\Github-Actions-Download-Stories\scripts\debug_output\live_probe")
    # count isolated in previous files
    for jf in ["probe_err_failed_retry_results.json", "probe_hammer_results.json", "probe_post_fix_results.json"]:
        p = base / jf
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding='utf-8'))
        # normalize
        if isinstance(data, dict) and "batch" in data:
            continue
        if isinstance(data, list):
            iso = sum(1 for r in data if r.get("first",{}).get("status")=="TIMEOUT_AFTER_REQUEST" or r.get("status")=="TIMEOUT_AFTER_REQUEST")
            print(f"  {jf}: TIMEOUT_AFTER_REQUEST (isolated-like) = {iso}/{len(data)}", flush=True)

    # Summary for this run
    isolated_triggered = [r for r in results if r["retry"]["triggered"]]
    retry_success = [r for r in isolated_triggered if r["retry"].get("status","").startswith("SUCCESS")]
    retry_fail = [r for r in isolated_triggered if not r["retry"].get("status","").startswith("SUCCESS")]
    print("\n=== SUMMARY THIS RUN ===", flush=True)
    print(f"Total probes: {total}", flush=True)
    print(f"Isolated retries triggered (request_seen && !response_seen && !failed): {len(isolated_triggered)}", flush=True)
    print(f"Retry SUCCESS (Stories or []): {len(retry_success)}", flush=True)
    for r in retry_success:
        print(f"  {r['seq']} @{r['username']} first_t={r['first'].get('first_request_t')} retry_start={r['retry'].get('retry_start_t')} second_resp={r['retry'].get('second_response_t')} items={r['retry'].get('items')} latency={r['retry'].get('latency_retry')}", flush=True)
    print(f"Retry FAIL: {len(retry_fail)}", flush=True)
    for r in retry_fail:
        print(f"  {r['seq']} @{r['username']} -> {r['retry'].get('status')} failed2={r['retry'].get('second_request_failed')}", flush=True)

    if isolated_count < 3:
        print("\nNOTE: Isolated case is rare locally. Verdict must rely on previous artifacts + production log 32456347593.", flush=True)

if __name__=="__main__":
    main()
