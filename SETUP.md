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

## 📦 חלק 2: יצירת אפליקציית Dropbox

### שלב 1: כניסה ל-Dropbox App Console
1. נווט ל: <https://www.dropbox.com/developers/apps>
2. התחבר עם חשבון ה-Dropbox שלך
3. לחץ על הכפתור הכחול **Create app**

### שלב 2: בחירת הגדרות
מלא את הטופס כך:
- **Choose an API**: בחר **Scoped access** (גישה מוגבלת - בטוח יותר)
- **Type of access**: בחר **Full Dropbox** (גישה מלאה - כדי שיוכל ליצור תיקיות)
  - לחילופין: **App folder** אם אתה רוצה שהכל יהיה בתיקייה נפרדת
- **Name**: תן שם ייחודי (למשל: `stories-downloader-12345`)

לחץ **Create app**.

### שלב 3: העתקת ה-App Key ו-App Secret
אתה תועבר לעמוד ההגדרות של האפליקציה. תראה:
- **App key** - מחרוזת ארוכה של אותיות ומספרים
- **App secret** - מחרוזת נוספת (לחץ על "Show" כדי לראות)

📋 **העתק את שני אלה** למקום בטוח (פנקס רשימות). נצטרך אותם בהמשך.

### שלב 4: הגדרת הרשאות
1. לחץ על הטאב **Permissions** (בצד)
2. סמן את התיבות:
   - ✅ `files.content.read`
   - ✅ `files.content.write`
3. לחץ **Submit** בתחתית

### שלב 5: הגדרת Redirect URI
1. חזור לטאב **Settings**
2. גלול למטה ל-"OAuth 2 → Redirect URIs"
3. הוסף את ה-URI: `http://localhost`
4. לחץ **Add** ואז **Save**

### שלב 6: קבלת Refresh Token
1. פתח את **PowerShell** במחשב שלך (חפש ב-Windows: "PowerShell")
2. העתק והדבק את הפקודה הבאה, אבל **החלף** את `YOUR_APP_KEY` ב-App Key שלך:

```powershell
$APP_KEY = "YOUR_APP_KEY"
$REDIRECT_URI = "http://localhost"
$url = "https://www.dropbox.com/oauth2/authorize?client_id=$APP_KEY&response_type=code&token_access_type=offline&redirect_uri=$REDIRECT_URI"
Write-Host "פתח את הקישור הבא בדפדפן:" -ForegroundColor Green
Write-Host $url -ForegroundColor Cyan
Start-Process $url
```

3. הדפדפן יפתח. אשר את הגישה (Allow).
4. הדפדפן ינסה להעביר אותך ל-localhost (שלא יעבוד - זה בסדר).
5. **העתק את הקוד משורת הכתובת** - הוא מופיע אחרי `code=` ב-URL, למשל:
   ```
   http://localhost/?code=ABCDEFGHIJKLMNOP&state=...
                                  ^^^^^^^^^^^^^^^^
                                  זה הקוד שלך
   ```

6. עכשיו הרץ ב-PowerShell (שנה גם את YOUR_APP_KEY וגם את YOUR_APP_SECRET וגם את הקוד):

```powershell
$APP_KEY = "YOUR_APP_KEY"
$APP_SECRET = "YOUR_APP_SECRET"
$AUTH_CODE = "הקוד_שהעתקת_מ_שלב_5"
$REDIRECT_URI = "http://localhost"

$body = @{
    code = $AUTH_CODE
    grant_type = "authorization_code"
    client_id = $APP_KEY
    client_secret = $APP_SECRET
    redirect_uri = $REDIRECT_URI
}

$response = Invoke-RestMethod -Uri "https://api.dropboxapi.com/oauth2/token" -Method Post -Body $body
Write-Host "`n✅ הנה ה-Refresh Token שלך:" -ForegroundColor Green
Write-Host $response.refresh_token -ForegroundColor Yellow
Write-Host "`nשמור אותו במקום בטוח! לא תראה אותו שוב." -ForegroundColor Red
```

7. 📋 **העתק את ה-Refresh Token** ושמור אותו עם שאר הפרטים.

עכשיו יש לך 3 דברים חשובים:
- `DROPBOX_APP_KEY` - ה-App Key
- `DROPBOX_APP_SECRET` - ה-App Secret
- `DROPBOX_REFRESH_TOKEN` - ה-Refresh Token (ארוך מאוד)

---

## 🗂️ חלק 2.5: חיבור OneDrive דרך rclone

**דלג על חלק זה אם אתה מעוניין להשתמש רק ב-Dropbox.**

במקום ליצור אפליקציה ב-Azure (שחסום עבורך), נשתמש ב-**rclone** - כלי חינמי שכבר יש לו Client ID מובנה. rclone יתחבר ל-OneDrive שלך, ינהל את ה-Refresh Token בעצמו, ואנחנו נשתמש בו מה-Python.

### שלב 1: התקנת rclone במחשב שלך
פתח PowerShell והרץ:
```powershell
winget install rclone
```
💡 אם `winget` לא מותקן, הורד מ-<https://rclone.org/downloads/> והתקן ידנית.

### שלב 2: יצירת קובץ תצורה ל-OneDrive (שלב אחר שלב)

#### 2.1 קבלת Token מ-Microsoft (בלי לפתוח דפדפן אוטומטי)

הפקודה הבאה **לא תפתח** דפדפן לבד - היא תיתן לך קישור או קוד, ואתה תעתיק אותם ידנית לדפדפן שאתה רוצה (Edge, Chrome, Firefox - מה שבא לך):

```powershell
rclone authorize "onedrive" --auth-no-open-browser
```

#### 2.2 מה יופיע במסך?

תראה משהו כזה:
```
Opening authorization URL in your browser (or copy it manually):
https://login.microsoftonline.com/common/oauth2/authorize?client_id=...

