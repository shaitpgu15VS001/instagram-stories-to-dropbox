#!/usr/bin/env python3
"""
probe ניסיוני - הכרעת Type A
- ללא שינוי production, ללא retry, ללא שינוי timeout, ללא cache/context חדש
- 12 ניסיונות, gap 3s
- flow ניסיוני: המתנה ל-disabled=false + window.Vue, ואז waitForResponse userInfo 15s לפני tabs
"""
import time, json, sys
from pathlib import Path
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_API_PATH = "/api/v1/instagram/userInfo"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUTPUT_DIR = Path(__file__).resolve().parent
USERS = ["kolbarama", "mizrahitpage", "glglz", "israel_bidur", "erevtov", "natgeo"]

def poll_dom(page):
    return page.evaluate("""()=>{
        const btn = document.querySelector('#searchFormButton');
        const vueExists = !!window.Vue || !!window.__VUE__ || !!window.app || !!document.querySelector('[data-v-app]');
        const tabs = Array.from(document.querySelectorAll('button.tabs-component__button'));
        const tabInfos = tabs.map(b=> {
            const r=b.getBoundingClientRect(); const s=window.getComputedStyle(b);
            return {text:(b.innerText||'').trim().slice(0,30), visible: !!(b.offsetParent!==null && r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'), className:b.className.slice(0,60)};
        });
        return {
            btnExists: !!btn,
            btnDisabled: btn ? !!btn.disabled : null,
            btnVisible: btn ? !!(btn.offsetParent!==null) : null,
            vueExists: vueExists,
            readyState: document.readyState,
            tabsCount: tabs.length,
            tabs: tabInfos,
            hasUserInfo: !!document.querySelector('.user-info, [class*="user-info"]'),
            loaders: document.querySelectorAll('.loader, .spinner, [class*="load"], .skeleton').length,
        };
    }""")

