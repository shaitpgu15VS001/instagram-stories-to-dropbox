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

## 🐙 חלק 3: יצירת חשבון GitHub

אם כבר יש לך חשבון GitHub - דלג לחלק 4.

1. נווט ל: <https://github.com/signup>
2. מלא את הפרטים (אימייל, סיסמה, שם משתמש)
3. אשר דרך האימייל שקיבלת
4. בחר תוכנית **Free** (חינמית)
