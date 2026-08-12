import json
import time
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, TimeoutError

VIEWER_URL = 'https://fastdl.app/en2/instagram-anonymously-viewer'
USERNAME = 'israel_bidur'
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)
OUTPUT_DIR = Path(__file__).resolve().parent

def normalize_request(req):
    return {
        'url': req.url,
        'method': req.method,
        'resource_type': req.resource_type,
        'headers': {k: v for k, v in req.headers.items() if k.lower() in ['content-type', 'accept', 'user-agent', 'accept-language', 'referer', 'origin', 'cookie', 'authorization']},
        'post_data': req.post_data if req.post_data else None,
    }


def normalize_response(resp):
    headers = {k: v for k, v in resp.headers.items() if k.lower() in ['content-type', 'content-length', 'set-cookie', 'cache-control', 'pragma', 'expires', 'server', 'vary']}
    body = None
    try:
        body = resp.text()
    except Exception:
        try:
            body = resp.body().decode('utf-8', errors='replace')
        except Exception:
            body = None
    if body is not None and len(body) > 20000:
        body = body[:20000] + '\n...TRUNCATED...'
    return {
        'url': resp.url,
        'status': resp.status,
        'request_url': resp.request.url if resp.request else None,
        'headers': headers,
        'body': body,
    }


def safe_eval(page, script, default=None):
    try:
        return page.evaluate(script)
    except Exception as exc:
        return {'error': str(exc)}


def collect_page_state(page):
    return {
        'url': page.url,
        'title': page.title(),
        'webdriver': safe_eval(page, '() => navigator.webdriver'),
        'user_agent': safe_eval(page, '() => navigator.userAgent'),
        'viewport': safe_eval(page, '() => ({width: window.innerWidth, height: window.innerHeight})'),
        'story_items': safe_eval(page, "() => document.querySelectorAll('.profile-media-list__item').length"),
        'download_buttons': safe_eval(page, "() => document.querySelectorAll('.button__download').length"),
        'meta_times': safe_eval(page, "() => document.querySelectorAll('.media-content__meta-time').length"),
        'story_text': safe_eval(page, "() => document.querySelector('.profile-media-list')?.innerText?.slice(0,1000) || null"),
        'scrollY': safe_eval(page, '() => window.scrollY || window.pageYOffset'),
        'document_height': safe_eval(page, '() => document.documentElement.scrollHeight'),
        'body_height': safe_eval(page, '() => document.body.scrollHeight'),
        'localStorage': safe_eval(page, '() => { const out={}; for (const i=0;i<localStorage.length;i++){ const k=localStorage.key(i); out[k]=localStorage.getItem(k);} return out;}'),
        'sessionStorage': safe_eval(page, '() => { const out={}; for (const i=0;i<sessionStorage.length;i++){ const k=sessionStorage.key(i); out[k]=sessionStorage.getItem(k);} return out;}'),
        'cookies': None,
    }


def run_session(headless: bool):
    label = 'headless' if headless else 'headed'
    results = {'label': label, 'headless': headless, 'network': [], 'page_states': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(user_agent=USER_AGENT, viewport={'width': 1280, 'height': 1200}, locale='en-US')
        page = context.new_page()

        def on_request(request):
            results['network'].append({'type': 'request', **normalize_request(request)})

        def on_response(response):
            if 'api/v1/instagram/stories' in response.url or 'api/v1/instagram/postsV2' in response.url or 'media.fastdl.app/get' in response.url:
                results['network'].append({'type': 'response', **normalize_response(response)})

        page.on('request', on_request)
        page.on('response', on_response)

        page.goto(VIEWER_URL, timeout=60000, wait_until='domcontentloaded')
        page.wait_for_selector('#search-form-input', timeout=30000)
        page.screenshot(path=OUTPUT_DIR / f'01_{label}_initial.png')
        results['page_states'].append({'step': 'loaded', **collect_page_state(page)})

        page.fill('#search-form-input', USERNAME)
        page.evaluate("() => { const overlays = Array.from(document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .overlay, .modal, .cookie-banner')); for (const el of overlays) el.remove(); }")
        page.click('#searchFormButton', timeout=30000, force=True)
        page.wait_for_timeout(4000)
        results['page_states'].append({'step': 'after_search', **collect_page_state(page)})
        page.screenshot(path=OUTPUT_DIR / f'02_{label}_after_search.png')

        page.evaluate(
            "() => { const bs = Array.from(document.querySelectorAll('button.tabs-component__button')); for (const b of bs) { if (b.innerText.toLowerCase().includes('stories')) { b.scrollIntoView(); b.click(); return true; } } return false; }"
        )
        page.wait_for_timeout(5000)
        results['page_states'].append({'step': 'after_click_stories', **collect_page_state(page)})
        page.screenshot(path=OUTPUT_DIR / f'03_{label}_after_click_stories.png')

        for scroll_index in range(1, 6):
            page.evaluate(
                "() => { const items = document.querySelectorAll('.profile-media-list__item'); if (!items.length) return false; items[items.length - 1].scrollIntoView({behavior:'auto', block:'end'}); return true; }"
            )
            page.wait_for_timeout(3000)
            results['page_states'].append({'step': f'scroll_{scroll_index}', **collect_page_state(page)})
            page.screenshot(path=OUTPUT_DIR / f'04_{label}_scroll_{scroll_index}.png')

        results['page_states'].append({'step': 'final', **collect_page_state(page)})
        results['cookies'] = context.cookies()
        browser.close()
    return results


def main():
    out = {'sessions': []}
    for headless in [True, False]:
        try:
            session = run_session(headless)
            out['sessions'].append(session)
        except TimeoutError as exc:
            out['sessions'].append({'label': 'headless' if headless else 'headed', 'error': str(exc)})
    path = OUTPUT_DIR / 'debug_fastdl_full_network.json'
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'wrote {path}')


if __name__ == '__main__':
    main()
