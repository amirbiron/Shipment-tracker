"""
Telegram Bot Handlers
All command and callback handlers for the bot
"""
import logging
import re
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from bson import ObjectId

from models import Shipment, Subscription, ShipmentState, STATUS_TRANSLATIONS_HE
from database import get_database
from tracking_api import get_tracking_api, TrackingAPIError
from config import get_config
from activity_reporter import create_reporter

logger = logging.getLogger(__name__)

# (שמור בראש הקובץ אחרי טעינת משתנים)
reporter = create_reporter(
    mongodb_uri=os.getenv(
        "ACTIVITY_MONGODB_URI",
        "mongodb+srv://mumin:M43M2TFgLfGvhBwY@muminai.tm6x81b.mongodb.net/?retryWrites=true&w=majority&appName=muminAI",
    ),
    service_id=os.getenv("ACTIVITY_SERVICE_ID", "srv-d5lkiv63jp1c739heon0"),
    service_name=os.getenv("ACTIVITY_SERVICE_NAME", "Shipment-tracker"),
)

# Rate limiting storage (user_id -> last_action_time)
_rate_limits: Dict[str, datetime] = {}


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Create the main menu keyboard with buttons"""
    keyboard = [
        [
            KeyboardButton("📦 המשלוחים שלי"),
            KeyboardButton("🔄 רענן משלוח")
        ],
        [
            KeyboardButton("📫 ארכיון"),
            KeyboardButton("🔕 השתק התראות")
        ],
        [
            KeyboardButton("❓ עזרה")
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    reporter.report_activity(update.effective_user.id)
    welcome_text = """
🎉 <b>ברוך הבא לבוט מעקב משלוחים!</b>

📦 הבוט מאפשר לך לעקוב אחר משלוחים מכל העולם ולקבל התראות אוטומטיות.

<b>כיצד להתחיל?</b>
• פשוט שלח מספר מעקב ישירות

<b>פעולות זמינות:</b>
📦 המשלוחים שלי - צפה במשלוחים פעילים
🔄 רענן משלוח - רענון ידני של סטטוס
📫 ארכיון - צפה במשלוחים שנמסרו
🔕 השתק התראות - נהל התראות
❓ עזרה - מידע נוסף
"""

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode='HTML'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    reporter.report_activity(update.effective_user.id)
    help_text = """
📖 <b>מדריך שימוש</b>

<b>הוספת משלוח:</b>
1. שלח מספר מעקב ישירות לבוט
2. אם יש מספר חברות שילוח אפשריות, בחר מהרשימה
3. הוסף שם לחבילה (אופציונלי)
4. קבל עדכון מיידי על הסטטוס

<b>ניהול משלוחים:</b>
• 📦 המשלוחים שלי - צפה בכל המשלוחים הפעילים
• 📫 ארכיון - צפה במשלוחים שנמסרו
• 🔄 רענן משלוח - רענן סטטוס ידנית

<b>התראות:</b>
• תקבל התראה אוטומטית בכל שינוי סטטוס
• השתמש ב-🔕 השתק התראות להשתקת התראות למשלוח מסוים
• משלוחים שנמסרו עוברים אוטומטית לארכיון

<b>מגבלות:</b>
• עד 30 משלוחים פעילים במקביל
• רענון ידני: פעם ב-10 דקות
• הוספה: 5 משלוחים לדקה

