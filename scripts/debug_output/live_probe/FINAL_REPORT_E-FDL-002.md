# דוח חקירה סופי — FastDL Stories API bridge (E-FDL-002)

תאריך: אוגוסט 2026. run_id מדווח: `32456347593` (שלושה משתמשים רצופים: `@kolbarama`, `@mizrahitpage`, `@glglz`). סטטוס: חקירה הושלמה, root cause חלקי-מאומת, תיקון: **לא בוצע – design בלבד, ממתין לאישור**.

> כלל ברזל בחקירה זו: לא שונה קוד production. נוצרו רק probes זמניים תחת `scripts/debug_output/live_probe/` לקבלת evidence אמיתי.

---

## 1. Executive Summary

התקלה החדשה אינה `{"result":[]} → None` (תוקנה ב-E-FDL-001). היא תקלה שונה לגמרי:

- **מה שקורה:** `STORIES_API_REQUEST_SEEN=true` אבל `STORIES_API_RESPONSE_SEEN=false` בתוך `page.expect_response(timeout=20000)` → `TimeoutError 20000ms` → `E-FDL-001`.
- **שלושה משתמשים ברצף** נפלו באותו pattern, כולל אחד ללא Stories (`kolbarama`) ושניים עם Stories (`mizrahitpage`, `glglz`) – ולכן זו **לא** בעיית "אין Stories".
- **Evidence מקומי:** FastDL אינו יציב. נמדדו 3 מצבים: response מהיר (~280–400ms), response איטי מאוד (~15–35 שניות), ו-response שלא מגיע בכלל תוך 40 שניות + `tabs TIMEOUT 30s`. אותו username בריצות חוזרות התנהג אחרת (flaky).
- **ההסבר הסביר ביותר (מאומת חלקית):** שרת FastDL / רשת GitHub Actions חווים **transient slowness / throttling אחרי batch**. ה-timeout הקשיח של 20 שניות ל-Stories response אינו מספיק ברגעי עומס, וגם שלב `wait_for_tabs 30s` ו-`page.goto 10s` נכשלים לעתים ב-30–40s. חוסר העקביות `Timeout 20000ms` מול `timeout_seconds=10` הוא logging mismatch בלבד (ראו סעיף 11) – אבל הוא מסתיר את ה-timeout האמיתי.
- **המלצה:** לא רק "להגדיל timeout". נדרש תיקון מינימלי שמטפל גם ב-late response, ב-retry מבוקר, ובלוגים שמבדילים בין שלושת סוגי ה-timeout. פירוט בסעיפים 18–20.

---

## 2. מה ידוע בוודאות

1. שלושת המשתמשים ב-`run_id=32456347593` נכשלו באותו גרף:
   `LISTENER_ATTACHED=true, SEARCH_CLICK_STARTED=true, SEARCH_CLICK_COMPLETED=true, STORIES_API_REQUEST_SEEN=true, STORIES_API_RESPONSE_SEEN=false, STORIES_API_REQUEST_METHOD=POST, STORIES_API_REQUEST_URL=https://api-wh.fastdl.app/api/v1/instagram/stories` → `TimeoutError 20000ms` → `timeout_seconds=10` → `E-FDL-001`.
2. `@kolbarama` הוכח כ-`{"result":[]}` – אין Stories – אך נפל באותו timeout (ולא כ-`NO_ACTIVE_STORIES`). זה מוכיח שהבעיה אינה parsing.
3. הקוד הנוכחי ב-`src/fastdl_api.py` **כבר תוקן** ל-E-FDL-001: `result = resp_json.get("result"); if result is None: result = resp_json.get("data")` (`src/fastdl_api.py:364-366`) ומחזיר `[]` כהצלחה (`src/fastdl_api.py:70-76`). אומת ב-production.
4. ב-local probes עם אותו flow מדויק: request->response בד"כ ~280–590ms (ראו טיימליין סעיף 9), אבל בריצות אחרות אותו request לקח 15–35 שניות או לא חזר כלל תוך 40 שניות – **ללא שינוי קוד**.
5. גם שלב ה-tabs נכשל לעתים ב-`Timeout 30000ms` (למשל `glglz`, `mizrahitpage` בחלק מהריצות) – כלומר חוסר היציבות אינו מוגבל ל-Stories API.
6. ה-`VIEWER_URL` ב-production הוא `https://fastdl.app/en2/instagram-anonymously-viewer` (`src/fastdl_api.py:27`) אך בפועל השרת מבצע `301 → https://fastdl.app/en3yO/...` (observed בכל ה-local probes). זה אינו גורם לכשל אך חשוב ל-logging.
7. ה-`response.json()` ב-responses המוצלחים מחזיר תמיד `{"result": [...]}` עם `content-type: application/json; charset=utf-8` ו-status 200, גם ל-empty וגם ל-full.
8. לא נמצא `requestfailed` עבור Stories API בריצות המוצלחות – הכשל הוא hang, לא reset.

