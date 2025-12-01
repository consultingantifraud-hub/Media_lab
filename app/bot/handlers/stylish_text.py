from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from loguru import logger
from PIL import Image

from app.bot.keyboards.main import build_main_keyboard, IMAGE_STYLISH_TEXT_BUTTON
from app.core.style_llm import wish_to_params_async
from app.core.text_render import render_text_box

# Ключи для FSM состояния
STYLISH_STAGE_KEY = "stylish_stage"
STYLISH_SOURCE_PATH_KEY = "stylish_source_path"
STYLISH_TEXT_KEY = "stylish_text"
STYLISH_HINT_KEY = "stylish_hint"

# Стадии обработки
STAGE_WAIT_IMAGE = "wait_image"
STAGE_WAIT_TEXT = "wait_text"
STAGE_WAIT_HINT = "wait_hint"


async def handle_stylish_start(message: types.Message, state: FSMContext) -> None:
    """Начало режима Stylish text - запрашиваем изображение."""
    logger.info("Stylish text mode started by user {}, text='{}'", 
                message.from_user.id if message.from_user else "unknown",
                message.text)
    await state.clear()  # Очищаем предыдущее состояние
    await state.update_data({STYLISH_STAGE_KEY: STAGE_WAIT_IMAGE})
    logger.debug("Stylish text stage set to: {}", STAGE_WAIT_IMAGE)
    await message.answer(
        "📝 Добавление текста на изображение\n\n"
        "📸 Отправьте изображение, на которое нужно добавить текст.\n\n"
        "💡 **Простая вставка текста:**\n"
        "Эта функция предназначена для простой вставки текста, указанного пользователем.\n\n"
        "🎨 **Для дизайнерского оформления:**\n"
        "Если нужно дизайнерское оформление текста на готовом изображении, используйте кнопку «✏️ Изменить» и выберите модель **Nano Banana Pro**.",
        reply_markup=build_main_keyboard(),
        parse_mode="Markdown",
    )


async def handle_stylish_media(message: types.Message, state: FSMContext) -> None:
    """Обработка загруженного изображения."""
    data = await state.get_data()
    stage = data.get(STYLISH_STAGE_KEY)
    
    logger.debug(
        "handle_stylish_media called: user={}, stage={}, expected={}",
        message.from_user.id if message.from_user else "unknown",
        stage,
        STAGE_WAIT_IMAGE,
    )
    
    if stage != STAGE_WAIT_IMAGE:
        logger.debug("handle_stylish_media: stage mismatch, skipping (allowing next handler)")
        return
    
    # Сохраняем изображение
    from app.core.config import settings
    
    image_path = settings.media_dir / "images" / f"{uuid4()}_source.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    
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
    
    await state.update_data(
        {
            STYLISH_STAGE_KEY: STAGE_WAIT_TEXT,
            STYLISH_SOURCE_PATH_KEY: str(image_path),
        }
    )
    
    await message.answer(
        "✍️ Теперь отправьте текст, который нужно добавить на изображение.\n"
        "Можно использовать многострочный текст и эмодзи.",
        reply_markup=build_main_keyboard(),
    )


async def handle_stylish_text_wrong_input(message: types.Message, state: FSMContext) -> None:
    """Защита от дурака: обработка текста, когда ожидается изображение."""
    data = await state.get_data()
    stage = data.get(STYLISH_STAGE_KEY)
    
    if stage == STAGE_WAIT_IMAGE:
        logger.info("User sent text instead of image in wait_image stage")
        await message.answer(
            "❌ Пожалуйста, отправьте **изображение** (фото или документ), а не текст.\n\n"
            "📸 Отправьте изображение, на которое нужно добавить текст.",
            reply_markup=build_main_keyboard(),
            parse_mode="Markdown",
        )
        return


async def handle_stylish_text(message: types.Message, state: FSMContext) -> None:
    """Обработка введенного текста."""
    logger.info("handle_stylish_text called, user_id: {}, text: {}", 
                message.from_user.id if message.from_user else "unknown",
                message.text[:50] if message.text else "None")
    
    data = await state.get_data()
    stage = data.get(STYLISH_STAGE_KEY)
    logger.debug("Current stage: {}, expected: {}", stage, STAGE_WAIT_TEXT)
    
    # Если мы в состоянии wait_hint, это пожелания по оформлению - не обрабатываем здесь
    if stage == STAGE_WAIT_HINT:
        logger.debug("In wait_hint stage, this should be handled by handle_stylish_hint, ignoring")
        return
    
    if stage != STAGE_WAIT_TEXT:
        logger.debug("Not in wait_text stage, ignoring")
        return
    
    text = message.text or message.caption or ""
    if not text.strip():
        await message.answer("Пожалуйста, введите текст для добавления на изображение.")
        return
    
    await state.update_data(
        {
            STYLISH_STAGE_KEY: STAGE_WAIT_HINT,
            STYLISH_TEXT_KEY: text,
        }
    )
    
    await message.answer(
        "🎨 Опишите пожелания по оформлению текста.\n\n"
        "**Примеры:**\n"
        "• 'Крупный белый текст в центре, на чёрной плашке'\n"
        "• 'Огромный текст по центру, красный цвет, без плашки'\n"
        "• 'Обычный текст снизу, белая плашка с прозрачностью 50%'\n"
        "• 'Текст размером 72px снизу, расстояние от низа 10%'\n"
        "• 'Белая плашка с размытием, радиус размытия 5'\n\n"
        "**Размеры текста:**\n"
        "• Маленький / Средний / Обычный / Крупный / Огромный\n"
        "• Или цифрами: 48px, 72 пикселей, размер 96\n\n"
        "Или отправьте /skip для настроек по умолчанию.",
        reply_markup=build_main_keyboard(),
        parse_mode="Markdown",
    )


