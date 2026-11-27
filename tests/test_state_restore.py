"""בדיקות לשחזור ה-state מהעותק העדכני ביותר."""
import json

from src import state_restore


def test_select_freshest_picks_newest(monkeypatch):
    metas = {
        "MG-S001": {"ModTime": "2026-11-26T06:21:45.000000000Z"},
        "MG-S002": {"ModTime": "2026-11-27T01:49:08.000000000Z"},
        "MG-S003": {"ModTime": "2026-11-25T12:00:00.000000000Z"},
    }
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        remote = args[2].split(":")[0]
        body = json.dumps([metas[remote]]) if remote in metas else "[]"
        return type("R", (), {"returncode": 0, "stdout": body, "stderr": ""})()

    monkeypatch.setattr(state_restore.subprocess, "run", fake_run)
    best, _ = state_restore.select_freshest(["MG-S001", "MG-S002", "MG-S003"], "rclone.conf")
    assert best == "MG-S002"


def test_select_freshest_skips_missing(monkeypatch):
    def fake_run(args, **kwargs):
        if "MG-S001" in args[2]:
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": "missing"})()
        return type("R", (), {"returncode": 0, "stdout": json.dumps([{"ModTime": "2026-11-27T00:00:00Z"}]), "stderr": ""})()

    monkeypatch.setattr(state_restore.subprocess, "run", fake_run)
    best, _ = state_restore.select_freshest(["MG-S001", "MG-S004"], "rclone.conf")
    assert best == "MG-S004"


def test_select_freshest_none(monkeypatch):
    def fake_run(args, **kwargs):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "no"})()

    monkeypatch.setattr(state_restore.subprocess, "run", fake_run)
    best, t = state_restore.select_freshest(["MG-S001"], "rclone.conf")
    assert best is None and t is None


def test_restore_copies_from_freshest(monkeypatch):
    metas = {
        "MG-S001": {"ModTime": "2026-11-26T06:00:00Z"},
        "MG-S002": {"ModTime": "2026-11-27T01:00:00Z"},
    }
    copy_calls = []

    def fake_run(args, **kwargs):
        if args[1] == "lsjson":
            remote = args[2].split(":")[0]
            return type("R", (), {"returncode": 0, "stdout": json.dumps([metas[remote]]), "stderr": ""})()
        if args[1] == "copyto":
            copy_calls.append(args)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        raise AssertionError(args)

    monkeypatch.setattr(state_restore.subprocess, "run", fake_run)
    rc = state_restore.restore("state.json", ["MG-S001", "MG-S002"], "rclone.conf")
    assert rc == 0
    assert "MG-S002:.instagram-sync/state.json" in copy_calls[0][2]


def test_restore_no_state_returns_1(monkeypatch):
    def fake_run(args, **kwargs):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "no"})()

    monkeypatch.setattr(state_restore.subprocess, "run", fake_run)
    assert state_restore.restore("state.json", ["MG-S001"], "rclone.conf") == 1
