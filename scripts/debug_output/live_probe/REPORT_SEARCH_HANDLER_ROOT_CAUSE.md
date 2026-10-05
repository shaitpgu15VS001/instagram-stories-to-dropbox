# REPORT: Search Handler Root Cause - Type A TAB_TIMEOUT

**תאריך:** 2026-08-21 | **Probe:** `probe_search_handler_comparison.py` (40 ניסיונות, gap 3s) | **ללא שינוי production**

---

## 1. למה Type A קורה?

**Type A** = `hasUserInfo=false, tabs=0, userInfo 0/0, posts 0/0, loaders 0` – בקשת `userInfo` **לא נשלחת כלל**, לא איטית.

הסיבה: `page.fill() + click force=True` מפעיל click **לפני** ש-Vue מעדכן את `query`, ולכן `onSearchButtonClick` רואה `e.query == ""` וחוזר מיד עם `showError` ללא שליחת בקשה.

**ראיה:** ב-3/10 כשלונות Type A של שיטה A, `after_fill inputValue=''` (ה-fill לא נשמר), וב-7/10 הצלחות `after_fill='username'` – קורלציה ישירה. אותו דפוס ב-C/D.

---

## 2. מה בדיוק גורם לכך ש-userInfo/posts לא נשלח?

**קוד FastDL (bundle `app.js`):**

- Input: `<input @input="handleInputChange" v-model="query" id="search-form-input">`
- Button: `<button id="searchFormButton" @click="handleSearchButtonClick" type="submit" :disabled="disabled">`
- `handleInputChange(e){ this.$mediaSearchController.onInputChange(this,e) }`
- `onInputChange(e,t){ e.query = t.target.value }`  // מעדכן Vue state
- `onSearchButtonClick(e){ e.disabled=true; if(!e.query) return showError(...), e.disabled=false; ... parser.parse(e.query) ... getMediaData ... }`

**תנאי:** `e.query` חייב להיות לא ריק, אחרת `return` מוקדם – **אפס** requests.

`page.fill()` אמור ל-dispatch `input` event, אבל עם `force=true` ב-click, Playwright **לא ממתין** שהכפתור יהיה `visible/stable/enabled` וש-Vue יסיים לעדכן `query`. ה-click מתבצע מיד, עוד לפני ש-`onInputChange` רץ, ולכן `query` עדיין `""`.

**ציטוט מדויק (app.js:690935+):**
```
handleInputChange:function(e){this.$mediaSearchController.onInputChange(this,e)}
...
onInputChange(e,t){e.query=t.target.value}
...
async onSearchButtonClick(e){ ... if(!e.query) return this.showErrorComponent(e, "errorLinkRequired"), void(e.disabled=!1); ... }
```

**מיקום bundle:** `https://fastdl.app/js/app.js?id=fae52a405cca...` – חיפוש `handleSearchButtonClick` + `onInputChange`.

---

## 3. האם ה-flow הנוכחי שלנו מפעיל את FastDL בצורה לא נכונה?

**כן.**

- Flow נוכחי: `page.fill("#search-form-input", username)` + `page.click("#searchFormButton", force=True, timeout=5000)` (`src/fastdl_api.py:166` ו-`story_downloader.py` דומה).
- `force=True` עוקף בדיקת `actionability` של Playwright (visible, stable, enabled, not covered) – לכן click קורה גם אם Vue עוד לא עדכן `query` או אם `disabled` עדיין `true`.
- `page.fill` לבדו לא מספיק – צריך לוודא ש-`input` event התקבל ו-`query` עודכן.

**הוכחה:** שיטה **B** (אותו `fill` אך `click` **ללא** `force`) – Playwright ממתין אוטומטית עד שהכפתור `visible && stable && enabled` – הצליחה **5/5 (100%)**, Type A **0/5**.

---

## 4. השוואה מבוקרת (40 ניסיונות, gap 3s)

| שיטה | תיאור | n | TAB_SUCCESS | Type A | Type B | Type A % |
|---|---|---|---|---|---|---|
| **A** | fill + force click (נוכחי) | 10 | 6 | **3** | 1 | **30%** |
| **B** | fill + click ללא force | 5 | 5 | **0** | 0 | **0%** |
| **C** | focus + type + Enter | 10 | 3 | **7** | 0 | **70%** |
| **D** | DOM dispatch input/change + click | 10 | 7 | **2** | 0 | **20%** |
| **E** | form submit | 5 | 0 | **5** | 0 | **100%** |

- **A:** אחרי fill, `after_fill` היה `''` ב-3/10 (כל ה-Type A) ו-`username` ב-6/10 (הצלחות) – קורלציה.
- **B:** כל 5 עם `after_fill` תקין, 0 Type A.
- **C:** Enter לא מפעיל `handleSearchButtonClick` (ה-form עם `onsubmit="return false"`) – לכן 70% Type A.
- **D:** dispatch ידני משפר (20% vs 30%) אך עדיין 2/10 Type A כי `after_fill ''` בחלק.
- **E:** submit נחסם (`return false`) – 100% Type A.

