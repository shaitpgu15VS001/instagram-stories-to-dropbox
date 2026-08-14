#!/usr/bin/env python3
"""Live E2E diagnostic: open FastDL viewer, trigger Stories API via Playwright,
parse stories, download media via browser-context, and report detailed results.

Usage:
  python scripts/debug_live_e2e.py <username>

Notes: Diagnostic-only script. Does not modify production code.
"""
import sys, os, time, json
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.fastdl_api import FastDLStoriesAPI
from src.story_downloader import StoryDownloader
from datetime import datetime, timezone

USERNAME = (sys.argv[1] if len(sys.argv) > 1 else 'erevtov').strip().lstrip('@')
OUT_ROOT = Path('tmp_live_e2e')
OUT_ROOT.mkdir(exist_ok=True)
OUT_DIR = OUT_ROOT / USERNAME
if OUT_DIR.exists():
    # keep previous runs for inspection; do not delete automatically
    pass
else:
    OUT_DIR.mkdir(parents=True)

print('Starting live E2E diagnostic for username=', USERNAME)
api = FastDLStoriesAPI()

print('Triggering live Playwright flow to capture Stories API...')
items = api._fetch_stories_with_playwright(USERNAME, timeout=20)
if not items:
    print('ERROR: No items returned from live API bridge')
    sys.exit(2)

print('API returned items:', len(items))
# examine taken_at values
taken_vals = []
for it in items:
    raw = it.get('raw') or {}
    ta = raw.get('taken_at')
    if ta:
        taken_vals.append(int(ta))

unique_taken = sorted(set(taken_vals))
print('Unique taken_at count:', len(unique_taken))
for v in unique_taken[:10]:
    print(' -', v, datetime.fromtimestamp(int(v), tz=timezone.utc).strftime('%d.%m.%Y, %H:%M:%S'))

if len(unique_taken) < 3:
    print('Warning: fewer than 3 unique taken_at found; continuing anyway')

# prepare downloader helper but we'll perform downloads using its browser-context method
sd = StoryDownloader(output_dir=OUT_ROOT)
# ensure browser context started
sd._ensure_browser_context()

results = []
max_dl = 6
count = 0
for it in items:
    if count >= max_dl:
        break
    u = it.get('u')
    raw = it.get('raw') or {}
    ta = raw.get('taken_at')
    t_formatted = None
    if isinstance(ta, (int, float)):
        t_formatted = datetime.fromtimestamp(int(ta), tz=timezone.utc).strftime('%d.%m.%Y, %H:%M:%S')
    entry = {'u': u, 't': t_formatted, 'raw': raw}
    # attempt download via browser context
    rec = {'taken_at': ta, 't': t_formatted, 'url': u, 'http_status': None, 'file_created': False, 'path': None, 'size': None, 'note': ''}
    try:
        media = sd._download_media_via_browser_context(u, timeout_seconds=60)
        rec['http_status'] = media.get('status')
        ct = (media.get('content_type') or '').lower()
        url_lower = u.lower() if u else ''
        if 'video' in ct or '.mp4' in url_lower or 'video/mp4' in ct:
            ext = '.mp4'
        elif 'png' in ct or url_lower.endswith('.png'):
            ext = '.png'
        elif 'webp' in ct or url_lower.endswith('.webp'):
            ext = '.webp'
        elif 'jpeg' in ct or 'jpg' in ct or url_lower.endswith(('.jpg', '.jpeg')):
            ext = '.jpg'
        else:
            ext = '.bin'
        # compute ts
        ts = None
        if t_formatted:
            try:
                d, mo, y_h = t_formatted.split('.', 2)
            except Exception:
                pass
            # better convert via parsing
            from datetime import datetime
            try:
                dt = datetime.strptime(t_formatted, '%d.%m.%Y, %H:%M:%S')
                ts = dt.strftime('%Y-%m-%d_%H-%M-%S')
            except Exception:
                ts = None
        # fallback to __expires
        if not ts and u:
            import re
            m = re.search(r'__expires=(\d+)', u)
            if m:
                try:
                    ts = datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')
                except Exception:
                    ts = None
        if not ts:
            ts = f'unknown_{int(time.time())}'
        filename = f"{USERNAME}-{ts}{ext}"
        p = OUT_DIR / filename
        p.write_bytes(media['content'])
        rec['file_created'] = True
        rec['path'] = str(p)
        rec['size'] = p.stat().st_size
        results.append(rec)
        count += 1
        print(f"Downloaded: {filename} status={rec['http_status']} size={rec['size']}")
    except Exception as exc:
        rec['note'] = str(exc)
        results.append(rec)
        print('Download failed for url=', u, 'exc=', exc)
        count += 1

# close context
sd._close_browser_context()

# summary print
print('\nDetailed results:')
for r in results:
    taken_h = datetime.fromtimestamp(int(r['taken_at']), tz=timezone.utc).strftime('%d.%m.%Y, %H:%M:%S') if r['taken_at'] else None
    print(json.dumps({
        'taken_at': r['taken_at'], 'taken_human': taken_h, 't': r['t'], 'url': r['url'], 'http_status': r['http_status'], 'file_created': r['file_created'], 'path': r['path'], 'size': r['size'], 'note': r['note']
    }, ensure_ascii=False))

print('\nResults directory:', OUT_DIR)
print('Done')
