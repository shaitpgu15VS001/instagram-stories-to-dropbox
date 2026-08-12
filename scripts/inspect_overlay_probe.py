from playwright.sync_api import sync_playwright

p = sync_playwright().start()
b = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
c = b.new_context(
    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    viewport={'width': 1280, 'height': 900},
    locale='en-US'
)
page = c.new_page()
page.goto('https://fastdl.app/en2/instagram-anonymously-viewer', wait_until='domcontentloaded')
page.wait_for_timeout(3000)
selectors = [
    '.fc-dialog-overlay',
    '.fc-consent-root',
    '.overlay',
    '.modal',
    '.cookie-banner',
    '.fc__dialog',
    '.fc-cookie-banner',
    '[role=dialog]'
]
for sel in selectors:
    print(sel, len(page.query_selector_all(sel)))
print('consent buttons count', len(page.query_selector_all('button:has-text("Consent")')))
print('manage buttons count', len(page.query_selector_all('button:has-text("Manage options")')))
print('search input visible', page.is_visible('#search-form-input'))
print('search button visible', page.is_visible('#searchFormButton'))
btn = page.query_selector('#searchFormButton')
print('search button text', btn.inner_text() if btn else 'none')
print('button texts', [e.inner_text() for e in page.query_selector_all('button') if e.inner_text()])
page.screenshot(path='scripts/inspect_overlay.png')
b.close()
p.stop()
