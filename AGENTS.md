# AGENTS — הוראות קצרות לסוכנים אוטומטיים

מטרה: לספק לסוכני AI (כמו Copilot) מידע ממוקד, קישורים ופקודות ריצה שיאפשרו התחלה מהירה בעבודה על הפרויקט.

תמצית מה לעשות ראשונה
- הרץ: `python -m pip install -r requirements.txt` (דרוש: Python 3.8+).
- נקודת כניסה להרצה מקומית: `python -m src.main` או `python src/main.py`.
- לפני בדיקות על XLSX ודפדפן, ודא ש־`openpyxl` ו־`playwright` מותקנים (ראה `requirements.txt`).

פקודות חשובות
- התקנת תלות ופלאגינים:
  - `python -m pip install -r requirements.txt`
  - `playwright install` (להתקנת דפדפנים עבור Playwright)

קבצי מפתח (קישור מהיר)
- בקוד: [src/main.py](src/main.py) — נקודת כניסה, טעינת שמות משתמשים וניהול סיכום.
- הורדה: [src/story_downloader.py](src/story_downloader.py) — לוגיקת הורדת הסטוריז (fastdl.app).
- העלאה: [src/rclone_uploader.py](src/rclone_uploader.py) — העלאה לשירותי ענן דרך rclone.
- מצב/מעקב: [src/state_manager.py](src/state_manager.py) — ניהול state והימנעות מהעלאות כפולות.
- לוגים: [src/logger.py](src/logger.py) — כלי לוגים מותאם.

תיעוד ומדריכים
- מדריך התקנה מלא: [SETUP.md](SETUP.md)
- שימוש ותפעול: [USAGE.md](USAGE.md)
- פתרון תקלות ו־FASTDL guide: [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [docs/FASTDL_GUIDE.md](docs/FASTDL_GUIDE.md)

כללי פעולה לסוכנים
- אל תשנה לוגיקת הורדה/upload (story_downloader.py / rclone_uploader.py) אלא אם זוהתה בעיה ספציפית שם.
- שינויים במנגנון טעינת שמות משתמשים (`src/main.py`) קבילים — הימנע משינויי API חיצוניים.
- שמור על תאימות אחורית: אל תשנה שמות קבצים/מבני תיקיות ללא עדכון README/SETUP.

איך להוסיף בדיקות מהירות
- להריץ בדיקת נרמול משתמשים עם קבצי דוגמה: כתוב סקריפט פשוט שיוצר TXT/CSV/XLSX זמניים ומריץ `load_usernames()` (מוכל ב־`src/main.py`).

מגעים מועילים
- קבצי קלט מצופים: `usernames.txt`, `usernames.csv`, `usernames.xlsx`.
- קבצי תצורה: `rclone.conf`, `STORAGE_BACKEND.txt`.

אם תרצו, אוסיף קבצי הנחיה נוספים (לרבות `.github/copilot-instructions.md`) שמכילים פקודות CI, דלפק בדיקות ומה לשמור כ־PR template.
