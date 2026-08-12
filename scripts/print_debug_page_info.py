import json
from pathlib import Path

p = Path('scripts/debug_fastdl_israel.json')
if not p.exists():
    raise SystemExit('missing file')
with p.open('r', encoding='utf-8') as f:
    d = json.load(f)
for run in d.get('runs', []):
    print('STEP', run.get('step'))
    if 'state' in run:
        print('state:', run['state'])
    if 'data' in run:
        data = run['data']
        print(' media_count', data.get('media_count'))
        print(' scrollY', data.get('scrollY'), 'innerHeight', data.get('innerHeight'), 'docHeight', data.get('docHeight'), 'bodyHeight', data.get('bodyHeight'))
        print(' selectors:')
        for sel in ['.profile-media-list__item', '.media-content--story', '.button__download', '.media-content__image', '.media-content__meta-time', '.tabs-component__button', '.profile-media-list', '.media-content__info']:
            info = data.get(sel)
            if info is not None:
                print('  ', sel, 'count=', info.get('count'), 'sample=', info.get('sample'))
        print('scrollables count', len(data.get('scrollables', [])))
        for scroll in data.get('scrollables', [])[:10]:
            print('  scrollable', scroll)
        print('count_texts', len(data.get('count_texts', [])))
        print('candidates items_count', data.get('candidates', {}).get('items_count'))
        print('candidates visible_count', data.get('candidates', {}).get('visible_count'))
        print('candidates items len', len(data.get('candidates', {}).get('items', [])))
        for item in data.get('candidates', {}).get('items', [])[:5]:
            print('   item', item.get('classes'), item.get('download_href'), item.get('meta_text'))
        print('---')
    print()
