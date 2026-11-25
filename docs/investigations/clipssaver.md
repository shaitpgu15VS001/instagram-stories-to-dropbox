# ClipSaver (clipssaver.com) — מקור סטוריז חלופי

**תאריך בדיקה:** 2026-11-25
**מצב:** אומץ כמקור ראשי. ממומש ב-`src/clipssaver_api.py` ומחובר ב-`src/story_downloader.py` (`_fetch_from_clipssaver`). ממתין לאימות IP בהרצת GitHub.

## מטרה
למצוא מקור סטוריז שעובד אחרי ש-insta-stories.io הוסיף Captcha ו-FastDL נחסם ב-Cloudflare.

## שיטה
בדיקות `requests` בלבד (ללא דפדפן), מול האתר החי, כולל הורדת מדיה בפועל.
כלי הבדיקה: `scripts/probe_clipssaver.py` (שאילתות + הורדה), `scripts/probe_story_sources.py` (סינון אתרים), `scripts/probe_story_source_deep.py` (מיפוי נתיבי API מתוך חבילות JS).

## זרימת ה-API (מאומת)
1. `GET https://clipssaver.com/api/token` → `{"ok":true,"token":"v1...."}` (אורך 57).
2. `POST https://clipssaver.com/api/instagram/instagramDownloader/stories`
   - גוף: `{"username":"<user>"}`
   - כותרת: `x-cs-tok: <token>`
   - אין צורך בעוגיות, ב-Referer או בדפדפן (אומת: עובד גם בלעדיהם).

## מבנה התשובה (מאומת)
```json
{"status":"success","data":{"stories":[{
  "id":4037543993482016300,
  "displayUrl":"https://cdn.socialhubapi.com/media/...",
  "downloadUrl":"https://cdn.socialhubapi.com/media/...",
  "videoUrl":null,
  "isVideo":false,
  "takenAt":1795532772,
  "expiringAt":1795619172,
  "mediaType":1,
  "owner":{"pk":17820655,"username":"idfonline"}
}]}}
```
- `downloadUrl` הוא פרוקסי (`cdn.socialhubapi.com/media/...?src=<base64 של CDN אינסטגרם>`).
- `takenAt`/`expiringAt` בשניות יוניקס; `expiringAt - takenAt = 86400` (24 שעות) — תואם לסטוריז.
- `isVideo` קובע סוג מדיה; `downloadUrl` מחזיר `image/jpeg` או `video/mp4` בהתאם.

## מקרי קצה (מאומת)
| מקרה | תשובה | משמעות לקוד |
|---|---|---|
| משתמש עם סטוריז | `stories` לא ריק | הצלחה |
| אין סטוריז כרגע | `{"data":{"stories":[]},"isAuthorized":false,...}` | "אין סטוריז" — לא כשל |
| עומס זמני בצד המקור | `{"data":{"stories":[],"reason":"upstream_unavailable","retryable":true,"retryAfter":10}}` | **כשל זמני** — אסור לדווח "אין סטוריז"; לחזור על הבקשה |
| משתמש לא קיים | `{"data":{"stories":[]},"isAuthorized":false}` | זהה ל"אין סטוריז" — אין הבחנה |

## עומס וקצב
- 23 בקשות רצופות (טוקן אחד) — כולן `200`, ללא `429`, ללא דעיכה.
- `GET /api/usage` מחזיר `405` (לא רלוונטי ל-API).
- תשובת `upstream_unavailable` הופיעה ב-2 מתוך 23 משתמשים, חלפה בבקשה חוזרת.

## סיכונים ומגבלות
- **IP של GitHub Actions לא נבדק.** ה-API עובר דרך Cloudflare (`server: cloudflare`) אבל בלי אתגר בדפדפן; ייתכן שינוי התנהגות מ-IP של מרכז נתונים. דורש הרצה ידנית אחת לאימות.
- תלות בצד שלישי חינמי — עלול להוסיף Captcha/מכסה כמו קודמיו. לכן המימוש חייב להישאר מופשט (החלפת מקור בלי לגעת ב-state/העלאה).
- `takenAt` מגיע מהמקור (בניגוד ל-insta-stories.io שהחזיר רק חותמות יחסיות) — יתרון לשמות קבצים דטרמיניסטיים.
- אין הבחנה בין "משתמש לא קיים" ל"אין סטוריז".

## השוואה למועמדים אחרים (נכון ל-2026-11-25)
- **dolphinradar.com** — דף הסטוריז טוען `challenges.cloudflare.com/turnstile`; לא נבדק לעומק לאחר שנמצא מקור עובד. סביר שדורש Turnstile.
- **snapgram.io / getlurk.app** — דפי בית נטענים ללא סימני Captcha, אבל לא אותר נתיב API בבדיקה הראשונית. לא נבדקו לעומק.
- **storynavigation.com** — פרופיל ו-highlights עובדים, `POST /get-user-last-stories` מחזיר `500`. לא שמיש.
- **insta-stories.io** — Captcha (`status: "Refresh"`, `Captcha verification failed`).
- **FastDL** — `403` מדף Cloudflare "Just a moment".

## מה מומש בפועל
- `src/clipssaver_api.py` — `ClipSaverAPI.fetch_stories` מחזיר `[{u, kind, ta, id}]`, `[]` ל"אין סטוריז", `None` לכשל + `last_error`.
- טוקן נלקח לכל קריאה (בקשה נוספת ~0.2-0.6 שנ'); רענון אוטומטי + ניסיון חוזר אחד על 401/403.
- `src/story_downloader.py` — `_fetch_from_clipssaver` רץ ראשון; על כשל עוברים ל-insta-stories.io ואז FastDL; על "אין סטוריז" עוצרים (לא ממשיכים לגיבוי).
- מניעת כפילויות: `id` של המדיה משמש כ-`pre_download_id` (במקום חילוץ מה-URL).
- בדיקות: `tests/test_clipssaver_api.py` (10 בדיקות, כולל רענון טוקן ו-`upstream_unavailable`), ועדכון בדיקות קיימות שכן קראו ל-`_fetch_story_urls`.

## צעדים הבאים
1. הרצה ידנית אחת ב-GitHub Actions לאימות IP.
2. מעקב אחרי הריצה הראשונה: צפויים קבצים כפולים-למראה מהעדכון החד-פעמי של המזהה.
