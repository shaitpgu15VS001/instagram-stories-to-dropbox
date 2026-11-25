# ClipSaver (clipssaver.com) — מקור סטוריז חלופי

**תאריך בדיקה:** 2026-11-25
**מצב:** אומץ כמקור ראשי ופעל בהרצת GitHub (764 קבצים הועלו). נמצאה מגבלת IP: `/api/token` מחזיר 403 אחרי כ-110 בקשות טוקן מאותו IP; תוקן ע"י שימוש חוזר בטוקן אחד + בדיקה מקדימה.

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
- `src/clipssaver_api.py` — `ClipSaverAPI.fetch_stories` מחזיר `[{u, kind, ta, id}]`, `[]` ל"אין סטוריז", `None` לכשל + `last_error`. יש גם `ensure_token()` לבדיקה מקדימה.
- **טוקן אחד לכל הריצה** (`StoryDownloader._get_clipssaver_api`): רענון אוטומטי רק כשה-API מחזיר 401/403. קודם נפתח טוקן לכל משתמש — וזה גרם ל-403 מ-IP של GitHub אחרי כ-110 משתמשים (ראה למטה).
- `src/story_downloader.py` — `ensure_story_source_ready()` בודקת טוקן לפני הלולאה (עם ניסיון חוזר אחד); `main` עוצר עם `exit 1` אם נכשל. `_fetch_from_clipssaver` רץ ראשון; על כשל עוברים ל-insta-stories.io ואז FastDL; על "אין סטוריז" עוצרים (לא ממשיכים לגיבוי).
- מניעת כפילויות: `id` של המדיה משמש כ-`pre_download_id` (במקום חילוץ מה-URL).
- בדיקות: `tests/test_clipssaver_api.py` (12 בדיקות: רענון טוקן, `upstream_unavailable`, שימוש חוזר בטוקן, ניסיון חוזר בבדיקה המקדימה) + בדיקות `diagnose` ב-`tests/test_insta_stories_api.py`.

## ממצא חדש מהרצת GitHub (45637110882, 2026-11-25)
- המקור עבד מה-IP של GitHub: 764 קבצים הועלו מ-106 משתמשים; 109 משתמשים בלי סטוריז.
- אחרי 17:17 (כ-110 משתמשים) **כל** בקשת `/api/token` החזירה `403` — 244 משתמשים נכשלו. שלושה נוספים ב-timeout של 30 שנ' ואחד ב-`upstream_unavailable`.
- בדיקה מקומית: טוקן אחד שירת 9 משתמשים רצופים; 20 בקשות טוקן מהירות — כולן 200 ⇒ ההגבלה קשורה ל-IP של GitHub ולמספר הבקשות.
- **תופעת לוואי**: כש-ClipSaver נכשל, הורדת insta-stories.io החזירה Captcha גם למשתמשים אמיתיים, ו-`diagnose` סימן 248 מהם `USER_NOT_FOUND` (למשל `24tv`, `i24news_he`). תוקן ע"י דרישת הודעת "not found" מפורשת.
- קובץ המקור: `debug (1).zip` (בתוך `debug_full.log`).

## צעדים הבאים
1. הרצת GitHub נוספת לאימות: אין `token_http_status=403`, אין `USER_NOT_FOUND` מזויף, והבדיקה המקדימה עוברת.
2. מעקב אחרי המזהים החדשים (כפילויות חד-פעמיות כבר נצפו בהרצה הראשונה).