---

## 3. מה לא ידוע

1. האם שלושת הכשלים ב-`32456347593` נגרמו מאותו hang של 35–40s (מעל 20s) או מ-reset שקט של החיבור שלא נלכד ב-listener.
2. האם FastDL ביצע rate-limit מפורש (status 429 / header) – לא נצפה 429 ב-local, רק hang. ב-GitHub Actions ייתכן שיש שוני ב-IP / headers.
3. האם אחרי ה-timeout ה-response הגיע בדיעבד (late) – לא ניתן לדעת כי `browser.close()` ב-`finally` (`src/fastdl_api.py:353`) סוגר מיד ולא מקשיב עוד.
4. האם משתמשים לפני `@kolbarama` הצליחו – אין בידינו לוג מלא של ה-run ההוא (רק שלושת הנכשלים דווחו).
5. האם הגדלת timeout ל-35–40s תספיק תמיד – אין percentile מבוסס על מאות samples.

---

## 4. timeline של production failure

מבוסס על הלוגים שדווחו:

```
06:56:41 API_BRIDGE_STAGE response_waiter create start
06:56:41 API_BRIDGE_STAGE click_stories_tab start
06:56:41 API_BRIDGE_STAGE click_stories_tab done
        → request POST https://api-wh.fastdl.app/api/v1/instagram/stories נשלח (on_request -> request_seen=true)
        → expect_response(timeout=20000) מתחיל להמתין
06:57:01 NETWORK_DIAGNOSTIC: LISTENER_ATTACHED=true SEARCH_CLICK_STARTED=true
          SEARCH_CLICK_COMPLETED=true STORIES_API_REQUEST_SEEN=true
          STORIES_API_RESPONSE_SEEN=false PAGE_URL_AFTER_SEARCH=None
          STORIES_API_REQUEST_METHOD=POST STORIES_API_REQUEST_URL=...
          exception_type=TimeoutError exception_message=Timeout 20000ms exceeded while waiting for event "response"
          timeout_seconds=10 E-FDL-001
```

חסר: `PAGE_URL_AFTER_SEARCH=None` – מעיד ש-`page_url_after_search` נקבע רק אחרי ה-`with` (`src/fastdl_api.py:230`) ולא עודכן לפני ה-exception, ולכן ה-diagnostic ב-`except PlaywrightTimeout` מדפיס את הערך הישן `None`.

שלושת המשתמשים נפלו ברצף בהפרש שניות בודדות (06:56:41 + ~שניות) – pattern של batch failure.

---

## 5. flow מדויק בקוד

`src/fastdl_api.py:_fetch_stories_with_playwright()` (`src/fastdl_api.py:80-353`):

1. `page = context.new_page(); page.set_default_timeout(timeout*1000)` – timeout ברירת מחדל 10s (`src/fastdl_api.py:116`)
2. `page.on("request", on_request)` + `page.on("response", on_response)` נרשמים **לפני** `page.goto` (`src/fastdl_api.py:143-145`), `listener_attached=True`
3. `page.goto(VIEWER_URL, wait_until="domcontentloaded", timeout=timeout*1000)` – 10s (`src/fastdl_api.py:148`)
4. `page.wait_for_selector("#search-form-input", state="visible", timeout=timeout*1000)` – 10s (`src/fastdl_api.py:151`)
5. `page.fill("#search-form-input", username)` (`src/fastdl_api.py:161`)
6. `page.click("#searchFormButton", force=True, timeout=timeout*1000)` → `search_click_started/completed` (`src/fastdl_api.py:163-180`)
7. `time.sleep(2.5)` hard-coded (`src/fastdl_api.py:184`)
8. `page.wait_for_selector("button.tabs-component__button", state="visible", timeout=30000)` hard-coded (`src/fastdl_api.py:200`)
9. `with page.expect_response(lambda response: STORIES_API_PATH in response.url and response.request.method=="POST", timeout=20000) as response_info:` (`src/fastdl_api.py:205-208`) – **hard-coded 20s, אינו תלוי ב-`timeout`**
10. בתוך ה-`with`: `page.evaluate(... click Stories tab ...)` (`src/fastdl_api.py:211-228`)
11. יציאה מה-`with` → אם לא הגיע response תוך 20s → `PlaywrightTimeout`
12. `response = response_info.value` (`src/fastdl_api.py:243`) – ב-timeout ייזרק שוב Timeout וייתפס ב-`except PlaywrightTimeout` (`src/fastdl_api.py:311`)
13. `if response.status != 200` → `E-FDL-002` (`src/fastdl_api.py:259`) – לא קשור לתקלה הנוכחית
14. `body = response.json(); items = parse_stories(body)` (`src/fastdl_api.py:281-282`)
15. `finally: browser.close()` (`src/fastdl_api.py:353`) – סגירה מיידית, ללא האזנה ל-late response

