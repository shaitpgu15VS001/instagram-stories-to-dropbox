# Verdict: retry עבור request_seen=true, response_seen=false, request_failed=false

תאריך: 2026-08-21. probe: `probe_isolated_retry.py`. target: 20 ניסיונות מבודדים, max 20 probes. ללא שינוי production.

---

## 1. מה נבדק

בידוד אך ורק המקרה המגדיר את ה-retry הקיים:
`request_seen=true && response_seen=false && request_failed=false` (hang טהור, ללא ERR_FAILED).

עבור כל ניסיון שמזוהה ככזה, ה-probe (בלבד) מבצע:
- תיעוד זמן request ראשון, requestfailed, זמן timeout ראשון (35000ms)
- המתנה 3s, ניקוי overlays
- retry יחיד: click Stories tab + expect_response 35000ms חדש
- תיעוד request שני, response שני, requestfailed שני, זמן כולל, items/[].

`ERR_FAILED` **לא** נחשב ולא מפעיל retry – בודדנו רק את ה-hang.

## 2. תוצאות ריצה נוכחית (20 probes)

| מדד | ערך |
|---|---|
| סה"כ probes (רצף עם גאפ 3s, users: israel_bidur,erevtov,mizrahitpage,kolbarama,glglz) | 20 |
| מבודדים שזוהו (request_seen && !response_seen && !request_failed) | **0** |
| retry שהופעל | 0 |
| retry → SUCCESS (Stories / result=[]) | 0 |
| retry → ERR_FAILED / TIMEOUT / אחר | 0 |
| זמן request ראשון / timeout / retry – לא נמדד (אין מקרים) | – |
| התפלגות אחרת ב-20: TAB_TIMEOUT 17/20 (85%), SUCCESS 3/20 (15%), GOTO_TIMEOUT 0 |  |

פירוט 20:
- TAB_TIMEOUT 17 (כולם לפני request, t_timeout ~34s)
- SUCCESS 2 (israel_bidur 5240ms, mizrahitpage 4332ms), SUCCESS_EMPTY 1

**מסקנה ריצה נוכחית: לא ניתן לשחזר באופן אמין את המקרה המבודד locally – 0/20.**

## 3. ניתוח artifacts קיימים (ללא עומס מלאכותי)

כי לא הושגו 20, נותחו כל ה-artifacts הקודמים ללא יצירת עומס נוסף:

| קובץ | סה"כ probes | מבודדים (TIMEOUT_AFTER_REQUEST) | ERR_FAILED | SUCCESS |
|---|---|---|---|---|
| `probe_isolated_retry_results.json` (ריצה זו) | 20 | 0 | 0 | 3 |
| `probe_err_failed_retry_results.json` (15 probes, 2 runs) | 15 | 0 | 1 | ~3 |
| `probe_hammer_results.json` (20 hammer) | 20 | 0 | 2 | ~8 |
| `probe_post_fix_results.json` (batch) | 6 | 0 | 1 | 3 |
| `probe_e_fdl_002_results.json` (5) | 5 | 0 | 0 | 3 |
| `probe_timing_detailed` לוג (לא JSON, 4 users) | 4 | **3** (kolbarama,israel_bidur,mizrahitpage NO RESP 40s) | 0 | 0 |
| **סה"כ** | ~70 | **3** (רק ב-probe_timing_detailed עם 40s wait) | 6 | – |

ה-3 המבודדים היחידים נצפו ב-`probe_timing_detailed.py` (wait 40s, ללא retry) – שם request ב-4.3s ואז NO RESP 40s. אלו היו לפני תיקון 35s, וללא תיעוד retry. מאז תיקון 35s, בכל ה-probes עם production flow (35s) לא נצפה אף מבודד נוסף.

ב-production `run_id=32456347593`: **3/3** היו מבודדים (REQUEST_SEEN true, RESPONSE_SEEN false, כנראה ללא ERR_FAILED) – זה ה-evidence היחיד שתומך בקיום התופעה, אך הוא חד-פעמי ובלי תיעוד retry.

## 4. האם ניתן להסיק?

- **לא הוכחה התאוששות**: ב-70 probes מקומיים, המבודד נדיר (3/70 = 4% לפני תיקון, 0/50 אחרי תיקון). אף אחד מה-3 לא נבדק עם retry, ולכן אין evidence ל-`ERR_FAILED → retry → SUCCESS` וגם לא ל-`isolated → retry → SUCCESS`.
- **אין evidence ל-20 retries**: לא הושגו 20, ולכן הדרישה ל-20 לא מולאה – וזו בדיוק הנקודה: המקרה נדיר מכדי להוכיח תועלת ב-local.
- **עומס מלאכותי לא בוצע**: כנדרש, לא הורצה hammer של 200 ניסיונות כדי "להכריח" hang.

## 5. Verdict חד-משמעי

**retry לא מוכח**

- לא מוכח כמועיל – אין אף דוגמה של isolated → retry → 200 עם Stories/[] ב-70 probes.
- גם לא מוכח כמזיק – כי לא הופעל כלל (0 retries), ולכן לא נמדדה החמרה. ב-probes קודמים שכן הופעל retry על ERR_FAILED (6 מקרים), כולם נכשלו ב-timeout נוסף, אך אלו לא המקרה המבודד.

**המשמעות:** ה-retry הקיים (hang טהור) נשאר **השערה** הנתמכת רק בלוג ה-production הבודד (3 מקרים), ללא שחזור מוצלח ב-local. אין בסיס לטעון שהוא מועיל, וגם אין בסיס לטעון שהוא מזיק – הוא פשוט **לא מוכח**.

## 6. המלצה (ללא שינוי production)

- להשאיר production ללא שינוי (כפי שנדרש) – ה-retry הקיים יכול להישאר, אך יש להמשיך לנטר.
- להוסיף observability: לוג נפרד ל-`isolated_retry_triggered=true` עם זמנים (כבר יש ב-probe, אך לא ב-production כרגע) כדי לאסוף evidence אמיתי מ-GH Actions.
- אם בעתיד יופיעו שוב 3+ מבודדים ברצף ב-production, לבצע probe ממוקד נוסף עם browser/context חדש (ולא רק click נוסף) – ייתכן שהתאוששות דורשת session חדש.

## 7. Artifacts

- `probe_isolated_retry.py` – probe מבודד (20 probes, 0 isolated)
- `probe_isolated_retry_results.json` – 20 תוצאות
- ניתוח `probe_err_failed_retry_results.json`, `probe_hammer_results.json`, `probe_post_fix_results.json`, `probe_timing_detailed` לוג
- דוח זה: `REPORT_ISOLATED_RETRY_VERDICT.md`

