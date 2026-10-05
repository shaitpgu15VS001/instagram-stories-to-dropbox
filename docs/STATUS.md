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

## אזהרות ומגבלות
- לא להוסיף תלות כבדה (FlareSolverr/Docker) לפני שהזרימה החדשה מובנת.
- אין לשנות `src/main.py`, אחסון, state או workflow עד שהמקור החדש יציב.
- קישורי הורדה כנראה זמניים (`__sig`/`__expires`) — לא לשמור ב-state.

## מסמכים קשורים
- docs/FASTDL_STORIES_ARCHITECTURE.md
- docs/FASTDL_GUIDE.md
- docs/investigations/fastdl-home-probe.md
- SETUP.md, USAGE.md, TROUBLESHOOTING.md
