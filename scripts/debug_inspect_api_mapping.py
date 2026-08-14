#!/usr/bin/env python3
import sys, os, json
from pathlib import Path
p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "debug_output" / "fastdl_media_test" / "run4" / "stories_response.json"
if not p.exists():
    print('missing', p); raise SystemExit(2)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.fastdl_api import FastDLStoriesAPI
from datetime import datetime, timezone

with open(p, 'r', encoding='utf-8') as f:
    data = json.load(f)
# extract body if needed
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
items = api.parse_stories(payload)
print('parsed', len(items), 'items')
mapped = []
from datetime import timezone
for it in items:
    raw = it.get('raw') or {}
    ta = raw.get('taken_at')
    taken = None
    if isinstance(ta, (int,float)):
        dt = datetime.fromtimestamp(int(ta), tz=timezone.utc)
        taken = dt.strftime('%d.%m.%Y, %H:%M:%S')
    mapped.append({'u': it.get('u'), 't': taken, 'txt': None, 'pk': raw.get('pk')})

for i,m in enumerate(mapped[:10],1):
    print(i, m['pk'], 't=', m['t'], 'u__expires=', ('__expires=' + m['u'].split('__expires=')[-1]) if m['u'] and '__expires=' in m['u'] else None)

print('done')
