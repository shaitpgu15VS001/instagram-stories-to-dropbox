# 🛠️ מדריך התקנה - צעד אחר צעד

מדריך זה ילווה אותך בהתקנה הראשונית של המערכת, מאפס ועד סוף.
זמן משוער: 30-45 דקות.

---

## 🛠️ חלק 1: הכנה

לפני שמתחילים, צריך:
- ✅ חשבון Dropbox (חינמי או בתשלום)
- ✅ גישה למייל (לאימות GitHub ו-Dropbox)
- ✅ 30-45 דקות פנויות
- ✅ מחשב עם Windows, Mac, או Linux

---

## 📦 חלק 2: חיבור אחסוני ענן דרך rclone

המערכת משתמשת בכלי **rclone** כדי להתחבר לכל שירותי הענן (Dropbox, OneDrive ועוד). כל ההגדרות מרוכזות בקובץ `rclone.conf` אחד.

### שלב 1: התקנת rclone במחשב שלך
פתח PowerShell והרץ:
```powershell
winget install rclone
```
💡 אם `winget` לא מותקן, הורד מ-<https://rclone.org/downloads/> והתקן ידנית.

### שלב 2: חיבור ל-Dropbox
הרץ:
```powershell
rclone authorize "dropbox"
```
- תיפתח הודעה עם קישור או קוד
- תפתח את הקישור בדפדפן, תתחבר לחשבון Dropbox שלך ותאשר גישה
- אחרי האישור, ה-PowerShell יציג token. **אל תסגור את החלון** — תצטרך את זה בשלב 4

### שלב 3: חיבור ל-OneDrive (אופציונלי)
אם אתה רוצה גם OneDrive, הרץ:
```powershell
rclone authorize "onedrive" --auth-no-open-browser
```
- תעתיק את הקישור/קוד שמופיע לדפדפן
- תתחבר לחשבון Microsoft שלך ותאשר גישה
- אחרי האישור, יופיע token ב-PowerShell

### שלב 4: יצירת קובץ התצורה
הרץ:
```powershell
rclone config
```
בתפריט:
1. הקש **n** (new remote) → Enter
2. **Name**: כתוב `dropbox` → Enter (חייב להיות זהה לשם משלב 2)
3. תקליד את המספר של **Dropbox** (בדרך כלל `8`) → Enter
4. Client Id: **השאר ריק** (Enter)
5. Client Secret: **השאר ריק** (Enter)
6. **"Use auto config?"** → **N** (no) → Enter
7. **"Got a token?"** → תדביק את ה-token שהתקבל בשלב 2 → Enter
8. **אשר** → **y** (yes) → Enter

אם הגדרת גם OneDrive:
1. הקש שוב **n** → Enter
2. **Name**: כתוב `onedrive` → Enter
3. תקליד את המספר של **Microsoft OneDrive** → Enter
4. Client Id: **השאר ריק** (Enter)
5. Client Secret: **השאר ריק** (Enter)
6. **"Use auto config?"** → **N** (no) → Enter
7. **"Got a token?"** → תדביק את ה-token משלב 3 → Enter
8. בחר **1** (OneDrive Personal) או **2** (Business) → Enter
9. בחר את מספר הכונן → Enter
10. **אשר** → **y** → Enter

בסיום, הקש **q** (quit) → Enter.

### שלב 5: העתקת קובץ התצורה
הרץ:
```powershell
notepad "$env:USERPROFILE\.config\rclone\rclone.conf"
```
העתק **את כל תוכן הקובץ** (העתק-הדבק). זה ייראה בערך כך:
```ini
[dropbox]
type = dropbox
token = {"access_token":"...", "refresh_token":"...", ...}

[onedrive]
type = onedrive
token = {"access_token":"...", "refresh_token":"...", ...}
```

📌 **שמור את התוכן הזה** — תדביק אותו ב-GitHub Secret בהמשך.

---

## 🗂️ חלק 2.5: הגדרת אחסון ברירת מחדל

המערכת תומכת במספר אחסוני ענן בו-זמנית (Dropbox, OneDrive וכו'). כדי לקבוע איזה אחסון ישמש כברירת מחדל:

### דרך א: קובץ STORAGE_BACKEND.txt (מומלץ)
ערוך את הקובץ `STORAGE_BACKEND.txt` וכתוב את שם החיבור הרצוי:
```
dropbox
```
או:
```
onedrive
```

### דרך ב: GitHub Secret (להרצה ידנית)
כשאתה מריץ ידנית (Run workflow), יש שדה אופציונלי **Storage backend** שבו תוכל להזין שם חיבור שונה להרצה הספציפית.

💡 בלוג ההרצה תראה אילו אחסונים מחוברים ואיזה מהם נבחר.

### שלב 6: שמירת קובץ התצורה ב-GitHub Secrets

1. עבור ל-GitHub → Settings → Secrets and variables → Actions → **New repository secret**
2. הוסף Secret:
   - **Name**: `RCLONE_CONF`
   - **Secret**: הדבק את כל תוכן קובץ `rclone.conf` שהעתקת בשלב 5
   - לחץ **Add secret**

✅ זהו! אין צורך ביותר Secrets. קובץ `rclone.conf` אחד מכיל את כל חיבורי הענן שלך.

---

## 🐙 חלק 3: יצירת חשבון GitHub

אם כבר יש לך חשבון GitHub - דלג לחלק 4.

1. נווט ל: <https://github.com/signup>
2. מלא את הפרטים (אימייל, סיסמה, שם משתמש)
3. אשר דרך האימייל שקיבלת
4. בחר תוכנית **Free** (חינמית)
