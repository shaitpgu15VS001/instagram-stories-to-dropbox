import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from playwright.sync_api import sync_playwright, TimeoutError
import base64

ACCOUNTS = [
    'israel_bidur',
    'erevtov',
    'harabanit',
    'kan_reshetb',
]

OUTPUT_FILE = Path('playwright_fastdl_audit.json')


def collect_attrs(page, el):
    if not el:
        return {}
    names = page.evaluate('(element) => element.getAttributeNames()', el)
    return {name: el.get_attribute(name) for name in names}


def decode_efg(raw):
    if not raw:
        return None
    s = raw.replace('-', '+').replace('_', '/')
    s += '=' * ((4 - len(s) % 4) % 4)
    try:
        decoded = base64.b64decode(s)
        text = decoded.decode('utf-8', errors='replace')
    except Exception as exc:
        return {'raw': raw, 'error': str(exc)}
    parsed = None
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = text
    return {'raw': raw, 'decoded': text, 'parsed': parsed}


def normalize_uri_data(href):
    if not href:
        return {
            'raw': None,
            'uri': None,
            'uri_decoded': None,
            'uri_path': None,
            'uri_filename': None,
            'uri_qs': {},
            'uri_params': {},
            'efg': None,
        }
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    uri = qs.get('uri', [''])[0]
    uri_decoded = unquote(uri) if uri else None
    uri_parts = urlparse(uri_decoded) if uri_decoded else None
    uri_qs = parse_qs(uri_parts.query) if uri_parts else {}
    efg_raw = uri_qs.get('efg', [])
    efg = [decode_efg(x) for x in efg_raw] if efg_raw else []
    return {
        'raw': href,
        'sig': qs.get('__sig', [''])[0],
        'expires': qs.get('__expires', [''])[0],
        'uri': uri,
        'uri_decoded': uri_decoded,
        'uri_path': uri_parts.path if uri_parts else None,
        'uri_filename': Path(uri_parts.path).name if uri_parts else None,
        'uri_qs': {k: v for k, v in uri_qs.items()},
        'uri_params': {k: v for k, v in uri_qs.items()},
        'efg': efg,
    }


def collect_story_data(page, li, idx):
    meta = li.query_selector('.media-content__meta-time')
    download = li.query_selector('.button__download')
    anchor = li.query_selector('a')
    preview = li.query_selector('img.media-content__image')
    dataset = page.evaluate('(el) => { const o={}; for (const k in el.dataset) o[k]=el.dataset[k]; return o; }', li)
    return {
        'index': idx,
        'li_id': li.get_attribute('id'),
        'li_classes': li.get_attribute('class'),
        'li_dataset': dataset,
        'download_attrs': collect_attrs(page, download),
        'download_href': download.get_attribute('href') if download else None,
        'anchor_attrs': collect_attrs(page, anchor),
        'anchor_href': anchor.get_attribute('href') if anchor else None,
        'meta_attrs': collect_attrs(page, meta),
        'meta_title': meta.get_attribute('title') if meta else None,
        'meta_text': page.evaluate('(el) => el.innerText.trim()', meta) if meta else None,
        'preview_src': preview.get_attribute('src') if preview else None,
        'preview_attrs': collect_attrs(page, preview),
        'outer_html': page.evaluate('(el) => el.outerHTML', li)[:2000],
    }


def collect_runs_for_account(account, page, runs=2):
    results = []
    current_network = []

    def handle_request(request):
        if current_network is not None:
            current_network.append({'type': 'request', 'url': request.url, 'method': request.method, 'resource_type': request.resource_type, 'post_data': request.post_data or None})

    def handle_response(response):
        if current_network is not None:
            try:
                current_network.append({'type': 'response', 'url': response.url, 'status': response.status, 'headers': dict(response.headers), 'request_url': response.request.url})
            except Exception as e:
                current_network.append({'type': 'response', 'url': response.url, 'status': None, 'error': str(e)})

    page.on('request', handle_request)
    page.on('response', handle_response)

    for run in range(runs):
        network = []
        current_network = network
        page.goto('https://fastdl.app/en2/instagram-anonymously-viewer', timeout=60000)
        page.wait_for_selector('#search-form-input', timeout=30000)
        page.fill('#search-form-input', account)
        page.keyboard.press('Enter')
        try:
            page.click('#searchFormButton', timeout=5000)
        except Exception:
            pass
        page.wait_for_selector('.profile-media-list__item, .user-info', timeout=30000)
        page.wait_for_timeout(8000)
        items = page.query_selector_all('.profile-media-list__item')
        story_items = []
        for idx, li in enumerate(items):
            story_items.append(collect_story_data(page, li, idx))
        results.append({
            'run': run + 1,
            'url': page.url,
            'items_count': len(story_items),
            'items': story_items,
            'network': network,
        })
        current_network = None
        if run == 0:
            page.reload(timeout=60000)
            page.wait_for_timeout(5000)
    return results


