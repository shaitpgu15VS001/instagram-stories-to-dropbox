import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
USERNAME = "israel_bidur"
OUTPUT = Path(__file__).resolve().parent / "debug_fastdl_compare.json"
SCREENSHOT_DIR = Path(__file__).resolve().parent / "debug_fastdl_compare_screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def collect_dom_counts(page):
    return page.evaluate("""
        () => {
            const items = Array.from(document.querySelectorAll('.profile-media-list__item'));
            const visible = items.filter(i => { const r = i.getBoundingClientRect(); return r.width>0 && r.height>0; }).length;
            const anchors = items.map(i => ({hrefs: Array.from(i.querySelectorAll('a')).map(a=>a.href)}));
            return {items_count: items.length, visible_count: visible, anchors_sample: anchors.slice(0,10)};
        }
    """)


def collect_js_state(page):
    return page.evaluate("""
        () => {
            const found = {};
            try {
                // try common places
                if (window.__INITIAL_STATE__) found.__INITIAL_STATE__ = Object.keys(window.__INITIAL_STATE__ || {}).slice(0,50);
            } catch(e){ found.__INITIAL_STATE__ = 'ERR'; }
            try {
                if (window.__BOOTSTRAP__) found.__BOOTSTRAP__ = Object.keys(window.__BOOTSTRAP__ || {}).slice(0,50);
            } catch(e){ found.__BOOTSTRAP__ = 'ERR'; }
            try { found.window_keys = Object.getOwnPropertyNames(window).filter(k=>/story|stories|fastdl|profile|media/i.test(k)).slice(0,50); } catch(e){ found.window_keys='ERR' }
            return found;
        }
    """)


def main():
    results = {"username": USERNAME, "network": [], "api_response": None, "runs": []}
    api_hits = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 1200}, locale="en-US")
        page = context.new_page()

        def on_request(request):
            results['network'].append({'type': 'request', 'url': request.url, 'method': request.method, 'resource_type': request.resource_type})

        def on_response(response):
            try:
                results['network'].append({'type': 'response', 'url': response.url, 'status': response.status, 'request_url': response.request.url})
                if '/api/v1/instagram/stories' in response.url:
                    try:
                        body = None
                        try:
                            body = response.json()
                        except Exception:
                            # fallback to text
                            body = response.text()
                        api_hits.append({'url': response.url, 'status': response.status, 'body_sample': (body if isinstance(body, dict) else str(body))})
                    except Exception as e:
                        api_hits.append({'url': response.url, 'status': response.status, 'error': str(e)})
            except Exception:
                pass

        page.on('request', on_request)
        page.on('response', on_response)

        page.goto(VIEWER_URL, timeout=60000, wait_until='domcontentloaded')
        page.wait_for_selector('#search-form-input', timeout=30000, state='visible')
        page.screenshot(path=SCREENSHOT_DIR / '01_initial.png')
        page.fill('#search-form-input', USERNAME)
        page.evaluate("""
            () => {
                const overlays = Array.from(document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .overlay, .modal, .cookie-banner'));
                for (const el of overlays) el.remove();
            }
        """)
        page.click('#searchFormButton', timeout=30000, force=True)
        page.wait_for_timeout(2000)
        page.screenshot(path=SCREENSHOT_DIR / '02_after_search.png')

        # click Stories tab
        page.evaluate(
            """
            () => {
                const bs = Array.from(document.querySelectorAll('button.tabs-component__button'));
                for (const b of bs) {
                    if (b.innerText && b.innerText.toLowerCase().includes('stories')) { b.scrollIntoView(); b.click(); return true; }
                }
                return false;
            }
            """
        )

        # wait for network hit to stories API or timeout (poll api_hits)
        waited = 0.0
        while waited < 15.0 and not api_hits:
            page.wait_for_timeout(500)
            waited += 0.5

        # extra wait for rendering
        page.wait_for_timeout(3000)
        page.screenshot(path=SCREENSHOT_DIR / '03_stories.png')

        # collect dom counts and js state
        dom = collect_dom_counts(page)
        js_state = collect_js_state(page)

        # store api_hits collected
        results['api_response'] = api_hits
        results['runs'].append({'dom': dom, 'js_state': js_state})

        # try scrolling to force virtualization
        for i in range(1,6):
            page.evaluate('() => { window.scrollTo(0, document.body.scrollHeight * 0.9); }')
            page.wait_for_timeout(1500)
            page.screenshot(path=SCREENSHOT_DIR / f'04_scroll_{i}.png')
            dom_after = collect_dom_counts(page)
            results['runs'].append({'step': f'scroll_{i}', 'dom': dom_after})

        # final capture of window state keys
        results['final_window_keys'] = page.evaluate('() => Object.getOwnPropertyNames(window).filter(k=>/story|stories|fastdl|profile|media/i.test(k))')

        browser.close()

    # write outputs
    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    # write raw api hits too
    (Path(__file__).resolve().parent / 'debug_fastdl_compare_api_hits.json').write_text(json.dumps(api_hits, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print('saved', OUTPUT)


if __name__ == '__main__':
    main()
