# 📦 בוט מעקב משלוחים - Shipment Tracker Bot

בוט טלגרם מתקדם למעקב אחר משלוחים מכל העולם עם התראות אוטומטיות בזמן אמת.

## ✨ תכונות עיקריות

- 🌍 **תמיכה ב-3100+ חברות שילוח** דרך 17TRACK או TrackingMore API
- 🔄 **בחירת ספק API** - 17TRACK (חינמי: 100/יום) או TrackingMore (חינמי: 100/יום)
- 🔍 **זיהוי אוטומטי** של חברת השילוח
- 📲 **התראות בזמן אמת** על שינויי סטטוס
- 🗄️ **ארכוב אוטומטי** של משלוחים שנמסרו
- ⏰ **Polling חכם** עם intervals דינמיים לפי סטטוס
- 🔕 **השתקת התראות** למשלוחים ספציפיים
- 📊 **ניהול מתקדם** עם עד 30 משלוחים פעילים
- 🛡️ **Rate limiting** מובנה נגד שימוש לרעה

## 🏗️ ארכיטקטורה

```
├── Telegram Bot (python-telegram-bot 22.5)
│   └── Async handlers + Inline keyboards
├── MongoDB (PyMongo Async)
│   ├── Shipments collection
│   ├── Subscriptions collection
│   └── Events collection (optional)
├── APScheduler (3.11.2)
│   └── Background polling worker
└── 17TRACK API
    └── Batch tracking requests
```

## 📋 דרישות מקדימות

- **Python 3.12+**
- **MongoDB Atlas** (חשבון חינמי)
- **17TRACK API Key** (100 queries חינמיים ליום)
- **Telegram Bot Token** (מ-@BotFather)

## 🚀 התקנה והרצה

### 1. שכפול הפרויקט

```bash
git clone <repository-url>
cd shipment_tracker
```

### 2. יצירת סביבה וירטואלית

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# או
venv\Scripts\activate  # Windows
```

### 3. התקנת Dependencies

```bash
pip install -r requirements.txt
```

### 4. הגדרת משתני סביבה

צור קובץ `.env` בתיקיית הפרויקט:

```bash
cp .env.example .env
```

ערוך את `.env` והזן את הערכים שלך:

```env
# Telegram
TELEGRAM_BOT_TOKEN=your_token_from_botfather

# MongoDB
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/shipment_tracker

# Tracking API - בחר ספק
TRACKING_PROVIDER=17track  # או trackingmore

# האם לחייב מפתח Tracking API בזמן עליית האפליקציה?
# מומלץ להשאיר true. אפשר לשים false כדי שהבוט יעלה בלי מעקב (לצרכי הקמה/דיבוג).
TRACKING_API_REQUIRED=true

# 17TRACK API (אם בחרת 17track)
TRACKING_API_KEY=your_17track_api_key

# TrackingMore API (אם בחרת trackingmore)
TRACKINGMORE_API_KEY=your_trackingmore_api_key

# Settings (אופציונלי)
ENVIRONMENT=development
LOG_LEVEL=INFO
TIMEZONE=Asia/Jerusalem
```

### 5. יצירת אינדקסים ב-MongoDB

האינדקסים נוצרים אוטומטית בהפעלה ראשונה, אך ודא שיש לך:

```javascript
// shipments collection
db.shipments.createIndex({ "state": 1, "next_check_at": 1 })
db.shipments.createIndex({ "tracking_number": 1, "carrier_code": 1 }, { unique: true })

// subscriptions collection
db.subscriptions.createIndex({ "user_id": 1 })
db.subscriptions.createIndex({ "shipment_id": 1 })
db.subscriptions.createIndex({ "user_id": 1, "shipment_id": 1 }, { unique: true })
```

### 6. הרצת הבוט

```bash
python main.py
```

## 🌐 פריסה ל-Render

### שיטה 1: דרך GitHub

1. העלה את הקוד ל-GitHub repository
2. התחבר ל-[Render](https://render.com)
3. לחץ "New" → "Web Service"
4. חבר את ה-repository שלך
5. Render יזהה את `render.yaml` אוטומטית
6. הוסף את משתני הסביבה:
   - `TELEGRAM_BOT_TOKEN`
   - `MONGODB_URI`
   - `TRACKING_API_KEY`
7. לחץ "Create Web Service"

### שיטה 2: Blueprint (מומלץ)

```bash
# בעזרת Render CLI
render blueprint deploy
```

או השתמש בקובץ `render.yaml` הקיים.

### הגדרות Render חשובות

- **Plan**: Free
- **Environment**: Python
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python main.py`
- **Health Check**: לא נדרש (הבוט מריץ polling)

