import json, pathlib
p=pathlib.Path('scripts/debug_output/viewsocials_probe/01_storynavigation_initial_network.json')
data=json.loads(p.read_text(encoding='utf-8'))
# find POST to get-user-last-stories request detail
for e in data:
    if e.get('type')=='request' and 'get-user-last-stories' in e.get('url',''):
        print(json.dumps(e, ensure_ascii=False, indent=2)[:8000])
        print("---")
    if e.get('type')=='response' and 'get-user-last-stories' in e.get('url',''):
        print(json.dumps({k:v for k,v in e.items() if k!='body_snippet'}, ensure_ascii=False, indent=2)[:3000])
        if 'body_snippet' in e:
            print(e['body_snippet'][:3000])
# also check initial GET to user page for set-cookie and meta csrf
for e in data:
    if e.get('type')=='response' and e.get('url','').endswith('/user/israel_bidur'):
        print("\n=== USER PAGE RESPONSE HEADERS ===")
        print(json.dumps(e.get('headers',{}), indent=2)[:3000])
        print(e.get('body_snippet','')[:2000] if 'body_snippet' in e else 'no snippet')

# check for token in page dumps
import re
html_path=pathlib.Path('scripts/debug_output/viewsocials_probe/01_storynavigation_initial_final.html')
html=html_path.read_text(encoding='utf-8')
# search csrf
for m in re.finditer(r'csrf|xsrf|token', html, re.I):
    snippet=html[m.start()-300:m.end()+600]
    print("\ncsrf snippet:", snippet[:1000].replace('\n',' '))
    break
# search meta
for m in re.finditer(r'<meta[^>]*csrf[^>]*>', html, re.I):
    print(m.group(0)[:1000])
for m in re.finditer(r'XSRF', html):
    print(html[m.start()-500:m.end()+500][:1200])

# check cookies file
import pathlib as pl
cookies_path=pathlib.Path('scripts/debug_output/viewsocials_probe/01_storynavigation_initial_cookies.json')
if cookies_path.exists():
    print("\n=== COOKIES ===")
    print(cookies_path.read_text(encoding='utf-8')[:3000])
