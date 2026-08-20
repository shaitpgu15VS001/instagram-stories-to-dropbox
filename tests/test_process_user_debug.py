import pathlib

from src import main, logger


def _make_fake_env(tmp_path):
    # create a sample downloaded file
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    f = files_dir / "story1.jpg"
    f.write_bytes(b"data")

    class FakeDownloader:
        def download_stories(self, username, folder_name=None):
            return {"success": True, "files": [f], "meta": {f.name: "pre1"}}

        def extract_story_id(self, name):
            return "storyid1"

    class FakeUploader:
        def get_folder_path_for_date(self, today, folder_name):
            return "dest"

        def upload_file(self, local_file, dropbox_path):
            return True

    class FakeState:
        def is_uploaded(self, username, story_id):
            return False

        def mark_uploaded(self, username, story_id, filename, dropbox_path, pre_download_id=None):
            return None

        def save(self):
            return None

        def get_stats(self):
            return {"total_uploaded": 0, "tracked_users": 0}

    return f, FakeDownloader(), FakeUploader(), FakeState()


def test_process_user_writes_user_markers_and_status_ok(tmp_path):
    lg = logger.logger
    debug_dir = tmp_path / "debug"
    lg.init_debug(debug_dir=str(debug_dir), run_id="test-run")

    f, downloader, uploader, state = _make_fake_env(tmp_path)

    stats = main.process_user("alice", downloader, uploader, state, force_redownload=False)
    assert stats["uploaded"] == 1

    content = (debug_dir / "debug_full.log").read_text(encoding="utf-8")
    assert "USER_START username=alice" in content
    assert "USER_FINISHED username=alice status=STORIES_FOUND" in content


def test_logger_write_failure_does_not_crash(tmp_path, monkeypatch):
    lg = logger.logger
    debug_dir = tmp_path / "debug"
    lg.init_debug(debug_dir=str(debug_dir), run_id="test-run")

    # Simulate a debug file object that raises on write
    class BrokenWriter:
        def write(self, text):
            raise OSError("disk full")

        def flush(self):
            pass

    # Replace underlying file handle with broken writer
    lg._debug_full_fh = BrokenWriter()

    # Prepare environment
    f, downloader, uploader, state = _make_fake_env(tmp_path)

    # Should not raise despite debug writes failing
    stats = main.process_user("bob", downloader, uploader, state, force_redownload=False)
    assert stats["uploaded"] == 1
    # Confirm that even though write failed, application continued
    assert isinstance(stats, dict)
