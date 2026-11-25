# Instagram Stories to Dropbox — מצב הפרויקט
עודכן: 2026-11-25

## סקירה
אוטומציה להורדת סטוריז ציבוריים ממקור API והעלאה לענן דרך rclone. מקורות לפי סדר: ClipSaver (ראשי), insta-stories.io (גיבוי), FastDL (גיבוי). רץ כל 3 שעות ב-GitHub Actions.

## מצב נוכחי
המקור הקודם (insta-stories.io) הוסיף Captcha ומחזיר `{"status":"Refresh"}`, ו-FastDL מחזיר 403 מ-Cloudflare — ולכן הריצה של 2026-11-25 (run 45590792533) דיווחה 463/463 `NO_ACTIVE_STORIES` ו-0 סטוריז (כשל שקט). תוקן זיהוי הכשל, נוסף מפסק תפעולי, ו**הוחלף המקור הראשי ל-ClipSaver** (`src/clipssaver_api.py`) שאומת חי: איסוף, הורדת מדיה, שמות קבצים עם זמן פרסום ומזהי מדיה יציבים. הנותר: הרצת GitHub ידנית אחת לאימות שה-API לא נחסם מ-IP של מרכז נתונים.

## פתוח כרגע
1. הרצה ידנית אחת ב-GitHub Actions לאימות ClipSaver מ-IP של מרכז נתונים (`workflow_dispatch`).
2. לעקוב בהרצה הראשונה: מספר הקבצים שהועלו צפוי להיות גבוה מהרגיל (פעם אחת) — ראו "אזהרות ומגבלות".
3. אם ClipSaver ייפול בעתיד: dolphinradar (Turnstile), snapgram.io / getlurk.app (לא נבדקו לעומק), storynavigation.com (500 כרגע).


