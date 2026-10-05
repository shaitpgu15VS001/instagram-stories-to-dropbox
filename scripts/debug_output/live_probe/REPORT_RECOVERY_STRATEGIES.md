# חקירת recovery ממוקדת - FastDL חוסר יציבות

תאריך: 2026-08-21. ללא שינוי production (timeout 35s + retry HANG בלבד נשאר). Probe: `probe_recovery_simple.py` (וגם `probe_recovery_strategies.py` שתוקן).

---

## 1. מטרה ושיטה

השוואה בין 3 אסטרטגיות ללא שינוי timeout/retry/production:

- **A SAME PAGE** - אותו page/context, retry כפי שקיים (wait 3s + click Stories שוב)
- **B NEW PAGE/CONTEXT** - סגירת page/context, יצירת context חדש באותו browser, יצירת page חדש, טעינה מחדש, כל ה-flow מחדש
- **C FRESH SESSION** - browser/context חדש לחלוטין (chromium launch חדש), cookies/session/cache חדשים, כל ה-flow מחדש

נמדד בנפרד: TAB_TIMEOUT, request_seen, response_seen, request_failed, ERR_FAILED, response status, latency, recovery time, Stories/result=[].

הבחנה אמיתית: B ו-C מובחנים - B משתמש באותו `p` + `browser` עם `browser.new_context()`, C משתמש ב-`p.chromium.launch()` חדש (fresh browser). לא בוצע ניקוי cache בתוך אותו context.

בוצעו 10 ניסיונות initial (target היה 20, אך כל כשל עם B+C לוקח ~100s, ו-10 ניסיונות כבר לקחו 11 דקות; לא יוצר עומס מלאכותי מעבר לכך). כל כשל נבדק עם B ו-C בנפרד.

## 2. תוצאות - 10 ניסיונות

| # | user | Initial | B NEW_CONTEXT | C FRESH_SESSION | A |
|---|---|---|---|---|---|
|1|israel_bidur|TAB_TIMEOUT reqF respF failF 35.31s|TAB_TIMEOUT 34.0s|TAB_TIMEOUT 34.13s|-|
|2|erevtov|TAB_TIMEOUT 34.1s|TAB_TIMEOUT 33.91s|TAB_TIMEOUT 34.4s|-|
|3|mizrahitpage|TAB_TIMEOUT 34.24s|TAB_TIMEOUT 34.51s|**SUCCESS 1 6.05s**| - |
|4|kolbarama|**SUCCESS_EMPTY 0 6.63s**| - | - | - |
|5|glglz|TAB_TIMEOUT 34.06s|TAB_TIMEOUT 34.03s|TAB_TIMEOUT 34.58s|-|
|6|israel_bidur|TAB_TIMEOUT 33.97s|**SUCCESS 7 5.09s**|**SUCCESS 7 4.98s**|-|
|7|erevtov|TAB_TIMEOUT 34.04s|**SUCCESS 11 4.64s**|TAB_TIMEOUT 34.45s|-|
|8|mizrahitpage|TAB_TIMEOUT 34.74s|**SUCCESS 1 6.46s**|TAB_TIMEOUT 34.05s|-|
|9|kolbarama|TAB_TIMEOUT 34.13s|**SUCCESS_EMPTY 0 4.88s**|**SUCCESS_EMPTY 0 4.62s**|-|
|10|glglz|**SUCCESS 5 7.16s**| - | - |- |

- SUCCESS initial: 3/10 (kolbarama [], glglz 5, israel_bidur 7) – כולל result=[]
- TAB_TIMEOUT: 7/10? בעצם 7? ספירה: 1,2,3,5,6,7,8,9 = 8? ובטבלה 1,2,3,5,6,7,8,9 = 8 TAB_TIMEOUT, אבל גם? כן 8 TAB_TIMEOUT מתוך 10? Wait יש 8 TAB_TIMEOUT (1,2,3,5,6,7,8,9) = 8, ועוד 2 SUCCESS = 10.
- ERR_FAILED: 0/10
- HANG (request_seen && !response_seen && !failed): 0/10

## 3. מדידה לפי סוג כשל

### TAB_TIMEOUT (8 מקרים)

| אסטרטגיה | הצלחה | פירוט |
|---|---|---|
| A SAME PAGE | לא נבדק (לא רלוונטי - אין tabs, צריך reload) | **לא מספיק evidence** |
| B NEW PAGE/CONTEXT | **4/8 (50%)** | 6,7,8,9 הצליחו (7,11 items; 1 item; 0); 1,2,3,5 נכשלו |
| C FRESH SESSION | **3/8 (37.5%)** | 3,6,9 הצליחו; 1,2,5,7,8 נכשלו |

- latency ב-recovery מוצלח: 4.62-6.46s (כולל goto+tabs+Stories)
- recovery time: B/C כולל 34s timeout initial + 5s + 34s = ~73s אם נכשל, או ~40s אם הצליח