def probe_one_exp(username, seq):
    t0 = time.time()
    def rel(): return round((time.time()-t0)*1000)
    # tracking
    user_req_t = None
    user_resp_t = None
    user_status = None
    stories_req_t = None
    stories_resp_t = None
    request_failed = False
    # timeline
    timeline = []
    def log(evt, **kw):
        timeline.append({"t": rel(), "evt": evt, **kw})

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page = ctx.new_page()
        page.set_default_timeout(10000)
        # listeners for userInfo
        def on_req(r):
            nonlocal user_req_t, stories_req_t
            if USER_API_PATH in r.url and r.method=="POST":
                if user_req_t is None:
                    user_req_t = time.time()
                    log("userInfo_request", url=r.url[:80])
            if STORIES_API_PATH in r.url and r.method=="POST":
                if stories_req_t is None:
                    stories_req_t = time.time()
        def on_resp(r):
            nonlocal user_resp_t, user_status, stories_resp_t
            if USER_API_PATH in r.url and r.request.method=="POST":
                if user_resp_t is None:
                    user_resp_t = time.time()
                    user_status = r.status
                    log("userInfo_response", status=r.status)
            if STORIES_API_PATH in r.url and r.request.method=="POST":
                if stories_resp_t is None:
                    stories_resp_t = time.time()
        def on_fail(r):
            nonlocal request_failed
            if STORIES_API_PATH in r.url or USER_API_PATH in r.url:
                if "ERR_FAILED" in str(r.failure):
                    request_failed = True
        page.on("request", on_req)
        page.on("response", on_resp)
        page.on("requestfailed", on_fail)

        # state before click
        pre_click_state = None
        click_t = None
        tabs_visible_t = None
        outcome = None
        outcome_detail = None

        try:
            page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=10000)
            page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
            # clean
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            page.fill("#search-form-input", username)
            # 1. המתן עד שכפתור Search קיים ו-disabled=false ו-window.Vue קיים
            pre_wait_start = time.time()
            try:
                page.wait_for_function("""()=>{
                    const btn=document.querySelector('#searchFormButton');
                    const vueExists=!!window.Vue || !!window.__VUE__ || !!window.app || !!document.querySelector('[data-v-app]');
                    return btn && !btn.disabled && btn.offsetParent!==null;
                }""", timeout=5000)
                log("pre_click_wait_success", waited_ms=round((time.time()-pre_wait_start)*1000))
            except PlaywrightTimeout:
                log("pre_click_wait_timeout", waited_ms=round((time.time()-pre_wait_start)*1000))
            pre_click_state = poll_dom(page)
            log("pre_click_state", **pre_click_state)
            # 2. click
            click_t = time.time()
            log("click", t_click=round((click_t - t0)*1000))
            page.click("#searchFormButton", force=True, timeout=10000)
            time.sleep(2.5)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            # 3. המתן ל-userInfo 15s - ניסיוני
            user_wait_start = time.time()
            try:
                with page.expect_response(lambda r: USER_API_PATH in r.url and r.status==200, timeout=15000) as uinfo:
                    # busy wait for response to arrive, expect_response will capture it
                    _resp = uinfo.value
                # ensure status captured
                if user_status is None:
                    try:
                        user_status = _resp.status
                    except:
                        pass
                log("userInfo_wait_success", waited_ms=round((time.time()-user_wait_start)*1000), user_status=user_status)
            except PlaywrightTimeout as e:
                log("userInfo_wait_timeout", waited_ms=round((time.time()-user_wait_start)*1000), user_status=user_status, has_req=user_req_t is not None)
                # if timeout, we still continue to tabs wait to see outcome, but this is Type A candidate
            # 4. רק אחרי userInfo -> tabs
            tabs_start = time.time()
            try:
                page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
                tabs_visible_t = time.time()
                log("tabs_visible", waited_ms=round((tabs_visible_t - tabs_start)*1000))
            except PlaywrightTimeout as e:
                log("tabs_timeout", waited_ms=round((time.time()-tabs_start)*1000))
                # classify Type A vs B
                dom = poll_dom(page)
                has_user = dom["hasUserInfo"]
                tabs_cnt = dom["tabsCount"]
                loaders = dom["loaders"]
                if not has_user and tabs_cnt==0 and user_req_t is None:
                    outcome = "TAB_TIMEOUT_TYPE_A"
                    outcome_detail = f"hasUserInfo false, tabs 0, userInfo 0/0 - Type A"
                elif has_user and tabs_cnt==4:
                    outcome = "TAB_TIMEOUT_TYPE_B"
                    outcome_detail = f"hasUserInfo true, tabs 4 but not visible, loaders {loaders} - Type B"
                else:
                    outcome = "TAB_TIMEOUT_OTHER"
                    outcome_detail = f"hasUser {has_user} tabs {tabs_cnt} loaders {loaders}"
                # also try stories to see if would have worked
                total_ms = round((time.time()-t0)*1000)
                try: browser.close()
                except: pass
                return {
                    "seq": seq, "username": username, "outcome": outcome, "detail": outcome_detail,
                    "pre_click_state": pre_click_state,
                    "user_req_t": round((user_req_t - click_t)*1000) if user_req_t and click_t else None,
                    "user_req_to_resp": round((user_resp_t - user_req_t)*1000) if user_req_t and user_resp_t else None,
                    "resp_to_tabs": None,
                    "total_ms": total_ms,
                    "timeline": timeline,
                    "dom_final": dom
                }
            # if tabs visible -> success, try stories
            dom = poll_dom(page)
            try:
                with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=10000) as info:
                    page.evaluate("""()=>{
                        const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                        for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                        return false;
                    }""")
                resp = info.value
                body = resp.json()
                import sys as _sys
                from pathlib import Path as _P
                _sys.path.insert(0, str(_P(__file__).resolve().parents[3]))
                from src.fastdl_api import FastDLStoriesAPI
                items = FastDLStoriesAPI.parse_stories(body)
                n = len(items) if items else 0
                outcome = "TAB_SUCCESS"
                total_ms = round((time.time()-t0)*1000)
                try: browser.close()
                except: pass
                return {
                    "seq": seq, "username": username, "outcome": outcome,
                    "pre_click_state": pre_click_state,
                    "user_req_t": round((user_req_t - click_t)*1000) if user_req_t and click_t else None,
                    "user_req_to_resp": round((user_resp_t - user_req_t)*1000) if user_req_t and user_resp_t else None,
                    "resp_to_tabs": round((tabs_visible_t - user_resp_t)*1000) if tabs_visible_t and user_resp_t else None,
                    "total_ms": total_ms,
                    "stories_items": n,
                    "timeline": timeline,
                    "dom_final": dom
                }
            except Exception as e:
                total_ms = round((time.time()-t0)*1000)
                try: browser.close()
                except: pass
                return {
                    "seq": seq, "username": username, "outcome": "TAB_SUCCESS_STORIES_TIMEOUT",
                    "pre_click_state": pre_click_state,
                    "user_req_t": round((user_req_t - click_t)*1000) if user_req_t and click_t else None,
                    "user_req_to_resp": round((user_resp_t - user_req_t)*1000) if user_req_t and user_resp_t else None,
                    "resp_to_tabs": round((tabs_visible_t - user_resp_t)*1000) if tabs_visible_t and user_resp_t else None,
                    "total_ms": total_ms,
                    "timeline": timeline,
                    "dom_final": dom,
                    "stories_exc": str(e)[:200]
                }
        except Exception as e:
            total_ms = round((time.time()-t0)*1000)
            try: browser.close()
            except: pass
            return {"seq": seq, "username": username, "outcome": f"EXC:{e}"[:200], "total_ms": total_ms, "timeline": timeline}
        finally:
            try: browser.close()
            except: pass

