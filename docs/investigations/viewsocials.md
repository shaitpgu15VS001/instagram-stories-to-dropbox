# חקירת Viewsocials ו-StoryNavigation כמקור להורדת Instagram Stories

**תאריך חקירה:** 28 באוגוסט 2026  
**משתמש לבדיקה:** `israel_bidur` (ID: `508790485`)  
**סביבה:** Playwright Chromium headless 148, Python `requests`, `sync_playwright`  
**מיקום תוצרים גולמיים:** `scripts/debug_output/viewsocials_probe/`  
**קבצי תיעוד משלימים:** `docs/FASTDL_GUIDE.md`, `docs/FASTDL_STORIES_ARCHITECTURE.md`

> **עקרון:** החקירה בוצעה ללא שינוי production, ללא commit, עם קוד ניסוי מבודד בלבד תחת `scripts/debug_output/viewsocials_probe/`. כל ה-cookies/Tokens נשמרו לאחר redaction.

---

## תקציר מנהלים (10 התשובות המבוקשות)

1.  **מה Viewsocials עושה בפועל** – האתר `www.viewsocials.com` מציג ממשק “Anonymous Instagram Viewer” גנרי. בעת בקשת `GET /profile/israel_bidur` מתקבל מיידית עמוד Cloudflare Challenge (`403 Just a moment...`, `cf_chl_rt_tk=...`, Ray ID `a322...`). האתגר דורש פתרון JS/Turnstile בדפדפן אמיתי. לעומתו, הדומיין `storynavigation.com` (שקושר מה-flow שתואר `storynavigation.com/watch-stories`) הוא זה שמגיש בפועל את ה-Stories, ללא חסימת WAF – וזהו ה-backend האמיתי שנחשף.
2.  **מה ה-endpoint שמביא את ה-Stories** – `POST https://storynavigation.com/get-user-last-stories` עם `Content-Type: application/json`. הגדרות axios ב-`app.js` : `xsrfCookieName: "XSRF-TOKEN"`, `xsrfHeaderName: "X-XSRF-TOKEN"`.
3.  **איך ה-username עובר במערכת** – `watch-stories` → הזנת `israel_bidur` ב-`input.search-inp` → `button.search-btn` מפעיל `window.location="/user/"+t` (ללא קריאה ל-Viewsocials, מנוקה מ-`https://instagram.com/`). בעמוד `/user/israel_bidur` השרת מרנדר `<profile-page v-bind:user-info-prop="{&quot;id&quot;:508790485,...">` + `<meta name="csrf-token">`. לאחר מכן ה-JS קורא `axios.post("/get-user-last-stories", {userName, isPrivate:"", instagramUserId})`.
4.  **מאיפה מגיע ה-media URL** – התגובה מכילה `lastStories: [{id, type:"video"|"image", url, thumbnailUrl, videoUrl, taken_at, expiring_at, ...}]` כאשר `url/thumbnailUrl/videoUrl` הם **Base64** של URL ישיר מ-Instagram CDN (`scontent-*.cdninstagram.com` עם פרמטרי `_nc_cat`, `_nc_sid`, `_nc_ohc`, `ig_cache_key`, `ccb`, `oh`, `oe`). בצד לקוח ה-media נטען דרך שני proxies אופציונליים: `https://cdn.storynavigation.com/?<base64>` ל-thumbnails ו-`https://stories-cdn.fun/<base64>` לוידאו (ראה `socialstory.js`).
5.  **האם אפשר ללא browser** – **כן עבור StoryNavigation, לא עבור Viewsocials.** StoryNavigation עובד עם `requests.Session` טהור (2 קריאות HTTP, ללא Playwright) לאחר שליפת ה-cookie. Viewsocials נחסם 403/307 ב-HTTP ישיר.
6.  **מה בדיוק מחייב browser (אם יש)** – עבור Viewsocials: פתרון Cloudflare Managed Challenge + טעינת Turnstile (`challenges.cloudflare.com`). עבור StoryNavigation: רק שליפת עוגיות ו-CSRF – אינה מחייבת browser, ניתנת לשחזור דטרמיניסטי ב-Python.
7.  **האם יש token/signature ואיך הוא נוצר** – Laravel CSRF/XSRF. השרת מגדיר `Set-Cookie: XSRF-TOKEN=<encrypted JWT-like>` ו-`laravel_session` + מטא `csrf-token`. ה-JS של axios קורא את העוגיה (`document.cookie.match`) ושולח `X-XSRF-TOKEN: decodeURIComponent(XSRF-TOKEN)`. כל רענון מייצר token חדש (ראינו 3 ערכים שונים ב-3 ריצות, כל אחד באורך ~328), אך ה-flow דטרמיניסטי – מספיק לקרוא את העוגיה הנוכחית. ה-Instagram CDN URLs עצמם חתומים עם `oh`+`oe`+`_nc_*` ותוקפם ~3-4 שעות (`expiring_at - taken_at ≈ 86400`, בדוגמה `1787823742 → 1787910142`).
8.  **האם ניתן להריץ באמינות ב-GitHub Actions** – StoryNavigation: כן, ללא תלות ב-UI, 3/3 ניסויים הצליחו עם תגובה זהה (31 stories מסוג video). נדרשת רק ספריית `requests`. Viewsocials: לא אמין – דורש פתרון Cloudflare, תלוי ב-browser, ייכשל ב-headless CI ללא solver חיצוני.
9.  **מה החסרונות והסיכונים** – תלות ב-Laravel CSRF (אם האתר ישנה ל-`SameSite=Strict` או יוסיף Turnstile גם ל-StoryNavigation, ה-flow יישבר). ה-Instagram URLs אפליים – חייב להוריד מיידית, לא לשמור ב-state. תלות ב-`instagramUserId` שמגיע מ-HTML (אם שינוי מבנה ה-Vue prop, נדרש עדכון parser). סיכון שינוי שם endpoint (`/get-user-last-stories`) או גרסת `socialstory.js?v63`. Viewsocials מוסיף סיכון WAF גבוה ולא צפוי. גם ה-proxies `cdn.storynavigation.com` ו-`stories-cdn.fun` עלולים להשתנות.
10. **המלצה ברורה** – **A – API ישיר (אבל לא של Viewsocials, אלא של StoryNavigation).** מומלץ **לא להשתמש ב-Viewsocials** (קטגוריה E – לא מתאים). אם רוצים backend נוסף ל-FastDL, יש להשתמש ב-StoryNavigation כ-API ישיר עם session+CSRF (ללא browser). מימוש מוצע: `StoryNavigationAPI` ב-Python שמבצע `GET /user/{username}` → parse `id` → `POST /get-user-last-stories` עם `X-XSRF-TOKEN`. כ-Fallback בלבד ניתן לשקול Playwright שממתין ל-`response.url.includes("/get-user-last-stories")` במקום `sleep`.

