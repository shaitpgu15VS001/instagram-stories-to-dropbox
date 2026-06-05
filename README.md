# 📸 Instagram Stories → Dropbox

אוטומציה שמורידה אוטומטית סטוריז מפרופילי אינסטגרם ציבוריים ושומרת אותם בדרופבוקס שלך, כל 3 שעות, ללא צורך בחשבון אינסטגרם.

---

## 🎯 מה הפרויקט עושה?

- **קורא** רשימת שמות משתמש מקובץ `usernames.txt`
- **מוריד** את הסטוריז הפעילים שלהם (ללא צורך בחשבון אינסטגרם!)
- **מעלה** את הסטוריז לדרופבוקס תחת תיקייה `Instagram/YYYY-MM-DD/<שם משתמש>/`
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

הפרויקט תומך כרגע באתר viewsocials.com להורדת סטוריז:

| אתר | סטטוס | תפקיד | תיעוד |
|---|---|---|---|
| **viewsocials.com** | ✅ פעיל | קוד ראשי ב-`story_downloader.py` | ראה סלקטורים למטה |
| **fastdl.app** | 🔄 גיבוי | `story_downloader_fastdl_backup.py` | [docs/FASTDL_GUIDE.md](docs/FASTDL_GUIDE.md) |
| **instanonimo.com** | ❌ לא עבר | נוסה אך חסום על ידי Cloudflare | ראה הערות למטה |

### סלקטורים של viewsocials.com
- URL: `https://www.viewsocials.com/profile/<username>` (ניווט ישיר)
- סטורי: `div.bg-white.my-2.p-3.rounded`
- כפתור הורדה: `a[href*="download-action"]` (href אמיתי, לא צריך JavaScript)
- popup סגירה: `button[aria-label="Close"]` (לא חוסם תוכן)
- 404: הדף מציג "404 NOT FOUND" למשתמש לא קיים

### תוצאות בדיקה (4 משתמשים)
- @natgeo: 2 קבצים, 7.2s
- @nike: 1 וידאו (10MB), 11.6s
- @instagram: 2 קבצים, 9.2s
- @cristiano: 1 וידאו (10MB), 11.8s
- **סה"כ: 6/6 הצליח, 21MB, ממוצע 10s למשתמש**

### הערה על instanonimo.com
ניסינו לעבור ל-instanonimo.com, אך האתר חוסם אוטומציה דרך Cloudflare Turnstile.
- ❌ Playwright headless נחסם
- ❌ Playwright headed נחסם
- ❌ persistent context נחסם
- ❌ playwright-stealth נחסם
- ❌ curl_cffi עם 5 impersonations שונים - כולם `BotBlocked`

---

## 📂 מבנה הפרויקט

```
instagram-stories-to-dropbox/
├── .github/workflows/sync.yml                ← קובץ האוטומציה של GitHub
├── src/                                       ← קוד Python
│   ├── main.py                                ← נקודת כניסה ראשית
│   ├── dropbox_uploader.py                    ← טיפול בדרופבוקס
│   ├── story_downloader.py                    ← הורדת סטוריז (viewsocials.com)
│   ├── story_downloader_fastdl_backup.py      ← גיבוי עם הערות תיעוד (fastdl.app)
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