`src/main.py` ממפה כל `None` / `api_error` / `timeout` ל-`E-FDL-001` (`src/main.py:358-379`).

---

## 6. כל hypotheses שנבדקו

| # | היפותזה | הובאה מהבקשה | סטטוס |
|---|---|---|---|
| 1 | FastDL לא מחזיר response בזמן | כן | **נתמך חלקית** – hang של 40s נצפה |
| 2 | Response מגיע מאוחר אחרי timeout | כן | **נתמך** – 15–35s נמדדו, מעל 20s threshold |
| 3 | Listener מפספס response | כן | **נפסל כ-primary** – on_response תפס כש-response כן הגיע; predicate זהה ל-on_request |
| 4 | כמה requests והקוד מאזין ללא נכון | כן | **נפסל** – ב-all probes רק POST אחד ל-`/stories` נצפה; predicate נכון |
| 5 | Race בין waiter ל-click | כן | **נפסל כ-primary** – waiter נוצר לפני click כנדרש; request הגיע אחרי click |
| 6 | Timing סביב Stories tab | כן | **נתמך חלקית** – tabs נכשלו ב-30s בחלק מהריצות (glglz, mizrahitpage) |
| 7 | Polling פנימי של FastDL | כן | **נצפה אך לא כ-root** – ב-`live_probe_report.json` היו 3 responses בהפרש ~29–32s, אך זו התנהגות תקינה |
| 8 | Rate-limit / throttling אחרי batch | כן | **נתמך חזק** – רצף של 3+ users + hang פתאומי ב-local אחרי batch |
| 9 | Browser/network ב-GitHub Actions | כן | **סביר** – local vs GH שונים, אך hang שוחזר גם ב-local |
| 10 | Response ב-browser network אך לא נתפס | כן | **נפסל** – כש-response הגיע, הוא נתפס גם ב-on_response וגם ב-expect_response |
| 11 | Timeout configuration שגוי | כן | **אומת** – mismatch 20s vs 10s; 20s קצר מדי ברגעי עומס |
| 12 | VIEWER_URL redirect / consent overlay חוסם | לא-רשמית | **נבדק ונפסל** – redirect `en2→en3yO` תקין, overlay מוסר פעמיים |

---

## 7. evidence עבור כל hypothesis

**H1/H2/H8 (slowness/throttling):**
- `probe_e_fdl_002.py` ריצה 1: `kolbarama` 278ms, `israel_bidur` 403ms (מהיר) – **אבל** `probe_polling_ratelimit` באותו יום: `kolbarama` 35033ms (43s→03s = ~35s), `polling_kolbarama` resp `T+39406ms` vs req `T+4373ms`.
- `probe_timing_detailed.py` לאחר מכן: כל 3 הראשונים `NO RESP after 40s` – כלומר מעבר מ-~0.4s ל-40s hang תוך שעה. זה evidence ל-transient server slowness / throttling.
- `probe_single.py` לאחר 30s המתנה: שוב `tabs TIMEOUT 30s` – instability.

**H6 (tabs):**
- `probe_e_fdl_002.py` ריצה 2: `glglz` ו-`mizrahitpage` נפלו ב-`wait_for_stories_tab TIMEOUT 30s` – כלומר אפילו לפני Stories API. `probe_polling_ratelimit` Rep 3/3: `kolbarama` שוב `tabs TIMEOUT`.

**H11 (timeout mismatch):**
- קוד: `timeout=10` (`src/fastdl_api.py:80`), `page.set_default_timeout(timeout*1000)` (`src/fastdl_api.py:116`), `expect_response(timeout=20000)` (`src/fastdl_api.py:207`), `except PlaywrightTimeout: timeout_seconds={timeout}` (`src/fastdl_api.py:323`). לכן הלוג מדפיס `Timeout 20000ms exceeded` ו-`timeout_seconds=10` – שני ערכים שונים שכל אחד נכון בהקשרו, אבל מבלבלים. `log_failure("waiting_for_response", exc, timeout_seconds=timeout)` (`src/fastdl_api.py:325`) מאבד את ה-20s האמיתי.

