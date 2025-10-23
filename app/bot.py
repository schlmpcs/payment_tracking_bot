from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import TelegramConfig
from app.routers import admin_router, user_router
from app.routers.users.admin import db


cfg = TelegramConfig()
storage = MemoryStorage()

bot = Bot(token=cfg.token.get_secret_value())
dp = Dispatcher(storage=storage)
dp.include_routers(admin_router, user_router)


async def main():
    print("🤖 Starting Spotify Payment Bot...")
    
    # Try to connect to database
    if await db.connect():
        print("📊 Database connected, initializing tables...")
        if await db.initialize():
            print("✅ Database tables initialized successfully!")
        else:
            print("⚠️  Database table initialization failed, but continuing...")
    else:
        print("⚠️  Database connection failed - bot will start but database features won't work")
        print("💡 Check your database credentials and try restarting the bot later")
    
    print("🚀 Starting bot polling...")
    await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