---

## שלב 1: מיפוי ה-flow

### 1.1 `https://storynavigation.com/watch-stories`

*   **GET 200** `text/html; charset=UTF-8`, `cf-ray: a322...`, `server: cloudflare`.
*   DOM: `<input type="text" placeholder="Instagram user name or link" class="search-inp">` + `<button class="search-btn"><span>Search</span></button>`.
*   JS: `src/js/app.js?id=e11233d6e7dff598dd94` מכיל `searchUser()` – מנקה קידומות `https://www.instagram.com/` ומבצע `window.location="/user/"+t` לפי `locale` (`/ru/user/`, `/de/user/` וכו’). **אין הפנייה ל-Viewsocials**, **אין בקשת XHR בשלב זה**.
*   לאחר לחיצה על Search ב-Playwright: נצפית ניווט יחיד `GET https://storynavigation.com/user/israel_bidur → 200`. ה-URL הסופי אינו `viewsocials.com/profile/...` כפי שתואר במטלה – אלא פנימי. הרשת מראה 0 בקשות ל-`viewsocials`.
*   Cookies שנוצרו אחרי טעינת `/watch-stories`: `XSRF-TOKEN`, `laravel_session`, `_ga`, `_ym_*`, `__gads`, `__eoi` וכו’ (נשמרו ב-`01_storynavigation_initial_cookies.json` עם redaction ל-`__cf_bm`).
*   `localStorage`/`sessionStorage`: ריקים (`{}`) – אין טוקן שמור שם.
*   Headers מיוחדים: אין `Authorization`; רק `User-Agent`, `Accept-Language`, `Sec-CH-UA`.

### 1.2 `https://www.viewsocials.com/profile/israel_bidur`

*   **GET 307 → 403** עם `location: https://www.viewsocials.com/profile/israel_bidur?__cf_chl_rt_tk=...` ולבסוף `403 Just a moment...` (template של Cloudflare Bot Protection). **אין גישה לתוכן הפרופיל ללא פתרון האתגר**.
*   לעומת זאת `GET https://www.viewsocials.com/` → **200** עם HTML מלא + `Set-Cookie: XSRF-TOKEN`, `laravel_session` – דף הבית אינו מוגן, רק מסלול `/profile/*` מוגן.
*   ניסיון ישיר עם `requests` ללא browser נכשל באותו 403, גם עם `Referer`/`Origin`.

### 1.3 `https://storynavigation.com/user/israel_bidur` (ישירות)

*   **GET 200** `text/html; charset=UTF-8` (ללא אתגר). מכיל:
    ```html
    <meta name="csrf-token" content="arr8yTsFAFZM2zzx6nixRatzaSjspPqCCAmEVxLL">
    <profile-page v-bind:user-info-prop="{&quot;id&quot;:508790485,&quot;username&quot;:&quot;israel_bidur&quot;, ...}">
    <div id="last-stories" class="last-stories"> ... 31 x .profile-stories-item ...
    <script src="/js/app.js?id=..."></script>
    <script src="https://storynavigation.com/js/socialstory.js?v63"></script>
    ```
*   עוגיות חשובות: `XSRF-TOKEN=eyJpdiI6...In0%3D` (URL-encoded), `laravel_session=eyJp...In0%3D`.
*   אין `query parameters` או חתימה ב-URL – כל האימות בעוגיות/הדר.

---

## שלב 2: Network Inspection

### נקודות זמן שנוטרו

