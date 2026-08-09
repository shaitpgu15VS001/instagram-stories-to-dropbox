import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import base64

path = Path('playwright_israel_bidur.json')
data = json.loads(path.read_text(encoding='utf-8'))

def decode_efg(value):
    s = value.replace('-', '+').replace('_', '/')
    s += '=' * ((4 - len(s) % 4) % 4)
    try:
        return base64.b64decode(s).decode('utf-8')
    except Exception as e:
        return f'ERROR: {e}'

for run_idx, run in enumerate(data, start=1):
    print(f'RUN {run_idx}: items={len(run["items"])}, network={len(run["network"])})')
    for item in run['items']:
        href = item['download_href'] or ''
        qs = parse_qs(urlparse(href).query)
        uri = qs.get('uri', [''])[0]
        uri_decoded = unquote(uri)
        uri_parts = urlparse(uri_decoded)
        uri_qs = parse_qs(uri_parts.query)
        efgs = uri_qs.get('efg', [])
        stable_id = Path(uri_parts.path).name
        print('INDEX', item['index'])
        print('  meta_title', item.get('meta_title'))
        print('  meta_text', item.get('meta_text'))
        print('  uri_path', uri_parts.path)
        print('  stable_id_candidate', stable_id)
        print('  uri_query_keys', sorted(uri_qs.keys()))
        print('  uri_id_like_keys', [k for k in uri_qs if k in ('shortcode','pk','id','media_id','story_id')])
        print('  sig', qs.get('__sig', [''])[0])
        print('  expires', qs.get('__expires', [''])[0])
        print('  efg_count', len(efgs))
        for efg in efgs:
            print('   efg raw', efg)
            print('   efg decoded', decode_efg(efg))
        print()
    print(' = network entries = ')
    for entry in run['network']:
        url = entry.get('url','')
        if 'fastdl.app/get' in url or 'instagram' in url or 'graphql' in url or 'api' in url:
            t = entry.get('type')
            if t == 'request':
                print(' ', t, entry.get('method'), url)
            else:
                print(' ', t, entry.get('status'), url)
    print('---')

# Compare runs by stable_id_candidate and meta_title
print('\nCOMPARE RUNS BY stable_id_candidate:')
if len(data) >= 2:
    run1 = data[0]['items']
    run2 = data[1]['items']
    for a, b in zip(run1, run2):
        href_a = a['download_href'] or ''
        href_b = b['download_href'] or ''
        path_a = Path(urlparse(unquote(parse_qs(urlparse(href_a).query).get('uri', [''])[0])).path).name
        path_b = Path(urlparse(unquote(parse_qs(urlparse(href_b).query).get('uri', [''])[0])).path).name
        same = path_a == path_b
        print('INDEX', a['index'], 'same_path', same, 'path_a', path_a, 'path_b', path_b)
