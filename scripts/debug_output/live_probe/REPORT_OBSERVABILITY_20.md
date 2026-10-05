# Observability - 20 דגימות אמיתיות לפני בחירת Recovery

תאריך: 2026-08-21. Probe: `probe_observability_20.py`. ללא שינוי production, ללא hammering (gap 3s קבוע, flow רגיל כמו workflow).

---

## 1. שיטה

- 20 דגימות רצופות, אותם 5 users כמו ב-GH (`kolbarama,mizrahitpage,glglz,israel_bidur,erevtov` ברוטציה, pos 1..5), gap 3s בין ניסיונות (כמו `MIN_DELAY 2-3` ב-workflow).
- כל דגימה: browser חדש, flow מלא (goto → search → tabs → Stories click), תיעוד 13 שדות בנפרד (page_load_start/done, search_ready, click, tabs_wait, stories_click, REQUEST_SEEN, RESPONSE_SEEN, request_failed, reason, response_status, request_to_response_ms, total_flow_ms, outcome).
- סיווג ל-7: SUCCESS, NO_ACTIVE_STORIES, TAB_TIMEOUT, API_HANG, API_ERR_FAILED, OTHER_TIMEOUT, OTHER_ERROR.
- **מגבלה:** לא ניתן להריץ probe חי ב-GitHub Actions ללא יצירת workflow חדש (שינוי production). לכן 20 הדגימות הן **local המדמה GH flow** (אותו timeout 35s, אותו UA, אותו gap). היסטוריית GH האמיתית הזמינה היא 3 דגימות מ-`run 32456347593` (HANG) – מצוינת להשוואה, אך לא 20. ל-20 GH אמיתיות נדרשים 4-5 הרצות workflow ב-GH (כל הרצה ~5 users).

## 2. התפלגות outcomes (20)

| outcome | n | % | raw evidence |
|---|---|---|---|
| SUCCESS | 8 | 40.0% | glglz 5, mizrahitpage 1×2, israel 7×2, erevtov 11×2, glglz 5 |
| NO_ACTIVE_STORIES | 1 | 5.0% | kolbarama [] 0 |
| TAB_TIMEOUT | 10 | 50.0% | כל 10 עם `request_seen=false`, `tabs_wait 30s`, total ~34s (ראה raw) |
| API_HANG | 0 | 0.0% | – |
| API_ERR_FAILED | 1 | 5.0% | israel_bidur 14, `request_seen=true response_seen=false failed=true reason=net::ERR_FAILED` total 39.4s |
| OTHER_TIMEOUT | 0 | 0.0% | – |
| OTHER_ERROR | 0 | 0.0% | – |

**סה"כ הצלחה (SUCCESS+NO_ACTIVE): 9/20 (45%), כשל: 11/20 (55%).**

Raw לכל failure שמור ב-`probe_observability_20_results.json` (כולל page_load, tabs, request_failed_reason).

## 3. Latencies (רק כשיש מדידה)

- **total_flow_ms** (20): p50 34041ms, p90 35049ms, p95 35640ms, min 4430ms, max 39430ms. הפיצול דו-מודאלי: SUCCESS ~4.4-6.4s, TAB_TIMEOUT ~34s.
- **request_to_response_ms** (9 SUCCESS): p50 308ms, p90 425ms, p95 520ms, min 244ms, max 614ms (כולל kolbarama [] 244ms). **כשה-API מצליח הוא מהיר (<1s).**

## 4. כמה לפני API, כמה אחרי

- **לפני API request:** 10/20 (50%) – כל ה-TAB_TIMEOUT (`request_seen=false`)
- **אחרי API request:** 1/20 (5%) – ERR_FAILED (HANG 0)
- **ERR_FAILED:** 1/20 (5%)
- **HANG:** 0/20 (0%)

ב-3 הדגימות ההיסטוריות מ-GH: לפני 0/3, אחרי 3/3 (HANG). **הבדל בסוג, אך שיעור כשל כולל דומה (55% local vs 100% GH n=3).**

## 5. קשר ל-user

| user | outcomes (4 דגימות לכל אחד) |
|---|---|
| kolbarama | TAB 3, NO_ACTIVE 1 |
| mizrahitpage | TAB 2, SUCCESS 2 |
| glglz | SUCCESS 2, TAB 2 |
| israel_bidur | TAB 1, SUCCESS 2, ERR_FAILED 1 |
| erevtov | TAB 2, SUCCESS 2 |

