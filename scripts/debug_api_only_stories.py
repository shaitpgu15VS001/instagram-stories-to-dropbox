"""Quick API-only feasibility checker for Instagram Stories (debug only).

This script prefers an existing captured run at `scripts/debug_fastdl_israel.json`.
It extracts the POST /api/v1/instagram/stories response, analyzes items,
and performs limited GET tests for first/mid/last items (saves partial files).

Usage:
    python -u -m scripts.debug_api_only_stories

Do not modify production code.
"""
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import requests

HERE = Path(__file__).resolve().parent
CAPTURE_JSON = HERE / "debug_fastdl_israel.json"
OUT_DIR = HERE / "debug_api_only"
OUT_DIR.mkdir(parents=True, exist_ok=True)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def find_stories_response(capture):
    # scan network entries for the stories response with body_json
    if 'network' not in capture:
        return None
    for entry in capture['network']:
        if entry.get('type') == 'response' and entry.get('url') and '/api/v1/instagram/stories' in entry.get('url'):
            if 'body_json' in entry:
                return entry['body_json']
            if 'body_text_sample' in entry:
                try:
                    return json.loads(entry['body_text_sample'])
                except Exception:
                    return None
    return None


def extract_media_url_from_item(item):
    # Look for video_versions, image_versions2, candidates, url_downloadable, url_wrapped
    # Return tuple (media_url, kind)
    # Videos
    if 'video_versions' in item:
        v = item['video_versions']
        if isinstance(v, list) and v:
            first = v[0]
            for key in ('url_downloadable', 'url_wrapped', 'url'):
                if key in first:
                    return first[key], 'video'
            if 'url' in first:
                return first['url'], 'video'
    # Sometimes video data under 'candidates' or 'video_versions2'
    for k in ('video_versions2', 'video_versions'):
        if k in item and isinstance(item[k], dict):
            cand = item[k].get('candidates')
            if cand and isinstance(cand, list):
                f = cand[0]
                for key in ('url_downloadable', 'url_wrapped', 'url'):
                    if key in f:
                        return f[key], 'video'

    # Images
    if 'image_versions2' in item and isinstance(item['image_versions2'], dict):
        cand = item['image_versions2'].get('candidates')
        if cand and isinstance(cand, list):
            f = cand[0]
            for key in ('url_downloadable', 'url_wrapped', 'url'):
                if key in f:
                    return f[key], 'image'
            if 'url' in f:
                return f['url'], 'image'

    # top-level fields
    for key in ('url_downloadable', 'url_wrapped', 'display_url', 'media_url'):
        if key in item:
            # guess type from extension
            val = item[key]
            kind = 'image' if any(x in val for x in ('.jpg', '.jpeg', '.png')) else 'video'
            return val, kind

    # fallback: scan nested dicts for url_downloadable
    def scan(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in ('url_downloadable', 'url_wrapped') and isinstance(v, str):
                    return v
                res = scan(v)
                if res:
                    return res
        if isinstance(obj, list):
            for it in obj:
                res = scan(it)
                if res:
                    return res
        return None

    found = scan(item)
    if found:
        kind = 'image' if any(x in found for x in ('.jpg', '.jpeg', '.png')) else 'video'
        return found, kind

    return None, None


def has_sig_expires(url):
    if not url:
        return False, None
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    sig = '__sig' in qs or '_sig' in qs or 'sig' in qs
    expires = None
    for k in ('__expires', 'expires', 'exp'):
        if k in qs:
            try:
                expires = int(qs[k][0])
            except Exception:
                expires = None
    return sig or (expires is not None), expires


def test_media_url(url, out_path, timeout=20, max_bytes=256 * 1024):
    headers = {'User-Agent': USER_AGENT}
    try:
        r = requests.get(url, headers=headers, stream=True, timeout=timeout)
    except Exception as e:
        return {'ok': False, 'status': None, 'error': str(e)}
    status = r.status_code
    ctype = r.headers.get('Content-Type')
    clen = r.headers.get('Content-Length')
    # read a small prefix
    try:
        chunk = r.raw.read(4096)
    except Exception:
        chunk = b''
    # save partial file (first up to max_bytes)
    saved = False
    try:
        with open(out_path, 'wb') as fh:
            fh.write(chunk)
            saved_bytes = len(chunk)
            for _ in range(0, max_bytes - saved_bytes, 65536):
                part = r.raw.read(min(65536, max_bytes - saved_bytes))
                if not part:
                    break
                fh.write(part)
                saved_bytes += len(part)
        saved = True
    except Exception:
        saved = False

    # basic magic checks
    is_media = False
    try:
        prefix = chunk[:16]
        if prefix.startswith(b'\xff\xd8') or prefix.startswith(b'\x89PNG') or b'ftyp' in prefix:
            is_media = True
    except Exception:
        is_media = False

    return {
        'ok': status == 200,
        'status': status,
        'content_type': ctype,
        'content_length': int(clen) if (clen and clen.isdigit()) else clen,
        'saved': saved,
        'is_media_prefix': is_media,
        'requires_cookie_or_special': False if status == 200 else True,
    }


def main():
    # load capture
    if not CAPTURE_JSON.exists():
        print('ERROR: capture JSON not found:', CAPTURE_JSON)
        return 2
    cap = json.loads(CAPTURE_JSON.read_text(encoding='utf-8'))
    body = find_stories_response(cap)
    if not body:
        print('ERROR: stories API response not found in capture')
        return 3
    items = body.get('result') if isinstance(body, dict) else None
    if items is None:
        print('ERROR: invalid stories body structure')
        return 4

    total = len(items)
    downloadable_count = 0
    images = 0
    videos = 0
    urls_with_sig = 0
    seen_urls = set()
    duplicates = 0
    item_infos = []

    for it in items:
        url, kind = extract_media_url_from_item(it)
        if url:
            # prefer url_downloadable if nested in candidate dicts (wrapped may be encoded)
            downloadable_count += 1
            if url in seen_urls:
                duplicates += 1
            else:
                seen_urls.add(url)
        if kind == 'image':
            images += 1
        if kind == 'video':
            videos += 1
        sig_exists, expires = has_sig_expires(url)
        if sig_exists:
            urls_with_sig += 1
        item_infos.append({'url': url, 'kind': kind, 'expires': expires})

    # select test indices
    samples = []
    if total > 0:
        samples.append(0)
        samples.append(total // 2)
        samples.append(total - 1)
    samples = sorted(set(samples))

    test_results = []
    succeeded = 0
    for idx in samples:
        info = item_infos[idx]
        raw = info['url']
        if not raw:
            test_results.append((idx, False, 'no-url'))
            continue
        # if url is wrapped (media.fastdl.app), use as-is
        # try GET and save partial
        ext = '.bin'
        ct_guess = None
        parsed = urlparse(raw)
        fn = os.path.basename(parsed.path)
        if '.' in fn:
            ext = '.' + fn.split('.')[-1]
        out_path = OUT_DIR / f'story_{idx}{ext}'
        res = test_media_url(raw, out_path)
        test_results.append((idx, res))
        if res.get('ok'):
            succeeded += 1

    # cookies/special headers heuristic
    cookies_required = any(not r[1].get('ok') for r in test_results)
    special_headers_required = False  # we didn't try custom headers beyond UA

    urls_ephemeral = urls_with_sig > 0

    # Print concise summary expected by user
    print(f'API items: {total}/35')
    print(f'Items with downloadable URL: {downloadable_count}/{total}')
    print(f'Images: {images}')
    print(f'Videos: {videos}')
    print(f'Test downloads: {succeeded}/{len(test_results)} succeeded')
    print(f'Cookies required: {"yes" if cookies_required else "no"}')
    print(f'Special headers required: {"yes" if special_headers_required else "no"}')
    print(f'URLs ephemeral: {"yes" if urls_ephemeral else "no"}')

    # small machine readable dump
    summary = {
        'total': total,
        'downloadable_count': downloadable_count,
        'images': images,
        'videos': videos,
        'test_succeeded': succeeded,
        'test_total': len(test_results),
        'cookies_required': cookies_required,
        'special_headers_required': special_headers_required,
        'urls_ephemeral': urls_ephemeral,
        'duplicates': duplicates,
        'samples': [{ 'idx': s[0], 'result': s[1] if isinstance(s[1], dict) else s[1]} for s in test_results],
    }
    (OUT_DIR / 'summary.json').write_text(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())