"""Try obtaining cookies via GET to the viewer page, then POST to Stories API with same session."""
import requests

VIEWER_URL = 'https://fastdl.app/instagram-anonymously-viewer'
STORIES_URL = 'https://api-wh.fastdl.app/api/v1/instagram/stories'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}

s = requests.Session()
s.headers.update(HEADERS)

print('GET viewer page...')
r = s.get(VIEWER_URL, timeout=20)
print('GET status', r.status_code)
print('cookies after GET:', s.cookies.get_dict())

payload = {'username': 'israel_bidur'}
print('POST stories...')
r2 = s.post(STORIES_URL, json=payload, headers={'Referer': VIEWER_URL, 'Origin': 'https://fastdl.app'}, timeout=20)
print('POST status', r2.status_code)
print('content-type', r2.headers.get('Content-Type'))
print('body snippet:', r2.text[:400])
