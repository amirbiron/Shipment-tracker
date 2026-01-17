# ⚡ Quick Start Guide - התחלה מהירה

## 🚀 התקנה ב-5 דקות

### 1️⃣ הורד את הקוד
```bash
# פתח את shipment_tracker_bot.tar.gz
tar -xzf shipment_tracker_bot.tar.gz
cd shipment_tracker
```

### 2️⃣ התקן dependencies
```bash
pip install -r requirements.txt
```

### 3️⃣ צור .env
```bash
cp .env.example .env
# ערוך .env והזן:
# - TELEGRAM_BOT_TOKEN (מ-@BotFather)
# - MONGODB_URI (מ-MongoDB Atlas)
# - TRACKING_API_KEY (מ-17TRACK)
```

### 4️⃣ הרץ
```bash
python main.py
```

זהו! הבוט רץ! 🎉

---

## 📦 הקבצים שקיבלת

```
shipment_tracker/
├── 📘 README.md              ← תיעוד מלא
├── 🚀 DEPLOYMENT.md          ← מדריך פריסה
├── 📊 PROJECT_SUMMARY.md     ← סיכום הפרויקט
├── ⚡ QUICK_START.md         ← המדריך הזה
│
├── 🐍 Python Files
│   ├── main.py               ← נקודת כניסה
│   ├── config.py             ← תצורה
│   ├── models.py             ← מודלים
│   ├── database.py           ← MongoDB
│   ├── tracking_api.py       ← 17TRACK
│   ├── scheduler.py          ← Polling
│   ├── bot_handlers.py       ← Handlers 1
│   └── bot_handlers_extra.py ← Handlers 2
│
├── ⚙️ Config Files
│   ├── requirements.txt      ← Dependencies
│   ├── .env.example          ← Template
│   ├── render.yaml           ← Render config
│   └── Procfile              ← Process
│
└── 📄 Docs
    ├── LICENSE               ← MIT
    └── .gitignore            ← Git
```

---

## 🎯 מה הבוט עושה?

1. **מקבל מספר מעקב** מהמשתמש
2. **מזהה חברת שילוח** אוטומטית
3. **עוקב אחר המשלוח** כל 2-6 שעות
4. **שולח התראות** בכל שינוי סטטוס
5. **מעביר לארכיון** אחרי מסירה

---

## 💬 פקודות הבוט

```
/start   - התחל
/add     - הוסף משלוח
/list    - רשימה פעילה
/archive - משלוחים שנמסרו
/refresh - רענן ידנית
/mute    - השתק התראות
/remove  - הסר משלוח
```

---

## 🌐 Deploy לענן (Render)

### אופציה A: דרך GitHub
1. העלה ל-GitHub
2. חבר ל-Render
3. Deploy אוטומטי!

### אופציה B: דרך CLI
```bash
# התקן Render CLI
npm install -g render

# Deploy
render blueprint deploy
```

ראה `DEPLOYMENT.md` למדריך מלא! →

---

## 🆘 עזרה מהירה

### הבוט לא עונה?
```bash
# בדוק logs
python main.py

# אמור לראות:
# ✅ Bot is running!
```

### MongoDB לא מתחבר?
```bash
# בדוק URI ב-.env
echo $MONGODB_URI

# אמור להתחיל ב:
# mongodb+srv://...
```

### 17TRACK לא עובד?
```bash
# בדוק API key
echo $TRACKING_API_KEY

# בדוק quota: features.17track.net
```

---

## 📚 תיעוד מלא

- **README.md** - תיעוד כללי
- **DEPLOYMENT.md** - פריסה צעד-אחר-צעד
- **PROJECT_SUMMARY.md** - טכני מפורט

---

## 🎓 טיפים

### 1. פיתוח מקומי
```bash
# הרץ עם debug
LOG_LEVEL=DEBUG python main.py
```

### 2. בדיקת קוד
```bash
# Install linters
pip install black flake8 mypy

# Format
black *.py

# Lint
flake8 *.py
```

### 3. Monitoring
```bash
# ב-Render
Logs → Live logs

# ב-MongoDB Atlas
Clusters → Metrics
```

---

## ✅ Checklist לפני Production

- [ ] Environment variables מוגדרים
- [ ] MongoDB indexes נוצרו
- [ ] 17TRACK API key תקף
- [ ] Telegram bot verified
- [ ] Logs עובדים
- [ ] Tested כל הפקודות

---

## 🔥 One-liner Deploy

```bash
git init && \
git add . && \
git commit -m "Initial" && \
gh repo create --public && \
git push -u origin main && \
render blueprint deploy
```

*(דורש: git, gh cli, render cli)*

---

## 💡 נתקעת?

1. **קרא** את הלוגים
2. **בדוק** environment variables
3. **חפש** ב-README.md
4. **פתח** Issue ב-GitHub

---

**Ready to ship! 📦🚀**
