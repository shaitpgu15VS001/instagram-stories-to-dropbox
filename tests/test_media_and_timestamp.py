import json
import tempfile
from pathlib import Path
from src.fastdl_api import FastDLStoriesAPI
from src.story_downloader import format_taken_at_for_filename, _is_jpeg, _is_mp4


def test_parse_prefers_video():
    # Construct a minimal API response with both image_versions2 and video_versions
    body = {
        "result": [
            {
                "id": "1",
                "image_versions2": {"candidates": [{"url": "https://example.com/thumb.jpg", "url_wrapped": "https://media.fastdl.app/get?uri=https%3A%2F%2Fexample.com%2Fthumb.jpg"}]},
                "video_versions": [{"url": "https://example.com/video.mp4", "url_wrapped": "https://media.fastdl.app/get?uri=https%3A%2F%2Fexample.com%2Fvideo.mp4"}],
            }
        ]
    }
    items = FastDLStoriesAPI.parse_stories(body)
    assert isinstance(items, list) and len(items) == 1
    it = items[0]
    assert it.get('kind') == 'video'
    # Ensure chosen URL is the video wrapped URL (contains .mp4)
    assert '.mp4' in (it.get('u') or '').lower()


def test_format_taken_at_for_filename_jerusalem():
    # 2026-08-14 11:30:00 Asia/Jerusalem -> unix timestamp
    # Build a timestamp from known local time and compare formatting
    import datetime
    from zoneinfo import ZoneInfo

    dt = datetime.datetime(2026, 8, 14, 11, 30, 0, tzinfo=ZoneInfo('Asia/Jerusalem'))
    ts = int(dt.timestamp())
    s = format_taken_at_for_filename(ts)
    assert s == '2026-08-14_11-30-00'


def test_content_signature_checks():
    # JPEG signature
    jpeg = b"\xff\xd8\xff\xe0" + b"0" * 100
    assert _is_jpeg(jpeg)
    assert not _is_mp4(jpeg)

    # MP4 with ftyp in header
    mp4 = b"\x00\x00\x00\x18ftyp" + b"isom" + b"0" * 200
    assert _is_mp4(mp4)
    assert not _is_jpeg(mp4)
