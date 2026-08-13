import asyncio
import json
import os
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright

URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
OUTDIR = Path("debug_fastdl_runtime")
OUTDIR.mkdir(exist_ok=True)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1500, "height": 1200}, locale="en-US")
        page = await context.new_page()

        # Full capture structures
        network_events = []
        js_resources = []
        call_log = []
        worker_events = []
        wasm_events = []
        stories_initiators = []
        body_sequence = []
        final_request = None

        # Very early instrumentation before navigation.
        await page.add_init_script("""
        (() => {
            const record = (kind, detail) => {
              try {
                const payload = { kind, detail, ts: Date.now(), stack: (new Error().stack || '').split('\n').slice(1, 8).join(' | ') };
                window.__fastdl_debug = window.__fastdl_debug || [];
                window.__fastdl_debug.push(payload);
                console.log('FASTDL_DEBUG', JSON.stringify(payload));
              } catch (e) {}
            };

            const origFetch = window.fetch ? window.fetch.bind(window) : null;
            if (origFetch) {
              window.fetch = (...args) => {
                const [url, init] = args;
                record('fetch', { url: String(url), init: init || {}, method: init && init.method ? init.method : 'GET' });
                if (String(url).includes('/api/v1/instagram/stories')) {
                  console.log('FASTDL_FETCH_STORIES', JSON.stringify({ url: String(url), init: init || {} }));
                }
                return origFetch(...args);
              };
            }

            const origOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(method, url, async, user, password) {
              record('xhr_open', { method: String(method), url: String(url), async: !!async, user: user || null, password: password || null });
              if (String(url).includes('/api/v1/instagram/stories')) {
                console.log('FASTDL_XHR_OPEN_STORIES', method, url);
              }
              return origOpen.call(this, method, url, async, user, password);
            };

            const origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.send = function(body) {
              record('xhr_send', { bodyType: typeof body, body: body && typeof body === 'string' ? body.slice(0, 4000) : (body instanceof FormData ? '[FormData]' : (body instanceof URLSearchParams ? '[URLSearchParams]' : String(body || ''))) });
              if (typeof body === 'string' && body.includes('username')) {
                console.log('FASTDL_XHR_SEND_BODY', body.slice(0, 2000));
              }
              return origSend.call(this, body);
            };

            const origFormAppend = FormData.prototype.append;
            FormData.prototype.append = function(name, value, filename) {
              record('formdata_append', { name: String(name), valuePreview: String(value).slice(0, 200), filename: filename || null });
              if (String(name) === '_s' || String(name) === 'username' || String(name) === '_ts' || String(name) === '_tsc' || String(name) === '_sv') {
                console.log('FASTDL_FORMDATA_FIELD', String(name), String(value).slice(0, 400));
              }
              return origFormAppend.call(this, name, value, filename);
            };

            const origURLAppend = URLSearchParams.prototype.append;
            URLSearchParams.prototype.append = function(name, value) {
              record('urlsearchparams_append', { name: String(name), value: String(value).slice(0, 300) });
              if (String(name) === '_s' || String(name) === 'username' || String(name) === '_ts' || String(name) === '_tsc' || String(name) === '_sv') {
                console.log('FASTDL_URLSP_FIELD', String(name), String(value).slice(0, 300));
              }
              return origURLAppend.call(this, name, value);
            };

            const origSet = URLSearchParams.prototype.set;
            URLSearchParams.prototype.set = function(name, value) {
              record('urlsearchparams_set', { name: String(name), value: String(value).slice(0, 300) });
              if (String(name) === '_s' || String(name) === 'username' || String(name) === '_ts' || String(name) === '_tsc' || String(name) === '_sv') {
                console.log('FASTDL_URLSP_SET', String(name), String(value).slice(0, 300));
              }
              return origSet.call(this, name, value);
            };

            const OrigWorker = window.Worker;
            window.Worker = function(...args) {
              record('worker_constructor', { url: args[0] || '', options: args[1] || null });
              return new OrigWorker(...args);
            };
            const OrigSharedWorker = window.SharedWorker;
            window.SharedWorker = function(...args) {
              record('sharedworker_constructor', { url: args[0] || '', options: args[1] || null });
              return new OrigSharedWorker(...args);
            };
            if (navigator.serviceWorker) {
              const origRegister = navigator.serviceWorker.register.bind(navigator.serviceWorker);
              navigator.serviceWorker.register = (...args) => {
                record('serviceworker_register', { url: String(args[0]) });
                return origRegister(...args);
              };
            }

            const origWasmInstantiate = WebAssembly.instantiate;
            WebAssembly.instantiate = function(...args) {
              record('wasm_instantiate', { arg0Type: typeof args[0], arg1Type: typeof args[1] });
              return origWasmInstantiate.apply(this, args);
            };
            const origWasmInstantiateStream = WebAssembly.instantiateStreaming;
            WebAssembly.instantiateStreaming = function(...args) {
              record('wasm_instantiate_streaming', { arg0Type: typeof args[0], arg1Type: typeof args[1] });
              return origWasmInstantiateStream.apply(this, args);
            };
        })();
        """)

        page.on('console', lambda msg: call_log.append({"type": "console", "text": msg.text}) if any(token in msg.text.lower() for token in ['fastdl_debug','fastdl_fetch_stories','fastdl_xhr','fastdl_formdata','fastdl_urlsp','fastdl_worker','fastdl_wasm']) else None)

        # Main collectors
        async def on_response(resp):
            url = resp.url
            if 'fastdl.app' in url or 'api-wh.fastdl.app' in url or 'google-analytics' in url or 'googletagmanager' in url or 'pagead' in url:
                js_resources.append({
                    'url': url,
                    'type': resp.request.resource_type,
                    'status': resp.status,
                    'content_type': resp.headers.get('content-type'),
                    'request_headers': dict(resp.request.headers),
                    'from_url': resp.request.frame.url if resp.request.frame else None,
                    'remote_address': resp.remote_address,
                    'timing': resp.timing,
                    'time': time.time(),
                })

        page.on('response', on_response)

        page.on('request', lambda req: network_events.append({
            'method': req.method,
            'url': req.url,
            'resourceType': req.resource_type,
            'frame': req.frame.url if req.frame else None,
            'headers': dict(req.headers),
            'postData': req.post_data,
        }) if ('fastdl.app' in req.url or 'api-wh.fastdl.app' in req.url or 'googletagmanager' in req.url or 'google-analytics' in req.url or 'pagead' in req.url or '/api/v1/instagram/stories' in req.url) else None)

        cdp = await context.new_cdp_session(page)
        await cdp.send('Network.enable', {'maxTotalBufferSize': 100000000, 'maxResourceBufferSize': 100000000})
        await cdp.send('Page.enable', {})
        await cdp.send('Runtime.enable', {})

        async def on_request_will_be_sent(event):
            params = event.get('params', {})
            req = params.get('request', {})
            url = req.get('url', '')
            if '/api/v1/instagram/stories' in url:
                stories_initiators.append({
                    'event': event,
                    'request': req,
                    'initiator': params.get('initiator'),
                    'redirect': params.get('redirectResponse'),
                    'timestamp': params.get('timestamp'),
                })
                print('STORIES_INITIATOR_RAW')
                print(json.dumps(params, ensure_ascii=False, indent=2, default=str))
                print('---END RAW---')
                final_request = { 'url': url, 'request': req, 'initiator': params.get('initiator') }

        cdp.on('Network.requestWillBeSent', on_request_will_be_sent)

        # Also track service workers / workers / wasm from page runtime.
        async def get_worker_info():
            try:
                workers = await page.evaluate('''() => {
                    const out = [];
                    if (navigator.serviceWorker) {
                        out.push({ kind: 'service_worker', controller: !!navigator.serviceWorker.controller, ready: !!navigator.serviceWorker.ready });
                    }
                    try {
                        const w = new Worker('data:text/javascript,console.log(\'worker-probe\')');
                        w.terminate();
                        out.push({ kind: 'worker', ok: true });
                    } catch (e) {
                        out.push({ kind: 'worker', ok: false, err: String(e) });
                    }
                    try {
                        const sw = new SharedWorker('data:text/javascript,console.log(\'shared-worker-probe\')');
                        sw.port.close();
                        out.push({ kind: 'shared_worker', ok: true });
                    } catch (e) {
                        out.push({ kind: 'shared_worker', ok: false, err: String(e) });
                    }
                    return out;
                }''')
                worker_events.append(workers)
            except Exception as e:
                worker_events.append({'error': str(e)})

        await page.goto(URL, wait_until='domcontentloaded', timeout=120000)
        await get_worker_info()
        await page.wait_for_timeout(4000)

        # Search flow trigger
        await page.fill('#search-form-input', 'israel_bidur')
        await page.click('#searchFormButton', force=True)
        await page.wait_for_timeout(12000)

        # second username same session
        await page.fill('#search-form-input', 'instagram')
        await page.click('#searchFormButton', force=True)
        await page.wait_for_timeout(12000)

        # If there was a response with JS chunks after search, save their content for deeper inspection.
        for item in js_resources:
            url = item.get('url')
            if not url or not ('fastdl.app/js/' in url or 'chunk' in url.lower()):
                continue
            try:
                # Save runtime-loaded JS bodies where possible.
                if 'fastdl.app' in url:
                    resp = await page.request.get(url)
                    text = resp.text()
                    if text and len(text) > 200:
                        sanitized = re.sub(r'\s+', ' ', text[:25000])
                        pth = OUTDIR / (re.sub(r'[^A-Za-z0-9_.-]+', '_', url)[:180] + '.js')
                        pth.write_text(text[:250000], encoding='utf-8', errors='replace')
                        if any(tok in text.lower() for tok in ['/api/v1/instagram/stories', '_s', '_ts', '_tsc', '_sv', 'crypto', 'subtle', 'digest', 'hmac', 'sha', 'md5', 'encode', 'sign', 'signature', 'formdata', 'fetch', 'xmlhttprequest']):
                            print('JS_MATCH_URL', url)
            except Exception:
                pass

        # Dump full complete data to JSON files.
        (OUTDIR / 'network_events.json').write_text(json.dumps(network_events, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        (OUTDIR / 'js_resources.json').write_text(json.dumps(js_resources, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        (OUTDIR / 'call_log.json').write_text(json.dumps(call_log, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        (OUTDIR / 'worker_events.json').write_text(json.dumps(worker_events, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        (OUTDIR / 'stories_initiators.json').write_text(json.dumps(stories_initiators, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        print('FILES', sorted(str(x) for x in OUTDIR.iterdir()))

        await browser.close()

asyncio.run(main())
