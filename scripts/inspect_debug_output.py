import json
from pathlib import Path
p = Path('scripts/debug_fastdl_israel.json')
if not p.exists():
    raise SystemExit('missing file')
with p.open('r', encoding='utf-8') as f:
    d = json.load(f)
print('username', d.get('username'))
print('runs', len(d.get('runs', [])))
for run in d['runs']:
    print('---', run['step'])
    if 'state' in run:
        print('state items:')
        for k, v in run['state'].items():
            print(' ', k, v)
    if 'data' in run:
        v = run['data']
        print('url', v.get('url'))
        print('title', v.get('title'))
        print('user_agent', v.get('user_agent'))
        print('webdriver', v.get('webdriver'))
        print('media_count', v.get('media_count'))
        print('scrollY', v.get('scrollY'), 'docHeight', v.get('docHeight'), 'innerHeight', v.get('innerHeight'))
        print('count_texts', len(v.get('count_texts', [])))
        print('candidates.items_count', v.get('candidates', {}).get('items_count'))
        print('candidates.visible_count', v.get('candidates', {}).get('visible_count'))
        print('candidates items len', len(v.get('candidates', {}).get('items', [])))
        if len(v.get('candidates', {}).get('items', [])) > 1:
            print(' first item href', v['candidates']['items'][1].get('download_href'))
            print(' first item classes', v['candidates']['items'][1].get('classes'))
