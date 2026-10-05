import pathlib, re
html = pathlib.Path('scripts/debug_output/viewsocials_probe/01_storynavigation_initial_final.html').read_text(encoding='utf-8')
scripts = re.findall(r'<script[^>]*src="([^"]+)"', html)
print(scripts)
inline = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
for i,s in enumerate(inline[:5]):
    snippet = s[:2000].replace('\n',' ')
    print(f'--- inline {i} len {len(s)}')
    print(snippet[:2000])
# search for any vue data
m = re.search(r'userName|instagramUserId|50879', html)
if m:
    idx = m.start()
    print(html[idx-800:idx+1200][:2000])
