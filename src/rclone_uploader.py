import json
import subprocess
from pathlib import Path

from .logger import logger

class InfrastructureError(Exception):
    """Raised when rclone reports a non-retryable infrastructure error."""


class RcloneUploader:
    MAX_RETRIES = 3
    RETRY_DELAY = 5
    # מעבר ענן כשניצול מגיע לסף (97%), עם שולי ביטחון לבייטים.
    MAX_USAGE = 0.97
    RESERVE_BYTES = 50 * 1024 * 1024
    QUOTA_TOKENS = [
        "quota",
        "no space left",
        "no space",
        "insufficient storage",
        "not_enough_space",
        "not enough space",
        "over quota",
        "storage quota",
        "disk quota",
        "out of space",
        "space exceeded",
        "507",
    ]

    def __init__(self, remote_name="onedrive", config_path="rclone.conf", failover_remotes=None):
        self.remote_name = remote_name
        if failover_remotes:
            seen = []
            for name in failover_remotes:
                name = (name or "").strip()
                if name and name not in seen:
                    seen.append(name)
            self.remote_names = seen or [remote_name]
        else:
            self.remote_names = [remote_name]
        self.config_path = str(config_path)
        self._rclone_checked = False
        # מצב failover: ענן נוכחי, מקום פנוי ידוע, בייטים שהועלו, מעברים.
        self.current_remote = self.remote_names[0]
        self._remote_free = {}
        self.bytes_uploaded = 0
        self.uploads_per_remote = {name: 0 for name in self.remote_names}
        self.switches = []

    def connect(self):
        logger.info("בודק התקנת rclone...")
        try:
            result = subprocess.run(
                ["rclone", "version"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                logger.error(f"rclone לא מותקן: {result.stderr}")
                return False
            self._rclone_checked = True
            version = result.stdout.splitlines()[0] if result.stdout else "?"
            logger.success(f"rclone מותקן ({version})")
            return True
        except FileNotFoundError:
            logger.error("rclone לא נמצא במערכת. יש להתקין: curl https://rclone.org/install.sh | sudo bash")
            return False
        except OSError as exc:
            logger.error(f"שגיאה בבדיקת rclone: {exc}")
            return False

    def _run_rclone(self, args, timeout=120):
        if not self._rclone_checked:
            if not self.connect():
                raise RuntimeError("rclone לא זמין")
        cmd = ["rclone"] + args + ["--config", self.config_path]
        logger.debug(f"רץ: {' '.join(cmd)}")
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )

    def get_usage(self, remote):
        """מחזיר {'used','total','free','pct'} או None אם לא ניתן למדוד."""
        try:
            result = self._run_rclone(["about", "--json", f"{remote}:"], timeout=60)
        except OSError:
            return None
        if result.returncode != 0:
            return None
        try:
            data = json.loads(result.stdout or "{}")
            total = int(data.get("total") or 0)
            used = int(data.get("used") or 0)
            free = data.get("free")
            free = int(free) if free is not None else max(total - used, 0)
            pct = (used / total) if total > 0 else 0.0
            return {"used": used, "total": total, "free": free, "pct": pct}
        except (ValueError, TypeError):
            return None

    @staticmethod
    def is_quota_error(text):
        text_l = (text or "").lower()
        return any(tok in text_l for tok in RcloneUploader.QUOTA_TOKENS)

    def select_initial(self):
        """בוחר ענן ראשון מתחת לסף. מחזיר שם או None אם אין מקום/גישה."""
        for remote in self.remote_names:
            usage = self.get_usage(remote)
            if usage is None:
                logger.warning(f"לא ניתן למדוד מקום ב-{remote}, מדלג")
                continue
            self._remote_free[remote] = usage["free"]
            logger.info(f"מקום ב-{remote}: {usage['pct'] * 100:.1f}% בשימוש")
            if usage["pct"] < self.MAX_USAGE:
                self.current_remote = remote
                logger.info(f"נבחר ענן להתחלה: {remote}")
                return remote
            logger.warning(f"{remote} מלא ({usage['pct'] * 100:.1f}%) - עובר לבא בתור")
        logger.error("כל העננים מלאים או לא זמינים")
        return None

    def _estimated_remaining(self, remote):
        free = self._remote_free.get(remote)
        if free is None:
            return None
        if remote == self.current_remote:
            return free - self.bytes_uploaded
        return free

    def _switch_remote(self, reason):
        """עובר לענן הבא עם מקום. מחזיר True אם נמצא, אחרת False."""
        tried = {self.current_remote}
        for remote in self.remote_names:
            if remote in tried:
                continue
            usage = self.get_usage(remote)
            if usage is None:
                continue
            self._remote_free[remote] = usage["free"]
            if usage["pct"] < self.MAX_USAGE:
                old = self.current_remote
                self.current_remote = remote
                self.switches.append({"from": old, "to": remote, "reason": reason})
                logger.warning(f"עובר ענן מ-{old} ל-{remote} (סיבה: {reason})")
                return True
        logger.error("אין ענן פנוי לעבור אליו")
        return False

    def _ensure_room(self, size):
        """בודק שיש מקום משוער. אם לא — מנסה לעבור ענן."""
        remaining = self._estimated_remaining(self.current_remote)
        if remaining is None:
            return True
        if remaining - size >= self.RESERVE_BYTES:
            return True
        logger.warning(
            f"מקום משוער ב-{self.current_remote} לא מספיק ({remaining // 1024 // 1024}MB) - מחפש ענן אחר"
        )
        return self._switch_remote("estimated-full")

    def upload_file(self, local_path, remote_path, force_overwrite=False):
        local_path = Path(local_path)
        if not local_path.exists():
            logger.error(f"הקובץ המקומי לא קיים: {local_path}")
            return False

        remote_path = remote_path.replace("\\", "/")
        if remote_path.startswith("/"):
            remote_path = remote_path[1:]

        try:
            size = local_path.stat().st_size
        except OSError:
            size = 0

        tried_remotes = set()
        while True:
            if not self._ensure_room(size):
                return False
            if self.current_remote in tried_remotes and len(tried_remotes) >= len(self.remote_names):
                logger.error("כל העננים נוסו ללא הצלחה")
                return False
            tried_remotes.add(self.current_remote)
            dest = f"{self.current_remote}:{remote_path}"

            try:
                outcome = self._attempt_upload(local_path, dest)
            except InfrastructureError:
                if len(self.remote_names) > 1 and self._switch_remote("infra"):
                    continue
                raise
            if outcome == "ok":
                self.bytes_uploaded += size
                self.uploads_per_remote[self.current_remote] = self.uploads_per_remote.get(self.current_remote, 0) + 1
                return True
            if outcome == "quota":
                if not self._switch_remote("quota"):
                    return False
                continue
            return False

    def _attempt_upload(self, local_path, dest):
        """ניסיונות מול ענן אחד. מחזיר 'ok'/'quota'/'fail'; שגיאת תשתית נזרקת."""
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = self._run_rclone(
                    ["copyto", str(local_path), dest],
                    timeout=300,
                )
                if result.returncode == 0:
                    size = local_path.stat().st_size
                    logger.debug(f"הועלה בהצלחה: {dest} ({size} בייטים)")
                    return "ok"
                err = (result.stderr or "").strip()
                err_l = err.lower()
                logger.warning(f"rclone copy נכשל (ניסיון {attempt}): {err}")

                if self.is_quota_error(err):
                    logger.warning(f"זוהתה שגיאת מכסה: {err}")
                    return "quota"

                # Detect non-retryable infrastructure/auth errors
                non_retryable_tokens = [
                    "401",
                    "403",
                    "permission denied",
                    "authentication",
                    "auth",
                    "invalid token",
                    "failed to create file system",
                    "failed to create backend",
                    "access denied",
                ]
                if any(tok in err_l for tok in non_retryable_tokens) or result.returncode in (2, 5):
                    logger.error(f"rclone reported an infrastructure error: {err} E-UP-001")
                    raise InfrastructureError(err)

                if attempt < self.MAX_RETRIES:
                    import time
                    time.sleep(self.RETRY_DELAY)
            except subprocess.TimeoutExpired:
                logger.warning(f"rclone copy תם הזמן הקצוב (ניסיון {attempt})")
                if attempt < self.MAX_RETRIES:
                    import time
                    time.sleep(self.RETRY_DELAY)
            except OSError as exc:
                logger.error(f"שגיאת מערכת: {exc}")
                return "fail"
        return "fail"

    def _ensure_folder_exists(self, folder_path):
        folder_path = folder_path.replace("\\", "/")
        if folder_path.startswith("/"):
            folder_path = folder_path[1:]
        if not folder_path:
            return True
        try:
            result = self._run_rclone(
                ["mkdir", f"{self.remote_name}:{folder_path}"],
                timeout=30,
            )
            return result.returncode == 0
        except OSError:
            return False

    def file_exists(self, remote_path):
        remote_path = remote_path.replace("\\", "/")
        if remote_path.startswith("/"):
            remote_path = remote_path[1:]
        parent = str(Path(remote_path).parent).replace("\\", "/")
        filename = Path(remote_path).name
        if not parent or parent == ".":
            parent = ""
        try:
            rclone_path = f"{self.remote_name}:{parent}" if parent else f"{self.remote_name}:"
            result = self._run_rclone(
                ["lsjson", rclone_path],
                timeout=30,
            )
            if result.returncode != 0:
                return False
            files = json.loads(result.stdout)
            return any(f.get("Name") == filename for f in files)
        except (OSError, json.JSONDecodeError):
            return False

    def get_folder_path_for_date(self, date_str, folder_name):
        safe_folder = self._sanitize(folder_name)
        return f"/Instagram/{date_str}/{safe_folder}"

    @staticmethod
    def _sanitize(name):
        invalid = '<>:"/\\|?*'
        return "".join("_" if c in invalid else c for c in str(name)).strip().strip(".") or "unknown"