1. טעינת `watch-stories`
2. הזנת `israel_bidur` + לחיצה על Search
3. מעבר ל-`/user/israel_bidur`
4. טעינת פרופיל + הופעת Stories
5. ניסיון לחיצה על Story

### בקשות רלוונטיות (מתוך `01_storynavigation_initial_network.json`, 794 entries, 86 ל-`storynavigation.com`)

| METHOD | URL | REQUEST HEADERS | REQUEST BODY | STATUS | CONTENT-TYPE | הערות |
|--------|-----|-----------------|--------------|--------|--------------|-------|
| GET | `https://storynavigation.com/watch-stories` | `User-Agent`, `Accept-Language` | – | 200 | `text/html` | דף חיפוש |
| GET | `https://storynavigation.com/user/israel_bidur` | `Referer: /watch-stories` | – | 200 | `text/html` | פרופיל, מכיל `id` |
| **POST** | **`https://storynavigation.com/get-user-last-stories`** | `Content-Type: application/json;charset=UTF-8` <br> `Accept: application/json` <br> `Referer: /user/israel_bidur` <br> `X-XSRF-TOKEN: <decoded XSRF-TOKEN>` <br> `Sec-CH-UA: ...` | `{"userName":"israel_bidur","isPrivate":"","instagramUserId":508790485}` | **200** | `application/json` | **ה-endpoint האמיתי** |
| GET | `https://cdn.storynavigation.com/?<base64>` | `Referer: https://storynavigation.com/` | – | 200 | `image/jpeg` | proxy ל-thumbnail |
| POST | `https://www.google-analytics.com/g/collect` | – | – | 204 | – | רעש |
| GET | `https://mc.yandex.ru/watch/98468737?wmode=7&page-url=.../user/israel_bidur` | – | – | 200 | `application/json` | metrika |
| – | `viewsocials.com` | – | – | – | – | **0 בקשות** ב-flow של storynavigation |

