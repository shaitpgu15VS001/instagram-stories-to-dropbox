"""Observability tests: USER_FINISHED statuses and Run Summary."""
import pathlib

from src import main, logger
from src.fastdl_api import FastDLStoriesAPI
from src.story_downloader import StoryDownloader
from src.state_manager import StateManager


def _fake_uploader(tmp_path):
    class FakeUploader:
        def get_folder_path_for_date(self, today, folder_name):
            return "dest"
        def upload_file(self, local_file, dropbox_path):
            return True
    return FakeUploader()


def _fake_state(allow_all=False):
    class FakeState:
        def is_uploaded(self, username, story_id):
            return False
        def mark_uploaded(self, *a, **kw):
            return None
        def save(self):
            return None
    return FakeState()


def test_no_active_stories_status(tmp_path):
    # User with no stories -> should be NO_ACTIVE_STORIES (valid, not failed)
    class FakeDownloader:
        def download_stories(self, username, folder_name=None):
            return {"success": True, "files": [], "error": None, "outcome": "no_active_stories", "stories_found": 0, "pre_skipped": 0}
        def extract_story_id(self, name):
            return name
    lg = logger.logger
    lg.init_debug(debug_dir=str(tmp_path/"debug"), run_id="test-no-active")
    downloader = FakeDownloader()
    uploader = _fake_uploader(tmp_path)
    state = _fake_state()
    stats = main.process_user("nouser", downloader, uploader, state, force_redownload=False)
    assert stats["status"] == "NO_ACTIVE_STORIES"
    assert stats["error"] is None
    # duplicates_skipped reliable
    assert stats["pre_skipped"] == 0
    assert stats["stories_found"] == 0


def test_stories_found_status(tmp_path):
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    f = files_dir / "story1.jpg"
    f.write_bytes(b"data")
    class FakeDownloader:
        def download_stories(self, username, folder_name=None):
            return {"success": True, "files": [f], "meta": {f.name: "pre1"}, "outcome": "stories_found", "stories_found": 1, "pre_skipped": 0}
        def extract_story_id(self, name):
            return "sid1"
    lg = logger.logger
    lg.init_debug(debug_dir=str(tmp_path/"debug2"), run_id="test-found")
    downloader = FakeDownloader()
    uploader = _fake_uploader(tmp_path)
    state = _fake_state()
    stats = main.process_user("user1", downloader, uploader, state, force_redownload=False)
    assert stats["status"] == "STORIES_FOUND"
    assert stats["downloaded"] == 1
    assert stats["uploaded"] == 1


def test_no_new_stories_status(tmp_path):
    class FakeDownloader:
        def download_stories(self, username, folder_name=None):
            return {"success": True, "files": [], "error": None, "outcome": "no_new_stories", "stories_found": 5, "pre_skipped": 5}
        def extract_story_id(self, name):
            return name
    lg = logger.logger
    lg.init_debug(debug_dir=str(tmp_path/"debug3"), run_id="test-no-new")
    downloader = FakeDownloader()
    uploader = _fake_uploader(tmp_path)
    state = _fake_state()
    stats = main.process_user("user2", downloader, uploader, state, force_redownload=False)
    assert stats["status"] == "NO_NEW_STORIES"
    assert stats["stories_found"] == 5
    assert stats["pre_skipped"] == 5


def test_api_error_status(tmp_path):
    class FakeDownloader:
        def download_stories(self, username, folder_name=None):
            return {"success": False, "files": [], "error": "api_error", "outcome": "api_error", "stories_found": 0, "pre_skipped": 0}
        def extract_story_id(self, name):
            return name
    lg = logger.logger
    lg.init_debug(debug_dir=str(tmp_path/"debug4"), run_id="test-api-err")
    downloader = FakeDownloader()
    uploader = _fake_uploader(tmp_path)
    state = _fake_state()
    stats = main.process_user("baduser", downloader, uploader, state, force_redownload=False)
    assert stats["status"] == "API_ERROR"
    assert stats["error_id"] == "E-FDL-001"


