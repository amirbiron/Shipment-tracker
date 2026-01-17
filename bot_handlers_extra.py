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
from tracking_api import get_tracking_api, TrackingAPIError, TrackingNotConfiguredError
from bot_handlers import _check_rate_limit, _format_time_ago

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
            "השתמש ב-/add להוספת משלוח.",
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
                    "❌ לא ניתן לקבל מידע על המשלוח כרגע.\n"
                    "נסה שוב מאוחר יותר.",
                    parse_mode='HTML'
                )
                return
            
            # Parse response
            new_event, new_hash = api.parse_tracking_response(tracking_data)
            
            if not new_event:
                await status_msg.edit_text(
                    "ℹ️ אין מידע זמין עבור משלוח זה כרגע.",
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
            
            # Build result message
            lines = [
                f"✅ <b>{item_name}</b>" + (" - עדכון חדש!" if changed else ""),
                "",
                f"📦 <code>{shipment.tracking_number}</code>",
                "",
                f"<b>סטטוס:</b> {STATUS_TRANSLATIONS_HE.get(new_event.status_norm, 'לא ידוע')}",
            ]
            
            if new_event.status_raw:
                lines.append(f"📝 {new_event.status_raw}")
            
            if new_event.location:
                lines.append(f"📍 {new_event.location}")
            
            if new_event.timestamp:
                time_str = new_event.timestamp.strftime("%d/%m/%Y %H:%M")
                lines.append(f"🕐 {time_str}")
            
            if changed:
                lines.append("\n🔔 זה שינוי חדש!")
            else:
                lines.append("\nℹ️ אין שינוי מהעדכון האחרון")
            
            await status_msg.edit_text(
                "\n".join(lines),
                parse_mode='HTML'
            )
    
    except TrackingNotConfiguredError:
        await status_msg.edit_text(
            "⚠️ <b>המעקב לא מוגדר</b>\n\n"
            "כדי לרענן סטטוס צריך להגדיר מפתח API:\n"
            "• 17TRACK: <code>TRACKING_API_KEY</code> (או <code>SEVENTEENTRACK_API_KEY</code>)\n"
            "• TrackingMore: <code>TRACKINGMORE_API_KEY</code> + <code>TRACKING_PROVIDER=trackingmore</code>\n\n"
            "ב־Render: Service → Environment → הוסף משתנים ואז Deploy מחדש.",
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
            "📭 אין לך משלוחים פעילים.",
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
            "📭 אין לך משלוחים פעילים.",
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


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle plain text messages
    Auto-detect tracking numbers
    """
    text = update.message.text.strip()
    
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
