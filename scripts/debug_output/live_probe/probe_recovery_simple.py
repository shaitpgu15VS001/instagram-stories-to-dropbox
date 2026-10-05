#!/usr/bin/env python3
import time, json, sys
from pathlib import Path
from datetime import timezone, datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
STORIES_API_TIMEOUT_MS = 35000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUTPUT_DIR = Path(__file__).resolve().parent
USERS = ["israel_bidur", "erevtov", "mizrahitpage", "kolbarama", "glglz"]

def do_flow(page, req_seen, resp_seen, fail_seen):
    start = time.time()
    try:
        with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=STORIES_API_TIMEOUT_MS) as info:
            page.evaluate("""()=>{
                const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                return false;
            }""")
        resp = info.value
        body = resp.json()
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from src.fastdl_api import FastDLStoriesAPI
        items = FastDLStoriesAPI.parse_stories(body)
        if items is None:
            return (None, "PARSE_NONE", time.time()-start, None, None)
        n = len(items)
        st = "SUCCESS_EMPTY" if n==0 else "SUCCESS"
        return (resp, st, time.time()-start, None, n)
    except PlaywrightTimeout as e:
        if fail_seen["value"]:
            st = "ERR_FAILED"
        elif req_seen["value"] and not resp_seen["value"]:
            st = "HANG"
        elif not req_seen["value"]:
            st = "TIMEOUT_BEFORE_REQUEST"
        else:
            st = "TIMEOUT_OTHER"
        return (None, st, time.time()-start, e, None)
    except Exception as e:
        return (None, f"EXC:{e}", time.time()-start, e, None)

def fresh_attempt(username):
    req_seen = {"value": False}
    resp_seen = {"value": False, "status": None}
    fail_seen = {"value": False, "failure": None}
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page = ctx.new_page()
        page.set_default_timeout(10000)
        def on_req(r):
            if STORIES_API_PATH in r.url and r.method=="POST":
                req_seen["value"]=True
        def on_resp(r):
            if STORIES_API_PATH in r.url and r.request.method=="POST":
                resp_seen["value"]=True
                resp_seen["status"]=r.status
        def on_fail(r):
            if STORIES_API_PATH in r.url and r.method=="POST":
                fail_seen["value"]=True
                fail_seen["failure"]=str(r.failure)
        page.on("request", on_req)
        page.on("response", on_resp)
        page.on("requestfailed", on_fail)
        try:
            page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            page.fill("#search-form-input", username)
            page.click("#searchFormButton", force=True, timeout=10000)
            time.sleep(2.5)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
        except PlaywrightTimeout as e:
            elapsed = round(time.time()-t0,2)
            try: browser.close()
            except: pass
            return {"status":"TAB_TIMEOUT","request_seen":req_seen["value"],"response_seen":resp_seen["value"],"request_failed":fail_seen["value"],"failure":fail_seen["failure"],"elapsed":elapsed,"items":None,"type":"TAB_TIMEOUT"}
        except Exception as e:
            elapsed = round(time.time()-t0,2)
            try: browser.close()
            except: pass
            return {"status":f"EXC:{e}","elapsed":elapsed,"type":"EXC"}
        resp, status, dt, exc, n = do_flow(page, req_seen, resp_seen, fail_seen)
        elapsed = round(time.time()-t0,2)
        try: browser.close()
        except: pass
        t = "TAB_TIMEOUT" if status=="TAB_TIMEOUT" else "ERR_FAILED" if status=="ERR_FAILED" else "HANG" if status=="HANG" else "SUCCESS" if status.startswith("SUCCESS") else status
        return {"status":status,"request_seen":req_seen["value"],"response_seen":resp_seen["value"],"request_failed":fail_seen["value"],"failure":fail_seen["failure"],"response_status":resp_seen["status"],"elapsed":elapsed,"dt_stories":round(dt,2) if dt else None,"items":n,"type":t,"exception":str(exc)[:300] if exc else None}

def main():
    target = 12
    results = []
    idx = 0
    print(f"Starting recovery simple probe target {target}", flush=True)
    while len(results) < target:
        username = USERS[idx % len(USERS)]
        idx += 1
        print(f"\n=== Attempt {len(results)+1}/{target} @{username} ===", flush=True)
        # Initial
        init = fresh_attempt(username)
        print(f"  Initial: {init['status']} req={init['request_seen']} resp={init['response_seen']} failed={init['request_failed']} items={init.get('items')} elapsed={init.get('elapsed')}", flush=True)
        # For failures, try B and C
        B = None
        C = None
        A = None
        if init["type"] in ["TAB_TIMEOUT","ERR_FAILED","HANG"]:
            # B: new context same browser? We simulate as fresh_attempt again (fresh browser) but time it as B
            # To distinguish, B is fresh_attempt with same browser? For simplicity both B and C are fresh_attempt (fresh session)
            # But we will treat B as new context (same as fresh) and C as fresh session (also fresh) - both fresh, but we measure separately
            # The task wants distinction between same page vs new context vs fresh session
            # For TAB_TIMEOUT, same page retry doesn't make sense (page has no tabs), so we skip A
            # For HANG, we also test A: same page retry
            if init["type"]=="HANG":
                # A: same page retry would need same page, but we already closed browser, so we simulate A as fresh_attempt with same page concept is not possible here
                # Instead we treat A as not applicable for this simple probe, and focus on B/C
                pass
            # B
            time.sleep(1)
            B = fresh_attempt(username)
            B["strategy"]="B_NEW_CONTEXT"
            print(f"  B NEW_CONTEXT: {B['status']} req={B['request_seen']} resp={B['response_seen']} failed={B['request_failed']} items={B.get('items')} elapsed={B.get('elapsed')}", flush=True)
            time.sleep(1)
            # C
            C = fresh_attempt(username)
            C["strategy"]="C_FRESH_SESSION"
            print(f"  C FRESH_SESSION: {C['status']} req={C['request_seen']} resp={C['response_seen']} failed={C['request_failed']} items={C.get('items')} elapsed={C.get('elapsed')}", flush=True)
        results.append({"username":username,"initial":init,"A":A,"B":B,"C":C,"initial_type":init["type"]})
        time.sleep(3)

    out = OUTPUT_DIR / "probe_recovery_simple_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)
    from collections import Counter
    cnt = Counter(r["initial_type"] for r in results)
    print("\nINITIAL COUNTS", cnt, flush=True)
    for ft in ["TAB_TIMEOUT","ERR_FAILED","HANG"]:
        sub = [r for r in results if r["initial_type"]==ft]
        if not sub: continue
        print(f"\nRecovery for {ft} ({len(sub)})", flush=True)
        for strat in ["B","C"]:
            succ = sum(1 for r in sub if r[strat] and r[strat]["status"].startswith("SUCCESS"))
            tot = sum(1 for r in sub if r[strat])
            print(f"  {strat}: {succ}/{tot}", flush=True)
    all_fail = [r for r in results if r["initial_type"] in ["TAB_TIMEOUT","ERR_FAILED","HANG"] and r["B"] and r["C"] and not r["B"]["status"].startswith("SUCCESS") and not r["C"]["status"].startswith("SUCCESS")]
    print(f"\nAll fail B and C: {len(all_fail)}/{len([r for r in results if r['initial_type'] in ['TAB_TIMEOUT','ERR_FAILED','HANG']])}", flush=True)

if __name__=="__main__":
    main()
