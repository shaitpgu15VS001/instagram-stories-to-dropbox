from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    context = browser.new_context(
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        viewport={'width': 1280, 'height': 900},
        locale='en-US'
    )
    page = context.new_page()
    page.goto('https://fastdl.app/en2/instagram-anonymously-viewer', wait_until='domcontentloaded', timeout=60000)
    page.wait_for_selector('#search-form-input', timeout=30000, state='visible')
    inputs = page.query_selector_all('#search-form-input')
    print('input count', len(inputs))
    for idx, inp in enumerate(inputs):
        print('input', idx, 'outerHTML', inp.evaluate('e => e.outerHTML'))
        print('visible', inp.is_visible())
        print('value', inp.evaluate('e => e.value'))
        print('style display', inp.evaluate('e => window.getComputedStyle(e).display'))
        print('attr disabled', inp.get_attribute('disabled'))
        print('rect', inp.evaluate('e => { const r=e.getBoundingClientRect(); return {width:r.width,height:r.height,x:r.x,y:r.y}; }'))
    page.fill('#search-form-input', 'israel_bidur')
    page.wait_for_timeout(500)
    print('after fill first input', inputs[0].evaluate('e => e.value'))
    print('after fill via query selector', page.query_selector('#search-form-input').evaluate('e => e.value'))
    page.evaluate("() => { const el=document.querySelector('#search-form-input'); if (el) { el.value='israel_bidur'; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); } }")
    page.wait_for_timeout(500)
    print('after eval event value', page.query_selector('#search-form-input').evaluate('e => e.value'))
    print('button disabled', page.query_selector('#searchFormButton').get_attribute('disabled'))
    page.screenshot(path='scripts/debug_inspect_input.png')
    browser.close()