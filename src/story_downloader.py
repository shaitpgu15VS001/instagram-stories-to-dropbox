import re
import shutil
import subprocess
from pathlib import Path

from .logger import logger


STORIES_DIR = Path("stories")
FABULA_BINARY = Path(shutil.which("fabula") or "./fabula")
FABULA_TIMEOUT = 180

MEDIA_EXTENSIONS = {".mp4", ".jpg", ".jpeg", ".png", ".webp", ".mov"}


class StoryDownloader:

    def __init__(self, binary_path=FABULA_BINARY, output_dir=STORIES_DIR):
        self.binary_path = Path(binary_path)
        self.output_dir = Path(output_dir)

    def check_binary(self):
        if self.binary_path.exists():
            binary_name = str(self.binary_path)
        else:
            binary_name = shutil.which("fabula")
        if not binary_name:
            logger.error("הבינארי של fabula לא נמצא. ודא ש-fabula מותקן וזמין ב-PATH")
            return False
        try:
            result = subprocess.run(
                [binary_name, "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as exc:
            logger.error(f"שגיאה בבדיקת fabula: {exc}")
            return False

    def download_stories(self, username):
        username = username.strip().lstrip("@")
        if not username:
            return {"success": False, "files": [], "error": "שם משתמש ריק"}

        user_dir = self.output_dir / username
        user_dir.mkdir(parents=True, exist_ok=True)

        for item in user_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
            except OSError as exc:
                logger.warning(f"לא ניתן למחוק {item}: {exc}")

        cmd = [
            str(self.binary_path),
            f"-username={username}",
            "-option=story",
        ]

        logger.info(f"מוריד סטוריז עבור @{username}...")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=FABULA_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"פג הזמן בהורדת סטוריז עבור @{username}")
            return {"success": False, "files": [], "error": "timeout"}
        except OSError as exc:
            logger.error(f"שגיאה בהפעלת fabula: {exc}")
            return {"success": False, "files": [], "error": str(exc)}

        stderr = (result.stderr or "").lower()
        stdout = (result.stdout or "")

        if "private" in stderr or "private" in stdout.lower():
            logger.warning(f"@{username} הוא חשבון פרטי - לא ניתן להוריד סטוריז")
            return {"success": False, "files": [], "error": "private_account"}
        if "not found" in stderr or "404" in stderr or "not found" in stdout.lower():
            logger.warning(f"@{username} לא נמצא")
            return {"success": False, "files": [], "error": "user_not_found"}
        if "rate" in stderr or "limit" in stderr:
            logger.warning(f"הגבלת קצב מ-storiesig.info עבור @{username}")
            return {"success": False, "files": [], "error": "rate_limit"}

        files = self._scan_downloaded_files(user_dir)
        if not files:
            logger.info(f"@{username}: אין סטוריז פעילים כרגע")
            return {"success": True, "files": [], "error": None}

        logger.success(f"@{username}: הורדו {len(files)} קבצים")
        return {"success": True, "files": files, "error": None}

    def _scan_downloaded_files(self, directory):
        files = []
        if not directory.exists():
            return files

        for item in sorted(directory.iterdir()):
            if not item.is_file():
                continue
            if item.suffix.lower() not in MEDIA_EXTENSIONS:
                continue
            files.append(item)
        return files

    def extract_story_id(self, filename):
        name = Path(filename).stem
        match = re.match(r"^(\d{10,25})$", name)
        if match:
            return match.group(1)
        return name

    def cleanup(self, username=None):
        if username:
            target = self.output_dir / username
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
        else:
            if self.output_dir.exists():
                shutil.rmtree(self.output_dir, ignore_errors=True)
