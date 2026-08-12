import json
from pathlib import Path
p = Path('scripts/debug_fastdl_israel.json')
with p.open('r', encoding='utf-8') as f:
    d = json.load(f)

for run in d.get('runs', []):
    if 'data' not in run:
        continue
    print('STEP', run['step'])
    data = run['data']
    items = data.get('candidates', {}).get('items', [])
    print('items', len(items))
    for idx, item in enumerate(items):
        if item.get('classes') != 'profile-media-list__item':
            print('non-item', idx, item.get('classes'))
    print('-----')
    for idx, item in enumerate(items[:10]):
        print('item', idx, 'href', item.get('download_href'), 'meta', item.get('meta_text'))
        html = item.get('outer_html', '')
        if 'profile-media-list__item' not in html:
            print('  outer missing class?')
    print('-----')
    print('body text length', len(data.get('raw_text','')))
    print('raw_text snippet:', repr(data.get('raw_text','')[:800]))
    print('-----')
    if run['step'] == 'initial':
        print('first 100 selectors in raw_text maybe count 42?')
        text = data.get('raw_text','')
        if '42' in text:
            print('found 42 in raw_text')
        else:
            print('did not find 42 in raw_text')
    print()