async def handle_stylish_hint(message: types.Message, state: FSMContext) -> None:
    """Обработка пожеланий по оформлению и рендеринг."""
    # Проверяем, что это текстовое сообщение
    if not message.text:
        return
    
    # Быстрая проверка состояния - если не wait_hint, сразу выходим
    # Это нужно, чтобы не перехватывать сообщения для handle_stylish_text
    data = await state.get_data()
    stage = data.get(STYLISH_STAGE_KEY)
    
    if stage != STAGE_WAIT_HINT:
        # Не логируем это как INFO, только DEBUG - это нормальное поведение
        logger.debug("handle_stylish_hint: not in wait_hint stage (current: {}), ignoring", stage)
        return
    
    # Только если мы в правильном состоянии, логируем и обрабатываем
    logger.info("handle_stylish_hint processing: user_id: {}, text: {}", 
                message.from_user.id if message.from_user else "unknown", 
                message.text[:50])
    logger.debug("Current FSM state: stage={}, all_data keys: {}", stage, list(data.keys()))
    
    source_path_str = data.get(STYLISH_SOURCE_PATH_KEY)
    text = data.get(STYLISH_TEXT_KEY)
    hint = message.text or message.caption or ""
    
    logger.info("Processing stylish hint: stage={}, source={}, text={}, hint={}", stage, source_path_str, text, hint)
    
    # Логируем парсинг пожеланий
    if hint.strip():
        logger.info("User hint: '{}'", hint.strip())
    
    if not source_path_str or not text:
        await message.answer("Ошибка: не найдены изображение или текст. Начните заново.")
        await state.clear()
        return
    
    # Проверка баланса перед добавлением текста
    from app.services.billing import BillingService
    from app.services.pricing import get_operation_price
    from app.db.base import SessionLocal
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    operation_id_for_confirmation = None
    db = SessionLocal()
    try:
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            await message.answer("Ошибка: не удалось определить пользователя.")
            await state.clear()
            return
        
        user, _ = BillingService.get_or_create_user(db, user_id, message.from_user)
        price = get_operation_price("add_text")
        
        # Check for active discount code in state or database
        from app.bot.handlers.image import get_operation_discount_percent
        discount_percent = None
        if state:
            discount_percent = await get_operation_discount_percent(state, user_id)
        
        success, error_msg, operation_id = BillingService.charge_operation(
            db, user.id, "add_text",
            discount_percent=discount_percent
        )
        
        if not success:
            balance = BillingService.get_user_balance(db, user.id)
            text_error = (
                f"❌ **Недостаточно средств**\n\n"
                f"Добавление текста стоит: {price} ₽\n"
                f"Ваш баланс: {round(float(balance), 2):.2f} ₽\n\n"
                f"Пополните баланс для продолжения работы."
            )
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="💰 Пополнить баланс",
                        callback_data="payment_menu"
                    )
                ]
            ])
            await message.answer(text_error, reply_markup=keyboard, parse_mode="Markdown")
            await state.clear()
            return
        
        logger.info("Add text reserved: operation_id={}, price={}₽", operation_id, price)
        operation_id_for_confirmation = operation_id
    finally:
        db.close()
    
    # Пропускаем пожелания если /skip или пусто
    hint_lower = hint.strip().lower()
    if hint_lower in ("/skip", "skip", "пропустить", "") or not hint.strip():
        hint = ""
        logger.info("Skipping style hints, using defaults")
    
    try:
        # Парсим пожелания через LLM
        parsed_params = {}
        if hint.strip():
            logger.info("Parsing style hint: {}", hint)
            # Отправляем сообщение о начале обработки
            processing_msg = await message.answer("🔄 Обрабатываю пожелания по оформлению...")
            try:
                logger.info("Calling wish_to_params_async with hint: {}", hint.strip())
                parsed_params = await wish_to_params_async(hint.strip())
                logger.info("Parsed params from LLM: {}", parsed_params)
                if not parsed_params:
                    logger.warning("LLM returned empty params, will use defaults")
                await processing_msg.delete()
            except Exception as llm_error:
                logger.error("Error in LLM parsing: {}", llm_error, exc_info=True)
                await processing_msg.delete()
                # Продолжаем с дефолтными параметрами
                await message.answer("⚠️ Не удалось обработать пожелания, использую настройки по умолчанию.")
        
        # Базовые параметры по умолчанию (только если не указаны пользователем)
        # Используем минимальные дефолты - только то, что действительно нужно
        auto_params = {
            "position": "center",
            "size": "L",  # Увеличиваем размер по умолчанию
            "align": "center",
        }
        
        # Если указан offset_bottom, автоматически устанавливаем position: 'bottom-center'
        if "offset_bottom" in parsed_params:
            auto_params["position"] = "bottom-center"
            logger.debug("offset_bottom specified, setting position to bottom-center")
        
        # Если пользователь явно не указал про плашку, не добавляем её
        # Если указал - используем его параметры
        if "box" not in parsed_params:
            # Пользователь не упомянул плашку - не добавляем
            auto_params["box"] = False
        if "box_alpha" not in parsed_params and "box" in parsed_params and parsed_params.get("box"):
            # Пользователь указал плашку, но не указал прозрачность - используем разумный дефолт
            auto_params["box_alpha"] = 0.6
        
        # Если пользователь не указал про тень, не добавляем её
        # (shadow не входит в parsed_params, так как это не парсится LLM, но можно добавить)
        
        # Объединяем: сначала авто, потом парсированные (парсированные имеют приоритет)
        final_params = {**auto_params, **parsed_params}
        
        # Если плашка отключена, отключаем и тень, и обводку (они нужны только с плашкой)
        # Также отключаем обводку по умолчанию, если пользователь не просит её явно
        if not final_params.get("box", False):
            final_params["shadow"] = False
            final_params["stroke"] = 0
            logger.debug("Box disabled, disabling shadow and stroke too")
        else:
            # Если плашка включена, но пользователь не упомянул обводку - отключаем её
            # Обводка нужна только если пользователь явно просит
            if "stroke" not in parsed_params:
                final_params["stroke"] = 0
                logger.debug("Box enabled but stroke not mentioned, disabling stroke")
            # Также отключаем тень по умолчанию, если пользователь не просит её явно
            if "shadow" not in parsed_params:
                final_params["shadow"] = False
                logger.debug("Box enabled but shadow not mentioned, disabling shadow")
        
        # Открываем изображение
        source_path = Path(source_path_str)
        if not source_path.exists():
            await message.answer("Ошибка: файл изображения не найден.")
            await state.clear()
            return
        
        img = Image.open(source_path)
        
        # Рендерим текст
        logger.info("Rendering text with params: {}", final_params)
        logger.info("Image object: type={}, size={}, mode={}", type(img), img.size, img.mode)
        logger.info("Text to render: '{}'", text)
        logger.info("About to call render_text_box with {} params", len(final_params))
        
        rendering_msg = await message.answer("🎨 Рендерю текст на изображение...")
        try:
            # Рендеринг может занять время, особенно при загрузке эмодзи из интернета
            # Запускаем в отдельном потоке с таймаутом
            import asyncio
            logger.info("Creating asyncio task for render_text_box...")
            
            # Пробуем вызвать напрямую сначала для проверки
            logger.info("Calling render_text_box directly (synchronous) to test...")
            try:
                result_img = render_text_box(img, text, **final_params)
                logger.info("Direct call successful! Result image size: {}", result_img.size if result_img else "None")
            except Exception as direct_error:
                logger.error("Direct call failed: {}", direct_error, exc_info=True)
                raise
            
            logger.info("Text rendering completed successfully, result image size: {}", result_img.size if result_img else "None")
            await rendering_msg.delete()
        except asyncio.TimeoutError:
            await rendering_msg.delete()
            logger.error("Text rendering timed out after 180 seconds")
            await message.answer(
                "❌ Рендеринг текста занял слишком много времени (более 3 минут). Попробуйте еще раз или упростите запрос.",
                reply_markup=build_main_keyboard(),
            )
            await state.clear()
            return
        except Exception as render_error:
            await rendering_msg.delete()
            logger.error("Text rendering error: {}", render_error, exc_info=True)
            raise render_error
        
        # Сохраняем результат
        from app.core.config import settings
        
        output_path = settings.media_dir / "images" / f"{uuid4()}_stylish.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Saving result image to: {}", output_path)
        result_img.save(output_path, "PNG", optimize=True)
        logger.info("Result image saved successfully, file size: {} bytes", output_path.stat().st_size)
        
        # Отправляем результат
        logger.info("Sending result image to user")
        await message.answer("✨ Готово! Текст добавлен на изображение.")
        await message.answer_document(
            FSInputFile(output_path),
            caption="✨ Stylish text готов!",
        )
        logger.info("Result image sent successfully")
        
        # Confirm operation after successful rendering
        if operation_id_for_confirmation:
            db = SessionLocal()
            try:
                success = BillingService.confirm_operation(db, operation_id_for_confirmation)
                if success:
                    logger.info("Confirmed operation {} for add text", operation_id_for_confirmation)
                else:
                    logger.error("Failed to confirm operation {} for add text", operation_id_for_confirmation)
            except Exception as e:
                logger.error("Error confirming operation {} for add text: {}", operation_id_for_confirmation, e, exc_info=True)
            finally:
                db.close()
        
        await state.clear()
        
    except Exception as e:
        logger.error("Error in stylish text rendering: {}", e, exc_info=True)
        
        # Mark operation as failed on error
        if operation_id_for_confirmation:
            db = SessionLocal()
            try:
                BillingService.fail_operation(db, operation_id_for_confirmation)
                logger.info("Marked operation {} as failed for add text due to error", operation_id_for_confirmation)
            except Exception as fail_error:
                logger.error("Error failing operation {} for add text: {}", operation_id_for_confirmation, fail_error, exc_info=True)
            finally:
                db.close()
        
        await message.answer(
            f"❌ Ошибка при обработке: {str(e)}\nПопробуйте еще раз.",
            reply_markup=build_main_keyboard(),
        )
        await state.clear()


