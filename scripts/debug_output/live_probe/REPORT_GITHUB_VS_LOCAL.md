# חקירה: GitHub Actions vs Local - האם חוסר היציבות תלוי IP/סביבה

תאריך: 2026-08-21. probe: `probe_github_vs_local.py`. ללא שינוי production, ללא hammering.

---

## 1. שיטה ומגבלות

- **Local:** 12 דגימות מבוקרות, gap 3s קבוע, אותם usernames כמו ב-GH (`kolbarama,mizrahitpage,glglz,israel_bidur,erevtov` ברוטציה), flow זהה ל-production (10s goto, 30s tabs, 35s Stories).
- **GitHub Actions:** לא ניתן להריץ probe חי ב-GH ללא יצירת workflow חדש (שהיה שינוי production). לכן הושוותה **היסטוריית 3 דגימות** מ-run `32456347593` (06:56:41, 3 users רצופים) כפי שתועדה ב-issue. זו מגבלה מרכזית.
- **IP נוסף:** אין אפשרות לגיטימית לסביבה נוספת עם IP ציבורי שונה ללא הקמת תשתית חדשה – **אין השוואת IP אמיתית** (מצוין במפורש).
- **Local IP:** `212.76.120.223` (api.ipify.org, נמדד ב-probe).
- **מדידות:** TAB_TIMEOUT, request_seen, response_seen, request_failed, ERR_FAILED, response status, request→response latency, total flow latency, SUCCESS, SUCCESS_EMPTY, timeout – זהים בשתי הסביבות.

---

## 2. תוצאות

### Local (12 דגימות, 2026-08-21)

| מדד | ערך |
|---|---|
| TAB_TIMEOUT | **9/12 (75.0%)** – כשל לפני request, `request_seen=false`, t~33.6-34.2s |
| SUCCESS | 2/12 (16.7%) – `glglz 5 items`, `mizrahitpage 1` |
| SUCCESS_EMPTY | 1/12 (8.3%) – `kolbarama 0` |
| HANG (req && !resp && !failed) | 0/12 |
| ERR_FAILED | 0/12 |
| request→response latency (SUCCESS) | avg **0.53s** (0.42, 0.89, 0.28) |
| total flow latency (SUCCESS) | avg **5.02s** (4.65, 4.88, 5.54) |
| total flow latency (TAB_TIMEOUT) | ~33.7s (כולל 30s tabs + 2.5s sleep) |

### GitHub Historical (3 דגימות, run 32456347593)

| מדד | ערך |
|---|---|
| HANG | **3/3 (100%)** – `request_seen=true, response_seen=false, request_failed=false`, timeout 35s (20s אז) |
| TAB_TIMEOUT | 0/3 |
| ERR_FAILED | 0/3 (לא דווח) |
| SUCCESS / SUCCESS_EMPTY | 0/3 |
| latency | לא נמדד, רק timeout 35s |

### השוואה ישירה (אותם 3 users)

| user | Local (מתוך 12) | GitHub (32456347593) |
|---|---|---|
| kolbarama | 1x SUCCESS_EMPTY (6.63s) + 2x TAB_TIMEOUT (33.78,34.28) | HANG |
| mizrahitpage | 1x SUCCESS (5.54s) + 2x TAB_TIMEOUT (33.61,33.57) | HANG |
| glglz | 1x SUCCESS (4.65s) + 1x TAB_TIMEOUT (33.79) | HANG |

אותו user מצליח locally ולפעמים נכשל ב-GH ולהפך – חוסר עקביות.

## 3. מענה ל-6 השאלות

**1. האם שיעור הכשל שונה משמעותית?**
- Local: 75% כשל (9/12 TAB_TIMEOUT), 25% הצלחה
- GitHub: 100% כשל (3/3 HANG)
- **לא שונה משמעותית בשיעור** (שניהם גבוהים 75-100%), אבל **שונה בסוג**: local נכשל ב-TAB, GH נכשל ב-Stories. עם n=3 בלבד ב-GH, אין מובהקות.

**2. האם latency שונה?**
- Local SUCCESS: total 5.02s, request→response 0.53s
- GitHub: אין SUCCESS לכן אין השוואה. ה-timeout בשניהם ~35s. אין evidence ל-latency שונה כשמצליח (כי GH לא הצליח).