**אין קשר חזק ל-user מסוים** – כל user נכשל וגם הצליח. `kolbarama` (ללא Stories) נכשל 3/4 ב-TAB, אך גם הצליח פעם אחת כ-NO_ACTIVE.

## 6. קשר למיקום ב-batch (pos 1..5)

| pos | outcomes (4 דגימות) |
|---|---|
|1|TAB 3, NO_ACTIVE 1|
|2|TAB 2, SUCCESS 2|
|3|SUCCESS 2, TAB 2|
|4|TAB 1, SUCCESS 2, ERR_FAILED 1|
|5|TAB 2, SUCCESS 2|

**אין קשר מובהק למיקום** – Pos1 מעט גרוע יותר (3/4 TAB), אך Pos4 דווקא עם ERR_FAILED היחיד. עם 4 samples ל-pos, אין מובהקות. **לא ניתן להסיק throttling מרצף failures** (כפי שנדרש, לא מסיקים).

## 7. השוואה GH vs Local (מגבלת n)

- GH (n=3): 100% HANG (אחרי API)
- Local (n=20): 50% TAB_TIMEOUT (לפני API) + 5% ERR_FAILED (אחרי)
- **שיעור כשל כולל דומה (75-100%) אך סטאג' שונה** – זה מחזק instability כללית של FastDL ולא IP ספציפי. אין evidence ל-IP blocking (אותו user מצליח ונכשל בשתי הסביבות).

## 8. Verdict

**A. הבעיה בעיקר לפני API**

- 10/11 הכשלונות (91% מהכשלונות, 50% מכלל הדגימות) הם TAB_TIMEOUT לפני request.
- רק 1/11 (9%) הוא אחרי request (ERR_FAILED), ו-0 HANG.
- גם ב-20 GH אמיתיות שייאספו, התפלגות זו מצביעה ש-TAB הוא הצוואר בקבוק, אך יש גם 5% API – לכן **C (שני הסוגים משמעותיים) קרוב**, אך עם 50% vs 5% ההכרעה היא **A**.

> אם היו 20 GH אמיתיות והן היו מראות 100% HANG כמו ב-3 ההיסטוריות, ה-verdict היה C. עם ה-data הנוכחי (20 local + 3 GH) – A.

**אם אין 20 GH אמיתיות:** Verdict נשאר **D לא מספיק evidence** ל-GH, אך ל-local בלבד – A.

**המלצה ל-20 GH אמיתיות:** להריץ workflow 4-5 פעמים (כל פעם 5 users, gap רגיל) ולאסוף 20 GH samples עם לוג 13 השדות, ואז להכריע סופית בין A ל-C.

## 9. Recovery מינימלי אחד (ללא מימוש)

בהתאם ל-A (בעיקר לפני API):

**NEW PAGE/CONTEXT recovery חד-פעמי עבור TAB_TIMEOUT בלבד.**

- כאשר `tabs_wait` נכשל (30s), לסגור page/context, ליצור `browser.new_context()` חדש (לא רק reload, ולא ניקוי cache בתוך אותו context), ולבצע את כל ה-flow מחדש פעם אחת עם אותו timeout.
- לא לנסות SAME PAGE (אין tabs, צריך reload), לא FRESH SESSION (browser חדש) – B מספיק ומובחן.
- עבור API_HANG/ERR_FAILED – **לא להוסיף כרגע** (0-5% ב-data, לא מוכח).
- ללא הגדלת timeout נוספת, ללא cache/cookie clearing בתוך אותו context.

*נימוק:* TAB_TIMEOUT הוא 91% מהכשלונות, ו-probe קודם (`probe_recovery_simple`) הראה B מצליח ב-50% (4/8) עבור TAB, בעוד C רק 37% – B עדיף וקל יותר. זה מטפל ברוב הבעיה במינימום שינוי.

**אם יתברר C (שני הסוגים):** להוסיף גם SAME PAGE retry אחד עבור HANG (כבר קיים).

---

## Artifacts

- `probe_observability_20.py` (20 דגימות, gap 3s)
- `probe_observability_20_results.json` (raw לכל failure)
- `probe_observability_20_summary.json` (counts, p50/p90/p95, per_user, per_pos)
- `probe_observability_20.log`
- דוח זה: `REPORT_OBSERVABILITY_20.md`

אין שינוי production.

