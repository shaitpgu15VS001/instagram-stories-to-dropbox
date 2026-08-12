import json
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError

VIEWER_URL = 'https://fastdl.app/en2/instagram-anonymously-viewer'
USERNAME = 'israel_bidur'
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)
OUTPUT_DIR = Path(__file__).resolve().parent


def collect_state(page):
    return {
        'webdriver': page.evaluate('() => navigator.webdriver'),
        'userAgent': page.evaluate('() => navigator.userAgent'),
        'url': page.url,
        'story_items': page.evaluate("() => document.querySelectorAll('.profile-media-list__item').length"),
        'download_buttons': page.evaluate("() => document.querySelectorAll('.button__download').length"),
        'meta_times': page.evaluate("() => document.querySelectorAll('.media-content__meta-time').length"),
        'story_item_texts': page.evaluate("() => Array.from(document.querySelectorAll('.profile-media-list__item')).map((el, idx) => ({idx, visible: el.getBoundingClientRect().width > 0 && el.getBoundingClientRect().height > 0, classes: el.className, html: el.outerHTML.slice(0,400)}))"),
        'localStorage': page.evaluate("() => { const out={}; for (let i=0;i<localStorage.length;i++){ const k=localStorage.key(i); out[k]=localStorage.getItem(k);} return out; }"),
        'sessionStorage': page.evaluate("() => { const out={}; for (let i=0;i<sessionStorage.length;i++){ const k=sessionStorage.key(i); out[k]=sessionStorage.getItem(k);} return out; }"),
    }


def run_session(headless: bool):
    label = 'headless' if headless else 'headed'
    results = {'label': label, 'headless': headless, 'requests': [], 'responses': [], 'page_states': []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(user_agent=USER_AGENT, viewport={'width': 1280, 'height': 1200}, locale='en-US')
        page = context.new_page()

        def on_request(request):
            if 'api/v1/instagram/stories' in request.url or 'api/v1/instagram/postsV2' in request.url:
                results['requests'].append({
                    'url': request.url,
                    'method': request.method,
                    'headers': {k: v for k, v in request.headers.items() if k.lower() in ['content-type', 'accept', 'referer', 'origin', 'user-agent']},
                    'post_data': request.post_data,
                })

        def on_response(response):
            if 'api/v1/instagram/stories' in response.url or 'api/v1/instagram/postsV2' in response.url:
                body = None
                try:
                    body = response.text()
                except Exception as exc:
                    body = f'ERROR: {exc}'
                results['responses'].append({
                    'url': response.url,
                    'status': response.status,
                    'headers': {k: v for k, v in response.headers.items() if k.lower() in ['content-type', 'content-length', 'vary', 'server']},
                    'body': body,
                })

        page.on('request', on_request)
        page.on('response', on_response)

        page.goto(VIEWER_URL, timeout=60000, wait_until='domcontentloaded')
        page.wait_for_selector('#search-form-input', timeout=30000)
        results['page_states'].append({'step': 'loaded', **collect_state(page)})

        page.fill('#search-form-input', USERNAME)
        page.evaluate("() => { const overlays = Array.from(document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .overlay, .modal, .cookie-banner')); for (const el of overlays) el.remove(); }")
        page.click('#searchFormButton', timeout=30000, force=True)
        page.wait_for_timeout(5000)
        results['page_states'].append({'step': 'after_search', **collect_state(page)})

        page.evaluate(
            "() => { const bs = Array.from(document.querySelectorAll('button.tabs-component__button')); for (const b of bs) { if (b.innerText.toLowerCase().includes('stories')) { b.scrollIntoView(); b.click(); return true; } } return false; }"
        )
        page.wait_for_timeout(6000)
        results['page_states'].append({'step': 'after_click_stories', **collect_state(page)})

        for i in range(1, 6):
            page.evaluate("() => { const items = document.querySelectorAll('.profile-media-list__item'); if (!items.length) return false; items[items.length - 1].scrollIntoView({behavior:'auto', block:'end'}); return true; }")
            page.wait_for_timeout(3000)
            results['page_states'].append({'step': f'scroll_{i}', **collect_state(page)})

        results['page_states'].append({'step': 'final', **collect_state(page)})
        browser.close()

    path = OUTPUT_DIR / f'debug_fastdl_story_api_raw_{label}.json'
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'wrote {path}')
    return results


def main():
    for headless in [True, False]:
        try:
            run_session(headless)
        except TimeoutError as exc:
            print('ERROR', 'headless' if headless else 'headed', exc)

if __name__ == '__main__':
    main()