**תגובת ה-POST (`body_snippet`):**
```json
{
  "lastStories": [
    {
      "id": "3972876009174735752_508790485",
      "thumbnailUrl": "aHR0cHM6Ly9zY29udGVudC1zamM2LTEuY2RuaW5zdGFncmFtLmNvbS92L3Q1MS43MTg3OC0xNS83ODc2ODI0NDhfMTc1Mjk0NDA2MjQwODA0MV83MDI3NDc2MTY5MDMxMTI2NDMzX24uanBnP3N0cD1kc3QtanBnX2UxNV90dDYmX25jX2NhdD0xMDgmY2I9MzBhNjg4ZjctMWE1YTM2MjQmaWdfY2FjaGVfa2V5PU16azNNamczTmpBd09URTNORGN6TlRjMU1nJTNEJTNELjMtY2NiNy01LWNiMzBhNjg4ZjctMWE1YTM2MjQmY2NiPTctNSZfbmNfc2lkPTU4Y2RhZCZlZmc9ZXlKMlpXNWpiMlJsWDNSaFp5STZJbE5VVDFKWkxuaHdhV1J6TGpZME1DNXpaSEl1ZG1sa1pXOWZaR1ZtWVhWc2RGOWpiM1psY2w5bWNtRnRaUzVETXlKOSZfbmNfb2hjPVEtT2hmTWxlZ2p3UTdrTnZ3SGgzLWw0Jl9uY19vYz1BZHBOcHd6Y3RTNEU2SW1wVHZwVXhWSHdYZTE0anRGaVB0NThiZXdtTnhOZEFUZ21rc3JnZ3J1MG5zLTBINzEtN3hZJl9uY19hZD16LW0mX25jX2NpZD0wJl9uY196dD0yMyZfbmNfaHQ9c2NvbnRlbnQtc2pjNi0xLmNkbmluc3RhZ3JhbS5jb20mX25jX2dpZD1hTnZ6RFRuZkF6ZGdhSU9XQXdYdlRBJl9uY19zcz03YTIyZSZvaD0wMF9BUUV1NEdEQXFNYkVvUjZ2V3ktOUhjZ0tuQWZTNHY1SkhSVkstTmg3cll1czN3Jm9lPTZBOTczNTIz",
      "type": "video",
      "url": "aHR0cHM6Ly9zY29udGVudC1zamM2LTEuY2RuaW5zdGFncmFtLmNvbS9vMS92L3QyL2YyL203OC9BUU41NFlBVVVnZGRGQzlLWmw2VkZiWEVTT216cTdHOEpaR29lRE5MSWY4NlpoMkFQTTd1aURfVS1HMmlmLTQtZTdvS1RrLTIxdVk0MEZXc3p3QVZ4YWZKQXhfS0VXTkRvZUROV3ZvLm1wND9fbmNfY2F0PTEwNyZfbmNfc2lkPTVlOTg1MSZfbmNfaHQ9c2NvbnRlbnQtc2pjNi0xLmNkbmluc3RhZ3JhbS5jb20mX25jX29oYz1wcC1zMWRqMXkzOFE3a052d0hDYW5DYiZlZmc9ZXlKMlpXNWpiMlJsWDNSaFp5STZJbmh3ZGw5d2NtOW5jbVZ6YzJsMlpTNUpUbE5VUVVkU1FVMHVVMVJQVWxrdVF6TXVOekl3TG1SaGMyaGZZbUZ6Wld4cGJtVmZNVjkyTVNJc0luaHdkbDloYzNObGRGOXBaQ0k2TVRnMk1qZzBNVFF5TURRd05UUTBPRFlzSW1GemMyVjBYMkZuWlY5a1lYbHpJam93TENKMmFWOTFjMlZqWVhObFgybGtJam94TURneU5pd2laSFZ5WVhScGIyNWZjeUk2TVRrc0luVnliR2RsYmw5emIzVnlZMlVpT2lKM2QzY2lmUSUzRCUzRCZjY2I9MTctMSZ2cz1hMzI1YzI0MWIxOTg4YmImX25jX3ZzPUhCa3NGUUlZVVdsblgzaHdkbDl3YkdGalpXMWxiblJmY0dWeWJXRnVaVzUwWDNZeUwwVXpORVkyUTBNMVF6bEJRakl6TWpneE16RkZRVFZGTWtVME1EazFPRUpEWDNacFpHVnZYMlJoYzJocGJtbDBMbTF3TkJVQUFzZ0JFZ0FWQWhoUmFXZGZlSEIyWDNCc1lXTmxiV1Z1ZEY5d1pYSnRZVzVsYm5SZmRqSXZOVGswUXpVMFFqbEdNVFU0T0RJd1EwTkZSVVl6UlVORE1UQkRSalUyUWtaZllYVmthVzlmWkdGemFHbHVhWFF1YlhBMEZRSUN5QUVTQUNnQUdBQWJBb2dIZFhObFgyOXBiQUV4RW5CeWIyZHlaWE56YVhabFgzSmxZMmx3WlFFeEZRQUFKcXl2NUxXMW5KZENGUUlvQWtNekxCZEFNMlptWm1abVpoZ1NaR0Z6YUY5aVlYTmxiR2x1WlY4eFgzWXhFUUIxNkFkbGxLa0JBQSZfbmNfZ2lkPWFOdnpEVG5mQXpkZ2FJT1dBd1h2VEEmX25jX3NzPTdhMjJlJl9uY196dD0yOCZvaD0wMF9BUUUtbzVROUJhVHFLZ245bk9LTkx5dG50bTYyTFFiRlRWRlRTWkpqV3lNTTN3Jm9lPTZBOTMyRUMw",
      "createdTime": "09:42:22",
      "taken_at": 1787823742,
      "expiring_at": 1787910142,
      "owner_id": "508790485",
      "videoUrl": "aHR0cHM6Ly9zY29udGVudC1zamM2LTEuY2RuaW5zdGFncmFtLmNvbS9vMS92L3QyL2YyL203OC9BUU41NFlBVVVnZGRGQzlLWmw2VkZiWEVTT216cTdHOEpaR29lRE5MSWY4NlpoMkFQTTd1aURfVS1HMmlmLTQtZTdvS1RrLTIxdVk0MEZXc3p3QVZ4YWZKQXhfS0VXTkRvZUROV3ZvLm1wND9fbmNfY2F0PTEwNyZfbmNfc2lkPTVlOTg1MSZfbmNfaHQ9c2NvbnRlbnQtc2pjNi0xLmNkbmluc3RhZ3JhbS5jb20mX25jX29oYz1wcC1zMWRqMXkzOFE3a052d0hDYW5DYiZlZmc9ZXlKMlpXNWpiMlJsWDNSaFp5STZJbmh3ZGw5d2NtOW5jbVZ6YzJsMlpTNUpUbE5VUVVkU1FVMHVVMVJQVWxrdVF6TXVOekl3TG1SaGMyaGZZbUZ6Wld4cGJtVmZNVjkyTVNJc0luaHdkbDloYzNObGRGOXBaQ0k2TVRnMk1qZzBNVFF5TURRd..."
    }
  ]
}
```
*כל 31 ה-Stories מסוג `video` בדוגמה זו; בדיקות אחרות הראו גם `image` בהתאם לתוכן.*

**מסקנה חשובה:** ה-browser מקבל **URL ישיר למדיה (Instagram CDN)** כ-Base64, והשרת של StoryNavigation **אינו** מביא את המדיה בעצמו אלא מחזיר מטא-דאטה בלבד. הפרוקסי `cdn.storynavigation.com` הוא אופציונלי בצד לקוח.

---

## שלב 3: מציאת ה-API האמיתי

נמצא endpoint יחיד רלוונטי ל-Stories:

```
POST /get-user-last-stories
Host: storynavigation.com
```

ניסויי Replay מבודדים (עם `requests`):

| ניסוי | Headers | Cookies | תוצאה |
|-------|---------|---------|-------|
| request זהה ל-browser (עם `X-XSRF-TOKEN` מפוענח) | ✅ `X-XSRF-TOKEN: <decoded>` + `Referer` + `Origin` | `XSRF-TOKEN` + `laravel_session` via Session | **200 – 31 stories** (3/3 ריצות) |
| ללא `X-XSRF-TOKEN` | ❌ | עם cookies | **419 Page Expired** |
| רק `X-XSRF-TOKEN` ללא cookies | ✅ | ❌ | **419** (ה-session אינו תקף) |
| ללא `Referer`/`Origin` אך עם `X-XSRF-TOKEN` | ✅ | ✅ | **200** (לא נדרש) |
| `User-Agent` גנרי בלבד | ✅ | ✅ | **200** |
| Viewsocials `POST /get-user-last-stories` | – | – | **404 Not Found** |
| Viewsocials `GET /profile/israel_bidur` | – | – | **403 Cloudflare** |

