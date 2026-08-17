import csv
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .logger import logger
from .rclone_uploader import RcloneUploader, InfrastructureError
from .state_manager import StateManager
from .story_downloader import StoryDownloader


USERNAMES_FILE = "usernames.txt"
USERNAMES_CSV = "usernames.csv"
USERNAMES_XLSX = "usernames.xlsx"
STORAGE_BACKEND_FILE = "STORAGE_BACKEND.txt"
RCLONE_CONF_FILE = "rclone.conf"
MIN_DELAY_BETWEEN_USERS = 2
MAX_DELAY_BETWEEN_USERS = 3
DELAY_AFTER_ERROR = 30


INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am"}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._]{0,28}[A-Za-z0-9_])?$")
HEADER_HINTS = {"username", "user", "account", "instagram", "name", "display"}


def _normalize_username(raw):
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    value = value.split()[0].strip()
    value = value.lstrip("@").strip()
    if not value:
        return None

    candidate = value
    lower_value = candidate.lower()
    if lower_value.startswith(("http://", "https://")) or lower_value.startswith("www.") or "instagram.com" in lower_value or "instagr.am" in lower_value:
        if not re.match(r"^https?://", lower_value):
            candidate = "https://" + candidate
        try:
            parts = urlsplit(candidate)
        except Exception:
            return None
        host = (parts.hostname or "").lower()
        if host not in INSTAGRAM_HOSTS:
            return None
        segments = [seg for seg in (parts.path or "").split("/") if seg.strip()]
        if not segments:
            return None
        username = segments[0]
    elif "/" in candidate:
        username = candidate.split("/", 1)[0]
    else:
        username = candidate

    username = str(username).strip().lstrip("@").strip().lower().rstrip(".")
    if not username:
        return None
    if any(char in username for char in " \\/:@"):  # invalid path or username chars
        return None
    if not USERNAME_PATTERN.match(username):
        return None
    return username


def _is_header_row(row_values):
    values = [str(value).strip().lower() for value in row_values if value is not None and str(value).strip()]
    if not values:
        return False
    return all(any(hint in value for hint in HEADER_HINTS) for value in values)


def _normalize_row_name(row):
    if not row:
        return None, None

    first_cell = row[0] if len(row) > 0 else None
    username = _normalize_username(first_cell) if first_cell is not None else None
    if username:
        display_name = str(row[1]).strip() if len(row) > 1 and row[1] is not None and str(row[1]).strip() else username
        return username, display_name

    for extra in row[1:]:
        if extra is None:
            continue
        username = _normalize_username(extra)
        if username:
            return username, username

    return None, None


def _build_source_summary(source_name, stats):
    logger.info(f"{source_name}:")
    logger.info(f"  {stats['raw_records']} רשומות")
    logger.info(f"  {stats['valid_records']} משתמשים תקינים")
    if stats["invalid_records"]:
        logger.info(f"  {stats['invalid_records']} רשומות לא תקינות")
    if stats["duplicate_count"]:
        logger.info(f"  {stats['duplicate_count']} כפילויות הוסרו")
    for example in stats.get("examples", []):
        logger.info(f"  {example}")


def _parse_txt(path):
    entries = []
    stats = {
        "raw_records": 0,
        "valid_records": 0,
        "invalid_records": 0,
        "duplicate_count": 0,
        "examples": [],
    }
    seen = set()

    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            raw_line = line.rstrip("\n")
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            stats["raw_records"] += 1
            if "|" in line:
                parts = [p.strip() for p in line.split("|", 1)]
                display_name = parts[0] or parts[1]
                username = _normalize_username(parts[1])
            else:
                display_name = line
                username = _normalize_username(line)

            if not username:
                stats["invalid_records"] += 1
                if len(stats["examples"]) < 5:
                    stats["examples"].append(f"שורה {lineno}: רשומה לא תקינה → {raw_line}")
                continue
            if username in seen:
                stats["duplicate_count"] += 1
                continue
            seen.add(username)
            stats["valid_records"] += 1
            if len(stats["examples"]) < 5 and line.lower().startswith(("http://", "https://", "www.", "instagram.com", "instagr.am")):
                stats["examples"].append(f"שורה {lineno}: URL זוהה → {username}")
            entries.append((display_name, username))

    if stats["raw_records"] or stats["examples"]:
        _build_source_summary("TXT", stats)
    return entries, stats


