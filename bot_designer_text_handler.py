from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile
from loguru import logger

from app.bot.keyboards.main import build_main_keyboard, IMAGE_DESIGNER_TEXT_BUTTON
from app.core.config import reload_settings
from app.providers.wavespeed.client import wavespeed_designer_text

# Ключи для FSM состояния
DESIGNER_TEXT_KEY = "designer_text"
DESIGNER_POSITION_KEY = "designer_position"
DESIGNER_IMAGE_PATH_KEY = "designer_image_path"

# Позиции текста
POSITION_TOP = "top"
POSITION_BOTTOM = "bottom"
POSITION_CENTER = "center"
POSITION_TOP_LEFT = "top_left"
POSITION_TOP_RIGHT = "top_right"
POSITION_BOTTOM_LEFT = "bottom_left"
POSITION_BOTTOM_RIGHT = "bottom_right"


class DesignerTextStates(StatesGroup):
    waiting_text = State()
    waiting_position = State()
    waiting_image = State()


def build_position_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора позиции текста."""
    buttons = [
        [
            InlineKeyboardButton(text="Сверху", callback_data=f"position_{POSITION_TOP}"),
            InlineKeyboardButton(text="Снизу", callback_data=f"position_{POSITION_BOTTOM}"),
        ],
        [
            InlineKeyboardButton(text="По центру", callback_data=f"position_{POSITION_CENTER}"),
        ],
        [
            InlineKeyboardButton(text="Верхний левый", callback_data=f"position_{POSITION_TOP_LEFT}"),
            InlineKeyboardButton(text="Верхний правый", callback_data=f"position_{POSITION_TOP_RIGHT}"),
        ],
        [
            InlineKeyboardButton(text="Нижний левый", callback_data=f"position_{POSITION_BOTTOM_LEFT}"),
            InlineKeyboardButton(text="Нижний правый", callback_data=f"position_{POSITION_BOTTOM_RIGHT}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def generate_designer_prompt(user_text: str, position: str) -> str:
    """
    Генерирует промпт для FLUX Kontext на основе текста и позиции.
    
    Args:
        user_text: Текст пользователя (на русском, с эмодзи)
        position: Позиция текста (top, bottom, center, top_left, etc.)
    
    Returns:
        Англоязычный промпт для модели
    """
    # Базовые шаблоны для разных позиций
    position_templates = {
        POSITION_BOTTOM: """CRITICAL: This is a LOCAL EDIT operation. You must ONLY modify the bottom 20% area of the image where the text banner will be placed. DO NOT regenerate, redraw, or modify ANY other part of the image.

TASK: Add ONLY a text banner overlay at the BOTTOM CENTER of the image, inside the bottom 20% of the image height.

STRICT PRESERVATION RULES:
- Keep 100% of the original image content ABOVE the bottom 20% area completely unchanged
- Do NOT regenerate, redraw, or modify any objects, people, backgrounds, colors, lighting, or composition outside the text banner area
- Do NOT change the style, atmosphere, or artistic quality of the original image
- The text banner should be a simple overlay that does not affect the rest of the image

TEXT BANNER SPECIFICATIONS:
- Position: Bottom center, inside bottom 20% of image height
- Style: Clean, modern rectangular bar with softly rounded corners
- Background: Slightly transparent dark rectangular bar (semi-transparent overlay)
- Text color: White
- Font: Bold sans-serif that supports Cyrillic characters
- Width: Spans most of the image width (80-90%)

CYRILLIC TEXT INSTRUCTIONS:
- Write the following Russian Cyrillic text EXACTLY as provided below
- The text contains Russian Cyrillic characters (А-Я, а-я, Ё, ё, numbers, punctuation, emojis)
- You MUST render ALL Cyrillic letters EXACTLY as provided, preserving their exact shape and form
- DO NOT replace Cyrillic letters with Latin letters (e.g., do not replace А with A, Р with P, О with O)
- DO NOT transliterate: keep Russian letters as Russian letters
- DO NOT translate the text to English
- Preserve ALL characters, spacing, punctuation, and emojis EXACTLY as given
- The text must be clearly readable with proper Cyrillic font rendering

TEXT TO ADD (Russian Cyrillic):

"{USER_TEXT}"

REMEMBER: Only edit the bottom 20% area. Everything else must remain 100% identical to the original image.""",

        POSITION_TOP: """CRITICAL: This is a LOCAL EDIT operation. You must ONLY modify the top 20% area of the image where the text banner will be placed. DO NOT regenerate, redraw, or modify ANY other part of the image.

