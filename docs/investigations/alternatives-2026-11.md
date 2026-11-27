# חקירת מקורות חלופיים לסטוריז — נובמבר 2026

**תאריך חקירה:** 2026-11-27
**מטרה:** למצוא אלטרנטיבות מוכנות למקרה ש־ClipSaver (המקור הראשי הנוכחי) יופסק, בדגש על מקורות ללא Captcha שעובדים מ־GitHub Actions.
**שיטה:** חיפוש ברשת + בדיקות HTTP חיות (requests, ללא דפדפן) לסימני הגנה (`turnstile`, `challenge-platform`, `data-sitekey`, `captcha`, `just a moment`) וסקירת תיעוד ה־API של המועמדים.
**הערה:** כל הבדיקות בוצעו ממכונת הפיתוח; לא נדרש מפתח עבור סריקת דפי הבית.

## ממצא מרכזי

**כמעט אין אלטרנטיבות חינמיות־לגמרי (בלי מפתח) שעובדות מ־GitHub Actions.** האתרים החינמיים שפונים לנתונים ציבוריים של אינסטגרם חושפים API דרך Cloudflare/Turnstile, או שהם מתים. אלה שעובדים בלי מפתח (כמו ClipSaver) הם בדיוק אלה שחוסמים כתובות IP של מרכזי נתונים (datacenter) לאחר זמן מה.

**מסקנה:** הדרך היציבה היחידה היא API עם מפתח. רוב השירותים מציעים **tier חינמי קטן** — מספיק לבדיקה ולהרצות ספורות.

## בדיקות חיות — אתרים חינמיים (סריקת דף בית)

| אתר | סטטוס | סימני הגנה | מסקנה |
|---|---|---|---|
| clipssaver.com | 200 | אין | המקור הנוכחי; חסם IP אחרי ~110 בקשות טוקן |
| snapgram.io | 200 | אין | Next.js; לא חשף API פשוט בבדיקה הראשונית |
| getlurk.app | 200 | אין | אותו דבר |
| dolphinradar.com | 200 | אין בדף הבית | Turnstile בטעינת סטוריז (לפי `screening.md`) |
| **insta-stories.io** | 200 | **turnstile** | **החמיר** — המקור הישן עבר Captcha; לא שמיש כגיבוי |
| storyviewer.io | 200 | אין | סתם בלוג WordPress, לא כלי הורדה |
| igram.world | 200 | turnstile, captcha | נפסל |
| instanavigation.io | 200 | turnstile | נפסל |
| anony-ig.com | 200 | turnstile | נפסל |
| storiesig.info | 200 | turnstile, captcha | נפסל |
| qoobee.io / instastoriesdown.com / saveinsta.app / igstory.site | שגיאת חיבור | — | נפסלו (לא נגישים) |

### מאמר השוואה חיצוני (Medium, יולי 2026)
בדיקה של 7 צופי סטוריז אנונימיים: IgAnony ו־InstaNavigation הם אותו אתר; picnob (לשעבר pixwox) ו־mollygram נכשלו בטעינה; Inflact מגביל לפרופיל אחד ביום. כולם פועלים בשיטה זהה — השרת שלהם שולף נתונים ציבוריים. אף אחד לא עובד על חשבונות פרטיים. המאמר נכתב ע"י מפתח StoriesFly (לא נייטרלי), אבל הטבלה עקבית עם הבדיקות החיות שלנו.

## אלטרנטיבות עם API (דורשות מפתח, רובן עם tier חינמי)

| שירות | נקודת קצה לסטוריז | חינם | מחיר בהמשך | Captcha | מגבלת קצב |
|---|---|---|---|---|---|
| **herascrape** | `GET /users/{pk}/stories` (אחרי פתרון שם←pk) | **$1 = 2,500 בקשות** (חיבור Telegram) | **$0.40 / 1,000** | אין | **50 req/s** |
| storiesfly | `GET /v1/user/stories?username=` | 100 בקשות | $1.50 / 1,000 | אין | 1–5 req/s |
| instagapi | `GET /api/v1/user/stories/by/username?username=` | 30 בקשות/חודש | $8.9/חודש (3,000) | אין | 1,000/h |
| socialfetch | API אחד ל־87 פלטפורמות | 100 credits | לפי התמחור | אין | — |
| scrapingbot | posts/reels/stories | 100 credits | לפי התמחור | אין | — |
| profilequery / inscrape / reefapi / tikhub | נקודות סטוריז | tier חינמי קטן | varies | אין | varies |

