#!/usr/bin/env python3
"""
חקירה בלבד - עומק TAB_TIMEOUT
- ללא שינוי production
- timeline מלא עד 30s עם network, DOM, console, errors
- recovery A vs B ומה השתנה
"""
import time, json, sys
from pathlib import Path
from datetime import datetime, timezone
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_API_PATH = "/api/v1/instagram/userInfo"
POSTS_API_PATH = "/api/v1/instagram/postsV2"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUTPUT_DIR = Path(__file__).resolve().parent
USERS = ["kolbarama", "mizrahitpage", "glglz", "israel_bidur", "erevtov", "natgeo"]


def poll_dom(page):
    return page.evaluate("""()=>{
        const tabs = Array.from(document.querySelectorAll('button.tabs-component__button'));
        const tabInfos = tabs.map(b=>{
            const rect = b.getBoundingClientRect();
            const style = window.getComputedStyle(b);
            const visible = !!(b.offsetParent !== null && rect.width>0 && rect.height>0 && style.visibility!=='hidden' && style.display!=='none' && style.opacity!=='0');
            return {
                text: (b.innerText||'').trim().slice(0,40),
                className: b.className.slice(0,80),
                visible: visible,
                rect: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                active: b.className.includes('active') || b.getAttribute('aria-selected')==='true'
            };
        });
        const allButtons = Array.from(document.querySelectorAll('button')).map(b=> (b.innerText||'').trim()).filter(t=>t && t.length<40).slice(0,15);
        const loaders = document.querySelectorAll('.loader, .spinner, .loading, [class*="spin"], [class*="load"], .skeleton, [class*="skeleton"]').length;
        const overlays = Array.from(document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .overlay, .modal, [role=dialog]')).map(e=> e.className.slice(0,60)).slice(0,5);
        const hasUserInfo = !!document.querySelector('.user-info, [class*="user-info"]');
        const hasProfile = !!document.querySelector('[class*="profile"], .profile-media');
        const readyState = document.readyState;
        const url = location.href;
        const bodyText = (document.body.innerText||'').slice(0,400).replace(/\\n/g,' | ');
        return {
            tabs: tabInfos,
            tabsCount: tabs.length,
            allButtons: allButtons,
            loaders: loaders,
            overlays: overlays,
            hasUserInfo: hasUserInfo,
            hasProfile: hasProfile,
            readyState: readyState,
            url: url,
            bodySnippet: bodyText
        };
    }""")