⚠️ **שים לב**: Render Free tier עובר לsleep לאחר 15 דקות ללא פעילות. הבוט ימשיך לעבוד אבל יתעורר רק כשיקבל הודעה.

## 📱 שימוש בבוט

### פקודות זמינות

```
/start - התחל שימוש בבוט
/help - עזרה ומידע
/add [מספר_מעקב] [שם] - הוסף משלוח חדש
/list - הצג משלוחים פעילים
/archive - הצג ארכיון משלוחים
/refresh - רענן משלוח ידנית
/mute - השתק/בטל השתקת התראות
/remove - הסר משלוח מהמעקב
```

### דוגמאות שימוש

```
# הוספה מהירה
RR123456789CN

# הוספה עם שם
/add LZ987654321CN אוזניות מאלי

# רענון ידני (פעם ב-10 דקות)
/refresh

# צפייה במשלוחים
/list
```

## 🔧 מבנה הפרויקט

```
shipment_tracker/
├── config.py              # ניהול תצורה
├── models.py              # מודלי נתונים
├── database.py            # MongoDB operations
├── tracking_api.py        # 17TRACK API client
├── scheduler.py           # Background polling
├── bot_handlers.py        # Telegram handlers (חלק 1)
├── bot_handlers_extra.py  # Telegram handlers (חלק 2)
├── main.py                # Entry point
├── requirements.txt       # Dependencies
├── .env.example           # Environment template
├── render.yaml            # Render configuration
├── Procfile               # Process file
└── README.md              # תיעוד זה
```

## 🎯 Polling חכם

הבוט משתמש באלגוריתם polling דינמי:

| סטטוס | תדירות בדיקה |
|-------|--------------|
| יצא לחלוקה | כל 15 דקות |
| במכס/הגיע ליעד | כל 1.5 שעות |
| בדרך | כל 5 שעות |
| חריגה | כל שעה |
| מידע התקבל | כל 6 שעות |

## 🛡️ Rate Limiting

- **הוספת משלוחים**: 5 לדקה
- **רענון ידני**: פעם ב-10 דקות
- **משלוחים פעילים**: עד 30 למשתמש
- **17TRACK API**: 3 requests/second

## 🔐 אבטחה

- סודות מאוחסנים ב-environment variables
- MongoDB connection מאובטח (TLS/SSL)
- Rate limiting מובנה
- Validation של tracking numbers
- Error handling מקיף

## 📊 לוגים ומעקב

```python
# רמות לוג זמינות
LOG_LEVEL=DEBUG    # מפורט מאוד
LOG_LEVEL=INFO     # רגיל (מומלץ)
LOG_LEVEL=WARNING  # אזהרות בלבד
LOG_LEVEL=ERROR    # שגיאות בלבד
```

## 🐛 בעיות נפוצות

### הבוט לא מגיב

1. בדוק ש-`TELEGRAM_BOT_TOKEN` תקין
2. ודא שהבוט רץ (`python main.py`)
3. בדוק logs לשגיאות

### MongoDB connection failed

1. ודא ש-`MONGODB_URI` נכון
2. בדוק IP whitelist ב-MongoDB Atlas
3. וודא שהרשת מאפשרת חיבורים

### 17TRACK API errors

1. בדוק שיש לך quota זמין
2. ודא ש-API key תקין
3. בדוק rate limits (3 req/sec)
4. אם הלוגים מראים ש-API key לא הוגדר, הוסף `TRACKING_API_KEY` (או `TRACKINGMORE_API_KEY` בהתאם ל-`TRACKING_PROVIDER`)

### Render deployment issues

1. ודא שכל environment variables מוגדרים
2. בדוק build logs לשגיאות
3. Free tier עובר לsleep - זה תקין

## 🔄 עדכונים עתידיים

- [ ] תמיכה ב-Webhooks במקום polling
- [ ] דוחות סטטיסטיקה למשתמשים
- [ ] תמיכה בשפות נוספות
- [ ] UI web למנהלי מערכת
- [ ] אינטגרציה עם Telegram Mini Apps

## 📄 רישיון

MIT License - ראה קובץ LICENSE לפרטים

## 🤝 תרומה

Pull requests מתקבלים בברכה! לשינויים גדולים, אנא פתח issue קודם.

## 📞 תמיכה

- בעיות טכניות: פתח Issue ב-GitHub
- שאלות: השתמש ב-Discussions
- דיווח באגים: Issue עם תגית `bug`

## 🙏 תודות

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [17TRACK](https://www.17track.net) - Tracking API
- [MongoDB](https://www.mongodb.com) - Database
- [Render](https://render.com) - Hosting

---

**נבנה עם ❤️ בישראל**

נהנית מהבוט? תן ⭐ ב-GitHub!
