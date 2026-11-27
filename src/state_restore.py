"""שחזור state.json מהענן — תמיד מהעותק העדכני ביותר.

הבעיה: כשענן מתמלא, המערכת כותבת את ה-state לענן הבא, אבל בענן הישן
נשאר עותק מעופש. לולאה של "הרמוט הראשון שיש לו state" עלולה לשחזר
דווקא את הישן. הכלי הזה בודק את זמן השינוי (ModTime) של כל עותק ובוחר
את החדש ביותר.

שימוש ( ע"י ה-workflow):
    python -m src.state_restore <out_path> <remote1> <remote2> ...

הקונפיג הגיע מ-RCLONE_CONFIG (ברירת מחדל rclone.conf).
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import List, Optional, Tuple


def _lsjson(remote: str, config: str) -> Optional[dict]:
    try:
        result = subprocess.run(
            ["rclone", "lsjson", f"{remote}:.instagram-sync/state.json", "--config", config],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    try:
        entries = json.loads(result.stdout)
        return entries[0] if entries else None
    except (ValueError, IndexError):
        return None


def _parse_time(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # rclone מחזיר RFC3339; fromisoformat מתמודד גם עם Z בגרסאות חדשות
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def select_freshest(remotes: List[str], config: str) -> Tuple[Optional[str], Optional[datetime]]:
    """מחזיר (remote, modtime) של העותק העדכני ביותר, או (None, None)."""
    best_remote = None
    best_time = None
    for remote in remotes:
        info = _lsjson(remote, config)
        if not info:
            continue
        mt = _parse_time(info.get("ModTime"))
        if mt is None:
            continue
        if best_time is None or mt > best_time:
            best_remote, best_time = remote, mt
    return best_remote, best_time


def restore(out_path: str, remotes: List[str], config: str) -> int:
    best, best_time = select_freshest(remotes, config)
    if not best:
        print("RESTORE_NO_STATE: no remote state.json found")
        return 1
    try:
        result = subprocess.run(
            ["rclone", "copyto", f"{best}:.instagram-sync/state.json", out_path, "--config", config],
            capture_output=True,
            text=True,
            timeout=180,
        )
    except Exception as exc:
        print(f"RESTORE_FAILED: {exc}", file=sys.stderr)
        return 2
    if result.returncode != 0:
        print(f"RESTORE_FAILED: {result.stderr.strip()}", file=sys.stderr)
        return 2
    print(f"RESTORE_OK remote={best} modtime={best_time.isoformat() if best_time else '?'}")
    return 0


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    out_path = argv[1]
    remotes = argv[2:]
    config = os.environ.get("RCLONE_CONFIG", "rclone.conf")
    return restore(out_path, remotes, config)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
