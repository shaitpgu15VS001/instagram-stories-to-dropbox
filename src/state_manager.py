import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .logger import logger


STATE_FILE = "state.json"
STATE_VERSION = 1


def _empty_state():
    return {
        "version": STATE_VERSION,
        "last_updated": None,
        "uploaded_files": {},
    }


class StateManager:

    def __init__(self, state_path=STATE_FILE):
        self.state_path = Path(state_path)
        self.state = self._load()

    def _load(self):
        if not self.state_path.exists():
            logger.debug(f"קובץ state לא קיים, יוצר חדש ב-{self.state_path}")
            return _empty_state()

        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"שגיאה בקריאת state: {exc}. מתחיל מחדש.")
            return _empty_state()

        if not isinstance(data, dict):
            logger.warning("state root must be a JSON object; starting fresh")
            return _empty_state()

        if data.get("version") != STATE_VERSION:
            logger.warning("גרסת state שונתה, מתחיל מחדש")
            return _empty_state()

        uploaded_files = data.get("uploaded_files")
        if not isinstance(uploaded_files, dict):
            logger.warning("state.uploaded_files is invalid or missing; starting fresh")
            return _empty_state()

        return data

    def save(self):
        self.state["last_updated"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=self.state_path.parent, prefix=".state_", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.state, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.state_path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        except OSError as exc:
            logger.error(f"שגיאה בשמירת state: {exc} E-STATE-001")

    def find_uploaded_entry(self, username, story_id):
        user_files = self.state["uploaded_files"].get(username, [])
        for item in user_files:
            # Backwards-compatible checks: match by existing instagram_id or new pre_download_id
            if item.get("instagram_id") == story_id:
                return "instagram_id", item
            if item.get("pre_download_id") and item.get("pre_download_id") == story_id:
                return "pre_download_id", item
        return None, None

    def is_uploaded(self, username, story_id):
        _, item = self.find_uploaded_entry(username, story_id)
        return item is not None

    def mark_uploaded(self, username, story_id, filename, dropbox_path, published_at=None, pre_download_id=None):
        if username not in self.state["uploaded_files"]:
            self.state["uploaded_files"][username] = []

        entry = {
            "instagram_id": story_id,
            "filename": filename,
            "dropbox_path": dropbox_path,
            "published_at": published_at,
            "uploaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        # Optionally store the pre-download identifier (uri_path) for faster skip-before-download
        if pre_download_id:
            entry["pre_download_id"] = pre_download_id

        self.state["uploaded_files"][username].append(entry)
        logger.debug(f"סומן כהועלה: {username}/{filename}")

    def get_uploaded_count(self, username=None):
        if username:
            return len(self.state["uploaded_files"].get(username, []))
        return sum(len(v) for v in self.state["uploaded_files"].values())

    def get_stats(self):
        total = self.get_uploaded_count()
        users = len(self.state["uploaded_files"])
        return {"total_uploaded": total, "tracked_users": users}

    def clear_user(self, username):
        if username in self.state["uploaded_files"]:
            del self.state["uploaded_files"][username]
            logger.info(f"נוקה מעקב עבור {username}")
