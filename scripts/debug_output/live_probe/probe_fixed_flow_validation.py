#!/usr/bin/env python3
import time, json, sys
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_API_PATH = "/api/v1/instagram/userInfo"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUTPUT_DIR = Path(__file__).resolve().parent
USERS = ["kolbarama","mizrahitpage","glglz","israel_bidur","erevtov","natgeo"]
GAP_S = 3
STORIES_TIMEOUT = 15000
TABS_TIMEOUT = 30000

def get_dom(page):
    return page.evaluate("""()=>{
        const input=document.querySelector('#search-form-input');
        const btn=document.querySelector('#searchFormButton');
        return {
            inputValue: input ? input.value : null,
            btnDisabled: btn ? btn.disabled : null,
            btnVisible: btn ? !!(btn.offsetParent) : null,
            hasUserInfo: !!document.querySelector('.user-info'),
            tabsCount: document.querySelectorAll('button.tabs-component__button').length,
            loaders: document.querySelectorAll('.loader, .spinner, [class*="load"], .skeleton').length,
        };
    }""")

def probe_one(username, seq):
    t0=time.time()
    req_seen={"v":False}
    resp_seen={"v":False,"status":None}
    fail_seen={"v":False,"failure":None}
    user_req=False
    user_resp=False
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx=browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page=ctx.new_page()
        page.set_default_timeout(10000)
        def on_req(r):
            if USER_API_PATH in r.url or STORIES_API_PATH in r.url:
                if USER_API_PATH in r.url:
                    req_seen["v"]=True
                # stories also
                if STORIES_API_PATH in r.url and r.method=="POST":
                    req_seen["v"]=True
        def on_resp(r):
            if USER_API_PATH in r.url or STORIES_API_PATH in r.url:
                if USER_API_PATH in r.url and r.status==200:
                    resp_seen["v"]=True
                    resp_seen["status"]=r.status
                if STORIES_API_PATH in r.url and r.request.method=="POST":
                    resp_seen["v"]=True
                    resp_seen["status"]=r.status
        def on_fail(r):
            if "api-wh.fastdl.app" in r.url:
                fail_seen["v"]=True
                fail_seen["failure"]=str(r.failure)
        page.on("request", on_req)
        page.on("response", on_resp)
        page.on("requestfailed", on_fail)
        try:
            page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            # Fixed flow: fill -> wait input contains username and button enabled -> click without force
            page.fill("#search-form-input", username)
            # wait input contains username and button enabled
            try:
                page.wait_for_function("""(u)=>{
                    const i=document.querySelector('#search-form-input');
                    const b=document.querySelector('#searchFormButton');
                    return i && i.value.includes(u) && b && !b.disabled && b.offsetParent!==null;
                }""", arg=username, timeout=5000)
            except PlaywrightTimeout:
                # still continue, but log
                pass
            before_click = get_dom(page)
            # click without force
            page.click("#searchFormButton", timeout=5000)
            time.sleep(2.5)
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            # wait tabs
            tabs_visible=False
            try:
                page.wait_for_selector("button.tabs-component__button", state="visible", timeout=TABS_TIMEOUT)
                tabs_visible=True
            except PlaywrightTimeout:
                tabs_visible=False
            dom_final = get_dom(page)
            total = round(time.time()-t0,2)
            # classify TAB
            if not tabs_visible:
                # TAB_TIMEOUT - distinguish A/B
                has_user = dom_final["hasUserInfo"]
                tabs_cnt = dom_final["tabsCount"]
                # need to know if userInfo was ever requested - use req_seen for userInfo
                # Our req_seen tracks both userInfo and stories, but for TAB we care userInfo
                # We can refine: check if any userInfo request was seen (we tracked)
                # For this probe, req_seen true means at least one of userInfo/stories was seen, but for TAB_TIMEOUT we want userInfo specifically
                # Use a more precise check: look at page requests - we already have generic
                # For simplicity, if hasUserInfo false and tabs 0 and not req_seen -> Type A, else B
                if not has_user and tabs_cnt==0 and not req_seen["v"]:
                    outcome="TAB_TIMEOUT_TYPE_A"
                elif has_user and tabs_cnt>0:
                    outcome="TAB_TIMEOUT_TYPE_B"
                else:
                    # hasUser false but req_seen true? then it's also B-like
                    outcome="TAB_TIMEOUT_TYPE_A" if not has_user else "TAB_TIMEOUT_TYPE_B"
                try: browser.close()
                except: pass
                return {
                    "seq":seq,"username":username,"outcome":outcome,
                    "hasUserInfo":has_user,"tabsCount":tabs_cnt,"loaders":dom_final["loaders"],
                    "req_seen":req_seen["v"],"resp_seen":resp_seen["v"],"request_failed":fail_seen["v"],"failure":fail_seen["failure"],
                    "total":total,"before_click":before_click,"dom_final":dom_final
                }
            # tabs visible -> try stories
            try:
                with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=STORIES_TIMEOUT) as info:
                    page.evaluate("""()=>{
                        const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                        for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                        return false;
                    }""")
                resp = info.value
                body=resp.json()
                sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
                from src.fastdl_api import FastDLStoriesAPI
                items=FastDLStoriesAPI.parse_stories(body)
                n=len(items) if items is not None else None
                total = round(time.time()-t0,2)
                try: browser.close()
                except: pass
                if n==0:
                    return {"seq":seq,"username":username,"outcome":"NO_ACTIVE_STORIES","items":0,"hasUserInfo":dom_final["hasUserInfo"],"tabsCount":dom_final["tabsCount"],"req_seen":True,"resp_seen":True,"request_failed":False,"total":total,"before_click":before_click}
                elif n and n>0:
                    return {"seq":seq,"username":username,"outcome":"SUCCESS","items":n,"hasUserInfo":dom_final["hasUserInfo"],"tabsCount":dom_final["tabsCount"],"req_seen":True,"resp_seen":True,"request_failed":False,"total":total,"before_click":before_click}
                else:
                    return {"seq":seq,"username":username,"outcome":"OTHER","items":n,"total":total,"before_click":before_click}
            except PlaywrightTimeout as e:
                total = round(time.time()-t0,2)
                try: browser.close()
                except: pass
                # after tabs, stories timeout
                if fail_seen["v"]:
                    return {"seq":seq,"username":username,"outcome":"API_ERR_FAILED","req_seen":True,"resp_seen":False,"request_failed":True,"failure":fail_seen["failure"],"total":total,"before_click":before_click}
                elif req_seen["v"] and not resp_seen["v"]:
                    return {"seq":seq,"username":username,"outcome":"API_HANG","req_seen":True,"resp_seen":False,"request_failed":False,"total":total,"before_click":before_click}
                else:
                    return {"seq":seq,"username":username,"outcome":"OTHER","req_seen":req_seen["v"],"resp_seen":resp_seen["v"],"total":total,"before_click":before_click}
        except Exception as e:
            total = round(time.time()-t0,2)
            try: browser.close()
            except: pass
            return {"seq":seq,"username":username,"outcome":f"OTHER:{e}"[:100],"total":total}