def _parse_csv(path):
    entries = []
    stats = {
        "raw_records": 0,
        "valid_records": 0,
        "invalid_records": 0,
        "duplicate_count": 0,
        "examples": [],
    }
    seen = set()
    encodings = ["utf-8-sig", "utf-8", "cp1255", "cp1252", "latin-1"]

    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                reader = csv.reader(f)
                for row_num, row in enumerate(reader, start=1):
                    if not row or all(not str(cell).strip() for cell in row):
                        continue
                    if row_num == 1 and _is_header_row(row):
                        continue
                    stats["raw_records"] += 1
                    username, display_name = _normalize_row_name(row)
                    raw_value = next((str(cell).strip() for cell in row if cell is not None and str(cell).strip()), "")
                    if not username:
                        stats["invalid_records"] += 1
                        if len(stats["examples"]) < 5:
                            stats["examples"].append(f"שורה {row_num}: רשומה לא תקינה → {raw_value}")
                        continue
                    if username in seen:
                        stats["duplicate_count"] += 1
                        continue
                    seen.add(username)
                    stats["valid_records"] += 1
                    if len(stats["examples"]) < 5 and raw_value.lower().startswith(("http://", "https://", "www.", "instagram.com", "instagr.am")):
                        stats["examples"].append(f"שורה {row_num}: URL זוהה → {username}")
                    entries.append((display_name, username))
            break
        except UnicodeDecodeError:
            continue
    else:
        logger.warning(f"לא ניתן לקרוא את {path} באף קידוד")
    if stats["raw_records"] or stats["examples"]:
        _build_source_summary("CSV", stats)
    return entries, stats


def _parse_xlsx(path):
    entries = []
    stats = {
        "raw_records": 0,
        "valid_records": 0,
        "invalid_records": 0,
        "duplicate_count": 0,
        "examples": [],
    }
    seen = set()
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl לא מותקן. הרץ: pip install openpyxl")
        return entries, stats
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        for row_num, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if not row or all(cell is None or not str(cell).strip() for cell in row):
                continue
            if row_num == 1 and _is_header_row(row):
                continue
            stats["raw_records"] += 1
            username, display_name = _normalize_row_name(row)
            raw_value = next((str(cell).strip() for cell in row if cell is not None and str(cell).strip()), "")
            if not username:
                stats["invalid_records"] += 1
                if len(stats["examples"]) < 5:
                    stats["examples"].append(f"שורה {row_num}: רשומה לא תקינה → {raw_value}")
                continue
            if username in seen:
                stats["duplicate_count"] += 1
                continue
            seen.add(username)
            stats["valid_records"] += 1
            if len(stats["examples"]) < 5 and raw_value.lower().startswith(("http://", "https://", "www.", "instagram.com", "instagr.am")):
                stats["examples"].append(f"שורה {row_num}: URL זוהה → {username}")
            entries.append((display_name, username))
        wb.close()
    except Exception as exc:
        logger.warning(f"שגיאה בקריאת {path}: {exc}")
    if stats["raw_records"] or stats["examples"]:
        _build_source_summary("XLSX", stats)
    return entries, stats


def load_usernames():
    all_entries = []
    source_stats = {}

    logger.section("📥 טוען שמות משתמשים")

    txt_path = Path(USERNAMES_FILE)
    if txt_path.exists():
        entries, stats = _parse_txt(txt_path)
        all_entries.extend(entries)
        source_stats["TXT"] = stats
    else:
        logger.debug(f"קובץ {USERNAMES_FILE} לא קיים, מדלג")

    csv_path = Path(USERNAMES_CSV)
    if csv_path.exists():
        entries, stats = _parse_csv(csv_path)
        all_entries.extend(entries)
        source_stats["CSV"] = stats

    xlsx_path = Path(USERNAMES_XLSX)
    if xlsx_path.exists():
        entries, stats = _parse_xlsx(xlsx_path)
        all_entries.extend(entries)
        source_stats["XLSX"] = stats

    if not all_entries:
        logger.error("לא נמצאו שמות משתמש באף קובץ (txt/csv/xlsx)")
        return [], {}

    seen = set()
    unique_entries = []
    for display_name, username in all_entries:
        if username not in seen:
            seen.add(username)
            unique_entries.append((display_name, username))

    global_duplicates = len(all_entries) - len(unique_entries)
    load_stats = {
        "sources": source_stats,
        "total_raw_records": sum(stats["raw_records"] for stats in source_stats.values()),
        "total_valid_records": sum(stats["valid_records"] for stats in source_stats.values()),
        "total_invalid_records": sum(stats["invalid_records"] for stats in source_stats.values()),
        "total_duplicates": global_duplicates,
        "unique_usernames": len(unique_entries),
    }

    logger.info(f"נטענו {len(unique_entries)} שמות משתמש ייחודיים (סה\"כ)")
    if global_duplicates:
        logger.info(f"{global_duplicates} כפילויות נוספות הוסרו חוצות קבצים")

    return unique_entries, load_stats


