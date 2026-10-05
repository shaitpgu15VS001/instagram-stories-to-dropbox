import time
from playwright.sync_api import sync_playwright
VIEWER_URL="https://fastdl.app/en2/instagram-anonymously-viewer"
STORIES_API_PATH="/api/v1/instagram/stories"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
username="kolbarama"
t0=time.perf_counter()
def rel(): return round((time.perf_counter()-t0)*1000)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
    ctx=browser.new_context(user_agent=UA, viewport={"width":1280,"height":900}, locale="en-US")
    page=ctx.new_page()
    req_t=None; resp_t=None; failed=[]
    def on_req(r):
        global req_t
        if STORIES_API_PATH in r.url and r.method=="POST":
            req_t=rel()
            print(f"REQ T+{req_t}ms {r.url[:60]} post_len={len(r.post_data) if r.post_data else 0}")
    def on_resp(r):
        global resp_t
        if STORIES_API_PATH in r.url:
            resp_t=rel()
            print(f"RESP T+{resp_t}ms status={r.status} url={r.url[:60]}")
            try:
                body=r.json()
                print(f"  body keys={list(body.keys()) if isinstance(body,dict) else type(body)}")
                if isinstance(body,dict) and "result" in body:
                    print(f"  result len={len(body['result']) if isinstance(body['result'],list) else body['result']}")
                else:
                    print(f"  body sample={str(body)[:400]}")
            except Exception as e:
                print(f"  json fail {e}")
                try:
                    print(f"  text sample={r.text()[:500]}")
                except: pass
    def on_fail(r):
        if STORIES_API_PATH in r.url:
            failed.append((rel(), str(r.failure)))
            print(f"FAILED T+{rel()}ms {r.failure}")
    page.on("request", on_req); page.on("response", on_resp); page.on("requestfailed", on_fail)
    print(f"goto T+{rel()}ms")
    page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=30000)
    print(f"goto done T+{rel()}ms url={page.url}")
    page.wait_for_selector("#search-form-input", state="visible", timeout=15000)
    print(f"input ready T+{rel()}ms")
    page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
    page.fill("#search-form-input", username)
    page.click("#searchFormButton", force=True, timeout=15000)
    print(f"search click T+{rel()}ms")
    time.sleep(2.5)
    page.evaluate("()=>{['.fc-dialog-overlay','.fc-consent-root','.overlay'].forEach(s=>document.querySelectorAll(s).forEach(e=>e.remove()))}")
    try:
        page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)
        print(f"tabs ready T+{rel()}ms")
    except Exception as e:
        print(f"tabs timeout T+{rel()}ms {e}")
        browser.close(); exit()
    clicked=page.evaluate("()=>{const bs=Array.from(document.querySelectorAll('button.tabs-component__button'));for(const b of bs){if(b.innerText.toLowerCase().includes('stories')){b.scrollIntoView();b.click();return true;}}return false;}")
    print(f"click stories={clicked} T+{rel()}ms")
    deadline=time.time()+45
    while time.time()<deadline and resp_t is None:
        time.sleep(0.5)
        print(f"  wait polling T+{rel()}ms req_t={req_t} resp_t={resp_t} failed={failed}")
    print(f"FINAL req_t={req_t} resp_t={resp_t} delta={resp_t-req_t if req_t and resp_t else 'N/A'} failed={failed}")
    browser.close()