TASK: Add ONLY a text banner overlay at the TOP CENTER of the image, inside the top 20% of the image height.

STRICT PRESERVATION RULES:
- Keep 100% of the original image content BELOW the top 20% area completely unchanged
- Do NOT regenerate, redraw, or modify any objects, people, backgrounds, colors, lighting, or composition outside the text banner area
- Do NOT change the style, atmosphere, or artistic quality of the original image
- The text banner should be a simple overlay that does not affect the rest of the image

TEXT BANNER SPECIFICATIONS:
- Position: Top center, inside top 20% of image height
- Style: Clean, modern rectangular bar with softly rounded corners
- Background: Slightly transparent dark rectangular bar (semi-transparent overlay)
- Text color: White
- Font: Bold sans-serif that supports Cyrillic characters

CYRILLIC TEXT INSTRUCTIONS:
- Write the following Russian Cyrillic text EXACTLY as provided below
- The text contains Russian Cyrillic characters (А-Я, а-я, Ё, ё, numbers, punctuation, emojis)
- You MUST render ALL Cyrillic letters EXACTLY as provided, preserving their exact shape and form
- DO NOT replace Cyrillic letters with Latin letters
- DO NOT transliterate: keep Russian letters as Russian letters
- DO NOT translate the text to English
- Preserve ALL characters, spacing, punctuation, and emojis EXACTLY as given

TEXT TO ADD (Russian Cyrillic):

"{USER_TEXT}"

REMEMBER: Only edit the top 20% area. Everything else must remain 100% identical to the original image.""",

        POSITION_CENTER: """CRITICAL: This is a LOCAL EDIT operation. You must ONLY modify a small area in the CENTER of the image where the text banner will be placed. DO NOT regenerate, redraw, or modify ANY other part of the image.

TASK: Add ONLY a text banner overlay in the CENTER of the image, without covering the main subject if possible.

STRICT PRESERVATION RULES:
- Keep 100% of the original image content OUTSIDE the text banner area completely unchanged
- Do NOT regenerate, redraw, or modify any objects, people, backgrounds, colors, lighting, or composition outside the text banner area
- Do NOT change the style, atmosphere, or artistic quality of the original image
- The text banner should be a simple overlay that does not affect the rest of the image

TEXT BANNER SPECIFICATIONS:
- Position: Center of the image
- Style: Clean, modern rectangular bar with softly rounded corners
- Background: Slightly transparent dark rectangular bar (semi-transparent overlay)
- Text color: White
- Font: Bold sans-serif that supports Cyrillic characters

CYRILLIC TEXT INSTRUCTIONS:
- Write the following Russian Cyrillic text EXACTLY as provided below
- The text contains Russian Cyrillic characters (А-Я, а-я, Ё, ё, numbers, punctuation, emojis)
- You MUST render ALL Cyrillic letters EXACTLY as provided, preserving their exact shape and form
- DO NOT replace Cyrillic letters with Latin letters
- DO NOT transliterate: keep Russian letters as Russian letters
- DO NOT translate the text to English
- Preserve ALL characters, spacing, punctuation, and emojis EXACTLY as given

TEXT TO ADD (Russian Cyrillic):

"{USER_TEXT}"

REMEMBER: Only edit the small center area where the banner is placed. Everything else must remain 100% identical to the original image.""",

        POSITION_TOP_LEFT: """Add a clean, modern text banner at the TOP LEFT corner of the image,
inside the top 20% of the image height and left 30% of the image width.

Inside this banner, write the following Russian Cyrillic text EXACTLY as provided below.
CRITICAL INSTRUCTIONS FOR CYRILLIC TEXT:
- The text contains Russian Cyrillic characters (А-Я, а-я, Ё, ё, numbers, punctuation, emojis)
- You MUST render ALL Cyrillic letters EXACTLY as provided, preserving their exact shape and form
- DO NOT replace Cyrillic letters with Latin letters that look similar (e.g., do not replace А with A, Р with P, О with O)
- DO NOT transliterate: keep Russian letters as Russian letters
- DO NOT translate the text to English
- Preserve ALL characters, spacing, punctuation, and emojis EXACTLY as given
- The text must be clearly readable with proper Cyrillic font rendering
- Use a font that properly supports Cyrillic characters

Write this text EXACTLY as shown below (it is in Russian Cyrillic):

"{USER_TEXT}"

Use bold sans-serif letters, white text on a slightly transparent dark rectangular bar
with softly rounded corners.

