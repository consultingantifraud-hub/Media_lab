from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot
from loguru import logger

from app.bot import build_dispatcher
from app.core import settings, setup_logging
from app.db.base import init_db
from app.services.payment import PaymentService, PAYMENT_RECONCILE_INTERVAL_SECONDS

# Import all models to ensure they are registered with Base.metadata before init_db()
from app.db import models  # noqa: F401


def _log_reconcile_task_exit(task: asyncio.Task) -> None:
    try:
        task.result()
        logger.warning("Payment reconciliation loop stopped without error")
    except asyncio.CancelledError:
        logger.info("Payment reconciliation loop task cancelled")
    except Exception as exc:
        logger.exception("Payment reconciliation loop crashed: %s", exc)


async def _payment_reconciliation_loop() -> None:
    """Background task that re-checks pending payments."""
    interval = max(5, PAYMENT_RECONCILE_INTERVAL_SECONDS)
    logger.info("Payment reconciliation loop started (interval=%ss)", interval)
    idle_elapsed = 0
    while True:
        try:
            stats = await asyncio.to_thread(PaymentService.reconcile_pending_payments)
            logger.info(
                (
                    "reconcile scanned={} processed={} succeeded={} canceled={} "
                    "credited={} stale={} errors={}"
                ),
                stats["scanned"],
                stats["processed"],
                stats["succeeded"],
                stats["canceled"],
                stats["credited"],
                stats["stale"],
                stats["errors"],
            )
            if stats["processed"] == 0:
                idle_elapsed += interval
                if idle_elapsed >= max(60, interval):
                    logger.info("reconcile heartbeat idle_for={}s", idle_elapsed)
                    idle_elapsed = 0
            else:
                idle_elapsed = 0
        except asyncio.CancelledError:
            logger.info("Payment reconciliation loop cancelled")
            raise
        except Exception as exc:
            logger.exception("Payment reconciliation loop failed: %s", exc)
        await asyncio.sleep(interval)


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
    reconcile_task = asyncio.create_task(_payment_reconciliation_loop())
    reconcile_task.add_done_callback(_log_reconcile_task_exit)
    try:
        await dp.start_polling(bot)
    finally:
        reconcile_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reconcile_task


if __name__ == "__main__":
    asyncio.run(main())

