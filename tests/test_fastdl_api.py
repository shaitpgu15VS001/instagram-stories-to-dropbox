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


def test_parse_empty_result_returns_empty_list():
    items = FastDLStoriesAPI.parse_stories({"result": []})
    assert items == []


def test_parse_result_with_story_returns_normalized_items():
    body = {
        "result": [
            {
                "url_downloadable": "https://media.fastdl.app/get?uri=https%3A%2F%2Fscontent.cdninstagram.com%2Fv%2Fstory.mp4&__sig=ABC",
                "taken_at": 1786200000,
                "pk": "123",
            }
        ]
    }
    items = FastDLStoriesAPI.parse_stories(body)
    assert isinstance(items, list) and len(items) == 1
    assert items[0]["kind"] == "video"
    assert ".mp4" in items[0]["u"]


def test_parse_falls_back_to_data_when_result_is_none():
    body = {
        "result": None,
        "data": [
            {
                "url_downloadable": "https://media.fastdl.app/get?uri=https%3A%2F%2Fscontent.cdninstagram.com%2Fv%2Fstory.jpg&__sig=ABC",
                "pk": "456",
            }
        ],
    }
    items = FastDLStoriesAPI.parse_stories(body)
    assert isinstance(items, list) and len(items) == 1
    assert items[0]["kind"] == "image"


def test_parse_unusable_response_returns_none():
    assert FastDLStoriesAPI.parse_stories({}) is None


def test_parse_message_only_returns_none():
    assert FastDLStoriesAPI.parse_stories({"message": "no stories"}) is None


def test_empty_result_is_no_stories_success(tmp_path, monkeypatch, capsys):
    from src.story_downloader import StoryDownloader

    monkeypatch.setattr(FastDLStoriesAPI, "fetch_stories", lambda self, username, timeout=10: [])
    sd = StoryDownloader(output_dir=tmp_path / "stories")

    urls = sd._fetch_story_urls("nouser")
    assert urls == []

    res = sd.download_stories("nouser")
    assert res["success"] is True
    assert res["error"] is None
    out = capsys.readouterr().out
    assert "אין סטוריז פעילים כרגע" in out
    assert "E-FDL-001" not in out
    assert "api_error" not in out
