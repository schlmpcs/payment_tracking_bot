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
from aiogram.types import BotCommand, BotCommandScopeDefault, BotCommandScopeChat

from bot.config.settings import Settings
from bot.database.operations import Database
from bot.handlers.user import user_router, init_user_handlers
from bot.handlers.admin import admin_router, init_admin_handlers
from bot.utils.notifications import NotificationScheduler


USER_COMMANDS = [
    BotCommand(command="start",   description="Start the bot"),
    BotCommand(command="status",  description="Check your payment status"),
    BotCommand(command="pay",     description="Submit a payment receipt"),
    BotCommand(command="join",    description="Join a payment group"),
    BotCommand(command="history", description="View payment history"),
    BotCommand(command="help",    description="Show available commands"),
    BotCommand(command="id",      description="Show your Telegram ID"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="admin",                  description="Open admin panel"),
    BotCommand(command="broadcast",              description="Send a message to users"),
    BotCommand(command="overdue",                description="Show overdue users"),
    BotCommand(command="notfull",                description="Show groups with open slots"),
    BotCommand(command="paid_in_advance",        description="Show users paid far ahead"),
    BotCommand(command="update_due_date",        description="Change a group's payment date"),
    BotCommand(command="setslots",               description="Set user slot count in a group"),
    BotCommand(command="link_group",             description="Link Telegram chat to a group"),
    BotCommand(command="import_groups",          description="Import groups from Excel file"),
    BotCommand(command="fraudcheck",             description="KZ payment reconciliation"),
    BotCommand(command="fraudcheck_ru",          description="RU payment reconciliation"),
    BotCommand(command="backfill_receipts",      description="Extract operation numbers from past receipts"),
    BotCommand(command="fixusers",               description="Fix corrupted user names"),
    BotCommand(command="test_notifications",     description="Send test reminders to all users"),
    BotCommand(command="check_notifications",    description="Check notification system"),
    BotCommand(command="adminhelp",              description="Show all admin commands"),
]


async def setup_bot_commands(bot: Bot, settings) -> None:
    """Set the bot command menu visible in the Telegram UI (left-side '/' menu)."""
    # Default menu for all users
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())

    # Per-admin override: admins see the full command list
    for admin_id in settings.tg_admin_ids:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception:
            pass  # Admin may not have started the bot yet


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

    # Initialize notification scheduler
    scheduler = None
    if db and db.pool:
        scheduler = NotificationScheduler(bot, db, settings)
        await scheduler.start()
        logger.info("🔔 Payment notification system started")
    else:
        logger.warning(
            "⚠️ Notification system disabled - database not available")

    # Set bot command menus
    await setup_bot_commands(bot, settings)
    logger.info("✅ Bot command menus configured")

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