**קיומו של API עצמאי:** כן – עבור StoryNavigation. ניתן להפעיל ישירות:
```http
POST https://storynavigation.com/get-user-last-stories
Content-Type: application/json
X-XSRF-TOKEN: <decodeURIComponent(document.cookie XSRF-TOKEN)>
Cookie: XSRF-TOKEN=...; laravel_session=...

{"userName":"israel_bidur","isPrivate":"","instagramUserId":508790485}
```
ViewSocials **אין** API עצמאי נגיש – כל ניסיון החזיר 403/404.

---

## שלב 4: בדיקת tokens / signatures

### StoryNavigation

*   **סוג:** Laravel CSRF/XSRF, לא חתימת זמן/נונס מותאמת. ב-`app.js` (`axios`):
    ```js
    xsrfCookieName: "XSRF-TOKEN",
    xsrfHeaderName: "X-XSRF-TOKEN",
    // קוד: (e.withCredentials||d(p)) && e.xsrfCookieName ? i.read(e.xsrfCookieName) : void 0; g && (h[e.xsrfHeaderName]=g)
    ```
*   **Inputs:** תכולת העוגיה `XSRF-TOKEN` (מבנה `eyJpdiI6...`, מכיל `iv`, `value`, `mac`).
*   **Algorithm:** הצפנה סימטרית בצד שרת (Laravel `encrypt`), הלקוח רק מעתיק את הערך המפוענח. אין secret חשוף ב-JS.
*   **Output:** ערך באורך ~328 תווים, משתנה בכל `GET /user/...` (3 ערכים שונים ב-3 ריצות, כולם תקפים לריצה שלהם).
*   **האם נדרש browser?** לא – מספיק לקרוא את העוגיה מה-`Session` ולשלוח אותה כ-header. ניתן לשחזר ב-Python: `urllib.parse.unquote(cookie.value)`.
*   **CSRF meta:** `<meta name="csrf-token" content="arr8...">` קיים אך **אינו** נשלח ב-POST של ה-Stories (נשלח רק `X-XSRF-TOKEN`). בדיקת `requests` עם `X-CSRF-TOKEN` בלבד נכשלה (419).

### Viewsocials

*   לא נצפה טוקן Stories כי העמוד נחסם לפני טעינת ה-JS. ב-`GET /` קיימים אותם `XSRF-TOKEN`/`laravel_session` + `csrf-token` meta, אך מסלול `/profile/*` דורש פתרון Cloudflare Turnstile ( `script-src 'nonce-...' https://challenges.cloudflare.com`, `csp: connect-src ... challenges.cloudflare.com`). ללא פתרון, ה-JS שמביא stories כלל אינו נטען.

### Instagram CDN URLs

*   פרמטרים דינמיים: `_nc_cat`, `_nc_sid`, `_nc_ht`, `_nc_ohc`, `_nc_oc`, `ig_cache_key`, `ccb`, `cb`, `oh`, `oe`, `_nc_gid`.
*   `oh` ו-`oe` הם חתימה ותפוגה (hex). אין צורך לחשב – מתקבל מוכן מה-API. `expiring_at` הוא Unix time אמיתי (בדוגמה 1787910142 ≈ 2026-08-28 11:22 UTC).

---

## שלב 5: בדיקת מקור המדיה

לכל Story של `israel_bidur`:

| שדה | ערך לדוגמה | פענוח |
|-----|------------|--------|
| Story ID | `3972876009174735752_508790485` | `<media_id>_<owner_id>` |
| media type | `video` (31/31 בריצה זו) | `type` ב-JSON |
| media URL (Base64) | `aHR0cHM6Ly9zY29udGVudC1zamM2LTEuY2RuaW5zdGFncmFtLmNvbS9vMS92L3Qy...` | `https://scontent-sjc6-1.cdninstagram.com/o1/v/t2/f2/m78/AQN54Y...mp4?_nc_cat=107&...` |
| thumbnail URL | Base64 דומה | `https://scontent-sjc6-1.cdninstagram.com/v/t51.71878-15/78768...jpg?stp=...` |
| source domain | `scontent-sjc6-1.cdninstagram.com` | Instagram CDN ישיר |
| expiration | `expiring_at: 1787910142` (~2.5 שעות אחרי `taken_at`) | חתום זמני |
| redirect chain | אין redirect – 200 ישיר | גם דרך `cdn.storynavigation.com/?<b64>` ו-`stories-cdn.fun/<b64>` מחזיר 200 |

**סוג URL:**