def test_summary_counts_statuses(tmp_path):
    # Simulate 4 users: 2 STORIES_FOUND, 1 NO_ACTIVE, 1 NO_NEW, 1 API_ERROR
    # Build stats dicts manually and aggregate as main does
    from src.main import process_user
    files_dir = tmp_path / "files2"
    files_dir.mkdir()
    f1 = files_dir / "a.jpg"
    f1.write_bytes(b"x")
    f2 = files_dir / "b.jpg"
    f2.write_bytes(b"x")

    # We'll call process_user for each case and then aggregate
    cases = [
        ({"success": True, "files": [f1], "meta": {f1.name: "p1"}, "outcome": "stories_found", "stories_found": 1, "pre_skipped": 0}, "STORIES_FOUND"),
        ({"success": True, "files": [], "error": None, "outcome": "no_active_stories", "stories_found": 0, "pre_skipped": 0}, "NO_ACTIVE_STORIES"),
        ({"success": True, "files": [], "error": None, "outcome": "no_new_stories", "stories_found": 3, "pre_skipped": 3}, "NO_NEW_STORIES"),
        ({"success": False, "files": [], "error": "api_error", "outcome": "api_error", "stories_found": 0, "pre_skipped": 0}, "API_ERROR"),
    ]
    lg = logger.logger
    lg.init_debug(debug_dir=str(tmp_path/"debug5"), run_id="test-summary")
    results = []
    for idx, (ret, expected) in enumerate(cases):
        class D:
            def __init__(self, r): self._r = r
            def download_stories(self, u, folder_name=None): return self._r
            def extract_story_id(self, name): return name
        d = D(ret)
        # need fresh state and uploader (upload not called for empty)
        class U:
            def get_folder_path_for_date(self, t, fn): return "dest"
            def upload_file(self, lf, dp): return True
        class S:
            def is_uploaded(self, u, sid): return False
            def mark_uploaded(self, *a, **kw): return None
            def save(self): return None
        stats = process_user(f"user{idx}", d, U(), S(), force_redownload=False)
        assert stats["status"] == expected
        results.append(stats)

    # Aggregate as main does
    total = {"users_processed": 0, "users_failed": 0, "users_successful": 0, "users_stories_found": 0, "users_no_active": 0, "users_no_new": 0, "files_downloaded": 0, "files_uploaded": 0, "duplicates_skipped": 0}
    failed = []
    for s in results:
        total["users_processed"] += 1
        total["files_downloaded"] += s.get("downloaded", 0)
        total["files_uploaded"] += s.get("uploaded", 0)
        total["duplicates_skipped"] += s.get("duplicates_skipped", s.get("pre_skipped", 0)+s.get("skipped",0))
        st = s.get("status")
        if st == "STORIES_FOUND": total["users_stories_found"] += 1
        elif st == "NO_ACTIVE_STORIES": total["users_no_active"] += 1
        elif st == "NO_NEW_STORIES": total["users_no_new"] += 1
        if st in ("API_ERROR","DOWNLOAD_ERROR","UPLOAD_ERROR","OTHER_ERROR"):
            total["users_failed"] += 1
            failed.append(st)
        else:
            total["users_successful"] += 1
    assert total["users_processed"] == 4
    assert total["users_stories_found"] == 1
    assert total["users_no_active"] == 1
    assert total["users_no_new"] == 1
    assert total["users_failed"] == 1
    assert total["users_successful"] == 3
    assert len(failed) == 1


def test_user_not_found_status(tmp_path):
    class FakeDownloader:
        def download_stories(self, username, folder_name=None):
            return {"success": False, "files": [], "error": "user_not_found: @ghost לא נמצא", "outcome": "user_not_found", "stories_found": 0, "pre_skipped": 0}
        def extract_story_id(self, name):
            return name
    lg = logger.logger
    lg.init_debug(debug_dir=str(tmp_path/"debug7"), run_id="test-not-found")
    stats = main.process_user("ghost", FakeDownloader(), _fake_uploader(tmp_path), _fake_state(), force_redownload=False)
    assert stats["status"] == "USER_NOT_FOUND"
    assert stats["error_id"] == "E-USR-001"


def test_failures_appear_in_list(tmp_path):
    class FakeDownloader:
        def download_stories(self, username, folder_name=None):
            return {"success": False, "files": [], "error": "api_error", "outcome": "api_error", "stories_found": 0, "pre_skipped": 0}
        def extract_story_id(self, n): return n
    lg = logger.logger
    lg.init_debug(debug_dir=str(tmp_path/"debug6"), run_id="test-fail-list")
    d = FakeDownloader()
    u = _fake_uploader(tmp_path)
    s = _fake_state()
    stats = main.process_user("failuser", d, u, s, force_redownload=False)
    assert stats["status"] == "API_ERROR"
    # simulate aggregation
    failed_users = []
    if stats.get("status") in ("API_ERROR","DOWNLOAD_ERROR","UPLOAD_ERROR","OTHER_ERROR"):
        failed_users.append(("failuser", stats.get("status"), stats.get("error_id")))
    assert len(failed_users) == 1
    assert failed_users[0][0] == "failuser"
    assert failed_users[0][1] == "API_ERROR"
    assert "E-FDL-001" in failed_users[0][2]


def test_existing_log_not_broken(tmp_path, capsys):
    # Ensure empty result does not trigger E-FDL-001
    from src.story_downloader import StoryDownloader as SD
    import pathlib
    # monkeypatch fetch to return empty
    orig = SD._fetch_story_urls
    SD._fetch_story_urls = lambda self, u: []
    try:
        sd = StoryDownloader(output_dir=tmp_path/"stories")
        res = sd.download_stories("nouser")
        assert res["success"] is True
        assert res["error"] is None
        assert res["outcome"] == "no_active_stories"
        out = capsys.readouterr().out
        # should not contain error id
        assert "E-FDL-001" not in out
    finally:
        SD._fetch_story_urls = orig


def test_result_empty_list_remains_valid():
    # The fixed parser must keep [] as empty list not None
    assert FastDLStoriesAPI.parse_stories({"result": []}) == []
    assert FastDLStoriesAPI.parse_stories({"result": None, "data": []}) == [] or FastDLStoriesAPI.parse_stories({"result": None, "data": []}) == []
    # But when both None, returns None? Actually result None triggers fallback to data, data [] -> []
    # Ensure {"result": []} not treated as fallback
    # Already verified by previous, but double check not regression
    items = FastDLStoriesAPI.parse_stories({"result": []})
    assert items == []
    # Ensure download_stories treats it as no_active not api_error
    from src.story_downloader import StoryDownloader
    import tempfile
    tmp = pathlib.Path(tempfile.mkdtemp())
    sd = StoryDownloader(output_dir=tmp/"stories")
    # mock fetch to empty list path
    sd._fetch_story_urls = lambda u: []
    res = sd.download_stories("testuser", folder_name="testuser")
    assert res["outcome"] == "no_active_stories"
    assert res["success"] is True
