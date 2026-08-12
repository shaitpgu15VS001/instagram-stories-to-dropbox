import base64
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


def run_session(headless: bool):
    label = 'headless' if headless else 'headed'
    results = {
        'label': label,
        'headless': headless,
        'response_saved': False,
        'response_file': None,
        'json_file': None,
        'response_metadata': None,
        'page_events': [],
        'error': None,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=['--no-sandbox', '--disable-dev-shm-usage'])
        context = browser.new_context(user_agent=USER_AGENT, viewport={'width': 1280, 'height': 1200}, locale='en-US')
        page = context.new_page()

        def on_response(response):
            try:
                if 'api/v1/instagram/stories' not in response.url:
                    return
                body_bytes = response.body()
                filename = OUTPUT_DIR / f'debug_fastdl_story_api_raw_full_{label}.bin'
                filename.write_bytes(body_bytes)
                results['response_saved'] = True
                results['response_file'] = str(filename)
                results['response_metadata'] = {
                    'url': response.url,
                    'status': response.status,
                    'headers': {k: v for k, v in response.headers.items()},
                    'body_length': len(body_bytes),
                }
                try:
                    text = body_bytes.decode('utf-8')
                    json_path = OUTPUT_DIR / f'debug_fastdl_story_api_raw_full_{label}.json'
                    json_path.write_text(text, encoding='utf-8')
                    results['json_file'] = str(json_path)
                except UnicodeDecodeError:
                    results['response_metadata']['decode_error'] = 'utf-8 decode failed'
            except Exception as exc:
                results['error'] = f'on_response failed: {exc}'

        page.on('response', on_response)

        try:
            page.goto(VIEWER_URL, timeout=60000, wait_until='domcontentloaded')
            page.wait_for_selector('#search-form-input', timeout=30000)
            page.fill('#search-form-input', USERNAME)
            page.evaluate("() => { const overlays = Array.from(document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root, .overlay, .modal, .cookie-banner')); for (const el of overlays) el.remove(); }")
            page.click('#searchFormButton', timeout=30000, force=True)
            page.wait_for_timeout(6000)
            page.evaluate(
                "() => { const bs = Array.from(document.querySelectorAll('button.tabs-component__button')); for (const b of bs) { if (b.innerText.toLowerCase().includes('stories')) { b.scrollIntoView(); b.click(); return true; } } return false; }"
            )
            page.wait_for_selector('.profile-media-list__item', timeout=30000)
            page.wait_for_timeout(3000)
            results['page_events'].append({'step': 'loaded', 'url': page.url, 'title': page.title(), 'webdriver': page.evaluate('() => navigator.webdriver'), 'story_items': page.evaluate("() => document.querySelectorAll('.profile-media-list__item').length")})
        except TimeoutError as exc:
            results['error'] = f'timeout: {exc}'
        except Exception as exc:
            results['error'] = f'page flow error: {exc}'
        finally:
            browser.close()

    path = OUTPUT_DIR / f'debug_fastdl_story_api_raw_full_{label}_meta.json'
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    return results


def main():
    all_results = []
    for headless in [True, False]:
        try:
            all_results.append(run_session(headless))
        except Exception as exc:
            all_results.append({'label': 'headless' if headless else 'headed', 'error': str(exc)})
    summary_path = OUTPUT_DIR / 'debug_fastdl_story_api_raw_full_summary.json'
    summary_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'wrote {summary_path}')


if __name__ == '__main__':
    main()
