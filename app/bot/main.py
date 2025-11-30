from __future__ import annotations

import asyncio

from aiogram import Bot
from loguru import logger

from app.bot import build_dispatcher
from app.core import settings, setup_logging
from app.db.base import init_db

# Import all models to ensure they are registered with Base.metadata before init_db()
from app.db import models  # noqa: F401


async def main() -> None:
    setup_logging()
    # Initialize database on startup
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize database: {}", e, exc_info=True)
    
    bot = Bot(token=settings.tg_bot_token)
    dp = build_dispatcher()
    logger.info("Starting bot in {} mode", settings.app_env)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

