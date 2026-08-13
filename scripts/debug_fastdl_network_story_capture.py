"""Temporary proof-of-concept: capture the real FastDL stories API response via Playwright.

This script intentionally does not modify production code and is limited to diagnostics.
It opens the live FastDL page, inputs the target username, and captures the real
browser-generated Stories API request/response from the network layer.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

VIEWER_URL = "https://fastdl.app/en2/instagram-anonymously-viewer"
USERNAME = "israel_bidur"
STORIES_API_URL = "https://api-wh.fastdl.app/api/v1/instagram/stories"
OUTPUT_DIR = Path("scripts")
OUTPUT_DIR.mkdir(exist_ok=True)


def find_value(obj: Any, key: str) -> List[Any]:
    """Return all values found under a given key recursively."""
    out: List[Any] = []

    def walk(node: Any):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key:
                    out.append(v)
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return out


def extract_media_urls(obj: Any) -> List[str]:
    """Try to extract media URLs from a captured JSON object without assuming a schema."""
    urls: List[str] = []
    seen = set()

    queue: List[Any] = [obj]
    while queue:
        current = queue.pop(0)
        if isinstance(current, dict):
            for k, v in current.items():
                if isinstance(v, (dict, list)):
                    queue.append(v)
                elif isinstance(v, str):
                    if v.startswith('http://') or v.startswith('https://'):
                        if v not in seen:
                            seen.add(v)
                            urls.append(v)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    queue.append(item)
                elif isinstance(item, str) and (item.startswith('http://') or item.startswith('https://')):
                    if item not in seen:
                        seen.add(item)
                        urls.append(item)
    return urls


def count_story_items(payload: Any) -> int:
    if isinstance(payload, dict):
        for key in ("result", "stories", "items", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                return len(val)
            if isinstance(val, dict):
                nested = val.get("result")
                if isinstance(nested, list):
                    return len(nested)
    elif isinstance(payload, list):
        return len(payload)
    return 0


def find_story_collection_path(payload: Any) -> Optional[str]:
    """Find the first likely story collection path dynamically."""
    if isinstance(payload, dict):
        for key in ("result", "stories", "items", "data"):
            if isinstance(payload.get(key), list):
                return f"$.{key}"
            if isinstance(payload.get(key), dict):
                nested = payload[key].get("result")
                if isinstance(nested, list):
                    return f"$.{key}.result"
        for k, v in payload.items():
            if isinstance(v, dict):
                path = find_story_collection_path(v)
                if path:
                    return f"$.{k}.{path[2:]}" if path.startswith("$.") else f"$.{k}.{path}"
            elif isinstance(v, list):
                if v and all(isinstance(i, dict) for i in v):
                    return f"$.{k}"
    elif isinstance(payload, list):
        if payload and all(isinstance(i, dict) for i in payload):
            return "$"
    return None


def summarize_url_domains(urls: Iterable[str]) -> List[str]:
    domains = []
    seen = set()
    for u in urls:
        try:
            d = urlparse(u).netloc.lower()
        except Exception:
            continue
        if d and d not in seen:
            seen.add(d)
            domains.append(d)
    return domains


def wait_for_search_ui(page):
    page.wait_for_selector('#search-form-input', state='visible', timeout=30000)
    page.wait_for_timeout(500)


def close_overlays(page):
    page.evaluate(
        """
        () => {
            const selectors = ['.fc-dialog-overlay', '.fc-consent-root', '.overlay', '.modal', '.cookie-banner', '.fc__dialog', '.fc-cookie-banner', '[role=dialog]'];
            for (const selector of selectors) {
                document.querySelectorAll(selector).forEach(el => el.remove());
            }
        }
        """
    )


def click_if_present(page, selectors: List[str]):
    for sel in selectors:
        try:
            page.click(sel, timeout=3000)
            return True
        except Exception:
            pass
    return False


def run_single_probe(run_id: int) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        'run_id': run_id,
        'request_captured': False,
        'response_captured': False,
        'http_status': None,
        'json_parsed': False,
        'story_count': 0,
        'media_url_count': 0,
        'media_url_domains': [],
        'json_path': None,
        'response_file': None,
        'request_file': None,
        'error': None,
    }

    request_capture = OUTPUT_DIR / f'debug_fastdl_network_request_run{run_id}.json'
    response_capture = OUTPUT_DIR / f'debug_fastdl_network_response_run{run_id}.json'
    result['request_file'] = str(request_capture)
    result['response_file'] = str(response_capture)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 900},
            locale='en-US',
        )
        page = context.new_page()
        page.set_default_timeout(60000)

        captured_request: Optional[Dict[str, Any]] = None
        captured_response: Optional[Dict[str, Any]] = None

        def on_request(request):
            nonlocal captured_request
            if request.url.startswith(STORIES_API_URL):
                captured_request = {
                    'url': request.url,
                    'method': request.method,
                    'headers': dict(request.headers),
                    'post_data': request.post_data or None,
                    'timestamp': int(time_ms()) if False else None,
                }
                result['request_captured'] = True
                request_capture.write_text(json.dumps(captured_request, ensure_ascii=False, indent=2), encoding='utf-8')

        def on_response(response):
            nonlocal captured_response
            if response.url.startswith(STORIES_API_URL):
                result['response_captured'] = True
                text = None
                try:
                    text = response.text()
                except Exception as exc:
                    text = None
                    result['error'] = f'response.text error: {exc}'

                parsed = None
                if isinstance(text, str):
                    try:
                        parsed = json.loads(text)
                        result['json_parsed'] = True
                    except Exception:
                        parsed = None
                        result['json_parsed'] = False

                result['http_status'] = response.status
                captured_response = {
                    'url': response.url,
                    'status': response.status,
                    'headers': dict(response.headers),
                    'body_text': text,
                    'json': parsed,
                }
                response_capture.write_text(json.dumps(captured_response, ensure_ascii=False, indent=2), encoding='utf-8')

        page.on('request', on_request)
        page.on('response', on_response)

        try:
            page.goto(VIEWER_URL, wait_until='domcontentloaded', timeout=60000)
            wait_for_search_ui(page)
            close_overlays(page)
            page.fill('#search-form-input', USERNAME)
            page.press('#search-form-input', 'Enter')
            page.wait_for_timeout(2500)
            close_overlays(page)

            for sel in ['button.tabs-component__button', '.tabs-component__button', '[data-tab="stories"]', 'button:has-text("Stories")']:
                try:
                    page.locator(sel).first.wait_for(state='visible', timeout=20000)
                    break
                except Exception:
                    pass

            found_tab = False
            for selector in ['button.tabs-component__button', '.tabs-component__button', '[data-tab="stories"]', 'button:has-text("Stories")']:
                try:
                    loc = page.locator(selector)
                    for i in range(loc.count()):
                        el = loc.nth(i)
                        txt = el.inner_text()
                        if 'story' in txt.lower():
                            el.click()
                            found_tab = True
                            break
                    if found_tab:
                        break
                except Exception:
                    pass

            page.wait_for_timeout(4000)
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('script')).some(s => (s.src || '').includes('/js/app.js')) || true",
                timeout=20000,
            )

            deadline = 30
            for _ in range(deadline * 2):
                if result['response_captured']:
                    break
                page.wait_for_timeout(500)

            if not result['response_captured']:
                result['error'] = 'No Stories API response captured within timeout.'

            if result['response_captured'] and captured_response and isinstance(captured_response.get('json'), (dict, list)):
                payload = captured_response['json']
                result['story_count'] = count_story_items(payload)
                json_path = find_story_collection_path(payload)
                result['json_path'] = json_path
                urls = extract_media_urls(payload)
                result['media_url_count'] = len(urls)
                result['media_url_domains'] = summarize_url_domains(urls)

        except Exception as exc:
            result['error'] = str(exc)
        finally:
            browser.close()

    return result


def time_ms() -> int:
    import time
    return int(time.time() * 1000)


def main():
    parser = argparse.ArgumentParser(description='Temporary Playwright capture of FastDL Stories API response.')
    parser.add_argument('--run-id', type=int, default=1)
    args = parser.parse_args()

    run = run_single_probe(args.run_id)
    print(json.dumps(run, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
