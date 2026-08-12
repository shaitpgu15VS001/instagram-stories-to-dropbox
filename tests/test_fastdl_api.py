import json
from pathlib import Path

from src.fastdl_api import FastDLStoriesAPI


def find_stories_body(capture_path: Path):
    cap = json.loads(capture_path.read_text(encoding='utf-8'))
    if 'network' in cap:
        for entry in cap['network']:
            if entry.get('type') == 'request' and entry.get('url') and '/api/v1/instagram/stories' in entry.get('url'):
                # in these captures the response body is stored nearby as a response entry
                # try to find the corresponding response object
                pass
    # fallback: scan for a response entry with url
    for entry in cap.get('network', []):
        if entry.get('type') == 'response' and entry.get('url') and '/api/v1/instagram/stories' in entry.get('url'):
            if 'body_json' in entry:
                return entry['body_json']
            if 'body' in entry:
                try:
                    return json.loads(entry['body'])
                except Exception:
                    return None
    return None


def test_parse_capture_returns_items():
    cap_file = Path('scripts/debug_fastdl_israel.json')
    assert cap_file.exists(), 'capture file missing for test'
    body = find_stories_body(cap_file)
    assert body is not None, 'stories response not found in capture'
    items = FastDLStoriesAPI.parse_stories(body)
    assert isinstance(items, list)
    # in our authoritative capture we expect 35 items
    assert len(items) == 35
