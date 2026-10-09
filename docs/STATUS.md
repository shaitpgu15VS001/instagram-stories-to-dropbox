# Instagram Stories to Dropbox — מצב הפרויקט
עודכן: 2026-10-05

## סקירה
אוטומציה להורדת סטוריז ציבוריים דרך fastdl.app והעלאה לענן דרך rclone. רץ כל 3 שעות ב-GitHub Actions.

## מצב נוכחי
נמצא מועמד מוביל: insta-stories.io — עובד בלי Captcha ובלי דפדפן (API פשוט, אומת על 3 השמות). ממתין לאישור אימוץ לפני מימוש. fastdl נכשל עם 422 CAPTCHA_REQUIRED (Turnstile) — לא כשל IP.

## פתוח כרגע
1. לאמת הרצה מלאה מקומית (`python -m src.main`) עם 3 השמות, ואז הרצת GitHub אחת לבדיקת IP.
2. לעקוב: אם insta-stories.io יוסיף Captcha בעתיד — הממשק מופשט וניתן להחליף מקור.

## החלטות והנימוקים
- אבחון כפול (בית + GitHub) אושר, אבל GitHub נדחה זמנית כי מקומית כבר נכשל מסיבה אחרת. נימוק: אין טעם לבדוק חסימת IP לפני שהזרימה הבסיסית עובדת.
- FlareSolverr / EzSolver / curl-impersonate נדחו כפתרון מיידי. נימוק: הדף נטען ללא אתגר Cloudflare; הבעיה היא חוזה קלט ושינוי API, לא TLS.
- תוקן לוגר לווינדוס (cp1255) כדי לאפשר אבחון. נימוק: קרס על אימוג'י והסתיר את השגיאה האמיתית.

## ממצאים מאומתים
- עובדה: `tests/test_fastdl_api.py` עובר (7/7), כל הבדיקות עוברות (40/40) אחרי תיקון הלוגר. אומת 2026-10-05.
- עובדה: מילוי שם משתמש בלבד (`israeli_songs`, `idfonline`, `995fm`, `instagram`) לא יוצר בקשת API ולא מציג `.user-info` או `button.tabs-component__button`. אומת מקומית עם Playwright.
- עובדה: placeholder הנוכחי הוא `Insert instagram link here` (קובץ: probe זמני שנמחק). ראה `scripts/debug_fastdl_api_bridge.py:1`.
- עובדה: עם קישור מלא נצפו `POST userInfo`, `postsV2`, `posts` וטעינת `challenges.cloudflare.com/turnstile`. ריצה אחרת עם אותו קלט לא יצרה בקשות — לא יציב, כנראה בגלל מסך הסכמה.
- עובדה: כל 3 השמות (`israeli_songs`, `idfonline`, `995fm`) מחזירים 422 `CAPTCHA_REQUIRED` עם `challenge type=turnstile siteKey=0x4AAAAAABhLwGG2XCb7fE2M` על `userInfo`, `postsV2`, `posts`. אומת 2026-10-05 עם קישור מלא.
- עובדה: FlareSolverr מצהיר כרגע שפותרי CAPTCHA לא עובדים; Turnstile באתר צד-שלישי דורש שירות פתרון בתשלום (10-30 שניות לפתרון) או דפדפן חמקמק — לא יציב ל-GitHub Actions.
- עובדה: `src/fastdl_api.py:43` מנסה `POST /api/v1/instagram/stories` עם `username` בלבד — לא תואם לזרימה החדשה שנצפתה.
- עובדה: ניסוי Camoufox מבודד על mollygram נכשל (2026-10-05): אין `window.turnstile`, אפס בקשות ל-API, תיבת הורדה ריקה. דפדפן חמקמק לא פתר את הבעיה.
- עובדה: ניסוי Patchright מבודד על mollygram נכשל (2026-10-05): אין `window.turnstile`, אפס תשובות API אחרי 30 שניות.
- עובדה: insta-stories.io אומת (2026-10-05): פרופיל + סטוריז לכל 3 השמות בלי Captcha, הורדה ישירה 200 JPEG תקין, חותמות יחסיות, שגיאת אין-סטוריז מובחנת. ראה docs/investigations/insta-stories.md.

## נבדקו ונשללו
- חסימת IP של GitHub כגורם ראשוני — נשלל כגורם בלעדי כי כשל מקומי על IP ביתי עם דף נטען תקין.
- FlareSolverr כפתרון — נשלל זמנית כי אין אתגר Cloudflare שחוסם טעינה.
- מחקר חינמיים (2026-10-05): אין פתרון חינמי מובטח ל-Turnstile מ-GitHub. Patchright מועמד ראשון, EzSolver/COOLasHEL שני, Camoufox מוגבל בלינוקס, FlareSolverr חלש מול Turnstile חדש. לא נמצא מקור סטוריז חינמי בלי Captcha.
- עובדה: save-free נשלל (2026-10-05): דף סטוריז ייעודי קיים ומקבל שם משתמש, אבל לחיצה לא יוצרת בקשת backend ללא טוקן Turnstile (sitekey `0x4AAAAAAA2PJ4paB_en7_5n`). דפוס זהה ל-fastdl ו-mollygram.

