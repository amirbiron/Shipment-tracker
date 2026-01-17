# 🚀 מדריך פריסה מפורט - Deployment Guide

מדריך צעד אחר צעד לפריסת הבוט על Render.

## 📋 תוכן עניינים

1. [הכנות](#הכנות)
2. [יצירת MongoDB Atlas](#יצירת-mongodb-atlas)
3. [קבלת 17TRACK API Key](#קבלת-17track-api-key)
4. [יצירת Telegram Bot](#יצירת-telegram-bot)
5. [פריסה על Render](#פריסה-על-render)
6. [בדיקה ותחזוקה](#בדיקה-ותחזוקה)

---

## 🎯 הכנות

### דרישות

- חשבון GitHub (חינמי)
- חשבון Render (חינמי)
- חשבון MongoDB Atlas (חינמי)
- חשבון 17TRACK (חינמי)
- חשבון Telegram

---

## 🗄️ יצירת MongoDB Atlas

### שלב 1: הרשמה ויצירת Cluster

1. עבור ל-[MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register)
2. הרשם עם Google/Email
3. לחץ "Build a Database"
4. בחר **M0 FREE** (Shared)
5. בחר region קרוב (למשל: AWS / Frankfurt)
6. שם ל-cluster: `shipment-tracker`
7. לחץ "Create"

### שלב 2: הגדרת Security

#### Network Access

1. בתפריט צד: "Network Access"
2. "Add IP Address"
3. בחר **"Allow Access from Anywhere"**
   ```
   IP: 0.0.0.0/0
   ```
4. לחץ "Confirm"

⚠️ **אזהרה**: זה מתאים לפיתוח. בייצור, הוסף רק את ה-IP של Render.

#### Database Access

1. בתפריט צד: "Database Access"
2. "Add New Database User"
3. בחר **"Password"**
4. שם משתמש: `shipment_bot`
5. סיסמה: לחץ "Autogenerate" ושמור!
6. Database User Privileges: **"Read and write to any database"**
7. לחץ "Add User"

### שלב 3: קבלת Connection String

1. לחץ "Connect" על ה-cluster
2. בחר "Drivers"
3. גרסת Driver: **Python / 3.12 or later**
4. העתק את ה-connection string:
   ```
   mongodb+srv://shipment_bot:<password>@cluster.mongodb.net/?retryWrites=true&w=majority
   ```
5. **החלף `<password>` בסיסמה האמיתית!**
6. הוסף בסוף שם database:
   ```
   mongodb+srv://shipment_bot:YOUR_PASSWORD@cluster.mongodb.net/shipment_tracker?retryWrites=true&w=majority
   ```

שמור את זה! תצטרך בהמשך.

---

## 🔑 קבלת 17TRACK API Key

### שלב 1: הרשמה

1. עבור ל-[17TRACK API](https://www.17track.net/en/api)
2. לחץ "Sign up for free"
3. מלא פרטים:
   - Email
   - Company (אפשר שם פרטי)
   - Purpose: "Personal tracking bot"
4. אשר email

### שלב 2: קבלת API Key

1. התחבר ל-[Management Console](https://features.17track.net/)
2. לך ל-**Settings** → **Security** → **Access Key**
3. לחץ "Generate Key"
4. העתק את ה-**17token** (API key)

⚠️ יש לך 100 queries חינמיים ליום - מספיק ל-MVP!

### שלב 3: הבנת Quotas

| תוכנית | Queries/יום | מחיר |
|--------|-------------|------|
| Free | 100 | $0 |
| Basic | 1,000 | $9.9/חודש |
| Pro | 10,000 | $49/חודש |

---

## 🤖 יצירת Telegram Bot

### שלב 1: פתיחת BotFather

1. פתח Telegram
2. חפש: `@BotFather`
3. שלח: `/start`

### שלב 2: יצירת Bot

1. שלח: `/newbot`
2. שם לבוט: `Shipment Tracker` (או כל שם)
3. Username: `shipment_tracker_bot` (חייב להסתיים ב-`bot`)

תקבל הודעה כזו:
```
Done! Congratulations on your new bot.
Token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

4. **שמור את ה-Token!** זה `TELEGRAM_BOT_TOKEN`

### שלב 3: הגדרות נוספות (אופציונלי)

```
/setdescription - הוסף תיאור
/setabouttext - טקסט About
/setuserpic - תמונה לבוט
/setcommands - רשימת פקודות
```

רשימת פקודות מומלצת:
```
start - התחל שימוש בבוט
help - עזרה ומידע
add - הוסף משלוח חדש
list - הצג משלוחים פעילים
archive - הצג ארכיון
refresh - רענן משלוח ידנית
mute - השתק התראות
remove - הסר משלוח
```

---

## ☁️ פריסה על Render

### שלב 1: העלאת קוד ל-GitHub

```bash
# אתחול Git
cd shipment_tracker
git init

# הוסף קבצים
git add .
git commit -m "Initial commit - Shipment Tracker Bot"

# צור repository ב-GitHub
# עבור ל-github.com/new
# שם: shipment-tracker-bot

# העלה
git remote add origin https://github.com/YOUR_USERNAME/shipment-tracker-bot.git
git branch -M main
git push -u origin main
```

### שלב 2: יצירת Web Service ב-Render

1. עבור ל-[Render Dashboard](https://dashboard.render.com/)
2. לחץ **"New"** → **"Web Service"**
3. **Connect Repository**:
   - "Connect account" עם GitHub
   - בחר את ה-repository שלך
   - לחץ "Connect"

### שלב 3: הגדרות Service

#### Basic Settings

```
Name: shipment-tracker-bot
Region: Oregon (US West) - או קרוב אליך
Branch: main
Runtime: Python
```

#### Build & Deploy

```
Build Command: pip install -r requirements.txt
Start Command: python main.py
```

#### Plan

- בחר **Free**
- 0.1 CPU
- 512 MB RAM
- Sleep after 15 min inactivity

### שלב 4: Environment Variables

לחץ "Add Environment Variable" ל**כל אחד מאלה**:

| שם | ערך | הערה |
|----|-----|------|
| `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | מ-BotFather |
| `MONGODB_URI` | `mongodb+srv://...` | מ-MongoDB Atlas |
| `TRACKING_API_KEY` | `your_17track_key` | מ-17TRACK |
| `ENVIRONMENT` | `production` | קבוע |
| `LOG_LEVEL` | `INFO` | לוגים רגילים |
| `TIMEZONE` | `Asia/Jerusalem` | או timezone שלך |
| `MAX_ACTIVE_SHIPMENTS_PER_USER` | `30` | מגבלה |
| `REFRESH_COOLDOWN_MINUTES` | `10` | cooldown |
| `POLLING_INTERVAL_MINUTES` | `2` | תדירות בדיקה |

### שלב 5: Deploy!

1. לחץ **"Create Web Service"**
2. Render יתחיל:
   - 📦 Build (התקנת dependencies)
   - 🚀 Deploy
   - ✅ Live

זה לוקח 2-3 דקות.

### שלב 6: וידוא שהבוט רץ

#### בדוק Logs

1. ב-Render, לך ל-"Logs"
2. חפש:
   ```
   ✅ Bot is running!
   Database connected
   Scheduler started
   ```

#### בדוק את הבוט

1. פתח Telegram
2. חפש את הבוט שלך: `@your_bot_username`
3. שלח `/start`
4. אמור לקבל הודעת ברוכים הבאים!

---

## 🧪 בדיקה ותחזוקה

### בדיקה בסיסית

```
/start
/help
/add RR123456789CN test-package
/list
/refresh
/archive
```

### מעקב אחר Logs

```bash
# ב-Render Dashboard
Logs → Live logs
```

או דרך CLI:
```bash
render logs --tail
```

### ניטור MongoDB

1. MongoDB Atlas → Clusters
2. לחץ "Browse Collections"
3. בדוק:
   - `shipments` - יש רשומות?
   - `subscriptions` - מנויים?

### בעיות נפוצות

#### הבוט לא מגיב

**סימפטום**: הבוט online אבל לא עונה

**פתרון**:
1. בדוק Logs לשגיאות
2. ודא ש-`TELEGRAM_BOT_TOKEN` נכון
3. רענן את הבוט: Render → "Manual Deploy"

#### MongoDB connection failed

**סימפטום**: `MongoServerSelectionError`

**פתרון**:
1. בדוק IP whitelist (0.0.0.0/0)
2. ודא שהסיסמה נכונה ב-URI
3. בדוק שה-URI כולל `/shipment_tracker`

#### 17TRACK quota exceeded

**סימפטום**: `Rate limit exceeded`

**פתרון**:
1. בדוק שיש quota: 17TRACK Console
2. הפחת `POLLING_INTERVAL_MINUTES` ל-5
3. או שדרג לתוכנית בתשלום

#### Render sleep (Free tier)

**סימפטום**: הבוט לא מגיב לאחר 15 דק'

**זה תקין!** Free tier עובר לsleep.

**אופציות**:
1. שדרג ל-Starter ($7/חודש) - no sleep
2. השתמש ב-cron job כדי להעיר את הבוט
3. קבל את ה-15 דקות downtime

---

## 🔄 עדכונים

### לעדכן את הקוד

```bash
# עשה שינויים בקוד
git add .
git commit -m "Update: feature X"
git push

# Render יעשה deploy אוטומטי!
```

### לעדכן Environment Variables

1. Render Dashboard → Service
2. Environment
3. Edit value
4. "Save Changes"
5. Render יעשה redeploy אוטומטית

---

## 📊 Monitoring

### Render Dashboard

- **Metrics**: CPU, Memory, Network
- **Logs**: Real-time logs
- **Events**: Deploy history

### MongoDB Metrics

- **Cluster Metrics**: Connections, Operations
- **Performance Advisor**: אופטימיזציות
- **Real-time**: תצפית חיה

### 17TRACK Usage

- Features.17track.net → Dashboard
- בדוק: Queries used today

---

## 💰 עלויות צפויות

| שירות | תוכנית | מחיר |
|-------|--------|------|
| Render | Free | $0 |
| MongoDB | M0 | $0 |
| 17TRACK | Free (100/day) | $0 |
| **סה"כ** | | **$0/חודש** |

### אופציות שדרוג (בעתיד)

| שירות | תוכנית | מחיר | יתרונות |
|-------|--------|------|---------|
| Render | Starter | $7/חודש | No sleep, 0.5GB RAM |
| MongoDB | M10 | $9/חודש | Dedicated, backups |
| 17TRACK | Basic | $9.9/חודש | 1,000 queries/יום |

---

## 🎉 סיימת!

הבוט שלך כעת רץ בענן! 🚀

### הצעדים הבאים

1. ✅ שתף את הבוט עם חברים
2. 📊 עקוב אחר השימוש
3. 🔧 שפר ותוסיף features
4. 📝 דווח על bugs

---

**יש שאלות? פתח Issue ב-GitHub!**