def get_today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def random_delay():
    return random.randint(MIN_DELAY_BETWEEN_USERS, MAX_DELAY_BETWEEN_USERS)


def _detect_remotes(config_path=RCLONE_CONF_FILE):
    path = Path(config_path)
    if not path.exists():
        return []
    remotes = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                name = line[1:-1].strip()
                if name:
                    remotes.append(name)
    return remotes


def _read_default_remote(file_path=STORAGE_BACKEND_FILE):
    path = Path(file_path)
    if path.exists():
        name = path.read_text(encoding="utf-8").strip()
        if name:
            return name
    return None


def process_user(username, downloader, uploader, state, force_redownload, folder_name=None):
    logger.section(f"מעבד את @{username}")
    # Structured per-user start marker
    logger.info(f"USER_START username={username} run_id={getattr(logger, 'run_id', 'local')}")
    logger.info(f"PROCESSING username={username} folder_name={folder_name}")

    # ensure downloader has access to state for pre-download skipping
    try:
        downloader.state_manager = state
    except Exception:
        pass

    result = downloader.download_stories(username, folder_name=folder_name)
    if not result["success"]:
        err = result.get("error")
        # Map known downloader errors to Error IDs
        if isinstance(err, str) and ("api_error" in err or "timeout" in err):
            err_id = "E-FDL-001"
        else:
            err_id = "E-DL-001"
        logger.warning(f"דילוג על @{username} עקב שגיאה: {err} {err_id}")
        logger.info(f"USER_FINISHED username={username} status=FAILED error_id={err_id}")
        return {"downloaded": 0, "uploaded": 0, "skipped": 0, "error": err, "error_id": err_id}

    files = result["files"]
    if not files:
        return {"downloaded": 0, "uploaded": 0, "skipped": 0, "error": None}

    today = get_today_str()
    folder_path = uploader.get_folder_path_for_date(today, folder_name or username)

    stats = {"downloaded": len(files), "uploaded": 0, "skipped": 0, "error": None}

    meta = result.get('meta', {})
    for idx, local_file in enumerate(files, 1):
        story_id = downloader.extract_story_id(local_file.name)
        pre_id = meta.get(local_file.name)
        dropbox_path = f"{folder_path}/{local_file.name}"
        # Check both legacy instagram_id and new pre_download_id (uri_path)
        if not force_redownload and (pre_id and state.is_uploaded(username, pre_id) or (not pre_id and state.is_uploaded(username, story_id))):
            logger.info(f"  [{idx}/{len(files)}] כבר הועלה: {local_file.name}")
            stats["skipped"] += 1
            try:
                local_file.unlink()
            except OSError:
                pass
            continue

        logger.info(f"  [{idx}/{len(files)}] מעלה: {local_file.name}")
        folder_path = uploader.get_folder_path_for_date(today, folder_name or username)
        logger.info(f"UPLOAD DESTINATION username={username} folder_name={folder_name} destination={folder_path}/{local_file.name}")
        success = uploader.upload_file(local_file, dropbox_path)

        if success:
            state.mark_uploaded(
                username=username,
                story_id=story_id,
                filename=local_file.name,
                dropbox_path=dropbox_path,
                pre_download_id=pre_id,
            )
            saved = False
            try:
                state.save()
                saved = True
            except Exception as exc:
                logger.error(f"שגיאה בשמירת state אחרי העלאה: {exc} E-STATE-001")
                # Do not delete local file if state wasn't persisted
            stats["uploaded"] += 1
            if saved:
                try:
                    local_file.unlink()
                except OSError:
                    pass
        else:
            logger.error(f"  נכשל בהעלאת {local_file.name} E-UP-001")
            stats["error"] = "upload_failed"
            stats["error_id"] = "E-UP-001"

    logger.info(f"USER_FINISHED username={username} status=OK downloaded={stats['downloaded']} uploaded={stats['uploaded']} skipped={stats['skipped']}")
    return stats


