import json
from pathlib import Path

path = Path(__file__).parent / 'debug_fastdl_story_api_raw_full_headless.json'
text = path.read_text(encoding='utf-8')
data = json.loads(text)
print('type', type(data).__name__)
print('keys', list(data.keys()))
result = data.get('result')
print('result type', type(result).__name__ if result is not None else None)
print('result len', len(result) if isinstance(result, list) else 'no-list')
print('has_next', data.get('has_next'))
print('cursor', data.get('cursor'))
print('limit', data.get('limit'))
if isinstance(result, list) and result:
    print('first item keys', list(result[0].keys())[:40])
    print('first item sample id', result[0].get('id'))
    print('first item sample media_type', result[0].get('media_type'))
    print('first item sample pk', result[0].get('pk'))
else:
    print('no result items or result not list')