**H3/H4/H5 (listener/race):**
- ב-`probe_e_fdl_002_results.json` המוצלח: `on_request STORIES T+4248ms` → `on_response STORIES T+4526ms` → `expect_response done 409ms` – אותו predicate, אותו request, נתפס בהצלחה. לכן listener אינו שבור.

**H7 (polling):**
- `scripts/debug_output/live_probe/live_probe_report.json`: `kolbarama` 3 responses: `T+06.567, 35.056, 07.019` בהפרשים ~28.5s ו-31.9s. זה polling שתועד בעבר, אך אינו מסביר את ה-timeout הנוכחי (הראשון היה 0.3s).

**H10 (response ב-network אך לא נתפס):**
- ב-probes כש-response הגיע, `STORIES_API_REQUEST_SEEN` ו-`STORIES_API_RESPONSE_SEEN` היו שניהם `true` ו-`request_to_response_ms` חושב נכון – לכן אין אובדן.

---

## 8. תוצאות probes

| Probe | קובץ | מה נבדק | תוצאה |
|---|---|---|---|
| probe_e_fdl_002 v1 | `probe_e_fdl_002.py` | 5 users ברצף ב-flow production מדויק + timeline ms | 4/5 SUCCESS, `glglz` TAB_NOT_FOUND; click->resp ~278–402ms |
| probe_e_fdl_002 v2 (fixed import) | `probe_e_fdl_002.py` | תיקון `src` import | `kolbarama` 278ms, `israel_bidur` 403ms, `mizrahitpage/glglz` TAB_NOT_FOUND 30s |
| probe_polling_ratelimit | `probe_e_fdl_002_polling_and_ratelimit.py` | keep_open 35s + polling + rate-limit batch | `kolbarama` req 4373ms → resp 39406ms (35s delay), `batch` כולם 19–35s delay, `israel_bidur` tabs TIMEOUT |
| probe_timing_detailed | `probe_timing_detailed.py` | req->resp עם body capture + 40s wait | `kolbarama/israel_bidur/mizrahitpage` **NO RESP after 40s**, `glglz` tabs TIMEOUT |
| probe_single | `probe_single.py` | single user אחרי 30s השהיה | `kolbarama` tabs TIMEOUT (שלישי ברצף) |
| live_probe_report.json (קודם) | `live_probe_report.json` | 3 users בהרצה קודמת (לפני חקירה זו) | `kolbarama` empty 1s, `israel_bidur` 28 items 1.6s, polling של 30s |

מסקנה: FastDL latency **אינו דטרמיניסטי** – נע בין 0.3s ל-40s+. Batch של מספר users מעלה סיכון ל-hang.

---

## 9. Network timeline (מ-`probe_e_fdl_002_results.json` ריצה מוצלחת)

```
T+   419ms page.goto start
T+  1510ms page.goto done → redirect en2 → en3yO (301 → 200)
T+  1570ms search_input visible
T+  1619ms fill + click search
T+  4197ms sleep 2.5s done
T+  4223ms wait_for_stories_tab start → done 8ms
T+  4231ms response_waiter create start
T+  4233ms click_stories_tab start
T+  4248ms on_request POST /stories  (request_seen=true)
T+  4249ms click_stories_tab done
T+  4527ms on_response 200 application/json; charset=utf-8 (response_seen=true)
T+  4640ms expect_response done (elapsed 409ms)
→ request_to_response = 278.5ms, click_to_response = 278.3ms
```

ב-runs האיטיים:

```
T+  4373ms REQ POST /stories
T+ 39406ms RESP 200 (35033ms later)  ← מעל 20s threshold
→ expect_response היה נכשל ב-20s
```

---

## 10. request/response behavior

- Endpoint: `POST https://api-wh.fastdl.app/api/v1/instagram/stories` (`src/fastdl_api.py:26-28`).
- Request headers: `User-Agent` + `Accept: application/json`, body JSON `{"username":..., "ts":..., "_ts":..., "_tsc":0, "_sv":2, "_s":"<redacted>"}` (חתימה דינמית מהדפדפן).
- Response הצלחה: `200`, `content-type: application/json; charset=utf-8`, body `{"result": [...]}` או `{"result":[]}`. גודל מלא ~1.1–1.5MB ל-27–35 items.
- לא נצפה 429 / 403 / 5xx ב-probes המוצלחים. ב-direct `requests.post` כן 403 (ללא חתימה) – לכן ה-browser bridge הכרחי.
- כל הריצות המוצלחות: request יחיד, response יחיד, predikate `STORIES_API_PATH in url and method==POST` תפס נכון.
- hang: request נשלח, אין `requestfailed`, אין response תוך 40s – שרת שותק.