def main():
    logger.section("🚀 מתחיל סנכרון סטוריז מאינסטגרם לדרופבוקס")
    # Initialize debug logging files early. Non-fatal if it fails.
    try:
        run_id = os.environ.get("GITHUB_RUN_ID")
        logger.init_debug(debug_dir="debug", run_id=run_id)
    except Exception:
        pass

    start_ts = datetime.now(timezone.utc)
    logger.info(f"זמן התחלה: {start_ts.isoformat()}")
    logger.info(f"SCROLL_DEBUG={os.environ.get('SCROLL_DEBUG')}")

    force_redownload = os.environ.get("FORCE_REDOWNLOAD", "false").lower() == "true"
    if force_redownload:
        logger.warning("מצב כפוי: כל הקבצים יועלו מחדש ללא בדיקת כפילויות")

    remote_from_env = os.environ.get("STORAGE_BACKEND", "").strip().lower()
    remote_from_file = _read_default_remote()
    remote_from_env = remote_from_env if remote_from_env else (remote_from_file or "")

    available = _detect_remotes()
    if not available:
        logger.error("לא נמצאו אחסונים בענן. יש להגדיר rclone.conf (ראה SETUP.md)")
        sys.exit(1)

    logger.info(f"אחסונים זמינים: {available}")

    if remote_from_env:
        if remote_from_env not in available:
            logger.warning(
                f"האחסון המבוקש '{remote_from_env}' לא נמצא ב-rclone.conf. "
                f"אפשרויות: {available}. בוחר אוטומטית..."
            )
            selected = available[0]
        else:
            selected = remote_from_env
    else:
        selected = available[0]

    logger.info(f"נבחר אחסון: {selected}")
    uploader = RcloneUploader(remote_name=selected, config_path=RCLONE_CONF_FILE)

    user_entries, load_stats = load_usernames()
    if not user_entries:
        logger.error("לא נמצאו שמות משתמשים באף קובץ (usernames.txt / usernames.csv / usernames.xlsx)")
        sys.exit(1)

    logger.section("📄 סיכום טעינת משתמשים")
    logger.info(f'סה"כ רשומות: {load_stats.get("total_raw_records", 0)}')
    logger.info(f'סה"כ משתמשים תקינים: {load_stats.get("total_valid_records", 0)}')
    if load_stats.get('total_invalid_records', 0):
        logger.info(f'סה"כ רשומות לא תקינות: {load_stats.get("total_invalid_records", 0)}')
    if load_stats.get('total_duplicates', 0):
        logger.info(f'סה"כ כפילויות: {load_stats.get("total_duplicates", 0)}')
    logger.info(f"משתמשים שנשארו לעיבוד: {len(user_entries)}")

    logger.section("🔗 מיפוי משתמשים")
    for idx, (display_name, username) in enumerate(user_entries, 1):
        logger.info(f"  {idx}. username={username}, folder_name={display_name}")

    state = StateManager()
    downloader = StoryDownloader()

    if not downloader.check_binary():
        logger.error("Playwright לא מותקן כראוי. בדוק את שלב ההתקנה ב-workflow.")
        sys.exit(1)

    if not uploader.connect():
        logger.error(f"לא ניתן להתחבר לאחסון '{selected}'. בדוק את rclone.conf.")
        sys.exit(1)

    total_stats = {
        "users_processed": 0,
        "users_failed": 0,
        "files_downloaded": 0,
        "files_uploaded": 0,
        "files_skipped": 0,
    }

    failed_users = []

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
                failed_users.append((username, stats.get("error_id") or stats.get("error")))
        except InfrastructureError as exc:
            logger.error(f"שגיאת תשתית קריטית ב-upload: {exc}")
            try:
                state.save()
            except Exception:
                logger.error("נכשלה שמירת state בזמן טיפול בשגיאת תשתית")
            sys.exit(1)
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
        exit_code = 0
    elif failed == total:
        logger.error(f"הסנכרון נכשל - כל {total} המשתמשים נכשלו")
        exit_code = 1
    else:
        logger.warning(f"הסנכרון הסתיים עם {failed} שגיאות מתוך {total} משתמשים")
        exit_code = 0

    # Write debug summary (safe)
    try:
        import platform

        end_ts = datetime.now(timezone.utc)
        summary = {
            "start_iso": start_ts.isoformat(),
            "end_iso": end_ts.isoformat(),
            "duration_seconds": int((end_ts - start_ts).total_seconds()),
            "python_version": platform.python_version(),
            "selected_backend": selected,
            "users_loaded": len(user_entries),
            "users_processed": total_stats.get("users_processed", 0),
            "users_failed": total_stats.get("users_failed", 0),
            "files_downloaded": total_stats.get("files_downloaded", 0),
            "files_uploaded": total_stats.get("files_uploaded", 0),
            "files_skipped": total_stats.get("files_skipped", 0),
            "state_total_uploaded": overall.get("total_uploaded"),
            "error_counts": getattr(logger, "error_counts", {}),
            "failed_users": failed_users,
            "status": ("SUCCESS" if failed == 0 else ("FAILED" if failed == total else "PARTIAL_SUCCESS")),
        }
        logger.write_summary(summary)
    except Exception:
        pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
