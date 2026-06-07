# 📖 מדריך שימוש - הרצה יומיומית

---

## 📂 חלק 4: יצירת ריפו

### שלב 1: יצירת ריפו חדש ב-GitHub
1. נווט ל: <https://github.com/new>
2. תן שם לריפו: `instagram-stories-to-dropbox`
3. בחר **Private** (פרטי - רק אתה רואה)
4. **אל סמן** "Add a README file"
5. לחץ **Create repository**

### שלב 2: העלאת הקבצים לריפו
GitHub יציג לך הוראות תחת "…or push an existing repository from the command line".

הרץ את הפקודות האלה ב-PowerShell **מתוך התיקייה של הפרויקט** (התיקייה הראשית שבה נמצאים הקבצים):

```powershell
cd "נתיב_מלא_לתיקייה_שלך"
git init
git add .
git commit -m "העלאה ראשונית"
git branch -M main
git remote add origin https://github.com/שם_המשתמש_שלך/instagram-stories-to-dropbox.git
git push -u origin main
```

💡 **טיפ**: החלף `שם_המשתמש_שלך` בשם המשתמש האמיתי שלך ב-GitHub.

💡 **טיפ**: אם Windows שואל אותך אישור לגישה, לחץ "Sign in with your browser" ואשר.

---

## 🔐 חלק 5: הגדרת Secrets

### שלב 1: כניסה להגדרות
1. בריפו שיצרת, לחץ על **Settings** (למעלה)
2. בתפריט השמאלי, לחץ על **Secrets and variables** → **Actions**
3. לחץ על **New repository secret**

### שלב 2: הוספת 3 סודות
לחץ **New repository secret** שלוש פעמים, והוסף:

**סוד ראשון:**
- Name: `DROPBOX_APP_KEY`
- Secret: הדבק את ה-App Key שלך
- לחץ **Add secret**

**סוד שני:**
- Name: `DROPBOX_APP_SECRET`
- Secret: הדבק את ה-App Secret שלך
- לחץ **Add secret**

**סוד שלישי:**
- Name: `DROPBOX_REFRESH_TOKEN`
- Secret: הדבק את ה-Refresh Token שלך
- לחץ **Add secret**


**אם התקנת גם OneDrive (ראה SETUP.md חלק 2.5), הוסף גם:**

**סוד רביעי:**
- Name: `RCLONE_CONF_BASE64`
- Secret: הדבק את קובץ `rclone.conf` שהומר ל-base64
- לחץ **Add secret**

---

## ⚙️ חלק 5.5: בחירת שירות אחסון ברירת מחדל

הפרויקט תומך בשני שירותי אחסון: **Dropbox** (ברירת מחדל) ו-**OneDrive**.

כדי לבחור איזה שירות ישמש כברירת מחדל:
1. בריפו ב-GitHub, לחץ על **Actions** → לחץ על **Download Instagram Stories to Dropbox** → ... → **Workflow file** (או נווט ישירות לקובץ `.github/workflows/sync.yml`)
2. לחץ על **Edit** (עיפרון)
3. מצא את השורה: `STORAGE_BACKEND: 'dropbox'`
4. שנה ל-`STORAGE_BACKEND: 'onedrive'` כדי להשתמש ב-OneDrive
5. לחץ **Commit changes** (כחול-ירוק למעלה)

💡 **טיפ**: הריצה הידנית משתמשת תמיד בברירת המחדל שבחרת. כדי להריץ עם השירות השני, שנה זמנית את `STORAGE_BACKEND` ב-`sync.yml`, הרץ ידנית, ואז החזר אחורה.

---

## 👥 חלק 6: הוספת שמות משתמשים

1. בריפו ב-GitHub, לחץ על הקובץ `usernames.txt`
2. לחץ על האייקון של העיפרון ✏️ (Edit)
3. מחק את הדוגמאות ורשום את שמות המשתמשים שאתה רוצה לעקוב אחריהם
4. **שורה אחת לכל שם משתמש**, בלי @, בלי רווחים מיותרים
5. לחץ **Commit changes** (כפתור ירוק למעלה)

📌 דוגמה:
```
natgeo
nike
instagram
```

---

## ▶️ חלק 7: הרצה ראשונה

### שלב 1: כניסה לטאב Actions
1. בריפו, לחץ על הטאב **Actions** (למעלה)
2. אם מופיעה הודעה "Workflows aren't being run", לחץ **I understand**

### שלב 2: הפעלה ידנית
1. בצד שמאל, תחת "All workflows", לחץ על **Download Instagram Stories to Dropbox**
2. בצד ימין למעלה, לחץ **Run workflow** → **Run workflow** (כפתור ירוק)

### שלב 3: מעקב אחר הלוגים
1. ההרצה תופיע למטה. לחץ עליה
2. לחץ על **sync** בצד שמאל
3. לחץ על השלבים השונים כדי לראות מה קורה
4. **ההרצה הראשונה יכולה לקחת 3-5 דקות** כי היא מתקינה את Chromium של Playwright (כ-150MB)
5. אחרי ההתקנה, כל משתמש לוקח 7-12 שניות (וידאו יכול להגיע ל-20MB ולקחת 15s)

✅ אם הכל הצליח, תראה סיכום עם מספר הקבצים שהועלו.

---

## 📂 חלק 8: בדיקה בדרופבוקס

1. היכנס לחשבון ה-Dropbox שלך באתר <https://www.dropbox.com/home>
2. נווט לתיקייה **Apps** → **[שם האפליקציה שלך]** (אם בחרת App folder)
   או לשורש (אם בחרת Full Dropbox)
3. אתה אמור לראות תיקייה בשם `Instagram`
4. בתוכה תיקייה עם התאריך של היום (למשל `2026-06-04`)
5. בתוכה תיקיות לכל שם משתמש, עם קבצי הסטוריז

📱 הקבצים יופיעו גם באפליקציית Dropbox בטלפון שלך תוך מספר שניות.

---

## 🔄 חלק 9: תחזוקה שוטפת

### הוספת משתמש חדש
1. ערוך את `usernames.txt` ב-GitHub
2. הוסף שם משתמש חדש בשורה חדשה
3. שמור (Commit)

### הסרת משתמש
1. מחק את השורה שלו ב-`usernames.txt`
2. שמור

### בדיקה ידנית
1. Actions → Download Instagram Stories to Dropbox → Run workflow
2. בדוק את הלוגים

### שינוי תדירות
אם אתה רוצה לשנות מ-3 שעות לתדירות אחרת:
1. ערוך את `.github/workflows/sync.yml`
2. שנה את השורה `cron: '0 */3 * * *'` לערך אחר
3. דוגמאות:
   - `0 */1 * * *` - כל שעה
   - `0 */6 * * *` - כל 6 שעות
   - `0 0 * * *` - פעם ביום (בחצות)
4. שמור
