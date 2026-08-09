import os
import tempfile
from pathlib import Path

from src.story_downloader import StoryDownloader


def test_preserve_existing_files(tmp_path, monkeypatch):
    base = tmp_path / "workspace"
    stories_root = base / "stories"
    stories_root.mkdir(parents=True)

    user = "testuser"
    user_dir = stories_root / user
    user_dir.mkdir(parents=True)
    existing = user_dir / "existing.jpg"
    existing.write_bytes(b"data")

    sd = StoryDownloader(output_dir=stories_root)

    # Monkeypatch network fetch to avoid Playwright
    monkeypatch.setattr(StoryDownloader, "_fetch_story_urls", lambda self, u: [])

    res = sd.download_stories(user, folder_name=user)
    assert res["success"] is True
    files = res["files"]
    assert any(p.name == "existing.jpg" for p in files)
