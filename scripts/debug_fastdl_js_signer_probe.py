import asyncio
import json
import os
from collections import defaultdict
from urllib.parse import urlparse

from playwright.async_api import async_playwright

URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
OUTDIR = os.path.join(os.getcwd(), "debug_fastdl_js_probe")
os.makedirs(OUTDIR, exist_ok=True)

async def main():
    script_urls = []
    scripts_by_host = defaultdict(int)
    script_bodies = {}
    request_log = []
    got_form = False

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1800}, java_script_enabled=True)
        page = await context.new_page()

        def capture_request(req):
            if req.resource_type == "script":
                script_urls.append(req.url)
                host = urlparse(req.url).netloc or "unknown"
                scripts_by_host[host] += 1
                request_log.append({
                    "method": req.method,
                    "url": req.url,
                    "resource_type": req.resource_type,
                    "frame": req.frame.url if req.frame else None,
                })

        def capture_console(msg):
            if any(token in msg.text.lower() for token in ["hook_fetch", "hook_xhr", "story", "api-wh", "_s", "_ts"]):
                print(f"CONSOLE: {msg.text}")

        page.on("request", capture_request)
        page.on("console", capture_console)

        async def capture_script_response(resp):
            if resp.request.resource_type == "script":
                url = resp.url
                try:
                    body = await resp.text()
                except Exception:
                    body = ""
                if not body:
                    return
                if any(token in url.lower() for token in ["fastdl.app", "cdn", "jsdelivr", "unpkg", "api-wh", "google-analytics", "gtag", "webpack", "chunk"]):
                    if any(token in body.lower() for token in ["api-wh.fastdl.app", "/api/v1/instagram/stories", "_s", "_ts", "_tsc", "_sv", "username", "fetch(", "xmlhttprequest", "axios"]):
                        script_bodies[url] = body[:12000]
                        print(f"SCRIPT_MATCH: {url}")
                        snippet = body[:700].replace("\n", " ")
                        print(snippet)
                        print("---END_SNIPPET---")

        page.on("response", capture_script_response)

        await page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(7000)

        print("PAGE_TITLE:", await page.title())
        print("PAGE_URL:", page.url)
        print("SCRIPT_TOTAL:", len(script_urls))
        for idx, u in enumerate(script_urls, 1):
            print(f"{idx}. {u}")
        print("SCRIPT_HOSTS:")
        for host, count in sorted(scripts_by_host.items()):
            print(f"  {host}: {count}")

        try:
            inputs = await page.locator("input").all()
            print("INPUT_COUNT:", len(inputs))
            for i, el in enumerate(inputs[:20]):
                attrs = await el.evaluate("(node) => ({name: node.name, type: node.type, placeholder: node.placeholder, id: node.id, value: node.value, className: node.className, ariaLabel: node.getAttribute('aria-label')})")
                print(f"INPUT {i}: {attrs}")
        except Exception as e:
            print("INPUT_SCAN_ERR:", repr(e))

        try:
            html = await page.content()
            if "instagram" in html.lower() and "search" in html.lower():
                got_form = True
            print("HTML_HAS_SEARCH_TEXT:", got_form)
        except Exception as e:
            print("HTML_ERR:", repr(e))

        with open(os.path.join(OUTDIR, "script_urls.json"), "w", encoding="utf-8") as f:
            json.dump({"script_urls": script_urls, "script_hosts": dict(scripts_by_host), "request_log": request_log}, f, ensure_ascii=False, indent=2)

        with open(os.path.join(OUTDIR, "script_matches.json"), "w", encoding="utf-8") as f:
            json.dump({k: v[:8000] for k, v in script_bodies.items()}, f, ensure_ascii=False, indent=2)

        print("FILES_WRITTEN:", os.path.join(OUTDIR, "script_urls.json"), os.path.join(OUTDIR, "script_matches.json"))

        await browser.close()

asyncio.run(main())