יש בעיה? פנה לתמיכה או השתמש ב-/start
"""

    await update.message.reply_text(
        help_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode='HTML'
    )


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /add command
    Format: /add [tracking_number] [item_name]
    """
    reporter.report_activity(update.effective_user.id)
    user_id = update.effective_user.id
    
    # Check rate limit
    if not await _check_rate_limit(user_id, 'add', minutes=1, max_actions=5):
        await update.message.reply_text(
            "⚠️ יותר מדי בקשות. נסה שוב בעוד דקה.",
            parse_mode='HTML'
        )
        return
    
    # Parse arguments
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ שימוש: /add [מספר_מעקב] [שם_פריט]\n"
            "דוגמה: /add RR123456789CN אוזניות",
            parse_mode='HTML'
        )
        return
    
    tracking_number = args[0].strip().upper()
    item_name = " ".join(args[1:]) if len(args) > 1 else "משלוח"
    
    # Validate tracking number
    if not _validate_tracking_number(tracking_number):
        await update.message.reply_text(
            "❌ מספר מעקב לא תקין. אנא בדוק ונסה שוב.",
            parse_mode='HTML'
        )
        return
    
    # Check user's active shipments limit
    db = await get_database()
    active_count = await db.count_user_active_subscriptions(user_id)
    config = get_config()
    
    if active_count >= config.app.max_active_shipments_per_user:
        await update.message.reply_text(
            f"⚠️ הגעת למגבלה של {config.app.max_active_shipments_per_user} משלוחים פעילים.\n"
            "הסר משלוח קיים או המתן שמשלוח יימסר.",
            parse_mode='HTML'
        )
        return
    
    # Detect carrier
    status_msg = await update.message.reply_text(
        "🔍 מזהה חברת שילוח...",
        parse_mode='HTML'
    )
    
    try:
        async with await get_tracking_api() as api:
            carriers = await api.detect_carrier(tracking_number)
            
            if not carriers:
                await status_msg.edit_text(
                    "❌ לא ניתן לזהות את חברת השילוח. אנא נסה שוב.",
                    parse_mode='HTML'
                )
                return
            
            # If only one carrier, proceed automatically
            if len(carriers) == 1:
                await _finalize_add_shipment(
                    update,
                    context,
                    tracking_number,
                    item_name,
                    carriers[0].code,
                    status_msg
                )
            else:
                # Multiple carriers - show selection
                await _show_carrier_selection(
                    update,
                    context,
                    tracking_number,
                    item_name,
                    carriers,
                    status_msg
                )
    
    except TrackingAPIError as e:
        logger.error(f"API error in add_command: {e}")
        await status_msg.edit_text(
            "❌ שגיאה בתקשורת עם שרת המעקב. נסה שוב מאוחר יותר.",
            parse_mode='HTML'
        )