def register_stylish_text_handlers(dp: Dispatcher) -> None:
    """Регистрирует обработчики для Stylish text."""
    logger.info("Registering stylish text handlers")
    
    # Начало режима - регистрируем первым с высоким приоритетом
    dp.message.register(
        handle_stylish_start,
        F.text == IMAGE_STYLISH_TEXT_BUTTON,
    )
    logger.debug("Registered handle_stylish_start")
    
    # Обработка изображения - только если в состоянии wait_image
    # Используем фильтр состояния, чтобы не перехватывать другие сообщения
    async def stylish_media_state_filter(message: types.Message, state: FSMContext) -> bool:
        """Фильтр для handle_stylish_media - проверяет, что состояние wait_image."""
        data = await state.get_data()
        stage = data.get(STYLISH_STAGE_KEY)
        return stage == STAGE_WAIT_IMAGE
    
    dp.message.register(
        handle_stylish_media,
        stylish_media_state_filter,
        F.photo | F.document,
    )
    logger.debug("Registered handle_stylish_media with state filter")
    
    # ВАЖНО: Регистрируем handle_stylish_hint ПЕРЕД handle_stylish_text,
    # чтобы пожелания по оформлению обрабатывались первыми
    # Обработка пожеланий и рендеринг - только если в состоянии wait_hint
    # Используем фильтр, который проверяет состояние
    async def stylish_hint_state_filter(message: types.Message, state: FSMContext) -> bool:
        """Фильтр для handle_stylish_hint - проверяет, что состояние wait_hint."""
        if not message.text:
            return False
        data = await state.get_data()
        stage = data.get(STYLISH_STAGE_KEY)
        return stage == STAGE_WAIT_HINT
    
    dp.message.register(handle_stylish_hint, stylish_hint_state_filter)
    logger.debug("Registered handle_stylish_hint with state filter")
    
    # Защита от дурака: обработка текста, когда ожидается изображение
    # Регистрируем ПЕРЕД handle_stylish_text, чтобы иметь приоритет
    async def stylish_text_wrong_input_filter(message: types.Message, state: FSMContext) -> bool:
        """Фильтр для handle_stylish_text_wrong_input - проверяет, что состояние wait_image и это текст."""
        if not message.text:
            return False
        data = await state.get_data()
        stage = data.get(STYLISH_STAGE_KEY)
        return stage == STAGE_WAIT_IMAGE
    
    dp.message.register(handle_stylish_text_wrong_input, stylish_text_wrong_input_filter)
    logger.debug("Registered handle_stylish_text_wrong_input with state filter")
    
    # Обработка текста - только если в состоянии wait_text
    # ВАЖНО: Используем фильтр состояния, чтобы не перехватывать другие сообщения
    async def stylish_text_state_filter(message: types.Message, state: FSMContext) -> bool:
        """Фильтр для handle_stylish_text - проверяет, что состояние wait_text."""
        if not message.text:
            return False
        data = await state.get_data()
        stage = data.get(STYLISH_STAGE_KEY)
        return stage == STAGE_WAIT_TEXT
    
    dp.message.register(handle_stylish_text, stylish_text_state_filter)
    logger.debug("Registered handle_stylish_text with state filter")

