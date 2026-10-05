# חקירת Insacret כמקור להורדת Instagram Stories

**תאריך חקירה:** 28 באוגוסט 2026  
**משתמש לבדיקה:** `israel_bidur`  
**דף בדיקה:** `https://insacret.org/en/stories/israel_bidur`  
**סביבה:** Playwright Chromium 148 headless, `requests`, `sync_playwright`  
**תוצרים גולמיים:** `scripts/debug_output/insacret_probe/`  
**מסמכים משלימים:** `docs/investigations/viewsocials.md`, `docs/FASTDL_STORIES_ARCHITECTURE.md`

> כל קוד הניסוי מבודד תחת `scripts/debug_output/insacret_probe/`, ללא שינוי production, ללא commit. עוגיות וטוקנים נשמרו לאחר redaction.

---

## תקציר מנהלים

1.  **איך Insacret מקבל את `israel_bidur`:** ה-username חלק מ-URL הנתיב (`/en/stories/israel_bidur`). ב-JS (`_next/static/chunks/pages/stories/[username]-c11afc8...js`) הוא נשלף דרך Next.js router (`const {username} = e`) ונשלח ב-POST הבא.
2.  **מאיפה מגיעים ה-Stories:** לא מה-HTML ולא מ-`insacret.org` עצמו, אלא משרת חיצוני `https://igstories.snapfirecdn.com` (Cloudflare). ה-HTML הוא רק skeleton.
3.  **מה ה-endpoint שמחזיר אותם:** `POST https://igstories.snapfirecdn.com/v2/stories` עם `{"username":"israel_bidur","turnstile":"<token>"}` וכן `POST https://igstories.snapfirecdn.com/GetHighlights` עבור Highlights. שניהם התגלו ב-`stories_chunk.js` (24446 bytes).
4.  **האם אפשר לקרוא אליו ללא browser:** לא – כל ניסיון `requests` ללא `turnstile` תקף החזיר `200 {"error":"BotBlocked"}` (5 ניסויים שונים, `test_snapfire.py`).
5.  **האם יש token/signature:** כן – **Turnstile invisible** (`sitekey: 0x4AAAAAADX-N6yaTE5-Bqc-`, `size:"invisible"`) + סקריפט טביעת אצבע `fx.js` (27988 bytes, מעורפל, מחקה `document`, `window`, `eval`, `localStorage`). ה-JS יוצר `div` נסתר, קורא `window.turnstile.render(..., callback: token)`, ממתין עד 10 שניות, ומנסה עד 3 פעמים.
6.  **איך ניתן לקבל את ה-media URLs:** רק לאחר קבלת תשובה תקינה מ-`snapfirecdn`. במצב תקין התשובה אמורה להכיל `stories` עם `media`, `mediaType`, `profile_pic_url` וכו’ (ראה קוד ה-React). בפועל לא הוחזרה אף story בחקירה (0/2 הרצות browser, 0/5 HTTP).
7.  **האם אפשר להוריד את המדיה ישירות:** תיאורטית כן – לפי `socialstory`-like לוגיקה ה-media אמור להיות URL ישיר מ-Instagram CDN או דרך ה-CDN של snapfire, אך לא הוכח כי לא התקבלה תגובה עם מדיה. בדיקת `requests` ל-snapfire חזרה `BotBlocked` לפני שלב המדיה.
8.  **האם המנגנון מתאים ל-GitHub Actions:** לא. נדרש Chromium + פתרון Turnstile תקף, אך ב-headless נצפה ` [Cloudflare Turnstile] Error: 600010` + `ERR_CERT_AUTHORITY_INVALID` + `ERR_NAME_NOT_RESOLVED`, ואף בקשה ל-`snapfirecdn` לא נשלחת (0 ב-`01_insacret_network.json` ו-`turnstile_network2.json`). זה מצביע על זיהוי headless/bot via `fx.js` + Turnstile.
9.  **מה עלול לשבור אותו:** שינוי `sitekey`, עדכון `fx.js` (שינוי לוגיקת טביעת אצבע), הידוק Cloudflare Turnstile ל-“managed challenge”, שינוי דומיין `snapfirecdn.com` או מבנה ה-JSON, הוספת `cf_clearance` נוספת.
10. **האם עדיף על פני FastDL/StoryNavigation:** לא. StoryNavigation עובד עם `requests` בלבד (2 קריאות, 31 stories, 3/3 הצלחה), FastDL עובד עם `POST` פשוט או Playwright bridge. Insacret דורש פתרון captcha בלתי פתיר ב-CI.
11. **Flow מומלץ אם היה מתאים (לצורך תיעוד):** `GET /en/stories/<user>` → המתנה ל-`window.turnstile` → `render` → קבלת `token` → `POST snapfirecdn/v2/stories` עם `token` → `X-Request-ID` ב-header → parse `stories` → download media. בפועל ה-flow נכשל בשלב ה-token.

