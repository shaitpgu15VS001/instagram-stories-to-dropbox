import json
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

from playwright.sync_api import sync_playwright, TimeoutError

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
USERNAME = "israel_bidur"
OUTPUT = Path(__file__).resolve().parent / "debug_fastdl_israel.json"
SCREENSHOT_DIR = Path(__file__).resolve().parent / "debug_fastdl_israel_screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def normalize_uri(href):
    if not href:
        return None
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    uri = qs.get("uri", [""])[0]
    uri_decoded = unquote(uri) if uri else None
    return {
        "raw": href,
        "uri": uri,
        "uri_decoded": uri_decoded,
        "uri_path": urlparse(uri_decoded).path if uri_decoded else None,
    }


def collect_candidates(page):
    return page.evaluate("""
        () => {
            const rows = [];
            const items = Array.from(document.querySelectorAll('.profile-media-list__item'));
            rows.push({kind:'profile_media_list_item', count: items.length});
            for (const item of items) {
                const download = item.querySelector('.button__download');
                const meta = item.querySelector('.media-content__meta-time');
                const img = item.querySelector('img');
                const sources = Array.from(item.querySelectorAll('source')).map(s => s.src).filter(Boolean);
                const anchors = Array.from(item.querySelectorAll('a')).map(a => a.href).filter(Boolean);
                rows.push({
                    kind: 'item',
                    index: rows.length - 1,
                    classes: item.className,
                    download_href: download?.href || null,
                    download_class: download?.className || null,
                    download_attrs: download ? Array.from(download.getAttributeNames()).reduce((acc, name) => (acc[name] = download.getAttribute(name), acc), {}) : {},
                    anchor_hrefs: anchors,
                    meta_title: meta?.title || null,
                    meta_text: meta?.innerText?.trim() || null,
                    img_src: img?.src || null,
                    img_alt: img?.alt || null,
                    sources: sources,
                    outer_html: item.outerHTML.slice(0,2000),
                    bounding: item.getBoundingClientRect() ? {x: item.getBoundingClientRect().x, y: item.getBoundingClientRect().y, width: item.getBoundingClientRect().width, height: item.getBoundingClientRect().height} : null,
                });
            }
            const visible = Array.from(document.querySelectorAll('.profile-media-list__item')).filter(item => {
                const rect = item.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            }).length;
            const countSpan = Array.from(document.querySelectorAll('*')).filter(el => el.innerText && el.innerText.match(/\b42\b/)).map(el => ({tag: el.tagName, class: el.className, text: el.innerText.slice(0,200)}));
            return {
                items_count: items.length,
                visible_count: visible,
                count_text_candidates: countSpan,
                items: rows,
            };
        }
    """)


def collect_page_info(page):
    return page.evaluate("""
        () => {
            const res = {};
            const selectors = [
                '.profile-media-list__item',
                '.media-content--story',
                '.button__download',
                '.media-content__image',
                '.media-content__meta-time',
                '.tabs-component__button',
                '.profile-media-list',
                '.media-content__info',
            ];
            for (const sel of selectors) {
                const els = Array.from(document.querySelectorAll(sel));
                res[sel] = {count: els.length, sample: els.slice(0,3).map(el => ({tag: el.tagName, class: el.className, text: el.innerText?.trim().slice(0,120), href: el.href || null, src: el.src || null}))};
            }
            const scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
                const st = window.getComputedStyle(el);
                return ['auto','scroll'].includes(st.overflowY) || ['auto','scroll'].includes(st.overflowX);
            }).map(el => ({tag: el.tagName, class: el.className, overflowY: window.getComputedStyle(el).overflowY, overflowX: window.getComputedStyle(el).overflowX, scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight, bounding: el.getBoundingClientRect()}));
            const debug = {
                url: location.href,
                title: document.title,
                user_agent: navigator.userAgent,
                webdriver: navigator.webdriver,
                media_count: document.querySelectorAll('.profile-media-list__item').length,
                scrollY: window.scrollY || window.pageYOffset,
                innerHeight: window.innerHeight,
                docHeight: document.documentElement.scrollHeight,
                bodyHeight: document.body.scrollHeight,
                scrollables: scrollables.slice(0,10),
                raw_text: document.body.innerText.slice(0,2000),
            };
            return debug;
        }
    """)


def extract_global_state(page):
    return page.evaluate("""
        () => {
            const candidates = {};
            for (const key of Object.getOwnPropertyNames(window)) {
                if (key.toLowerCase().includes('story') || key.toLowerCase().includes('fastdl') || key.toLowerCase().includes('data')) {
                    try {
                        const value = window[key];
                        candidates[key] = typeof value === 'string' ? (value.length < 1000 ? value : value.slice(0,1000)) : (typeof value === 'object' ? (Array.isArray(value) ? value.slice(0,5) : Object.keys(value).slice(0,20)) : value);
                    } catch (e) {
                        candidates[key] = 'ERROR';
                    }
                }
            }
            return candidates;
        }
    """)


