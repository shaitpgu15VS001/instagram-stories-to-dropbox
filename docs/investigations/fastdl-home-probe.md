# אבחון fastdl מהבית — אוקטובר 2026

## מטרה
להבין למה הורדה מ-fastdl נכשלת, והאם זה חסימת IP של GitHub או שינוי באתר.

## מצב נוכחי
גורם שורש אומת: 422 CAPTCHA_REQUIRED (Turnstile) על כל 3 השמות, גם מ-IP ביתי. fastdl לא שמיש לאוטומציה ללא שירות פתרון בתשלום.

## שלבי החקירה
1. הרצת `tests/test_fastdl_api.py` — עבר.
2. הרצת `FastDLStoriesAPI.fetch_stories('israeli_songs')` — החזיר None עם timeout על `button.tabs-component__button`.
3. בדיקת DOM אחרי חיפוש ל-4 שמות — `TABS_COUNT=0`, `USERINFO_COUNT=0`.
4. בדיקת מבנה חדש — placeholder חדש, כפתור Download, אין בקשת API עם שם משתמש בלבד.
5. בדיקה עם קישור מלא — נצפו userInfo/posts + Turnstile; ריצה חוזרת לא יצרה בקשות.

## קבצים ומסלולי קוד שנבדקו
- `src/fastdl_api.py:43` — מנסה POST stories עם username בלבד.
- `src/story_downloader.py:478` — זרימת API-first, ללא גיבוי DOM אוטומטי.
- `src/logger.py:52` — קרס על cp1255, תוקן.
- `scripts/debug_fastdl_api_bridge.py:1`, `scripts/debug_fastdl_israel.py:1` — קיימים, לא נוצר כפיל.

## ממצאים מאומתים
- הדף נטען תקין, אין חסימת Cloudflare בטעינה.
- קלט מצפה לקישור מלא, לא לשם משתמש.
- מסך הסכמה (Consent, 210 שותפים) מופיע וחוסם לסירוגין.
- endpoints שנצפו: userInfo, postsV2, posts. לא נצפה stories בריצות האחרונות.

## השערות
- ייתכן שהזרימה החדשה: userInfo קודם, ואז stories רק אחרי לחיצה על טאב — אבל הטאב לא מופיע כי userInfo נכשל/נחסם על ידי הסכמה.
- ייתכן שיש Turnstile סמוי שחוסם לסירוגין.

## אפשרויות שנשללו
- חסימת IP כגורם יחיד.
- פותר Cloudflare כפתרון מיידי.

## בדיקות וניסויים שבוצעו
- 4 שמות עם שם משתמש בלבד — כשל עקבי.
- קישור מלא `https://www.instagram.com/instagram/` — בקשות API נצפו פעם אחת.
- קישור מלא `https://www.instagram.com/israeli_songs/` עם המתנה 15 שניות — אפס בקשות API.
- 2026-10-05: לכידת payload מלא עם קישור מלא ל-3 השמות — כל הבקשות (`userInfo`, `postsV2`, `posts`) החזירו 422 `{"code":"CAPTCHA_REQUIRED","challenge":{"type":"turnstile","siteKey":"0x4AAAAAABhLwGG2XCb7fE2M"}}`. החתימות (`ts`,`_ts`,`_tsc`,`_sv`,`_s`) נוצרות בדפדפן אבל לא מספיקות ללא טוקן Turnstile.

## שאלות פתוחות
- מה payload הנכון ל-userInfo החדש? צריך ללכוד `post_data` כשהבקשה כן מצליחה.
- האם הסכמה ניתנת לסגירה אוטומטית בצורה יציבה?
- האם stories עדיין קיים כ-endpoint או הוחלף?

## צעדים הבאים
1. ללכוד `post_data` ותשובת userInfo בהצלחה אחת יציבה.
2. לבדוק חילוץ תאריך (`taken_at`) מהתשובה החדשה.
3. להחליט: התאמה ל-fastdl החדש או מעבר לאתר חלופי.

## מסקנה סופית
זמנית: הבעיה היא שינוי חוזה באתר + מסך הסכמה, לא חסימת IP. פותרים לא רלוונטיים כרגע.
