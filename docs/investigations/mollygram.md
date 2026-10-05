# בדיקת mollygram.com — אתר חלופי

## מטרה
לבדוק האם mollygram יכול להחליף את fastdl: חילוץ סטוריז, תאריך ושעה, API או DOM, עומס, התאמה ל-GitHub Actions.

## מצב נוכחי
נבדק מקומית. האתר נטען אבל לחיצת View לא מפעילה פנייה ללא פתרון Turnstile. קריאה ישירה ל-API מחזירה `Captcha verification failed`. לא ניתן לחלץ סטוריז/תאריך ללא פותר בתשלום.

## שלבי החקירה
1. טעינת דף הבית ובדיקת מבנה (שדה חיפוש, כפתורים, API).
2. בדיקה על 3 שמות: israeli_songs, idfonline, 995fm.
3. לכידת בקשות/תשובות רשת, קישורי הורדה, שדות תאריך.
4. בדיקת עומס בסיסית ויציבות.

## קבצים ומסלולי קוד שנבדקו
- טרם נבדק קוד פרודקשן — רק probe מבודד.

## ממצאים מאומתים
- עובדה (2026-10-05): דף הבית נטען עם `#link` ו-`#btn-download` (View). לחיצה לא יוצרת בקשת backend — רק טעינת Turnstile ופרסומות.
- עובדה: הטופס הוא `wire:submit` (Livewire) אבל הזרימה האמיתית ב-`my.js`: `renderOrResetTurnstile` עם sitekey קבוע `0x4AAAAAACYB7qJyv8meg-6o`, ואז `GET https://media.mollygram.com?url=<user>` עם כותרת `X-Api-Token: <turnstile-token>`.
- עובדה: קריאה ישירה ללא טוקן מחזירה `{"status":"error","msg":"Captcha verification failed"}` (אומת עם requests).
- עובדה: שלב 2 הוא `GET media.mollygram.com?url=<username>&method=allstories` עם `X-Api-Token: window.API_TOKEN` מהתשובה הראשונה. לא נבדק עד הסוף כי אין טוקן.

## השערות
- אין עדיין.

## אפשרויות שנשללו
- אין עדיין.

## בדיקות וניסויים שבוצעו
- אין עדיין.
- 2026-10-05: ניסוי Camoufox מבודד (headless+humanize) על mollygram עם `israeli_songs` — כשל: `window.turnstile` לא נטען, אפס בקשות ל-`media.mollygram.com`, תיבת הורדה ריקה אחרי 30 שניות. מסקנה: דפדפן חמקמק לא מקדם כאן, רק מאט ומסבך.
- 2026-10-05: ניסוי Patchright מבודד (channel=chrome, headless) על mollygram — כשל: אין `window.turnstile`, מיכל Turnstile מוצג אבל ווידג'ט לא נטען, אפס תשובות API אחרי 30 שניות. הורדת דפדפן Patchright נכשלה (CDN timeout), עבד רק עם כרום קיים.

## שאלות פתוחות
- האם נדרש חשבון אינסטגרם? האם יש Turnstile/Captcha?
- האם קישורי ההורדה זמניים? האם יש `taken_at`?
- האם עובד ב-headless וב-GitHub?

## צעדים הבאים
1. להריץ probe מקומי ולתעד.
2. להחליט: לאמץ או לשלול.

## מסקנה סופית
mollygram פשוט יותר מ-fastdl (GET + כותרת אחת, sitekey קבוע), אבל עדיין דורש פתרון Turnstile לכל חיפוש. ניסוי Camoufox נכשל (אין turnstile, אין בקשות API). לא מתאים לאוטומציה חינמית יציבה ב-GitHub Actions ללא שירות פתרון בתשלום.
