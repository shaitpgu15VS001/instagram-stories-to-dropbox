"""בדיקות למפסק התפעולי: עצירת ריצה אחרי רצף כשלי API."""
import pytest

from src import main


class FakeUploader:
    def __init__(self, *args, **kwargs):
        self.uploads_per_remote = {}
        self.switches = []
        self.current_remote = "test"

    def select_initial(self):
        return "test"

    def connect(self):
        return True

    def get_folder_path_for_date(self, today, folder_name):
        return "dest"

    def upload_file(self, local_file, dropbox_path):
        return True


class FakeState:
    def __init__(self, *args, **kwargs):
        pass

    def is_uploaded(self, username, story_id):
        return False

    def mark_uploaded(self, *args, **kwargs):
        pass

    def save(self):
        pass

    def get_stats(self):
        return {"total_uploaded": 0, "tracked_users": 0}


API_ERROR_RESULT = {
    "success": False,
    "files": [],
    "error": "api_error",
    "outcome": "api_error",
    "stories_found": 0,
    "pre_skipped": 0,
}

NO_ACTIVE_RESULT = {
    "success": True,
    "files": [],
    "error": None,
    "outcome": "no_active_stories",
    "stories_found": 0,
    "pre_skipped": 0,
}


def _run_main(monkeypatch, results, preflight_ok=True):
    """מריץ את main() עם תלויות מדומות. מחזיר (מספר משתמשים שעובדו, exit code)."""
    import src.logger as logger_module

    calls = {"n": 0}

    class FakeDownloader:
        def __init__(self, *args, **kwargs):
            self.state_manager = None

        def ensure_story_source_ready(self):
            return preflight_ok

        def check_binary(self):
            return True

        def download_stories(self, username, folder_name=None):
            index = min(calls["n"], len(results) - 1)
            calls["n"] += 1
            return dict(results[index])

        def extract_story_id(self, name):
            return name

        def cleanup(self, folder_name=None):
            pass

    entries = [(f"folder{i}", f"user{i}") for i in range(len(results))]

    monkeypatch.setattr(main, "RcloneUploader", FakeUploader)
    monkeypatch.setattr(main, "StoryDownloader", FakeDownloader)
    monkeypatch.setattr(main, "StateManager", FakeState)
    monkeypatch.setattr(main, "_read_remote_list", lambda *a, **k: ["test"])
    monkeypatch.setattr(main, "_detect_remotes", lambda *a, **k: ["test"])
    monkeypatch.setattr(main, "load_usernames", lambda *a, **k: (entries, {}))
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr("src.schedule.read_trigger", lambda *a, **k: "manual")
    monkeypatch.setattr("src.schedule.should_run", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(logger_module.Logger, "init_debug", lambda *a, **k: None)
    monkeypatch.setattr(logger_module.Logger, "write_summary", lambda *a, **k: None)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main.main()
    return calls["n"], exc_info.value.code


def test_preflight_failure_aborts_before_any_user(monkeypatch):
    processed, code = _run_main(monkeypatch, [NO_ACTIVE_RESULT] * 10, preflight_ok=False)
    assert processed == 0
    assert code == 1


def test_threshold_env_parsing(monkeypatch):
    monkeypatch.delenv("MAX_CONSECUTIVE_API_ERRORS", raising=False)
    assert main._max_consecutive_api_errors() == main.DEFAULT_MAX_CONSECUTIVE_API_ERRORS
    monkeypatch.setenv("MAX_CONSECUTIVE_API_ERRORS", "2")
    assert main._max_consecutive_api_errors() == 2
    monkeypatch.setenv("MAX_CONSECUTIVE_API_ERRORS", "0")
    assert main._max_consecutive_api_errors() == 0
    monkeypatch.setenv("MAX_CONSECUTIVE_API_ERRORS", "not-a-number")
    assert main._max_consecutive_api_errors() == main.DEFAULT_MAX_CONSECUTIVE_API_ERRORS


def test_aborts_after_default_threshold(monkeypatch):
    monkeypatch.delenv("MAX_CONSECUTIVE_API_ERRORS", raising=False)
    processed, code = _run_main(monkeypatch, [API_ERROR_RESULT] * 10)
    assert processed == main.DEFAULT_MAX_CONSECUTIVE_API_ERRORS
    assert code == 1


def test_breaker_disabled_processes_all_users(monkeypatch):
    monkeypatch.setenv("MAX_CONSECUTIVE_API_ERRORS", "0")
    processed, code = _run_main(monkeypatch, [API_ERROR_RESULT] * 6)
    assert processed == 6
    assert code == 1


def test_success_resets_consecutive_counter(monkeypatch):
    monkeypatch.setenv("MAX_CONSECUTIVE_API_ERRORS", "3")
    results = [API_ERROR_RESULT, API_ERROR_RESULT, NO_ACTIVE_RESULT] + [API_ERROR_RESULT] * 4
    processed, code = _run_main(monkeypatch, results)
    # 2 כשלים -> איפוס בהצלחה -> 3 כשלים -> עצירה במשתמש השישי
    assert processed == 6
    assert code == 1
