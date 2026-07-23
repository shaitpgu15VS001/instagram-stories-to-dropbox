# 📸 Instagram Stories → Dropbox

אוטומציה שמורידה אוטומטית סטוריז מפרופילי אינסטגרם ציבוריים ושומרת אותם בדרופבוקס שלך, כל 3 שעות, ללא צורך בחשבון אינסטגרם.

---

## 🎯 מה הפרויקט עושה?

- **קורא** רשימת שמות משתמש מקבצי `usernames.txt`, `usernames.csv` או `usernames.xlsx`
- **מוריד** את הסטוריז הפעילים שלהם (ללא צורך בחשבון אינסטגרם!)
- **מעלה** את הסטוריז לדרופבוקס תחת תיקייה `Instagram/YYYY-MM-DD/<שם תיקייה>/` (ניתן לקבוע שם מותאם עם `תצוגה | username`)`
- **לא מעלה** קובץ שכבר הועלה בעבר
- **רץ אוטומטית** כל 3 שעות דרך GitHub Actions
- **לא דורש** שרת משלך, מחשב פועל, או ידע טכני

---

## ⚠️ אזהרה חשובה - קרא לפני שמתחילים

הפרויקט משתמש בשירותים חיצוניים כדי להוריד סטוריז.
- ✅ זה עובד בלי חשבון אינסטגרם
- ✅ משתמש בדפדפן אמיתי (Playwright) - עוקף חסימות אנטי-בוט
- ⚠️ אין ערובה רשמית שהשירותים ימשיכו לעבוד לתמיד
- ⚠️ אם האתר הנוכחי יפסיק לעבוד, יש גיבוי מוכן (`docs/FASTDL_GUIDE.md`)
- ⚠️ סטוריז של חשבונות **פרטיים** לא יורדו (רק ציבוריים)

---

## 📋 תוכן העניינים

המדריך מחולק ל-3 קבצים:

1. **[SETUP.md](SETUP.md)** - הכנה והתקנה צעד אחר צעד
   - יצירת אפליקציית Dropbox
   - קבלת מפתחות API
   - יצירת חשבון GitHub
   - יצירת הריפו
   - הגדרת Secrets
2. **[USAGE.md](USAGE.md)** - שימוש יומיומי
   - הוספת שמות משתמשים
   - הרצה ראשונה
   - בדיקה בדרופבוקס
   - תחזוקה שוטפת
3. **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - פתרון בעיות
   - שגיאות נפוצות
   - מה לעשות כשמשהו לא עובד

---

## 🌐 אתרים נתמכים

הפרויקט משתמש ב-`fastdl.app` להורדת סטוריז:

| שירות אחסון | סטטוס | מימוש | תיעוד |
|---|---|---|---|---|
| **Dropbox** | ✅ פעיל (ברירת מחדל) | `dropbox_uploader.py` | SETUP.md חלק 2 |
| **OneDrive** | ✅ פעיל | `rclone_uploader.py` (דרך rclone) | SETUP.md חלק 2.5 |

הבחירה בין Dropbox ל-OneDrive נעשית דרך משתנה הסביבה `STORAGE_BACKEND` (ברירת מחדל: `dropbox`).

---

### אתרים נתמכים

| אתר | סטטוס | תפקיד | תיעוד |
|---|---|---|---|
| **fastdl.app** | ✅ פעיל | קוד ראשי ב-`story_downloader.py` | ראה סלקטורים למטה |
| **viewsocials.com** | ❌ חסום ב-GitHub | נוסה אך Cloudflare חוסם את ה-IP של GitHub Actions | ראה הערות למטה |
| **instanonimo.com** | ❌ לא עבר | נוסה אך חסום על ידי Cloudflare Turnstile | ראה הערות למטה |

### סלקטורים של fastdl.app
- URL ראשי: `https://fastdl.app/instagram-anonymously-viewer` (טופס חיפוש)
- שדה חיפוש: `#search-form-input`
- כפתור חיפוש: `#searchFormButton`
- מידע משתמש: `.user-info`
- טאב Stories: `button.tabs-component__button` (מכיל "Stories")
- סטורי: `.media-content--story`
- כפתור הורדה: `.button__download`
- URL הורדה: `https://media.fastdl.app/?filename=...&token=...` (CDN נפרד)

### תוצאות בדיקה מקומית (4 משתמשים)
- @natgeo: ✅ (לפעמים אין סטוריז פעילים)
- @nike: 1 וידאו (10MB), ~13s
- @instagram: 2 קבצים, ~7s
- @cristiano: ✅ (לפעמים אין סטוריז פעילים)
- **בדרך כלל 1-3 קבצים למשתמש, 7-20 שניות**

### הערה על viewsocials.com
ניסינו לעבור ל-viewsocials.com, אך Cloudflare חוסם את ה-IP של GitHub Actions:
- ❌ `context.request.get()` → 403
- ❌ `fetch()` מהדפדפן → 403
- ❌ `page.goto()` בכרטיסייה חדשה → 403
- ❌ `curl_cffi` עם TLS impersonation → 403
- ❌ לחיצה על לינק → ניווט לדף HTML (Cloudflare), ללא download event

הקוד נשמר בגיבוי למקרה שהבעיה תיפתר.

---

## 📂 מבנה הפרויקט

```
instagram-stories-to-dropbox/
├── .github/workflows/sync.yml                ← קובץ האוטומציה של GitHub
├── src/                                       ← קוד Python
│   ├── main.py                                ← נקודת כניסה ראשית
│   ├── dropbox_uploader.py                    ← טיפול בדרופבוקס
│   ├── rclone_uploader.py                     ← טיפול ב-OneDrive (דרך rclone)
│   ├── story_downloader.py                    ← הורדת סטוריז (fastdl.app)
│   ├── state_manager.py                       ← מניעת כפילויות
│   └── logger.py                              ← לוגים
├── docs/                                      ← תיעוד
│   └── FASTDL_GUIDE.md                        ← מדריך מלא ל-fastdl.app
├── usernames.txt                              ← רשימת שמות משתמש (לעריכה)
├── requirements.txt                           ← תלויות Python
├── README.md                                  ← הקובץ הזה
├── SETUP.md                                   ← מדריך ההתקנה
├── USAGE.md                                   ← מדריך השימוש
└── TROUBLESHOOTING.md                         ← פתרון בעיות
```

---

## 🔒 אבטחה ופרטיות

- ✅ כל הסיסמאות והטוקנים מאוחסנים ב-**GitHub Secrets** - מוצפנים ולא גלויים
- ✅ אף אחד אחר לא יכול לראות את הקבצים בריפו אם הוא Private
- ✅ Dropbox מקבל גישה רק לקבצים שהאפליקציה יוצרת
- ⚠️ אל תשתף את הריפו עם אנשים אחרים אם הוא Public
- 💡 אם אתה חושד שמישהו קיבל גישה - תוכל לבטל את ה-Refresh Token ב-Dropbox App Console

---

## 📞 עזרה נוספת

אם משהו לא עובד ולא מצאת פתרון:
- עבור ל-[TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- בדוק את הלוגים ב-GitHub Actions - הם מפורטים מאוד ומסבירים בדיוק מה קרה

---

## 📜 רישיון

הפרויקט הזה הוא קוד פתוח, השימוש בו על אחריותך בלבד.
