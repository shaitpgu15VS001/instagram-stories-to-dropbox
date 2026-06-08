import json
import subprocess
from pathlib import Path

from .logger import logger


RCLONE_NAME = "onedrive"


class RcloneUploader:

    MAX_RETRIES = 3
    RETRY_DELAY = 5

    def __init__(self, config_path="rclone.conf"):
        self.config_path = str(config_path)
        self._rclone_checked = False

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

    def upload_file(self, local_path, remote_path, force_overwrite=False):
        local_path = Path(local_path)
        if not local_path.exists():
            logger.error(f"הקובץ המקומי לא קיים: {local_path}")
            return False

        remote_path = remote_path.replace("\\", "/")
        if remote_path.startswith("/"):
            remote_path = remote_path[1:]

        dest = f"{RCLONE_NAME}:{remote_path}"

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                result = self._run_rclone(
                    ["copyto", str(local_path), dest],
                    timeout=300,
                )
                if result.returncode == 0:
                    size = local_path.stat().st_size
                    logger.debug(f"הועלה בהצלחה: {remote_path} ({size} בייטים)")
                    return True
                err = result.stderr.strip()
                logger.warning(f"rclone copy נכשל (ניסיון {attempt}): {err}")
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
                return False
        return False

    def _ensure_folder_exists(self, folder_path):
        folder_path = folder_path.replace("\\", "/")
        if folder_path.startswith("/"):
            folder_path = folder_path[1:]
        if not folder_path:
            return True
        try:
            result = self._run_rclone(
                ["mkdir", f"{RCLONE_NAME}:{folder_path}"],
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
            rclone_path = f"{RCLONE_NAME}:{parent}" if parent else f"{RCLONE_NAME}:"
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

    def get_folder_path_for_date(self, date_str, username):
        safe_username = self._sanitize(username)
        return f"/Instagram/{date_str}/{safe_username}"

    @staticmethod
    def _sanitize(name):
        invalid = '<>:"/\\|?*'
        return "".join("_" if c in invalid else c for c in str(name)).strip().strip(".") or "unknown"
