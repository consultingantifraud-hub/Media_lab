from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Update, ErrorEvent
from loguru import logger

from app.bot.handlers import setup_handlers


async def error_handler(event: ErrorEvent) -> bool:
    """Глобальный обработчик ошибок для всех обработчиков бота."""
    exception = event.exception
    update = event.update
    if (
        isinstance(exception, TelegramBadRequest)
        and "message is not modified" in str(exception)
    ):
        logger.debug("TelegramBadRequest ignored: {}", exception)
        return True
    
    # Логируем ошибку
    logger.error(
        "Unhandled exception in bot handler: {}",
        exception,
        exc_info=exception,
    )
    
    # Пытаемся отправить сообщение пользователю, если это возможно
    try:
        if update.message:
            chat_id = update.message.chat.id
            error_text = (
                "❌ Произошла ошибка при обработке запроса.\n\n"
                "Пожалуйста, попробуйте еще раз или обратитесь в поддержку, если проблема повторяется."
            )
            await update.message.answer(error_text)
        elif update.callback_query:
            await update.callback_query.answer(
                "❌ Произошла ошибка. Попробуйте еще раз.",
                show_alert=True
            )
    except Exception as send_error:
        logger.error("Failed to send error notification to user: {}", send_error, exc_info=True)


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    # Регистрируем глобальный обработчик ошибок
    dp.errors.register(error_handler)
    setup_handlers(dp)
    return dp

