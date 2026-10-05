# REPORT: TAB_TIMEOUT Root Cause - FastDL Stories Tab

**Date:** 2026-08-21 | **Probe:** `probe_tab_timeout_root_cause.py` (16 probes, gap 3s) | **No production change**

---

## 1. שאלת המחקר

למה `page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)` נכשל ב-50% מהמקרים (8/16), **לפני** שנשלחת בכלל בקשת Stories API.

---

## 2. FACTS (עובדות מאומתות)

1. Stories tab אמור להופיע רק אחרי שהדף טוען פרופיל: Vue מ-render-רת `button.tabs-component__button` (POSTS/STORIES/HIGHLIGHTS/REELS) רק אחרי ש-`POST /api/v1/instagram/userInfo` ו-`POST /api/v1/instagram/postsV2` חוזרים 200.
2. ברצף 16 probes מבוקר (gap 3s, users רוטציה): **8 TAB_TIMEOUT, 8 TAB_SUCCESS** – 50% כשל, ללא hammering.
3. כל ה-probes עברו `page.goto en2 → 301 → en3yO` באופן זהה (2/2 דקות ה-redirect תקין, לא גורם).
4. ב-TAB_SUCCESS: `hasUserInfo=true`, `tabsCount=4`, `userInfo 1/1`, `posts 1/1`, `loaders 0`, Stories API נשלח מיד אחרי click והצליח (200, <1s).
5. ב-TAB_TIMEOUT: 2 תת-סוגים:
   - **Type A - Idle (6/8):** `hasUserInfo=false`, `tabsCount=0`, `userInfo 0/0`, `posts 0/0`, `loaders=0`, `console_errors=0`, `requestfailed` רק `google-analytics ERR_ABORTED` (לא רלוונטי), URL נשאר `en3yO`, `readyState=interactive`, אין בקשות FastDL אחרי search_click.
   - **Type B - Visible-but-blocked (2/8):** `hasUserInfo=true`, `tabsCount=4`, `userInfo 1/1`, `posts 1/1`, `loaders=6`, `tabs` קיימים (`POSTS/STORIES...`) אך `wait_for_selector visible` נכשל (locator מצא 4 elements אבל אף אחד לא visible).
6. Recovery A (אותו page/context, wait 10s נוספים): **0/8 הצלחה**.
7. Recovery B (page חדש, context חדש באותו browser, flow מלא מחדש): **4/8 הצלחה** (2→B SUCCESS, 8→B SUCCESS, 9→B SUCCESS, 15→B SUCCESS) – 50%.
8. `document.readyState` בכל ה-TAB_TIMEOUT היה `interactive` (לא `complete`), אך גם ב-SUCCESS היה `interactive` בהתחלה – לא מבדיל.
9. אין JS errors / page errors ב-6/8 ה-Idle (0 console errors), וב-2 ה-Visible יש 0-2 errors, לא קשור.

---

## 3. EVIDENCE (ראיות מפורטות)

### Type A Idle (6 מקרים: #2 mizrahitpage, #7 kolbarama, #8 mizrahitpage, #12 natgeo, #15 glglz, #16 israel_bidur)