def main():
    target=30
    results=[]
    print(f"Starting fixed flow validation 30 attempts gap {GAP_S}s", flush=True)
    for i in range(target):
        u=USERS[i % len(USERS)]
        print(f"\n=== {i+1}/{target} @{u} ===", flush=True)
        r=probe_one(u, i+1)
        print(f"  -> {r['outcome']} hasUser={r.get('hasUserInfo')} tabs={r.get('tabsCount')} req={r.get('req_seen')} resp={r.get('resp_seen')} failed={r.get('request_failed')} items={r.get('items')} total={r.get('total')} before_input='{r.get('before_click',{}).get('inputValue')}' btnDis={r.get('before_click',{}).get('btnDisabled')}", flush=True)
        results.append(r)
        if i < target-1:
            time.sleep(GAP_S)
    out=OUTPUT_DIR / "probe_fixed_flow_validation_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)
    from collections import Counter
    cnt=Counter(r["outcome"] for r in results)
    print("\n=== DISTRIBUTION ===", flush=True)
    for k in ["SUCCESS","NO_ACTIVE_STORIES","TAB_TIMEOUT_TYPE_A","TAB_TIMEOUT_TYPE_B","API_HANG","API_ERR_FAILED","OTHER"]:
        v=cnt.get(k,0)
        if v: print(f"  {k}: {v}/{target} ({v/target*100:.1f}%)", flush=True)
    # Type A specific
    type_a = cnt.get("TAB_TIMEOUT_TYPE_A",0)
    print(f"\nType A: {type_a}/{target} ({type_a/target*100:.1f}%) vs baseline A 30% (3/10) and 83% experimental", flush=True)
    # also check before_click input contains username
    bad_before = sum(1 for r in results if r.get("before_click",{}).get("inputValue") != r["username"])
    print(f"before_click input mismatch: {bad_before}/{target}", flush=True)

if __name__=="__main__":
    main()
