#!/usr/bin/env python3
import json
import sys, os
from pathlib import Path

# ensure project root on sys.path so we can import src modules
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DATA = Path('scripts/debug_fastdl_israel.json')
if not DATA.exists():
    print('Missing artifact:', DATA)
    raise SystemExit(1)

with DATA.open('r', encoding='utf-8') as fh:
    j = json.load(fh)

# The capture artifact may embed the API response under nested entries
# (e.g. entries with 'body_json' containing {'result': [...]}); find the
# largest 'result' list we can locate.
def find_result_lists(obj):
    found = []
    if isinstance(obj, dict):
        if 'body_json' in obj and isinstance(obj['body_json'], dict) and isinstance(obj['body_json'].get('result'), list):
            found.append(obj['body_json']['result'])
        for v in obj.values():
            found.extend(find_result_lists(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(find_result_lists(v))
    return found

results_lists = find_result_lists(j)
if not results_lists:
    # fallback: top-level shape
    res = j.get('result') or j.get('data') or j
else:
    # pick the largest result list (most likely the stories payload)
    res = max(results_lists, key=lambda x: len(x))

# import parser
from src.fastdl_api import FastDLStoriesAPI
parse = FastDLStoriesAPI.parse_stories
norm = parse({'result': res})

# build index of normalized items by pk if present
norm_by_pk = {}
for item in norm:
    raw = item.get('raw') or {}
    pk = raw.get('pk') or raw.get('id') or raw.get('media_id')
    if pk:
        norm_by_pk[str(pk)] = item

count = 0
print('Searching for items with video_versions present...')
for it in res:
    if not isinstance(it, dict):
        continue
    if 'video_versions' in it and it.get('video_versions'):
        count += 1
        print('\n--- ITEM', count, '---')
        pk = it.get('pk') or it.get('id') or it.get('media_id')
        print('pk:', pk)
        ta = it.get('taken_at') or it.get('taken_at_timestamp') or it.get('taken_at')
        print('taken_at (unix):', ta)
        dt_utc = datetime.fromtimestamp(int(ta), tz=timezone.utc)
        dt_jer = dt_utc.astimezone(ZoneInfo('Asia/Jerusalem'))
        print('UTC:', dt_utc.isoformat(), 'Asia/Jerusalem:', dt_jer.isoformat())
        print('\n-- image_versions2 candidates (first) --')
        iv2 = it.get('image_versions2') or {}
        c = iv2.get('candidates') if isinstance(iv2, dict) else None
        if c and isinstance(c, list) and len(c)>0:
            print('candidate[0]:')
            for k in ('url','url_wrapped','url_downloadable','width','height'):
                if k in c[0]:
                    print(' ',k,':',c[0].get(k))
        else:
            print(' None')
        print('\n-- video_versions (first) --')
        vv = it.get('video_versions')
        if vv and isinstance(vv, list) and len(vv)>0:
            print('video[0]:')
            for k in ('url','url_wrapped','url_downloadable','width','height','type'):
                if k in vv[0]:
                    print(' ',k,':',vv[0].get(k))
        else:
            print(' None')

        # what parser chooses
        picked = None
        if pk and str(pk) in norm_by_pk:
            picked = norm_by_pk[str(pk)]
        else:
            # try to match by taken_at
            for ni in norm:
                raw = ni.get('raw') or {}
                if raw.get('taken_at') == ta:
                    picked = ni
                    break
        print('\n-- parser normalized result for this item (if found) --')
        if picked:
            print('normalized kind:', picked.get('kind'))
            print('normalized url:', picked.get('u'))
            # show lower level check: is the chosen url from image or video?
            chosen = picked.get('u') or ''
            if '.mp4' in chosen or 'video' in chosen:
                print('parser chose VIDEO (mp4)')
            else:
                print('parser chose IMAGE/thumbnail')
        else:
            print('No normalized parser entry matched for this pk')

        count_limit = 5
        if count >= count_limit:
            break

print('\nDone')
