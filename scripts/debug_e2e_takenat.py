#!/usr/bin/env python3
"""End-to-end local check: FastDL API -> parse_stories -> StoryDownloader mapping -> filename generation

Usage:
  python scripts/debug_e2e_takenat.py [path/to/stories_response.json]

Writes files into tmp_e2e_stories/<username>/
"""
import sys, os, json, shutil
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.fastdl_api import FastDLStoriesAPI
from src.story_downloader import StoryDownloader

ART = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / 'debug_output' / 'fastdl_media_test' / 'run4' / 'stories_response.json'
if not ART.exists():
    print('artifact not found:', ART); raise SystemExit(2)

# load payload (same helper as debug script)
with open(ART, 'r', encoding='utf-8') as f:
    data = json.load(f)
sr = data.get('stories_response') or data
body = None
if isinstance(sr, dict):
    body = sr.get('body_text') or sr.get('body_text_sample') or sr.get('body')
if body and isinstance(body, str):
    try:
        payload = json.loads(body)
    except Exception:
        payload = sr
else:
    payload = data

api = FastDLStoriesAPI()
parsed = api.parse_stories(payload)
print('parse_stories -> normalized items:', len(parsed))
# check taken_at present in raw
taken_vals = []
for it in parsed:
    raw = it.get('raw') or {}
    ta = raw.get('taken_at')
    if ta:
        taken_vals.append(int(ta))

unique_taken = sorted(set(taken_vals))
print('unique taken_at count:', len(unique_taken))
# print first 5 unique human-readable
from datetime import datetime, timezone
for v in unique_taken[:5]:
    print(' -', v, datetime.fromtimestamp(int(v), tz=timezone.utc).strftime('%d.%m.%Y, %H:%M:%S'))

if len(unique_taken) < 3:
    print('ERROR: fewer than 3 distinct taken_at values found in API payload')

# Monkeypatch FastDLStoriesAPI.fetch_stories to return parsed (simulate API)
orig_fetch = FastDLStoriesAPI.fetch_stories

def fake_fetch(self, username):
    return parsed

FastDLStoriesAPI.fetch_stories = fake_fetch

# Prepare StoryDownloader and temp output dir
tmp = Path('tmp_e2e_stories')
if tmp.exists():
    shutil.rmtree(tmp)
sd = StoryDownloader(output_dir=tmp)

try:
    normalized = sd._fetch_story_urls('erevtov')
    print('story_downloader._fetch_story_urls ->', len(normalized), 'items')
    # count non-None t
    t_count = sum(1 for s in normalized if s.get('t'))
    print('items with t (not None):', t_count)
    if t_count < 3:
        print('ERROR: fewer than 3 items have t populated')

    # Now download files (will use browser-context and write into tmp)
    print('Downloading up to 6 items (to limit network):')
    to_dl = normalized[:6]
    out_dir = tmp / 'erevtov'
    out_dir.mkdir(parents=True, exist_ok=True)
    results = sd._download_files(to_dl, out_dir, 'erevtov')
    print('downloaded count:', len(results))
    filenames = [r['path'].name for r in results]
    print('filenames:')
    for fn in filenames:
        print(' -', fn)
    # check uniqueness
    if len(set(filenames)) >= 3:
        print('OK: at least 3 distinct filenames')
    else:
        print('ERROR: filenames collision detected')

    # Verify each filename timestamp matches the t value
    matches = []
    for s, res in zip(to_dl, results):
        t = s.get('t')
        fn = res['path'].name
        # extract timestamp substring between username- and extension
        ts = fn.replace('erevtov-', '')
        ts = ts.rsplit('.', 1)[0]
        matches.append((t, ts, fn))
    print('Filename vs t samples:')
    for m in matches[:6]:
        print(' t=', m[0], ' -> filename_ts=', m[1], ' file=', m[2])

finally:
    # restore
    FastDLStoriesAPI.fetch_stories = orig_fetch
    sd._close_browser_context()

print('done')
