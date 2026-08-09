import tempfile
import os
from pathlib import Path

from src.story_downloader import extract_pre_download_id
from src.state_manager import StateManager


def test_extract_pre_download_id_basic():
    href = "https://fastdl.app/download?uri=https%3A%2F%2Finstagram.com%2Fo1%2Fv%2Fpath%2Ffile.jpg&__sig=AAA"
    pid = extract_pre_download_id(href)
    assert pid == "/o1/v/path/file.jpg"


def test_extract_ignores_sig_and_expires():
    base = "https://fastdl.app/download?uri=https%3A%2F%2Finstagram.com%2Fv%2Ffile.jpg"
    a = base + "&__sig=AAA&__expires=123"
    b = base + "&__sig=BBB&__expires=456"
    assert extract_pre_download_id(a) == extract_pre_download_id(b)


def test_extract_none_when_missing_uri():
    href = "https://fastdl.app/download?something=else"
    assert extract_pre_download_id(href) is None


def test_state_marks_and_checks_pre_download_id(tmp_path):
    p = tmp_path / "state.json"
    sm = StateManager(state_path=str(p))
    username = "alice"
    pre_id = "/v/t51.82787-15/12345.jpg"
    assert not sm.is_uploaded(username, pre_id)
    sm.mark_uploaded(username=username, story_id="legacy1", filename="f.jpg", dropbox_path="/x/f.jpg", pre_download_id=pre_id)
    sm.save()
    sm2 = StateManager(state_path=str(p))
    assert sm2.is_uploaded(username, pre_id)


def test_same_uri_different_users_not_confused(tmp_path):
    p = tmp_path / "state.json"
    sm = StateManager(state_path=str(p))
    pre_id = "/v/t51.82787-15/12345.jpg"
    sm.mark_uploaded(username="alice", story_id="legacy1", filename="f.jpg", dropbox_path="/x/f.jpg", pre_download_id=pre_id)
    sm.save()
    sm2 = StateManager(state_path=str(p))
    assert sm2.is_uploaded("alice", pre_id)
    assert not sm2.is_uploaded("bob", pre_id)
