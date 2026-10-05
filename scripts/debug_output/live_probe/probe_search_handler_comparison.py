#!/usr/bin/env python3
import time, json, sys, re
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_API_PATH = "/api/v1/instagram/userInfo"
POSTS_API_PATH = "/api/v1/instagram/postsV2"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUTPUT_DIR = Path(__file__).resolve().parent
GAP_S = 3

def get_dom_state(page):
    return page.evaluate("""()=>{
        const input = document.querySelector('#search-form-input');
        const btn = document.querySelector('#searchFormButton');
        const form = document.querySelector('#searchForm');
        // find Vue query by searching for component with query prop
        let vueQuery = null;
        let vueFound = false;
        try {
            const all = document.querySelectorAll('*');
            for(const el of all){
                const comp = el.__vueParentComponent;
                if(comp){
                    const data = comp.data || comp.setupState || comp.exposed;
                    if(data && ('query' in data)){
                        vueQuery = data.query;
                        vueFound = true;
                        break;
                    }
                    // also check proxy
                    if(comp.proxy && 'query' in comp.proxy){
                        vueQuery = comp.proxy.query;
                        vueFound = true;
                        break;
                    }
                }
            }
            // fallback via window
            if(!vueFound && window.__vue_app__){
                vueQuery = 'app exists but not found';
            }
        } catch(e){ vueQuery = 'err:'+e.message; }
        return {
            inputValue: input ? input.value : null,
            inputExists: !!input,
            btnExists: !!btn,
            btnDisabled: btn ? btn.disabled : null,
            btnVisible: btn ? !!(btn.offsetParent) : null,
            btnRect: btn ? {x: Math.round(btn.getBoundingClientRect().x), y: Math.round(btn.getBoundingClientRect().y), w: Math.round(btn.getBoundingClientRect().width), h:Math.round(btn.getBoundingClientRect().height)} : null,
            formExists: !!form,
            formOnSubmit: form ? form.getAttribute('onsubmit') : null,
            vueQuery: vueQuery,
            vueFound: vueFound,
            hasUserInfo: !!document.querySelector('.user-info'),
            tabsCount: document.querySelectorAll('button.tabs-component__button').length,
            readyState: document.readyState,
            url: location.href
        };
    }""")

def do_search_via_method(page, method, username):
    """Returns dict with timings and events"""
    events = []
    reqs = []
    cons = []
    def on_req(r):
        if "api-wh.fastdl.app" in r.url:
            reqs.append(r.url[:100])
            events.append(f"REQ {r.method} {r.url.split('/')[-1][:40]}")
    def on_console(m):
        if m.type in ["error","warning","log"]:
            cons.append(f"{m.type}:{m.text[:100]}")
    page.on("request", on_req)
    page.on("console", on_console)
    # before state
    before = get_dom_state(page)
    # do method
    if method == "A":
        # current: fill + force click
        page.fill("#search-form-input", username)
        time.sleep(0.2)
        after_fill = get_dom_state(page)
        page.click("#searchFormButton", force=True, timeout=5000)
        time.sleep(0.1)
        after_click = get_dom_state(page)
        return {"before": before, "after_fill": after_fill, "after_click": after_click, "reqs": reqs, "cons": cons, "method": "A_fill_forceClick"}
    elif method == "B":
        page.fill("#search-form-input", username)
        time.sleep(0.2)
        after_fill = get_dom_state(page)
        page.click("#searchFormButton", timeout=5000)
        time.sleep(0.1)
        after_click = get_dom_state(page)
        return {"before": before, "after_fill": after_fill, "after_click": after_click, "reqs": reqs, "cons": cons, "method": "B_fill_clickNoForce"}
    elif method == "C":
        page.focus("#search-form-input")
        # clear first
        page.evaluate("()=>{const i=document.querySelector('#search-form-input'); i.value=''; i.dispatchEvent(new Event('input',{bubbles:true}));}")
        time.sleep(0.2)
        page.keyboard.type(username, delay=80)
        time.sleep(0.3)
        after_fill = get_dom_state(page)
        before_press = get_dom_state(page)
        page.keyboard.press("Enter")
        time.sleep(0.1)
        after_click = get_dom_state(page)
        return {"before": before, "after_fill": after_fill, "after_click": after_click, "reqs": reqs, "cons": cons, "method": "C_type_Enter"}
    elif method == "D":
        # DOM value + dispatch input/change
        page.evaluate("""(u)=>{
            const input=document.querySelector('#search-form-input');
            input.focus();
            input.value=u;
            input.dispatchEvent(new Event('input', {bubbles:true}));
            input.dispatchEvent(new Event('change', {bubbles:true}));
            // Vue needs composition?
            input.dispatchEvent(new KeyboardEvent('keydown', {bubbles:true, key:'a'}));
            input.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true, key:'a'}));
        }""", username)
        time.sleep(0.3)
        after_fill = get_dom_state(page)
        page.click("#searchFormButton", timeout=5000)
        time.sleep(0.1)
        after_click = get_dom_state(page)
        return {"before": before, "after_fill": after_fill, "after_click": after_click, "reqs": reqs, "cons": cons, "method": "D_dispatch_input"}
    elif method == "E":
        page.fill("#search-form-input", username)
        time.sleep(0.2)
        after_fill = get_dom_state(page)
        # submit form
        page.evaluate("""()=>{
            const form=document.querySelector('#searchForm');
            if(form){
                form.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}));
                if(form.requestSubmit) form.requestSubmit();
            }
        }""")
        time.sleep(0.1)
        after_click = get_dom_state(page)
        return {"before": before, "after_fill": after_fill, "after_click": after_click, "reqs": reqs, "cons": cons, "method": "E_formSubmit"}
    else:
        return {"before": before, "reqs": reqs, "cons": cons}

