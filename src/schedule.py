"""בחירת טריגר להרצה: GitHub עצמו או שירות חיצוני מדויק.

קובץ SCHEDULE.txt (ברירת מחדל: github):
    trigger=github     # cron של GitHub + כפתור ידני
    trigger=external   # שירות חיצוני (למשל cron-job.org) דרך workflow_dispatch;
                       # הרצות cron של GitHub מדולגות כדי למנוע כפילויות.
"""

SCHEDULE_FILE = "SCHEDULE.txt"
VALID_TRIGGERS = ("github", "external")


def read_trigger(path=SCHEDULE_FILE):
    """קורא את מצב הטריגר. כל ערך חסר/לא תקין -> 'github' (תאימות לאחור)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip().lower() == "trigger":
                    value = value.strip().lower()
                    if value in VALID_TRIGGERS:
                        return value
                    return "github"
    except OSError:
        pass
    return "github"


def should_run(trigger, event):
    """האם להריץ? event: schedule/workflow_dispatch/מקומי.

    מחזיר (run: bool, reason: str).
    """
    trigger = (trigger or "github").strip().lower()
    if trigger not in VALID_TRIGGERS:
        trigger = "github"
    event = (event or "").strip().lower()
    if not event or event == "workflow_dispatch":
        # הפעלה ידנית או מקומית — תמיד רצה
        return True, "manual-or-local"
    if trigger == "external":
        return False, "scheduled run skipped (trigger=external)"
    return True, "scheduled run (trigger=github)"