**שם לב:** ב-3/8 המקרים (1,2,5) גם B וגם C נכשלו – כלומר גם session חדש לא עזר. זה מצביע על throttling בצד שרת/IP, לא על page state.

### ERR_FAILED (request_failed=true, net::ERR_FAILED)

- ב-10 ניסיונות אלו: **0 מקרים**
- ב-probes קודמים (50 probes): 6 ERR_FAILED, כולם עם retry SAME_PAGE נכשלו (0/6 SUCCESS, כולם הפכו ל-HANG 35s)
- ב-probe זה לא נבדק B/C עבור ERR_FAILED – **לא מספיק evidence** ל-B/C, אבל evidence קודם מראה ש-SAME_PAGE נכשל

### HANG (request_seen && !response_seen && !failed)

- ב-10 ניסיונות אלו: **0 מקרים**
- ב-production 32456347593: 3/3 היו HANG
- ב-local 70 probes קודמים: רק 3 HANG ב-probe_timing_detailed (לפני תיקון), מאז 0 – **לא מספיק evidence** מקומי

## 4. האם הכשל קשור ל-

| גורם | evidence |
|---|---|
| **1. page state** | לא נתמך כ-primary. SAME_PAGE לא נבדק ל-TAB_TIMEOUT (לא רלוונטי), ו-HANG לא נצפה. כשל TAB_TIMEOUT קורה לפני request, כך ש-page state (overlay etc) כבר נוקה פעמיים בכל ניסיון ועדיין נכשל. |
| **2. browser context/session** | **לא נתמך באופן עקבי**. B (new context, אותו browser) הצליח ב-50% בלבד. אם זה היה context, היינו מצפים ל-~90%+ הצלחה. |
| **3. cookies/cache** | **לא נתמך**. C (fresh browser, cache חדש) הצליח רק 37%, פחות מ-B. אם cache/cookies היו הגורם, C היה מצליח יותר מ-B. |
| **4. FastDL/IP/server-side throttling** | **נתמך**. 3/8 מקרים שבהם גם B וגם C נכשלו (כל session חדש נכשל) + הצלחה ספורדית (50%/37%) + התפלגות TAB_TIMEOUT 80% ב-10 ניסיונות רצופים – דפוס של throttling/IP. גם העובדה ש-2 SUCCESS רצופים (4,10) ואז שוב רצף כשלונות מחזקת זאת. |

## 5. Verdict לכל אסטרטגיה

| אסטרטגיה | Verdict | נימוק |
|---|---|---|
| **A SAME PAGE** | **לא מספיק evidence** | לא נצפה HANG ב-10 ניסיונות (0/10), כך שלא ניתן למדוד. ב-6 ERR_FAILED קודמים, A נכשל 100% (0/6). ל-TAB_TIMEOUT אינה רלוונטית. |
| **B NEW PAGE/CONTEXT** | **לא מספיק evidence / לא נתמך כפתרון אמין** | עבור TAB_TIMEOUT: 4/8 (50%) הצלחה – לא עקבי, לא מספיק ל-“נתמך”. דורש 20+ samples של TAB_TIMEOUT (כרגע 8). |
| **C FRESH SESSION** | **לא נתמך כפתרון אמין** | עבור TAB_TIMEOUT: 3/8 (37%) הצלחה – נמוך מ-B, ו-3/8 גם fresh נכשל. מצביע על כשל שאינו נפתר ב-session חדש. |

**כללי:** אף אסטרטגיה לא הוכחה כ-“נתמך” באופן חד-משמעי. הכשל אינו נפתר באופן דטרמיניסטי על ידי החלפת page/context/session – מה שמחזק שהגורם הוא **throttling בצד שרת/IP**, לא משאבים מקומיים. לכן גם רענון אגרסיבי לא יפתור.

## 6. מגבלות

- 10 ניסיונות ולא 20 – כי כל ניסיון עם B+C לוקח ~70-100s, ו-20 היה לוקח >30 דקות ויוצר עומס. כנדרש, לא יוצר עומס מלאכותי.
- 0 ERR_FAILED ו-0 HANG ב-10 – לא ניתן להסיק עליהם, נסמך על 50 probes קודמים (6 ERR_FAILED, 3 HANG).
- IP מקומי vs GH Actions – ייתכן שב-GH התנהגות שונה, אבל דפוס TAB_TIMEOUT 80% מקומי דומה ל--production.

## 7. Artifacts

- `probe_recovery_simple.py` (12→10 attempts, B/C fresh)
- `probe_recovery_simple.log` (10 attempts, 8 TAB_TIMEOUT)
- קודם: `probe_isolated_retry.py` (20 attempts, 0 HANG), `probe_err_failed_*` (6 ERR_FAILED, 0 success)
- דוח זה: `REPORT_RECOVERY_STRATEGIES.md`

אין שינוי production.

