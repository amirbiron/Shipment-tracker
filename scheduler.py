"""
Scheduler module for background polling
Uses APScheduler to periodically check shipments
"""
import logging
from datetime import datetime, timedelta
from typing import List
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from models import Shipment, StatusNorm, ShipmentState
from database import get_database
from tracking_api import get_tracking_api, TrackingAPIError, RateLimitError
from config import get_config

logger = logging.getLogger(__name__)


class ShipmentScheduler:
    """Background scheduler for tracking shipments"""
    
    def __init__(self, bot):
        """
        Initialize scheduler
        bot: Telegram Bot instance for sending notifications
        """
        self.bot = bot
        self.scheduler = AsyncIOScheduler(timezone='UTC')
        self.config = get_config()
    
    def start(self):
        """Start the scheduler"""
        if not getattr(self.config.tracking_api, "enabled", True):
            logger.warning(
                "Tracking API is disabled (TRACKING_API_REQUIRED=false or missing key). "
                "Scheduler will not start."
            )
            return

        # Add polling job
        self.scheduler.add_job(
            self._poll_shipments,
            trigger=IntervalTrigger(
                minutes=self.config.app.polling_interval_minutes
            ),
            id='poll_shipments',
            name='Poll shipments for updates',
            replace_existing=True
        )
        
        self.scheduler.start()
        logger.info("Scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    async def _poll_shipments(self):
        """
        Main polling job
        Fetches shipments due for check and processes them
        """
        logger.info("Starting shipment polling...")
        
        try:
            db = await get_database()
            
            # Get shipments that need checking
            shipments = await db.get_shipments_due_for_check(limit=100)
            
            if not shipments:
                logger.debug("No shipments due for check")
                return
            
            logger.info(f"Found {len(shipments)} shipments to check")
            
            # Process in batch
            await self._process_shipments_batch(shipments)
            
        except Exception as e:
            logger.error(f"Error in polling job: {e}", exc_info=True)
    
    async def _process_shipments_batch(self, shipments: List[Shipment]):
        """Process multiple shipments in batch"""
        db = await get_database()
        
        # Prepare batch request
        shipment_pairs = [
            (s.tracking_number, s.carrier_code)
            for s in shipments
        ]
        
        try:
            async with await get_tracking_api() as api:
                # Batch get tracking info
                results = await api.batch_get_tracking_info(shipment_pairs)
                
                # Process each result
                for shipment in shipments:
                    tracking_data = results.get(shipment.tracking_number)
                    
                    if tracking_data:
                        await self._process_single_shipment(
                            shipment,
                            tracking_data,
                            api
                        )
                    else:
                        # No data returned, schedule next check
                        await self._schedule_next_check(shipment, no_data=True)
        
        except RateLimitError:
            logger.warning("API rate limit exceeded, will retry later")
            # Schedule all shipments for retry in 5 minutes
            for shipment in shipments:
                shipment.next_check_at = datetime.utcnow() + timedelta(minutes=5)
                await db.update_shipment(shipment)
        
        except TrackingAPIError as e:
            logger.error(f"API error during batch processing: {e}")
    
    async def _process_single_shipment(
        self,
        shipment: Shipment,
        tracking_data: dict,
        api
    ):
        """Process tracking update for a single shipment"""
        db = await get_database()
        
        # Parse the response
        new_event, new_hash = api.parse_tracking_response(tracking_data)
        
        if not new_event:
            # No events found
            await self._schedule_next_check(shipment, no_data=True)
            return
        
        # Check if event has changed
        if new_hash != shipment.last_event_hash:
            # Status has changed!
            logger.info(f"Status changed for {shipment.tracking_number}: {new_event.status_norm}")
            
            # Update shipment
            old_event = shipment.last_event
            shipment.last_event = new_event
            shipment.last_event_hash = new_hash
            shipment.last_check_at = datetime.utcnow()
            
            # Check if delivered
            if new_event.status_norm == StatusNorm.DELIVERED:
                await db.archive_shipment(shipment.id)
                shipment.state = ShipmentState.ARCHIVED
                shipment.delivered_at = datetime.utcnow()
            else:
                # Schedule next check based on status
                await self._schedule_next_check(shipment)
            
            await db.update_shipment(shipment)
            
            # Save event to history (optional)
            await db.add_shipment_event(shipment.id, new_event.to_dict())
            
            # Send notifications
            await self._send_notifications(shipment, old_event, new_event)
        
        else:
            # No change, just update check time
            shipment.last_check_at = datetime.utcnow()
            await self._schedule_next_check(shipment)
            await db.update_shipment(shipment)
    
    async def _schedule_next_check(self, shipment: Shipment, no_data: bool = False):
        """
        Calculate next check time based on shipment status
        Implements smart polling intervals
        """
        if no_data:
            # If no data, retry in 1 hour
            shipment.next_check_at = datetime.utcnow() + timedelta(hours=1)
            return
        
        if not shipment.last_event:
            # No event yet, check frequently
            shipment.next_check_at = datetime.utcnow() + timedelta(hours=2)
            return
        
        status = shipment.last_event.status_norm
        
        # Smart intervals based on status
        if status == StatusNorm.OUT_FOR_DELIVERY:
            # Check every 10-20 minutes when out for delivery
            interval = timedelta(minutes=15)
        
        elif status in [StatusNorm.ARRIVED_DESTINATION, StatusNorm.CUSTOMS]:
            # Check every 1-2 hours at destination or customs
            interval = timedelta(hours=1.5)
        
        elif status in [StatusNorm.IN_TRANSIT, StatusNorm.ARRIVED_SORTING_CENTER]:
            # Check every 4-6 hours when in transit
            interval = timedelta(hours=5)
        
        elif status == StatusNorm.EXCEPTION:
            # Check every hour for exceptions
            interval = timedelta(hours=1)
        
        elif status == StatusNorm.INFO_RECEIVED:
            # Check every 6 hours when only info received
            interval = timedelta(hours=6)
        
        else:
            # Default: check every 4 hours
            interval = timedelta(hours=4)
        
        shipment.next_check_at = datetime.utcnow() + interval
    
    async def _send_notifications(
        self,
        shipment: Shipment,
        old_event,
        new_event
    ):
        """Send notifications to all subscribers"""
        db = await get_database()
        
        # Get all non-muted subscribers
        subscribers = await db.get_shipment_subscribers(
            shipment.id,
            include_muted=False
        )
        
        if not subscribers:
            return
        
        # Build notification message
        message = self._build_notification_message(
            shipment,
            old_event,
            new_event
        )
        
        # Send to each subscriber
        for subscription in subscribers:
            try:
                await self.bot.send_message(
                    chat_id=subscription.user_id,
                    text=message,
                    parse_mode='HTML'
                )
                logger.info(f"Sent notification to user {subscription.user_id}")
            
            except Exception as e:
                logger.error(f"Failed to send notification to {subscription.user_id}: {e}")
    
    def _build_notification_message(
        self,
        shipment: Shipment,
        old_event,
        new_event
    ) -> str:
        """Build Hebrew notification message"""
        from models import STATUS_TRANSLATIONS_HE
        
        # Get subscription for item name
        # (We'll need to pass this differently in production)
        item_name = "החבילה שלך"  # Default
        
        # Status emoji
        emoji = self._get_status_emoji(new_event.status_norm)
        
        # Build message
        lines = [
            f"{emoji} <b>עדכון עבור: {item_name}</b>",
            "",
            f"📦 מספר מעקב: <code>{shipment.tracking_number}</code>",
            "",
            f"✅ <b>סטטוס חדש:</b> {STATUS_TRANSLATIONS_HE.get(new_event.status_norm, 'לא ידוע')}",
        ]
        
        # Add raw status if different
        if new_event.status_raw:
            lines.append(f"📝 {new_event.status_raw}")
        
        # Add location if available
        if new_event.location:
            lines.append(f"📍 מיקום: {new_event.location}")
        
        # Add timestamp
        if new_event.timestamp:
            time_str = new_event.timestamp.strftime("%d/%m/%Y %H:%M")
            lines.append(f"🕐 זמן: {time_str}")
        
        # Special message for delivery
        if new_event.status_norm == StatusNorm.DELIVERED:
            lines.append("")
            lines.append("🎉 <b>החבילה נמסרה בהצלחה!</b>")
            lines.append("המעקב הועבר לארכיון.")
        
        return "\n".join(lines)
    
    def _get_status_emoji(self, status: StatusNorm) -> str:
        """Get emoji for status"""
        emoji_map = {
            StatusNorm.INFO_RECEIVED: "ℹ️",
            StatusNorm.IN_TRANSIT: "✈️",
            StatusNorm.ARRIVED_SORTING_CENTER: "📬",
            StatusNorm.ARRIVED_DESTINATION: "🏠",
            StatusNorm.CUSTOMS: "🛃",
            StatusNorm.OUT_FOR_DELIVERY: "🚚",
            StatusNorm.DELIVERED: "✅",
            StatusNorm.EXCEPTION: "⚠️",
            StatusNorm.EXPIRED: "⏰",
            StatusNorm.UNKNOWN: "❓"
        }
        return emoji_map.get(status, "📦")