async def _show_carrier_selection(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tracking_number: str,
    item_name: str,
    carriers: list,
    status_msg
):
    """Show inline keyboard for carrier selection"""
    # Build keyboard
    keyboard = []
    for carrier in carriers[:5]:  # Max 5 options
        keyboard.append([
            InlineKeyboardButton(
                carrier.name,
                callback_data=f"select_carrier:{tracking_number}:{carrier.code}:{item_name}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await status_msg.edit_text(
        f"📋 נמצאו מספר חברות שילוח אפשריות עבור <code>{tracking_number}</code>\n\n"
        "אנא בחר את חברת השילוח הנכונה:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def carrier_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle carrier selection from inline keyboard"""
    reporter.report_activity(update.effective_user.id)
    query = update.callback_query
    await query.answer()
    
    # Parse callback data
    data_parts = query.data.split(':', 3)
    if len(data_parts) != 4:
        await query.edit_message_text("❌ שגיאה בעיבוד הבחירה.")
        return
    
    _, tracking_number, carrier_code, item_name = data_parts
    
    await _finalize_add_shipment(
        update,
        context,
        tracking_number,
        item_name,
        carrier_code,
        query.message
    )


async def _finalize_add_shipment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    tracking_number: str,
    item_name: str,
    carrier_code: str,
    status_msg
):
    """Finalize adding shipment after carrier is determined"""
    user_id = update.effective_user.id
    db = await get_database()
    
    try:
        await status_msg.edit_text(
            "📡 מתחבר לשרת המעקב...",
            parse_mode='HTML'
        )
        
        async with await get_tracking_api() as api:
            # Register with tracking API
            await api.register_tracking(tracking_number, carrier_code)
            
            # Get initial status
            tracking_data = await api.get_tracking_info(tracking_number, carrier_code)
            
            # Create or get shipment
            existing = await db.get_shipment_by_tracking(tracking_number, carrier_code)
            
            if existing:
                shipment = existing
            else:
                # Create new shipment
                event, event_hash = api.parse_tracking_response(tracking_data) if tracking_data else (None, "")
                
                shipment = Shipment(
                    tracking_number=tracking_number,
                    carrier_code=carrier_code,
                    last_event=event,
                    last_event_hash=event_hash,
                    last_check_at=datetime.utcnow(),
                    next_check_at=datetime.utcnow() + timedelta(hours=2)
                )
                
                shipment.id = await db.create_shipment(shipment)
            
            # Create subscription
            subscription = Subscription(
                user_id=user_id,
                shipment_id=shipment.id,
                item_name=item_name
            )
            
            await db.create_subscription(subscription)
            
            # Build success message
            success_text = [
                "✅ <b>המעקב הופעל בהצלחה!</b>",
                "",
                f"📦 <b>{item_name}</b>",
                f"מספר מעקב: <code>{tracking_number}</code>",
            ]
            
            if shipment.last_event:
                success_text.extend([
                    "",
                    "<b>סטטוס נוכחי:</b>",
                    f"• {STATUS_TRANSLATIONS_HE.get(shipment.last_event.status_norm, 'לא ידוע')}",
                ])
                
                if shipment.last_event.location:
                    success_text.append(f"• מיקום: {shipment.last_event.location}")
            
            success_text.append("\n🔔 תקבל עדכונים אוטומטיים בכל שינוי סטטוס.")
            
            # Check if item_name was not provided (default name)
            if item_name == "משלוח":
                # Prompt user to add a name
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "✏️ הוסף שם לחבילה",
                            callback_data=f"prompt_name:{shipment.id}"
                        ),
                        InlineKeyboardButton(
                            "⏭️ דלג",
                            callback_data="skip_name"
                        )
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await status_msg.edit_text(
                    "\n".join(success_text),
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await status_msg.edit_text(
                    "\n".join(success_text),
                    parse_mode='HTML'
                )
    
    except Exception as e:
        logger.error(f"Error finalizing shipment: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ שגיאה בהוספת המשלוח. נסה שוב מאוחר יותר.",
            parse_mode='HTML'
        )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /list command - show active shipments"""
    reporter.report_activity(update.effective_user.id)
    user_id = update.effective_user.id
    db = await get_database()
    
    # Get active subscriptions
    subscriptions = await db.get_user_subscriptions(
        user_id,
        state=ShipmentState.ACTIVE
    )
    
    if not subscriptions:
        await update.message.reply_text(
            "📭 אין לך משלוחים פעילים כרגע.\n\n"
            "שלח מספר מעקב ישירות כדי להוסיף משלוח.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # Build message with shipment details
    lines = [f"📦 <b>המשלוחים הפעילים שלך ({len(subscriptions)}):</b>", ""]
    
    keyboard = []
    
    for i, (subscription, shipment) in enumerate(subscriptions):
        # Add shipment info to message
        mute_icon = " 🔕" if subscription.muted else ""
        lines.append(f"<b>{i+1}. {subscription.item_name}</b>{mute_icon}")
        lines.append(f"    🔢 <code>{shipment.tracking_number}</code>")
        
        if shipment.last_event:
            status = STATUS_TRANSLATIONS_HE.get(shipment.last_event.status_norm, 'לא ידוע')
            lines.append(f"    📍 {status}")
            if shipment.last_event.location:
                lines.append(f"    📌 {shipment.last_event.location}")
        else:
            lines.append(f"    ⚠️ לחץ על רענן לקבלת סטטוס")
        
        lines.append("")
        
        # Main shipment button (shorter label)
        keyboard.append([
            InlineKeyboardButton(
                f"📦 {subscription.item_name[:20]}",
                callback_data=f"shipment_details:{shipment.id}"
            )
        ])
        
        # Action buttons row
        keyboard.append([
            InlineKeyboardButton(
                "🔄",
                callback_data=f"refresh:{shipment.id}"
            ),
            InlineKeyboardButton(
                "✏️ ערוך",
                callback_data=f"edit_name:{user_id}:{shipment.id}"
            ),
            InlineKeyboardButton(
                "📫 ארכב",
                callback_data=f"archive:{user_id}:{shipment.id}"
            ),
            InlineKeyboardButton(
                "🗑 מחק",
                callback_data=f"remove:{user_id}:{shipment.id}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def archive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /archive command - show delivered shipments"""
    reporter.report_activity(update.effective_user.id)
    user_id = update.effective_user.id
    db = await get_database()
    
    # Get archived subscriptions
    subscriptions = await db.get_user_subscriptions(
        user_id,
        state=ShipmentState.ARCHIVED
    )
    
    if not subscriptions:
        await update.message.reply_text(
            "📪 אין משלוחים בארכיון.\n\n"
            "משלוחים שנמסרו יופיעו כאן.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # Build message with inline keyboard for actions
    lines = [
        f"📫 <b>ארכיון משלוחים ({len(subscriptions)}):</b>",
        ""
    ]
    
    keyboard = []
    
    for subscription, shipment in subscriptions:
        lines.append(f"✅ <b>{subscription.item_name}</b>")
        lines.append(f"   <code>{shipment.tracking_number}</code>")
        
        if shipment.delivered_at:
            date_str = shipment.delivered_at.strftime("%d/%m/%Y")
            lines.append(f"   נמסר ב-{date_str}")
        
        lines.append("")
        
        # Add restore button
        keyboard.append([
            InlineKeyboardButton(
                f"🔄 החזר למעקב: {subscription.item_name}",
                callback_data=f"restore:{shipment.id}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def restore_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle restore shipment callback"""
    reporter.report_activity(update.effective_user.id)
    query = update.callback_query
    await query.answer()
    
    shipment_id_str = query.data.split(':', 1)[1]
    shipment_id = ObjectId(shipment_id_str)
    
    db = await get_database()
    await db.reactivate_shipment(shipment_id)
    
    await query.edit_message_text(
        "✅ המשלוח הוחזר למעקב פעיל!",
        parse_mode='HTML'
    )


def _validate_tracking_number(tracking_number: str) -> bool:
    """Validate tracking number format"""
    # Basic validation
    if len(tracking_number) < 5 or len(tracking_number) > 30:
        return False
    
    # Should contain alphanumeric
    if not re.match(r'^[A-Z0-9]+$', tracking_number):
        return False
    
    return True


def _format_time_ago(dt: datetime) -> str:
    """Format datetime as 'X time ago' in Hebrew"""
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.total_seconds() < 60:
        return "עכשיו"
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() / 60)
        return f"לפני {minutes} דקות"
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() / 3600)
        return f"לפני {hours} שעות"
    else:
        days = int(diff.total_seconds() / 86400)
        return f"לפני {days} ימים"


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle button presses from the main menu keyboard
    Route to appropriate command handlers
    """
    reporter.report_activity(update.effective_user.id)
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    # Map button text to handlers
    if text == "📦 המשלוחים שלי":
        await list_command(update, context)
    elif text == "🔄 רענן משלוח":
        from bot_handlers_extra import refresh_command
        await refresh_command(update, context)
    elif text == "📫 ארכיון":
        await archive_command(update, context)
    elif text == "🔕 השתק התראות":
        from bot_handlers_extra import mute_command
        await mute_command(update, context)
    elif text == "❓ עזרה":
        await help_command(update, context)


async def _check_rate_limit(
    user_id: int,
    action: str,
    minutes: int,
    max_actions: int
) -> bool:
    """
    Check if user is within rate limit
    Returns True if allowed, False if rate limited
    """
    key = f"{user_id}:{action}"
    now = datetime.utcnow()

    if key in _rate_limits:
        last_time = _rate_limits[key]
        if now - last_time < timedelta(minutes=minutes):
            # Still in cooldown
            return False

    _rate_limits[key] = now
    return True
