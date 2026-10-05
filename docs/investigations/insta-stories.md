# insta-stories.io — מועמד מוביל (נבדק ואומת)

## מטרה
להחליף את fastdl כמקור סטוריז: בלי Captcha, עם API פשוט.

## ממצאים מאומתים (2026-10-05, IP ביתי, requests בלבד)
- עובדה: `GET /content.php?url=<username>` מחזיר `{"status":"ok","source":"GetProfileInfo","username","full_name","html"}` לשלושת השמות. אין Turnstile, אין כותרת מיוחדת.
- עובדה: `GET /content.php?url=<username>&method=allstories` מחזיר `{"status":"ok","source":"GetAllStories","html"}` עם מדיה אמיתית: israeli_songs = 1 וידאו, idfonline = 4 תמונות + 2 וידאו, 995fm = 7 תמונות.
- עובדה: חותמות זמן יחסיות ב-HTML: `21 hours ago`, `12 minutes ago` וכו' — נתפסות על ידי `_parse_meta_timestamp` הקיים.
- עובדה: קישורי הורדה ישירים ב-HTML (`media2.php?media=...`), צפייה דרך `media.php?media=...`.
- עובדה: הורדת מדיה ישירה עובדת: 200, `image/jpeg`, 423KB, חתימת JPEG תקינה, עם `Referer` בלבד.
- עובדה: אין סטוריז = `{"status":"error","msg":"The user has no stories..."}` — מובחן נקי.
- עובדה: אין צורך בדפדפן בכלל — requests קל, מהיר (שניות), מתאים ל-GitHub Actions ולמגבלת 25 דקות.

## איך האתר פועל
- `my.js`: `Downnload()` קורא `#link`, שולח `GET /content.php?url=...`, מציג פרופיל, ואז `Downnload2(username,'allstories')` מביא סטוריז. אין Turnstile בקוד.
- מדיה דרך פרוקסי `fr*.anon-viewer.com/media.php?media=<encoded-cdn-url>`.

## עומס ועמידות
- 3 בקשות רצופות עבדו ללא חסימה. קל בהרבה מ-Playwright (אין 30 שניות המתנה למשתמש).
- סיכון: האתר עלול להוסיף Captcha בעתיד כמו האחרים — לכן לשמור את ממשק ההורדה מופשט (להחליף מקור בלי לשנות main/state/upload).

## צעדים הבאים
1. לאשר אימוץ.
2. לממש מקור חדש (`src/insta_stories_api.py` או הרחבת `fastdl_api.py`) + בדיקות יחידה עם הקלטות.
3. לעדכן מדריכים ו-STATUS.

## מסקנה
מומלץ לאמץ. עונה על כל הדרישות: סטוריז, תאריך, API פשוט, עומס נמוך, בלי דפדפן ובלי תשלום.
