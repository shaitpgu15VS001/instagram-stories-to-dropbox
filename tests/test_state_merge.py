"""בדיקות למיזוג קובצי state של חלקים מקבילים."""
import json

import pytest

from src.state_merge import _dedup_key, merge_state_files, merge_states


def _state(users):
    return {"version": 1, "last_updated": None, "uploaded_files": users}


def _entry(pid, filename=None, ts="2026-11-26T00:00:00Z"):
    return {
        "instagram_id": f"sid-{pid}",
        "pre_download_id": pid,
        "filename": filename or f"file-{pid}.jpg",
        "dropbox_path": f"/x/{pid}",
        "uploaded_at": ts,
    }


def test_dedup_key_prefers_pre_download_id():
    assert _dedup_key(_entry("abc")) == "pre_download_id:abc"
    assert _dedup_key({"filename": "f.jpg"}) == "filename:f.jpg"
    assert _dedup_key({"instagram_id": "sid"}) == "instagram_id:sid"


def test_merge_disjoint_users():
    a = _state({"alice": [_entry("a1")]})
    b = _state({"bob": [_entry("b1")]})
    merged, stats = merge_states([a, b])
    assert set(merged["uploaded_files"]) == {"alice", "bob"}
    assert stats["entries"] == 2
    assert stats["no_drop"]


def test_merge_same_user_dedups_by_pre_download_id():
    a = _state({"alice": [_entry("a1"), _entry("a2")]})
    b = _state({"alice": [_entry("a2"), _entry("a3")]})
    merged, stats = merge_states([a, b])
    pids = {e["pre_download_id"] for e in merged["uploaded_files"]["alice"]}
    assert pids == {"a1", "a2", "a3"}
    assert stats["entries"] == 3


def test_merge_keeps_newer_uploaded_at():
    old = _entry("a1", ts="2026-11-20T00:00:00Z")
    new = _entry("a1", ts="2026-11-26T00:00:00Z")
    merged, _ = merge_states([_state({"alice": [old]}), _state({"alice": [new]})])
    assert merged["uploaded_files"]["alice"][0]["uploaded_at"] == new["uploaded_at"]


def test_merge_with_failed_empty_part():
    # חלק שנכשל לא מעלה כלום — שאר החלקים עדיין מתמזגים.
    a = _state({"alice": [_entry("a1")]})
    empty = _state({})
    merged, stats = merge_states([a, empty])
    assert stats["entries"] == 1
    assert stats["no_drop"]


def test_merge_files_atomic_and_idempotent(tmp_path):
    p1 = tmp_path / "part1.json"
    p2 = tmp_path / "part2.json"
    p1.write_text(json.dumps(_state({"alice": [_entry("a1")]})), encoding="utf-8")
    p2.write_text(json.dumps(_state({"bob": [_entry("b1")]})), encoding="utf-8")
    out = tmp_path / "state.json"

    stats1 = merge_state_files(out, [p1, p2])
    first = out.read_text(encoding="utf-8")
    stats2 = merge_state_files(out, [p1, p2])
    second = out.read_text(encoding="utf-8")

    assert stats1["entries"] == 2
    # idempotent: הערכים המובנים זהים (רק last_updated מתעדכן)
    d1, d2 = json.loads(first), json.loads(second)
    assert d1["uploaded_files"] == d2["uploaded_files"]


def test_merge_empty_raises(tmp_path):
    with pytest.raises(ValueError, match="no state part files"):
        merge_state_files(tmp_path / "state.json", [])


def test_cli_main(tmp_path):
    from src.state_merge import main

    p1 = tmp_path / "part1.json"
    p1.write_text(json.dumps(_state({"alice": [_entry("a1")]})), encoding="utf-8")
    out = tmp_path / "state.json"
    rc = main(["state_merge", str(out), str(p1)])
    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["uploaded_files"]["alice"]
