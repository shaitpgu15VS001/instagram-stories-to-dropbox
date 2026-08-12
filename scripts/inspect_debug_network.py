import json
from pathlib import Path
p = Path('scripts/debug_fastdl_israel.json')
if not p.exists():
    raise SystemExit('missing file')
with p.open('r', encoding='utf-8') as f:
    d = json.load(f)
net = d.get('network', [])
print('network entries', len(net))
counts = {'fastdl_story_api': 0, 'media_get': 0, 'others': 0}
for i, entry in enumerate(net, 1):
    url = entry.get('url', '')
    if 'api/v1/instagram/stories' in url:
        counts['fastdl_story_api'] += 1
    elif 'media.fastdl.app/get' in url:
        counts['media_get'] += 1
    else:
        counts['others'] += 1
print('counts', counts)
for i, entry in enumerate(net[:100], 1):
    if entry.get('type') == 'request' and ('api/v1/instagram/stories' in entry.get('url', '') or 'media.fastdl.app/get' in entry.get('url', '')):
        print(i, entry['method'], entry['url'])