### herascrape — מועמד מוביל (מבוסס על Datacircle + התיעוד הרשמי)
- מדורג **ראשון** מתוך 46 ספקי Instagram post API בבנצ'מרק של Datacircle (ציון 82/100, נתונים **live**, נבדק 2026-11-05).
- **הכי זול בשוק**: $0.40 ל־1,000 בקשות (פחות מפי 4 מ־StoriesFly); 2,500 בקשות בחינם רק עבור חיבור Telegram; יתרה לא פוקעת.
- **מגבלה נדיבה**: 50 בקשות/שנ' — מתאים ל־4 חלקים מקבילים.
- זרימה: תחילה `GET /users/username/{username}` → `pk`, ואז `GET /users/{pk}/stories`. שתי קריאות למשתמש.
- שגיאות מתועדות: `profile_not_found`, `private_account`, `too_many_requests`, `upstream_error` (זמני — ניתן למיפוי ל־`None`).
- ספריית לקוח רשמית: `pip install herascrape`; תיעוד ב־`herascrape.com/docs`.
- תנאי שימוש: אוסר שימוש לרעה (מעקב, doxxing, מכירת מידע); מתיר ארכוב של תוכן ציבורי בכפוף לחוק.

### storiesfly (כבר נחקר בעבר)
- `GET /v1/user/stories?username=` עם כותרת `X-Api-Key`. 100 חינם, $1.50/1,000 afterwards. rate limit 1 req/s (Free) עד 5 (Growth).
- יתרון: קריאה אחת למשתמש, בלי צורך ב־pk. חסרון: יקר פי ~4 מ־herascrape.

## כיוונים שנשללו
- **אתרי viewer (instanavigation, anony-ig, storiesig, igram, mollygram, picnob, inflact):** Turnstile/Captcha, שבורים, או מגבילים חזק. כמו רוב האתרים שנבדקו ב־`screening.md`.
- **Apify actors ("No API Key, No Login"):** Apify עצמה דורשת חשבון וקרדיטים — לא חינמי באמת.
- **Self-hosted (instaloader, ig-story-viewer):** דורש IP ביתי/פרוקסי; לא מתאים ל־GitHub Actions ללא הקמת runner מקומי.
- **WARP / VPN:** מחליפת IP של GitHub ב־IP של Cloudflare; מול שירות שגם הוא מאחורי Cloudflare אין בטחון שה־403 נעלם (ראה דיון בצ'אט).

## המלצה
1. **herascrape כגיבוי מוכן** — ה־API היציב והזול ביותר, עם 2,500 בקשות חינם (≈5 ריצות מלאות של 463 משתמשים).
2. דורש מפתח: רישום ב־herascrape.com + חיבור Telegram (פעולה של המשתמש).
3. אם מיושם: לחבר אחרי ClipSaver בשרשרת המקורות, דרך Secret `HERASCRAPE_KEY`; להשתמש באותו דפוס כמו `clipssaver_api.py`.
4. **לעדכן את `screening.md`**: insta-stories.io עבר Turnstile — הגיבוי הישן אינו זמין יותר.

## ראיות
- בדיקות HTTP חיות (2026-11-27): טבלת האתרים למעלה.
- Datacircle: `datacircle.dev/best-instagram-post-api` (46 ספקים; herascrape #1), `datacircle.dev/instagram-post-apis/herascrape/free-...`.
- תיעוד רשמי: `herascrape.com/docs/api/users` (נקודות stories/highlights, שגיאות, פתרון pk), `herascrape.com/pricing` ($0.40/1k, $1 חינם דרך Telegram).
- Medium: "I Tested 7 Anonymous Instagram Story Viewers (July 2026)" — השוואת צופים (מחבר מפתח StoriesFly).
- `storiesfly.com/developers`, `instagapi.com/instagram-stories-api`.

## מצב
תועד בלבד — **לא מומש**. ממתין להחלטה האם לחבר גיבוי בפועל.