def find_count_text(page):
    return page.evaluate("""
        () => {
            const matches = [];
            const pattern = /\b42\b/;
            for (const el of Array.from(document.querySelectorAll('body *'))) {
                if (el.children.length === 0 && el.innerText && pattern.test(el.innerText)) {
                    matches.push({tag: el.tagName, class: el.className, text: el.innerText.trim().slice(0,200)});
                }
            }
            return matches.slice(0,20);
        }
    """)


def main():
    results = {
        "username": USERNAME,
        "view": VIEWER_URL,
        "runs": [],
        "network": [],
    }
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 1200}, locale="en-US")
        page = context.new_page()

        def on_request(request):
            try:
                post_data = None
                try:
                    post_data = request.post_data
                except Exception:
                    post_data = None
                results['network'].append({'type': 'request', 'url': request.url, 'method': request.method, 'resource_type': request.resource_type, 'post_data': post_data})
            except Exception:
                results['network'].append({'type': 'request', 'url': request.url, 'method': request.method, 'resource_type': request.resource_type})

        def on_response(response):
            entry = {'type': 'response', 'url': response.url, 'status': response.status, 'request_url': None}
            try:
                entry['request_url'] = response.request.url
            except Exception:
                entry['request_url'] = None
            # capture full body for stories endpoint and any JSON responses
            try:
                ct = response.headers.get('content-type', '') if hasattr(response, 'headers') else ''
                text = None
                json_body = None
                # try to read body if JSON or if URL matches stories
                if '/api/v1/instagram/stories' in (response.url or '') or 'application/json' in ct:
                    try:
                        text = response.text()
                        try:
                            json_body = response.json()
                        except Exception:
                            json_body = None
                    except Exception:
                        text = None
                if text is not None:
                    entry['body_text_sample'] = text if len(text) < 200000 else text[:200000]
                if json_body is not None:
                    entry['body_json'] = json_body
            except Exception:
                pass
            results['network'].append(entry)

        page.on('request', on_request)
        page.on('response', on_response)

        page.goto(VIEWER_URL, timeout=60000, wait_until='domcontentloaded')
        page.wait_for_selector('#search-form-input', timeout=30000, state='visible')
        page.screenshot(path=SCREENSHOT_DIR / '01_initial.png')
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
        page.wait_for_timeout(3000)
        page.screenshot(path=SCREENSHOT_DIR / '02_after_search.png')
        search_state = page.evaluate('''() => {
            const query = selector => {
                const els = Array.from(document.querySelectorAll(selector));
                return {count: els.length, visible: els.filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                }).length};
            };
            return {
                user_info: query('.user-info'),
                stories_tab: query('button.tabs-component__button'),
                media_items: query('.profile-media-list__item'),
                story_blocks: query('.media-content--story'),
                download_buttons: query('.button__download'),
                meta_time: query('.media-content__meta-time'),
            };
        }''')
        results['runs'].append({'step': 'after_search', 'state': search_state})
        page.screenshot(path=SCREENSHOT_DIR / '02_after_search_debug.png')
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
        page.wait_for_timeout(3000)
        page.screenshot(path=SCREENSHOT_DIR / '03_after_click_stories.png')

        page.wait_for_timeout(5000)
        page.screenshot(path=SCREENSHOT_DIR / '04_after_stories_ready.png')
        data0 = collect_page_info(page)
        data0['count_texts'] = find_count_text(page)
        data0['global_state'] = extract_global_state(page)
        data0['candidates'] = collect_candidates(page)
        results['runs'].append({'step': 'initial', 'data': data0})

        for scroll_index in range(1, 5):
            step = f'scroll_{scroll_index}'
            page.evaluate(
                """
                () => {
                    const items = document.querySelectorAll('.profile-media-list__item');
                    if (!items.length) return false;
                    items[items.length - 1].scrollIntoView({behavior: 'smooth', block: 'end'});
                    return true;
                }
                """
            )
            page.wait_for_timeout(3000)
            page.screenshot(path=SCREENSHOT_DIR / f'05_{step}.png')
            data = collect_page_info(page)
            data['count_texts'] = find_count_text(page)
            data['candidates'] = collect_candidates(page)
            data['scroll_position'] = page.evaluate('() => ({scrollY: window.scrollY, docHeight: document.documentElement.scrollHeight, bodyHeight: document.body.scrollHeight, innerHeight: window.innerHeight})')
            results['runs'].append({'step': step, 'data': data})

        browser.close()

    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print('saved', OUTPUT)


if __name__ == '__main__':
    main()
