"""
Main Application Entry Point
Initializes and runs the Telegram bot with all components
"""
import logging
import asyncio
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

from config import get_config
from database import get_database
from scheduler import ShipmentScheduler
import bot_handlers
import bot_handlers_extra

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application: Application):
    """Post initialization hook"""
    logger.info("Bot initialized successfully")


async def post_shutdown(application: Application):
    """Post shutdown hook"""
    logger.info("Bot shutting down...")
    
    # Close database connection
    db = await get_database()
    await db.disconnect()


def setup_handlers(application: Application):
    """Setup all command and callback handlers"""
    
    # Command handlers
    application.add_handler(CommandHandler("start", bot_handlers.start_command))
    application.add_handler(CommandHandler("help", bot_handlers.help_command))
    application.add_handler(CommandHandler("add", bot_handlers.add_command))
    application.add_handler(CommandHandler("list", bot_handlers.list_command))
    application.add_handler(CommandHandler("archive", bot_handlers.archive_command))
    application.add_handler(CommandHandler("refresh", bot_handlers_extra.refresh_command))
    application.add_handler(CommandHandler("mute", bot_handlers_extra.mute_command))
    application.add_handler(CommandHandler("remove", bot_handlers_extra.remove_command))
    
    # Callback query handlers
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers.carrier_selection_callback,
            pattern=r"^select_carrier:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers.restore_callback,
            pattern=r"^restore:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers_extra.refresh_callback,
            pattern=r"^refresh:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers_extra.mute_callback,
            pattern=r"^mute:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers_extra.remove_callback,
            pattern=r"^remove:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers_extra.archive_callback,
            pattern=r"^archive:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers_extra.edit_name_callback,
            pattern=r"^edit_name:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers_extra.prompt_for_name_callback,
            pattern=r"^prompt_name:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers_extra.skip_name_callback,
            pattern=r"^skip_name$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers_extra.shipment_details_callback,
            pattern=r"^shipment_details:"
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            bot_handlers_extra.back_to_list_callback,
            pattern=r"^back_to_list$"
        )
    )

    # Button handler for main menu buttons (must be before message_handler)
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^(📦 המשלוחים שלי|🔄 רענן משלוח|📫 ארכיון|🔕 השתק התראות|❓ עזרה)$"),
            bot_handlers.button_handler
        )
    )

    # Message handler for tracking numbers
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            bot_handlers_extra.message_handler
        )
    )

    logger.info("Handlers registered")


async def main():
    """Main application function"""
    try:
        # Load configuration
        config = get_config()
        logger.info(f"Starting Shipment Tracker Bot (Environment: {config.app.environment})")
        
        # Initialize database
        db = await get_database()
        logger.info("Database connected")
        
        # Create application
        application = (
            Application.builder()
            .token(config.telegram.bot_token)
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .build()
        )
        
        # Setup handlers
        setup_handlers(application)
        
        # Initialize scheduler
        scheduler = ShipmentScheduler(application.bot)
        scheduler.start()
        logger.info("Scheduler started")
        
        # Start the bot
        logger.info("Starting bot polling...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            allowed_updates=["message", "callback_query"]
        )
        
        logger.info("✅ Bot is running!")
        
        # Keep the bot running
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            # Cleanup
            scheduler.stop()
            await application.updater.stop()
            await application.stop()
            await application.shutdown()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Application crashed: {e}", exc_info=True)
