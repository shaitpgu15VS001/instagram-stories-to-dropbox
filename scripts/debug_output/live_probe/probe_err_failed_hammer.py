#!/usr/bin/env python3
"""
Hammer test for ERR_FAILED transient - rapid sequential requests on same user
to trigger ERR_FAILED and test retry recovery
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

def probe_once(username, impression):
    request_seen = {"value": False}
    response_seen = {"value": False, "status": None}
    request_failed = {"value": False, "failure": None}
    t0 = time.time()
    def elapsed(): return round(time.time()-t0,2)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        try:
            ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
            page = ctx.new_page()
            page.set_default_timeout(10000)
            def on_req(r):
                if STORIES_API_PATH in r.url and r.method=="POST":
                    request_seen["value"]=True
            def on_resp(r):
                if STORIES_API_PATH in r.url and r.request.method=="POST":
                    response_seen["value"]=True
                    response_seen["status"]=r.status
            def on_fail(r):
                if STORIES_API_PATH in r.url and r.method=="POST":
                    request_failed["value"]=True
                    request_failed["failure"]=str(r.failure)
            page.on("request", on_req); page.on("response", on_resp); page.on("requestfailed", on_fail)
            page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            page.fill("#search-form-input", username)
            page.click("#searchFormButton", force=True, timeout=10000)
            time.sleep(2.5)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            try:
                page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
            except PlaywrightTimeout:
                return {"username":username, "impression":impression, "status":"TAB_TIMEOUT", "request_failed":request_failed["value"], "failure":request_failed["failure"], "elapsed":elapsed()}
            # initial attempt
            initial_failed = None
            initial_status = None
            try:
                with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=STORIES_API_TIMEOUT_MS) as info:
                    page.evaluate("""()=>{
                        const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                        for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                        return false;
                    }""")
                resp = info.value
                # parse
                body = resp.json()
                sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
                from src.fastdl_api import FastDLStoriesAPI
                items = FastDLStoriesAPI.parse_stories(body)
                if items is not None:
                    return {"username":username, "impression":impression, "status":"SUCCESS" if len(items)>0 else "SUCCESS_EMPTY", "items":len(items), "request_failed":request_failed["value"], "elapsed":elapsed()}
                else:
                    return {"username":username, "impression":impression, "status":"PARSE_NONE", "elapsed":elapsed()}
            except PlaywrightTimeout as e:
                if request_failed["value"]:
                    ini = "ERR_FAILED"
                    ini_fail = request_failed["failure"]
                elif request_seen["value"] and not response_seen["value"]:
                    ini = "TIMEOUT_AFTER_REQUEST"
                    ini_fail = None
                else:
                    ini = "TIMEOUT_BEFORE_REQUEST"
                    ini_fail = None
                # retry if ERR_FAILED
                if ini=="ERR_FAILED":
                    time.sleep(4)
                    page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
                    # reset for retry detection
                    request_failed["value"]=False
                    request_failed["failure"]=None
                    response_seen["value"]=False
                    try:
                        with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=STORIES_API_TIMEOUT_MS) as info2:
                            page.evaluate("""()=>{
                                const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                                for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                                return false;
                            }""")
                        resp2 = info2.value
                        body2 = resp2.json()
                        from src.fastdl_api import FastDLStoriesAPI
                        items2 = FastDLStoriesAPI.parse_stories(body2)
                        if items2 is not None:
                            retry_status = "SUCCESS" if len(items2)>0 else "SUCCESS_EMPTY"
                            return {"username":username, "impression":impression, "status":ini, "retry_status":retry_status, "retry_items":len(items2), "retry_request_failed":request_failed["value"], "retry_failure":request_failed["failure"], "retry_elapsed":elapsed(), "elapsed":elapsed(), "initial_failure":ini_fail, "final":"RETRY_"+retry_status}
                        else:
                            return {"username":username, "impression":impression, "status":ini, "retry_status":"PARSE_NONE", "elapsed":elapsed()}
                    except PlaywrightTimeout as e2:
                        if request_failed["value"]:
                            retry_s = "ERR_FAILED"
                        elif request_seen["value"] and not response_seen["value"]:
                            retry_s = "TIMEOUT_AFTER_REQUEST"
                        else:
                            retry_s = "TIMEOUT_BEFORE_REQUEST"
                        return {"username":username, "impression":impression, "status":ini, "retry_status":retry_s, "retry_request_failed":request_failed["value"], "retry_failure":request_failed["failure"], "elapsed":elapsed(), "initial_failure":ini_fail, "final":"RETRY_"+retry_s}
                    except Exception as e2:
                        return {"username":username, "impression":impression, "status":ini, "retry_status":f"EXC:{e2}", "elapsed":elapsed()}
                else:
                    return {"username":username, "impression":impression, "status":ini, "request_failed":request_failed["value"], "failure":ini_fail, "elapsed":elapsed()}
            except Exception as e:
                return {"username":username, "impression":impression, "status":f"EXC:{e}", "elapsed":elapsed()}
        finally:
            try: browser.close()
            except: pass

def main():
    username = "israel_bidur"  # has stories, likely to trigger ERR_FAILED after hammer
    results = []
    print(f"=== HAMMER {username} 12 impressions no gap ===")
    for i in range(1,13):
        r = probe_once(username, i)
        results.append(r)
        print(f"  {i}: {r}", flush=True)
        # no gap to hammer
    # also test alternating users hammer
    print(f"\n=== HAMMER alternating 8 ===")
    for i, u in enumerate(["israel_bidur","mizrahitpage","erevtov","glglz"]*2, start=13):
        r = probe_once(u, i)
        results.append(r)
        print(f"  {i} {u}: {r}", flush=True)

    out = OUTPUT_DIR / "probe_hammer_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")

    err = [r for r in results if r.get("status")=="ERR_FAILED"]
    retry_suc = [r for r in results if r.get("retry_status","").startswith("SUCCESS")]
    print(f"\nERR_FAILED total: {len(err)}/{len(results)}")
    print(f"Retry SUCCESS: {len(retry_suc)}")
    for r in err:
        print(f"  {r['impression']} {r['username']} -> retry {r.get('retry_status')}")

if __name__=="__main__":
    main()