def main():
    target = 12
    results = []
    print(f"Starting Type A experimental probe target {target} gap 3s", flush=True)
    for i in range(target):
        u = USERS[i % len(USERS)]
        print(f"\n=== Probe {i+1}/{target} @{u} ===", flush=True)
        r = probe_one_exp(u, i+1)
        print(f"  outcome={r['outcome']} detail={r.get('detail','')} pre_btnDisabled={r.get('pre_click_state',{}).get('btnDisabled')} vue={r.get('pre_click_state',{}).get('vueExists')} userReq={r.get('user_req_t')} userResp={r.get('user_req_to_resp')} resp2tabs={r.get('resp_to_tabs')} total={r.get('total_ms')} stories_items={r.get('stories_items')}", flush=True)
        results.append(r)
        if i < target-1:
            time.sleep(3)
    out = OUTPUT_DIR / "probe_typeA_experimental_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)
    # summary
    from collections import Counter
    cnt = Counter(r["outcome"] for r in results)
    print("\n=== SUMMARY ===", flush=True)
    for k,v in cnt.items():
        print(f"  {k}: {v}/{len(results)} ({v/len(results)*100:.1f}%)", flush=True)
    # baseline 6/8 Type A
    type_a = sum(1 for r in results if r["outcome"]=="TAB_TIMEOUT_TYPE_A")
    type_b = sum(1 for r in results if r["outcome"]=="TAB_TIMEOUT_TYPE_B")
    print(f"\nType A: {type_a}/{len(results)} ({type_a/len(results)*100:.1f}%) vs baseline 6/8 (75% of TAB, 37.5% overall) or 6/16 (37.5%)", flush=True)
    print(f"Type B: {type_b}/{len(results)}", flush=True)
    # timings for success
    for r in results:
        if r["outcome"]=="TAB_SUCCESS":
            print(f"  SUCCESS @{r['username']} click->userReq {r.get('user_req_t')}ms req->resp {r.get('user_req_to_resp')}ms resp->tabs {r.get('resp_to_tabs')}ms", flush=True)

if __name__ == "__main__":
    main()
