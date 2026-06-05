import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .dropbox_uploader import DropboxUploader
from .logger import logger
from .state_manager import StateManager
from .story_downloader import StoryDownloader


USERNAMES_FILE = "usernames.txt"
MIN_DELAY_BETWEEN_USERS = 2
MAX_DELAY_BETWEEN_USERS = 3
DELAY_AFTER_ERROR = 30


def load_usernames(file_path=USERNAMES_FILE):
    path = Path(file_path)
    if not path.exists():
        logger.error(f"קובץ שמות המשתמשים לא נמצא: {path}")
        return []

    usernames = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            username = line.lstrip("@").strip()
            if username:
                usernames.append(username)

    unique = list(dict.fromkeys(usernames))
    logger.info(f"נטענו {len(unique)} שמות משתמש ייחודיים")
    return unique


def get_today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def random_delay():
    return random.randint(MIN_DELAY_BETWEEN_USERS, MAX_DELAY_BETWEEN_USERS)


def process_user(username, downloader, uploader, state, force_redownload):
    logger.section(f"מעבד את @{username}")

    result = downloader.download_stories(username)
    if not result["success"]:
        logger.warning(f"דילוג על @{username} עקב שגיאה: {result.get('error')}")
        return {"downloaded": 0, "uploaded": 0, "skipped": 0, "error": result.get("error")}

    files = result["files"]
    if not files:
        return {"downloaded": 0, "uploaded": 0, "skipped": 0, "error": None}

    today = get_today_str()
    folder_path = uploader.get_folder_path_for_date(today, username)

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

    app_key = os.environ.get("DROPBOX_APP_KEY")
    app_secret = os.environ.get("DROPBOX_APP_SECRET")
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")

    if not all([app_key, app_secret, refresh_token]):
        logger.error(
            "חסרים משתני סביבה. יש להגדיר DROPBOX_APP_KEY, DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN"
        )
        sys.exit(1)

    usernames = load_usernames()
    if not usernames:
        logger.error("לא נמצאו שמות משתמשים ב-usernames.txt")
        sys.exit(1)

    state = StateManager()
    downloader = StoryDownloader()
    uploader = DropboxUploader(app_key, app_secret, refresh_token)

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

    total = len(usernames)
    for idx, username in enumerate(usernames, 1):
        logger.progress(idx, total, prefix="התקדמות")
        stats = {"downloaded": 0, "uploaded": 0, "skipped": 0, "error": None}
        try:
            stats = process_user(username, downloader, uploader, state, force_redownload)
            total_stats["users_processed"] += 1
            total_stats["files_downloaded"] += stats.get("downloaded", 0)
            total_stats["files_uploaded"] += stats.get("uploaded", 0)
            total_stats["files_skipped"] += stats.get("skipped", 0)
            if stats.get("error"):
                total_stats["users_failed"] += 1
        except Exception as exc:
            logger.error(f"שגיאה לא צפויה בעיבוד @{username}: {exc}")
            total_stats["users_failed"] += 1

        downloader.cleanup(username)

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