def probe_one(username, seq):
    t0 = time.time()
    def rel(): return round((time.time()-t0)*1000)
    timeline = []
    requests = []
    responses = []
    failed = []
    console_msgs = []
    page_errors = []
    url_changes = []

    def log(event, **kw):
        timeline.append({"t": rel(), "event": event, **kw})

    result = {
        "seq": seq,
        "username": username,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "timeline": timeline,
        "requests": requests,
        "responses": responses,
        "failed": failed,
        "console": console_msgs,
        "page_errors": page_errors,
        "url_changes": url_changes,
        "outcome": None,
        "dom_final": None,
        "recovery_A": None,
        "recovery_B": None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page = ctx.new_page()
        page.set_default_timeout(10000)

        # listeners
        def on_req(r):
            url = r.url
            if "fastdl.app" in url or "api-wh.fastdl.app" in url:
                requests.append({"t": rel(), "method": r.method, "url": url[:120], "resourceType": r.resource_type})
                # also check for key apis
                if USER_API_PATH in url or POSTS_API_PATH in url or STORIES_API_PATH in url:
                    log("request", method=r.method, url=url[:120], resourceType=r.resource_type)
        def on_resp(r):
            url = r.url
            if "fastdl.app" in url or "api-wh.fastdl.app" in url:
                responses.append({"t": rel(), "status": r.status, "url": url[:120], "ct": r.headers.get("content-type","")[:40]})
                if USER_API_PATH in url or POSTS_API_PATH in url or STORIES_API_PATH in url:
                    log("response", status=r.status, url=url[:120])
        def on_fail(r):
            url = r.url
            if "fastdl.app" in url or "api-wh.fastdl.app" in url:
                failed.append({"t": rel(), "method": r.method, "url": url[:120], "failure": str(r.failure)})
                log("requestfailed", method=r.method, url=url[:120], failure=str(r.failure))
        def on_console(msg):
            console_msgs.append({"t": rel(), "type": msg.type, "text": msg.text[:300]})
            if msg.type in ["error","warning"]:
                log("console", type=msg.type, text=msg.text[:200])
        def on_page_error(err):
            page_errors.append({"t": rel(), "msg": str(err)[:400]})
            log("page_error", msg=str(err)[:200])
        def on_frame(frame):
            try:
                url_changes.append({"t": rel(), "url": frame.url[:120], "is_main": frame==page.main_frame})
                log("frame_navigated", url=frame.url[:80])
            except: pass

        page.on("request", on_req)
        page.on("response", on_resp)
        page.on("requestfailed", on_fail)
        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("framenavigated", on_frame)

        try:
            log("goto_start", url=VIEWER_URL)
            page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=10000)
            log("goto_done", url=page.url[:120], readyState=page.evaluate("()=>document.readyState"))
            page.wait_for_selector("#search-form-input", state="visible", timeout=10000)
            log("search_ready", readyState=page.evaluate("()=>document.readyState"))
            # initial DOM
            dom0 = poll_dom(page)
            log("dom_initial", **{k: dom0[k] for k in ["tabsCount","hasUserInfo","readyState","url"]})

            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            page.fill("#search-form-input", username)
            log("fill_done")
            page.click("#searchFormButton", force=True, timeout=10000)
            log("search_click_done", url=page.url[:120])
            time.sleep(2.5)
            log("post_sleep", readyState=page.evaluate("()=>document.readyState"), url=page.url[:120])
            page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
            # poll for tabs up to 30s with detailed DOM every 500ms
            tabs_start = time.time()
            tabs_found = False
            tabs_visible = False
            last_dom = None
            # also track network idle: count requests in last 5s
            while time.time() - tabs_start < 30:
                dom = poll_dom(page)
                last_dom = dom
                # log every 2s or when change
                if int((time.time()-tabs_start)*2) % 4 == 0: # every 2s
                    log("dom_poll", tabsCount=dom["tabsCount"], tabs=[t["text"] for t in dom["tabs"]], hasUserInfo=dom["hasUserInfo"], loaders=dom["loaders"], overlays=len(dom["overlays"]), readyState=dom["readyState"])
                # check if tabs visible
                visible_tabs = [t for t in dom["tabs"] if t["visible"]]
                if visible_tabs:
                    tabs_found = True
                    # need at least one visible tab that is stories? Actually any tab visible means wait would succeed
                    # But we wait for any button.tabs-component__button visible, not specifically stories
                    tabs_visible = True
                    log("tabs_visible", tabs=[t["text"] for t in visible_tabs], count=len(visible_tabs))
                    break
                # also check if network idle: no new requests in last 3s and no loaders
                time.sleep(0.5)
            if not tabs_visible:
                # timeout
                dom_final = poll_dom(page)
                result["dom_final"] = dom_final
                log("TAB_TIMEOUT", tabsCount=dom_final["tabsCount"], hasUserInfo=dom_final["hasUserInfo"], loaders=dom_final["loaders"], readyState=dom_final["readyState"], url=dom_final["url"][:120])
                result["outcome"] = "TAB_TIMEOUT"
                # capture timeline for analysis: check network activity in last 30s
                # check if requests for userInfo/posts arrived
                user_req = [r for r in requests if USER_API_PATH in r["url"]]
                user_resp = [r for r in responses if USER_API_PATH in r["url"]]
                posts_req = [r for r in requests if POSTS_API_PATH in r["url"]]
                posts_resp = [r for r in responses if POSTS_API_PATH in r["url"]]
                result["analysis"] = {
                    "userInfo_req": len(user_req),
                    "userInfo_resp": len(user_resp),
                    "posts_req": len(posts_req),
                    "posts_resp": len(posts_resp),
                    "total_req": len(requests),
                    "total_resp": len(responses),
                    "failed": len(failed),
                    "console_errors": len([c for c in console_msgs if c["type"]=="error"]),
                    "page_errors": len(page_errors),
                    "hasUserInfo": dom_final["hasUserInfo"],
                    "tabsCount": dom_final["tabsCount"],
                    "tabs": dom_final["tabs"],
                    "loaders": dom_final["loaders"],
                    "url": dom_final["url"][:120],
                    "readyState": dom_final["readyState"],
                }
                # Recovery A: same page/context - wait 3s, clean overlay, try wait again 10s (not 30 to save time)
                log("recovery_A_start", strategy="SAME_PAGE")
                time.sleep(3)
                page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
                try:
                    page.wait_for_selector("button.tabs-component__button", state="visible", timeout=10000)
                    dom_a = poll_dom(page)
                    result["recovery_A"] = {"status": "SUCCESS", "dom": dom_a, "requests": len([r for r in requests if r["t"]> (time.time()-t0)*1000 - 10000]), "responses": len([r for r in responses if r["t"]> (time.time()-t0)*1000 - 10000])}
                    log("recovery_A_success", tabsCount=dom_a["tabsCount"])
                except Exception as e:
                    dom_a = poll_dom(page)
                    result["recovery_A"] = {"status": f"TAB_TIMEOUT_A:{e}"[:200], "dom": dom_a}
                    log("recovery_A_fail", tabsCount=dom_a["tabsCount"])

                # Recovery B: new page/context same browser
                log("recovery_B_start", strategy="NEW_CONTEXT")
                try:
                    ctx.close()
                except: pass
                # new context
                ctx2 = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
                page2 = ctx2.new_page()
                page2.set_default_timeout(10000)
                # attach listeners for B
                b_reqs = []
                b_resps = []
                b_fails = []
                def on_req_b(r):
                    if "fastdl.app" in r.url or "api-wh.fastdl.app" in r.url:
                        b_reqs.append({"t": round((time.time()-t0)*1000), "method": r.method, "url": r.url[:120]})
                def on_resp_b(r):
                    if "fastdl.app" in r.url or "api-wh.fastdl.app" in r.url:
                        b_resps.append({"t": round((time.time()-t0)*1000), "status": r.status, "url": r.url[:120]})
                def on_fail_b(r):
                    if "fastdl.app" in r.url or "api-wh.fastdl.app" in r.url:
                        b_fails.append({"t": round((time.time()-t0)*1000), "failure": str(r.failure), "url": r.url[:120]})
                page2.on("request", on_req_b)
                page2.on("response", on_resp_b)
                page2.on("requestfailed", on_fail_b)
                try:
                    page2.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=10000)
                    page2.wait_for_selector("#search-form-input", state="visible", timeout=10000)
                    page2.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
                    page2.fill("#search-form-input", username)
                    page2.click("#searchFormButton", force=True, timeout=10000)
                    time.sleep(2.5)
                    page2.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
                    page2.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
                    dom_b = page2.evaluate("""()=>{
                        const tabs = Array.from(document.querySelectorAll('button.tabs-component__button')).map(b=>b.innerText.trim());
                        return {tabs, count: tabs.length, url: location.href, readyState: document.readyState};
                    }""")
                    result["recovery_B"] = {"status": "SUCCESS", "dom": dom_b, "b_reqs": b_reqs[-5:], "b_resps": b_resps[-5:], "b_fails": b_fails}
                    log("recovery_B_success", tabs=dom_b["tabs"])
                except Exception as e:
                    try:
                        dom_b = page2.evaluate("""()=>{
                            const tabs = Array.from(document.querySelectorAll('button.tabs-component__button')).map(b=>b.innerText.trim());
                            return {tabs, count: tabs.length, url: location.href, readyState: document.readyState};
                        }""")
                    except:
                        dom_b = {"tabs": [], "count": 0}
                    result["recovery_B"] = {"status": f"TAB_TIMEOUT_B:{e}"[:300], "dom": dom_b, "b_reqs": b_reqs[-5:], "b_resps": b_resps[-5:], "b_fails": b_fails}
                    log("recovery_B_fail", tabs=dom_b.get("tabs"), b_reqs=len(b_reqs), b_resps=len(b_resps))
                try:
                    ctx2.close()
                except: pass
            else:
                # tabs visible -> success path, check stories
                dom_final = poll_dom(page)
                result["dom_final"] = dom_final
                # Now try Stories click to confirm, but outcome is SUCCESS for tabs
                # For this probe, TAB_TIMEOUT is only failure, so success means tabs visible
                # Check if stories would work
                result["outcome"] = "TAB_SUCCESS"
                # Try stories click quickly
                try:
                    with page.expect_response(lambda r: STORIES_API_PATH in r.url and r.request.method=="POST", timeout=10000) as info:
                        page.evaluate("""()=>{
                            const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));
                            for(const b of bs){ if(b.innerText.toLowerCase().includes('stories')){ b.scrollIntoView(); b.click(); return true; } }
                            return false;
                        }""")
                    resp = info.value
                    result["stories_status"] = f"STORIES_{resp.status}"
                    try:
                        body = resp.json()
                        from pathlib import Path as _P
                        import sys as _sys
                        _sys.path.insert(0, str(_P(__file__).resolve().parents[3]))
                        from src.fastdl_api import FastDLStoriesAPI
                        items = FastDLStoriesAPI.parse_stories(body)
                        result["stories_items"] = len(items) if items else 0
                    except:
                        result["stories_items"] = None
                except Exception as e:
                    result["stories_status"] = f"STORIES_TIMEOUT:{e}"[:200]

        except Exception as e:
            result["outcome"] = f"EXC:{e}"[:300]
            log("exc", msg=str(e)[:200])
        finally:
            try: browser.close()
            except: pass

    result["total_ms"] = round((time.time()-t0)*1000)
    return result

