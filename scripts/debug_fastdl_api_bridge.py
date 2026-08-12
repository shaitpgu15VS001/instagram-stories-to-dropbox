"""Stand-alone diagnostic helper: capture FastDL Stories API response through Playwright.

This script is intentionally isolated from production code.
It records the real browser-generated API request/response for `israel_bidur`.
"""
import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from playwright.sync_api import TimeoutError, sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USERNAME = "israel_bidur"
OUTPUT_DIR = Path("scripts")
OUTPUT_DIR.mkdir(exist_ok=True)
STORIES_API_PATH = "/api/v1/instagram/stories"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def clean_popups(page):
    page.evaluate(
        """
        () => {
            const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });
            document.querySelectorAll('button, input').forEach(el => {
                const style = window.getComputedStyle(el);
                if (style.pointerEvents === 'none' && el.closest('.fc-consent-root')) {
                    el.closest('.fc-consent-root')?.remove();
                }
            });
        }
        """
    )


def click_stories_tab(page):
    return page.evaluate(
        """
        () => {
            const buttons = Array.from(document.querySelectorAll('button.tabs-component__button'));
            for (const button of buttons) {
                if (button.innerText && button.innerText.toLowerCase().includes('stories')) {
                    button.scrollIntoView();
                    button.click();
                    return true;
                }
            }
            return false;
        }
        """
    )


def set_search_input_value(page, selector: str, value: str) -> bool:
    return page.evaluate(
        """
        (data) => {
            const input = document.querySelector(data.sel);
            if (!input) return false;
            input.focus();
            input.value = data.val;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return input.value === data.val;
        }
        """,
        {"sel": selector, "val": value},
    )


