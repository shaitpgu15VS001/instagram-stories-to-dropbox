#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Viewsocials deep probe - captures network, cookies, storage, JS analysis
Temporary debug script - isolated under scripts/debug_output/viewsocials_probe/
"""
import json
import time
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT_DIR = Path(__file__).parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def redact(s, max_len=2000):
    if s is None:
        return None
    s = str(s)
    # redact cookies tokens
    for pat in [r'cf_clearance=[^\s;]+', r'__cf_bm=[^\s;]+', r'cf_chl_[^\s=]+=[^\s;]+']:
        s = re.sub(pat, '[REDACTED_CF]', s)
    if len(s) > max_len:
        return s[:max_len] + f"...[truncated {len(s)-max_len} chars]"
    return s

def capture_page(page, label):
    """helper to dump cookies, storage, headers"""
    data = {}
    try:
        data["url"] = page.url
        data["title"] = page.title()
        data["cookies"] = page.context.cookies()
        # redact sensitive cookie values
        for c in data["cookies"]:
            if "cf" in c["name"].lower() or "sess" in c["name"].lower():
                c["value"] = "[REDACTED]"
        try:
            data["localStorage"] = page.evaluate("() => JSON.stringify({...localStorage})")
        except: data["localStorage"] = "error"
        try:
            data["sessionStorage"] = page.evaluate("() => JSON.stringify({...sessionStorage})")
        except: data["sessionStorage"] = "error"
        try:
            data["html_snippet"] = page.content()[:15000]
        except: data["html_snippet"] = ""
        try:
            data["js_urls"] = page.evaluate("""() => Array.from(document.querySelectorAll('script[src]')).map(s=>s.src).slice(0,50)""")
        except: data["js_urls"] = []
        try:
            data["inline_js_snippet"] = page.evaluate("""() => Array.from(document.querySelectorAll('script:not([src])')).map(s=>s.textContent.slice(0,3000)).join('\\n---\\n').slice(0,10000)""")
        except: data["inline_js_snippet"] = ""
        # check for interesting window globals
        try:
            data["window_keys"] = page.evaluate("() => Object.keys(window).filter(k=>/token|api|stories|profile|instagram|media|fetch|axios/i.test(k)).slice(0,50)")
        except: data["window_keys"] = []
    except Exception as e:
        data["capture_error"] = str(e)
    # save
    (OUT_DIR / f"{label}_page_dump.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data

def run_probe(url, label, action_fn=None):
    print(f"\n=== PROBE {label} : {url} ===")
    network_log = []
    requests_failed = []
    console_msgs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width":1280,"height":900}, locale="en-US")
        page = context.new_page()
        page.set_default_timeout(30000)

        def on_request(req):
            try:
                entry = {"type":"request", "method":req.method, "url":req.url, "headers": dict(req.headers), "postData": req.post_data}
                # redact
                if entry["headers"].get("cookie"):
                    entry["headers"]["cookie"] = "[REDACTED]"
                network_log.append(entry)
            except: pass
        def on_response(resp):
            try:
                entry = {"type":"response", "method":resp.request.method, "url":resp.url, "status":resp.status, "headers": dict(resp.headers), "requestHeaders": dict(resp.request.headers)}
                if entry["headers"].get("set-cookie"):
                    entry["headers"]["set-cookie"] = "[REDACTED]"
                if entry["requestHeaders"].get("cookie"):
                    entry["requestHeaders"]["cookie"] = "[REDACTED]"
                # try to capture body for interesting endpoints
                interesting = any(x in resp.url for x in ["/api", "/ajax", "/graphql", "viewsocials", "storynavigation", "instagram", "cdninstagram", "fbcdn"])
                body_snippet = None
                if interesting and resp.headers.get("content-type","").lower().find("json")!=-1:
                    try:
                        body = resp.text()
                        body_snippet = body[:5000]
                    except: body_snippet = "[body-read-error]"
                    entry["body_snippet"] = body_snippet
                # for image/video urls also capture?
                network_log.append(entry)
            except: pass
        def on_failed(req):
            try:
                requests_failed.append({"url":req.url, "method":req.method, "failure":req.failure})
            except: pass
        def on_console(msg):
            console_msgs.append(f"{msg.type}: {msg.text[:500]}")

        page.on("request", on_request)
        page.on("response", on_response)
        page.on("requestfailed", on_failed)
        page.on("console", on_console)

        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            print(f"  goto status: {resp.status if resp else 'no resp'} url: {page.url}")
            time.sleep(3)
            capture_page(page, f"{label}_initial")

            # dump all script contents via evaluate for token search
            try:
                scripts_content = page.evaluate("""() => {
                    const urls = Array.from(document.querySelectorAll('script[src]')).map(s=>s.src);
                    return {urls, inlineCount: document.querySelectorAll('script:not([src])').length, html: document.documentElement.outerHTML.slice(0,20000)};
                }""")
                (OUT_DIR / f"{label}_scripts_meta.json").write_text(json.dumps(scripts_content, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"scripts meta error {e}")

            if action_fn:
                print(f"  running action_fn for {label}")
                action_fn(page, context)

                time.sleep(4)
                capture_page(page, f"{label}_after_action")
                # after action wait for network idle-ish
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except: pass
                time.sleep(2)

            # final capture
            # check for stories DOM elements
            try:
                stories_dom = page.evaluate("""() => {
                    const els = Array.from(document.querySelectorAll('*'));
                    const storyCandidates = els.filter(e=>e.className && typeof e.className==='string' && /story/i.test(e.className)).slice(0,20).map(e=>({tag:e.tagName, cls:e.className, txt:e.innerText?.slice(0,200), html:e.outerHTML.slice(0,800)}));
                    const imgs = Array.from(document.querySelectorAll('img')).slice(0,20).map(i=>({src:i.src, alt:i.alt?.slice(0,100)}));
                    const vids = Array.from(document.querySelectorAll('video, [src*=".mp4"]')).slice(0,20).map(v=>({src:v.src || v.getAttribute('src'), html:v.outerHTML.slice(0,800)}));
                    const links = Array.from(document.querySelectorAll('a')).slice(0,30).map(a=>({href:a.href, text:a.innerText?.slice(0,100)}));
                    return {storyCandidates, imgs, vids, links, bodyText: document.body.innerText.slice(0,5000)};
                }""")
                (OUT_DIR / f"{label}_dom_analysis.json").write_text(json.dumps(stories_dom, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as e:
                print(f"dom analysis error {e}")

        except Exception as e:
            print(f"  probe error: {e}")
            import traceback; traceback.print_exc()
        finally:
            # save logs
            (OUT_DIR / f"{label}_network.json").write_text(json.dumps(network_log, ensure_ascii=False, indent=2), encoding="utf-8")
            (OUT_DIR / f"{label}_failed.json").write_text(json.dumps(requests_failed, ensure_ascii=False, indent=2), encoding="utf-8")
            (OUT_DIR / f"{label}_console.json").write_text(json.dumps(console_msgs, ensure_ascii=False, indent=2), encoding="utf-8")
            # also save full page content
            try:
                (OUT_DIR / f"{label}_final.html").write_text(page.content(), encoding="utf-8")
            except: pass
            try:
                cookies = context.cookies()
                for c in cookies:
                    if "cf" in c["name"].lower():
                        c["value"] = "[REDACTED]"
                (OUT_DIR / f"{label}_cookies.json").write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
            except: pass
            browser.close()
    print(f"  done {label}, network entries: {len(network_log)}")
    return network_log

# Action for storynavigation watch-stories
def action_storynavigation(page, context):
    try:
        # find input field
        # the page likely has search input
        print("  searching for input...")
        # dump page HTML snippet
        html = page.content()
        # find all inputs
        inputs = page.evaluate("""() => Array.from(document.querySelectorAll('input')).map(i=>({type:i.type, id:i.id, name:i.name, placeholder:i.placeholder, className:i.className, outer:i.outerHTML.slice(0,500)}))""")
        print(f"  inputs found: {json.dumps(inputs, ensure_ascii=False)[:1000]}")
        # try common selectors
        selectors = ["input[placeholder*='nickname']", "input[placeholder*='username']", "input[type='text']", "input[type='search']", "#search", ".search-input", "input"]
        found = False
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    print(f"  found visible input with sel {sel}")
                    el.fill("israel_bidur")
                    found = True
                    break
            except: pass
        if not found:
            print("  no visible input found via selectors, trying evaluate")
            page.evaluate("""() => {
                const inp = document.querySelector('input');
                if(inp){ inp.value='israel_bidur'; inp.dispatchEvent(new Event('input',{bubbles:true})); inp.dispatchEvent(new Event('change',{bubbles:true})); }
            }""")
        time.sleep(1)
        # find button
        buttons = page.evaluate("""() => Array.from(document.querySelectorAll('button, a.btn, [role=button]')).map(b=>({txt:b.innerText?.slice(0,100), cls:b.className, id:b.id, href:b.href || '', outer:b.outerHTML.slice(0,600)}))""")
        (OUT_DIR / "storynavigation_buttons.json").write_text(json.dumps(buttons, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  buttons: {json.dumps(buttons, ensure_ascii=False)[:2000]}")
        # try to click submit/search
        clicked = page.evaluate("""() => {
            const btns = Array.from(document.querySelectorAll('button'));
            for(const b of btns){
                if(/search|view|watch|find|go/i.test(b.innerText)){
                    b.click(); return b.innerText;
                }
            }
            const form = document.querySelector('form');
            if(form){ form.submit(); return 'form.submit'; }
            return null;
        }""")
        print(f"  clicked: {clicked}")
        time.sleep(3)
        print(f"  after click url: {page.url}")
        # Check for redirect chain: maybe navigated to viewsocials
        # also check if any fetch was made
    except Exception as e:
        print(f"  action error {e}")
        import traceback; traceback.print_exc()

def action_viewsocials(page, context):
    try:
        print(f"  viewsocials page url: {page.url}")
        # Check if Cloudflare challenge present
        cf = page.evaluate("""() => ({title:document.title, body:document.body.innerText.slice(0,3000), html:document.documentElement.outerHTML.slice(0,5000)})""")
        print(f"  cf check title: {cf['title']}")
        # Wait a bit for stories to load
        time.sleep(5)
        # Look for stories elements
        # try to click any story item
        clicked = page.evaluate("""() => {
            const candidates = Array.from(document.querySelectorAll('[class*="story"], [class*="Story"], [data-story], .profile-media-list__item, a[href*="story"]'));
            if(candidates.length){ candidates[0].click(); return 'clicked '+candidates[0].className; }
            const imgs = Array.from(document.querySelectorAll('img'));
            if(imgs.length>5){ return 'found '+imgs.length+' imgs, no story click'; }
            return 'no candidates, imgs '+imgs.length;
        }""")
        print(f"  stories interaction: {clicked}")
        # Search for JS that fetches stories - dump network was already captured, also search inline JS
        js_search = page.evaluate("""() => {
            const scripts = Array.from(document.querySelectorAll('script')).map(s=>s.textContent).join('\\n').slice(0,20000);
            const has = {token: /token/i.test(scripts), api: /\\/api\\//i.test(scripts), stories: /stories/i.test(scripts), fetch: /fetch\\(/i.test(scripts), axios: /axios/i.test(scripts)};
            return {has, snippet: scripts.slice(0,8000)};
        }""")
        (OUT_DIR / "viewsocials_js_search.json").write_text(json.dumps(js_search, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"  viewsocials action error {e}")
        import traceback; traceback.print_exc()

if __name__ == "__main__":
    print("Starting Viewsocials probe...")
    # Phase 1: storynavigation
    run_probe("https://storynavigation.com/watch-stories", "01_storynavigation_initial", action_storynavigation)
    time.sleep(2)
    # Phase 2: direct viewsocials
    run_probe("https://www.viewsocials.com/profile/israel_bidur", "02_viewsocials_direct", action_viewsocials)
    # Phase 3: viewsocials with alternate username check? maybe generic
    # also probe storynavigation domain api discovery via fetching JS files directly
    print("\nProbe finished. Files in", OUT_DIR)

