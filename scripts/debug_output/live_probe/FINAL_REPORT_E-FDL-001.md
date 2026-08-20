# דוח חקירה סופי — FastDL Stories API bridge (E-FDL-001)

תאריך: אוגוסט 2026. סטטוס: חקירה הושלמה, root cause אומת. תיקון: ברמת design בלבד, לא בוצע.

---

## 1. מועמדים לגורם שורש

| # | השערה | סטטוס | איך נבדקה |
|---|-------|-------|-----------|
| 1 | ה-API מחזיר `{"result": []}` (אין Stories) וה-parse מחזיר None במקום רשימה ריקה | **אומת — זה הגורם** | פרוב חי + הרצה ישירה של `parse_stories` |
| 2 | חוסר חתימה (`_s`) ב-requests פשוטים | נפסל כגורם עיקרי | requests פשוטים מחזירים 403, אך ה-browser bridge מצליח תמיד; 403 לא הופיע ב-production |
| 3 | ה-API חוזר 4xx/5xx או timeout | נפסל | ב-production ובפרוב: response 200 `application/json; charset=utf-8` תמיד |
| 4 | בעיית DOM/סלקטורים | נפסל | ה-bridge לוכד את ה-API request/response, אינו נשען על DOM; ה-DOM archived |
| 5 | Stories איטיים: response ראשון ריק ואז מלא | חלקי — לא הוכח ישירות | נצפה polling (עד 3 responses בהפרש של ~29–32 שניות), לא נתפס מקרה ריק-אז-מלא. מכסה את קטגוריית שלוש הנקודות |
| 6 | Rate-limit / חוסר יציבות של fastdl ל-headless | **אומת כתופעה** | בהרצות חוזרות ה-search click לא ייצר tabs או בקשת API כלל |

מסקנה: הגורם היחיד שמסביר false-failure לחשבונות ללא Stories הוא סעיף 1 — bug ב-`parse_stories`.

---

## 2. טבלת שלושת המצבים

| מצב | מה ה-API מחזיר | תוצאה נוכחית בקוד | תוצאה צפויה |
|-----|----------------|-------------------|-------------|
| ללא Stories פעילים | `{"result": []}` | `parse_stories` -> None -> `ValueError` -> **E-FDL-001 (false failure)** | success עם רשימה ריקה — אין סטוריז פעילים כרגע |
| Stories מהירים | `{"result": [items...]}` | `parse_stories` -> רשימה מלאה -> הורדה תקינה | הורדה תקינה (עובד כרגע) |
| Stories איטיים | ריק ואז מלא (משוער), או מלא אחרי עיכוב | במקרה ריק -> E-FDL-001; במקרה מלא -> הצלחה | להבחין בין אין Stories לבין עוד לא מוכנים |

---

## 3. Timeline אמיתי מהריצה שנכשלה

דוגמה: `username=kolbarama run_id=32404984421`.

1. `fetch_stories` מנסה requests ישירים -> 403 -> נופל ל-Playwright bridge.
2. ה-bridge טוען את ה-viewer, לוחץ על חיפוש, לוכד את בקשת ה-API.
3. הבקשה נשלחת עם payload חתום; ה-response חוזר 200 `application/json; charset=utf-8`.
4. `parse_stories` מקבל `{"result": []}` -> מחזיר None.
5. ב-bridge: `items is None` -> `log_failure("parsing", ValueError("API response parsed to no usable stories"))` -> מחזיר None.
6. `story_downloader` -> `return {"success": False, "files": [], "error": "api_error"}`.
7. `main.py`: `api_error` ממופה ל-E-FDL-001 -> FAILED.

בפרוב החי נצפו עבור kolbarama שלושה responses זהים (ריקים) במרווחים של ~29–32 שניות — Polling/retry של הדף.

---

## 4. מבנה ה-response האמיתי

- Response ראשי: 200, `application/json; charset=utf-8`.
- מבנה הצלחה: `{"result": [ {item...}, ... ]}`.
- שדות פריט: `image_versions2.candidates` (תמונות), `video_versions` (סרטונים), `url_downloadable`, `url_wrapped`, `taken_at`, `pk`, `user`.
- כתובות הורדה: פרוקסי אפמרלי ב-`media.fastdl.app/get?__sig=...&__expires=...`.
- מבנה ריק: `{"result": []}`.
- גודל response מלא שנצפה: ~1,553,159 bytes (israel_bidur).

---

## 5. נקודת הכשל המדויקת

- `src/fastdl_api.py:364` — `result = resp_json.get("result") or resp_json.get("data")`
- רשימה ריקה היא falsy ב-Python, לכן `[] or resp_json.get("data")` נותן את `data` (None) במקום `[]`.
- `src/fastdl_api.py:365-366` — `if not isinstance(result, list): return None` -> מחזיר None.
- `src/fastdl_api.py:70-78` — הכוונה המקורית בקוד היתה להבחין בין None לרשימה ריקה (ראו הערה בשורות 71-74), אך ה-`or` הורס זאת.
- `src/fastdl_api.py:296` — `log_failure("parsing", ValueError("API response parsed to no usable stories"))`.
- `src/story_downloader.py:384-395` — מחזיר `error: api_error`.
- `src/main.py:354-360` — `api_error`/`timeout` ממופים ל-E-FDL-001.
- מצד שני, קוד קיים תומך במפורש ב-רשימה ריקה כהצלחה: `src/story_downloader.py:398` ו-`:514` — אין סטוריז פעילים כרגע.

---

## 6. תיקון מומלץ (design only)

החלפת השורה ב-`src/fastdl_api.py:364` כך שרשימה ריקה תישמר כרשימה ריקה:

```python
result = resp_json.get("result")
if result is None:
    result = resp_json.get("data")
```

השפעה: `parse_stories` יחזיר `[]` עבור `{"result": []}` -> ה-bridge יחזיר `[]` -> `story_downloader` יטפל ב-אין סטוריז כהצלחה (כבר קיים בלוג). נשאר None רק למקרי שגיאה אמיתיים.

הערה: אינו מטפל בקטגוריית Stories איטיים (ריק-אז-מלא). לשם כך יידרש שינוי רחב יותר (למשל הבחנה ב-polling), שאינו מומלץ בשלב זה.

---

## 7. סיכונים

- שינוי מינימלי ושימור backwards-compatibility — סיכון נמוך.
- יש לוודא ש-`data` (מבנה אחר אפשרי) עדיין נתמך.
- אין השפעה על שמות קבצים, מבנה תיקיות או פורמט קלט משתמש.
- Rate-limit/חוסר היציבות שנצפה הוא סיכון חיצוני בלתי תלוי ב-bug הזה.
- דרישת חתימת `_s` נשארת — אי אפשר לעקוף את ה-browser bridge בלי התפתחות נוספת.

---

## 8. בדיקות לפני ביצוע

1. הרצה ישירה: `parse_stories({"result": []})` -> צפוי `[]`.
2. `parse_stories({"result": [פריט]})` -> צפוי רשימה עם פריט מנורמל.
3. `parse_stories({"result": None})` -> צפוי None (שגיאה).
4. `parse_stories({"message": "no stories"})` -> צפוי None.
5. `python -m pytest -q` — סט הבדיקות הקיים.
6. ריצה מקומית: `python -m src.main` על חשבון ללא Stories -> צפוי הצלחה עם אין סטוריז, ללא E-FDL-001.
7. ריצה על חשבון עם Stories -> צפויה הורדה תקינה ללא רגרסיה.
8. אימות YAML workflow: `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/sync.yml').read_text(encoding='utf-8'))"`.