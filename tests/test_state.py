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


