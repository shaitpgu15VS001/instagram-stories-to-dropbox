#!/usr/bin/env python3
"""Detailed timing probe: measure exact request->response delay with body capture."""
import json, time
from pathlib import Path
from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def redact(s):
    try:
        import json as j
        d=j.loads(s)
        for k in ("_s","_ts","_tsc","ts","_sv"):
            if k in d and isinstance(d[k],str) and len(d[k])>10:
                d[k]="<redacted>"
        return j.dumps(d)
    except: return s[:150] if s else s

usernames=["kolbarama","israel_bidur","mizrahitpage","glglz"]
for username in usernames:
    print(f"\n=== {username} ===")
    t0=time.perf_counter()
    def rel(): return round((time.perf_counter()-t0)*1000)
    state={"req_t":None,"resp_t":None,"resp_status":None,"resp_body_info":None}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx=browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page=ctx.new_page()
        def on_req(r):
            if STORIES_API_PATH in r.url and r.method=="POST":
                state["req_t"]=rel()
                print(f"  REQ T+{state['req_t']}ms POST {r.url}")
        def on_resp(r):
            if STORIES_API_PATH in r.url and r.request.method=="POST":
                state["resp_t"]=rel()
                state["resp_status"]=r.status
                try:
                    body=r.json()
                    keys=list(body.keys()) if isinstance(body,dict) else str(type(body))
                    rl=len(body.get("result")) if isinstance(body,dict) and isinstance(body.get("result"),list) else body.get("result") if isinstance(body,dict) else None
                    state["resp_body_info"]=f"keys={keys} result_len={rl}"
                    txt=r.text()
                    sample=txt[:300] if txt else ""
                except Exception as e:
                    try:
                        txt=r.text()
                        sample=txt[:400]
                    except Exception as e2:
                        sample=str(e2)
                    state["resp_body_info"]=f"json_fail {e} sample={sample[:150]}"
                print(f"  RESP T+{state['resp_t']}ms status={state['resp_status']} {state['resp_body_info']} delta={state['resp_t']-state['req_t'] if state['req_t'] else '?'}ms")
        page.on("request", on_req); page.on("response", on_resp)
        page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("#search-form-input", state="visible", timeout=15000)
        page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
        page.fill("#search-form-input", username)
        page.click("#searchFormButton", force=True, timeout=15000)
        time.sleep(2.5)
        page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
        try:
            page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
            tabs_ok=True
            print(f"  TABS OK T+{rel()}ms")
        except Exception as e:
            tabs_ok=False
            print(f"  TABS FAIL T+{rel()}ms {e}")
            browser.close(); continue
        # Now click stories and wait with expect_response like production but with 35s to see late response
        clicked=page.evaluate("()=>{const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));for(const b of bs){if(b.innerText.toLowerCase().includes('stories')){b.scrollIntoView();b.click();return true;}}return false;}")
        print(f"  CLICK stories={clicked} T+{rel()}ms")
        # wait up to 40s for response
        deadline=time.time()+40
        while time.time()<deadline and state["resp_t"] is None:
            time.sleep(0.2)
            if time.time()-t0>60:
                break
        if state["resp_t"] is None:
            print(f"  NO RESP after 40s (req_t={state['req_t']} tabs_ok={tabs_ok})")
        else:
            print(f"  FINAL delta req->resp = {state['resp_t']-state['req_t']}ms")
        browser.close()
    time.sleep(3)
