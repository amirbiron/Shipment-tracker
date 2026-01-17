# 🔄 בחירת ספק API - 17TRACK vs TrackingMore

הבוט תומך בשני ספקי API למעקב משלוחים. מדריך זה יעזור לך לבחור את הספק המתאים.

---

## 📊 השוואה מהירה

| תכונה | 17TRACK | TrackingMore |
|-------|---------|--------------|
| **תמיכה בחברות שילוח** | 3,100+ | 1,700+ |
| **Free Tier** | 100 queries/יום | 100 queries/יום |
| **זיהוי אוטומטי** | ✅ טוב | ✅ מצוין |
| **API Response** | מהיר | מהיר מאוד |
| **תיעוד** | טוב | מצוין |
| **Webhook Support** | ✅ | ✅ |
| **קלות שימוש** | ⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 🎯 מתי לבחור ב-17TRACK?

### ✅ יתרונות
- **כיסוי רחב יותר** - 3,100+ חברות שילוח
- **פופולרי** - נמצא בשימוש נרחב
- **אמין** - API יציב ומבוסס
- **תמיכה בחברות קטנות** - כולל carrier אזוריים

### ⚠️ חסרונות
- **תיעוד פחות ידידותי**
- **Response structure** - צריך parsing מורכב יותר
- **Rate limiting** - 3 req/sec

### 💰 מחירים

| תוכנית | Queries | מחיר |
|--------|---------|------|
| Free | 100/יום | $0 |
| Basic | 1,000/יום | $9.9/חודש |
| Pro | 10,000/יום | $49/חודש |
| Enterprise | Custom | Custom |

### 📝 הרשמה

1. עבור ל-[17TRACK API](https://www.17track.net/en/api)
2. "Sign up for free"
3. מלא פרטים (Email, Company)
4. אשר Email
5. [Console](https://features.17track.net/) → Settings → Security → Access Key
6. העתק את ה-**17token**

---

## 🚀 מתי לבחור ב-TrackingMore?

### ✅ יתרונות
- **API מודרני** - RESTful, נקי, מתועד היטב
- **תיעוד מצוין** - דוגמאות, Postman collection
- **Response structure** - JSON פשוט וברור
- **Dashboard טוב** - UI נוח לניהול
- **Support מהיר** - תגובה טובה

### ⚠️ חסרונות
- **כיסוי קטן יותר** - 1,700+ חברות (עדיין מעולה)
- **פחות ותיק** - API צעיר יותר

### 💰 מחירים

| תוכנית | Queries | מחיר |
|--------|---------|------|
| Free | 100/יום | $0 |
| Starter | 1,000/יום | $9/חודש |
| Growth | 10,000/יום | $49/חודש |
| Business | 100,000/יום | $299/חודש |

### 📝 הרשמה

1. עבור ל-[TrackingMore](https://www.trackingmore.com/api.html)
2. "Sign Up Free"
3. מלא פרטים
4. אמת Email
5. [Dashboard](https://admin.trackingmore.com/) → API
6. העתק את ה-**Tracking-Api-Key**

---

## 🔧 הגדרה בבוט

### אופציה 1: 17TRACK (ברירת מחדל)

```bash
# בקובץ .env
TRACKING_PROVIDER=17track
TRACKING_API_KEY=your_17track_api_key_here
```

### אופציה 2: TrackingMore

```bash
# בקובץ .env
TRACKING_PROVIDER=trackingmore
TRACKINGMORE_API_KEY=your_trackingmore_api_key_here
```

---

## 🧪 בדיקת ה-API

### 17TRACK

```bash
curl -X POST \
  "https://api.17track.net/track/v1/register" \
  -H "17token: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '[{"number":"RR123456789CN"}]'
```

### TrackingMore

```bash
curl -X POST \
  "https://api.trackingmore.com/v4/trackings/create" \
  -H "Tracking-Api-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "tracking_number": "RR123456789CN",
    "carrier_code": "china-post"
  }'
```

---

## 💡 המלצות

### למתחילים
👉 **TrackingMore** - API פשוט יותר, תיעוד טוב יותר

### למקרי שימוש מיוחדים
👉 **17TRACK** - אם צריך carriers נדירים או אזוריים

### לפרודקשן רציני
👉 **שניהם זהים** - שני ה-APIs מעולים ויציבים

### לחיסכון בעלויות
👉 **שווים** - שניהם 100 free queries/יום

---

## 🔄 החלפת ספק

אפשר להחליף בכל רגע! פשוט:

```bash
# עדכן בקובץ .env
TRACKING_PROVIDER=trackingmore  # או 17track
TRACKINGMORE_API_KEY=...        # הוסף את המפתח

# הפעל מחדש את הבוט
python main.py
```

**הערה**: משלוחים קיימים ימשיכו לעבוד - הבוט יעבור לספק החדש באופן שקוף.

---

## 🎓 דוגמאות Carriers נתמכים

### שני הספקים תומכים

- ✅ China Post / EMS
- ✅ USPS
- ✅ DHL
- ✅ FedEx
- ✅ UPS
- ✅ Israel Post
- ✅ Aramex
- ✅ TNT
- ✅ SF Express
- ✅ Cainiao

### רק 17TRACK

- Carriers מקומיים קטנים
- שירותים אזוריים נדירים
- חברות חדשות שעדיין לא ב-TrackingMore

---

## 📊 Quota Management

### עקוב אחר השימוש

**17TRACK**:
```
https://features.17track.net/ → Dashboard → Quota
```

**TrackingMore**:
```
https://admin.trackingmore.com/ → API Usage
```

### טיפים לחיסכון ב-Quota

1. **הגדר POLLING_INTERVAL_MINUTES גבוה** (5-10 דקות)
2. **השתמש ב-Batch queries** (הבוט עושה זאת אוטומטית)
3. **הסר משלוחים שנמסרו** לארכיון
4. **השתמש ב-/refresh במשורה** (יש cooldown)

---

## 🔒 אבטחה

שני הספקים:
- ✅ HTTPS/TLS encryption
- ✅ API Key authentication
- ✅ Rate limiting
- ✅ מוגנים מפני abuse

**חשוב**: 
- 🔐 אל תשתף את ה-API key
- 🔐 השתמש ב-environment variables
- 🔐 אל תעלה .env ל-GitHub

---

## ❓ שאלות נפוצות

### האם יכול להשתמש בשניהם במקביל?
לא. הבוט תומך בספק אחד בכל זמן נתון.

### האם יש הבדל בדיוק?
לא. שני הספקים מקבלים נתונים מאותם מקורות.

### מה קורה אם נגמר לי ה-quota?
הבוט יתקע עד שה-quota יתחדש (יום חדש).

### האם יש webhook במקום polling?
כן! שני הספקים תומכים. נוסיף בגרסה עתידית.

---

## 🎯 הסיכום שלי

| קריטריון | המלצה |
|----------|-------|
| **מתחילים** | TrackingMore 🥇 |
| **Carriers נדירים** | 17TRACK 🥇 |
| **API נקי** | TrackingMore 🥇 |
| **Coverage רחב** | 17TRACK 🥇 |
| **Documentation** | TrackingMore 🥇 |

**Bottom line**: שניהם מצוינים! בחר לפי העדפה אישית. 🚀

---

**צריך עזרה בבחירה? שאל בגיטהאב!** 💬
