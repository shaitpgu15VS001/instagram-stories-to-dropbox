#!/usr/bin/env python3
"""
חקירה בלבד - ללא שינוי production
בדיקת האם רענון/ context חדש / session חדש מתאושש מחוסר יציבות FastDL
- משווה 3 אסטרטגיות: A SAME PAGE, B NEW PAGE/CONTEXT, C FRESH SESSION
- מודד בנפרד TAB_TIMEOUT, request_seen, response_seen, request_failed, ERR_FAILED, status, latency, recovery time, Stories/result=[]
- הבחנה אמיתית בין resources
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

def do_stories_flow(page, request_seen, response_seen, request_failed, label=""):
    """Helper to do Stories tab click + expect_response, returns (resp_or_none, status, dt, exception)"""
    start = time.time()
    try:
        with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=STORIES_API_TIMEOUT_MS) as info:
            clicked = page.evaluate("""()=>{
                const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                return false;
            }""")
            if not clicked:
                pass
        resp = info.value
        dt = round(time.time()-start,2)
        body = resp.json()
        sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
        from src.fastdl_api import FastDLStoriesAPI
        items = FastDLStoriesAPI.parse_stories(body)
        if items is None:
            return (resp, "PARSE_NONE", dt, None, None)
        items_len = len(items)
        status = "SUCCESS_EMPTY" if items_len==0 else "SUCCESS"
        return (resp, status, dt, None, items_len)
    except PlaywrightTimeout as e:
        dt = round(time.time()-start,2)
        if request_failed["value"]:
            st = "ERR_FAILED"
        elif request_seen["value"] and not response_seen["value"]:
            st = "HANG"
        elif not request_seen["value"]:
            st = "TIMEOUT_BEFORE_REQUEST"
        else:
            st = "TIMEOUT_OTHER"
        return (None, st, dt, e, None)
    except Exception as e:
        dt = round(time.time()-start,2)
        return (None, f"EXC:{e}", dt, e, None)

def attempt_fresh_browser_via_p(p, username):
    """C: fresh browser/context/page via same playwright p but new browser - fresh session"""
    request_seen = {"value": False}
    response_seen = {"value": False, "status": None}
    request_failed = {"value": False, "failure": None}
    t0 = time.time()
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
                return {"status": "TAB_TIMEOUT", "request_seen": request_seen["value"], "response_seen": response_seen["value"], "request_failed": request_failed["value"], "failure": request_failed["failure"], "elapsed": elapsed, "items": None, "response_status": None}
            except Exception as e:
                elapsed = round(time.time()-t0,2)
                return {"status": f"EXC_GOTO:{e}", "elapsed": elapsed, "request_seen": request_seen["value"], "response_seen": response_seen["value"], "request_failed": request_failed["value"]}

            resp, status, dt, exc, items_len = do_stories_flow(page, request_seen, response_seen, request_failed)
            elapsed = round(time.time()-t0,2)
            return {
                "status": status,
                "request_seen": request_seen["value"],
                "response_seen": response_seen["value"],
                "request_failed": request_failed["value"],
                "failure": request_failed["failure"],
                "response_status": response_seen["status"],
                "elapsed": elapsed,
                "dt_stories": dt,
                "items": items_len,
                "exception": str(exc)[:300] if exc else None
            }
        finally:
            try: browser.close()
            except: pass

def attempt_new_context_same_browser(p, browser, username):
    """B: new page/context within same browser (same playwright, same browser instance)"""
    request_seen = {"value": False}
    response_seen = {"value": False, "status": None}
    request_failed = {"value": False, "failure": None}
    t0 = time.time()
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
    try:
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
            try: ctx.close()
            except: pass
            return {"status": "TAB_TIMEOUT", "request_seen": request_seen["value"], "response_seen": response_seen["value"], "request_failed": request_failed["value"], "failure": request_failed["failure"], "elapsed": elapsed, "items": None}
        except Exception as e:
            elapsed = round(time.time()-t0,2)
            try: ctx.close()
            except: pass
            return {"status": f"EXC_GOTO:{e}", "elapsed": elapsed}

        resp, status, dt, exc, items_len = do_stories_flow(page, request_seen, response_seen, request_failed)
        elapsed = round(time.time()-t0,2)
        try: ctx.close()
        except: pass
        return {
            "status": status,
            "request_seen": request_seen["value"],
            "response_seen": response_seen["value"],
            "request_failed": request_failed["value"],
            "failure": request_failed["failure"],
            "response_status": response_seen["status"],
            "elapsed": elapsed,
            "dt_stories": dt,
            "items": items_len,
            "exception": str(exc)[:300] if exc else None
        }
    except Exception as e:
        try: ctx.close()
        except: pass
        return {"status": f"EXC:{e}", "elapsed": round(time.time()-t0,2)}

def attempt_same_page(page, request_seen, response_seen, request_failed):
    """A: same page/context retry - wait 3s, clean overlay, click again"""
    t0 = time.time()
    time.sleep(3)
    page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
    # reset trackers for second attempt on same page
    # keep original but clear for new detection
    # we will reuse same dicts but need to detect new request/response
    # So we snapshot first, then clear
    first_failed = request_failed["value"]
    # clear for new detection (but keep old for comparison)
    request_failed["value"] = False
    request_failed["failure"] = None
    response_seen["value"] = False
    response_seen["status"] = None
    # request_seen stays true, but we need to know if new request
    # we will track new request via same dict - it will stay true, but we care about second response
    # For simplicity, we treat same as before: if second response appears, success
    # Need separate tracker for second request/response
    second_req = {"value": False}
    second_resp = {"value": False, "status": None}
    second_fail = {"value": False, "failure": None}
    # we need to capture new events - but our listeners already set to set request_seen etc.
    # To isolate second attempt, we can add temporary listeners or just rely on same dicts being reset
    # Simpler: we already reset response_seen and request_failed, so second attempt will set them again
    def on_req2(r):
        if STORIES_API_PATH in r.url and r.method=="POST":
            second_req["value"]=True
    def on_resp2(r):
        if STORIES_API_PATH in r.url and r.request.method=="POST":
            second_resp["value"]=True
            second_resp["status"]=r.status
    def on_fail2(r):
        if STORIES_API_PATH in r.url and r.method=="POST":
            second_fail["value"]=True
            second_fail["failure"]=str(r.failure)
    # We already have listeners that set request_seen etc, but we also track second
    # Add additional listeners for second
    page.on("request", on_req2)
    page.on("response", on_resp2)
    page.on("requestfailed", on_fail2)
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
        items_len = len(items) if items is not None else None
        status = "SUCCESS_EMPTY" if items_len==0 else "SUCCESS" if items_len is not None else "PARSE_NONE"
        elapsed = round(time.time()-t0,2)
        return {
            "status": status,
            "request_seen": second_req["value"] or request_seen["value"],
            "response_seen": second_resp["value"],
            "request_failed": second_fail["value"],
            "failure": second_fail["failure"],
            "response_status": second_resp["status"] or resp.status,
            "elapsed": elapsed,
            "dt_stories": elapsed,
            "items": items_len,
        }
    except PlaywrightTimeout as e:
        elapsed = round(time.time()-t0,2)
        if second_fail["value"]:
            st = "ERR_FAILED"
        elif second_req["value"] and not second_resp["value"]:
            st = "HANG"
        elif not second_req["value"]:
            st = "TIMEOUT_BEFORE_REQUEST"
        else:
            st = "TIMEOUT_OTHER"
        return {
            "status": st,
            "request_seen": second_req["value"],
            "response_seen": second_resp["value"],
            "request_failed": second_fail["value"],
            "failure": second_fail["failure"],
            "elapsed": elapsed,
            "dt_stories": elapsed,
            "items": None,
            "exception": str(e)[:300]
        }
    except Exception as e:
        elapsed = round(time.time()-t0,2)
        return {"status": f"EXC:{e}", "elapsed": elapsed}
    finally:
        try:
            page.remove_listener("request", on_req2)
            page.remove_listener("response", on_resp2)
            page.remove_listener("requestfailed", on_fail2)
        except:
            pass

def probe_initial_with_same_page_retry(username):
    """
    Does initial flow on same page, and if HANG (request_seen && !response_seen && !failed) does A retry
    Returns dict with initial and A result
    """
    t0 = time.time()
    request_seen = {"value": False, "t": time.time()}
    response_seen = {"value": False, "status": None}
    request_failed = {"value": False, "failure": None}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
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
            return {
                "username": username,
                "initial": {"status": "TAB_TIMEOUT", "request_seen": request_seen["value"], "response_seen": response_seen["value"], "request_failed": request_failed["value"], "elapsed": elapsed, "failure": request_failed["failure"]},
                "A": None, "B": None, "C": None,
                "initial_type": "TAB_TIMEOUT"
            }
        except Exception as e:
            elapsed = round(time.time()-t0,2)
            try: browser.close()
            except: pass
            return {"username": username, "initial": {"status": f"EXC:{e}", "elapsed": elapsed}, "A": None, "B": None, "C": None, "initial_type": "EXC"}

        # Initial Stories attempt (first)
        resp, status, dt, exc, items_len = do_stories_flow(page, request_seen, response_seen, request_failed)
        initial = {
            "status": status,
            "request_seen": request_seen["value"],
            "response_seen": response_seen["value"],
            "request_failed": request_failed["value"],
            "failure": request_failed["failure"],
            "response_status": response_seen["status"],
            "elapsed": round(time.time()-t0,2),
            "dt_stories": dt,
            "items": items_len,
            "exception": str(exc)[:300] if exc else None
        }
        initial_type = None
        if status == "TAB_TIMEOUT":
            initial_type = "TAB_TIMEOUT"
        elif status == "ERR_FAILED":
            initial_type = "ERR_FAILED"
        elif status == "HANG":
            initial_type = "HANG"
        elif status.startswith("SUCCESS"):
            initial_type = "SUCCESS"
        else:
            initial_type = status

        # If initial was HANG, try A same page retry
        A_result = None
        B_result = None
        C_result = None
        # For investigation we want to test B and C for all failure types, but A only for HANG per existing logic
        # However task says test B/C for TAB_TIMEOUT, ERR_FAILED, HANG separately
        # So we will attempt B and C for any failure (TAB_TIMEOUT, ERR_FAILED, HANG)
        if initial_type in ["TAB_TIMEOUT", "ERR_FAILED", "HANG"]:
            # A: same page retry only if HANG (existing logic)
            if initial_type == "HANG":
                # do A
                A_result = attempt_same_page(page, request_seen, response_seen, request_failed)
                A_result["strategy"] = "A_SAME_PAGE"
            # B: new page/context within same browser (keep p and browser)
            # We need to close current page/context and create new
            try:
                ctx.close()
            except: pass
            # B uses same browser
            B_result = attempt_new_context_same_browser(p, browser, username)
            B_result["strategy"] = "B_NEW_CONTEXT"
            # C: fresh browser via same p but new browser instance (fresh session, fresh cache)
            # Use same playwright p but launch new browser to get fresh cache/session
            try:
                # browser is already the old one, we will launch a new one via p
                C_result = attempt_fresh_browser_via_p(p, username)
            except Exception as e:
                C_result = {"status": f"EXC_C:{e}", "strategy": "C_FRESH_SESSION"}
            else:
                C_result["strategy"] = "C_FRESH_SESSION"
            try: browser.close()
            except: pass
            return {"username": username, "initial": initial, "A": A_result, "B": B_result, "C": C_result, "initial_type": initial_type}
        else:
            # success - no recovery needed
            try: browser.close()
            except: pass
            return {"username": username, "initial": initial, "A": None, "B": None, "C": None, "initial_type": initial_type}

def main():
    target = 20
    results = []
    user_idx = 0
    print(f"Starting recovery strategies probe: target {target} initial attempts", flush=True)
    while len(results) < target:
        username = USERS[user_idx % len(USERS)]
        user_idx += 1
        print(f"\n=== Attempt {len(results)+1}/{target} @{username} ===", flush=True)
        r = probe_initial_with_same_page_retry(username)
        print(f"  Initial: {r['initial']['status']} req={r['initial']['request_seen']} resp={r['initial']['response_seen']} failed={r['initial']['request_failed']} items={r['initial'].get('items')} elapsed={r['initial'].get('elapsed')}", flush=True)
        if r["A"]:
            print(f"  A SAME_PAGE: {r['A']['status']} req={r['A']['request_seen']} resp={r['A']['response_seen']} failed={r['A']['request_failed']} items={r['A'].get('items')} elapsed={r['A'].get('elapsed')}", flush=True)
        if r["B"]:
            print(f"  B NEW_CONTEXT: {r['B']['status']} req={r['B']['request_seen']} resp={r['B']['response_seen']} failed={r['B']['request_failed']} items={r['B'].get('items')} elapsed={r['B'].get('elapsed')}", flush=True)
        if r["C"]:
            print(f"  C FRESH_SESSION: {r['C']['status']} req={r['C']['request_seen']} resp={r['C']['response_seen']} failed={r['C']['request_failed']} items={r['C'].get('items')} elapsed={r['C'].get('elapsed')}", flush=True)
        results.append(r)
        time.sleep(3)

    out = OUTPUT_DIR / "probe_recovery_strategies_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out} with {len(results)} attempts", flush=True)

    # Summary per failure type and strategy
    from collections import Counter
    init_counts = Counter(r["initial_type"] for r in results)
    print("\n=== INITIAL COUNTS ===", flush=True)
    for k,v in init_counts.items():
        print(f"  {k}: {v}", flush=True)

    # For each failure type, recovery success
    for fail_type in ["TAB_TIMEOUT", "ERR_FAILED", "HANG"]:
        subset = [r for r in results if r["initial_type"]==fail_type]
        if not subset:
            continue
        print(f"\n--- Recovery for {fail_type} ({len(subset)} cases) ---", flush=True)
        for strat in ["A","B","C"]:
            succ = sum(1 for r in subset if r[strat] and r[strat]["status"].startswith("SUCCESS"))
            total = sum(1 for r in subset if r[strat] is not None)
            print(f"  {strat}: {succ}/{total} success", flush=True)
            for r in subset:
                if r[strat]:
                    print(f"    -> {r['username']}: {r[strat]['status']} req={r[strat]['request_seen']} resp={r[strat]['response_seen']} failed={r[strat]['request_failed']} items={r[strat].get('items')} elapsed={r[strat].get('elapsed')}", flush=True)

    # Also check if failures correlate to IP throttling (all strategies fail)
    all_fail = [r for r in results if r["initial_type"] in ["TAB_TIMEOUT","ERR_FAILED","HANG"] and r["B"] and r["C"] and not r["B"]["status"].startswith("SUCCESS") and not r["C"]["status"].startswith("SUCCESS")]
    print(f"\nAll-strategies-fail (likely server/IP throttling): {len(all_fail)}/{len([r for r in results if r['initial_type'] in ['TAB_TIMEOUT','ERR_FAILED','HANG']])}", flush=True)
    for r in all_fail:
        print(f"  {r['username']} initial {r['initial_type']} -> B {r['B']['status']} C {r['C']['status']}", flush=True)

if __name__ == "__main__":
    main()