def extract_download_urls(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    urls = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidates = []
        if isinstance(item.get('image_versions2'), dict):
            candidates = item['image_versions2'].get('candidates', []) or []
        if isinstance(item.get('video_versions'), list):
            candidates = item['video_versions'] or candidates
        for key in ('url_downloadable', 'url_wrapped', 'url'):
            for c in candidates:
                if isinstance(c, dict) and key in c and isinstance(c[key], str):
                    urls.append({'url': c[key], 'kind': 'video' if 'video' in key or 'mp4' in c[key] else 'image'})
                    break
            if urls:
                break
        if not urls and any(k in item for k in ('url_downloadable', 'url_wrapped', 'url')):
            for key in ('url_downloadable', 'url_wrapped', 'url'):
                if key in item and isinstance(item[key], str):
                    kind = 'video' if 'mp4' in item[key] or 'video' in item[key].lower() else 'image'
                    urls.append({'url': item[key], 'kind': kind})
                    break
    return urls


def test_media_url(url: str) -> Dict[str, Any]:
    headers = {
        'User-Agent': USER_AGENT,
        'Accept': '*/*',
        'Referer': VIEWER_URL,
    }
    try:
        r = requests.get(url, headers=headers, stream=True, timeout=20)
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
    status = r.status_code
    ctype = r.headers.get('Content-Type')
    size = 0
    try:
        for chunk in r.iter_content(8192):
            if chunk:
                size += len(chunk)
                break
    except Exception:
        pass
    return {'ok': status == 200, 'status': status, 'content_type': ctype, 'size': size}


def run_bridge(run_id: int) -> Dict[str, Any]:
    run_output = {
        'run_id': run_id,
        'api_requests': [],
        'api_responses': [],
        'story_count': None,
        'download_urls': [],
        'test_results': [],
        'dom_count': None,
        'search_succeeded': False,
        'stories_tab_succeeded': False,
        'api_succeeded': False,
        'page_url': None,
        'page_title': None,
        'debug_resource_urls': [],
    }
    screenshot_prefix = OUTPUT_DIR / f'debug_fastdl_api_bridge_run{run_id}'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        try:
            context = browser.new_context(user_agent=USER_AGENT, viewport={'width': 1280, 'height': 900}, locale='en-US')
            page = context.new_page()
            page.set_default_timeout(60000)
            api_request_ids = set()

            def on_request(request):
                if STORIES_API_PATH in request.url and request.method == 'POST':
                    run_output['api_requests'].append({
                        'url': request.url,
                        'method': request.method,
                        'headers': dict(request.headers),
                        'post_data': request.post_data or None,
                    })
                    api_request_ids.add(request.timing.get('startTime', time.time()))

            def on_response(response):
                if STORIES_API_PATH in response.url and response.request.method == 'POST':
                    body_text = None
                    body_json = None
                    try:
                        body_text = response.text()
                    except Exception:
                        body_text = None
                    try:
                        body_json = response.json()
                    except Exception:
                        body_json = None
                    entry = {
                        'url': response.url,
                        'status': response.status,
                        'headers': dict(response.headers),
                        'body_text_sample': body_text[:2000] if isinstance(body_text, str) else None,
                        'body_json': body_json,
                    }
                    run_output['api_responses'].append(entry)

            page.on('request', on_request)
            page.on('response', on_response)
            page.goto(VIEWER_URL, wait_until='domcontentloaded')
            page.wait_for_selector('#search-form-input', state='visible', timeout=30000)
            clean_popups(page)
            page.wait_for_timeout(1000)
            page.wait_for_selector('#search-form-input', state='visible', timeout=30000)
            run_output['page_url'] = page.url
            run_output['page_title'] = page.title()
            page.screenshot(path=screenshot_prefix.with_name(f'{screenshot_prefix.name}_01_initial.png'))

            page.wait_for_timeout(500)
            page.evaluate("() => { const overlays = Array.from(document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .overlay, .modal, .cookie-banner, .fc__dialog, .fc-cookie-banner, [role=dialog]')); overlays.forEach(el => el.remove()); }")
            page.wait_for_timeout(500)
            input_ok = set_search_input_value(page, '#search-form-input', USERNAME)
            run_output['search_input_set'] = input_ok
            page.click('#searchFormButton', force=True, timeout=30000)
            page.wait_for_timeout(2500)
            clean_popups(page)
            page.wait_for_timeout(1000)
            page.screenshot(path=screenshot_prefix.with_name(f'{screenshot_prefix.name}_02_after_search.png'))

            try:
                page.wait_for_selector('button.tabs-component__button', state='visible', timeout=30000)
                run_output['search_succeeded'] = True
            except TimeoutError:
                run_output['search_succeeded'] = False

            if run_output['search_succeeded']:
                run_output['page_url'] = page.url
                run_output['page_title'] = page.title()
                run_output['stories_tab_succeeded'] = click_stories_tab(page)
                page.wait_for_timeout(2000)
                page.screenshot(path=screenshot_prefix.with_name(f'{screenshot_prefix.name}_03_after_stories_click.png'))

            if run_output['stories_tab_succeeded']:
                try:
                    page.wait_for_selector('.media-content--story', timeout=20000, state='visible')
                    page.wait_for_selector('.media-content__meta-time', timeout=20000, state='visible')
                except TimeoutError:
                    pass

            urls = page.evaluate(
                "() => Array.from(window.performance.getEntriesByType('resource')).map(r => r.name).filter(u => u.includes('/api/v1/instagram/')).slice(0, 50)"
            )
            run_output['debug_resource_urls'] = urls

            deadline = time.time() + 40
            while time.time() < deadline and not run_output['api_responses']:
                time.sleep(0.5)

            try:
                dom_count = page.evaluate("() => document.querySelectorAll('.profile-media-list__item').length")
                run_output['dom_count'] = dom_count
            except Exception:
                run_output['dom_count'] = None

            if run_output['api_responses']:
                resp = run_output['api_responses'][-1]
                body_json = resp.get('body_json')
                if isinstance(body_json, dict):
                    result = body_json.get('result')
                    run_output['story_count'] = len(result) if isinstance(result, list) else None
                    if isinstance(result, list) and result:
                        run_output['api_succeeded'] = resp.get('status') == 200
                        urls = []
                        duplicates = set()
                        for item in result:
                            if not isinstance(item, dict):
                                continue
                            for field in ('url_downloadable', 'url_wrapped', 'url'):
                                if field in item and isinstance(item[field], str):
                                    if item[field] not in duplicates:
                                        duplicates.add(item[field])
                                        kind = 'video' if 'video' in item[field].lower() or item[field].endswith('.mp4') else 'image'
                                        urls.append({'url': item[field], 'kind': kind})
                                    break
                            if 'image_versions2' in item and isinstance(item['image_versions2'], dict):
                                cands = item['image_versions2'].get('candidates') or []
                                if cands and isinstance(cands, list):
                                    first = cands[0]
                                    if isinstance(first, dict) and 'url_downloadable' in first:
                                        u = first['url_downloadable']
                                        if u not in duplicates:
                                            duplicates.add(u)
                                            urls.append({'url': u, 'kind': 'image'})
                        run_output['download_urls'] = urls
                        for sample in urls[:3]:
                            res = test_media_url(sample['url'])
                            run_output['test_results'].append({**sample, **res})

            save_path = OUTPUT_DIR / f'debug_fastdl_api_bridge_run{run_id}.json'
            save_path.write_text(json.dumps(run_output, indent=2, ensure_ascii=False), encoding='utf-8')
            return run_output
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_id', type=int, help='Run number for output file naming')
    args = parser.parse_args()
    result = run_bridge(args.run_id)
    print('run_id', result['run_id'])
    print('api_requests', len(result['api_requests']))
    print('api_responses', len(result['api_responses']))
    print('story_count', result['story_count'])
    print('dom_count', result['dom_count'])
    print('download_urls', len(result['download_urls']))
    print('test_results', [f"{r['kind']} {r['status']} size={r.get('size')}" for r in result['test_results']])
    if result['api_requests']:
        first = result['api_requests'][0]
        print('request_method', first['method'])
        print('request_payload_present', bool(first['post_data']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
