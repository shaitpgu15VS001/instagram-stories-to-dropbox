# Verdict ניסוי הכרעה Type A

**תאריך:** 2026-08-21 | **Probe:** `probe_typeA_experimental.py` (12 ניסיונות, gap 3s) | **ללא שינוי production, ללא retry, ללא שינוי timeout, ללא cache/context**

---

## 1. מה נבדק

היפותזה: Type A (37.5% בכלל, 75% מה-TAB_TIMEOUT) נגרם כי ה-Search click מתבצע לפני שה-Vue/app ו-userInfo מוכנים.

Flow ניסיוני (vs baseline):
1. המתנה עד ש-`#searchFormButton` קיים, `disabled=false`, `window.Vue` קיים (waitForFunction 5s) + תיעוד `btnDisabled`, `vueExists`, `readyState`.
2. click.
3. המתנה מפורשת ל-`userInfo` `POST 200` עם `expect_response` timeout 15s.
4. רק אחרי success המתנה ל-Stories tabs (30s).
5. תיעוד: Type A/B, SUCCESS, timings click→userReq, req→resp, resp→tabs.

Baseline להשוואה: `probe_tab_timeout_root_cause.py` (16 probes, 8 TAB_TIMEOUT, מתוכם 6 Type A = 37.5% כלל, 75% מה-TAB).

## 2. תוצאות (12 ניסיוני)

| outcome | n | % | baseline |
|---|---|---|---|
| TAB_TIMEOUT_TYPE_A | **10/12 (83.3%)** | **החמרה** | 6/16 (37.5%) כלל, 6/8 (75% מה-TAB) |
| TAB_TIMEOUT_TYPE_B | 0/12 (0%) | שיפור | 2/16 (12.5%) |
| TAB_SUCCESS | 2/12 (16.7%) | ירידה | 8/16 (50%) |

- **Type A לא נעלם – עלה מ-37.5% ל-83.3%.**
- Type B נעלם (0/12 vs 2/16) – אך זה כי כל הכשלים הפכו ל-Type A (userInfo לא נשלח כלל, אז לא מגיעים ל-Type B).

### Timings

- **הצלחות (2):**
  - `glglz`: click→userReq **2572ms**, req→resp **2ms**, resp→tabs **15044ms**, total 21.1s, pre `btnDisabled=false vue=true`
  - `israel_bidur`: 2523ms, 4ms, 15074ms, total 19.6s
  - click→userReq ~2.5s (כולל `sleep 2.5s` הקיים) – userInfo נשלח רק אחרי ה-sleep.

- **כשלונות Type A (10):**
  - `pre_click_state`: תמיד `btnDisabled=false vue=true` (ה-wait הצליח), `readyState` לא נמדד אך vue true.
  - `userReq=None` – **אפס** בקשות userInfo נשלחו (0/0), גם אחרי המתנה 15s.
  - `total ~49-50s` (15s userInfo wait + 30s tabs + overhead) – ארוך יותר מ-baseline (~34-35s).

### תצפית מרכזית

ההמתנה ל-`Vue` הצליחה תמיד (`vue=true`), אך Type A עדיין 83% – כלומר **Vue ready אינו הגורם**.

ההמתנה ל-`userInfo` תמיד נכשלה ב-Type A (timeout 15s, `has_req false`) – כי הבקשה כלל לא נשלחה, לא כי היא איטית. לכן `waitForResponse` מיותר ורק מאריך.

## 3. מבחן הכרעה

**המבחן:** האם Type A נעלם או יורד משמעותית מ-6/8 (75% מה-TAB)?

**תוצאה:** **לא – עלה ל-10/12 (83%)**. אין שיפור, יש החמרה.

- Baseline Type A: 6/8 = 75% מה-TAB, 6/16 = 37.5% כלל
- Experimental Type A: 10/10 = 100% מה-TAB, 10/12 = 83% כלל

**ההבדל מובהק לרעה**, לא לטובה.

## 4. Verdict חד

**C. אין שיפור → NO-GO**

אין הצדקה לתקן production עם flow ניסיוני זה. הוא לא פותר Type A, אף מחמיר (מאריך total ב-15s ומעלה שיעור כשל).

### למה?

- `btnDisabled=false + vue=true` כבר מתקיים ב-100% מהמקרים (גם בכשלונות), כך שה-wait הזה מיותר.
- `userInfo` לא נשלח כלל ב-Type A, לכן `waitForResponse` לא יכול להצליח – הוא רק מוסיף timeout.
- Type A אינו race של Vue ready, אלא **אי-שליחת הבקשה** – כנראה ה-Vue handler ל-search לא נקשר, או שה-input event לא הופעל.

## 5. ההיפותזה הבאה שצריך לבדוק

**היפותזה הבאה:** ה-`page.fill()` + `page.click(force=True)` לא מפעיל את ה-Vue `v-model` / `input` event, ולכן ה-search handler לא שולח userInfo.

**ניסוי אחד ממוקד שיכריע:**

Probe עם 10 ניסיונות, אותו gap 3s, ללא שינוי timeout/retry/context, המשווה:

- **שיטה נוכחית:** `page.fill()` + `click force`
- **שיטה ניסיונית:** `page.evaluate(() => { input.focus(); input.value='user'; input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); input.dispatchEvent(new KeyboardEvent('keydown',...)) })` + המתנה 500ms + `click` **ללא force** או עם `press('Enter')`

**קריטריון הכרעה:** אם Type A יורד מ-6/8 ל-≤2/8, ההיפותזה אומתה ו-Go לתיקון `fill` → `evaluate dispatchEvent`. אם נשאר ≥5/8, ההיפותזה נפסלת וצריך לבדוק `form submit` vs `button click` או `networkidle`.

**אין לשנות production עד תוצאות ניסוי זה.** ההמלצה כרגע היא **NO-GO**.

---

## Artifacts

- `probe_typeA_experimental.py` (12 ניסיונות, wait Vue + wait userInfo 15s)
- `probe_typeA_experimental_results.json` (10 Type A, 2 SUCCESS)
- `probe_typeA_experimental.log`
- דוח זה: `REPORT_TYPEA_EXPERIMENT_VERDICT.md`

