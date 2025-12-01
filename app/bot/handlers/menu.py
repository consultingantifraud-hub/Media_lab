from __future__ import annotations

from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.bot.handlers.start import START_INSTRUCTION, INFO_INSTRUCTION
from app.bot.keyboards.main import INFO_BUTTON, build_main_keyboard


async def cmd_menu(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        START_INSTRUCTION,
        reply_markup=build_main_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


async def handle_info(message: types.Message, state: FSMContext) -> None:
    """Обработчик кнопки Info - показывает инструкцию."""
    await state.clear()
    await message.answer(
        INFO_INSTRUCTION,
        reply_markup=build_main_keyboard(),
        parse_mode="Markdown"
    )


def register_menu_handlers(dp: Dispatcher) -> None:
    from app.bot.handlers.image import _match_button
    
    dp.message.register(cmd_menu, Command("menu"))
    dp.message.register(handle_info, _match_button(INFO_BUTTON))