Or open https://microsoft.com/devicelogin and enter the code: ABCDEF123
```

יש שני תרחישים:
- **קישור ארוך** (הכי נפוץ) - תעתיק אותו ותדביק בדפדפן
- **קוד קצר (ABCDEF123) + קישור microsoft.com/devicelogin** - תפתח את הקישור בדפדפן, תזין את הקוד

#### 2.3 מה עושים בדפדפן?

1. תפתח את הדפדפן שאתה רוצה (Edge, Chrome, Firefox - זה לא משנה)
2. תדביק את הקישור (או תפתח `microsoft.com/devicelogin` ותזין את הקוד)
3. תתחבר לחשבון Microsoft שלך (זה שאליו אתה רוצה להעלות את הסטוריז)
4. תופיע הודעה: **"rclone מבקש גישה לקבצים שלך"**
   - תלחץ **"כן"** או **"Accept"**
   - זה נותן ל-rclone גישה רק לקבצים שלך ב-OneDrive (לא לסיסמה, לא למיילים, לא לשום דבר אחר)
5. הדפדפן יגיד **"You can close this window"** - תסגור אותו

#### 2.4 חזרה ל-PowerShell

אחרי שאישרת בדפדפן, ה-PowerShell יראה:
```
Successfully authorized.

Paste the following into the config...
------PASTE START------
{"access_token":"...", "refresh_token":"...", "token_type":"Bearer", "expiry":"..."}
------PASTE END------
```

**תעתיק** את כל הטקסט בין `PASTE START` ל-`PASTE END` (כולל הסוגריים `{}`). זה ה-token שלך.

#### 2.5 שימוש ב-rclone config (הדרך שעובדת)

עכשיו נשתמש בתפריט של rclone כדי ליצור את קובץ התצורה המלא (עם `drive_id` ו-`drive_type` ש-rclone צריך):

```powershell
rclone config
```

תראה תפריט. בצע לפי הסדר:
1. **תמחק את הרמיט הישן** (אם קיים):
   - הקש **d** (delete) → Enter
   - כתוב `onedrive` → Enter
2. **תיצור רמיט חדש**:
   - הקש **n** (new remote) → Enter
   - Name: כתוב `onedrive` → Enter
3. **בחירת סוג אחסון**:
   - תראה רשימה ארוכה של שירותים
   - תקליד את המספר של **Microsoft OneDrive** (בדרך כלל `23`) → Enter
4. **פרטי אפליקציה**:
   - Client Id: **השאר ריק** (Enter)
   - Client Secret: **השאר ריק** (Enter)
5. **"Use auto config?"** → תענה **N** (no) → Enter
   - זה אומר ל-rclone: "אל תפתח דפדפן לבד, אני אדביק את ה-token ידנית"
6. **"Got a code?"** → **תדביק** את כל המחרוזת שהעתקת בשלב 2.4 → Enter
7. **"Choose drive type:"** → **1** (OneDrive Personal) → Enter
   ⚠️ אם אתה משתמש ב-OneDrive של עבודה/לימודים, תבחר **2** (OneDrive Business)
8. **"config_driveid"** → תופיע רשימה של כוננים. תבחר את המספר של **OneDrive (personal)** (אצלך זה היה 3) → Enter
   (זה הכונן האישי שלך, לא תיקיות משותפות)
9. **אשר** → הקש **y** (yes) → Enter
10. **צא** → הקש **q** (quit) → Enter

#### 2.6 לוודא שהכול עובד

הרץ:
```powershell
rclone ls onedrive:
```
אם לא קיבלת שגיאה (גם אם הרשימה ריקה) - זה עובד!

אם קיבלת שגיאה, חוזרים לשלב 2.5 ובוחרים מספר כונן אחר. אצל רוב האנשים זה 0 או 1 או 3.

### שלב 3: המרה ל-base64 ושמירה ב-GitHub Secrets

💡 **מה זה base64?** פשוט דרך להפוך קובץ למחרוזת אחת שאין בעיה להעתיק ולהדביק ב-GitHub. ככה שומרים את קובץ ה-config בתור Secret.

1. הרץ ב-PowerShell:
```powershell
$content = Get-Content "$env:USERPROFILE\.config\rclone\rclone.conf" -Raw
$bytes = [Text.Encoding]::UTF8.GetBytes($content)
$base64 = [Convert]::ToBase64String($bytes)
Write-Host $base64 -ForegroundColor Cyan
```
2. **העתק** את המחרוזת הארוכה שיצאה.
3. עבור ל-GitHub → Settings → Secrets and variables → Actions → **New repository secret**
4. הוסף Secret:
   - **Name**: `RCLONE_CONF_BASE64`
   - **Secret**: הדבק את המחרוזת מהשלב הקודם
   - לחץ **Add secret**

### שלב 4: הגדרת שירות ברירת מחדל
אם אתה רוצה ש-OneDrive יהיה ברירת המחדל במקום Dropbox:
1. פתח את `.github/workflows/sync.yml` ב-GitHub
2. שנה `STORAGE_BACKEND: 'dropbox'` ל-`STORAGE_BACKEND: 'onedrive'`
3. שמור (Commit)

---

## 🐙 חלק 3: יצירת חשבון GitHub

אם כבר יש לך חשבון GitHub - דלג לחלק 4.

1. נווט ל: <https://github.com/signup>
2. מלא את הפרטים (אימייל, סיסמה, שם משתמש)
3. אשר דרך האימייל שקיבלת
4. בחר תוכנית **Free** (חינמית)