Keep everything else in the original image completely unchanged.""",

        POSITION_TOP_RIGHT: """CRITICAL: This is a LOCAL EDIT operation. You must ONLY modify the top-right corner area (top 20% height, right 30% width) where the text banner will be placed. DO NOT regenerate, redraw, or modify ANY other part of the image.

TASK: Add ONLY a text banner overlay at the TOP RIGHT corner, inside the top 20% of image height and right 30% of image width.

STRICT PRESERVATION RULES:
- Keep 100% of the original image content OUTSIDE the top-right corner area completely unchanged
- Do NOT regenerate, redraw, or modify any objects, people, backgrounds, colors, lighting, or composition outside the text banner area
- Do NOT change the style, atmosphere, or artistic quality of the original image
- The text banner should be a simple overlay that does not affect the rest of the image

TEXT BANNER SPECIFICATIONS:
- Position: Top right corner (top 20% height, right 30% width)
- Style: Clean, modern rectangular bar with softly rounded corners
- Background: Slightly transparent dark rectangular bar
- Text color: White
- Font: Bold sans-serif that supports Cyrillic characters

CYRILLIC TEXT INSTRUCTIONS:
- Write the following Russian Cyrillic text EXACTLY as provided below
- Preserve ALL Cyrillic letters, characters, spacing, punctuation, and emojis EXACTLY as given
- DO NOT replace Cyrillic letters with Latin letters
- DO NOT transliterate or translate

TEXT TO ADD (Russian Cyrillic):

"{USER_TEXT}"

REMEMBER: Only edit the top-right corner area. Everything else must remain 100% identical to the original image.""",

        POSITION_BOTTOM_LEFT: """CRITICAL: This is a LOCAL EDIT operation. You must ONLY modify the bottom-left corner area (bottom 20% height, left 30% width) where the text banner will be placed. DO NOT regenerate, redraw, or modify ANY other part of the image.

TASK: Add ONLY a text banner overlay at the BOTTOM LEFT corner, inside the bottom 20% of image height and left 30% of image width.

STRICT PRESERVATION RULES:
- Keep 100% of the original image content OUTSIDE the bottom-left corner area completely unchanged
- Do NOT regenerate, redraw, or modify any objects, people, backgrounds, colors, lighting, or composition outside the text banner area
- Do NOT change the style, atmosphere, or artistic quality of the original image
- The text banner should be a simple overlay that does not affect the rest of the image

TEXT BANNER SPECIFICATIONS:
- Position: Bottom left corner (bottom 20% height, left 30% width)
- Style: Clean, modern rectangular bar with softly rounded corners
- Background: Slightly transparent dark rectangular bar
- Text color: White
- Font: Bold sans-serif that supports Cyrillic characters

CYRILLIC TEXT INSTRUCTIONS:
- Write the following Russian Cyrillic text EXACTLY as provided below
- Preserve ALL Cyrillic letters, characters, spacing, punctuation, and emojis EXACTLY as given
- DO NOT replace Cyrillic letters with Latin letters
- DO NOT transliterate or translate

TEXT TO ADD (Russian Cyrillic):

"{USER_TEXT}"

REMEMBER: Only edit the bottom-left corner area. Everything else must remain 100% identical to the original image.""",

        POSITION_BOTTOM_RIGHT: """CRITICAL: This is a LOCAL EDIT operation. You must ONLY modify the bottom-right corner area (bottom 20% height, right 30% width) where the text banner will be placed. DO NOT regenerate, redraw, or modify ANY other part of the image.

TASK: Add ONLY a text banner overlay at the BOTTOM RIGHT corner, inside the bottom 20% of image height and right 30% of image width.

STRICT PRESERVATION RULES:
- Keep 100% of the original image content OUTSIDE the bottom-right corner area completely unchanged
- Do NOT regenerate, redraw, or modify any objects, people, backgrounds, colors, lighting, or composition outside the text banner area
- Do NOT change the style, atmosphere, or artistic quality of the original image
- The text banner should be a simple overlay that does not affect the rest of the image

TEXT BANNER SPECIFICATIONS:
- Position: Bottom right corner (bottom 20% height, right 30% width)
- Style: Clean, modern rectangular bar with softly rounded corners
- Background: Slightly transparent dark rectangular bar
- Text color: White
- Font: Bold sans-serif that supports Cyrillic characters

CYRILLIC TEXT INSTRUCTIONS:
- Write the following Russian Cyrillic text EXACTLY as provided below
- Preserve ALL Cyrillic letters, characters, spacing, punctuation, and emojis EXACTLY as given
- DO NOT replace Cyrillic letters with Latin letters
- DO NOT transliterate or translate

TEXT TO ADD (Russian Cyrillic):

