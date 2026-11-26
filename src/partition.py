"""חלוקת רשימת המשתמשים לחלקים להרצות מקבילות.

עקרון: החלוקה קובעת רק מי מעבד אילו משתמשים — לא איפה ה-state נשמר.
כל חלק מוריד state מלא, ולכן שינוי במספר החלקים או ברשימת המשתמשים
אינו גורם לאיבוד היסטוריה או לכפילויות.
"""
import math
import os
import sys
from pathlib import Path
from typing import List, Tuple

USERS_PER_PART_FILE = "USERS_PER_PART.txt"
DEFAULT_USERS_PER_PART = 80


def read_users_per_part(path: str = USERS_PER_PART_FILE) -> int:
    """קורא כמה משתמשים לחלק. ערך לא תקין/חסר -> ברירת מחדל 80."""
    try:
        raw = Path(path).read_text(encoding="utf-8").strip()
        value = int(raw)
        if value > 0:
            return value
    except (OSError, ValueError):
        pass
    return DEFAULT_USERS_PER_PART


def part_count(total_users: int, users_per_part: int) -> int:
    """מספר החלקים הנדרש לכיסוי כל המשתמשים."""
    if total_users <= 0:
        return 1
    if users_per_part <= 0:
        return 1
    return max(1, math.ceil(total_users / users_per_part))


def partition_entries(
    entries: List[Tuple[str, str]], part_index: int, part_total: int
) -> List[Tuple[str, str]]:
    """מחזיר את המשתמשים ששייכים לחלק `part_index` (1-based).

    `part_total=1` מחזיר את הרשימה המלאה (תאימות לאחור).
    """
    if part_total <= 1:
        return list(entries)
    if part_index < 1 or part_index > part_total:
        raise ValueError(f"part_index must be in 1..{part_total}, got {part_index}")
    return [entry for i, entry in enumerate(entries) if i % part_total == part_index - 1]


def resolve_partition(entries: List[Tuple[str, str]]) -> Tuple[List[Tuple[str, str]], int, int]:
    """פותר פרמטרי חלוקה מהסביבה ומחזיר (entries של החלק, index, total).

    משתני סביבה:
      PART_INDEX / PART_TOTAL — נקבעים ע"י ה-workflow (matrix).
      USERS_PER_PART — עוקף את הקובץ (input של workflow_dispatch).
    """
    part_index = int(os.environ.get("PART_INDEX", "1") or "1")
    part_total_env = os.environ.get("PART_TOTAL", "").strip()
    if part_total_env:
        part_total = int(part_total_env)
    else:
        # הרצה מקומית ללא matrix: לחשב מהקובץ/משתנה.
        per_part = int(os.environ.get("USERS_PER_PART", "0") or "0") or read_users_per_part()
        part_total = part_count(len(entries), per_part)

    if part_total <= 1:
        return list(entries), 1, 1
    return partition_entries(entries, part_index, part_total), part_index, part_total


def _count_unique_users() -> int:
    """סופר משתמשים ייחודיים מהקבצים, בלי להריץ את כל main.

    `load_usernames` מדפיס לוגים ל-stdout; מסיטים אותם ל-stderr כדי שפלט
    ה-CLI יהיה מספר גרידא (ה-workflow לוכד את ה-stdout).
    """
    import contextlib

    from src.main import load_usernames

    with contextlib.redirect_stdout(sys.stderr):
        entries, _ = load_usernames()
    return len(entries)


def cli(argv: List[str]) -> int:
    """CLI קטן לג'וב ה-setup ב-workflow.

    Usage:
      python -m src.partition count          -> מספר המשתמשים הייחודיים
      python -m src.partition total <users>  -> מספר החלקים
      python -m src.partition parts <total>  -> רשימת אינדקסים כ-JSON
    """
    if len(argv) >= 2 and argv[1] == "count":
        print(_count_unique_users())
        return 0
    if len(argv) >= 3 and argv[1] == "total":
        users = int(argv[2])
        per = int(os.environ.get("USERS_PER_PART", "0") or "0") or read_users_per_part()
        print(part_count(users, per))
        return 0
    if len(argv) >= 3 and argv[1] == "parts":
        import json

        total = int(argv[2])
        print(json.dumps(list(range(1, total + 1))))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(cli(sys.argv))