def main():
    target = 16  # aim for 16 to get ~8 TAB_TIMEOUT with 50% rate, gap 3s
    results = []
    for i in range(target):
        u = USERS[i % len(USERS)]
        print(f"\n=== Probe {i+1}/{target} @{u} ===", flush=True)
        r = probe_one(u, i+1)
        print(f"  outcome={r['outcome']} dom_tabs={r.get('dom_final',{}).get('tabsCount') if r.get('dom_final') else 'N/A'} hasUserInfo={r.get('dom_final',{}).get('hasUserInfo') if r.get('dom_final') else 'N/A'} req={len(r['requests'])} resp={len(r['responses'])} failed={len(r['failed'])} total={r['total_ms']}ms", flush=True)
        if r["outcome"]=="TAB_TIMEOUT":
            print(f"    analysis: userInfo {r['analysis']['userInfo_req']}/{r['analysis']['userInfo_resp']} posts {r['analysis']['posts_req']}/{r['analysis']['posts_resp']} failed={r['analysis']['failed']} console_err={r['analysis']['console_errors']} loaders={r['analysis']['loaders']}", flush=True)
            if r.get("recovery_A"):
                print(f"    A: {r['recovery_A']['status']}", flush=True)
            if r.get("recovery_B"):
                print(f"    B: {r['recovery_B']['status']} tabs={r['recovery_B'].get('dom',{}).get('tabs')}", flush=True)
        else:
            print(f"    stories: {r.get('stories_status')} items={r.get('stories_items')}", flush=True)
        results.append(r)
        if i < target-1:
            time.sleep(3)

    out = OUTPUT_DIR / "probe_tab_timeout_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)

    # summary
    from collections import Counter
    cnt = Counter(r["outcome"] for r in results)
    print("\n=== OUTCOME ===", flush=True)
    for k,v in cnt.items():
        print(f"  {k}: {v}/{len(results)}", flush=True)

    tab_cases = [r for r in results if r["outcome"]=="TAB_TIMEOUT"]
    print(f"\nTAB_TIMEOUT detailed {len(tab_cases)} cases:", flush=True)
    for r in tab_cases:
        print(f"  {r['seq']} @{r['username']}: hasUserInfo={r['dom_final']['hasUserInfo']} tabs={r['dom_final']['tabsCount']} loaders={r['dom_final']['loaders']} url={r['dom_final']['url'][:80]} total={r['total_ms']} userInfo {r['analysis']['userInfo_req']}/{r['analysis']['userInfo_resp']} posts {r['analysis']['posts_req']}/{r['analysis']['posts_resp']} failed={len(r['failed'])} console={len([c for c in r['console'] if c['type']=='error'])}", flush=True)

    # Recovery success
    if tab_cases:
        a_succ = sum(1 for r in tab_cases if r.get("recovery_A") and "SUCCESS" in r["recovery_A"]["status"])
        b_succ = sum(1 for r in tab_cases if r.get("recovery_B") and "SUCCESS" in r["recovery_B"]["status"])
        print(f"\nRecovery A (same page): {a_succ}/{len(tab_cases)}", flush=True)
        print(f"Recovery B (new context): {b_succ}/{len(tab_cases)}", flush=True)

if __name__ == "__main__":
    main()