"{USER_TEXT}"

REMEMBER: Only edit the bottom-right corner area. Everything else must remain 100% identical to the original image.""",
    }
    
    template = position_templates.get(position, position_templates[POSITION_CENTER])
    return template.format(USER_TEXT=user_text)


async def handle_designer_text_start(message: types.Message, state: FSMContext) -> None:
    """Начало режима Дизайнерский текст."""
    logger.info("Designer text mode started by user {}", message.from_user.id if message.from_user else "unknown")
    await state.clear()
    await state.set_state(DesignerTextStates.waiting_text)
    await state.update_data({
        DESIGNER_TEXT_KEY: None,
        DESIGNER_POSITION_KEY: None,
        DESIGNER_IMAGE_PATH_KEY: None,
    })
    await message.answer(
        "🧩 Режим «Дизайнерский текст»\n\n"
        "⚠️ Экспериментальный режим, который использует внешнюю модель FLUX Kontext.\n"
        "Кириллица может отображаться некорректно — тестируем качество.\n\n"
        "1️⃣ Напишите текст надписи на русском (можно использовать эмодзи).",
        reply_markup=build_main_keyboard(),
    )


async def handle_designer_text_input(message: types.Message, state: FSMContext) -> None:
    """Обработка введенного текста."""
    current_state = await state.get_state()
    if current_state != DesignerTextStates.waiting_text.state:
        return
    
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение с надписью.")
        return
    
    text = message.text.strip()
    if not text:
        await message.answer("Текст не может быть пустым. Введите надпись.")
        return
    
    await state.update_data({DESIGNER_TEXT_KEY: text})
    await state.set_state(DesignerTextStates.waiting_position)
    
    await message.answer(
        "2️⃣ Выберите, где разместить текст:",
        reply_markup=build_position_keyboard(),
    )


async def handle_designer_position_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Обработка выбора позиции текста."""
    current_state = await state.get_state()
    if current_state != DesignerTextStates.waiting_position.state:
        await callback.answer("Неверное состояние. Начните заново.")
        return
    
    # Извлекаем позицию из callback_data
    if not callback.data or not callback.data.startswith("position_"):
        await callback.answer("Ошибка выбора позиции.")
        return
    
    position = callback.data.replace("position_", "")
    
    # Проверяем, что позиция валидна
    valid_positions = {
        POSITION_TOP, POSITION_BOTTOM, POSITION_CENTER,
        POSITION_TOP_LEFT, POSITION_TOP_RIGHT,
        POSITION_BOTTOM_LEFT, POSITION_BOTTOM_RIGHT,
    }
    if position not in valid_positions:
        await callback.answer("Неверная позиция.")
        return
    
    await state.update_data({DESIGNER_POSITION_KEY: position})
    await state.set_state(DesignerTextStates.waiting_image)
    
    position_names = {
        POSITION_TOP: "сверху",
        POSITION_BOTTOM: "снизу",
        POSITION_CENTER: "по центру",
        POSITION_TOP_LEFT: "в верхнем левом углу",
        POSITION_TOP_RIGHT: "в верхнем правом углу",
        POSITION_BOTTOM_LEFT: "в нижнем левом углу",
        POSITION_BOTTOM_RIGHT: "в нижнем правом углу",
    }
    
    await callback.message.edit_text(
        f"✅ Позиция выбрана: {position_names.get(position, position)}\n\n"
        "3️⃣ Теперь отправьте изображение (фото или картинку), на которое нужно добавить надпись.",
    )
    await callback.answer()