## בוצע עד כה
- 2026-10-05: תיקון קריסת לוגר בווינדוס (`src/logger.py:52`, `src/logger.py:229`, `src/logger.py:261`).
- 2026-10-05: אבחון ביתי על 4 שמות עם Playwright, כולל בדיקת DOM ורשת.
- 2026-10-05: אימוץ insta-stories.io כמקור ראשי (`src/insta_stories_api.py`, חיבור ב-`src/story_downloader.py:478`, הרחבת `extract_pre_download_id`, Referer עודכן). אומת מקצה לקצה: 6 קבצים ל-idfonline. כל 47 הבדיקות עוברות.
- 2026-10-05: מדריכי HTML בעברית RTL (`docs/SETUP.html`, `docs/USAGE.html` עם סעיף קבצים והחלטות, `docs/TROUBLESHOOTING.html`). סונכרנו גם קבצי ה-md (מקור חדש + סעיף קבצים ב-USAGE.md) וקישורים ב-README.
- 2026-10-05: תיקון סיומת `.bin` (`_decide_ext` + `_is_heic` ב-`src/story_downloader.py:50`, בדיקות `tests/test_media_ext.py`). סיבה: שרת מחזיר `image/heic` על תוכן JPEG. אומת מול קובץ BIN אמיתי מהענן. כל 51 הבדיקות עוברות.
- 2026-10-05: תיקון כפילויות-שווא (שמות קבצים זהים באותה שנייה דרסו זה את זה). `_unique_path` מוסיף `_2`... כל 52 הבדיקות עוברות.
- 2026-10-09: אבחנת "משתמש לא קיים" (`diagnose` ב-`src/insta_stories_api.py`, סטטוס `USER_NOT_FOUND` + `E-USR-001` ב-`src/main.py`/`src/story_downloader.py`). אומת חי מול shlomo__abraham. כל 57 הבדיקות עוברות.
- 2026-10-09: אופטימיזציה שלב 4: נמדד (חציון 9שנ'/משתמש, ממוצע 17שנ', חריג לגיטימי 35 סטוריז). נוסה ניסיון-חוזר זול אחד לכשל רגעי. הורדות מקביליות נדחו (סיכון thread-safety ו-rate-limit). כל 58 הבדיקות עוברות. תחזית: 463 משתמשים ≈ שעתיים, בתוך ברירת 360 הדקות.
- 2026-10-09: סקירת API מלאה: פרופיל/full_name לא נדרשים (שמות תצוגה של המשתמש גוברים), אין taken_at מדויק במקור (רק יחסי — אומת ב-HTML), נוספה תמיכה בשניות/just now. כל 60 הבדיקות עוברות.
- 2026-10-09: ניתוח 4 כשלונות DOWNLOAD_ERROR: בכל משתמש נכשל סטורי חדש יחיד (הישנים דולגו, לא נוסו). 2 מ-504×3 (גיהוק פרוקסי), 2 מ-aborted ללא ניסיון חוזר — תוקן (ניסיון חוזר לשגיאות רשת רגעיות). כל 66 הבדיקות עוברות.
- 2026-10-09: שתי הרצות מלאות (463 משתמשים): ידנית 2.5 שעות/1536 הועלו, אוטומטית 47 דקות/65 חדשים. אומת בסקאלה: 0 `.bin`, 0 שמות כפולים, 38 חשבונות מתים זוהו (USER_NOT_FOUND). כשלונות DOWNLOAD_ERROR מ-504 רגעיים (מחלימים לבד).
- 2026-10-09: סקר חוסן: 3 תיקונים — HTML לא-מפוענח מדווח שגיאה (לא "אין סטוריז"), דף-שגיאה כמדיה נדחה (לא מועלה זבל), שמות תיקיות מחוטאים (`/ : * ?` → `_`, קיצוץ 100). כל 63 הבדיקות עוברות.
- 2026-10-09: חיזוק שחזור הורדות לחלון 24 השעות: 4 ניסיונות עם המתנה גדלה (2/4/8 שניות), ניסיון חוזר רק לזמני (5xx/429/timeout/aborted) — לא ל-4xx ולשגיאות תוכן. כל 70 הבדיקות עוברות.
- 2026-10-09: אומת מנגנון הדילוג: מזהי pre_download_id יציבים 6/6 בין הרצות חיות + סימולציית שתי רצות (שנייה מעלה 0, סטטוס NO_NEW_STORIES). כל 64 הבדיקות עוברות.
- 2026-10-09: ניקוי שלב 3 (חלקי): נמחקו מטמונים מתחדשים (`__pycache__`, `.pytest_cache`), תיקיות probe ריקות/ישנות (`tmp_e2e*`, `tmp_live_fastdl_probe` ~69MB) וקבצי דיבאג לא מקושרים ב-root. כל 57 הבדיקות עוברות. נותר להחליט: גיזום `scripts/` (72MB, חלק מתועד ככלי תחזוקה) ומחיקת workflow האבחון של fastdl.
- 2026-10-09: ניקוי שלב 3 (הושלם): נמחקו ~70MB פלטים מ-`scripts/` (צילומים, דיווחים, `debug_output`), נשארו קוד + קובץ הבדיקה. נמחק workflow האבחון המת של fastdl. כל 57 הבדיקות עוברות.
- 2026-10-07: הוסרה מגבלת `timeout-minutes: 25` מ-`.github/workflows/sync.yml` (בקשת משתמש). שים לב: ברירת המחדל של GitHub היא 360 דקות להרצה.

## אזהרות ומגבלות
- לא להוסיף תלות כבדה (FlareSolverr/Docker) לפני שהזרימה החדשה מובנת.
- אין לשנות `src/main.py`, אחסון, state או workflow עד שהמקור החדש יציב.
- קישורי הורדה כנראה זמניים (`__sig`/`__expires`) — לא לשמור ב-state.

## מסמכים קשורים
- docs/FASTDL_STORIES_ARCHITECTURE.md
- docs/FASTDL_GUIDE.md
- docs/investigations/fastdl-home-probe.md
- SETUP.md, USAGE.md, TROUBLESHOOTING.md
