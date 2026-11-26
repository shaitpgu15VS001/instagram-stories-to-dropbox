"""בדיקות לחלוקת המשתמשים להרצות מקבילות."""
from src.partition import (
    DEFAULT_USERS_PER_PART,
    part_count,
    partition_entries,
    read_users_per_part,
    resolve_partition,
)

ENTRIES = [(f"folder{i}", f"user{i}") for i in range(10)]


def test_partition_disjoint_and_complete():
    total = 3
    parts = [partition_entries(ENTRIES, i, total) for i in range(1, total + 1)]
    flat = [e for part in parts for e in part]
    assert len(flat) == len(ENTRIES)
    assert set(flat) == set(ENTRIES)  # אין כפילויות, אין פספוס
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            assert not (set(parts[i]) & set(parts[j]))  # זרים


def test_part_total_one_returns_all():
    assert partition_entries(ENTRIES, 1, 1) == ENTRIES


def test_partition_stable_for_same_user():
    # אותו משתמש נשאר באותו חלק בין הרצות (חלוקה לפי אינדקס יציב).
    a = partition_entries(ENTRIES, 2, 3)
    b = partition_entries(ENTRIES, 2, 3)
    assert a == b


def test_part_count():
    assert part_count(10, 3) == 4
    assert part_count(9, 3) == 3
    assert part_count(0, 80) == 1
    assert part_count(5, 0) == 1


def test_read_users_per_part(tmp_path, monkeypatch):
    p = tmp_path / "USERS_PER_PART.txt"
    p.write_text("80\n", encoding="utf-8")
    assert read_users_per_part(str(p)) == 80
    p.write_text("not-a-number", encoding="utf-8")
    assert read_users_per_part(str(p)) == DEFAULT_USERS_PER_PART
    assert read_users_per_part(str(tmp_path / "missing")) == DEFAULT_USERS_PER_PART


def test_resolve_partition_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PART_INDEX", "2")
    monkeypatch.setenv("PART_TOTAL", "3")
    monkeypatch.delenv("USERS_PER_PART", raising=False)
    entries, idx, total = resolve_partition(ENTRIES)
    assert idx == 2 and total == 3
    assert entries == partition_entries(ENTRIES, 2, 3)


def test_resolve_partition_local_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PART_INDEX", raising=False)
    monkeypatch.delenv("PART_TOTAL", raising=False)
    monkeypatch.setenv("USERS_PER_PART", "4")
    entries, idx, total = resolve_partition(ENTRIES)
    assert idx == 1
    assert total == 3  # ceil(10/4)


def test_invalid_part_index_raises():
    import pytest

    with pytest.raises(ValueError):
        partition_entries(ENTRIES, 5, 3)


def test_cli_count_prints_only_a_number(monkeypatch, tmp_path, capsys):
    """פלט ה-CLI חייב להיות מספר גרידא — ה-workflow לוכד אותו ב-command substitution."""
    from src import partition

    # מדמה קריאת משתמשים שמדפיסה לוגים ל-stdout (כמו load_usernames האמיתי)
    def fake_load():
        print("📥 טוען שמות משתמשים")
        print("\x1b[94m[timestamp] ℹ️  TXT: 1 רשומה\x1b[0m")
        return [("a", "ua"), ("b", "ub"), ("c", "uc")], {}

    import src.main as main_mod
    monkeypatch.setattr(main_mod, "load_usernames", fake_load)

    rc = partition.cli(["partition", "count"])
    captured = capsys.readouterr()

    assert rc == 0
    # כל הלוגים הוסטו ל-stderr; stdout מכיל רק את המספר
    assert captured.out.strip() == "3"
    int(captured.out.strip())  # לא זורק
    assert "טוען שמות משתמשים" in captured.err
