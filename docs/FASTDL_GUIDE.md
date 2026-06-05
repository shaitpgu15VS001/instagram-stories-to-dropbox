# 📘 מדריך: הורדת סטוריז מ-instagram דרך fastdl.app

מסמך זה מתעד את שיטת ההורדה השנייה של הפרויקט — באמצעות האתר **fastdl.app**.
הקוד הראשי כרגע עובד עם **instanonimo.com**, אך הקוד של fastdl.app שמור כגיבוי ב-`src/story_downloader_fastdl_backup.py`.

> **תאריך בדיקה אחרון:** 2026-06-05
> **סטטוס:** ✅ עובד מצוין, שמור כגיבוי

---

## סקירה כללית

**fastdl.app** הוא אתר אנונימי לצפייה והורדת סטוריז מחשבונות ציבוריים ב-instagram, ללא צורך בהתחברות.

### למה בחרנו בו (במקור)
- ✅ תומך בחיפוש לפי שם משתמש
- ✅ מציג סטוריז, פוסטים, היילייטס ורילס
- ✅ קישורי הורדה ישירים (URL מוכן, לא דורש JavaScript)
- ✅ לא דורש Cloudflare challenge
- ✅ מהיר — טעינה של 9-18 שניות למשתמש

### למה עברנו ממנו
- לעיתים מופיעים פופאפים של מודעות שחוסמים את הלחיצה על לשונית Stories
- המבנה של האתר תלוי ב-Vue.js, מה שמקשה על שליפה ישירה (חייבים Playwright)

---

## איך זה עובד — זרימה טכנית

```
┌─────────────────────────────────────────────┐
│ 1. פתיחת הדף: /instagram-anonymously-viewer│
│ 2. המתנה לטופס #search-form-input           │
│ 3. הזנת שם משתמש + לחיצה על #searchFormButton│
│ 4. המתנה ל-.user-info (פרופיל נטען)         │
│ 5. לחיצה על לשונית "Stories" (force=True)   │
│ 6. המתנה ל-.media-content--story            │
│ 7. חילוץ href מ-.button__download           │
│ 8. סינון URLs שמכילים media.fastdl.app      │
│ 9. הורדה עם requests                         │
└─────────────────────────────────────────────┘
```

### URL בסיסי
```
https://fastdl.app/instagram-anonymously-viewer
```

### URL של קובץ להורדה
```
https://media.fastdl.app/get?__sig=<חתימה>&__expires=<תוקף>&uri=<URI>&filename=<שם>
```
- `__expires` — בתוקף ל-20 שעות
- `__sig` — חתימה דיגיטלית ייחודית לכל בקשה
- `filename` — שם הקובץ המקורי מ-instagram

---

## דרישות טכניות

| רכיב | גרסה | הערות |
|---|---|---|
| Python | 3.11+ | נבדק על 3.12 |
| playwright | 1.40+ | נבדק על 1.60 |
| chromium | 180MB | מותקן אוטומטית על ידי Playwright |
| זיכרון | 512MB+ | לכל ריצה |

התקנה:
```bash
pip install playwright>=1.40.0
playwright install --with-deps chromium
```

---

## מבנה הקוד

**קובץ:** `src/story_downloader_fastdl_backup.py`

### מחלקה: `StoryDownloader`

| מתודה | תפקיד | החזרה |
|---|---|---|
| `__init__(output_dir)` | אתחול תיקיית פלט | — |
| `check_binary()` | בדיקה ש-Playwright מותקן | bool |
| `download_stories(username)` | פונקציה ראשית | dict |
| `_fetch_story_urls(username)` | שליפת URLs מ-fastdl | list / None / [] |
| `_download_files(urls, user_dir)` | הורדת URLs | list[Path] |
| `_make_filename(url, response, idx)` | בניית שם קובץ | str |
| `_ext_from_content_type(ct)` | מיפוי content-type | str |
| `extract_story_id(filename)` | חילוץ ID ייחודי | str |
| `cleanup(username=None)` | מחיקת קבצים | — |

### קבועים חשובים

```python
VIEWER_URL = "https://fastdl.app/instagram-anonymously-viewer"
PAGE_LOAD_TIMEOUT = 60000      # 60 שניות
PROFILE_LOAD_TIMEOUT = 30000   # 30 שניות
STORIES_LOAD_TIMEOUT = 15000   # 15 שניות
DOWNLOAD_TIMEOUT = 60          # 60 שניות
```

---

## סלקטורים (CSS)

| סלקטור | מה הוא מוצא | חשוב |
|---|---|---|
| `#search-form-input` | תיבת החיפוש | חייב להיות visible |
| `#searchFormButton` | כפתור החיפוש | — |
| `.user-info` | פרופיל המשתמש (אחרי חיפוש) | אם לא קיים → משתמש פרטי |
| `button.tabs-component__button` (filter: Stories) | לשונית Stories | חסומה על ידי ad → force=True |
| `.media-content--story` | סטורי בודד | — |
| `.button__download` | כפתור הורדה | href ישיר |

---

