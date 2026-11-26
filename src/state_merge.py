"""מיזוג קבצי state מג'ובים מקבילים ל-state.json אחד.

כל חלק מוריד state מלא, מוסיף רק את המשתמשים שלו, ומעלה עותק כ-artifact.
המיזוג מאחד את כל העותקים: union של uploaded_files לפי משתמש, עם דדופ
לפי pre_download_id (נפילה ל-filename / instagram_id). הפעולה idempotent.

שימוש מקובץ ( ע"י ה-workflow):
    python -m src.state_merge <out.json> <part1.json> <part2.json> ...
"""
import json
import os
import sys
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

STATE_VERSION = 1


def _dedup_key(entry: dict) -> str:
    """מפתח יציב לרשומה — pre_download_id עדיף, ואז filename/instagram_id."""
    for key in ("pre_download_id", "filename", "instagram_id"):
        value = entry.get(key)
        if value:
            return f"{key}:{value}"
    # נפילה אחרונה: תוכן הרשומה כולה
    return "raw:" + json.dumps(entry, sort_keys=True, ensure_ascii=False)


def _load_state(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("uploaded_files"), dict):
        raise ValueError(f"invalid state file: {path}")
    return data


def _merge_user_entries(entries: Iterable[dict]) -> List[dict]:
    """מאחד רשומות של משתמש אחד, מוריד כפילויות, משאיר את העדכנית ביותר."""
    merged: "OrderedDict[str, dict]" = OrderedDict()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = _dedup_key(entry)
        existing = merged.get(key)
        if existing is None:
            merged[key] = entry
            continue
        # אם לאחת יש uploaded_at מאוחר יותר — היא עדכנית יותר
        existing_ts = str(existing.get("uploaded_at") or "")
        new_ts = str(entry.get("uploaded_at") or "")
        if new_ts > existing_ts:
            merged[key] = entry
    return list(merged.values())


def merge_states(parts: List[dict]) -> Tuple[dict, dict]:
    """מאחד רשימות state. מחזיר (state מאוחד, סטטיסטיקות)."""
    uploaded: Dict[str, List[dict]] = {}
    for part in parts:
        for username, entries in part.get("uploaded_files", {}).items():
            if not isinstance(entries, list):
                continue
            uploaded.setdefault(username, []).extend(entries)

    merged_users = {}
    for username, entries in uploaded.items():
        merged_users[username] = _merge_user_entries(entries)

    merged_count = sum(len(v) for v in merged_users.values())
    max_input_count = max(
        (sum(len(v) for v in p.get("uploaded_files", {}).values()) for p in parts),
        default=0,
    )

    state = {
        "version": STATE_VERSION,
        "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "uploaded_files": merged_users,
    }
    stats = {
        "parts": len(parts),
        "users": len(merged_users),
        "entries": merged_count,
        "max_input_entries": max_input_count,
        "no_drop": merged_count >= max_input_count,
    }
    return state, stats


def _atomic_write(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".state_merge_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def merge_state_files(out_path: Path, part_paths: List[Path]) -> dict:
    """קורא קבצי חלק, מאחד, בודק שלמות, וכותב לפי שם קובץ אטומי.

    זורק ValueError אם אין קבצי חלק או אם המספר ירד (שלמות נפגעה).
    """
    if not part_paths:
        raise ValueError("no state part files to merge")
    parts = [_load_state(p) for p in part_paths]
    state, stats = merge_states(parts)
    if not stats["no_drop"]:
        raise ValueError(
            f"state merge would drop entries: merged={stats['entries']} "
            f"< max_input={stats['max_input_entries']}"
        )
    _atomic_write(out_path, state)
    return stats


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    out_path = Path(argv[1])
    part_paths = [Path(p) for p in argv[2:]]
    missing = [str(p) for p in part_paths if not p.exists()]
    if missing:
        print(f"missing state part files: {missing}", file=sys.stderr)
        return 3
    try:
        stats = merge_state_files(out_path, part_paths)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"state merge failed: {exc}", file=sys.stderr)
        return 4
    print(
        "STATE_MERGE_OK parts={parts} users={users} entries={entries} "
        "max_input_entries={max_input_entries} no_drop={no_drop}".format(**stats)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