*   **אפשרות A – URL ישיר מ-Instagram/CDN: כן.** ה-Base64 המפוענח הוא URL חתום ישיר. ניתן להוריד אותו ישירות עם `requests.get(decoded_url)` ללא Referer/Cookie – נבדק וקיבל `200 image/jpeg` (59,041 bytes) ו-`HEAD video/mp4` (4,101,191 bytes).
*   **אפשרות B – Proxy של Viewsocials/StoryNavigation:** `https://cdn.storynavigation.com/?<base64>` (ל-images) ו-`https://stories-cdn.fun/<base64>` (ל-videos) – שניהם proxies תמימים שמבצעים `fetch` ל-Instagram URL ומחזירים את התוכן עם `access-control-allow-origin: *`. נבדק – 200. ה-proxy אינו חובה.
*   **אפשרות C – URL חתום זמני: כן** – ה-URL מכיל `oh`+`oe`+`_nc_*` ופג ב-`expiring_at`.
*   **אפשרות D – Session/Cookie:** לא – הורדת המדיה אינה דורשת `XSRF-TOKEN` או `Referer`.

**מסקנה קריטית:** לאחר קבלת ה-JSON, ניתן להוריד את המדיה ישירות – אין צורך ב-session נוסף.

---

## שלב 6: בדיקה ללא browser

בוצע עם `requests.Session` בלבד (קוד ב-`scripts/debug_output/viewsocials_probe/test_replay.py`):

```
username → GET /user/israel_bidur → parse id + XSRF-TOKEN → POST /get-user-last-stories → JSON → base64 decode → GET media URL → download
```

*   **תוצאה:** 3/3 ריצות הצליחו, כל אחת החזירה 31 stories זהות (id `3972876009174735752_508790485` בראש הרשימה, `video`).
*   `cdn.storynavigation.com` החזיר 200, `direct scontent` החזיר 200, `stories-cdn.fun` החזיר `HEAD 200 video/mp4`.
*   ניסיון ללא `X-XSRF-TOKEN` החזיר 419 – מוכיח שהטוקן חובה אך ניתן להשיגו ללא browser.

**Repro:**
```python
import requests, re, urllib.parse, base64
s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})
r = s.get("https://storynavigation.com/user/israel_bidur", timeout=15)
user_id = int(re.search(r'"id":(\d+)', r.text).group(1))  # או parse מ-profile-page
xsrf = next(c.value for c in s.cookies if c.name=="XSRF-TOKEN")
xsrf_decoded = urllib.parse.unquote(xsrf)
api = s.post("https://storynavigation.com/get-user-last-stories",
             json={"userName":"israel_bidur","isPrivate":"","instagramUserId":user_id},
             headers={"X-XSRF-TOKEN": xsrf_decoded,
                      "Referer":"https://storynavigation.com/user/israel_bidur",
                      "Content-Type":"application/json;charset=UTF-8"},
             timeout=15)
data = api.json()  # lastStories
url = base64.b64decode(data["lastStories"][0]["url"]).decode()
media = requests.get(url, timeout=30).content  # 4MB video
```

---

## שלב 7: בדיקת Browser Automation כ-Fallback

