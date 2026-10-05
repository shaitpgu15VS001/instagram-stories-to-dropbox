# סינון אתרים מועמדים — אוקטובר 2026

## שיטה
בדיקת דף בית בלבד (requests, ללא דפדפן): סימני `challenges.cloudflare.com`, `data-sitekey`, `cf-turnstile-response`, `challenge-platform`, `turnstile`, `just a moment`, `attention required`.

## תוצאות
| אתר | סטטוס | סימנים | החלטה |
|---|---|---|---|
| insta-stories.io | 200 | אין | עובר לבדיקה מלאה |
| dolphinradar | 200 | אין | עובר לבדיקה מלאה |
| igstoryviewer.to | 403 | challenge-platform, attention required | נפסל |
| gramsnap | 200 | challenge-platform, turnstile | נפסל |
| inflact | 200 | data-sitekey, turnstile | נפסל |
| clipssaver | 200 | אין | עובר לבדיקה מלאה |
| snapgram | 200 | אין | עובר לבדיקה מלאה |
| storiesig | 200 | challenges + turnstile | נפסל |
| storiesdown.co | 200 | challenges + data-sitekey + turnstile | נפסל |
| gramho.app | שגיאת חיבור | — | נפסל (לא נגיש) |
| getlurk.app | 200 | אין | עובר לבדיקה מלאה |

## מסקנה
5 עוברים לסינון שני (חיפוש חי): insta-stories.io, dolphinradar, clipssaver, snapgram, getlurk.
6 נפסלו (5 עם Turnstile/Cloudflare + 1 לא נגיש).