**3. האם ERR_FAILED מופיע בעיקר בסביבה אחת?**
- Local 12: 0/12, GitHub 3: 0/3 – לא מופיע בכלל בריצה זו.
- ב-50 probes קודמים local: 6 ERR_FAILED (12%) – כן מופיע מקומית, אך לא ב-GH ההיסטורי. **אין evidence ש-ERR_FAILED הוא ספציפי לסביבה.**

**4. האם TAB_TIMEOUT מופיע בעיקר בסביבה אחת?**
- Local: 9/12 (75%), GitHub: 0/3 (0%) – נראה הבדל, אך n=3 קטן. ב-probes קודמים local גם 50-80% TAB_TIMEOUT, כך שזה דפוס מקומי עקבי. **קיים הבדל נצפה, אך לא ניתן לקבוע סיבתיות (correlation ≠ causation).**

**5. האם יש evidence ל-IP/rate limiting?**
- **לא.** אין השוואת IP אמיתית (רק local IP אחד, אין IP של GH runner). גם שיעורי כשל גבוהים בשתי הסביבות (75% vs 100%) לא תומכים ב-IP ספציפי. אם היה rate limiting לפי IP, היינו מצפים ש-GH (IP משותף) ייכשל יותר, אבל local נכשל גם כן 75%. אין evidence חזק.

**6. האם הבעיה נראית כמו instability כללית של FastDL ללא קשר לסביבה?**
- **כן, זה ההסבר הסביר ביותר עם ה-data הקיים.** שתי הסביבות מראות חוסר יציבות גבוה (75-100% כשל), אך בסטאג' שונה (local TAB, GH HANG) ועם הצלחות ספורדיות (25% local). זה מתאים ל-instability כללית של FastDL (שרת איטי/עומס) ולא ל-IP ספציפי. גם העובדה שאותו user (`kolbarama`) מצליח פעם ונכשל פעם באותה סביבה מחזקת זאת.

## 4. Verdict

**D. לא מספיק evidence** – עם הסתייגות לכיוון **B**.

- **לא A (IP/rate limiting):** אין השוואת IP אמיתית, ושיעורי כשל גבוהים בשתי הסביבות.
- **לא C (בעיה ספציפית ב-GH/network):** local נכשל גם כן 75%, כך שלא ספציפי ל-GH.
- **B (FastDL instability כללית) הוא ההסבר הסביר ביותר**, אך עם n=3 ב-GH בלבד, **אין evidence חזק** – לכן Verdict רשמי הוא **D**, עם נטייה ל-B.

> לא מוצג correlation כהוכחה, ולא נקבע מראש שזו throttling.

## 5. Recovery Strategy מומלצת (ללא מימוש)

בהתאם ל-B/D (instability כללית, לא IP):

- **לא** להסתמך על החלפת IP/סביבה (לא יפתור).
- **כן** להתמקד ב-robustness כללית: timeout 35s (כבר), הפרדה בין TAB_TIMEOUT (retry עם new context/page) לבין HANG (retry same page), ו-backoff בין users (גאפ 3s כבר קיים, אפשר 4-5s ב-batch גדול).
- עבור TAB_TIMEOUT – ניסיון עם **NEW PAGE/CONTEXT** (כ-50% הצלחה ב-probe הקודם) עדיף על SAME PAGE, אך לא אמין (ולכן לא לנסות יותר מפעם אחת).
- עבור HANG – SAME PAGE retry (כבר קיים) הוא הנכון, אך ללא evidence להצלחה (0/0 בריצה זו, 0/6 ב-ERR_FAILED).
- הכי חשוב: **observability** – לוג נפרד ל-TAB_TIMEOUT vs HANG vs ERR_FAILED כדי לאסוף עוד GH samples לפני החלטה על שינוי.

**אין לבצע שינוי production עד שייאספו לפחות 20 GH samples נוספים.**

## 6. Artifacts

- `probe_github_vs_local.py` – 12 דגימות מבוקרות
- `probe_github_vs_local_results.json` – local_ip 212.76.120.223, 12 local + 3 GH historical
- דוח זה: `REPORT_GITHUB_VS_LOCAL.md`

אין שינוי production.

