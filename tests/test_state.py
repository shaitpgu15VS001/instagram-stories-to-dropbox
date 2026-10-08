import os
import tempfile

from src.state_manager import StateManager


def test_state_save_and_reload():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        sm = StateManager(state_path=path)
        assert not sm.is_uploaded("alice", "id1")
        sm.mark_uploaded(username="alice", story_id="id1", filename="f1.jpg", dropbox_path="/Instagram/2026-01-01/alice/f1.jpg")
        sm.save()

        sm2 = StateManager(state_path=path)
        assert sm2.is_uploaded("alice", "id1")
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def test_state_restarts_cleanly_when_uploaded_files_is_malformed(tmp_path):
    p = tmp_path / "state.json"
    p.write_text('{"version": 1, "uploaded_files": null}', encoding="utf-8")

    sm = StateManager(state_path=str(p))

    assert sm.state["version"] == 1
    assert sm.state["uploaded_files"] == {}
    assert not sm.is_uploaded("alice", "id1")

    sm.mark_uploaded(username="alice", story_id="id1", filename="f1.jpg", dropbox_path="/Instagram/2026-01-01/alice/f1.jpg")
    sm.save()

    reloaded = StateManager(state_path=str(p))
    assert reloaded.is_uploaded("alice", "id1")


def test_second_run_skips_everything_first_run_uploaded(tmp_path, monkeypatch):
    """סימולציית שתי הרצות עם State אמיתי: השנייה לא מעלה כלום."""
    from src import main
    from src.story_downloader import StoryDownloader

    items = [
        {"u": "https://fr1.anon-viewer.com/media2.php?media=https%3A%2F%2Fcdn%2Fs1_n.jpg", "ta": None, "txt": "5 minutes ago"},
        {"u": "https://fr2.anon-viewer.com/media2.php?media=https%3A%2F%2Fcdn%2Fs2_n.jpg", "ta": None, "txt": "2 hours ago"},
        {"u": "https://fr3.anon-viewer.com/media2.php?media=https%3A%2F%2Fcdn%2Fs3.mp4", "ta": None, "txt": "1 hours ago"},
    ]
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 100
    mp4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00" + b"\x00" * 100

    def fake_fetch(self, username):
        return [dict(it) for it in items]

    def fake_dl(self, url, timeout_seconds=60):
        if url.endswith(".mp4") or "/s3.mp4" in url:
            return {"content": mp4, "content_type": "video/mp4", "final_url": url, "status": 200}
        return {"content": jpeg, "content_type": "image/jpeg", "final_url": url, "status": 200}

    monkeypatch.setattr(StoryDownloader, "_fetch_story_urls", fake_fetch)
    monkeypatch.setattr(StoryDownloader, "_download_media_via_browser_context", fake_dl)
    monkeypatch.setattr("time.sleep", lambda s: None)

    uploads = []

    class Uploader:
        def get_folder_path_for_date(self, today, folder_name):
            return "dest/" + folder_name

        def upload_file(self, local_file, dropbox_path):
            uploads.append(dropbox_path)
            return True

    state_path = str(tmp_path / "state.json")

    # הרצה 1
    sd1 = StoryDownloader(output_dir=tmp_path / "s1")
    st1 = StateManager(state_path=state_path)
    r1 = main.process_user("u1", sd1, Uploader(), st1, force_redownload=False, folder_name="u1")
    assert r1["uploaded"] == 3
    assert len(uploads) == 3
    st1.save()

    # הרצה 2 — תהליך חדש עם אותו קובץ state
    uploads.clear()
    sd2 = StoryDownloader(output_dir=tmp_path / "s2")
    st2 = StateManager(state_path=state_path)
    r2 = main.process_user("u1", sd2, Uploader(), st2, force_redownload=False, folder_name="u1")
    assert r2["uploaded"] == 0
    assert uploads == []
    assert r2["status"] == "NO_NEW_STORIES"


