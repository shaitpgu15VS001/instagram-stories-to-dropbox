import json, time
from pathlib import Path
from urllib.parse import urlparse

from curl_cffi import requests as cf_requests
from playwright.sync_api import sync_playwright

API_URL = "https://api-wh.fastdl.app/api/v1/instagram/stories"
VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USERNAME = "israel_bidur"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUT = Path("scripts") / "debug_fastdl_capture_replay.json"


def js_to_obj(s):
    if not isinstance(s, str):
        return s
    try:
        return json.loads(s)
    except Exception:
        return s


def make_curl_probe(label, payload, cookies, headers, impersonate=None):
    s = cf_requests.Session()
    s.headers.update(headers)
    for c in cookies:
        if c.get("name"):
            s.cookies.set(c["name"], c["value"], domain=c.get("domain") or None, path=c.get("path") or "/")
    kwargs = {"timeout": 30}
    if impersonate:
        kwargs["impersonate"] = impersonate
    try:
        r = s.post(API_URL, json=payload, **kwargs)
        return {
            "label": label,
            "status": r.status_code,
            "mime": r.headers.get("Content-Type"),
            "server": r.headers.get("Server"),
            "json": r.headers.get("Content-Type", "").lower().find("application/json") >= 0,
            "body": (r.text or "")[:800],
            "headers": dict(r.headers),
        }
    except Exception as e:
        return {"label": label, "status": None, "error": f"{type(e).__name__}: {e}"}


def build_browser_roundtrip():
    captured = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, locale="en-US")
        page = context.new_page()
        page.on("request", lambda req: captured.append({"kind": "request", "url": req.url, "method": req.method, "headers": dict(req.headers), "post_data": req.post_data, "cookies": [{"name": c["name"], "value": c["value"], "domain": c.get("domain"), "path": c.get("path")} for c in context.cookies()]}) if "api/v1/instagram/stories" in req.url and req.method == "POST" else None)

        page.on("response", lambda resp: None)
        page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=60000)
        page.locator('#search-form-input').wait_for(state='visible', timeout=20000)
        page.evaluate("() => { document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .fc-cookie-banner, .modal, [role=dialog]').forEach(el => el.remove()); }")
        for attempt in range(2):
            page.locator('#search-form-input').fill(USERNAME)
            page.locator('#searchFormButton').click(force=True)
            page.wait_for_timeout(4000)
            try:
                button = page.locator('button.tabs-component__button')
                for i in range(button.count()):
                    txt = button.nth(i).inner_text()
                    if 'stories' in txt.lower():
                        button.nth(i).click(); break
            except Exception:
                pass
            page.wait_for_timeout(7000)
            # collect request+response for this cycle during the wait above
            # we will inspect page's request history from a custom event below using a list mutated in closure
        browser.close()

    return captured


def record_two_requests():
    reqs = []

    def collect_request(req):
        if 'api/v1/instagram/stories' in req.url and req.method == 'POST':
            payload = js_to_obj(req.post_data)
            reqs.append({
                'captured_at_local_ms': int(time.time() * 1000),
                'captured_at_iso': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'url': req.url,
                'method': req.method,
                'headers': dict(req.headers),
                'post_data': req.post_data,
                'payload': payload if isinstance(payload, dict) else None,
            })

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={'width': 1400, 'height': 900}, locale='en-US')
        page = context.new_page()
        page.on('request', collect_request)
        page.goto(VIEWER_URL, wait_until='domcontentloaded', timeout=60000)
        page.locator('#search-form-input').wait_for(state='visible', timeout=30000)
        page.evaluate("() => { document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .fc-cookie-banner, .modal, [role=dialog]').forEach(el => el.remove()); }")

        for cycle in range(2):
            page.locator('#search-form-input').fill(USERNAME)
            page.locator('#searchFormButton').click(force=True)
            page.wait_for_timeout(4000)
            try:
                buttons = page.locator('button.tabs-component__button')
                for i in range(buttons.count()):
                    txt = buttons.nth(i).inner_text()
                    if 'stories' in txt.lower():
                        buttons.nth(i).click(); break
            except Exception:
                pass
            page.wait_for_timeout(5000)
            if len(reqs) >= 2:
                break

        # collect response status for each request by tracking in same list
        for req in reqs:
            # response status tracked from separate response handler
            pass

        # add response statuses by listening to response events
        responses = []
        def collect_response(resp):
            if 'api/v1/instagram/stories' in resp.url and resp.request.method == 'POST':
                try:
                    text = resp.text()
                except Exception:
                    text = ''
                for req in reqs:
                    if req['url'] == resp.url and req['method'] == resp.request.method:
                        req['status'] = resp.status
                        req['response_headers'] = dict(resp.headers)
                        req['response_body_prefix'] = text[:800]
                        break
        page.on('response', collect_response)
        # Wait for response events on the last two requests; they are already mostly done, but this wait gives them time to finish.
        page.wait_for_timeout(2000)
        browser.close()
    return reqs


