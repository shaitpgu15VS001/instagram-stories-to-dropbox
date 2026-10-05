#!/usr/bin/env python3
import json, time, re, pathlib
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).parent
OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def capture_page(page, label):
    data={}
    try:
        data["url"]=page.url
        data["title"]=page.title()
        try:
            data["cookies"]=[{**c, "value":"[REDACTED]" if "cf" in c["name"].lower() or "sess" in c["name"].lower() or "token" in c["name"].lower() else c["value"]} for c in page.context.cookies()]
        except: data["cookies"]=[]
        try: data["localStorage"]=page.evaluate("() => JSON.stringify({...localStorage})")[:5000]
        except: data["localStorage"]="error"
        try: data["sessionStorage"]=page.evaluate("() => JSON.stringify({...sessionStorage})")[:5000]
        except: data["sessionStorage"]="error"
        try: data["html_snippet"]=page.content()[:20000]
        except: data["html_snippet"]=""
        try: data["js_urls"]=page.evaluate("() => Array.from(document.querySelectorAll('script[src]')).map(s=>s.src).slice(0,50)")
        except: data["js_urls"]=[]
        try: data["window_keys"]=page.evaluate("() => Object.keys(window).filter(k=>/token|api|stories|profile|instagram|media|fetch|axios|insacret/i.test(k)).slice(0,50)")
        except: data["window_keys"]=[]
    except Exception as e:
        data["error"]=str(e)
    (OUT / f"{label}_page_dump.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

def run_probe(url, label):
    print(f"\n=== PROBE {label} : {url} ===")
    net=[]
    failed=[]
    console=[]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        ctx = browser.new_context(user_agent=UA, viewport={"width":1280,"height":900}, locale="en-US")
        page = ctx.new_page()
        page.set_default_timeout(30000)
        def on_req(req):
            try:
                entry={"type":"request","method":req.method,"url":req.url,"headers":dict(req.headers),"postData":req.post_data}
                if entry["headers"].get("cookie"): entry["headers"]["cookie"]="[REDACTED]"
                net.append(entry)
            except: pass
        def on_resp(resp):
            try:
                entry={"type":"response","method":resp.request.method,"url":resp.url,"status":resp.status,"headers":dict(resp.headers),"requestHeaders":dict(resp.request.headers)}
                if entry["headers"].get("set-cookie"): entry["headers"]["set-cookie"]="[REDACTED]"
                if entry["requestHeaders"].get("cookie"): entry["requestHeaders"]["cookie"]="[REDACTED]"
                interesting = any(x in resp.url.lower() for x in ["/api","/ajax","/graphql","insacret","story","stories","profile","media","instagram","cdn","graphql"])
                ct = resp.headers.get("content-type","").lower()
                if interesting and ("json" in ct or "javascript" in ct or "html" in ct):
                    try: entry["body_snippet"]=resp.text()[:8000]
                    except: entry["body_snippet"]="[read-error]"
                net.append(entry)
            except: pass
        def on_fail(req):
            try: failed.append({"url":req.url,"method":req.method,"failure":req.failure})
            except: pass
        page.on("request", on_req)
        page.on("response", on_resp)
        page.on("requestfailed", on_fail)
        page.on("console", lambda msg: console.append(f"{msg.type}: {msg.text[:800]}"))
        try:
            resp=page.goto(url, wait_until="domcontentloaded", timeout=30000)
            print(f" goto {resp.status if resp else 'none'} -> {page.url}")
            time.sleep(5)
            capture_page(page, f"{label}_initial")
            # wait for network idle-ish
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except: pass
            time.sleep(3)
            # DOM analysis
            try:
                dom = page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('*'));
                    const storyCandidates = els.filter(e=>e.className && typeof e.className==='string' && /story/i.test(e.className)).slice(0,30).map(e=>({tag:e.tagName, cls:e.className, txt:(e.innerText||'').slice(0,200), html:e.outerHTML.slice(0,1000)}));
                    const imgs = Array.from(document.querySelectorAll('img')).slice(0,30).map(i=>({src:i.src, alt:(i.alt||'').slice(0,100), cls:i.className}));
                    const vids = Array.from(document.querySelectorAll('video')).slice(0,20).map(v=>({src:v.src||v.currentSrc, poster:v.poster, html:v.outerHTML.slice(0,1000)}));
                    const links = Array.from(document.querySelectorAll('a')).slice(0,30).map(a=>({href:a.href, text:(a.innerText||'').slice(0,100)}));
                    const scripts = Array.from(document.querySelectorAll('script')).map(s=>s.textContent.slice(0,3000)).join('\\n---\\n').slice(0,15000);
                    const bodyText = document.body.innerText.slice(0,8000);
                    const html = document.documentElement.outerHTML.slice(0,30000);
                    return {storyCandidates, imgs, vids, links, bodyText, htmlSnippet: html.slice(0,20000), scriptsSnippet: scripts.slice(0,10000)}
                }""")
                (OUT / f"{label}_dom_analysis.json").write_text(json.dumps(dom, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                print(f" dom error {e}")
            # additional JS search
            try:
                js_search = page.evaluate("""() => {
                    const scripts = Array.from(document.querySelectorAll('script')).map(s=>s.textContent).join('\\n');
                    return {
                        hasFetch: /fetch\\(/.test(scripts),
                        hasAxios: /axios/.test(scripts),
                        hasStories: /stories/i.test(scripts),
                        hasApi: /\\/api\\//i.test(scripts),
                        hasToken: /token/i.test(scripts),
                        snippet: scripts.slice(0,12000)
                    }
                }""")
                (OUT / f"{label}_js_search.json").write_text(json.dumps(js_search, ensure_ascii=False, indent=2), encoding="utf-8")
            except: pass
            # try clicking any story
            try:
                clicked = page.evaluate("""() => {
                    const sel = document.querySelector('[class*="story"]');
                    if(sel){ sel.click(); return 'clicked '+sel.className }
                    const imgs = document.querySelectorAll('img');
                    return 'no story click, imgs='+imgs.length
                }""")
                print(f" click attempt: {clicked}")
                time.sleep(3)
            except: pass
            capture_page(page, f"{label}_final")
        except Exception as e:
            print(f" probe error {e}")
            import traceback; traceback.print_exc()
        finally:
            (OUT / f"{label}_network.json").write_text(json.dumps(net, ensure_ascii=False, indent=2), encoding="utf-8")
            (OUT / f"{label}_failed.json").write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
            (OUT / f"{label}_console.json").write_text(json.dumps(console, ensure_ascii=False, indent=2), encoding="utf-8")
            try: (OUT / f"{label}_final.html").write_text(page.content(), encoding="utf-8")
            except: pass
            try:
                cookies = ctx.cookies()
                for c in cookies:
                    if "cf" in c["name"].lower() or "token" in c["name"].lower():
                        c["value"]="[REDACTED]"
                (OUT / f"{label}_cookies.json").write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
            except: pass
            browser.close()
    print(f" done {label} net={len(net)}")
if __name__=="__main__":
    run_probe("https://insacret.org/en/stories/israel_bidur", "01_insacret")
    print("probe finished")