def analyze_account(account, raw_runs):
    analyses = []
    for run in raw_runs:
        items = []
        for item in run['items']:
            dh = normalize_uri_data(item['download_href'])
            ah = normalize_uri_data(item['anchor_href'])
            items.append({
                **item,
                'download_uri': dh,
                'anchor_uri': ah,
                'download_uri_same': dh['uri_path'] == ah['uri_path'] if dh['uri_path'] and ah['uri_path'] else False,
                'story_type': 'video' if dh['uri_filename'] and dh['uri_filename'].lower().endswith('.mp4') else 'image',
            })
        analyses.append({**run, 'items': items})
    return analyses


def match_items(run_a, run_b):
    matches = []
    unmatched_a = list(run_a)
    unmatched_b = list(run_b)
    for item_a in list(unmatched_a):
        best = None
        for item_b in unmatched_b:
            score = 0
            if item_a['meta_title'] and item_a['meta_title'] == item_b['meta_title']:
                score += 10
            if item_a['download_uri']['uri_path'] and item_a['download_uri']['uri_path'] == item_b['download_uri']['uri_path']:
                score += 20
            if item_a['download_uri']['uri_filename'] and item_a['download_uri']['uri_filename'] == item_b['download_uri']['uri_filename']:
                score += 5
            if item_a['meta_text'] and item_a['meta_text'] == item_b['meta_text']:
                score += 2
            if score > 0 and (best is None or score > best[0]):
                best = (score, item_b)
        if best is not None:
            _, item_b = best
            matches.append({'a': item_a, 'b': item_b})
            unmatched_a.remove(item_a)
            unmatched_b.remove(item_b)
    return matches, unmatched_a, unmatched_b


def summarize_matches(matches):
    summary = []
    for match in matches:
        a = match['a']
        b = match['b']
        summary.append({
            'meta_title': a['meta_title'],
            'meta_text': a['meta_text'],
            'story_type': a['story_type'],
            'uri_path_a': a['download_uri']['uri_path'],
            'uri_path_b': b['download_uri']['uri_path'],
            'uri_path_same': a['download_uri']['uri_path'] == b['download_uri']['uri_path'],
            'filename_a': a['download_uri']['uri_filename'],
            'filename_b': b['download_uri']['uri_filename'],
            'sig_a': a['download_uri']['sig'],
            'sig_b': b['download_uri']['sig'],
            'expires_a': a['download_uri']['expires'],
            'expires_b': b['download_uri']['expires'],
            'efg_a': a['download_uri']['efg'],
            'efg_b': b['download_uri']['efg'],
            'download_href_a': a['download_href'],
            'download_href_b': b['download_href'],
            'anchor_href_a': a['anchor_href'],
            'anchor_href_b': b['anchor_href'],
            'li_id_a': a['li_id'],
            'li_id_b': b['li_id'],
            'li_dataset_a': a['li_dataset'],
            'li_dataset_b': b['li_dataset'],
            'uri_qs_keys_a': sorted(a['download_uri']['uri_qs'].keys()),
            'uri_qs_keys_b': sorted(b['download_uri']['uri_qs'].keys()),
        })
    return summary


def account_summary(account, analyses):
    run1 = analyses[0]['items']
    run2 = analyses[1]['items']
    matches, unmatched1, unmatched2 = match_items(run1, run2)

    count_images = sum(1 for item in run1 if item['story_type'] == 'image')
    count_videos = sum(1 for item in run1 if item['story_type'] == 'video')

    return {
        'account': account,
        'run1_count': len(run1),
        'run2_count': len(run2),
        'images': count_images,
        'videos': count_videos,
        'matches': summarize_matches(matches),
        'unmatched_run1': [{'meta_title': i['meta_title'], 'uri_path': i['download_uri']['uri_path']} for i in unmatched1],
        'unmatched_run2': [{'meta_title': i['meta_title'], 'uri_path': i['download_uri']['uri_path']} for i in unmatched2],
        'uri_paths_run1': [i['download_uri']['uri_path'] for i in run1],
        'uri_paths_run2': [i['download_uri']['uri_path'] for i in run2],
    }


def main():
    audit = {'accounts': []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        for account in ACCOUNTS:
            raw_runs = collect_runs_for_account(account, page, runs=2)
            analyses = analyze_account(account, raw_runs)
            account_report = account_summary(account, analyses)
            audit['accounts'].append({
                'account': account,
                'runs': analyses,
                'summary': account_report,
            })
        browser.close()

    OUTPUT_FILE.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Wrote audit results to {OUTPUT_FILE}')


if __name__ == '__main__':
    main()