---

## 11. timeout analysis

| Timeout | היכן מוגדר | ערך | האם זה הtimeout שגרם ל-log |
|---|---|---|---|
| `timeout` param | `FastDLStoriesAPI.fetch_stories(username, timeout=10)` (`src/fastdl_api.py:42`) | 10s | לא – זה ה-`timeout_seconds=10` בלוג |
| `page.set_default_timeout` | `src/fastdl_api.py:116` | `timeout*1000 = 10000ms` | חל על goto / wait_for_selector / click (לא על expect_response) |
| `page.goto` | `src/fastdl_api.py:148` | `timeout*1000 = 10s` | לא קשור לתקלה זו |
| `wait_for_selector #search-form-input` | `src/fastdl_api.py:151` | `10s` | לא קשור |
| `page.click #searchFormButton` | `src/fastdl_api.py:166` | `10s` | לא קשור |
| `wait_for_selector tabs` | `src/fastdl_api.py:200` | `30000ms` hard-coded | קשור לחלק מהכשלים (glglz) אך לא ל-log הנוכחי |
| `page.expect_response` | `src/fastdl_api.py:207` | `20000ms` hard-coded | **זה ה-Timeout 20000ms בלוג** |

**ה-mismatch:** `except PlaywrightTimeout: log_failure(..., timeout_seconds=timeout)` (`src/fastdl_api.py:323-325`) מדפיס את ה-10s, בעוד ה-exception מכיל `Timeout 20000ms`. זה metadata mismatch, לא mismatch פונקציונלי, אבל הוא מסתיר את האמת בלוגים. תיקון logging צריך להדפיס את שני הערכים.

**האם 20s קצר מדי?** Evidence: רוב ה-responses 0.3–2.7s, אבל נמדדו גם 15s, 19s, 35s, ו-40s hang. 20s קצר מדי ברגעי עומס. percentile מ-~15 samples: p50 ~0.4s, p90 ~15s, p95 >30s (מדגם קטן). הגדלה ל-35–40s תפתור ~90% אך לא את ה-hang המוחלט.

---

## 12. Playwright listener analysis

- `on_request` / `on_response` נרשמים לפני `goto` – נכון.
- `listener_attached` נקבע ל-True מיד אחרי הרישום (`src/fastdl_api.py:145`) וגם בתוך ה-handlers – ולכן `LISTENER_ATTACHED=true` תמיד (אלא אם exception לפני הרישום).
- `request_seen` / `response_seen` הם dicts שמתעדכנים רק כש-`STORIES_API_PATH in url and method==POST` (`src/fastdl_api.py:126-141`) – predicate תקין.
- `expect_response` משתמש באותו predicate (`src/fastdl_api.py:206`) – עקבי.
- אין race: `expect_response` נוצר **לפני** ה-click, וה-click בתוך ה-`with` – pattern מומלץ של Playwright.
- מה שחסר: אין `page.on("requestfailed")` ב-production – ולכן hang שקט (ללא response וללא failed) לא נותן sign. ב-probe עם `requestfailed` לא נצפה failed גם ב-hang – כלומר החיבור פשוט שותק.

---

## 13. rate-limit analysis

- Production: 3 users רצופים נכשלו עם הפרש שניות (`kolbarama` 06:56:41, הבאים מיד אחריו) – דפוס batch.
- Local: הרצה של 5 users ברצף הצליחה רק 3/5, ואחרי מספר probes ברצף ה-latency קפץ מ-0.4s ל-35s ואז ל-hang. `probe_polling_ratelimit` Rep 3/3: `kolbarama` שוב tabs TIMEOUT אחרי 2 ריצות מוצלחות.
- אין 429 – throttling מתבטא כ-**slow response / hang**, לא כ-error מפורש.
- לא בוצע עומס חריג – probes היו מתונים (2–3s gap כמו production `MIN_DELAY 2s MAX_DELAY 3s` ב-`src/main.py:22-23`).
- מסקנה: FastDL כנראה מגביל לפי IP / session / rate אחרי batch של ~3–5 requests. Evidence נסיבתי אך עקבי.

---

## 14. polling / delayed-response analysis

