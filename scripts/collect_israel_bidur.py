import json
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError


def collect(page):
    items = page.query_selector_all('.profile-media-list__item')
    results = []
    for idx, li in enumerate(items):
        data = page.evaluate('(el) => { const o={}; for (const k in el.dataset) o[k]=el.dataset[k]; return o; }', li)
        idv = li.get_attribute('id')
        download = li.query_selector('.button__download')
        anchor = li.query_selector('a')
        meta = li.query_selector('.media-content__meta-time')
        def attrs(el):
            if not el:
                return {}
            a = {}
            for name in page.evaluate('(el) => el.getAttributeNames()', el):
                a[name] = el.get_attribute(name)
            return a
        item = {
            'index': idx,
            'li_id': idv,
            'li_dataset': data,
            'li_classes': li.get_attribute('class'),
            'download_attrs': attrs(download),
            'download_href': download.get_attribute('href') if download else None,
            'anchor_attrs': attrs(anchor),
            'anchor_href': anchor.get_attribute('href') if anchor else None,
            'meta_attrs': attrs(meta),
            'meta_title': meta.get_attribute('title') if meta else None,
            'meta_text': page.evaluate('(el) => el.innerText.trim()', meta) if meta else None,
            'outer_html': page.evaluate('(el) => el.outerHTML', li)[:1000],
        }
        results.append(item)
    return results


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    history = []
    for run in range(2):
        page.goto('https://fastdl.app/en2/instagram-anonymously-viewer', timeout=60000)
        page.wait_for_selector('#search-form-input', timeout=30000)
        page.fill('#search-form-input', 'israel_bidur')
        try:
            page.click('#searchFormButton', timeout=5000)
        except Exception:
            pass
        try:
            page.wait_for_selector('.profile-media-list__item, .user-info', timeout=30000)
        except TimeoutError:
            pass
        network = []
        def handle_request(request):
            network.append({'type':'request','url':request.url,'method':request.method,'resource_type':request.resource_type,'post_data':request.post_data or None})
        def handle_response(response):
            try:
                network.append({'type':'response','url':response.url,'status': response.status,'headers': dict(response.headers), 'request_url': response.request.url})
            except Exception as e:
                network.append({'type':'response','url':response.url,'status':None,'error':str(e)})
        page.on('request', handle_request)
        page.on('response', handle_response)
        page.wait_for_timeout(8000)
        items = collect(page)
        history.append({'run': run+1, 'url': page.url, 'items_count': len(items), 'items': items, 'network_len': len(network), 'network': network[:80]})
        if run == 0:
            page.reload(timeout=60000)
            page.wait_for_timeout(5000)
    browser.close()
    out = Path('playwright_israel_bidur.json')
    out.write_text(json.dumps(history, indent=2, ensure_ascii=False))
    print(out)
