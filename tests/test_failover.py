import json

import pytest

from src.rclone_uploader import RcloneUploader, InfrastructureError


class DummyResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _about(free, total=10 * 1024 * 1024 * 1024):
    return DummyResult(returncode=0, stdout=json.dumps({"total": total, "used": total - free, "free": free}))


GB = 1024 * 1024 * 1024


class FailoverUploader(RcloneUploader):
    def __init__(self, script, **kw):
        super().__init__(**kw)
        self.script = script
        self.calls = []

    def _run_rclone(self, args, timeout=120):
        self.calls.append(args)
        key = args[0]
        if key == "about":
            remote = args[2].rstrip(":")
            return self.script["about"].get(remote, DummyResult(returncode=1, stderr="nope"))
        if key == "copyto":
            dest = args[2]
            remote = dest.split(":")[0]
            handler = self.script["copyto"].get(remote)
            if handler is None:
                return DummyResult(returncode=0)
            if isinstance(handler, list):
                return handler.pop(0)
            return handler
        return DummyResult(returncode=0)


def _tmp_file(tmp_path, size=10):
    p = tmp_path / "f.bin"
    p.write_bytes(b"x" * size)
    return p


def test_select_initial_skips_full_remote(tmp_path):
    up = FailoverUploader(
        {"about": {"a": _about(int(0.01 * GB)), "b": _about(5 * GB)}, "copyto": {}},
        remote_name="a",
        failover_remotes=["a", "b"],
    )
    assert up.select_initial() == "b"
    assert up.current_remote == "b"


def test_select_initial_none_when_all_full():
    up = FailoverUploader(
        {"about": {"a": _about(int(0.01 * GB)), "b": _about(int(0.005 * GB))}, "copyto": {}},
        remote_name="a",
        failover_remotes=["a", "b"],
    )
    assert up.select_initial() is None


def test_quota_error_switches_and_uploads(tmp_path):
    up = FailoverUploader(
        {
            "about": {"a": _about(5 * GB), "b": _about(5 * GB)},
            "copyto": {"a": DummyResult(returncode=1, stderr="disk quota exceeded"), "b": DummyResult(returncode=0)},
        },
        remote_name="a",
        failover_remotes=["a", "b"],
    )
    assert up.select_initial() == "a"
    assert up.upload_file(_tmp_file(tmp_path), "x/f.bin") is True
    assert up.current_remote == "b"
    assert up.uploads_per_remote["b"] == 1
    assert up.switches and up.switches[0]["reason"] == "quota"


def test_byte_counter_switches_before_wall(tmp_path):
    up = FailoverUploader(
        {"about": {"a": _about(50 * 1024 * 1024, total=1024 * 1024 * 1024), "b": _about(9 * GB)}, "copyto": {}},
        remote_name="a",
        failover_remotes=["a", "b"],
    )
    assert up.select_initial() == "a"
    # 50MB פנוי פחות 50MB רזרבה: קובץ 15MB לא נכנס
    big = tmp_path / "big.bin"
    big.write_bytes(b"x" * (15 * 1024 * 1024))
    assert up.upload_file(big, "x/big.bin") is True
    assert up.current_remote == "b"


def test_single_remote_quota_returns_false_no_switch(tmp_path):
    up = FailoverUploader(
        {"about": {"a": _about(5 * GB)}, "copyto": {"a": DummyResult(returncode=1, stderr="quota exceeded")}},
        remote_name="a",
    )
    assert up.select_initial() == "a"
    assert up.upload_file(_tmp_file(tmp_path), "x/f.bin") is False
    assert up.current_remote == "a"
    assert up.switches == []


def test_single_remote_infra_still_raises(tmp_path):
    up = FailoverUploader(
        {"about": {}, "copyto": {"a": DummyResult(returncode=1, stderr="401 Unauthorized")}},
        remote_name="a",
    )
    with pytest.raises(InfrastructureError):
        up.upload_file(_tmp_file(tmp_path), "x/f.bin")


def test_is_quota_error_keywords():
    assert RcloneUploader.is_quota_error("disk quota exceeded") is True
    assert RcloneUploader.is_quota_error("Error 507 Insufficient Storage") is True
    assert RcloneUploader.is_quota_error("all good") is False
    assert RcloneUploader.is_quota_error("") is False


def test_read_remote_list_ordered(tmp_path):
    from src.main import _read_remote_list

    p = tmp_path / "STORAGE_BACKEND.txt"
    p.write_text("dropbox\n\n# comment\nonedrive\ndropbox\n", encoding="utf-8")
    assert _read_remote_list(str(p)) == ["dropbox", "onedrive"]
    assert _read_remote_list(str(tmp_path / "missing.txt")) == []


def test_mark_uploaded_stores_remote(tmp_path):
    from src.state_manager import StateManager

    sm = StateManager(state_path=str(tmp_path / "state.json"))
    sm.mark_uploaded(username="u", story_id="s", filename="f.jpg", dropbox_path="d/f.jpg", remote="onedrive")
    sm.save()
    sm2 = StateManager(state_path=str(tmp_path / "state.json"))
    entries = sm2.state["uploaded_files"]["u"]
    assert entries[0]["remote"] == "onedrive"
    assert sm2.is_uploaded("u", "s")


def test_process_user_records_upload_remote(tmp_path):
    from src import main

    files_dir = tmp_path / "files"
    files_dir.mkdir()
    f = files_dir / "story1.jpg"
    f.write_bytes(b"data")

    class FakeDownloader:
        def download_stories(self, username, folder_name=None):
            return {"success": True, "files": [f], "meta": {f.name: "pre1"}, "outcome": "stories_found", "stories_found": 1, "pre_skipped": 0}

        def extract_story_id(self, name):
            return "sid1"

    class FakeUploader:
        current_remote = "second"

        def get_folder_path_for_date(self, today, folder_name):
            return "dest"

        def upload_file(self, local_file, dropbox_path):
            return True

    recorded = {}

    class FakeState:
        def is_uploaded(self, username, story_id):
            return False

        def mark_uploaded(self, *a, **kw):
            recorded.update(kw)

        def save(self):
            return None

    stats = main.process_user("user1", FakeDownloader(), FakeUploader(), FakeState(), force_redownload=False)
    assert stats["status"] == "STORIES_FOUND"
    assert recorded.get("remote") == "second"