- ב-`live_probe_report.json` הקודם: עבור `kolbarama` היו 3 requests/responses בהפרשים ~28–32s (1.058s ראשון, ואז 28.5s, 31.9s). זה polling אוטומטי של הדף (כנראה retry / keep-alive).
- ב-probes הנוכחיים: כל ריצה מוצלחת הראתה **request יחיד + response יחיד** – לא polling, כי ה-probe סגר מיד אחרי response. ב-`probe_polling_ratelimit` עם keep_open 35s: רק request אחד נצפה – כלומר ה-polling אינו תמידי, תלוי ב-state הדף.
- חשוב: ה-response הראשון (המהיר) הוא התוצאה הסופית – אין evidence ל-`empty → full` delayed. `kolbarama` תמיד `{"result":[]}` גם ב-response הראשון וגם במאוחרים.
- לכן polling אינו root cause ל-timeout הנוכחי, אך הוא רלוונטי אם נרצה להמתין ל-response מאוחר – צריך להחליט אם להקשיב רק לראשון או לכל.

---

## 15. השוואה בין users עם/בלי Stories

| סוג | דוגמה | תוצאה production | תוצאה local probe (כשהצליח) | items | latency |
|---|---|---|---|---|---|
| ללא Stories | `kolbarama` | timeout (false failure) | SUCCESS, `{"result":[]}` → `[]` → `NO_ACTIVE_STORIES` | 0 | 278ms (מהיר) / 35s (איטי) |
| עם Stories | `israel_bidur` | SUCCESS (בעבר) | SUCCESS, 27 items | 27 | 403ms / hang |
| עם Stories (מדווח כנכשל) | `mizrahitpage` | timeout | flaky: פעם TAB_NOT_FOUND, פעם 1160ms SUCCESS | 28 ב-probe ישן | משתנה |
| עם Stories (מדווח כנכשל) | `glglz` | timeout | TAB_NOT_FOUND ברוב הריצות | – | – |
| עם Stories | `erevtov` | לא ב-batch הנכשל | SUCCESS, 23 items | 23 | 385ms |

**לקח:** כשל אינו תלוי בתוכן – גם empty וגם full נכשלים באותו timeout. זה מחזק שהבעיה היא תשתיתית (network/server), לא לוגית (parsing).

---

## 16. root cause אם ניתן לאמת

**Root cause מאומת חלקית (evidence חזק אך לא 100% הוכחה ל-production):**

> **FastDL Stories API hang / throttling אחרי batch** – השרת מפסיק לענות (או עונה אחרי 35–40s) על `POST /api/v1/instagram/stories`, בעוד ה-client ממתין רק 20s. ה-`request` נשלח ולכן `REQUEST_SEEN=true`, אך ה-`response` לא מגיע בזמן ולכן `RESPONSE_SEEN=false` → `PlaywrightTimeout 20000ms`.

**למה זה מסביר את ה-production log במדויק:**
- `SEARCH_CLICK_*=true` – ה-profile נטען, ה-tabs הופיעו.
- `REQUEST_SEEN=true` – ה-POST ל-stories נשלח (נצפה ב-on_request).
- `RESPONSE_SEEN=false` – לא הגיע response תוך 20s (גם ב-local נצפה hang של 35–40s).
- `exception_message=Timeout 20000ms` – זה ה-`expect_response` timeout.
- `timeout_seconds=10` – זה ה-logging bug (מדפיס את ה-param ולא את ה-20s).

**מה לא הוכח ב-100%:** שאכן ב-`run_id=32456347593` ה-delay היה 35s ולא reset. אבל ה-local reproduction של אותו delay מחזק מאוד.

**Root causes משניים שתורמים:**
- `wait_for_stories_tab 30s` נכשל לעתים (glglz) – אותו throttling משפיע גם על שלב ה-profile.
- `browser.close()` מיידי מאבד late response.

---

## 17. אם לא ניתן לאמת root cause, מה חסר

- לוג שרת FastDL (לא זמין) – האם ה-request הגיע לשרת והתעכב, או נחסם ב-firewall.
- לוג `requestfailed` ב-production (אינו קיים) – היה מבדיל בין hang ל-reset.
- Timestamp מדויק של כל שלושת הכשלים ב-GH Actions (יש רק 06:56:41 לראשון) – היה מאשר batch timing.
- מדידה של late response אחרי timeout (צריך probe שממשיך להאזין 60s אחרי timeout, ללא `browser.close()`).
- percentile אמיתי מ-50+ samples ב-GH Actions – כדי לקבוע timeout חדש מבוסס data.

---

## 18. תיקון מומלץ (מינימלי, מבוסס evidence)

**עקרון:** לא רק להגדיל timeout, אלא לטפל ב-hang, ב-logging, וב-retry מבוקר.

**שינויים ב-`src/fastdl_api.py` בלבד (אל לגעת ב-parser שכבר תוקן, לא לגעת ב-rclone/workflow):**

