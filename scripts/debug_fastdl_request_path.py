import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
OUTDIR = Path("debug_fastdl_request_path")
OUTDIR.mkdir(exist_ok=True)

TARGET = "/api/v1/instagram/stories"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1500, "height": 1200},
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/148.0.7778.96 Safari/537.36",
        )
        page = await context.new_page()

        exact_request = {}
        script_parsed = []
        script_sources = {}
        request_events = []
        request_ids = []
        debugger_events = []

        # Build a very specific, endpoint-focused probe. We do not repeat the broad generic hooks.
        await page.add_init_script(f"""
        (() => {{
            const target = {json.dumps(TARGET)};
            const probe = (kind, payload) => {{
              const stack = (new Error().stack || '').split('\n').slice(1, 12).join(' | ');
              const rec = {{kind, ts: Date.now(), payload, stack}};
              window.__fastdl_target_probe = window.__fastdl_target_probe || [];
              window.__fastdl_target_probe.push(rec);
              console.log('FASTDL_TARGET_PROBE', JSON.stringify(rec));
            }};

            const origFetch = window.fetch ? window.fetch.bind(window) : null;
            if (origFetch) {{
              window.fetch = function(url, init) {{
                const u = String(url || '');
                if (u.includes(target)) {{
                  probe('fetch', {{ url: u, method: (init && init.method) || 'GET', body: init && init.body ? String(init.body).slice(0, 4000) : null, hasInit: !!init }});
                }}
                return origFetch(url, init);
              }};
            }}

            const origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, async, user, password) {{
              const u = String(url || '');
              if (u.includes(target)) {{
                probe('xhr_open', {{ method: String(method), url: u, async: !!async }});
                this.__fastdl_target_url = u;
              }}
              return origOpen.call(this, method, url, async, user, password);
            }};

            const origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = function(body) {{
              const u = this.__fastdl_target_url || '';
              if (u.includes(target)) {{
                const preview = typeof body === 'string' ? body.slice(0, 4000) : (body instanceof FormData ? '[FormData]' : (body instanceof URLSearchParams ? '[URLSearchParams]' : String(body || '')));
                probe('xhr_send', {{ url: u, bodyPreview: preview.slice(0, 4000) }});
              }}
              return origSend.call(this, body);
            }};

            const origFormAppend = FormData.prototype.append;
            FormData.prototype.append = function(name, value, filename) {{
              const n = String(name || '');
              if (n === 'username' || n === '_ts' || n === '_tsc' || n === '_sv' || n === '_s') {{
                probe('formdata_append', {{ name: n, valuePreview: String(value || '').slice(0, 500), filename: filename || null }});
              }}
              return origFormAppend.call(this, name, value, filename);
            }};

            const origURLAppend = URLSearchParams.prototype.append;
            URLSearchParams.prototype.append = function(name, value) {{
              const n = String(name || '');
              if (n === 'username' || n === '_ts' || n === '_tsc' || n === '_sv' || n === '_s') {{
                probe('urlsp_append', {{ name: n, valuePreview: String(value || '').slice(0, 500) }});
              }}
              return origURLAppend.call(this, name, value);
            }};
        }})();
        """)

        page.on("console", lambda msg: request_events.append({"type": "console", "text": msg.text}) if "FASTDL_TARGET_PROBE" in msg.text else None)

        cdp = await context.new_cdp_session(page)
        await cdp.send("Network.enable", {"maxTotalBufferSize": 100000000, "maxResourceBufferSize": 100000000})
        await cdp.send("Page.enable", {})
        await cdp.send("Runtime.enable", {})
        await cdp.send("Debugger.enable", {"maxScriptsCacheSize": 100000000})
        await cdp.send("Runtime.setAsyncCallStackDepth", {"maxDepth": 32})

        event_handlers = []

        def capture_request(event):
            params = event.get("params", {})
            req = params.get("request", {})
            url = req.get("url", "")
            if TARGET in url:
                request_ids.append(params.get("requestId"))
                exact_request = {
                    "requestId": params.get("requestId"),
                    "documentURL": params.get("documentURL"),
                    "frameId": params.get("frameId"),
                    "loaderId": params.get("loaderId"),
                    "timestamp": params.get("timestamp"),
                    "initiator": params.get("initiator"),
                    "request": req,
                    "redirectResponse": params.get("redirectResponse"),
                }
                request_events.append({"event": "Network.requestWillBeSent", "data": exact_request})
                print("REQUEST_WILL_BE_SENT", json.dumps(exact_request, ensure_ascii=False, default=str, indent=2))

        def capture_extra_info(event):
            params = event.get("params", {})
            req_id = params.get("requestId")
            if req_id in request_ids or TARGET in json.dumps(params, default=str):
                request_events.append({"event": "Network.requestWillBeSentExtraInfo", "data": params})
                print("REQUEST_WILL_BE_SENT_EXTRA_INFO", json.dumps(params, ensure_ascii=False, default=str, indent=2)[:20000])

        def capture_response(event):
            params = event.get("params", {})
            req = params.get("request", {})
            url = req.get("url", "")
            if TARGET in url:
                request_events.append({"event": "Network.responseReceived", "data": params})
                print("RESPONSE_RECEIVED", json.dumps(params, ensure_ascii=False, default=str, indent=2)[:20000])

        def capture_response_extra(event):
            params = event.get("params", {})
            req_id = params.get("requestId")
            if req_id in request_ids or TARGET in json.dumps(params, default=str):
                request_events.append({"event": "Network.responseReceivedExtraInfo", "data": params})
                print("RESPONSE_RECEIVED_EXTRA_INFO", json.dumps(params, ensure_ascii=False, default=str, indent=2)[:20000])

        def capture_loading_finished(event):
            params = event.get("params", {})
            req_id = params.get("requestId")
            if req_id in request_ids:
                request_events.append({"event": "Network.loadingFinished", "data": params})
                print("LOADING_FINISHED", json.dumps(params, ensure_ascii=False, default=str, indent=2)[:20000])

        cdp.on("Network.requestWillBeSent", capture_request)
        cdp.on("Network.requestWillBeSentExtraInfo", capture_extra_info)
        cdp.on("Network.responseReceived", capture_response)
        cdp.on("Network.responseReceivedExtraInfo", capture_response_extra)
        cdp.on("Network.loadingFinished", capture_loading_finished)

        def on_script_parsed(event):
            params = event.get("params", {})
            script_parsed.append({
                "scriptId": params.get("scriptId"),
                "url": params.get("url"),
                "startLine": params.get("startLine"),
                "startColumn": params.get("startColumn"),
                "endLine": params.get("endLine"),
                "executionContextId": params.get("executionContextId"),
                "hash": params.get("hash"),
                "sourceMapURL": params.get("sourceMapURL"),
            })
            if params.get("url") and ("fastdl.app" in params.get("url") or "googletagmanager" in params.get("url") or "google-analytics" in params.get("url") or "api-wh.fastdl.app" in params.get("url")):
                debugger_events.append({"event": "scriptParsed", "data": params})

        cdp.on("Debugger.scriptParsed", on_script_parsed)

        async def materialize_scripts():
            # Get the source for scripts with fastdl or google origins. Keep the exact scriptId mapping.
            for rec in script_parsed:
                sid = rec.get("scriptId")
                if not sid:
                    continue
                url = rec.get("url") or ""
                if "fastdl.app" in url or "googletagmanager" in url or "google-analytics" in url or "api-wh.fastdl.app" in url:
                    try:
                        source = await cdp.send("Debugger.getScriptSource", {"scriptId": sid})
                        script_sources[sid] = {
                            "url": url,
                            "source": source.get("scriptSource", ""),
                        }
                    except Exception as exc:
                        script_sources[sid] = {"url": url, "source_error": str(exc)}

        # Request route with direct interception, then continue
        await page.route("**/api/v1/instagram/stories**", lambda route: route.continue_())

        await page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(5000)

        try:
            search = page.locator("input, textarea")
            await search.first.fill("israel_bidur")
            button = page.locator("button:has-text('Search'), button[type='submit'], input[type='submit']").first
            await button.click(force=True)
        except Exception as exc:
            print("SEARCH_CLICK_ERROR", exc)
        await page.wait_for_timeout(15000)

        # second request to a different username to compare
        try:
            search = page.locator("input, textarea")
            await search.first.fill("instagram")
            button = page.locator("button:has-text('Search'), button[type='submit'], input[type='submit']").first
            await button.click(force=True)
        except Exception as exc:
            print("SEARCH_CLICK_ERROR_2", exc)
        await page.wait_for_timeout(10000)

        await materialize_scripts()

        # Fetch actual post data for any matched requestId.
        for req_id in request_ids:
            try:
                resp = await cdp.send("Network.getRequestPostData", {"requestId": req_id})
                exact_request.setdefault("postData", resp)
                print("GET_REQUEST_POST_DATA", json.dumps(resp, ensure_ascii=False, default=str, indent=2)[:20000])
            except Exception as exc:
                print("POST_DATA_ERROR", req_id, type(exc).__name__, exc)

        # Write outputs.
        (OUTDIR / "request_events.json").write_text(json.dumps(request_events, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (OUTDIR / "script_parsed.json").write_text(json.dumps(script_parsed, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (OUTDIR / "script_sources.json").write_text(json.dumps({k: {"url": v.get("url"), "source_len": len(v.get("source", "")), "error": v.get("source_error")} for k, v in script_sources.items()}, ensure_ascii=False, indent=2), encoding="utf-8")

        # Save all scripts that match the endpoint field names or relevant endpoints.
        for sid, rec in script_sources.items():
            source = rec.get("source", "")
            if not source:
                continue
            if any(token in source for token in ["api/v1/instagram/stories", "instagram", "_tsc", "_sv", "_s", "username", "FormData", "URLSearchParams"]):
                path = OUTDIR / f"script_{sid}.js"
                path.write_text(source[:250000], encoding="utf-8", errors="replace")
                print("SCRIPT_SOURCE_SAVED", rec.get("url"), path)

        print("REQUEST_IDS", request_ids)
        print("TOTAL_SCRIPT_PARSED", len(script_parsed))
        await browser.close()


asyncio.run(main())
