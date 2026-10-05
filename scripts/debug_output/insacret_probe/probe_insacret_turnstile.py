import json, time, pathlib, re
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def run():
    net=[]
    console=[]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":900}, locale="en-US")
        page = ctx.new_page()
        page.set_default_timeout(30000)
        def on_req(req):
            try:
                net.append({"type":"request","method":req.method,"url":req.url,"headers":dict(req.headers),"postData":req.post_data})
            except: pass
        def on_resp(resp):
            try:
                entry={"type":"response","method":resp.request.method,"url":resp.url,"status":resp.status,"headers":dict(resp.headers)}
                if "snapfire" in resp.url or "turnstile" in resp.url or "insacret" in resp.url:
                    try: entry["body"]=resp.text()[:5000]
                    except: pass
                net.append(entry)
            except: pass
        page.on("request", on_req)
        page.on("response", on_resp)
        page.on("console", lambda m: console.append(f"{m.type}:{m.text[:1000]}"))
        page.on("pageerror", lambda e: console.append(f"pageerror:{str(e)[:1000]}"))
        print("goto insacret")
        page.goto("https://insacret.org/en/stories/israel_bidur", wait_until="domcontentloaded", timeout=30000)
        print("goto done", page.url)
        # wait longer for turnstile
        for i in range(6):
            time.sleep(5)
            print(f"wait {i*5}s, url {page.url}, title {page.title()[:100]}")
            # try to dump some state
            try:
                has_turnstile = page.evaluate("() => !!window.turnstile")
                has_gtag = page.evaluate("() => typeof window.gtag")
                body_len = page.evaluate("() => document.documentElement.outerHTML.length")
                print(f"  turnstile={has_turnstile} gtag={has_gtag} bodyLen={body_len}")
                # check if any snapfire request appeared
                snap_reqs = [e for e in net if "snapfire" in e.get("url","")]
                print(f"  snapfire requests so far: {len(snap_reqs)}")
                if snap_reqs:
                    for sr in snap_reqs[-2:]:
                        print("   ", sr)
            except Exception as e:
                print(" eval error",e)
            # check for stories DOM
            try:
                stories = page.evaluate("() => document.querySelectorAll('[class*=\"story\"],[data-story]').length")
                print(f"  story elements: {stories}")
            except: pass
        # final dump
        try:
            html = page.content()
            pathlib.Path(OUT / "turnstile_final.html").write_text(html, encoding="utf-8")
            print("saved html len", len(html))
            # try to find any story data in html
            if "snapfire" in html.lower():
                print("snapfire in html")
            if "israel_bidur" in html:
                idx=html.find("israel_bidur")
                print(html[idx-500:idx+1000][:1500])
        except Exception as e:
            print("final html error",e)
        # save
        pathlib.Path(OUT / "turnstile_network.json").write_text(json.dumps(net, ensure_ascii=False, indent=2), encoding="utf-8")
        pathlib.Path(OUT / "turnstile_console.json").write_text(json.dumps(console, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            cookies = ctx.cookies()
            for c in cookies:
                c["value"]="[REDACTED]" if "cf" in c["name"].lower() else c["value"]
            pathlib.Path(OUT / "turnstile_cookies.json").write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
            print("cookies", cookies[:5])
        except: pass
        browser.close()
        print("done net len", len(net))
        # print snapfire details
        for e in net:
            if "snapfire" in e.get("url",""):
                print(e)

if __name__=="__main__":
    run()