## החלטות והנימוקים
- 2026-11-25: **הוחלף המקור הראשי ל-ClipSaver** (`src/clipssaver_api.py`, מחובר ב-`_fetch_from_clipssaver` בראש `src/story_downloader.py`). נימוק: insta-stories.io חסום ב-Captcha ו-FastDL ב-Cloudflare, ו-ClipSaver אומת חי (API בלבד, בלי דפדפן, הורדת מדיה תקינה, `takenAt` מדויק). חלופה שנדחתה: חשבון אינסטגרם עם `sessionid` — יציב יותר אבל סיכון חסימת חשבון.
- 2026-11-25: תשובת "אין סטוריז" של ClipSaver היא סופית ואינה ממשיכה למקורות הגיבוי. נימוק: מעבר לגיבוי על כל משתמש בלי סטוריז היה מפעיל את גשר Playwright (~35 שנ'/משתמש) ומפוצץ את זמן הריצה; הגיבויים ממילא חסומים. מנגד, `upstream_unavailable`/`retryable` מוחזר כ-`None` ולכן כן ממשיך לגיבוי.
- 2026-11-25: טוקן מתחדש לכל משתמש (בקשה נוספת ~0.2-0.6 שנ'), ולא נשמר בין משתמשים. נימוק: טוקן שפג עלול להחזיר "אין סטוריז" בשקט — בדיוק הכשל השקט שתוקן. רענון אוטומטי קיים בכל מקרה על 401/403.
- 2026-11-25: מזהה המדיה של ClipSaver (`id`) משמש כ-`pre_download_id` למניעת כפילויות, כי לכתובת הפרוקסי אין פרמטר `media`/`uri`. השינוי: `download_stories` נופל ל-`s["pre_download_id"]` כשחילוץ מה-URL נכשל.
- 2026-11-25: כשל מקור חייב להיראות כשגיאה, לא כ"אין סטוריז". `insta_stories_api.fetch_stories` מחזיר `[]` רק על תשובת "no stories" מוצהרת; כל `status` לא מוכר (למשל `Refresh`) מחזיר `None` + `last_error`. נימוק: התנהגות קודמת גרמה ל-463 משתמשים "מצליחים" עם 0 סטוריז, ביטלה את האבחון והגיבוי, והציגה ריצה ירוקה.
- 2026-11-25: נוסף מפסק תפעולי `MAX_CONSECUTIVE_API_ERRORS` (ברירת מחדל 5, `0` מכבה). נימוק: אחרי תיקון הזיהוי כל משתמש היה מפעיל את גשר Playwright של FastDL (~10-35 שניות) — 463 משתמשים היו חורגים ממגבלת הזמן של Actions. חלופה שנדחתה: בדיקת מקדימה על משתמש אחד בלבד (עלולה לעצור על כשל רגעי של משתמש בודד).
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
- עובדה (2026-11-25, ריצה 45590792533): 463/463 משתמשים → `NO_ACTIVE_STORIES`, 0 סטוריז, 0 קבצים; בלוג אין אף אזכור ל-FastDL/`API_BRIDGE_STAGE` ⇒ הגיבוי לא רץ כלל. דיבאג: `debug_full.log`.
- עובדה (2026-11-25, בדיקה חיה): `GET /content.php?url=<user>&method=allstories` → `{"msg":"Error, Please refresh the page and try again.","status":"Refresh"}`; `GET /content.php?url=<user>` (פרופיל) → `{"msg":"Captcha verification failed","status":"error"}`. גם עם Referer של דף הצפייה ו-`X-Requested-With` — אותה תשובה.
- עובדה (2026-11-25): FastDL `POST https://api-wh.fastdl.app/api/v1/instagram/stories` → 403 עם דף Cloudflare "Just a moment..." ⇒ הגיבוי המתועד אינו זמין.
- עובדה (2026-11-25): StoryNavigation — `GET /user/<name>` 200 + cookies `XSRF-TOKEN`/`laravel_session`; `POST /get-user-highlights` 200; `POST /get-user-last-stories` 500 `Server Error` (עם CSRF תקין) ⇒ לא שמיש כרגע.
- עובדה (2026-11-25): אחרי השינוי `fetch_stories('djyochaiedri')` מחזיר `None` ו-`last_error="unexpected_status=Refresh ..."` במקום `[]`. 95 בדיקות עוברות.
- עובדה (2026-11-25): **ClipSaver עובד** — `GET /api/token` ואז `POST /api/instagram/instagramDownloader/stories` עם `x-cs-tok` ו-`{"username":...}` מחזיר `status=success` עם `downloadUrl`/`isVideo`/`takenAt`; הורדת מדיה 200 (`image/jpeg` 279KB, `video/mp4` 3MB). 23 בקשות רצופות ללא 429, ללא עוגיות/Referer/דפדפן. `upstream_unavailable` (retryable) מופיע לפעמים — חייב להיחשב כשל זמני. פרטים: `docs/investigations/clipssaver.md`.
- עובדה (2026-11-25, אחרי המימוש): `_fetch_story_urls('idfonline')` → 9 פריטים עם `ta` ו-`pre_download_id`; `download_stories('idfonline')` הוריד 9 קבצים תקינים (`image/jpeg`/`video/mp4`, 0.2-2.5MB); `avishairosen` → 0 ("אין סטוריז"). זמנים: טוקן ~0.2-0.6 שנ', שאילתת סטוריז ~3.3-3.7 שנ'. כל 106 הבדיקות עוברות.

## נבדקו ונשללו
- חסימת IP של GitHub כגורם ראשוני — נשלל כגורם בלעדי כי כשל מקומי על IP ביתי עם דף נטען תקין.
- FlareSolverr כפתרון — נשלל זמנית כי אין אתגר Cloudflare שחוסם טעינה.
- מחקר חינמיים (2026-10-05): אין פתרון חינמי מובטח ל-Turnstile מ-GitHub. Patchright מועמד ראשון, EzSolver/COOLasHEL שני, Camoufox מוגבל בלינוקס, FlareSolverr חלש מול Turnstile חדש. לא נמצא מקור סטוריז חינמי בלי Captcha.
- עובדה: save-free נשלל (2026-10-05): דף סטוריז ייעודי קיים ומקבל שם משתמש, אבל לחיצה לא יוצרת בקשת backend ללא טוקן Turnstile (sitekey `0x4AAAAAAA2PJ4paB_en7_5n`). דפוס זהה ל-fastdl ו-mollygram.

## בוצע עד כה
- 2026-11-25: **מימוש ClipSaver כמקור ראשי** — `src/clipssaver_api.py` (טוקן, שאילתת סטוריז, רענון טוקן על 401/403, `last_error`), חיבור בראש `_fetch_story_urls`, מזהה מדיה כ-`pre_download_id`, עדכון טקסטים/מסמכים. אומת חי מקצה לקצה: `idfonline` → 9 קבצים (תמונות ווידאו) בשמות `<user>-<זמן פרסום>.<ext>`; `meni_music` → 3; `avishairosen` → 0 ("אין סטוריז"). כל 106 הבדיקות עוברות.
- 2026-11-25: חקירת מקור חלופי — נמצא ClipSaver עובד (API ללא דפדפן, 23 בקשות רצופות תקינות, הורדת מדיה מאומתת). תועד ב-`docs/investigations/clipssaver.md`; נוספו כלי בדיקה `scripts/probe_clipssaver.py`, `scripts/probe_story_sources.py`, `scripts/probe_story_source_deep.py`.
- 2026-11-25: תיקון כשל שקט + מפסק תפעולי. `src/insta_stories_api.py` (החזרת `None` על `status` לא מוכר + `last_error`), `src/story_downloader.py` (סיבת הכשל ב-WARNING), `src/main.py` (`MAX_CONSECUTIVE_API_ERRORS`, עצירה עם exit code 1, דיווח ב-RUN SUMMARY/Step Summary/debug summary), בדיקות חדשות (`tests/test_circuit_breaker.py`, הרחבות ב-`tests/test_insta_stories_api.py`, עדכון `tests/test_fastdl_api.py`). כל 95 הבדיקות עוברות.
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
- 2026-10-11: שרשרת עננים (failover): `STORAGE_BACKEND.txt` כרשימה לפי סדר, מעבר אוטומטי ב-97% (מונה בייטים + ריאקטיבי), state תמיד בראשון, שחזור/שמירה בסדר ב-workflow. כל 80 הבדיקות עוברות.
- 2026-10-11: בחירת טריגר בקובץ `SCHEDULE.txt` (`github`/`external`). מצב external מדלג על cron של GitHub (מונע כפילויות), כפתור ידני תמיד עובד. מדריך חיבור cron-job.org ב-USAGE. כל 86 הבדיקות עוברות.
- 2026-10-11: עקביות אזור זמן: תיקיית תאריך עברה ל-Asia/Jerusalem (הייתה UTC, בניגוד לשמות הקבצים). תועד: cron של GitHub = UTC, cron-job.org = Asia/Jerusalem, קבצים = ישראל, לוגים = UTC. כל 87 הבדיקות עוברות.
- 2026-10-11: הובהר במדריך: טוקן Fine-grained (לא classic) עם Actions Read+Write + תזכורת תפוגה שנתית.
- 2026-10-11: הוראות cron-job.org מפורטות לפי ממשק 2026 (Title/URL/POST/Headers/Body/Schedule/Timezone/Preview/Notifications/Save) + מגבלות חינם.
- 2026-10-11: הוראות cron-job.org תוקנו לפי צילומי המסך האמיתיים (לשוניות COMMON/NOTIFICATIONS/ADVANCED, Custom crontab, TEST RUN לפני CREATE).
- 2026-10-12: שעון GitHub לכל 7 שעות + `run-name` עם סוג אירוע ([schedule]/[workflow_dispatch]) להבחנה ברשימה.
- 2026-10-11: תיקון הוראות cron-job.org מול תיעוד רשמי (FAQ מאומת; שמות שדות מדויקים הוסרו עד לאימות מול המסך האמיתי).
- 2026-10-11: שכתוב `docs/USAGE.html` למתחילים (מילון, צעדים ממוספרים, הסבר RUN SUMMARY, מספרים עדכניים). סונכרן מילון + טבלת דו"ח ל-USAGE.md.
- 2026-10-11: שכתוב מלא של שני המדריכים מאפס (קצר: קצר וקולע; מורחב: הכל כולל GitHub מאפס, web-upload, מילון מורחב, טעויות נפוצות, גבולות חינם) — מעודכן 2026.
- 2026-10-09: שתי הרצות מלאות (463 משתמשים): ידנית 2.5 שעות/1536 הועלו, אוטומטית 47 דקות/65 חדשים. אומת בסקאלה: 0 `.bin`, 0 שמות כפולים, 38 חשבונות מתים זוהו (USER_NOT_FOUND). כשלונות DOWNLOAD_ERROR מ-504 רגעיים (מחלימים לבד).
- 2026-10-09: הרצה מלאה שלישית (~70 דקות, 317 הועלו, 0 `.bin`, 0 כפילויות-שווא). מנגנון 4 הניסיונות הוכח (2 סטוריז שרדו 4 ניסיונות 504 ועדיין דווחו נכון, המשתמשים הסתיימו בהצלחה חלקית). dudi_friedman יציב כ-USER_NOT_FOUND (2/3) — מומלץ להסיר.
- 2026-10-09: סקר חוסן: 3 תיקונים — HTML לא-מפוענח מדווח שגיאה (לא "אין סטוריז"), דף-שגיאה כמדיה נדחה (לא מועלה זבל), שמות תיקיות מחוטאים (`/ : * ?` → `_`, קיצוץ 100). כל 63 הבדיקות עוברות.
- 2026-10-09: חיזוק שחזור הורדות לחלון 24 השעות: 4 ניסיונות עם המתנה גדלה (2/4/8 שניות), ניסיון חוזר רק לזמני (5xx/429/timeout/aborted) — לא ל-4xx ולשגיאות תוכן. כל 70 הבדיקות עוברות.
- 2026-10-09: אומת מנגנון הדילוג: מזהי pre_download_id יציבים 6/6 בין הרצות חיות + סימולציית שתי רצות (שנייה מעלה 0, סטטוס NO_NEW_STORIES). כל 64 הבדיקות עוברות.
- 2026-10-09: ניקוי שלב 3 (חלקי): נמחקו מטמונים מתחדשים (`__pycache__`, `.pytest_cache`), תיקיות probe ריקות/ישנות (`tmp_e2e*`, `tmp_live_fastdl_probe` ~69MB) וקבצי דיבאג לא מקושרים ב-root. כל 57 הבדיקות עוברות. נותר להחליט: גיזום `scripts/` (72MB, חלק מתועד ככלי תחזוקה) ומחיקת workflow האבחון של fastdl.
- 2026-10-09: ניקוי שלב 3 (הושלם): נמחקו ~70MB פלטים מ-`scripts/` (צילומים, דיווחים, `debug_output`), נשארו קוד + קובץ הבדיקה. נמחק workflow האבחון המת של fastdl. כל 57 הבדיקות עוברות.
- 2026-10-07: הוסרה מגבלת `timeout-minutes: 25` מ-`.github/workflows/sync.yml` (בקשת משתמש). שים לב: ברירת המחדל של GitHub היא 360 דקות להרצה.

## אזהרות ומגבלות
- הרצה ראשונה אחרי המעבר למקור החדש תעלה מחדש סטוריז פעילים שכבר הועלו (עד 24 שעות אחורה): המזהה היציב השתנה מ-path של insta-stories למזהה מדיה של ClipSaver, ולכן אין התאמה ל-state ההיסטורי. חד-פעמי.
- ClipSaver לא מבחין בין "משתמש לא קיים/פרטי" ל"אין סטוריז" — שניהם ייספרו `NO_ACTIVE_STORIES`. אין יותר זיהוי `USER_NOT_FOUND` אוטומטי מהמקור הראשי.
- סטוריז מתקופת השבתת המקור אבודים — אינסטגרם מוחק אחרי 24 שעות ואין שחזור.
- ריצה שמסתיימת ב-exit code 1 עם `Aborted` היא מכוונת (מפסק) — לא כשל תשתית.
- לא להחזיר `[]` על תשובת מקור לא מוכרת: זה מסתיר השבתה שלמה כ"אין סטוריז".
- לא להוסיף תלות כבדה (FlareSolverr/Docker) לפני שהזרימה החדשה מובנת.
- אין לשנות `src/main.py`, אחסון, state או workflow עד שהמקור החדש יציב.
- קישורי הורדה כנראה זמניים (`__sig`/`__expires`) — לא לשמור ב-state.

## מסמכים קשורים
- docs/investigations/clipssaver.md
- docs/FASTDL_STORIES_ARCHITECTURE.md
- docs/FASTDL_GUIDE.md
- docs/investigations/fastdl-home-probe.md
- SETUP.md, USAGE.md, TROUBLESHOOTING.md
