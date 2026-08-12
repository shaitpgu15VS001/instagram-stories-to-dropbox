import json
from pathlib import Path
from playwright.sync_api import sync_playwright

VIEWER_URL = 'https://fastdl.app/en2/instagram-anonymously-viewer'
USERNAME = 'israel_bidur'
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)
OUTPUT = Path('scripts/debug_fastdl_story_response.json')

results = {'responses': []}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = browser.new_context(user_agent=USER_AGENT, viewport={'width': 1280, 'height': 1200}, locale='en-US')
    page = context.new_page()

    def on_response(response):
        try:
            url = response.url
            if 'api/v1/instagram/stories' in url or 'api/v1/instagram/postsV2' in url:
                body = None
                try:
                    body = response.text()
                except Exception as exc:
                    body = f'ERROR: {exc}'
                results['responses'].append({'url': url, 'status': response.status, 'body_snippet': body[:2000] if isinstance(body, str) else None, 'body_length': len(body) if body is not None else None})
        except Exception:
            pass

    page.on('response', on_response)
    page.goto(VIEWER_URL, timeout=60000, wait_until='domcontentloaded')
    page.wait_for_selector('#search-form-input', timeout=30000)
    page.fill('#search-form-input', USERNAME)
    page.evaluate("""
        () => {
            const overlays = Array.from(document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .overlay, .modal, .cookie-banner'));
            for (const el of overlays) {
                el.remove();
            }
            const elems = Array.from(document.querySelectorAll('button, input'));
            for (const el of elems) {
                const style = window.getComputedStyle(el);
                if (style.pointerEvents === 'none' && el.closest('.fc-consent-root')) {
                    el.closest('.fc-consent-root').remove();
                }
            }
        }
    """)
    page.click('#searchFormButton', timeout=30000, force=True)
    page.wait_for_timeout(5000)
    page.evaluate(
        """
        () => {
            const bs = Array.from(document.querySelectorAll('button.tabs-component__button'));
            for (const b of bs) {
                if (b.innerText.toLowerCase().includes('stories')) {
                    b.scrollIntoView();
                    b.click();
                    return true;
                }
            }
            return false;
        }
        """
    )
    page.wait_for_timeout(8000)
    page.screenshot(path=Path('scripts/debug_fastdl_story_response.png'))
    results['page_info'] = page.evaluate(
        """
        () => ({
            title: document.title,
            url: location.href,
            webdriver: navigator.webdriver,
            story_items: document.querySelectorAll('.profile-media-list__item').length,
            download_buttons: document.querySelectorAll('.button__download').length,
            media_meta: document.querySelectorAll('.media-content__meta-time').length,
            tabs: Array.from(document.querySelectorAll('button.tabs-component__button')).map(b => b.innerText),
            story_text: document.querySelector('.profile-media-list')?.innerText?.slice(0,1000) || null,
        })
        """
    )
    OUTPUT.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    browser.close()

print(f'wrote {OUTPUT}')
