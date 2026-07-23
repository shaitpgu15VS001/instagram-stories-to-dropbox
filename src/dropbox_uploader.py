import os
import time
from pathlib import Path

import dropbox
from dropbox.exceptions import ApiError, AuthError, DropboxException

from .logger import logger


class DropboxUploader:

    MAX_RETRIES = 3
    RETRY_DELAY = 5
    CHUNK_SIZE = 8 * 1024 * 1024

    def __init__(self, app_key, app_secret, refresh_token):
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token
        self._dbx = None

    def connect(self):
        if not all([self.app_key, self.app_secret, self.refresh_token]):
            raise ValueError(
                "חסרים פרטי התחברות לדרופבוקס. "
                "ודא שהוגדרו DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN"
            )

        logger.info("מתחבר לדרופבוקס...")
        try:
            self._dbx = dropbox.Dropbox(
                app_key=self.app_key,
                app_secret=self.app_secret,
                oauth2_refresh_token=self.refresh_token,
            )
            account = self._dbx.users_get_current_account()
            logger.success(
                f"מחובר לדרופבוקס בהצלחה כ-{account.email}"
            )
            return True
        except AuthError as exc:
            logger.error(f"שגיאת אימות בדרופבוקס: {exc}")
            return False
        except DropboxException as exc:
            logger.error(f"שגיאת דרופבוקס: {exc}")
            return False

    def _get_client(self):
        if self._dbx is None:
            if not self.connect():
                raise RuntimeError("לא ניתן להתחבר לדרופבוקס")
        return self._dbx

    def upload_file(self, local_path, dropbox_path, force_overwrite=False):
        local_path = Path(local_path)
        if not local_path.exists():
            logger.error(f"הקובץ המקומי לא קיים: {local_path}")
            return False

        if not dropbox_path.startswith("/"):
            dropbox_path = "/" + dropbox_path

        dbx = self._get_client()
        file_size = local_path.stat().st_size
        mode = dropbox.files.WriteMode.overwrite if force_overwrite else dropbox.files.WriteMode.add

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                with open(local_path, "rb") as f:
                    if file_size <= self.CHUNK_SIZE:
                        data = f.read()
                        dbx.files_upload(
                            data,
                            dropbox_path,
                            mode=mode,
                            autorename=not force_overwrite,
                            mute=True,
                        )
                    else:
                        upload_session_start_result = dbx.files_upload_session_start(
                            f.read(self.CHUNK_SIZE)
                        )
                        cursor = dropbox.files.UploadSessionCursor(
                            session_id=upload_session_start_result.session_id,
                            offset=f.tell(),
                        )
                        commit = dropbox.files.CommitInfo(
                            path=dropbox_path,
                            mode=mode,
                            autorename=not force_overwrite,
                            mute=True,
                        )

                        while f.tell() < file_size:
                            if (file_size - f.tell()) <= self.CHUNK_SIZE:
                                dbx.files_upload_session_finish(
                                    f.read(self.CHUNK_SIZE), cursor, commit
                                )
                            else:
                                dbx.files_upload_session_append(
                                    f.read(self.CHUNK_SIZE), cursor
                                )
                                cursor.offset = f.tell()

                logger.debug(f"הועלה בהצלחה: {dropbox_path} ({file_size} בייטים)")
                return True

            except ApiError as exc:
                error_str = str(exc).lower()
                if "path" in error_str and "not_found" in error_str:
                    logger.warning(f"תיקיית יעד לא קיימת, מנסה ליצור: {dropbox_path}")
                    self._ensure_folder_exists(str(Path(dropbox_path).parent))
                    continue
                if "rate" in error_str or "too_many" in error_str:
                    wait = self.RETRY_DELAY * attempt * 2
                    logger.warning(
                        f"הגבלת קצב, ממתין {wait} שניות לפני ניסיון {attempt}/{self.MAX_RETRIES}"
                    )
                    time.sleep(wait)
                    continue
                logger.error(f"שגיאת API בהעלאה: {exc}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    continue
                return False

            except (OSError, DropboxException) as exc:
                logger.error(f"שגיאה בהעלאת {local_path}: {exc}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(self.RETRY_DELAY)
                    continue
                return False

        return False

    def _ensure_folder_exists(self, folder_path):
        if not folder_path or folder_path == "/":
            return True
        folder_path = str(folder_path).rstrip("/")
        if not folder_path:
            return True

        dbx = self._get_client()
        try:
            dbx.files_get_metadata(folder_path)
            return True
        except ApiError:
            pass

        parts = folder_path.split("/")
        current = ""
        for part in parts:
            if not part:
                continue
            current = f"{current}/{part}"
            try:
                dbx.files_create_folder_v2(current)
            except ApiError as exc:
                if "path" in str(exc).lower() and "conflict" in str(exc).lower():
                    continue
                logger.error(f"שגיאה ביצירת תיקייה {current}: {exc}")
                return False
        return True

    def file_exists(self, dropbox_path):
        if not dropbox_path.startswith("/"):
            dropbox_path = "/" + dropbox_path
        try:
            dbx = self._get_client()
            dbx.files_get_metadata(dropbox_path)
            return True
        except ApiError as exc:
            if "not_found" in str(exc).lower():
                return False
            logger.warning(f"שגיאה בבדיקת קיום קובץ: {exc}")
            return False

    def get_folder_path_for_date(self, date_str, folder_name):
        safe_folder = self._sanitize(folder_name)
        return f"/Instagram/{date_str}/{safe_folder}"

    @staticmethod
    def _sanitize(name):
        invalid = '<>:"/\\|?*'
        cleaned = "".join("_" if c in invalid else c for c in str(name))
        return cleaned.strip().strip(".") or "unknown"
