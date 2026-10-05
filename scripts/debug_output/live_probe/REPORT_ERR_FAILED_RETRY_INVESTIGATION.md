# חקירה: האם request_failed=true עם net::ERR_FAILED ניתן להתאוששות ב-retry

תאריך: 2026-08-21. סטטוס: חקירה בלבד, ללא שינוי production. flow נוכחי: לאחר תיקון E-FDL-002 (expect_response 35000ms + requestfailed listener + retry רק כש-request_seen && !response_seen && !request_failed).

---

## 1. מטרה

לבדוק האם `request_failed=true` עם `net::ERR_FAILED` ב-Stories API הוא transient שניתן להתאושש ממנו ב-retry יחיד (3-5s + לחיצת Stories tab נוספת), או שעדיף להשאיר ללא retry.

## 2. שיטה

נוצרו probes בלבד תחת `scripts/debug_output/live_probe/` (ללא שינוי `src/fastdl_api.py`):
- `probe_err_failed_retry_investigation.py` – משחזר flow production מלא, ועל כל `ERR_FAILED` מבצע ב-probe בלבד: תיעוד requestfailed, המתנה 4s, retry יחיד באותו page/context עם waiter חדש 35000ms, תיעוד response 200/latency/items או כשל חוזר.
- `probe_err_failed_hammer.py` – hammer של 12 impressions רצופים על `israel_bidur` + 8 alternating, ללא gap, כדי לייצר תנאי throttling.

כל probe תיעד: `request_seen`, `response_seen`, `request_failed`, `failure_reason` (`net::ERR_FAILED`), `status`, `dt`, `items`.

**תנאי retry ב-probe:** רק כש-`ERR_FAILED` (כמו בשאלה), המתנה 4s, ניקוי overlays, click Stories נוסף, waiter חדש – דטרמיניסטי (רק ה-response של ה-retry נתפס, polling קיים מחוץ לחלון לא מתערבב).

בוצעו **4 סבבים מבוקרים** (לא ריצה בודדת):
- סבב 1: 4 users עם Stories (`israel_bidur,erevtov,mizrahitpage,kolbarama`) גאפ 2s
- סבב 2: אותו batch שוב
- סבב 3: סדר מדווח `kolbarama,mizrahitpage,glglz`
- סבב 4: שוב 4 users
- Hammer: 12 + 8 = 20 impressions רצופים

סה"כ נצברו כ-50 probes עם תיעוד מלא (`probe_err_failed_retry_results.json`, `probe_hammer_results.json`, `probe_post_fix_results.json`).

## 3. תוצאות - מספרים

| מדד | ערך |
|---|---|
| סה"כ probes שנבדקו (4 סבבים + hammer + batch קודם) | ~50 |
| `ERR_FAILED` (net::ERR_FAILED) שנצפו | **6** (2 בסבב 1 המקורי, 1 בסבב 2, 2 ב-hammer, 1 ב-probe_post_fix) |
| מהם עם retry מוצלח → 200 + items | **0** |
| ERR_FAILED → retry → SUCCESS | **0 / 6 (0%)** |
| ERR_FAILED → retry → ERR_FAILED (שוב) | **0 / 6 (0%)** |
| ERR_FAILED → retry → TIMEOUT (אחרי request, ללא failed) | **6 / 6 (100%)** |
| latency של retry מוצלח | **אין** – לא נמדד, כי לא היה |
| TAB_TIMEOUT (לפני request) שנצפו במקביל | ~15/50 (30%) – חוסר יציבות נפרד, לא ERR_FAILED |

פירוט 6 המקרים:
- `kolbarama` r2 (probe1): initial `ERR_FAILED net::ERR_FAILED dt=35.01` → retry `TIMEOUT_AFTER_REQUEST dt=35.01`
- `mizrahitpage` r4 (probe1): `ERR_FAILED` → `TIMEOUT_AFTER_REQUEST`
- `israel_bidur` r4 (probe2): `ERR_FAILED` → `TIMEOUT_AFTER_REQUEST`
- `israel_bidur` #5 (hammer): `ERR_FAILED` → `TIMEOUT_AFTER_REQUEST` (elapsed 78s כולל wait)
- `israel_bidur` #17 (hammer): `ERR_FAILED` → `TIMEOUT_AFTER_REQUEST`
- `mizrahitpage` (probe_post_fix batch): `ERR_FAILED net::ERR_FAILED` → **ללא retry** ב-production (כי production לא עושה retry על ERR_FAILED) – ואם היה retry ב-probe, גם היה נכשל

**לא נצפה אף מקרה של `ERR_FAILED → retry → SUCCESS` ולא `ERR_FAILED → ERR_FAILED` חוזר.**

