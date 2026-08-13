import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
OUT_DIR = Path("debug_fastdl_js_probe_v2")
OUT_DIR.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1500, "height": 1200})
    page = context.new_page()

    request_events = []
    response_events = []
    console_lines = []

    page.on("request", lambda req: request_events.append({
        "method": req.method,
        "url": req.url,
        "resource_type": req.resource_type,
        "post_data": req.post_data,
    }) if ("api-wh.fastdl.app" in req.url or "fastdl.app" in req.url or req.resource_type == "script") else None)

    page.on("response", lambda resp: response_events.append({
        "url": resp.url,
        "status": resp.status,
        "content_type": resp.headers.get("content-type"),
        "request_method": resp.request.method,
    }) if ("api-wh.fastdl.app" in resp.url or "fastdl.app" in resp.url or resp.request.resource_type == "script") else None)

    page.on("console", lambda msg: console_lines.append(msg.text))

    page.add_init_script(
        """
        (() => {
            const originalFetch = window.fetch.bind(window);
            window.fetch = function(...args) {
                const info = {type: 'fetch', url: args[0], init: args[1] || {}};
                console.log('HOOK_FETCH', JSON.stringify(info));
                return originalFetch(...args);
            };
            const originalOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, async, user, password) {
                console.log('HOOK_XHR_OPEN', method, url);
                return originalOpen.call(this, method, url, async, user, password);
            };
            const originalSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = function(body) {
                console.log('HOOK_XHR_SEND', String(body || ''));
                return originalSend.call(this, body);
            };
            const origSubtle = crypto.subtle;
            crypto.subtle = new Proxy(origSubtle, {
                get(target, prop, receiver) {
                    const v = Reflect.get(target, prop, receiver);
                    if (typeof v === 'function') {
                        return function(...args) {
                            console.log('HOOK_CRYPTO', String(prop), JSON.stringify(args.slice(0, 2)));
                            return v.apply(target, args);
                        };
                    }
                    return v;
                }
            });
        })();
        """
    )

    page.goto(URL, wait_until="domcontentloaded", timeout=90000)
    time.sleep(4)

    input_sel = '#search-form-input'
    try:
        page.fill(input_sel, 'israel_bidur')
        page.click('#searchFormButton', force=True)
    except Exception as e:
        print('CLICK_ERROR', repr(e))

    time.sleep(8)

    print('REQUEST_COUNT', len(request_events))
    print('RESPONSE_COUNT', len(response_events))
    for evt in request_events[:50]:
        if 'api-wh.fastdl.app' in evt['url'] or 'fastdl.app' in evt['url'] or evt['resource_type'] == 'script':
            print('REQUEST', evt)
    print('---RESPONSES---')
    for evt in response_events[:50]:
        print('RESPONSE', evt)
    print('---CONSOLE---')
    for line in console_lines[:200]:
        print(line)

    (OUT_DIR / 'request_events.json').write_text(json.dumps(request_events, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT_DIR / 'response_events.json').write_text(json.dumps(response_events, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT_DIR / 'console_lines.json').write_text(json.dumps(console_lines, ensure_ascii=False, indent=2), encoding='utf-8')
    print('FILES', [str(x) for x in sorted(OUT_DIR.glob('*'))])
    browser.close()
