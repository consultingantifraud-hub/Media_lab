from __future__ import annotations

from aiogram import Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.bot.keyboards.main import build_main_keyboard

START_INSTRUCTION = (
    "👋 Привет, нажмите кнопку ниже, выберите режим:\n\n"
    "🎨 Создать — генерация изображений по тексту\n"
    "✏️ Редактировать — редактирование готового или загруженного изображения\n"
    "🔗 Объединить ➕ Добавить — объединение нескольких изображений в одну сцену\n"
    "✨ Ретушь — деликатная ретушь лица\n"
    "📝 Добавить текст — добавление текста на изображение\n"
    "🔄 Заменить лицо — замена лица на фотографии\n"
    "⬆️ Улучшить — улучшение качества изображения (Upscale)"
)


async def cmd_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(START_INSTRUCTION, reply_markup=build_main_keyboard())


def register_start_handlers(dp: Dispatcher) -> None:
    dp.message.register(cmd_start, Command("start"))

