from aiogram import Dispatcher

from app.bot.handlers import setup_handlers


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    setup_handlers(dp)
    return dp

