"""
Additional Bot Handlers - Part 2
Refresh, Mute, Remove functionality
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bson import ObjectId

from models import STATUS_TRANSLATIONS_HE
from database import get_database
from tracking_api import get_tracking_api, TrackingAPIError
from bot_handlers import _check_rate_limit, _format_time_ago, get_main_menu_keyboard

logger = logging.getLogger(__name__)


async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /refresh command - manual refresh of shipment status
    With cooldown to prevent API abuse
    """
    user_id = update.effective_user.id
    
    # Check cooldown (10 minutes)
    if not await _check_rate_limit(user_id, 'refresh', minutes=10, max_actions=1):
        await update.message.reply_text(
            "⏳ ניתן לרענן פעם ב-10 דקות.\n"
            "נסה שוב בעוד מספר דקות.",
            parse_mode='HTML'
        )
        return
    
    db = await get_database()
    
    # Get user's active shipments
    subscriptions = await db.get_user_subscriptions(user_id)
    
    if not subscriptions:
        await update.message.reply_text(
            "📭 אין לך משלוחים פעילים.\n\n"
            "לחץ על '➕ הוסף משלוח' או שלח מספר מעקב ישירות.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # If only one shipment, refresh it directly
    if len(subscriptions) == 1:
        subscription, shipment = subscriptions[0]
        await _perform_refresh(update, shipment, subscription.item_name)
    else:
        # Multiple shipments - show selection
        await _show_refresh_selection(update, subscriptions)


async def _show_refresh_selection(update: Update, subscriptions: list):
    """Show keyboard to select which shipment to refresh"""
    keyboard = []
    
    for subscription, shipment in subscriptions:
        keyboard.append([
            InlineKeyboardButton(
                f"🔄 {subscription.item_name} ({shipment.tracking_number})",
                callback_data=f"refresh:{shipment.id}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📦 בחר משלוח לרענון:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle refresh callback from inline keyboard"""
    query = update.callback_query
    await query.answer()
    
    shipment_id_str = query.data.split(':', 1)[1]
    shipment_id = ObjectId(shipment_id_str)
    
    db = await get_database()
    shipment = await db.get_shipment(shipment_id)
    
    if not shipment:
        await query.edit_message_text("❌ משלוח לא נמצא.")
        return
    
    await _perform_refresh(update, shipment, "המשלוח", is_callback=True)


async def _perform_refresh(update: Update, shipment, item_name: str, is_callback: bool = False):
    """Perform the actual refresh operation"""
    db = await get_database()
    
    # Send status message
    if is_callback:
        status_msg = await update.callback_query.edit_message_text(
            f"🔄 מרענן את {item_name}...",
            parse_mode='HTML'
        )
    else:
        status_msg = await update.message.reply_text(
            f"🔄 מרענן את {item_name}...",
            parse_mode='HTML'
        )
    
    try:
        async with await get_tracking_api() as api:
            # Get fresh tracking data
            tracking_data = await api.get_tracking_info(
                shipment.tracking_number,
                shipment.carrier_code
            )
            
            if not tracking_data:
                await status_msg.edit_text(
                    f"❌ לא ניתן לקבל מידע על המשלוח כרגע.\n"
                    f"מספר מעקב: <code>{shipment.tracking_number}</code>\n"
                    f"נסה שוב מאוחר יותר.",
                    parse_mode='HTML'
                )
                return
            
            # Parse response
            new_event, new_hash = api.parse_tracking_response(tracking_data)
            
            if not new_event:
                # Show what we got from API for debugging
                track_info = tracking_data.get('track', {})
                status_code = track_info.get('b', 'N/A') if track_info else 'N/A'
                await status_msg.edit_text(
                    f"ℹ️ אין מידע זמין עבור משלוח זה כרגע.\n\n"
                    f"מספר מעקב: <code>{shipment.tracking_number}</code>\n"
                    f"קוד סטטוס API: {status_code}\n\n"
                    f"ייתכן שהמשלוח עדיין לא נרשם במערכת המעקב.",
                    parse_mode='HTML'
                )
                return
            
            # Check if changed
            changed = new_hash != shipment.last_event_hash
            
            # Update shipment
            if changed:
                shipment.last_event = new_event
                shipment.last_event_hash = new_hash
            
            shipment.last_check_at = datetime.utcnow()
            await db.update_shipment(shipment)
            
            # Get all events for history
            all_events = api.parse_all_events_17track(tracking_data)
            
            # Build result message
            lines = [
                f"📦 <b>{item_name}</b>",
                f"מספר מעקב: <code>{shipment.tracking_number}</code>",
                "",
                f"<b>סטטוס:</b> {STATUS_TRANSLATIONS_HE.get(new_event.status_norm, 'לא ידוע')}",
            ]
            
            if changed:
                lines.append("🔔 <i>עדכון חדש!</i>")
            
            # Add tracking history
            if all_events:
                lines.append("")
                lines.append("<b>📜 היסטוריית מעקב:</b>")
                
                # Show up to 10 recent events
                for event in all_events[:10]:
                    timestamp = event.get('timestamp', '')
                    status = event.get('status', '')
                    location = event.get('location', '')
                    
                    # Format timestamp for display
                    time_display = timestamp[:16] if timestamp else ''  # "YYYY-MM-DD HH:MM"
                    
                    if location:
                        lines.append(f"• {time_display} - {location}")
                        lines.append(f"  {status}")
                    else:
                        lines.append(f"• {time_display} - {status}")
                
                if len(all_events) > 10:
                    lines.append(f"<i>... ועוד {len(all_events) - 10} אירועים</i>")
            
            await status_msg.edit_text(
                "\n".join(lines),
                parse_mode='HTML'
            )
    
    except TrackingAPIError as e:
        logger.error(f"API error during refresh: {e}")
        await status_msg.edit_text(
            "❌ שגיאה בתקשורת עם שרת המעקב.\n"
            "נסה שוב מאוחר יותר.",
            parse_mode='HTML'
        )


async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /mute command - toggle mute for a shipment"""
    user_id = update.effective_user.id
    db = await get_database()

    # Get user's shipments
    subscriptions = await db.get_user_subscriptions(user_id)

    if not subscriptions:
        await update.message.reply_text(
            "📭 אין לך משלוחים פעילים.\n\n"
            "לחץ על '➕ הוסף משלוח' או שלח מספר מעקב ישירות.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # Show selection keyboard
    keyboard = []
    
    for subscription, shipment in subscriptions:
        mute_emoji = "🔕" if subscription.muted else "🔔"
        action = "בטל השתקה" if subscription.muted else "השתק"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{mute_emoji} {action}: {subscription.item_name}",
                callback_data=f"mute:{subscription.user_id}:{shipment.id}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔔 בחר משלוח להשתקה/ביטול השתקה:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mute toggle callback"""
    query = update.callback_query
    await query.answer()
    
    _, user_id_str, shipment_id_str = query.data.split(':')
    user_id = int(user_id_str)
    shipment_id = ObjectId(shipment_id_str)
    
    db = await get_database()
    new_muted = await db.toggle_mute(user_id, shipment_id)
    
    status = "הושתק" if new_muted else "התראות הופעלו"
    emoji = "🔕" if new_muted else "🔔"
    
    await query.edit_message_text(
        f"{emoji} {status} בהצלחה!",
        parse_mode='HTML'
    )


async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /remove command - remove shipment tracking"""
    user_id = update.effective_user.id
    db = await get_database()

    # Get user's subscriptions
    subscriptions = await db.get_user_subscriptions(user_id)

    if not subscriptions:
        await update.message.reply_text(
            "📭 אין לך משלוחים פעילים.\n\n"
            "לחץ על '➕ הוסף משלוח' או שלח מספר מעקב ישירות.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode='HTML'
        )
        return
    
    # Show selection keyboard
    keyboard = []
    
    for subscription, shipment in subscriptions:
        keyboard.append([
            InlineKeyboardButton(
                f"🗑 הסר: {subscription.item_name} ({shipment.tracking_number})",
                callback_data=f"remove:{user_id}:{shipment.id}"
            )
        ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚠️ בחר משלוח להסרה:\n\n"
        "שים לב: פעולה זו תסיר את המעקב אך הנתונים יישמרו במערכת.",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle remove shipment callback"""
    query = update.callback_query
    await query.answer()
    
    _, user_id_str, shipment_id_str = query.data.split(':')
    user_id = int(user_id_str)
    shipment_id = ObjectId(shipment_id_str)
    
    db = await get_database()
    success = await db.delete_subscription(user_id, shipment_id)
    
    if success:
        await query.edit_message_text(
            "✅ המשלוח הוסר מהמעקב שלך.",
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text(
            "❌ שגיאה בהסרת המשלוח.",
            parse_mode='HTML'
        )


async def archive_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle archive shipment callback"""
    query = update.callback_query
    await query.answer()
    
    _, user_id_str, shipment_id_str = query.data.split(':')
    user_id = int(user_id_str)
    shipment_id = ObjectId(shipment_id_str)
    
    db = await get_database()
    success = await db.archive_shipment_for_user(user_id, shipment_id)
    
    if success:
        await query.edit_message_text(
            "📫 המשלוח הועבר לארכיון.",
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text(
            "❌ שגיאה בארכוב המשלוח.",
            parse_mode='HTML'
        )


async def edit_name_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle edit name callback - prompt user for new name"""
    query = update.callback_query
    await query.answer()
    
    _, user_id_str, shipment_id_str = query.data.split(':')
    
    # Store the shipment_id in user context for the next message
    context.user_data['editing_name_for'] = shipment_id_str
    
    await query.edit_message_text(
        "✏️ שלח את השם החדש לחבילה:",
        parse_mode='HTML'
    )


async def handle_name_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Handle name edit if user is in edit mode.
    Returns True if handled, False otherwise.
    """
    if 'editing_name_for' not in context.user_data:
        return False
    
    shipment_id_str = context.user_data.pop('editing_name_for')
    new_name = update.message.text.strip()
    
    if len(new_name) > 50:
        new_name = new_name[:50]
    
    user_id = update.effective_user.id
    shipment_id = ObjectId(shipment_id_str)
    
    db = await get_database()
    success = await db.update_subscription_name(user_id, shipment_id, new_name)
    
    if success:
        await update.message.reply_text(
            f"✅ שם החבילה עודכן ל: <b>{new_name}</b>",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            "❌ שגיאה בעדכון השם.",
            parse_mode='HTML'
        )
    
    return True


async def prompt_for_name_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'add name' prompt callback"""
    query = update.callback_query
    await query.answer()
    
    _, shipment_id_str = query.data.split(':', 1)
    
    # Store in context for next message
    context.user_data['naming_shipment'] = shipment_id_str
    
    await query.edit_message_text(
        "✏️ שלח שם לחבילה (או /skip לדילוג):",
        parse_mode='HTML'
    )


async def skip_name_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle skip name callback"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "✅ המעקב הופעל! ניתן לשנות את השם בכל עת דרך 'המשלוחים שלי'.",
        parse_mode='HTML'
    )


async def handle_new_shipment_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Handle name input for newly added shipment.
    Returns True if handled, False otherwise.
    """
    if 'naming_shipment' not in context.user_data:
        return False
    
    text = update.message.text.strip()
    
    # Check for skip command
    if text.lower() == '/skip':
        context.user_data.pop('naming_shipment', None)
        await update.message.reply_text(
            "✅ בסדר! ניתן לשנות את השם בכל עת דרך 'המשלוחים שלי'.",
            parse_mode='HTML'
        )
        return True
    
    shipment_id_str = context.user_data.pop('naming_shipment')
    new_name = text[:50] if len(text) > 50 else text
    
    user_id = update.effective_user.id
    shipment_id = ObjectId(shipment_id_str)
    
    db = await get_database()
    success = await db.update_subscription_name(user_id, shipment_id, new_name)
    
    if success:
        await update.message.reply_text(
            f"✅ שם החבילה עודכן ל: <b>{new_name}</b>",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            "❌ שגיאה בעדכון השם.",
            parse_mode='HTML'
        )
    
    return True


async def shipment_details_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shipment details callback - show full shipment info with history"""
    query = update.callback_query
    await query.answer()
    
    shipment_id_str = query.data.split(':', 1)[1]
    shipment_id = ObjectId(shipment_id_str)
    
    user_id = update.effective_user.id
    db = await get_database()
    
    # Get shipment and subscription
    shipment = await db.get_shipment(shipment_id)
    subscription = await db.get_subscription(user_id, shipment_id)
    
    if not shipment or not subscription:
        await query.edit_message_text("❌ משלוח לא נמצא.")
        return
    
    # Build detailed message
    lines = [
        f"📦 <b>{subscription.item_name}</b>",
        f"מספר מעקב: <code>{shipment.tracking_number}</code>",
        "",
    ]
    
    if shipment.last_event:
        from models import STATUS_TRANSLATIONS_HE
        status = STATUS_TRANSLATIONS_HE.get(shipment.last_event.status_norm, 'לא ידוע')
        lines.append(f"<b>סטטוס:</b> {status}")
        
        if shipment.last_event.timestamp:
            time_str = shipment.last_event.timestamp.strftime("%d/%m/%Y %H:%M")
            lines.append(f"🕐 {time_str}")
        
        if shipment.last_event.location:
            lines.append(f"📍 {shipment.last_event.location}")
    
    if subscription.muted:
        lines.append("🔕 התראות מושתקות")
    
    lines.append("")
    lines.append("💡 לחץ על <b>רענן</b> לצפייה בהיסטוריה המלאה")
    
    if shipment.last_check_at:
        time_ago = _format_time_ago(shipment.last_check_at)
        lines.append(f"<i>עדכון אחרון: {time_ago}</i>")
    
    # Action buttons
    keyboard = [
        [
            InlineKeyboardButton(
                "🔄 רענן והצג היסטוריה",
                callback_data=f"refresh:{shipment.id}"
            )
        ],
        [
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
        ],
        [
            InlineKeyboardButton(
                "◀️ חזרה לרשימה",
                callback_data="back_to_list"
            )
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def back_to_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back to list callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    db = await get_database()
    
    # Get active subscriptions
    from models import ShipmentState, STATUS_TRANSLATIONS_HE
    subscriptions = await db.get_user_subscriptions(
        user_id,
        state=ShipmentState.ACTIVE
    )
    
    if not subscriptions:
        await query.edit_message_text(
            "📭 אין לך משלוחים פעילים כרגע.\n\n"
            "שלח מספר מעקב ישירות כדי להוסיף משלוח.",
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
    
    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=reply_markup,
        parse_mode='HTML'
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle plain text messages
    Auto-detect tracking numbers
    """
    text = update.message.text.strip()
    
    # Check if user is in name editing/naming mode
    if await handle_name_edit(update, context):
        return
    
    if await handle_new_shipment_name(update, context):
        return
    
    # Check if looks like a tracking number
    if len(text) >= 8 and len(text) <= 30:
        # Might be a tracking number
        cleaned = text.upper().replace(' ', '').replace('-', '')
        
        if cleaned.isalnum():
            # Treat as add command
            context.args = [cleaned]
            await add_command(update, context)
            return
    
    # Not a tracking number
    await update.message.reply_text(
        "❓ לא הבנתי. השתמש ב-/help לעזרה.",
        parse_mode='HTML'
    )


# Import add_command for the message handler
from bot_handlers import add_command
