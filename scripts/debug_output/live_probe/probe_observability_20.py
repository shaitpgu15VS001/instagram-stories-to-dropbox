#!/usr/bin/env python3
"""
חקירה בלבד - observability production לפני בחירת Recovery
- ללא שינוי production
- 20 דגימות מבוקרות עם flow וגאפ כמו workflow (3s), ללא hammering
- תיעוד 13 שדות + סיווג ל-7 קטגוריות
- מדידת latencies, התפלגות, מיקום כשל לפני/אחרי API, קשר ל-user/batch
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
USERS = ["kolbarama", "mizrahitpage", "glglz", "israel_bidur", "erevtov"]
GAP_S = 3

def classify(req_seen, resp_seen, fail_seen, resp_status, tab_timeout, page_timeout, items, exc_str):
    # SUCCESS: response 200 and items>0
    # NO_ACTIVE_STORIES: response 200 and items==0
    # TAB_TIMEOUT: tabs wait timeout
    # API_HANG: req_seen && !resp_seen && !fail_seen
    # API_ERR_FAILED: fail_seen true
    # OTHER_TIMEOUT: page/goto/other timeout
    # OTHER_ERROR: parse or other
    if tab_timeout:
        return "TAB_TIMEOUT"
    if page_timeout:
        return "OTHER_TIMEOUT"
    if fail_seen:
        return "API_ERR_FAILED"
    if req_seen and not resp_seen:
        return "API_HANG"
    if resp_seen and resp_status == 200:
        if items is not None:
            if items == 0:
                return "NO_ACTIVE_STORIES"
            elif items > 0:
                return "SUCCESS"
        return "OTHER_ERROR"
    if "PARSE" in str(exc_str):
        return "OTHER_ERROR"
    return "OTHER_ERROR"

def single_observability(username, seq):
    t_flow_start = time.time()
    # timestamps
    page_load_start = None
    page_load_done = None
    search_ready = None
    search_click_started = None
    search_click_completed = None
    tabs_wait_started = None
    tabs_wait_done = None
    stories_click = None
    request_seen = False
    request_seen_t = None
    response_seen = False
    response_seen_t = None
    request_failed = False
    request_failed_reason = None
    response_status = None
    request_to_response_ms = None
    total_flow_ms = None
    outcome = None
    # internal
    req_t = None
    resp_t = None
    fail_t = None
    tab_timeout = False
    page_timeout = False
    items = None
    exc_str = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page = ctx.new_page()
        page.set_default_timeout(10000)
        def on_req(r):
            nonlocal request_seen, request_seen_t, req_t
            if STORIES_API_PATH in r.url and r.method=="POST":
                if not request_seen:
                    request_seen = True
                    request_seen_t = round((time.time()-t_flow_start)*1000)
                    req_t = time.time()
        def on_resp(r):
            nonlocal response_seen, response_seen_t, response_status, resp_t, req_t, request_to_response_ms
            if STORIES_API_PATH in r.url and r.request.method=="POST":
                if not response_seen:
                    response_seen = True
                    response_seen_t = round((time.time()-t_flow_start)*1000)
                    response_status = r.status
                    resp_t = time.time()
                    if req_t:
                        request_to_response_ms = round((resp_t - req_t)*1000)
        def on_fail(r):
            nonlocal request_failed, request_failed_reason, fail_t
            if STORIES_API_PATH in r.url and r.method=="POST":
                if not request_failed:
                    request_failed = True
                    request_failed_reason = str(r.failure)
                    fail_t = round((time.time()-t_flow_start)*1000)
        page.on("request", on_req)
        page.on("response", on_resp)
        page.on("requestfailed", on_fail)

        try:
            page_load_start = round((time.time()-t_flow_start)*1000)
            page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=10000)
            page_load_done = round((time.time()-t_flow_start)*1000)
            page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
            search_ready = round((time.time()-t_flow_start)*1000)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            page.fill("#search-form-input", username)
            search_click_started = round((time.time()-t_flow_start)*1000)
            page.click("#searchFormButton", force=True, timeout=10000)
            search_click_completed = round((time.time()-t_flow_start)*1000)
            time.sleep(2.5)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            tabs_wait_started = round((time.time()-t_flow_start)*1000)
            page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
            tabs_wait_done = round((time.time()-t_flow_start)*1000)
            stories_click = round((time.time()-t_flow_start)*1000)
            # Stories API
            try:
                with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=STORIES_API_TIMEOUT_MS) as info:
                    page.evaluate("""()=>{
                        const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                        for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                        return false;
                    }""")
                resp = info.value
                if resp.status == 200:
                    body = resp.json()
                    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
                    from src.fastdl_api import FastDLStoriesAPI
                    parsed = FastDLStoriesAPI.parse_stories(body)
                    if parsed is not None:
                        items = len(parsed)
                    else:
                        items = None
                        exc_str = "parse_none"
                else:
                    exc_str = f"status_{resp.status}"
                # response already captured via on_resp
            except PlaywrightTimeout as e:
                exc_str = f"Timeout {e}"
                # request_seen/response_seen already via listeners
                pass
            except Exception as e:
                exc_str = str(e)
                pass
        except PlaywrightTimeout as e:
            s = str(e)
            if "tabs-component__button" in s:
                tab_timeout = True
                exc_str = f"TAB_TIMEOUT:{s[:200]}"
            elif "goto" in s or "page_load" in s.lower():
                page_timeout = True
                exc_str = f"PAGE_TIMEOUT:{s[:200]}"
            else:
                exc_str = f"Timeout:{s[:200]}"
                if tabs_wait_started and not tabs_wait_done:
                    tab_timeout = True
                else:
                    page_timeout = True
        except Exception as e:
            exc_str = f"EXC:{e}"
        finally:
            total_flow_ms = round((time.time()-t_flow_start)*1000)
            try: browser.close()
            except: pass

    outcome = classify(request_seen, response_seen, request_failed, response_status, tab_timeout, page_timeout, items, exc_str)
    # NO_ACTIVE_STORIES is SUCCESS with 0, already handled
    # Ensure OTHER cases
    if outcome == "SUCCESS" and items == 0:
        outcome = "NO_ACTIVE_STORIES"

    return {
        "seq": seq,
        "username": username,
        "page_load_start": page_load_start,
        "page_load_done": page_load_done,
        "search_ready": search_ready,
        "search_click_started": search_click_started,
        "search_click_completed": search_click_completed,
        "tabs_wait_started": tabs_wait_started,
        "tabs_wait_done": tabs_wait_done,
        "stories_click": stories_click,
        "STORIES_API_REQUEST_SEEN": request_seen,
        "STORIES_API_RESPONSE_SEEN": response_seen,
        "request_failed": request_failed,
        "request_failed_reason": request_failed_reason,
        "response_status": response_status,
        "request_to_response_ms": request_to_response_ms,
        "total_flow_ms": total_flow_ms,
        "outcome": outcome,
        "items": items,
        "exc": exc_str[:400] if exc_str else None,
        "raw": {
            "request_seen_t": request_seen_t,
            "response_seen_t": response_seen_t,
            "request_failed_t": fail_t,
            "page_load_ms": (page_load_done - page_load_start) if page_load_start and page_load_done else None,
            "tabs_wait_ms": (tabs_wait_done - tabs_wait_started) if tabs_wait_started and tabs_wait_done else None,
        }
    }

def main():
    print("Starting observability probe 20 samples, gap 3s, no hammering", flush=True)
    results = []
    for i in range(20):
        u = USERS[i % len(USERS)]
        print(f"\n--- {i+1}/20 @{u} ---", flush=True)
        r = single_observability(u, i+1)
        print(f"  outcome={r['outcome']} req={r['STORIES_API_REQUEST_SEEN']} resp={r['STORIES_API_RESPONSE_SEEN']} failed={r['request_failed']} reason={r['request_failed_reason']} status={r['response_status']} req2resp={r['request_to_response_ms']} total={r['total_flow_ms']} items={r['items']}", flush=True)
        results.append(r)
        if i < 19:
            time.sleep(GAP_S)

    out = OUTPUT_DIR / "probe_observability_20_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)

    # Analysis
    from collections import Counter, defaultdict
    import statistics
    cnt = Counter(r["outcome"] for r in results)
    print("\n=== OUTCOME DISTRIBUTION ===", flush=True)
    for k in ["SUCCESS","NO_ACTIVE_STORIES","TAB_TIMEOUT","API_HANG","API_ERR_FAILED","OTHER_TIMEOUT","OTHER_ERROR"]:
        v = cnt.get(k,0)
        print(f"  {k}: {v}/20 ({v/20*100:.1f}%)", flush=True)

    # latencies
    total_vals = [r["total_flow_ms"] for r in results if r["total_flow_ms"]]
    req_vals = [r["request_to_response_ms"] for r in results if r["request_to_response_ms"] is not None]
    def pctl(arr, p):
        if not arr: return None
        s = sorted(arr)
        k = (len(s)-1)*p/100
        f = int(k); c = min(f+1, len(s)-1)
        if f==c: return s[f]
        d0 = k - f
        return s[f]*(1-d0)+s[c]*d0
    print("\n=== LATENCIES ===", flush=True)
    if total_vals:
        print(f"  total_flow_ms p50 {pctl(total_vals,50):.0f} p90 {pctl(total_vals,90):.0f} p95 {pctl(total_vals,95):.0f} min {min(total_vals)} max {max(total_vals)}", flush=True)
    if req_vals:
        print(f"  request_to_response_ms p50 {pctl(req_vals,50):.0f} p90 {pctl(req_vals,90):.0f} p95 {pctl(req_vals,95):.0f} min {min(req_vals)} max {max(req_vals)}", flush=True)
        for r in results:
            if r["request_to_response_ms"]:
                print(f"    {r['seq']} @{r['username']} {r['outcome']} req2resp {r['request_to_response_ms']} items {r['items']}", flush=True)
    else:
        print("  no request_to_response samples (no SUCCESS)", flush=True)

    before_api = sum(1 for r in results if r["outcome"] in ["TAB_TIMEOUT","OTHER_TIMEOUT"] and not r["STORIES_API_REQUEST_SEEN"])
    after_api = sum(1 for r in results if r["STORIES_API_REQUEST_SEEN"])
    print(f"\nFailures before API request: {before_api}/20", flush=True)
    print(f"Failures after API request: {sum(1 for r in results if r['outcome'] in ['API_HANG','API_ERR_FAILED'])}/20", flush=True)
    print(f"  HANG: {cnt.get('API_HANG',0)} ERR_FAILED: {cnt.get('API_ERR_FAILED',0)}", flush=True)

    # per user
    per_user = defaultdict(list)
    for r in results:
        per_user[r["username"]].append(r["outcome"])
    print("\n=== PER USER ===", flush=True)
    for u, lst in per_user.items():
        c = Counter(lst)
        print(f"  @{u}: {dict(c)}", flush=True)

    # batch position (1..5 repeating)
    per_pos = defaultdict(list)
    for r in results:
        pos = ((r["seq"]-1) % 5) + 1
        per_pos[pos].append(r["outcome"])
    print("\n=== PER BATCH POSITION (1..5) ===", flush=True)
    for pos in range(1,6):
        lst = per_pos[pos]
        c = Counter(lst)
        print(f"  pos {pos}: {dict(c)}", flush=True)

    # Save summary
    summary = {
        "counts": dict(cnt),
        "total_p50": pctl(total_vals,50) if total_vals else None,
        "total_p90": pctl(total_vals,90) if total_vals else None,
        "total_p95": pctl(total_vals,95) if total_vals else None,
        "req_p50": pctl(req_vals,50) if req_vals else None,
        "req_p90": pctl(req_vals,90) if req_vals else None,
        "req_p95": pctl(req_vals,95) if req_vals else None,
        "before_api": before_api,
        "after_api": after_api,
        "hang": cnt.get("API_HANG",0),
        "err_failed": cnt.get("API_ERR_FAILED",0),
        "per_user": {k: dict(Counter(v)) for k,v in per_user.items()},
        "per_pos": {k: dict(Counter(v)) for k,v in per_pos.items()},
    }
    (OUTPUT_DIR / "probe_observability_20_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
