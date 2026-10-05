#!/usr/bin/env python3
"""
Probe v2 for E-FDL-002: polling + rate-limit investigation.

- Keeps page open 45s after Stories click, captures ALL STORIES API requests/responses
- Tests same username 3x sequentially with same browser context (like production batch)
- Tests the 3 failing usernames in reported order with production delays (2-3s)
"""
import json, time
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUT = Path(__file__).resolve().parent

def redact(s):
    if s:
        try:
            import json as j
            d = j.loads(s)
            for k in ("_s","_ts","_tsc","ts","_sv"):
                if k in d and isinstance(d[k], str) and len(d[k])>10:
                    d[k]="<redacted>"
            return j.dumps(d)
        except: return s[:200]
    return s

def run_polling_test(username: str, keep_open_s=45):
    print(f"\n--- Polling test: {username} keep_open={keep_open_s}s ---")
    requests_log=[]; responses_log=[]; failed_log=[]; t0=time.perf_counter()
    def rel(): return round((time.perf_counter()-t0)*1000,1)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx=browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page=ctx.new_page()
        def on_req(r):
            if STORIES_API_PATH in r.url:
                requests_log.append({"t_ms":rel(),"method":r.method,"url":r.url,"post_data":redact(r.post_data)})
                print(f"  T+{rel():.0f}ms REQ {r.method} {r.url[:60]}")
        def on_resp(r):
            if STORIES_API_PATH in r.url:
                body_len=None; keys=None
                try:
                    j=r.json()
                    if isinstance(j, dict):
                        keys=list(j.keys())
                        rv=j.get("result")
                        body_len=len(rv) if isinstance(rv,list) else str(type(rv))
                except: pass
                responses_log.append({"t_ms":rel(),"status":r.status,"url":r.url,"keys":keys,"result_len":body_len})
                print(f"  T+{rel():.0f}ms RESP {r.status} keys={keys} len={body_len}")
        def on_fail(r):
            if STORIES_API_PATH in r.url:
                failed_log.append({"t_ms":rel(),"method":r.method,"url":r.url,"failure":str(r.failure)})
                print(f"  T+{rel():.0f}ms FAILED {r.failure}")
        page.on("request",on_req); page.on("response",on_resp); page.on("requestfailed",on_fail)
        page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#search-form-input", state="visible", timeout=15000)
        page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay','.modal'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
        page.fill("#search-form-input", username)
        page.click("#searchFormButton", force=True, timeout=15000)
        print(f"  T+{rel():.0f}ms search clicked, sleep 2.5s")
        time.sleep(2.5)
        page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay','.modal'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
        try:
            page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
            print(f"  T+{rel():.0f}ms tabs visible")
        except Exception as e:
            print(f"  T+{rel():.0f}ms tabs TIMEOUT {e}")
            browser.close(); return {"username":username,"tabs":False,"req":requests_log,"resp":responses_log,"failed":failed_log}
        clicked=page.evaluate("()=>{const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));for(const b of bs){if(b.innerText.toLowerCase().includes('stories')){b.scrollIntoView();b.click();return true;}}return false;}")
        print(f"  T+{rel():.0f}ms stories click={clicked}")
        # keep open
        for i in range(keep_open_s):
            time.sleep(1)
            if i%5==0:
                print(f"  T+{rel():.0f}ms polling alive req={len(requests_log)} resp={len(responses_log)} failed={len(failed_log)}")
        browser.close()
    return {"username":username,"tabs":True,"req":requests_log,"resp":responses_log,"failed":failed_log, "polling_observed": len(responses_log)>=2}

def run_ratelimit_batch():
    print("\n=== Rate-limit batch: kolbarama,mizrahitpage,glglz in order with 2-3s gaps ===")
    seq=["kolbarama","mizrahitpage","glglz"]
    batch=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx=browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page=ctx.new_page()
        t0=time.perf_counter()
        def rel(): return round((time.perf_counter()-t0)*1000,1)
        for i,uname in enumerate(seq):
            requests_log=[];responses_log=[];failed_log=[]
            def on_req(r):
                if STORIES_API_PATH in r.url:
                    requests_log.append({"t_ms":rel(),"method":r.method})
            def on_resp(r):
                if STORIES_API_PATH in r.url:
                    responses_log.append({"t_ms":rel(),"status":r.status})
            def on_fail(r):
                if STORIES_API_PATH in r.url:
                    failed_log.append({"t_ms":rel(),"failure":str(r.failure)})
            # attach per-iteration handlers (need to remove old? simplest: use page.on and clear logs per user)
            # Use a single set of handlers with closure capturing current logs lists is messy; reinitialize with new page
            # Instead create new page per user but same browser/context to simulate production reuse? Production creates new page per user? In fastdl_api each call creates new browser+context+page
            # So here we will reuse same browser but new context/page per user like production does per-call fresh browser.
            pass
        browser.close()
    # Simpler: sequential fresh browser per user like production, measure timing
    results=[]
    for i,uname in enumerate(seq):
        print(f"\n  Batch user {i+1}/{len(seq)}: {uname}")
        r=run_polling_test(uname, keep_open_s=15)
        results.append(r)
        if i < len(seq)-1:
            gap=3
            print(f"  Gap {gap}s")
            time.sleep(gap)
    return results

if __name__=="__main__":
    # Test 1: polling observation for kolbarama (known empty) - expect polling requests?
    res1=run_polling_test("kolbarama", keep_open_s=35)
    res2=run_polling_test("israel_bidur", keep_open_s=35)
    # Test 2: sequential same username to detect throttling
    print("\n=== Same username 3x sequentially (kolbarama) ===")
    for rep in range(3):
        print(f"\nRep {rep+1}/3")
        rr=run_polling_test("kolbarama", keep_open_s=10)
        print(f"  result: req={len(rr['req'])} resp={len(rr['resp'])}")
        time.sleep(2)
    # Test 3: reported failing sequence short polling
    batch_results=run_ratelimit_batch()
    out={"generated_at":datetime.now(timezone.utc).isoformat(),"polling_kolbarama":res1,"polling_israel":res2,"batch":batch_results}
    pth=OUT/"probe_polling_ratelimit.json"
    pth.write_text(json.dumps(out, ensure_ascii=False, indent=2),encoding="utf-8")
    print(f"\nWrote {pth}")
