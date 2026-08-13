import asyncio
import json
import os
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
OUT = Path("debug_fastdl_cdp")
OUT.mkdir(exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1500, "height": 1200}, locale="en-US")
        page = await context.new_page()

        network_events = []
        stories_request = None
        request_body_cache = {}

        # Install runtime hooks for fetch/XHR and WebCrypto before the page does work.
        await page.add_init_script("""
        (() => {
            const wrap = (name, fn) => function (...args) {
              try {
                const stack = new Error().stack || '';
                console.log('HOOK_' + name, JSON.stringify({args: args.slice(0,2), stack: stack.split('\n').slice(1,5).join(' | ')}));
              } catch (e) {}
              return fn.apply(this, args);
            };
            if (window.fetch) {
              window.fetch = wrap('FETCH', window.fetch.bind(window));
            }
            const origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = wrap('XHR_OPEN', function(method, url, async, user, password) {
              return origOpen.call(this, method, url, async, user, password);
            });
            const origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = wrap('XHR_SEND', function(body) {
              try {
                if (body) {
                  const text = typeof body === 'string' ? body : (body instanceof Blob ? '[Blob]' : '[Body]');
                  console.log('HOOK_XHR_BODY', text.slice(0, 500));
                }
              } catch (e) {}
              return origSend.call(this, body);
            });
            const origPostMessage = Worker.prototype.postMessage;
            Worker.prototype.postMessage = function(...args) {
              console.log('HOOK_WORKER_POSTMESSAGE', args.length, args[0]);
              return origPostMessage.apply(this, args);
            };
            try {
              const oldSubtle = crypto.subtle;
              crypto.subtle = new Proxy(oldSubtle, {
                get(target, prop, receiver) {
                  const val = Reflect.get(target, prop, receiver);
                  if (typeof val === 'function') {
                    return function(...args) {
                      console.log('HOOK_CRYPTO', String(prop), JSON.stringify(args.slice(0,2)));
                      return val.apply(target, args);
                    };
                  }
                  return val;
                }
              });
            } catch (e) {}
        })();
        """)

        page.on("console", lambda msg: print(f"console> {msg.text}"))

        def on_request(req):
            url = req.url
            if "api-wh.fastdl.app" in url or "/api/v1/instagram/stories" in url or "fastdl.app" in url:
                network_events.append({
                    "type": "request",
                    "method": req.method,
                    "url": url,
                    "resource_type": req.resource_type,
                    "post_data": req.post_data,
                    "headers": dict(req.headers),
                    "frame": req.frame.url if req.frame else None,
                })

        def on_response(resp):
            url = resp.url
            if "api-wh.fastdl.app" in url or "/api/v1/instagram/stories" in url or "fastdl.app" in url:
                try:
                    body = resp.text()
                except Exception:
                    body = None
                network_events.append({
                    "type": "response",
                    "status": resp.status,
                    "url": url,
                    "content_type": resp.headers.get("content-type"),
                    "text_preview": body[:1000] if isinstance(body, str) else None,
                })

        page.on("request", on_request)
        page.on("response", on_response)

        cdp = await context.new_cdp_session(page)
        await cdp.send("Network.enable", {"maxTotalBufferSize": 10000000, "maxResourceBufferSize": 10000000})

        def request_will_be_sent(event):
            nonlocal stories_request
            req = event["params"]["request"]
            url = req["url"]
            if "/api/v1/instagram/stories" in url:
                story = {
                    "url": url,
                    "method": req.get("method"),
                    "headers": req.get("headers"),
                    "post_data": req.get("postData"),
                    "initiator": event["params"].get("initiator"),
                    "redirect_chain": event["params"].get("redirectResponse")
                }
                print("STORIES_REQUEST_EVENT", json.dumps(story, ensure_ascii=False, default=str)[:4000])
                stories_request = story
                request_body_cache[url] = req.get("postData")

        cdp.on("Network.requestWillBeSent", request_will_be_sent)

        await page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        await page.wait_for_timeout(3000)

        await page.fill("#search-form-input", "israel_bidur")
        await page.click("#searchFormButton", force=True)
        await page.wait_for_timeout(8000)

        # second username in same session
        await page.fill("#search-form-input", "instagram")
        await page.click("#searchFormButton", force=True)
        await page.wait_for_timeout(8000)

        base = OUT / "cdp_capture.json"
        base.write_text(json.dumps({"network_events": network_events, "stories_request": stories_request}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("CAPTURE_WRITTEN", str(base))

        await browser.close()

asyncio.run(main())
