from __future__ import annotations

from aiogram import Dispatcher, types
from aiogram.filters import Command


async def cmd_ping(message: types.Message) -> None:
    await message.answer("pong 🏓")


def register_ping_handlers(dp: Dispatcher) -> None:
    dp.message.register(cmd_ping, Command("ping"))

