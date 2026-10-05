import json, pathlib, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from urllib.parse import urlparse
p=pathlib.Path('scripts/debug_output/insacret_probe/01_insacret_network.json')
data=json.loads(p.read_text(encoding='utf-8'))
out_lines=[]
for e in data:
    url=e.get('url','')
    if 'insacret.org' in url:
        out_lines.append(f"{e.get('type'):8} {e.get('method'):4} {url[:800]}  {e.get('status','')}")
        if e.get('type')=='response' and e.get('body_snippet'):
            bs=e['body_snippet']
            if 'story' in bs.lower() or 'israel_bidur' in bs.lower():
                out_lines.append("  BODY story snippet: "+ bs[:4000].replace('\n',' ').replace('\r',' ')[:3000])
        out_lines.append("---")
# also check all responses with json
out_lines.append("\n=== JSON responses ===")
for e in data:
    if e.get('type')=='response':
        ct=e.get('headers',{}).get('content-type','').lower()
        if 'json' in ct:
            out_lines.append(f"{e['method']} {e['url'][:800]} {e['status']}")
            out_lines.append("  snack: "+ (e.get('body_snippet') or '')[:3000].replace('\n',' ').replace('\r',' ')[:2000])
            out_lines.append("---")
# check for any graphql/api
out_lines.append("\n=== POTENTIAL API ===")
for e in data:
    url=e.get('url','').lower()
    if any(k in url for k in ['/api','/ajax','graphql','story','media','instagram']):
        out_lines.append(f"{e.get('type')} {e.get('method')} {e.get('url')[:800]}")
        if e.get('body_snippet'):
            out_lines.append("  snippet: "+ e['body_snippet'][:3000].replace('\n',' ').replace('\r',' ')[:2000])
pathlib.Path('scripts/debug_output/insacret_probe/analysis_output.txt').write_text("\n".join(out_lines), encoding='utf-8')
print("written analysis_output.txt")