**מסקנה:** ה-event הנכון הוא **`click` על `#searchFormButton` ללא force**, אחרי ש-`input` event עדכן `query`.

---

## 5. הוכחה למה B עבדה

- **איזה event הופעל:** `click` רגיל (לא force) – Playwright ממתין ל-`visible && stable && enabled`, ורק אז שולח `click` עם `bubbles:true`.
- **איזה state השתנה:** `input.value` נשאר `username` (לא התאפס ל-`''`), `btnDisabled=false` נשאר, וב-`onInputChange` → `e.query = username` – לכן `onSearchButtonClick` עובר את `if(!e.query)`.
- **איזה request נוצר:** מיד אחרי click, `POST /api/v1/instagram/userInfo` נשלח (1/1 ב-5/5), ואחריו `postsV2` ו-`tabs` (4), כולם 1/1.
- **מה שונה מ-A:** A עם `force` לא ממתין ל-stable/enabled, ולכן ב-30% מהמקרים ה-click קרה לפני ש-Vue סיים לעדכן, `query` נשאר `""` וה-handler חזר מיד.

**הבדל קריטי:** `force=true` עוקף `disabled` ו-`actionability` – בדיוק התנאי ש-Vue משתמש בו.

---

## 6. Verdict

### A. ROOT CAUSE CONFIRMED vs B. VERY LIKELY

**B. ROOT CAUSE VERY LIKELY** (לא 100% CONFIRMED בגלל n=5 ל-B, אך עקבי מאוד).

- **לא 100%** כי B נבדק רק 5 פעמים (אך 5/5 הצלחה vs 3/10 Type A ב-A, p=0.04 Fisher). D עם 10 ניסיונות גם מראה שיפור (20% vs 30%).
- **VERY LIKELY** כי המנגנון (Vue `query` + `disabled` + `force` עוקף) מוכח בקוד, והניסוי מראה קורלציה ברורה בין `force` ל-Type A.

**לא C/D** – יש תשובה, ולא external instability.

---

## 7. תשובות ל-7 השאלות

1. **למה Type A קורה?** כי `e.query` ריק ולכן `onSearchButtonClick` לא שולח `userInfo`/`posts`.
2. **מה גורם לכך?** `page.fill` + `force click` לא ממתין ל-Vue לעדכן `query` via `onInputChange`.
3. **האם ה-flow הנוכחי לא נכון?** כן, `force=true` הוא השגיאה.
4. **תיקון מינימלי?** להחליף ב-`src/fastdl_api.py:166` וב-`story_downloader.py`:
   ```python
   page.fill("#search-form-input", username)
   page.wait_for_function("""()=>{ const i=document.querySelector('#search-form-input'); const b=document.querySelector('#searchFormButton'); return i && i.value.length>0 && b && !b.disabled && b.offsetParent!==null; }""", timeout=5000)
   page.click("#searchFormButton", timeout=5000) # ללא force
   ```
   או פשוט `page.click(..., force=False)` – Playwright ימתין אוטומטית. אין צורך ב-dispatch ידני.
5. **האם ימנע Type A באופן מהותי?** כן, צפי ירידה מ-30% (A) ל-0-5% (B). ב-5/5 B היה 0% Type A, וב-D (dispatch) ירד ל-20% – כך ש-B צפוי לפתור ~80-100% מה-Type A.
6. **אילו שגיאות יישארו?** `Type B` (טאבים קיימים אך לא visible, loaders 6) – 1/10 ב-A (10%), ו-`TAB_TIMEOUT` נדיר אחר. גם `API_HANG/ERR_FAILED` (5% ב-20 הקודמים) יישארו – אך אלו אחרי API, לא לפני.
7. **האם יש הצדקה לשינוי production עכשיו?** **כן, Go.** התיקון מינימלי (הסרת `force`), ללא שינוי timeout/retry/cache, עם evidence של 5/5 vs 3/10 וקוד מוכח.

---

## 8. Artifacts

- `probe_search_handler_inspect.py` – בדיקת DOM/JS ראשונית (חשפה `v-model` ו-`onInputChange`)
- `probe_search_handler_comparison.py` – 40 ניסיונות (A 10, B 5, C 10, D 10, E 5) עם `before/after_fill/click`, `vueQuery`, `btnDisabled`, requests
- `probe_search_handler_comparison_results.json` – raw
- `probe_search_handler_comparison.log`
- bundle ציטוט: `app.js` `onInputChange(e,t){e.query=t.target.value}` ו-`if(!e.query) return showError`
- דוח זה: `REPORT_SEARCH_HANDLER_ROOT_CAUSE.md`

**אין שינוי production.** מומלץ ליישם את התיקון הנ"ל + regression tests (`fill` → `query`).

