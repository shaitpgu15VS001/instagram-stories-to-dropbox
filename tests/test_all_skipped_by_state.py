import tempfile
from pathlib import Path

from src.story_downloader import StoryDownloader
from src.state_manager import StateManager


def test_all_stories_filtered_by_state(tmp_path, monkeypatch):
    # Setup state with pre-uploaded IDs for user 'alice'
    state_path = tmp_path / "state.json"
    sm = StateManager(state_path=str(state_path))
    pre_ids = ["/p/1.jpg", "/p/2.jpg"]
    for i, pid in enumerate(pre_ids, start=1):
        sm.mark_uploaded(username="alice", story_id=f"legacy{i}", filename=f"f{i}.jpg", dropbox_path=f"/x/f{i}.jpg", pre_download_id=pid)
    sm.save()

    # Create downloader and attach the state
    dl = StoryDownloader(output_dir=tmp_path / "stories")
    dl.state_manager = sm

    # Simulate download_urls as would be returned by _fetch_story_urls
    download_urls = []
    for pid in ["/p/1.jpg", "/p/2.jpg"]:
        pid_no_lead = pid.lstrip('/')
        download_urls.append({
            "u": f"https://fastdl.app/download?uri=https%3A%2F%2Finstagram.com%2F{pid_no_lead}",
            "t": "1.1.2026, 12:00:00",
            "txt": "1 minute",
        })

    # Monkeypatch _fetch_story_urls to return our simulated items
    monkeypatch.setattr(StoryDownloader, "_fetch_story_urls", lambda self, u: download_urls)

    res = dl.download_stories("alice")
    assert res["success"] is True
    assert res["files"] == []
    assert res["error"] is None
