import json, os, time
from pathlib import Path
from urllib.parse import urlparse

import requests
import httpx
from curl_cffi import requests as cf_requests
from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USERNAME = "israel_bidur"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def collect_browser_payload_and_media():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=UA, viewport={"width": 1400, "height": 900}, locale="en-US")
        page = context.new_page()
        result = {"api_request": None, "api_response": None, "cookies": [], "story_url": None, "page_url": None}
        seen = {}

        def on_request(req):
            if "api/v1/instagram/stories" in req.url and req.method == "POST":
                seen['request'] = {"url": req.url, "method": req.method, "headers": dict(req.headers), "post_data": req.post_data, "timestamp": int(time.time()*1000)}
                result['api_request'] = seen['request']

        def on_response(resp):
            if "api/v1/instagram/stories" in resp.url and resp.request.method == "POST":
                try:
                    body = resp.text()
                except Exception:
                    body = ""
                try:
                    payload = resp.json()
                except Exception:
                    payload = None
                seen['response'] = {"status": resp.status, "headers": dict(resp.headers), "body_sample": body[:2000], "payload": payload}
                result['api_response'] = seen['response']

        page.on('request', on_request)
        page.on('response', on_response)
        page.goto(VIEWER_URL, wait_until='domcontentloaded', timeout=60000)
        page.locator('#search-form-input').wait_for(state='visible', timeout=30000)
        page.evaluate("""
        () => {
            document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .fc-cookie-banner, .modal, [role=dialog]').forEach(el => el.remove())
        }
        """)
        page.locator('#search-form-input').fill(USERNAME)
        page.locator('#searchFormButton').click(force=True)
        page.wait_for_timeout(4000)
        try:
            page.locator('button.tabs-component__button').first.wait_for(timeout=15000)
        except Exception:
            pass
        try:
            buttons = page.locator('button.tabs-component__button')
            for i in range(buttons.count()):
                txt = buttons.nth(i).inner_text()
                if 'stories' in txt.lower():
                    buttons.nth(i).click(); break
        except Exception:
            pass
        page.wait_for_timeout(7000)
        result['page_url'] = page.url
        result['cookies'] = [{"name": c['name'], "value": c['value'], "domain": c.get('domain'), "path": c.get('path')} for c in context.cookies()]

        payload = result['api_response'].get('payload') if result.get('api_response') else None
        if isinstance(payload, dict):
            items = payload.get('result') if isinstance(payload.get('result'), list) else []
            for item in items:
                if not isinstance(item, dict):
                    continue
                for key in ('url_downloadable','url_wrapped','url'):
                    if key in item and isinstance(item[key], str):
                        result['story_url'] = item[key]
                        break
                if result['story_url']:
                    break
                if isinstance(item.get('image_versions2'), dict):
                    cands = item['image_versions2'].get('candidates') or []
                    for cand in cands:
                        if isinstance(cand, dict):
                            for key in ('url_downloadable','url_wrapped','url'):
                                if key in cand and isinstance(cand[key], str):
                                    result['story_url'] = cand[key]
                                    break
                        if result['story_url']:
                            break
                if result['story_url']:
                    break
        browser.close()
    return result


def fetch_status(label, req_fn, short=True):
    try:
        r = req_fn()
        body = (r.text or '')[:300]
        return {
            'label': label,
            'status': getattr(r, 'status_code', None),
            'content_type': r.headers.get('Content-Type') if hasattr(r, 'headers') else None,
            'content_length': r.headers.get('Content-Length') if hasattr(r, 'headers') else None,
            'is_json': 'application/json' in str(r.headers.get('Content-Type','')).lower(),
            'body_prefix': body,
            'redirected': getattr(r, 'is_redirect', None) or 'location' in r.headers,
            'ok': getattr(r, 'status_code', 0) == 200,
        }
    except Exception as e:
        return {'label': label, 'status': None, 'error': type(e).__name__ + ': ' + str(e), 'ok': False}


def main():
    capture = collect_browser_payload_and_media()
    print('=== BROWSER CAPTURE ===')
    print(json.dumps({
        'page_url': capture.get('page_url'),
        'story_url': capture.get('story_url'),
        'api_status': capture.get('api_response', {}).get('status'),
        'api_json': isinstance(capture.get('api_response', {}).get('payload'), dict),
        'cookie_count': len(capture.get('cookies', [])),
        'request_sample': (capture.get('api_request', {}) or {}).get('post_data')
    }, ensure_ascii=False, indent=2))

    if not capture.get('story_url'):
        print('No story URL captured; aborting media tests')
        return

    media_url = capture['story_url']
    req_headers = {'User-Agent': UA, 'Referer': 'https://fastdl.app/', 'Origin': 'https://fastdl.app'}

    print('=== MEDIA TESTS ===')
    tests = []
    tests.append(fetch_status('requests', lambda: requests.get(media_url, headers=req_headers, timeout=30, stream=True)))
    tests.append(fetch_status('httpx', lambda: httpx.get(media_url, headers=req_headers, timeout=30)))

    s = cf_requests.Session()
    s.headers.update(req_headers)
    tests.append(fetch_status('curl_cffi_no_cookie', lambda: s.get(media_url, impersonate='chrome120', timeout=30)))

    s2 = cf_requests.Session()
    s2.headers.update(req_headers)
    for c in capture.get('cookies', []):
        if c.get('name'):
            s2.cookies.set(c['name'], c['value'], domain=c.get('domain') or None, path=c.get('path') or '/')
    tests.append(fetch_status('curl_cffi_with_cookie', lambda: s2.get(media_url, impersonate='chrome120', timeout=30)))

    print(json.dumps(tests, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