1. **תיקון logging mismatch** – ב-`except PlaywrightTimeout` להדפיס גם `expect_timeout_ms=20000` וגם `configured_timeout_s=timeout` (`src/fastdl_api.py:311-325`). הוספת `PAGE_URL_AFTER_SEARCH` נכון (כבר יש `page.url` לפני exception).

2. **הגדלת `expect_response` ל-35s** (לא 20s) – מבוסס על p90 ~15s ו-worst 35s. 35s עדיין מתחת ל-`sync.yml timeout-minutes:25` ולסביר ל-GH Actions. אל לעלות ל-60s (יחסום batch).

3. **הוספת `requestfailed` listener** – כמו ב-probes, ל-log `failure` ו-`PAGE_URL` אם יש reset.

4. **Retry אחד מבוקר ל-Stories API בלבד** – אם `expect_response` timeout ו-`request_seen=true` אבל `response_seen=false`, לנסות שוב פעם אחת: לרענן overlay, ללחוץ שוב על Stories tab, ולהמתין שוב 35s. לא יותר מ-retry אחד כדי לא להחמיר throttling. זה יפתור את רוב ה-hangs החד-פעמיים.

5. **שמירת `browser` פתוח 5s נוספים אחרי timeout** לפני `browser.close()` – לאפשר capture של late response ל-log (observability), אך לא לחסום.

**דוגמה ל-diff המומלץ (design only, לא לבצע עכשיו):**
```python
# before: timeout=20000 hard-coded
# after: STORIES_API_TIMEOUT = 35000  # was 20000, evidence: p90 15s, worst 35s
with page.expect_response(..., timeout=STORIES_API_TIMEOUT) as response_info:
    click_stories_tab()
# on PlaywrightTimeout: log expect_timeout_ms=STORIES_API_TIMEOUT, configured_timeout_s=timeout, requestfailed, page_url
# if request_seen and not response_seen: retry once with same timeout
```

6. **אלטרנטיבה אם retry לא רצוי:** לפחות להגדיל ל-35s ולתקן logging – זה יפתור את רוב המקרים ש-delay 15–35s.

---

## 19. חלופות לתיקון

| חלופה | יתרונות | חסרונות |
|---|---|---|
| **A. רק להגדיל ל-35s** (מינימלי) | שינוי שורה אחת, סיכון נמוך | לא פותר hang של 40s+, לא פותר tabs TIMEOUT |
| **B. הגדלה + retry אחד** (מומלץ) | פותר hang חד-פעמי, evidence תומך | עלול להחמיר throttling אם retry אגרסיבי |
| **C. לעבור ל-`page.on("response")` + polling 45s** במקום `expect_response` | תופס גם late response, מטפל ב-polling | שינוי ארכיטקטורה גדול, סיכון regressions |
| **D. להמתין 5s לפני `expect_response` + לבדוק tabs שוב** | מטפל ב-race של tabs | לא פותר hang של API |
| **E. להחזיר DOM fallback אוטומטי** כש-API timeout | נותן recovery path | `docs/FASTDL_STORIES_ARCHITECTURE.md` אומר שה-DOM archived, ו-API מחזיר יותר items מה-DOM (35 vs 6) – עלול להחזיר תוצאה חלקית |
| **F. להוסיף delay גדול יותר בין users (5–10s)** במקום 2–3s | מפחית throttling | מאריך run, לא פותר hang בודד |

---

## 20. סיכונים של כל פתרון

- **הגדלה ל-35s:** מאריכה כל user ב-15s במקרה הגרוע; ב-20 users זה +5 דקות (עדיין מתחת ל-25 דקות `sync.yml`).
- **Retry:** עלול להכפיל load על FastDL בדיוק כשיש throttling; צריך backoff (למשל 3s sleep לפני retry).
- **Polling 45s:** עלול לתפוס response שני (duplicate) – צריך deduplication.
- **DOM fallback:** עלול להוריד פחות stories (incomplete) ולהסתיר בעיית API.
- **Delay בין users:** לא מבטיח פתרון, רק מפחית הסתברות.

---

## 21. בדיקות regression מומלצות