def probe_one_method(username, method):
    t0 = time.time()
    req_seen = {"v": False}
    resp_seen = {"v": False}
    fail_seen = {"v": False}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page = ctx.new_page()
        page.set_default_timeout(10000)
        def on_req(r):
            if USER_API_PATH in r.url or POSTS_API_PATH in r.url:
                req_seen["v"]=True
        def on_resp(r):
            if USER_API_PATH in r.url or POSTS_API_PATH in r.url:
                if r.status==200:
                    resp_seen["v"]=True
        def on_fail(r):
            if USER_API_PATH in r.url:
                fail_seen["v"]=True
        page.on("request", on_req)
        page.on("response", on_resp)
        page.on("requestfailed", on_fail)
        page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
        page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
        # do method
        info = do_search_via_method(page, method, username)
        time.sleep(2.5)
        page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
        # wait for tabs 15s (shorter to save time, but enough to see Type A)
        tabs_start = time.time()
        tabs_visible = False
        try:
            page.wait_for_selector("button.tabs-component__button", state="visible", timeout=15000)
            tabs_visible = True
        except PlaywrightTimeout:
            tabs_visible = False
        total = round(time.time()-t0,2)
        # final DOM
        final_dom = get_dom_state(page)
        # determine outcome
        if tabs_visible:
            outcome = "TAB_SUCCESS"
            # check type
            has_user = final_dom["hasUserInfo"]
            tabs_cnt = final_dom["tabsCount"]
            if has_user and tabs_cnt>=2:
                # try stories quickly
                try:
                    with page.expect_response(lambda r: STORIES_API_PATH in r.url, timeout=8000) as inf:
                        page.evaluate("""()=>{
                            const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                            for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.click(); return true; }}
                        }""")
                    resp = inf.value
                    stories = f"STORIES_{resp.status}"
                except:
                    stories = "STORIES_TIMEOUT"
            else:
                stories = "NO_STORIES"
        else:
            # TAB_TIMEOUT - classify A vs B
            has_user = final_dom["hasUserInfo"]
            tabs_cnt = final_dom["tabsCount"]
            if not has_user and tabs_cnt==0 and not req_seen["v"]:
                outcome = "TAB_TIMEOUT_TYPE_A"
            elif has_user and tabs_cnt>0:
                outcome = "TAB_TIMEOUT_TYPE_B"
            else:
                outcome = "TAB_TIMEOUT_OTHER"
            stories = None
        try: browser.close()
        except: pass
        return {
            "method": method,
            "username": username,
            "outcome": outcome,
            "hasUserInfo": final_dom["hasUserInfo"],
            "tabsCount": final_dom["tabsCount"],
            "req_seen": req_seen["v"],
            "resp_seen": resp_seen["v"],
            "fail_seen": fail_seen["v"],
            "total": total,
            "before": info["before"],
            "after_fill": info["after_fill"],
            "after_click": info["after_click"],
            "stories": stories,
            "reqs": info["reqs"][:3],
        }

def main():
    # test 10 per method for A, C, D (most relevant) = 30
    methods = ["A","C","D"]
    per_method = 10
    results = []
    for method in methods:
        print(f"\n===== METHOD {method} 10 attempts =====", flush=True)
        for i in range(per_method):
            u = ["kolbarama","mizrahitpage","glglz","israel_bidur","erevtov"][i % 5]
            print(f"  {method} {i+1}/10 @{u}", flush=True)
            r = probe_one_method(u, method)
            print(f"    -> {r['outcome']} hasUser={r['hasUserInfo']} tabs={r['tabsCount']} req={r['req_seen']} resp={r['resp_seen']} total={r['total']} beforeVal='{r['before']['inputValue']}' afterFill='{r['after_fill']['inputValue']}' vue={r['after_fill']['vueQuery']} btnDis={r['after_fill']['btnDisabled']}", flush=True)
            results.append(r)
            time.sleep(GAP_S)
    # also test B and E 5 each for completeness
    for method in ["B","E"]:
        print(f"\n===== METHOD {method} 5 attempts =====", flush=True)
        for i in range(5):
            u = ["kolbarama","israel_bidur"][i%2]
            print(f"  {method} {i+1}/5 @{u}", flush=True)
            r = probe_one_method(u, method)
            print(f"    -> {r['outcome']} req={r['req_seen']} resp={r['resp_seen']}", flush=True)
            results.append(r)
            time.sleep(GAP_S)

    out = OUTPUT_DIR / "probe_search_handler_comparison_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)
    from collections import Counter
    for method in ["A","B","C","D","E"]:
        sub = [r for r in results if r["method"]==method]
        if not sub: continue
        cnt = Counter(r["outcome"] for r in sub)
        print(f"\nMethod {method} ({len(sub)}): {dict(cnt)}", flush=True)
        # Type A rate
        type_a = sum(1 for r in sub if r["outcome"]=="TAB_TIMEOUT_TYPE_A")
        print(f"  Type A: {type_a}/{len(sub)} ({type_a/len(sub)*100:.1f}%)", flush=True)

if __name__=="__main__":
    main()