- **Timeline (דוגמה #2):**
  ```
  t=886 goto_start en2
  t=1509 frame_navigated en3yO (301)
  t=2400 goto_done readyState=interactive
  t=2440 search_ready
  t=2495 search_click_done
  t=5003 post_sleep (2.5s) -> NO userInfo request sent thereafter
  t=5003-8000 only google-analytics failed (ERR_ABORTED)
  t=34000-52247 polling dom every 500ms: tabs 0, hasUserInfo false, loaders 0, no network
  t=52247 TAB_TIMEOUT
  ```
- **Network:** 26 requests total, כולם static (css, js, images) + 301, **אפס** FastDL API (userInfo/posts). 26 responses, 2 failed (google-analytics). **idle** – אין hanging request, פשוט לא נשלח.
- **DOM:** `tabsCount 0` לכל אורך 30s, `hasUserInfo false`, `overlays 0`, `loaders 0`.
- **URL:** נשאר `en3yO`, לא משתנה.
- **Recovery B:** ב-2 מתוך 6 (probes 15, 8) הצליח, ב-4 נכשל שוב עם אותו idle.

### Type B Visible-but-blocked (2 מקרים: #9 glglz, #14 mizrahitpage)

- **Timeline #9:**
  ```
  t=... search_click
  t=... userInfo POST -> 200, posts POST -> 200 (1/1)
  t=... DOM: tabsCount 4, hasUserInfo true, loaders 6, tabs=[POSTS,STORIES,HIGHLIGHTS,REELS] but visible=false
  t=52807 TAB_TIMEOUT (30s)
  t=52807-... A retry 10s: locator resolved 4 elements but visible false -> fail
  t=... B new context: SUCCESS tabs 4, loaders 0
  ```
- **Network:** userInfo/posts כן הגיעו (1/1), אך `loaders=6` (skeleton/spinner) נשאר. 2 console errors (לא קריטי).
- **DOM:** tabs קיימים ב-DOM אך `style.visibility`/`display`/`offsetParent` מונעים visible.
- **Recovery B:** #9 הצליח (new context loaders 0), #14 נכשל גם ב-B (tabs 0 ב-B).

---

## 4. HYPOTHESES (השערות שנבדקו)

| # | היפותזה | סטטוס |
|---|---|---|
| H1 | JS click על search לא שולח userInfo בכלל (Vue handler לא נקשר) | **נתמך חלקית ל-Type A** – 0/0 requests מצביע על handler שלא הופעל |
| H2 | Overlay/consent חוסם את הכפתור/טאבים | **נפסל ל-Type A** (overlays 0), **נתמך ל-Type B** (loaders 6, אך overlays 0) |
| H3 | Redirect en2→en3yO שובר את ה-flow | **נפסל** – כל ה-probes (גם הצלחות) עוברים אותו redirect |
| H4 | Network idle / FastDL server לא עונה ל-userInfo | **נתמך ל-Type A** – אין request, לא idle בגלל hang אלא בגלל שלא נשלח |
| H5 | Vue rendering תלוי ב-userInfo+posts, ואם הם לא מגיעים הטאבים לא נוצרים | **נתמך** – 6/8 ללא userInfo → ללא טאבים |
| H6 | TAB_TIMEOUT תלוי ב-user / batch position / זמן בריצה | **נפסל** – פיזור אחיד: כל user נכשל (mizrahitpage 2/3, kolbarama 1/2, etc), pos 1..5 שווה |
| H7 | ה-tab קיים אך hidden (Type B) | **אומת ל-2/8** – 4 tabs ב-DOM אך visible false |
| H8 | Page state vs context vs server – רק context חדש מתקן | **חצי נתמך** – B הצליח 50%, אבל גם נכשל 50% עם אותו idle, כך ש-context לא פותר תמיד |

---

## 5. מה נפסל

- **Redirect** – לא גורם.
- **Overlay/consent כגורם יחיד** – ב-Type A אין overlays, וב-Type B ה-overlays נוקו פעמיים לפני wait ובכל זאת נכשל.
- **JS errors** – כמעט אין (0 ב-6/8).
- **User-specific / batch position** – אין קורלציה.
- **Network hanging** – ב-Type A אין hanging, יש **אפס** requests; לא idle בגלל hang אלא בגלל שלא נשלח.
- **Cache/cookies כגורם יחיד** – B הצליח רק 50%, וגם כשנכשל שוב היה idle זהה, כך ש-cache לא מסביר.

## 6. מה עדיין לא ידוע

1. למה לחיצת `page.click("#searchFormButton", force=True)` לא מפעילה את ה-Vue handler ב-6/8 המקרים (Type A) – האם זה race בין `fill` ל-`click`, או שהכפתור disabled, או ש-Vue לא סיים hydration (`readyState interactive`)? אין לוג של `button.disabled` או Vue state.
2. למה ב-Type B הטאבים קיימים אך לא visible (loaders 6) – האם זה `opacity:0` או `pointer-events` או `transform`? לא נמדד `getComputedStyle` לכל tab.
3. האם הפתרון ל-Type A הוא `wait_until: networkidle` או `waitForFunction` על Vue, או פשוט `page.click` עם `delay`?
4. האם Type A ו-Type B הם שני root causes שונים או שני שלבים של אותו race?

## 7. Root Cause Confidence

- **Type A (75% מה-TAB_TIMEOUT, 37.5% מכלל ה-probes):** **בינוני-גבוה** – הכשל הוא ש-`search click` לא שולח userInfo/posts, כנראה race/hydration. Confidence **65%** שזה גורם השורש, אך חסר לוג של כפתור state.
- **Type B (25% מה-TAB_TIMEOUT):** **בינוני** – טאבים נוצרים אך לא visible בגלל loader/skeleton. Confidence **50%**.
- **כללי:** **אין root cause יחיד ברמת ודאות גבוהה (>80%)** – יש שני תת-סוגים, ו-B מצליח רק 50%.

**לכן: לא זוהה root cause ברמת ודאות גבוהה.**

## 8. הבחנה: page vs context vs server

- **Page state:** A נכשל 0/8 – page state לא מתאושש ללא reload → page state תורם.
- **Context/session:** B הצליח 4/8 (50%) – context חדש עוזר בחצי המקרים, אך גם נכשל בחצי עם אותו idle → לא פותר תמיד.
- **Network/server instability:** 6/8 idle עם אפס requests – מצביע על client-side (Vue) ולא על שרת, כי השרת כלל לא נקרא. 2/8 עם requests אך לא visible – גם client-side.
- **תלות ב-request:** Type A תלוי ב-**אי-שליחת** userInfo, לא ב-אי-הגעתו.

**מסקנה:** הכשל הוא **DOM/rendering + Vue handler race**, לא IP/throttling.

---

## 9. המלצה לתיקון production (ללא ביצוע)

**תיקון מינימלי ומדויק (Go אם יאושר):**

1. **לפני `page.click`**, להוסיף:
   ```js
   await page.waitForFunction(() => {
     const btn = document.querySelector('#searchFormButton');
     return btn && !btn.disabled && window.Vue;
   }, timeout=5000)
   ```
   או fallback: `page.fill` + `page.waitForTimeout(500)` + `page.click` עם `delay: 100`.

2. **אחרי click**, להמתין לא ל-`button.tabs` בלבד אלא ל-**userInfo response** כ-signal:
   ```js
   await page.waitForResponse(r => r.url.includes('/userInfo') && r.status===200, timeout=15000)
   ```
   ואז `wait_for_selector(tabs, visible, 30000)`.

3. **אם עדיין timeout**, לוג חדש: `TAB_TIMEOUT_TYPE=A/B` עם `hasUserInfo`, `tabsCount`, `loaders` – כדי להבדיל.

זה מטפל ב-Type A (העיקרי, 75%) ללא שינוי timeout, וללא retry מיותר. Type B (loaders) ייפתר כי tabs יופיעו רק אחרי userInfo.

**סיכון:** נמוך, רק הוספת wait, לא שינוי ארכיטקטורה.

---

## 10. VERDICT

### 1. האם זוהה root cause ברמת ודאות גבוהה?
**לא.** יש שני תת-סוגים (Idle 75% ו-Visible-but-blocked 25%) עם confidence 65%/50%, לא root cause יחיד >80%.

### 2. האם ניתן לבצע תיקון נקודתי שמטפל בגורם שזוהה?
**כן, חלקית** – עבור Type A (37.5% מכלל ה-probes, 75% מה-TAB) ניתן תיקון נקודתי (wait ל-userInfo / Vue ready) שסביר שיפתור את רוב המקרים.

### 3. תיקון מינימלי (כמפורט בסעיף 9) – האם Go?
**Go מותנה** – מומלץ לבצע את התיקון הנ"ל (waitForFunction + waitForResponse) כ-**תיקון נקודתי ל-Type A**, עם לוג Type A/B, ולנטר. זה Go עבור 75% מה-TAB_TIMEOUT, לא עבור 100%.

### 4. מה חסר ל-root cause מלא?
- לוג של `button.disabled`, `Vue` hydration, ו-`getComputedStyle` של הטאבים ב-Type B.
- האם Type A נפתר על ידי `delay` ב-click או `waitForFunction` – דרוש ניסוי אחד ממוקד.

### 5. ניסוי אחד ממוקד שיכריע (לא “עוד חקירה” כללית)

**ניסוי:** Probe עם 10 ניסיונות נוספים, כל ניסיון מבצע:
- לפני click: `waitForFunction` על `!btn.disabled` + `window.Vue` (או `networkidle`)
- אחרי click: `waitForResponse` על `userInfo` (15s) לפני `waitForSelector` על tabs

**הכרעה:** אם Type A יורד מ-6/8 ל-0-1/8, ה-root cause אומת ו-Go מלא. אם נשאר 4+/8, ה-root cause אינו click race וצריך חקירת Vue hydration.

---

**Go/No-Go סופי:** **Go מותנה** – לבצע תיקון נקודתי ל-Type A (waitForFunction + waitForResponse) + לוג A/B, ולבצע את הניסוי הממוקד הנ"ל לפני תיקון מלא ל-Type B. לא להמשיך לחקירות ללא סוף.

