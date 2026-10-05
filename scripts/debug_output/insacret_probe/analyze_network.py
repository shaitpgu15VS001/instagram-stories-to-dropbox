import json, pathlib
from urllib.parse import urlparse
p=pathlib.Path('scripts/debug_output/insacret_probe/01_insacret_network.json')
data=json.loads(p.read_text(encoding='utf-8'))
# full dump of insacret.org requests/responses
for e in data:
    url=e.get('url','')
    if 'insacret.org' in url:
        print(f"{e.get('type'):8} {e.get('method'):4} {url[:500]}  {e.get('status','')}")
        if e.get('type')=='response' and e.get('body_snippet'):
            bs=e['body_snippet']
            # look for stories keywords
            if 'story' in bs.lower() or 'israel_bidur' in bs.lower():
                print("  BODY contains story:", bs[:3000].replace('\n',' ')[:2000])
        print("---")
# also check all responses with json
print("\n=== JSON responses ===")
for e in data:
    if e.get('type')=='response':
        ct=e.get('headers',{}).get('content-type','').lower()
        if 'json' in ct:
            print(e['method'], e['url'][:500], e['status'])
            print("  snack:", (e.get('body_snippet') or '')[:2000].replace('\n',' ')[:1500])
            print("---")
# check for any graphql/api
print("\n=== POTENTIAL API ===")
for e in data:
    url=e.get('url','').lower()
    if any(k in url for k in ['/api','/ajax','graphql','story','media','instagram']):
        print(e.get('type'), e.get('method'), e.get('url')[:600])
        if e.get('body_snippet'):
            print("  snippet:", e['body_snippet'][:2000].replace('\n',' ')[:1500])