1. `python -m pytest -q` – כל הבדיקות הקיימות, במיוחד `tests/test_fastdl_api.py:test_parse_empty_result_returns_empty_list` ו-`test_empty_result_is_no_stories_success` (לוודא ש-`[]` עדיין SUCCESS).
2. `python -c "from src.fastdl_api import FastDLStoriesAPI; assert FastDLStoriesAPI.parse_stories({'result':[]})==[]"` – regression ל-E-FDL-001.
3. `python -c "from src.fastdl_api import FastDLStoriesAPI; assert FastDLStoriesAPI.parse_stories({'result':[{'url_downloadable':'https://...mp4'}]})[0]['kind']=='video'"`
4. `python scripts/debug_output/live_probe/probe_e_fdl_002.py` (הגרסה המתוקנת) – 3 ריצות, לוודא שרובן SUCCESS ו-`request_to_response < 35000`.
5. ריצה מקומית `python -m src.main` על `kolbarama` (empty) → צפוי `NO_ACTIVE_STORIES`, לא `E-FDL-001`.
6. ריצה על `israel_bidur` (full) → צפוי `STORIES_FOUND` עם 20+ items.
7. `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/sync.yml').read_text(encoding='utf-8'))"` – ולידציית workflow.

---

## 22. observability נוספת שכדאי להוסיף

- ב-`NETWORK_DIAGNOSTIC` להוסיף: `EXPECT_TIMEOUT_MS`, `CONFIGURED_TIMEOUT_S`, `REQUESTFAILED`, `REQUEST_T_MS`, `RESPONSE_T_MS`, `CLICK_TO_RESPONSE_MS`, `PAGE_URL_BEFORE/AFTER` נכונים, `RESPONSE_STATUS`, `CONTENT_TYPE`.
- ל-log גם `requestfailed` events (כמו ב-probe).
- ל-log `PAGE_URL` גם ב-`except PlaywrightTimeout` (כיום `PAGE_URL_AFTER_SEARCH=None` בגלל שהמשתנה נקבע רק אחרי `with`).
- להוסיף `API_BRIDGE_STAGE retry start/done` אם מיישמים retry.
- לשמור `debug_output/fastdl_api_bridge` artifacts ב-GH Actions גם ב-failure (כבר יש `debug/`).

---

## 23. מה לא כדאי לשנות

- **לא לגעת ב-parser** (`src/fastdl_api.py:355-407`) – הוא כבר תוקן ומאומת ל-E-FDL-001. שינוי יכניס regression.
- **לא להחזיר DOM fallback אוטומטי** (`src/story_downloader.py:_fetch_story_urls` ה-archived) – אלא אם הוחלט ב-explicit design review (ה-DOM incomplete).
- **לא לשנות `STORAGE_BACKEND` / `rclone` / `state.json` / `sync.yml`** – אין קשר לתקלה.
- **לא לשנות `VIEWER_URL` מ-`en2` ל-`en3yO`** – ה-redirect תקין.
- **לא לבצע "פשוט להגדיל timeout ל-60s"** ללא evidence ו-retry logic – מסתיר בעיה ומאריך run.

---

## 24. מסקנה

- התקלה `E-FDL-002` (REQUEST_SEEN true, RESPONSE_SEEN false, Timeout 20000ms) **אינה** parsing – היא hang של FastDL Stories API.
- Evidence מ-5 probes מראה ש-FastDL latency נע בין 0.28s ל-40s+, עם batch throttling. ה-timeout הקשיח 20s כושל ברגעי עומס.
- ה-mismatch `Timeout 20000ms` vs `timeout_seconds=10` הוא logging bug שמקשה על דיאגנוזה.
- התיקון המינימלי המומלץ: **35s timeout + תיקון logging + requestfailed + retry אחד מבוקר** – יפתור את רוב ה-failures הנוכחיים תוך שמירה על יציבות.
- **אין לבצע תיקון לפני אישור.** הדוח מוכן ל-review.

---

## Artifacts שנוצרו בחקירה (לא production)

- `scripts/debug_output/live_probe/probe_e_fdl_002.py` – probe מדויק ל-production flow + timeline
- `scripts/debug_output/live_probe/probe_e_fdl_002_polling_and_ratelimit.py` – polling + rate-limit
- `scripts/debug_output/live_probe/probe_timing_detailed.py` – req->resp עם body
- `scripts/debug_output/live_probe/probe_single.py` – single user
- `scripts/debug_output/live_probe/probe_e_fdl_002_results.json` – raw results
- `scripts/debug_output/live_probe/probe_polling_ratelimit.json` – raw polling
- `scripts/debug_output/live_probe/live_probe_report.json` – הרצת עבר (3 users)
- `scripts/debug_output/live_probe/kolbarama_v2.json` – capture של tabs failure
- `scripts/debug_output/live_probe/FINAL_REPORT_E-FDL-001.md` – דוח קודם (reference)
- `scripts/debug_output/live_probe/FINAL_REPORT_E-FDL-002.md` – **דוח זה**

> הערה פרטיות: כל ה-probes מ-redact חתימות `_s`, `__sig`, ו-cookies; אין tokens מלאים ב-logs.

