import time
from urllib.parse import urlencode

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from src.story_downloader import StoryDownloader, MAX_RETRIES


def test_playwright_timeout_triggers_retries(tmp_path, monkeypatch):
    sd = StoryDownloader(output_dir=tmp_path)

    calls = {"count": 0}

    def broken_download(url, timeout_seconds=60):
        calls["count"] += 1
        raise PlaywrightTimeout("timeout")

    # monkeypatch the internal downloader to always timeout
    monkeypatch.setattr(sd, "_download_media_via_browser_context", broken_download)

    stories = [{"u": "https://media.fastdl.app/get?" + urlencode({"__sig": "abc", "__expires": int(time.time()) + 3600})}]

    downloaded = sd._download_files(stories, tmp_path / "out", "tester")

    # Ensure no files downloaded
    assert downloaded == []
    # Ensure attempts == MAX_RETRIES
    assert calls["count"] == MAX_RETRIES
