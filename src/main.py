import csv
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .dropbox_uploader import DropboxUploader
from .logger import logger
from .rclone_uploader import RcloneUploader
from .state_manager import StateManager
from .story_downloader import StoryDownloader


USERNAMES_FILE = "usernames.txt"
USERNAMES_CSV = "usernames.csv"
USERNAMES_XLSX = "usernames.xlsx"
MIN_DELAY_BETWEEN_USERS = 2
MAX_DELAY_BETWEEN_USERS = 3
DELAY_AFTER_ERROR = 30


def _parse_txt(path):
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "|" in line:
                parts = [p.strip() for p in line.split("|", 1)]
                display_name = parts[0]
                username = parts[1].lstrip("@").strip()
                if not display_name:
                    display_name = username
                if not username:
                    continue
            else:
                username = line.lstrip("@").strip()
                if not username:
                    continue
                display_name = username
            entries.append((display_name, username))
    return entries


def _parse_csv(path):
    entries = []
    encodings = ["utf-8-sig", "utf-8", "cp1255", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    return entries
                username_col = 0
                display_col = 1 if len(header) > 1 else None
                for row in reader:
                    if not row or not row[0].strip():
                        continue
                    username = row[username_col].strip().lstrip("@")
                    if not username:
                        continue
                    if display_col is not None and len(row) > display_col and row[display_col].strip():
                        display_name = row[display_col].strip()
                    else:
                        display_name = username
                    entries.append((display_name, username))
            break
        except UnicodeDecodeError:
            continue
    else:
        logger.warning(f"לא ניתן לקרוא את {path} באף קידוד")
    return entries


def _parse_xlsx(path):
    entries = []
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl לא מותקן. הרץ: pip install openpyxl")
        return entries
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return entries
        header = rows[0]
        username_col = 0
        display_col = 1 if len(header) > 1 else None
        for row in rows[1:]:
            if not row or not row[username_col]:
                continue
            username = str(row[username_col]).strip().lstrip("@")
            if not username:
                continue
            if display_col is not None and len(row) > display_col and row[display_col]:
                display_name = str(row[display_col]).strip()
            else:
                display_name = username
            entries.append((display_name, username))
        wb.close()
    except Exception as exc:
        logger.warning(f"שגיאה בקריאת {path}: {exc}")
    return entries


def load_usernames():
    all_entries = []

    txt_path = Path(USERNAMES_FILE)
    if txt_path.exists():
        entries = _parse_txt(txt_path)
        all_entries.extend(entries)
        logger.info(f"נקראו {len(entries)} משתמשים מ-{USERNAMES_FILE}")
    else:
        logger.debug(f"קובץ {USERNAMES_FILE} לא קיים, מדלג")

    csv_path = Path(USERNAMES_CSV)
    if csv_path.exists():
        entries = _parse_csv(csv_path)
        all_entries.extend(entries)
        logger.info(f"נקראו {len(entries)} משתמשים מ-{USERNAMES_CSV}")

    xlsx_path = Path(USERNAMES_XLSX)
    if xlsx_path.exists():
        entries = _parse_xlsx(xlsx_path)
        all_entries.extend(entries)
        logger.info(f"נקראו {len(entries)} משתמשים מ-{USERNAMES_XLSX}")

    if not all_entries:
        logger.error("לא נמצאו שמות משתמש באף קובץ (txt/csv/xlsx)")
        return []

    seen = set()
    unique_entries = []
    for display_name, username in all_entries:
        if username not in seen:
            seen.add(username)
            unique_entries.append((display_name, username))

    logger.info(f"נטענו {len(unique_entries)} שמות משתמש ייחודיים (סה\"כ)")
    return unique_entries


def get_today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def random_delay():
    return random.randint(MIN_DELAY_BETWEEN_USERS, MAX_DELAY_BETWEEN_USERS)


def process_user(username, downloader, uploader, state, force_redownload, folder_name=None):
    logger.section(f"מעבד את @{username}")

    result = downloader.download_stories(username, folder_name=folder_name)
    if not result["success"]:
        logger.warning(f"דילוג על @{username} עקב שגיאה: {result.get('error')}")
        return {"downloaded": 0, "uploaded": 0, "skipped": 0, "error": result.get("error")}

    files = result["files"]
    if not files:
        return {"downloaded": 0, "uploaded": 0, "skipped": 0, "error": None}

    today = get_today_str()
    folder_path = uploader.get_folder_path_for_date(today, folder_name or username)

    stats = {"downloaded": len(files), "uploaded": 0, "skipped": 0, "error": None}

    for idx, local_file in enumerate(files, 1):
        story_id = downloader.extract_story_id(local_file.name)
        dropbox_path = f"{folder_path}/{local_file.name}"

        if not force_redownload and state.is_uploaded(username, story_id):
            logger.info(f"  [{idx}/{len(files)}] כבר הועלה: {local_file.name}")
            stats["skipped"] += 1
            try:
                local_file.unlink()
            except OSError:
                pass
            continue

        logger.info(f"  [{idx}/{len(files)}] מעלה: {local_file.name}")
        success = uploader.upload_file(local_file, dropbox_path)

        if success:
            state.mark_uploaded(
                username=username,
                story_id=story_id,
                filename=local_file.name,
                dropbox_path=dropbox_path,
            )
            stats["uploaded"] += 1
            try:
                local_file.unlink()
            except OSError:
                pass
        else:
            logger.error(f"  נכשל בהעלאת {local_file.name}")
            stats["error"] = "upload_failed"

    return stats


def main():
    logger.section("🚀 מתחיל סנכרון סטוריז מאינסטגרם לדרופבוקס")
    logger.info(f"זמן התחלה: {datetime.now(timezone.utc).isoformat()}")

    force_redownload = os.environ.get("FORCE_REDOWNLOAD", "false").lower() == "true"
    if force_redownload:
        logger.warning("מצב כפוי: כל הקבצים יועלו מחדש ללא בדיקת כפילויות")

    storage_backend = os.environ.get("STORAGE_BACKEND", "dropbox").lower()
    logger.info(f"שירות אחסון: {storage_backend}")

    if storage_backend == "onedrive":
        rclone_config = os.environ.get("RCLONE_CONF_PATH", "rclone.conf")
        if not os.environ.get("RCLONE_CONF_PATH") and not os.path.exists("rclone.conf"):
            logger.error(
                "חסר קובץ תצורת rclone ל-OneDrive. "
                "יש להגדיר RCLONE_CONF_BASE64 ב-Secrets (ראה SETUP.md)"
            )
            sys.exit(1)
        uploader = RcloneUploader(config_path=rclone_config)
    else:
        app_key = os.environ.get("DROPBOX_APP_KEY")
        app_secret = os.environ.get("DROPBOX_APP_SECRET")
        dbx_refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
        if not all([app_key, app_secret, dbx_refresh_token]):
            logger.error(
                "חסרים משתני סביבה. "
                "יש להגדיר DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN"
            )
            sys.exit(1)
        uploader = DropboxUploader(app_key, app_secret, dbx_refresh_token)

    user_entries = load_usernames()
    if not user_entries:
        logger.error("לא נמצאו שמות משתמשים באף קובץ (usernames.txt / usernames.csv / usernames.xlsx)")
        sys.exit(1)

    state = StateManager()
    downloader = StoryDownloader()

    if not downloader.check_binary():
        logger.error("Playwright לא מותקן כראוי. בדוק את שלב ההתקנה ב-workflow.")
        sys.exit(1)

    if not uploader.connect():
        logger.error("לא ניתן להתחבר לדרופבוקס. בדוק את ה-Secrets.")
        sys.exit(1)

    total_stats = {
        "users_processed": 0,
        "users_failed": 0,
        "files_downloaded": 0,
        "files_uploaded": 0,
        "files_skipped": 0,
    }

    total = len(user_entries)
    for idx, (display_name, username) in enumerate(user_entries, 1):
        logger.progress(idx, total, prefix="התקדמות")
        stats = {"downloaded": 0, "uploaded": 0, "skipped": 0, "error": None}
        try:
            stats = process_user(username, downloader, uploader, state, force_redownload, folder_name=display_name)
            total_stats["users_processed"] += 1
            total_stats["files_downloaded"] += stats.get("downloaded", 0)
            total_stats["files_uploaded"] += stats.get("uploaded", 0)
            total_stats["files_skipped"] += stats.get("skipped", 0)
            if stats.get("error"):
                total_stats["users_failed"] += 1
        except Exception as exc:
            logger.error(f"שגיאה לא צפויה בעיבוד @{username}: {exc}")
            total_stats["users_failed"] += 1

        downloader.cleanup(folder_name=display_name)

        if idx < total:
            if stats.get("error") == "rate_limit":
                wait = DELAY_AFTER_ERROR
                logger.warning(f"ממתין {wait} שניות אחרי שגיאת rate_limit")
            else:
                wait = random_delay()
                logger.info(f"ממתין {wait} שניות לפני המשתמש הבא")
            time.sleep(wait)

    state.save()

    logger.section("📊 סיכום")
    logger.info(f"משתמשים שעובדו: {total_stats['users_processed']}/{total}")
    logger.info(f"משתמשים עם שגיאות: {total_stats['users_failed']}")
    logger.info(f"קבצים שהורדו: {total_stats['files_downloaded']}")
    logger.info(f"קבצים שהועלו: {total_stats['files_uploaded']}")
    logger.info(f"קבצים שדולגו (כבר היו): {total_stats['files_skipped']}")
    overall = state.get_stats()
    logger.info(f"סה\"כ קבצים במעקב: {overall['total_uploaded']} (עבור {overall['tracked_users']} משתמשים)")

    failed = total_stats["users_failed"]
    if failed == 0:
        logger.success("הסנכרון הסתיים בהצלחה - כל המשתמשים עובדו")
        sys.exit(0)
    elif failed == total:
        logger.error(f"הסנכרון נכשל - כל {total} המשתמשים נכשלו")
        sys.exit(1)
    else:
        logger.warning(f"הסנכרון הסתיים עם {failed} שגיאות מתוך {total} משתמשים")
        sys.exit(0)


if __name__ == "__main__":
    main()