## בעיות ידועות ופתרונות

### 1. 🔴 Ad modal חוסם לחיצה על לשונית Stories

**תסמין:** הקוד נתקע 30 שניות ב-`wait_for_selector(".user-info")` או בלחיצה על Stories.

**גורם:** מודעת Google Ad (`<div role="dialog" class="ad-modal">`) מופיעה מעל לשונית Stories.

**פתרון:**
```python
stories_tab.first.click(force=True, timeout=5000)
```
ה-`force=True` עוקף את בדיקת החסימה ולוחץ בכל מקרה.

### 2. 🟡 `domcontentloaded` מחזיר לפני ש-Vue.js מסיים

**תסמין:** `page.fill` נכשל או `page.click` לא מפעיל handler.

**פתרון:** הוסף `wait_for_selector` מפורש:
```python
page.goto(URL, wait_until="domcontentloaded")
page.wait_for_selector("#search-form-input", state="visible")
page.fill("#search-form-input", username)
```

### 3. 🟢 משתמש פרטי / לא קיים

**תסמין:** `wait_for_selector(".user-info")` נכשל ב-30 שניות.

**פתרון:** הקוד מחזיר `None` במקרה כזה, ומטפל בזה כ-`user_not_found`.

### 4. 🟢 אין סטוריז פעילים

**תסמין:** `wait_for_selector(".media-content--story")` נכשל.

**פתרון:** הקוד מחזיר `[]` (רשימה ריקה) — לוג "אין סטוריז פעילים", ממשיך הלאה.

### 5. 🟢 Rate limits

**תסמין:** אתר חוסם בקשות אחרי הרבה משתמשים.

**פתרון:** ב-`main.py` יש delay של 2-3 שניות בין משתמשים.

---

## איך לחזור ל-fastdl.app (Rollback)

אם instanonimo.com נופל או שאתה רוצה לחזור לגרסה הקודמת:

### שלב 1: החלף את הקובץ הראשי
```bash
# ב-Windows PowerShell:
Copy-Item -LiteralPath "src\story_downloader_fastdl_backup.py" -Destination "src\story_downloader.py" -Force
```

### שלב 2: בדוק מקומית
```bash
python -m src.main
```
ודא שאתה רואה לוג "מתחבר לדרופבוקס" ואז הורדות.

### שלב 3: בדוק שלא צריך לשנות imports ב-main.py
- הקובץ `main.py` מייבא את `StoryDownloader` מ-`src.story_downloader`
- השם לא השתנה → אין צורך לשנות את `main.py`

### שלב 4: Commit + push
```bash
git add src/story_downloader.py
git commit -m "חזרה ל-fastdl.app"
git push
```

### שלב 5: הפעל workflow
- ב-GitHub → Actions → Instagram Story Sync → Run workflow

---

## תוצאות בדיקה (2026-06-05)

| משתמש | תוצאה | זמן | קבצים שהורדו |
|---|---|---|---|
| @natgeo | ✅ הצליח | 9.4s | 2 (jpegs, 362KB סה"כ) |
| @nike | ✅ אין סטוריז | 18.1s | 0 |
| @instagram | ✅ אין סטוריז | 18.2s | 0 |
| @cristiano | ✅ אין סטוריז | 18.2s | 0 |

**סה"כ:** 64 שניות ל-4 משתמשים (16 שניות בממוצע).

### קבצים לדוגמה
```
714631431_18663668626019133_4646312830966306100_n..jpg  (241,851 bytes)
717168991_18663754630019133_9023224996632399525_n..jpg  (120,012 bytes)
```

---

## השוואה מהירה עם instanonimo.com

| נושא | fastdl.app | instanonimo.com |
|---|---|---|
| URL pattern | `/instagram-anonymously-viewer` (חיפוש) | `/en/stories/<user>` (ישיר) |
| כפתור הורדה | href ישיר | `href=""` + JS click |
| צריך ללחוץ Stories tab? | כן | לא |
| Ad modal | חוסם Stories tab | חוסם Download |
| Cloudflare | לא | כן (Turnstile) |
| קבצים | jpg/mp4 (mixed) | jpeg |
| זמן טעינה | 10-18s | 15-20s |

---

## שאלות נפוצות

**למה לא להשתמש בשני האתרים במקביל?**
- אפשר, אבל זה מסבך את הקוד
- עדיף גיבוי ברור שאפשר להחליף במהירות

**מה קורה אם fastdl.app נחסם במדינה מסוימת?**
- רוב ה-VPN עוקפים את החסימה
- GitHub Actions רץ בענן של AWS, לא נחסם

**למה לא להשתמש ב-API ישיר?**
- fastdl.app לא חושף API ציבורי
- הקוד הנוכחי (Playwright) הוא הפתרון היציב ביותר

---

## ראה גם

- `src/story_downloader.py` — קוד פעיל (instanonimo.com)
- `src/story_downloader_fastdl_backup.py` — קוד גיבוי (fastdl.app)
- `docs/` — תיקיית תיעוד
- `TROUBLESHOOTING.md` — פתרון בעיות כללי
