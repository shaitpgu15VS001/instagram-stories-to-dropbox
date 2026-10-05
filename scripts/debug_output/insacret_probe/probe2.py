import json, time, pathlib, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from playwright.sync_api import sync_playwright
OUT = pathlib.Path(__file__).parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
net=[]
console=[]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
    ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":900}, locale="en-US")
    page = ctx.new_page()
    def on_req(req):
        try: net.append({"type":"request","method":req.method,"url":req.url,"postData":req.post_data})
        except: pass
    def on_resp(resp):
        try:
            entry={"type":"response","method":resp.request.method,"url":resp.url,"status":resp.status,"headers":dict(resp.headers)}
            if "snapfire" in resp.url or "turnstile" in resp.url:
                try: entry["body"]=resp.text()[:5000]
                except: pass
            net.append(entry)
        except: pass
    page.on("request", on_req)
    page.on("response", on_resp)
    page.on("console", lambda m: console.append(f"{m.type}:{m.text[:800]}"))
    print("goto insacret")
    page.goto("https://insacret.org/en/stories/israel_bidur", wait_until="domcontentloaded", timeout=30000)
    print("goto done")
    for i in range(6):
        time.sleep(5)
        print(f"wait {i*5}s")
        try:
            has_turnstile = page.evaluate("() => !!window.turnstile")
            print(f" turnstile={has_turnstile}")
            snap_reqs = [e for e in net if "snapfire" in e.get("url","")]
            print(f" snapfire reqs: {len(snap_reqs)}")
            for sr in snap_reqs[-3:]:
                print("  ", sr.get("method"), sr.get("url")[:200], sr.get("status",""))
            story_len = page.evaluate("() => document.documentElement.outerHTML.length")
            print(f" html len {story_len}")
        except Exception as e:
            print(" eval error",e)
    html = page.content()
    pathlib.Path(OUT / "turnstile_final2.html").write_text(html, encoding="utf-8")
    print("saved html len", len(html))
    pathlib.Path(OUT / "turnstile_network2.json").write_text(json.dumps(net, ensure_ascii=False, indent=2), encoding="utf-8")
    pathlib.Path(OUT / "turnstile_console2.json").write_text(json.dumps(console, ensure_ascii=False, indent=2), encoding="utf-8")
    browser.close()
    print("done")
