#!/usr/bin/env python3
"""
Spotify Family Payment Bot - Main Entry Point

A Telegram bot for managing Spotify family subscription payments.
Users can upload payment receipts, check payment status, and admins can manage groups.
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config.settings import Settings
from bot.database.operations import Database
from bot.handlers.user import user_router, init_user_handlers
from bot.handlers.admin import admin_router, init_admin_handlers
from bot.handlers.buy import buy_router, init_buy_handlers
from bot.utils.notifications import NotificationScheduler


async def main():
    """Main bot function"""

    # Load configuration
    settings = Settings()

    # Setup logging
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    # Force UTF-8 encoding for console output on Windows
    if sys.platform == 'win32':
        sys.stdout.reconfigure(encoding='utf-8')
    logger = logging.getLogger(__name__)

    # Initialize bot and dispatcher
    bot = Bot(token=settings.tg_token.get_secret_value())
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Include routers
    dp.include_router(admin_router)
    dp.include_router(buy_router)
    dp.include_router(user_router)

    logger.info("🤖 Starting Spotify Payment Bot...")

    # Initialize database
    db = Database(settings)
    try:
        if await db.connect():
            logger.info("✅ Database connected successfully")
            if await db.initialize_tables():
                logger.info("✅ Database tables initialized")
            else:
                logger.warning("⚠️ Database table initialization failed")
        else:
            logger.error(
                "❌ Database connection failed - continuing without database")
    except Exception as e:
        logger.error(f"❌ Database error: {e}")
        logger.info("🔄 Bot will continue without database functionality")

    # Initialize handlers with database and settings
    init_user_handlers(db, settings)
    init_admin_handlers(db, settings)
    init_buy_handlers(db, settings)

    # Initialize notification scheduler
    scheduler = None
    if db and db.pool:
        scheduler = NotificationScheduler(bot, db, settings)
        await scheduler.start()
        logger.info("🔔 Payment notification system started")

        # Catch any missed 24h unpaid checks from before restart
        await scheduler.check_unpaid_on_startup()
    else:
        logger.warning(
            "⚠️ Notification system disabled - database not available")

    try:
        logger.info("🚀 Starting bot polling...")
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    finally:
        # Cleanup
        if scheduler:
            await scheduler.stop()
        await bot.session.close()
        if 'db' in locals():
            await db.close()


if __name__ == "__main__":
    asyncio.run(main())