async def handle_designer_image(message: types.Message, state: FSMContext) -> None:
    """Обработка загруженного изображения и вызов Wavespeed."""
    current_state = await state.get_state()
    if current_state != DesignerTextStates.waiting_image.state:
        return
    
    data = await state.get_data()
    text = data.get(DESIGNER_TEXT_KEY)
    position = data.get(DESIGNER_POSITION_KEY)
    
    if not text or not position:
        await message.answer("Ошибка: не найден текст или позиция. Начните заново.")
        await state.clear()
        return
    
    # Сохраняем изображение
    from app.core.config import reload_settings
    current_settings = reload_settings()
    
    image_path = current_settings.media_dir / "edits" / f"{uuid4()}_designer_source.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        if message.photo:
            file = message.photo[-1]
            await message.bot.download(file, destination=image_path)
        elif message.document:
            document = message.document
            if document.mime_type and not document.mime_type.startswith("image"):
                await message.answer("Пожалуйста, отправьте изображение (PNG/JPEG).")
                return
            await message.bot.download(document, destination=image_path)
        else:
            await message.answer("Пожалуйста, отправьте изображение.")
            return
    except Exception as e:
        logger.error("Failed to download image: {}", e)
        await message.answer("Ошибка при загрузке изображения. Попробуйте еще раз.")
        await state.clear()
        return
    
    # Генерируем промпт
    prompt = generate_designer_prompt(text, position)
    logger.info("Generated prompt for designer text: position={}, text_length={}", position, len(text))
    
    # Отправляем сообщение о начале обработки
    processing_msg = await message.answer("🔄 Обрабатываю изображение, это может занять несколько секунд...")
    
    try:
        # Используем WaveSpeedAI (который теперь использует OpenAI модели)
        logger.info("Using WaveSpeedAI (OpenAI model) for designer text")
        result_url, original_size = wavespeed_designer_text(
            image_path=image_path.as_posix(),
            prompt=prompt,
            position=position,  # Передаем позицию для создания маски
        )
        logger.info("Designer text completed successfully via WaveSpeedAI (OpenAI): {}, original_size={}", result_url[:50], original_size)
        
        # Скачиваем результат
        import httpx
        output_path = current_settings.media_dir / "edits" / f"{uuid4()}_designer_result.png"
        timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.get(result_url)
            response.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(response.content)
        
        # Восстанавливаем исходные пропорции, если изображение было квадратизировано
        if original_size:
            try:
                from PIL import Image
                with Image.open(output_path) as result_img:
                    result_size = result_img.size
                    # Если результат квадратный, а оригинал был не квадратным, обрезаем padding
                    if result_size[0] == result_size[1] and original_size[0] != original_size[1]:
                        # Вычисляем область для обрезки (убираем белый padding)
                        orig_w, orig_h = original_size
                        result_w, result_h = result_size
                        
                        # Определяем, какой padding был добавлен
                        if orig_w > orig_h:
                            # Горизонтальное изображение - padding сверху/снизу
                            crop_h = int(result_h * (orig_h / max(orig_w, orig_h)))
                            y_offset = (result_h - crop_h) // 2
                            crop_box = (0, y_offset, result_w, y_offset + crop_h)
                        else:
                            # Вертикальное изображение - padding слева/справа
                            crop_w = int(result_w * (orig_w / max(orig_w, orig_h)))
                            x_offset = (result_w - crop_w) // 2
                            crop_box = (x_offset, 0, x_offset + crop_w, result_h)
                        
                        # Обрезаем изображение
                        cropped_img = result_img.crop(crop_box)
                        # Масштабируем до исходного размера
                        cropped_img = cropped_img.resize(original_size, Image.Resampling.LANCZOS)
                        cropped_img.save(output_path, "PNG")
                        logger.info("Restored original aspect ratio: {}x{} -> {}x{}", result_size[0], result_size[1], original_size[0], original_size[1])
            except Exception as e:
                logger.warning("Failed to restore original aspect ratio: {}", e)
        
        await processing_msg.delete()
        
        # Отправляем результат
        await message.answer("✨ Готово! Текст добавлен на изображение.")
        await message.answer_document(
            FSInputFile(output_path),
            caption="🧩 Дизайнерский текст готов!",
        )
        
        logger.info("Designer text completed successfully: text_length={}, position={}", len(text), position)
        
    except Exception as e:
        logger.error("Designer text error: {}", e, exc_info=True)
        await processing_msg.delete()
        await message.answer(
            "❌ Ошибка при обработке изображения.\n\n"
            "Модель временно недоступна. Попробуйте позже или используйте стандартный режим «Добавить текст».",
            reply_markup=build_main_keyboard(),
        )
    finally:
        await state.clear()


def register_designer_text_handlers(dp: Dispatcher) -> None:
    """Регистрирует обработчики для Дизайнерский текст."""
    logger.info("Registering designer text handlers")
    
    # Начало режима
    dp.message.register(
        handle_designer_text_start,
        F.text == IMAGE_DESIGNER_TEXT_BUTTON,
    )
    
    # Обработка текста
    dp.message.register(
        handle_designer_text_input,
        StateFilter(DesignerTextStates.waiting_text),
        F.text,
    )
    
    # Обработка выбора позиции (callback)
    dp.callback_query.register(
        handle_designer_position_callback,
        StateFilter(DesignerTextStates.waiting_position),
        F.data.startswith("position_"),
    )
    
    # Обработка изображения - регистрируем с StateFilter для приоритета
    dp.message.register(
        handle_designer_image,
        StateFilter(DesignerTextStates.waiting_image),
        F.photo | F.document,
    )