def main():
    reqs = record_two_requests()
    print('RAW_REQUEST_COUNT', len(reqs))
    print(json.dumps(reqs, ensure_ascii=False, indent=2)[:12000])

    # Replay each request immediately using curl_cffi with cookies + headers + impersonation
    if reqs:
        base = []
        for i, r in enumerate(reqs[:2], 1):
            payload = r.get('payload')
            if not isinstance(payload, dict):
                continue
            headers = {k: v for k, v in r.get('headers', {}).items() if k.lower() not in {'host','content-length'}}
            cookies = [{"name": c["name"], "value": c["value"], "domain": c.get("domain"), "path": c.get("path")} for c in context_cookies_for_this_test] if False else []
            # Use cookies collected from the browser context before closure is lost by repopulating from a fresh context below.
            # We intentionally do a fresh browser flow for the immediate replay, to keep the data exact and fresh.
            base.append({"index": i, "payload": payload, "headers": headers})
        print('REPLAY_PREP_READY', len(base))

    # Build a second fresh browser session just for immediate replay tests and final JSON output.
    fresh = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={'width': 1400, 'height': 900}, locale='en-US')
        page = context.new_page()
        replay_payloads = []

        def on_request(req):
            if 'api/v1/instagram/stories' in req.url and req.method == 'POST':
                replay_payloads.append({
                    'captured_at_local_ms': int(time.time() * 1000),
                    'url': req.url,
                    'method': req.method,
                    'headers': dict(req.headers),
                    'post_data': req.post_data,
                    'payload': js_to_obj(req.post_data),
                    'cookies': [{'name': c['name'], 'value': c['value'], 'domain': c.get('domain'), 'path': c.get('path')} for c in context.cookies()],
                })
        page.on('request', on_request)
        page.goto(VIEWER_URL, wait_until='domcontentloaded', timeout=60000)
        page.locator('#search-form-input').wait_for(state='visible', timeout=30000)
        page.evaluate("() => { document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .fc-cookie-banner, .modal, [role=dialog]').forEach(el => el.remove()); }")
        page.locator('#search-form-input').fill(USERNAME)
        page.locator('#searchFormButton').click(force=True)
        page.wait_for_timeout(5000)
        try:
            buttons = page.locator('button.tabs-component__button')
            for i in range(buttons.count()):
                txt = buttons.nth(i).inner_text()
                if 'stories' in txt.lower():
                    buttons.nth(i).click(); break
        except Exception:
            pass
        page.wait_for_timeout(7000)
        for idx, item in enumerate(replay_payloads[:2], 1):
            payload = item['payload'] if isinstance(item['payload'], dict) else None
            headers = {k: v for k, v in item['headers'].items() if k.lower() not in {'host','content-length'}}
            replay = make_curl_probe(f'replay_{idx}_cookies_impersonation', payload, item['cookies'], headers, impersonate='chrome120')
            replay_no_cookies = make_curl_probe(f'replay_{idx}_no_cookies_impersonation', payload, [], headers, impersonate='chrome120')
            replay_no_impersonation = make_curl_probe(f'replay_{idx}_cookies_no_impersonation', payload, item['cookies'], headers)
            fresh.append({'capture_index': idx, 'payload': payload, 'replay': replay, 'replay_no_cookies': replay_no_cookies, 'replay_no_impersonation': replay_no_impersonation})
        browser.close()
    OUT.write_text(json.dumps({'fresh_requests': fresh}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('WROTE', OUT)


if __name__ == '__main__':
    main()