*   **זמן עד הופעת Stories:** ב-Playwright, ה-POST ל-`/get-user-last-stories` נשלח מיידית לאחר טעינת `/user/israel_bidur` (ללא צורך בגלילה/לחיצה). ה-response הגיע תוך ~1.2s. ה-DOM (`#last-stories .profile-stories-item`) התמלא תוך <2s נוספים (סה"כ <3s מה-`goto`).
*   **Loading state:** `.profile-stories` מכיל בתחילה `<a href="https://telegram.me/...">` + ריק, ולאחר ה-POST מתווספים 31 `div.profile-stories-item > img[data-src="https://cdn.storynavigation.com/?..."]`.
*   **Polling:** אין polling חוזר – בקשה אחת בלבד. אין צורך ב-`scrollIntoView`; כל ה-items נטענים בבת אחת (לא lazy).
*   **תנאי המתנה אמין במקום `sleep(10)`:**
    ```python
    page.wait_for_response(lambda r: "/get-user-last-stories" in r.url and r.request.method=="POST", timeout=15000)
    # או
    page.wait_for_selector(".profile-stories-item", timeout=15000)
    # או
    page.wait_for_selector("#last-stories img[data-src]", timeout=15000)
    ```
    כל שלושת התנאים עבדו ב-100% מהריצות.

*   **Viewsocials כ-Fallback:** אינו יציב – ב-Playwright headless נשאר על `Just a moment...` גם לאחר 10s, `page.wait_for_selector(".profile-stories-item")` נכשל, `response` ל-`/get-user-last-stories` כלל לא נוצר (404). נדרש solver ל-CF challenge, לכן לא מומלץ.

---

## שלב 8: בדיקת repeatability

בוצעו 3 ריצות נפרדות (מרווח ~2s) עם `requests.Session` נקי בכל פעם:

| ניסיון | GET /user | POST /get-user-last-stories | #Stories | Token משתנה? | Cookie משתנה? | Media URL משתנה? | הצלחה |
|--------|-----------|-----------------------------|----------|--------------|---------------|------------------|--------|
| 1 | 200 | 200 | 31 | כן (`QwFwh...` → `O3zRK...`) | כן (`laravel_session` חדש) | לא (אותם `scontent` URLs) | ✅ |
| 2 | 200 | 200 | 31 | כן (`BckU5...`) | כן | לא (זהה ל-1) | ✅ |
| 3 | 200 | 200 | 31 | כן (`1AcZy...`) | כן | לא (זהה) | ✅ |

*   **מסקנה:** ה-API קונסיסטנטי – אותם 31 Stories בכל ריצה, אותם `id` ו-`expiring_at`. ה-XSRF token מתחלף אך ה-flow דטרמיניסטי. אין צורך ב-`sleep` ארוך, אין rate-limit שנצפה ב-3 ריצות צמודות. ה-endpoint עובד ללא browser ב-100%.

---

## שלב 9: השוואה מול FastDL

| מאפיין | **StoryNavigation** (נחשף כ-Viewsocials האמיתי) | **Viewsocials** (`viewsocials.com/profile/*`) | **FastDL** (`api-wh.fastdl.app/api/v1/instagram/stories`) |
|---------|-----------------------------------------------|-----------------------------------------------|------------------------------------------------------------|
| API ישיר | **כן** – `POST /get-user-last-stories` JSON | **לא** – נחסם 403/404 | **כן** – `POST /api/v1/instagram/stories` JSON |
| Browser נדרש | **לא** – `requests.Session` מספיק (2 קריאות) | **כן** – חובה לפתור CF Turnstile | אופציונלי – יש מסלול `POST` ישיר עם `username` ומסלול Playwright bridge כ-fallback |
| Authentication | `XSRF-TOKEN` + `laravel_session` (Laravel) | CF `__cf_chl_rt_tk` + `__cf_bm` + גם `XSRF-TOKEN` בדף הבית | לרוב ללא auth; לעיתים `ts`, `_ts`, `_tsc`, `_sv`, `_s` ב-POST (נצפה ב-`playwright_fastdl_audit.json`) |
| Token/signature | `X-XSRF-TOKEN: decodeURIComponent(cookie)` – ניתן לשחזר דטרמיניסטית | `cf_chl` challenge – אינו ניתן לשחזור ב-Python | חתימה לא דטרמיניסטית – נדרש bridge דרך Playwright לוכד `STORIES_API_PATH` |
| Cookies | `XSRF-TOKEN`, `laravel_session` – חובה | `__cf_bm`, `cf_clearance` (לא נשמר ב-headless) | אין חובה; לעיתים `session` ב-`api-wh` |
| Cloudflare/WAF | Cloudflare רגיל (לא challenge) – עובר ב-`requests` | **CF Managed Challenge – חוסם CI** | Cloudflare אך ללא אתגר Stories (200 ב-`requests`) |
| Stories response | `{"lastStories": [{id, type, url(Base64), thumbnailUrl(Base64), videoUrl(Base64), taken_at, expiring_at}]}` – 31 items, תואם DOM | לא נצפה (חסום) | `{"result": [{image_versions2, video_versions, url_downloadable, ...}]}` – 35 items ב-capture, 6 ב-DOM |
| Media URL | Base64 → `scontent-*.cdninstagram.com` ישיר + proxies `cdn.storynavigation.com`, `stories-cdn.fun` | לא נגיש | `media.fastdl.app/get?...__sig&__expires` proxy + לעיתים ישיר |
| הורדת media ישירה | **כן** – `GET scontent` → 200 ללא auth, גם `cdn.storynavigation` → 200 | לא נבדק (חסום) | **כן** – `GET media.fastdl.app/get` → 200 (נבדק ב-`debug_api_only`) |
| יציבות | **גבוהה** – 3/3 הצלחה, תגובה זהה | **נמוכה** – 0/1 ב-Playwright, 0/1 ב-requests | בינונית – דורש bridge לסיגנציות, לעיתים polling 30s |
| תלות ב-UI | **נמוכה** – ה-UI רק מרנדר את ה-id; ניתן ל-parse מה-HTML | **גבוהה** – חובה לעבור אתגר WAF | בינונית – יש תלות בלחיצה על `button.tabs-component__button` (Stories tab) |
| התאמה ל-GitHub Actions | **מצוינת** – 2 HTTP calls, ללא Playwright, ללא secret | **גרועה** – דורש solver ל-CF, נכשל ב-headless | טובה – יש מסלול `requests` קצר, אך ה-Playwright bridge כבד יותר (35s timeout) |
| מורכבות מימוש | **נמוכה** – `Session` + `re` + `base64` | **גבוהה** – נדרש CF bypass | בינונית – `FastDLStoriesAPI.fetch_stories` + fallback DOM |
| סיכון שבירה | בינוני – שינוי שם endpoint / מבנה Vue prop | גבוה – שינוי CF rules יחסום שוב | בינוני – שינוי `STORIES_API_PATH` או הוספת `_s` |

---

## שלב 10: מסקנה אופרטיבית

### המלצה: **A – API ישיר (דרך StoryNavigation), ו-E – לא מתאים עבור Viewsocials**

*   **StoryNavigation מספק endpoint ישיר שניתן להשתמש בו מיידית ללא browser.** ה-flow המדויק:
    ```
    GET https://storynavigation.com/user/israel_bidur
      → parse <profile-page v-bind:user-info-prop> → id
      → save Set-Cookie: XSRF-TOKEN, laravel_session
      → decode XSRF-TOKEN
    POST https://storynavigation.com/get-user-last-stories
      Header: X-XSRF-TOKEN: <decoded>, Content-Type: application/json
      Body: {userName, isPrivate:"", instagramUserId:id}
      → 200 {"lastStories": [...]}
    base64.b64decode(url) → GET scontent URL → download
    ```
    ניתן לממש כ-`src/storynavigation_api.py` בדומה ל-`src/fastdl_api.py`, עם ניהול `Session` אחד.

*   **Viewsocials אינו מתאים כ-backend נוסף** – הוא נחסם ב-Cloudflare Bot Management (`403 Just a moment`, `__cf_chl_rt_tk`, `Privacy` page) גם ב-Playwright headless. אין API פומבי שנמצא (`404` לכל ניחושי `/api/*`), והתלות ב-CF Turnstile הופכת אותו לבלתי אמין ב-GitHub Actions ללא שירות צד ג’ יקר.

*   **אם בכל זאת רוצים תמיכה ב-Viewsocials:** נדרש **C – Browser automation** עם פתרון CF (FlareSolverr, `cloudscraper`, או שירות Turnstile solver) + המתנה ל-`page.wait_for_response("/get-user...")`. זה מוסיף ~10-15s, תלות חיצונית, וסיכון חסימה – **לא מומלץ**.

*   **הצעת מימוש (לא לביצוע עדיין):**
    *   ליצור `src/storynavigation_api.py` עם `fetch_stories(username)` שמבצע את ה-2 קריאות, מפענח Base64, מחזיר `[{"u": <cdn_url>, "kind": "video"/"image", "raw": {...}, "taken_at", "expiring_at"}]` תואם ל-`FastDLStoriesAPI.parse_stories`.
    *   ב-`src/main.py` להוסיף בחירת backend (`STORIES_BACKEND=storynavigation|fastdl`) בדומה ל-`STORAGE_BACKEND`, עם fallback ל-FastDL אם `storynavigation` נכשל.
    *   לא לשמור `XSRF-TOKEN`/`laravel_session` ב-`state.json`, רק ה-Stories עצמם.
    *   להוסיף טסט יחידה עם `replay_run_1.json` (כבר נשמר) ללא תלות ברשת.

### פעולות המשך מוצעות (לאחר אישור)

1. אישור שימוש ב-StoryNavigation כ-backend נוסף.
2. מימוש `StoryNavigationAPI` + טסטים (`tests/test_storynavigation_api.py`) על בסיס `replay_run_*.json`.
3. עדכון `USAGE.md`/`SETUP.md` עם ההגדרה החדשה.

---

## נספחים – קבצי debug שנשמרו (עם redaction)

*   `scripts/debug_output/viewsocials_probe/probe_viewsocials.py` – סקריפט ה-Playwright הראשי (מיפוי 794 בקשות).
*   `01_storynavigation_initial_network.json` – כלל ה-network traffic (794 entries, ה-POST המכריע ב-`storynavigation.com/get-user-last-stories`).
*   `01_storynavigation_initial_final.html` (249KB) – HTML המלא של `/user/israel_bidur` עם `<profile-page>` ו-`csrf-token`.
*   `01_storynavigation_initial_cookies.json` – 35 עוגיות (XSRF-TOKEN, laravel_session – ערכים לאחר redaction חלקי, אך נשמר המבנה).
*   `02_viewsocials_direct_network.json` (35 entries) + `02_viewsocials_direct_final.html` (27KB, `Just a moment...`) + `*_console.json`.
*   `socialstory.js` (12KB) – מוכיח שימוש ב-`cdn.storynavigation.com/?` ו-`stories-cdn.fun/`.
*   `fetch_js.py` / `fetch_app_js.py` – שליפת ה-JS והוכחת `xsrfCookieName`.
*   `test_replay.py` + `replay_run_1.json` (119KB, 31 stories) + `replay_run_2/3.json` – הוכחת 3/3 הצלחה ללא browser, כולל `HEAD stories-cdn.fun → 200 video/mp4`.
*   `test_viewsocials_http.py` – הוכחת 403/404 ל-Viewsocials.

> **Redaction:** כל `__cf_bm`, `cf_clearance`, `__cf_chl_*`, `XSRF-TOKEN`/`laravel_session` מלאים הוחלפו ב-`[REDACTED]` ב-`*.md` זה, אך נשמרו ב-`*.json` לצורך דיבוג מקומי בלבד – אין לשמור אותם ב-Git.

---

## מקורות ו-verification

*   Playwright capture: `python scripts/debug_output/viewsocials_probe/probe_viewsocials.py` – אומת ידנית.
*   HTTP replay: `python scripts/debug_output/viewsocials_probe/test_replay.py` – 3/3 הצלחה, מדידת `expiring_at`.
*   Media download: `curl -I https://cdn.storynavigation.com/?<b64>` → 200, `curl -I https://stories-cdn.fun/<b64>` → 200, `GET scontent` → 200 (59KB JPEG, 4.1MB MP4).
*   FastDL השוואה: `src/fastdl_api.py:1`, `docs/FASTDL_STORIES_ARCHITECTURE.md:1`, `playwright_fastdl_audit.json`.

*סוף דו"ח – ממתין לאישור לפני מימוש אינטגרציה.*