**Verdict:** **E – לא מתאים** | Reliability 2/10 | Complexity 9/10 | GH Actions 1/10

---

## שלב 1: מיפוי האתר

### טעינה ראשונית `GET https://insacret.org/en/stories/israel_bidur`

*   **200** `text/html`, `server: cloudflare`, `cf-ray: ...`
*   ה-HTML **אינו** מכיל Stories. `01_insacret_dom_analysis.json` מראה `storyCandidates: []`, `imgs: [logo.png]` בלבד, `bodyText` מכיל רק FAQ + footer. `htmlSnippet` מציג skeleton:
    ```html
    <div class="flex md:flex-row justify-center mt-4 md:mt-10 ">
      <span class="bg-gray-500 rounded-full ... aspect-square"></span>
      <div class="h-5 bg-gray-500 rounded w-full"></div>
    </div>
    <div class="animate-pulse h-[585px]">Loading...</div>
    ```
*   אין redirect, אין iframe.
*   Resources שנטענים (50 ל-`insacret.org` מתוך 393 סה"כ):
    *   CSS: `/_next/static/css/092368e19ede7d30.css`, `cf6b498ff61df216.css`
    *   JS: `webpack-87b3a303122f2f0d.js`, `framework-ecc4130bc7a58a64.js`, `main-481c763ed46ee0f5.js`, `pages/_app-3e10ce2a17f1d842.js`, `pages/stories/[username]-c11afc8aba09979b.js` (24446 bytes – מכיל לוגיקת ה-stories), `296-5d742a851acc25de.js`, `polyfills-78c92fac7aa8fdd8.js`, `_buildManifest.js`, `_ssgManifest.js`
    *   נוספים: `logo.png`, `/fx.js` (27988 bytes מעורפל), `/9x43Iaq6G.js` (15773 bytes), `/_next/data/TJDhLbfVUq2l_whFvvOF2/en.json` (תרגומים בלבד)
*   JS bundles רלוונטיים: `stories/[username]` הוא היחיד שמכיל `fetch("https://igstories.snapfirecdn.com/v2/stories")`.
*   Cookies לאחר טעינה (`01_insacret_cookies.json`): `_ga`, `FCCDCF`, `FCNEC`, `__gads`, `__gpi`, `__eoi`, `IDE` (doubleclick), `i`/`yandexuid` (yango), אין `XSRF-TOKEN`/`laravel_session` ספציפיים ל-insacret (האתר הוא Next.js, לא Laravel).
*   `localStorage`: `google_adsense_settings`, `google_ama_config` (רק פרסום). `sessionStorage: {}` – אין token שמור.
*   `js_urls`: 5 דומיינים חיצוניים (googlesyndication, yandex, gtm, fundingchoices, challenges.cloudflare.com).

**מסקנה שלב 1:** הדף הוא SPA של Next.js שמציג skeleton ומצפה לטעינה אסינכרונית. כל הנתונים אמורים להגיע לאחר מכן – אך לא הגיעו.

---

## שלב 2: Network Capture

נעשה עם Playwright (`probe_insacret.py` ו-`probe2.py`, `01_insacret_network.json:950KB`, 393 entries).

| קטגוריה | כמות | דומיינים עיקריים |
|---------|------|------------------|
| `insacret.org` | 50 | `/_next/static/*`, `/en/stories/israel_bidur`, `/fx.js`, `/9x43Iaq6G.js` |
| `pagead2/googlesyndication` | 62+26 | פרסום |
| `challenges.cloudflare.com` | 34 | Turnstile |
| `fundingchoices` | 34 | CMP |
| `google-analytics` | 8 | `load_profile_initiate` |
| `snapfirecdn.com` | **0** | **אף בקשה לא נצפתה** |

**בקשות שנבדקו ואינן קיימות:**
*   אין `fetch`/`XHR` ל-`/api/`, `/ajax/`, `/graphql` תחת `insacret.org`
*   אין `POST` ל-`/stories`, `/profile`, `/media` תחת `insacret.org`
*   אין בקשות לדומיינים חיצוניים מלבד פרסום/Turnstile
*   `analysis_output.txt` מאשר: כל 50 ה-insacret הן `GET` ל-static או ל-`/_next/data/.../en.json` (תרגומים בלבד)

**ה-endpoint האמיתי התגלה רק ב-JS, לא ב-network:** `https://igstories.snapfirecdn.com/v2/stories` (POST) – אך הוא **לא נשלח** בפועל כי Turnstile נכשל.

**תיעוד endpoint (מהקוד, לא מהרשת):**
```
METHOD: POST
URL: https://igstories.snapfirecdn.com/v2/stories
QUERY PARAMETERS: אין
REQUEST HEADERS: Accept: application/json, Content-Type: application/json, Origin: https://insacret.org, Referer: https://insacret.org/en/stories/israel_bidur
REQUEST BODY: {"username":"israel_bidur","turnstile":"<token>"}
STATUS (כשאין token): 200
CONTENT-TYPE: application/json
RESPONSE STRUCTURE (שגיאה): {"error":"BotBlocked"}  או  {"error":"InvalidUsername"} / {"error":"fail"}
RELEVANT COOKIES: אין (Cloudflare רק)
TOKENS: turnstile (invisible, sitekey 0x4AAAAAADX-N6yaTE5-Bqc-)
```

נוסף: `POST https://igstories.snapfirecdn.com/GetHighlights` עם `{"highlightsId": e}` – עבור Highlights (גם דורש turnstile עקיף).

---

## שלב 3: בדיקת ה-HTML

חיפוש ב-`01_insacret_final.html` (142KB) ו-`turnstile_final2.html` (286KB) וב-DOM לאחר 30 שניות:

*   `israel_bidur`: מופיע רק ב-`og:title`, `og:description` וב-`gtag("load_profile_initiate", username)`, **לא** כנתון story.
*   `stories`/`story`: 0 אלמנטים עם `class*="story"` (dom_analysis: `storyCandidates: []`), רק skeleton.
*   `media`/`video`/`image`: אין `video` tags, רק `img` לוגו.
*   `cdn`/`instagram`/`graphql`/`api`/`ajax`: אין ב-HTML, רק ב-JS chunk.
*   URL מדיה: **לא נמצא** בשום מקום – לא ב-HTML, לא ב-attributes, לא ב-JSON מוטמע (`__NEXT_DATA__` מכיל רק תרגומים), לא ב-API (כי לא הוחזר).

**מסקנה:** Scraping פשוט עם `requests` + `BeautifulSoup` **אינו אפשרי** – הדף ריק ללא JS, וה-JS עצמו לא מחזיר נתונים ללא Turnstile.

---

## שלב 4: איתור API

ה-API אותר ב-`stories_chunk.js:4527`:

```js
// Highlights
await fetch("https://igstories.snapfirecdn.com/GetHighlights",{method:"POST",headers:{Accept:"application/json","Content-Type":"application/json"},body:JSON.stringify({highlightsId:e})})

// Stories – עם Turnstile
let a = await new Promise((e,t)=>{
  let s=document.createElement("div");
  s.style.position="absolute"; s.style.left="-9999px";
  document.body.appendChild(s);
  let l=()=>{ window.turnstile.render(s,{sitekey:"0x4AAAAAADX-N6yaTE5-Bqc-",size:"invisible",callback:t=>e(t),"error-callback":()=>t(Error("Turnstile error"))}) };
  // polling 100ms עד 10s ל-window.turnstile
});
let i = await fetch("https://igstories.snapfirecdn.com/v2/stories",{method:"POST",headers:{Accept:"application/json","Content-Type":"application/json"},body:JSON.stringify({username:s,turnstile:a})});
let e = await i.json();
if(e.error==="fail" && retry<3) continue;
```

**ניסויי Replay (5 ניסויים, `test_snapfire.py`):**

| ניסוי | Headers | Body | תוצאה |
|-------|---------|------|--------|
| 1 | `Accept, Content-Type, Origin, Referer` | `{"username":"israel_bidur"}` | **200 `{"error":"BotBlocked"}`** |
| 2 | כנ"ל | `{"username":"israel_bidur","turnstile":"dummy"}` | **200 `BotBlocked`** |
| 3 | כנ"ל | `{"username":"israel_bidur","turnstile":""}` | **200 `BotBlocked`** |
| 4 | כנ"ל | `{"username":"israel_bidur","turnstile":null}` | **200 `BotBlocked`** |
| 5 | עם `Session` cookies מ-`GET insacret` | כנ"ל | **200 `BotBlocked`** |

**מסקנה:** קיים API, אך הוא **אינו עצמאי** – דורש `turnstile` תקף. ללא browser שמפיק token, ה-flow נכשל. רמת השחזור ללא browser: 0%.

---

## שלב 5: Tokens / Signatures / Session

*   **Turnstile token:**
    *   Inputs: `sitekey` קבוע (`0x4AAAAAADX-N6yaTE5-Bqc-`), מיקום ה-DOM (div נסתר), `userAgent`, `fingerprint` מ-`fx.js`
    *   Algorithm: Cloudflare Turnstile (proof-of-work + behavioral). לא חשוף ב-JS – ה-token נוצר ב-iframe של `challenges.cloudflare.com` ומוחזר ב-callback.
    *   Output: string אקראי (~500 chars), תקף לדקות ספורות, תלוי ב-session וב-IP.
    *   תלות ב-browser: **כן** – `window.turnstile` חייב להיות טעון, ה-DOM חייב להיות נראה, ה-`fx.js` מטביע אצבע (מעקב אחרי `document`, `window.eval`, `localStorage`, `XMLHttpRequest` – ר' `fx.js` המעורפל).
    *   שגיאה שנצפתה: `[Cloudflare Turnstile] Error: 600010` ב-`turnstile_console2.json` – מצביעה על זיהוי headless / `ERR_CERT_AUTHORITY_INVALID` (ה-iframe של Turnstile נכשל ב-Playwright headless).
*   **Session:** אין `XSRF-TOKEN` ייעודי, רק `_ga`, `FCNEC` וכו’. ה-`X-Request-ID` מוחזר ב-header של התשובה (`i.headers.get("X-Request-ID")`) רק כשיש תשובה תקינה – לא נצפה.
*   **ניתן לשחזר ב-Python?** לא – ה-token דורש הרצת JS ב-browser אמיתי עם פתרון Turnstile, ואין secret חשוף.

אלמנטים שנבדקו ב-JS: `fetch(`, `axios` (לא קיים, רק `fetch`), `/api/` (רק snapfire), `stories`, `turnstile`, `sitekey`, `fx.js` (fingerprint).

---

## שלב 6: מקור ה-media

לא התקבל אף story, ולכן לא ניתן לקבוע בוודאות, אך לפי הקוד:

```js
// ב-React – הצגת story
"max-w-7xl" ... {x.profile_pic_url} ... {x.username} ... {x.media_count} ... {v(x.follower_count)}
...
"video"==i.mediaType ? <video src={i.media} poster={p}> : <img src={p}>
```

המדיה אמורה להגיע בשדה `i.media` (וידאו) או `p` (תמונה) מתוך תשובת `snapfirecdn`. לפי דפוס אתרים דומים (StoryNavigation), ה-media יהיה URL חתום מ-Instagram CDN (`scontent-*.cdninstagram.com`).

**הערכה (לא מאומתת עקב חסימה):**
*   סוג D – endpoint של snapfire שמחזיר JSON עם media URLs (לא ישיר מהדפדפן ל-Instagram)
*   סוג A/C – ה-URLs עצמם הם `scontent` חתומים עם `expiring_at` (כמו ב-StoryNavigation)
*   נדרש session/cookies? כנראה **לא** למדיה עצמה, אך כן ל-API שמספק את ה-URLs.

הורדת מדיה ישירה **לא נבדקה** כי לא היו URLs.

---

## שלב 7: בדיקה ללא Browser

Probe מבודד (`test_snapfire.py`):

```
israel_bidur → POST snapfirecdn/v2/stories (ללא turnstile) → {"error":"BotBlocked"} → אין parse → אין download
```

מדדים:
*   HTTP status: 200 (אך שגיאת אפליקציה)
*   response time: ~300ms
*   response size: 23 bytes
*   מספר Stories: 0
*   מספר media URLs: 0
*   הצלחת download: 0
*   סוג מדיה: לא ידוע

**מסקנה:** ללא browser עם Turnstile תקף, ה-flow נכשל לחלוטין.

---

## שלב 8: אם אין API ברור – Playwright

מדדים מ-2 הרצות (5 שניות + 30 שניות):

*   זמן עד הופעת Stories: **לא הופיעו כלל** (30 שניות המתנה, `storyCandidates: []`)
*   Loading state: `animate-pulse` skeleton (אפור, `bg-gray-500`) נשאר קבוע.
*   Polling: קוד ה-JS מנסה polling ל-`window.turnstile` כל 100ms עד 10 שניות, ואז 3 ניסיונות `fetch` – אך אף `fetch` ל-`snapfirecdn` לא נשלח (0 ב-network), כי ה-`render` נכשל.
*   Request לאחר שניות: אין – ה-console מראה `Turnstile Error: 600010` מיד.
*   Scroll/lazy: לא רלוונטי – אין נתונים לטעון.
*   DOM: `bodyText` מכיל רק FAQ, אין `img[data-src]`, אין `video`.
*   Media כ-URL ישיר: לא קיים.

תנאי המתנה שהיה אמור לעבוד (אם ה-API היה עובד):
```python
page.wait_for_response(lambda r: "snapfirecdn.com/v2/stories" in r.url, timeout=30000)
# או
page.wait_for_selector(".profile-stories-item", timeout=30000)
```
בפועל שניהם נכשלים (timeout).

---

## שלב 9: בדיקת יציבות

| ניסיון | page_load | stories_detected | API_detected | media_urls | download_success | response_time | errors |
|--------|-----------|------------------|--------------|------------|------------------|---------------|--------|
| 1 (probe_insacret.py, 8s) | 200 | 0 | 0 | 0 | 0 | ~5s | Turnstile 600010 |
| 2 (probe2.py, 30s) | 200 | 0 | 0 | 0 | 0 | ~30s | Turnstile 600010, ERR_CERT_AUTHORITY_INVALID |
| 3 (test_snapfire POST) | 200 (BotBlocked) | 0 | 1 (אך שגיאה) | 0 | 0 | 0.3s | BotBlocked |
| 4 (repeat POST dummy) | 200 | 0 | 1 | 0 | 0 | 0.3s | BotBlocked |
| 5 (repeat POST empty) | 200 | 0 | 1 | 0 | 0 | 0.3s | BotBlocked |

*   endpoint משתנה? לא – תמיד `snapfirecdn.com/v2/stories`
*   token משתנה? כן – אמור להשתנות בכל `render`, אך לא נוצר כלל
*   cookies נדרשים? לא – גם עם cookies נחסם
*   media URLs משתנים? לא ידוע (אין)
*   URL פג? לא רלוונטי
*   תלוי ב-session? לא, תלוי ב-Turnstile
*   עובד ללא browser? **לא – 0%**

**יציבות:** 0/5 הצלחות – לא repeatable.

---

## שלב 10: התאמה ל-GitHub Actions

*   נדרש Chromium? **כן** – חובה להריץ JS ו-Turnstile
*   נדרש session persistent? לא, אך נדרש token טרי בכל ריצה
*   IP של GH Actions נחסם? לא נבדק ישירות, אך `BotBlocked` גם מ-local IP – מצביע על חסימת headless ללא קשר ל-IP
*   Cloudflare/WAF? **כן** – Turnstile + `fx.js` fingerprinting + Cloudflare edge (server: cloudflare)
*   Rate limits? לא נצפה (5 קריאות רצופות החזירו אותו `BotBlocked`)
*   עובד משרת ולא רק מדפדפן? **לא** – רק מדפדפן עם Turnstile תקף
*   תלות ב-cookie מ-browser? לא, אך תלות ב-Turnstile token
*   token קשה לייצר מחוץ ל-browser? **כן – בלתי אפשרי ב-Python** (דרוש פתרון Turnstile חיצוני)
*   media URL נגיש מ-GH Actions? לא נבדק (אין URL)

**סיכום GH Actions:** **לא מתאים** – ה-flow נכשל כבר בשלב ה-token ב-headless, ודורש solver חיצוני יקר ולא אמין.

---

## שלב 11: השוואה ל-FastDL ול-StoryNavigation (Viewsocials)

| מאפיין | **Insacret** | **StoryNavigation** (Viewsocials האמיתי) | **FastDL** |
|--------|--------------|-------------------------------------------|------------|
| API ישיר | לא – `POST snapfirecdn/v2/stories` דורש Turnstile | **כן** – `POST /get-user-last-stories` עם `XSRF-TOKEN` | **כן** – `POST api-wh.fastdl.app/api/v1/instagram/stories` |
| Browser נדרש | **כן, חובה** (Turnstile) | **לא** (2 קריאות `requests`) | לא חובה (יש מסלול ישיר + bridge) |
| Authentication | Turnstile invisible + `fx.js` fingerprint | `XSRF-TOKEN` + `laravel_session` | לרוב ללא, לעיתים `ts/_s/_tsc` |
| Token/signature | Turnstile token (sitekey 0x4..., תלוי ב-IP/UA, תוקף קצר) | `X-XSRF-TOKEN: decodeURIComponent(cookie)` (דטרמיניסטי) | חתימת `ts/_s` (לא דטרמיניסטית, דורשת bridge) |
| Cookies | `_ga`, `FCNEC` – לא קריטיים | `XSRF-TOKEN`, `laravel_session` – חובה | אין חובה |
| Cloudflare/WAF | **Turnstile 600010 + fx.js – חוסם headless** | Cloudflare רגיל – עובר | Cloudflare רגיל – עובר |
| Stories response | `{"error":"BotBlocked"}` / `{"error":"fail"}` (0 stories) | `{"lastStories":[{id, type, url(Base64), thumbnailUrl, videoUrl, taken_at, expiring_at}]}` 31 videos | `{"result":[{image_versions2, video_versions, url_downloadable}]}` 35 items |
| Media URL | לא הוחזר (אמור להיות `scontent` via snapfire) | Base64 → `scontent-*.cdninstagram.com` + proxies `cdn.storynavigation`, `stories-cdn.fun` (200) | `media.fastdl.app/get?__sig&__expires` (200) |
| Media download | לא נבדק (חסום) | **כן** – direct `scontent` 200, cdn 200 | **כן** – proxy 200 |
| יציבות | **0/5** – Turnstile נכשל תמיד | **3/3** – קונסיסטנטי | בינונית (polling 30s לעיתים) |
| תלות ב-UI | גבוהה – skeleton בלבד ללא JS | נמוכה – ה-id מגיע ב-HTML | בינונית – לחיצה על Stories tab |
| GitHub Actions | **1/10 – לא מתאים** | **9/10 – מצוין** | **7/10 – טוב** |
| מורכבות | **9/10 – גבוהה** (Turnstile solver) | 3/10 – נמוכה | 5/10 – בינונית |
| יתרונות | דומיין נפרד (snapfirecdn), אם היה עובד – API נקי | API ישיר ללא captcha, מהיר | API ישיר, מוכר בפרויקט |
| חסרונות | Turnstile חוסם CI, fx.js כבד, אין fallback | תלוי ב-Laravel CSRF (אם ישתנה) | חתימות דורשות bridge |

---

## שלב 12: מסקנה

### Verdict: **E – לא מתאים**

Insacret אינו ניתן לשימוש כ-backend אמין לפרויקט, לא כ-API ישיר ולא כ-Browser automation ב-GitHub Actions.

**דירוג:**
```
Reliability: 2/10 (0% הצלחה בחקירה)
Implementation complexity: 9/10 (Turnstile + fx.js)
GitHub Actions suitability: 1/10 (נכשל ב-headless, 600010)
Dependency on UI: 10/10 (skeleton בלבד)
Risk of breaking: 9/10 (שינוי sitekey/fx.js יחסום שוב)
```

**השוואה סופית:**
*   **StoryNavigation** הוא הבחירה המומלצת כ-backend נוסף (A – API ישיר, יציב, ללא captcha).
*   **FastDL** נשאר ברירת מחדל יציבה.
*   **Insacret** – **לא מומלץ** – התלות ב-Turnstile invisible + `fx.js` הופכת אותו לבלתי עביר ב-CI.

---

## נספחים – קבצי debug

*   `scripts/debug_output/insacret_probe/probe_insacret.py` – probe ראשוני (393 entries)
*   `01_insacret_network.json` (950KB) – כלל התעבורה, 0 קריאות ל-snapfirecdn
*   `01_insacret_dom_analysis.json` – `storyCandidates: []`, skeleton בלבד
*   `stories_chunk.js` (24446 bytes) – מכיל את ה-`fetch` ל-`snapfirecdn.com/v2/stories`
*   `fx.js` (27988 bytes) / `9x43Iaq6G.js` (15773 bytes) – fingerprinting מעורפל
*   `test_snapfire.py` – 5 ניסויי Replay, כולם `BotBlocked`
*   `probe2.py` / `turnstile_network2.json` (502KB) – 30 שניות המתנה, `turnstile=True` אך 0 snapfire, console עם `Error: 600010`
*   `analysis_output.txt` – ניתוח ממוקד של כלל ה-insacret URLs

> כל עוגיות וטוקנים הוחלפו ב-`[REDACTED]` בדו"ח וב-JSON.

---

*סוף דו"ח – אין לבצע אינטגרציה לפני אישור. StoryNavigation הוא ה-backend המומלץ אם נדרש גיבוי ל-FastDL.*