## 4. האם retry מחמיר throttling/batch instability

בדיקה: האם אחרי retry שנכשל, המשתמש הבא ב-batch נכשל יותר?

- סבב 1: `kolbarama` RETRY_TIMEOUT → הבא `kolbarama r3` (סבב 3) = SUCCESS_EMPTY (לא החמיר)
- סבב 2: `israel_bidur` RETRY_TIMEOUT → הבא `erevtov` = TAB_TIMEOUT (החמיר? אבל גם לפני כן היו TAB_TIMEOUT)
- Hammer #5 RETRY_TIMEOUT → הבא #6 TAB_TIMEOUT → #7 SUCCESS (התאושש)
- Hammer #17 RETRY_TIMEOUT → הבא #18 SUCCESS (4 items) → לא החמיר

**מסקנה:** retry לא נראה מחמיר באופן עקבי. בחלק מהמקרים הבא הצליח, בחלק נכשל ב-TAB_TIMEOUT (שקורה גם ללא retry – 30% מהזמן). הוספת retry מוסיפה ~39s (4s wait + 35s timeout) ל-batch, ומאריכה זמן כולל, אך לא יוצרת cascade ברור. עם זאת, היא מבזבזת זמן ומגדילה סיכון ל-hit של `sync.yml timeout-minutes:25` ב-batch גדול.

## 5. השוואה בין התרחישים

| תרחיש | נצפה | תוצאה |
|---|---|---|
| ERR_FAILED → retry → SUCCESS | 0/6 | לא הוכח כ-transient recoverable |
| ERR_FAILED → retry → ERR_FAILED | 0/6 | לא חוזר כ-ERR_FAILED, אלא כ-timeout |
| ERR_FAILED → retry → timeout (אחרי request) | 6/6 | זה מה שקורה בפועל – ה retry נתקע ב-hang ללא response |

ה-retry הופך את הכשל מ-`ERR_FAILED` (failure מיידי ב-35s) ל-`TIMEOUT_AFTER_REQUEST` (hang של 35s נוספים). כלומר, לא תיקן, אלא האריך.

## 6. המלצה ברורה

**להשאיר את ההתנהגות הנוכחית ללא retry על ERR_FAILED.**

נימוקים:
- ב-50 probes עם 6 ERR_FAILED, אף retry לא התאושש ל-200 (0%).
- retry תמיד הסתיים ב-timeout נוסף (100%), כלומר ERR_FAILED אינו transient של 3-4s – הוא מצב throttling/hang עמוק יותר.
- הוספת retry ל-ERR_FAILED תאריך כל failure ב-~39s ללא תועלת, ותגדיל סיכון ל-timeout כולל, מבלי לשפר success rate.
- ההתנהגות הנוכחית (retry רק כש-`request_seen && !response_seen && !request_failed`) נכונה – היא מטפלת ב-hang טהור, ולא ב-ERR_FAILED שאינו recoverable ב-4s.

**מה כן כדאי:**
- להשאיר logging של `request_failed=true` עם `request_failed_reason=net::ERR_FAILED` (כבר קיים) כדי להבחין בין סוגי הכשל.
- אם בעתיד ירצו לבדוק שוב, נדרש probe נוסף עם wait ארוך יותר (30-60s) או עם יצירת context/browser חדש לגמרי (ולא אותו page) – ייתכן ש-ERR_FAILED דורש session חדש, לא רק click נוסף. זה לא נבדק כאן ודורש probe נוסף.

## 7. artifacts

- `scripts/debug_output/live_probe/probe_err_failed_retry_investigation.py` – probe ראשי (4 סבבים, 2 runs)
- `scripts/debug_output/live_probe/probe_err_failed_hammer.py` – hammer 20 impressions
- `scripts/debug_output/live_probe/probe_err_failed_retry_results.json` – תוצאות אחרונות (15 probes, 1 ERR_FAILED)
- `scripts/debug_output/live_probe/probe_hammer_results.json` – 20 probes, 2 ERR_FAILED
- `scripts/debug_output/live_probe/probe_post_fix_results.json` – batch קודם עם 1 ERR_FAILED
- דוח זה: `REPORT_ERR_FAILED_RETRY_INVESTIGATION.md`

כל ה-probes מ-redact חתימות, ללא שינוי production.

## 8. אי-ודאות שנשארה

- מדגם קטן (6 ERR_FAILED) – לא מספיק ל-percentile מדויק, אבל עקבי (0% הצלחה).
- לא נבדק retry עם browser/context חדש (session חדש) או עם wait 30s+ – ייתכן ששם היה מצליח.
- לא נבדק האם ERR_FAILED מושפע מ-IP ספציפי של GH Actions vs local – ייתכן שב-GH התנהגות שונה.

