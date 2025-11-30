from __future__ import annotations

from pathlib import Path
from typing import Iterable
from uuid import uuid4

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from loguru import logger

from app.bot.keyboards.main import (
    IMAGE_FACE_SWAP_BUTTON,
    build_main_keyboard,
)
from app.bot.services.jobs import enqueue_face_swap
from app.core.config import reload_settings
from app.core.storage import storage
from app.utils.translation import translate_to_english


class FaceSwapStates(StatesGroup):
    waiting_source = State()
    waiting_target = State()
    waiting_instruction = State()


FACE_SWAP_SOURCE_PATH_KEY = "face_swap_source_path"
FACE_SWAP_TARGET_PATH_KEY = "face_swap_target_path"
FACE_SWAP_MODEL_KEY = "face_swap_model"  # Модель: "fal-ai/face-swap" или "wavespeed-ai/image-face-swap" (высокое качество)


async def handle_face_swap_start(message: types.Message, state: FSMContext) -> None:
    # Проверяем, не находимся ли мы в режиме "Написать"
    from app.bot.handlers.prompt_writer import PromptWriterStates
    current_state = await state.get_state()
    if current_state == PromptWriterStates.waiting_input:
        logger.info("handle_face_swap_start: user is in prompt writer mode, showing message")
        await message.answer(
            "⚠️ Вы находитесь в режиме **«✍️ Написать»**.\n\n"
            "Для перехода в другой режим:\n"
            "• Нажмите кнопку **«ℹ️ Info»** для сброса текущей сессии\n"
            "• Затем выберите нужный режим\n\n"
            "Или введите текст промпта для генерации.",
            parse_mode="Markdown",
        )
        return
    """Начало процесса замены лица - используем только WaveSpeed модель."""
    await state.clear()
    
    # Устанавливаем WaveSpeed модель по умолчанию
    try:
        current_settings = reload_settings()
        model = current_settings.wavespeed_face_swap_model
        logger.info("handle_face_swap_start: using WaveSpeed model {}", model)
    except Exception as e:
        logger.error("handle_face_swap_start: failed to load settings: {}", e)
        await message.answer("Ошибка при загрузке настроек. Попробуйте позже.")
        return
    
    await state.set_state(FaceSwapStates.waiting_source)
    await state.update_data(
        {
            FACE_SWAP_SOURCE_PATH_KEY: None,
            FACE_SWAP_TARGET_PATH_KEY: None,
            FACE_SWAP_MODEL_KEY: model,  # Устанавливаем WaveSpeed модель сразу
        }
    )
    await message.answer(
        "🔄 Замена лица\n\n"
        "1) Загрузите портрет с лицом (источник).\n"
        "2) Затем отправьте фото, в котором нужно заменить лицо.",
        reply_markup=build_main_keyboard(),
    )




def _generate_face_swap_path(extension: str | None = None) -> Path:
    suffix = extension if extension else ".png"
    filename = f"{uuid4().hex}{suffix}"
    destination = storage.base_dir / "face_swap" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _normalize_extension(candidates: Iterable[str | None]) -> str:
    for item in candidates:
        if not item:
            continue
        cleaned = item.strip().lower()
        if not cleaned:
            continue
        if not cleaned.startswith("."):
            cleaned = f".{cleaned}"
        if cleaned in {".png", ".jpg", ".jpeg"}:
            return ".jpg" if cleaned == ".jpeg" else cleaned
        if cleaned == ".webp":
            return ".png"
    return ".png"


async def _download_image(message: types.Message) -> Path | None:
    """Загружает изображение с обработкой ошибок и повторными попытками."""
    import asyncio
    
    if message.photo:
        # Используем самое большое доступное фото для лучшего качества
        # Telegram предоставляет несколько размеров, берем последний (самый большой)
        file = message.photo[-1]
        destination = _generate_face_swap_path(".png")
        # Попытка загрузки с повторными попытками
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Скачиваем файл напрямую через get_file для получения оригинального качества
                file_info = await message.bot.get_file(file.file_id)
                await message.bot.download_file(file_info.file_path, destination=destination)
                logger.info("Downloaded photo: file_id={}, size={} bytes, path={}", 
                           file.file_id, file.file_size if hasattr(file, 'file_size') else 'unknown', destination)
                return destination
            except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
                if attempt < max_attempts - 1:
                    logger.warning("Failed to download photo (attempt {}/{}): {}, retrying...", 
                                 attempt + 1, max_attempts, exc)
                    await asyncio.sleep(1)  # Небольшая задержка перед повтором
                else:
                    logger.error("Failed to download photo after {} attempts: {}", max_attempts, exc)
                    await message.answer(
                        "Не удалось загрузить изображение. Пожалуйста, попробуйте отправить файл меньшего размера или попробуйте позже."
                    )
                    return None
        return None
    
    if message.document:
        document = message.document
        if document.mime_type and not document.mime_type.startswith("image"):
            await message.answer("Пожалуйста, отправьте изображение (PNG или JPEG).")
            return None
        
        # Проверяем размер файла
        if document.file_size and document.file_size > 10 * 1024 * 1024:  # 10 МБ
            await message.answer(
                "Файл слишком большой (более 10 МБ). Пожалуйста, отправьте изображение меньшего размера."
            )
            return None
        
        extension = _normalize_extension(
            [
                Path(document.file_name or "").suffix,
                document.mime_type.split("/")[-1] if document.mime_type else None,
            ]
        )
        destination = _generate_face_swap_path(extension)
        
        # Попытка загрузки с повторными попытками и увеличенным таймаутом
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Используем увеличенный таймаут для больших файлов
                timeout = 60 if document.file_size and document.file_size > 2 * 1024 * 1024 else 30
                await asyncio.wait_for(
                    message.bot.download(document, destination=destination),
                    timeout=timeout
                )
                return destination
            except asyncio.TimeoutError:
                if attempt < max_attempts - 1:
                    logger.warning("Timeout downloading document (attempt {}/{}), retrying...", 
                                 attempt + 1, max_attempts)
                    await asyncio.sleep(2)  # Задержка перед повтором
                else:
                    logger.error("Timeout downloading document after {} attempts", max_attempts)
                    await message.answer(
                        "Превышено время ожидания при загрузке файла. "
                        "Пожалуйста, попробуйте отправить файл меньшего размера или попробуйте позже."
                    )
                    return None
            except Exception as exc:  # noqa: BLE001
                if attempt < max_attempts - 1:
                    logger.warning("Failed to download document (attempt {}/{}): {}, retrying...", 
                                 attempt + 1, max_attempts, exc)
                    await asyncio.sleep(1)
                else:
                    logger.error("Failed to download document after {} attempts: {}", max_attempts, exc)
                    await message.answer(
                        "Не удалось загрузить файл. Пожалуйста, попробуйте отправить файл меньшего размера или попробуйте позже."
                    )
                    return None
        return None
    
    await message.answer("Пожалуйста, отправьте изображение в виде фото или документа.")
    return None


def _build_notify_options(message: types.Message, prompt: str | None) -> dict[str, object]:
    options: dict[str, object] = {}
    if message.chat:
        options["notify_chat_id"] = message.chat.id
        if getattr(message.chat, "linked_chat_id", None):
            options["notify_linked_chat_id"] = message.chat.linked_chat_id
    if message.message_thread_id:
        options["notify_message_thread_id"] = message.message_thread_id
    if message.message_id:
        options["notify_reply_to_message_id"] = message.message_id
    label = prompt.strip() if prompt else "Замена лица"
    options["notify_prompt"] = label
    return options


async def _queue_face_swap_job(
    message: types.Message,
    state: FSMContext,
    *,
    source_path: Path,
    target_path: Path,
    instruction: str | None,
    operation_id: int | None = None,
) -> None:
    """Постановка задачи замены лица в очередь."""
    from app.services.billing import BillingService
    from app.services.pricing import get_operation_price
    from app.db.base import SessionLocal
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    # Проверка баланса (если operation_id не передан, проверяем баланс)
    if operation_id is None:
        db = SessionLocal()
        try:
            user_id = message.from_user.id if message.from_user else None
            if not user_id:
                await message.answer("Ошибка: не удалось определить пользователя.")
                await state.clear()
                return
            
            user, _ = BillingService.get_or_create_user(db, user_id, message.from_user)
            price = get_operation_price("face_swap")
            
            # Check for active discount code in state or database
            from app.bot.handlers.image import get_operation_discount_percent
            discount_percent = None
            if state:
                discount_percent = await get_operation_discount_percent(state, user_id)
            
            success, error_msg, op_id = BillingService.charge_operation(
                db, user.id, "face_swap",
                discount_percent=discount_percent
            )
            
            if not success:
                balance = BillingService.get_user_balance(db, user.id)
                text = (
                    f"❌ **Недостаточно средств**\n\n"
                    f"Замена лица стоит: {price} ₽\n"
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
                await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")
                await state.clear()
                return
            
            operation_id = op_id
            logger.info("Face swap charged: operation_id={}, price={}₽", operation_id, price)
        finally:
            db.close()
    
    # Получаем выбранную модель из state (по умолчанию WaveSpeed)
    data = await state.get_data()
    model = data.get(FACE_SWAP_MODEL_KEY)
    if not model:
        # Если модель не установлена, загружаем WaveSpeed модель из настроек
        try:
            current_settings = reload_settings()
            model = current_settings.wavespeed_face_swap_model
            logger.info("_queue_face_swap_job: model not found in state, using WaveSpeed model from settings: {}", model)
        except Exception as e:
            logger.error("_queue_face_swap_job: failed to load WaveSpeed model from settings: {}", e)
            await message.answer("Ошибка при загрузке настроек модели. Попробуйте позже.")
            await state.clear()
            return
    
    translated_instruction = translate_to_english(instruction) if instruction else None
    options = _build_notify_options(message, instruction or "Замена лица")
    if translated_instruction and translated_instruction != instruction:
        options["provider_instruction"] = translated_instruction
    
    # Передаем модель в options для worker
    options["model"] = model
    
    # Передаем operation_id в options для worker
    if operation_id:
        options["operation_id"] = operation_id
        logger.info("_queue_face_swap_job: adding operation_id={} to options for job", operation_id)
    else:
        logger.warning("_queue_face_swap_job: operation_id is None, not adding to options")
    
    logger.info("_queue_face_swap_job: calling enqueue_face_swap with operation_id={}, options_keys={}", 
                operation_id, list(options.keys()))
    job_id, _ = enqueue_face_swap(
        source_path=source_path.as_posix(),
        target_path=target_path.as_posix(),
        instruction=instruction,
        **options,
    )
    logger.info(
        "Queued face swap job {} for user {} (model={}, source={}, target={}, operation_id={})",
        job_id,
        message.from_user.id if message.from_user else "unknown",
        model,
        source_path,
        target_path,
        operation_id,
    )
    await message.answer("🚀 Замена лица запущена. Когда будет готово — пришлю результат документом.")


async def handle_face_swap_source_media(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != FaceSwapStates.waiting_source.state:
        return
    saved = await _download_image(message)
    if not saved:
        return
    await state.update_data({FACE_SWAP_SOURCE_PATH_KEY: saved.as_posix()})
    await state.set_state(FaceSwapStates.waiting_target)
    await message.answer(
        "Источник получен ✅\nТеперь отправьте фото, в котором нужно заменить лицо.",
        reply_markup=build_main_keyboard(),
    )


async def handle_face_swap_target_media(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != FaceSwapStates.waiting_target.state:
        return
    saved = await _download_image(message)
    if not saved:
        return
    await state.update_data({FACE_SWAP_TARGET_PATH_KEY: saved.as_posix()})
    
    # Get both images and check which model is selected (should be WaveSpeed)
    data = await state.get_data()
    source_raw = data.get(FACE_SWAP_SOURCE_PATH_KEY)
    target_raw = saved.as_posix()
    model = data.get(FACE_SWAP_MODEL_KEY)
    if not model:
        # Если модель не установлена, загружаем WaveSpeed модель из настроек
        try:
            current_settings = reload_settings()
            model = current_settings.wavespeed_face_swap_model
            logger.info("handle_face_swap_target_media: model not found in state, using WaveSpeed model from settings: {}", model)
        except Exception as e:
            logger.error("handle_face_swap_target_media: failed to load WaveSpeed model from settings: {}", e)
            await message.answer("Ошибка при загрузке настроек модели. Попробуйте позже.")
            await state.clear()
            return
    
    if not source_raw:
        await message.answer(
            "Не удалось найти исходное изображение. Запустите режим замены лица заново.",
            reply_markup=build_main_keyboard(),
        )
        await state.clear()
        return
    
    source_path = Path(source_raw)
    target_path = Path(target_raw)
    if not source_path.exists() or not target_path.exists():
        await message.answer(
            "Исходные файлы недоступны. Пожалуйста, начните режим замены лица заново.",
            reply_markup=build_main_keyboard(),
        )
        await state.clear()
        return
    
    # Все модели (fal-ai/face-swap и WaveSpeedAI) запускаются сразу без запроса инструкций
    try:
        await message.answer("Оба изображения получены ✅", reply_markup=build_main_keyboard())
        await _queue_face_swap_job(
            message,
            state,
            source_path=source_path,
            target_path=target_path,
            instruction=None,  # Инструкции не используются
        )
        await state.clear()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to enqueue face swap job: {}", exc)
        await message.answer(
            "Не удалось отправить запрос на замену лица. Попробуйте позже.",
            reply_markup=build_main_keyboard(),
        )
        await state.clear()


def _is_instruction_skip(text: str | None) -> bool:
    if not text:
        return True
    lowered = text.strip().lower()
    return lowered in {"", "готово", "ok", "ок", "без инструкции", "skip", "пропустить"}


async def handle_face_swap_instruction(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != FaceSwapStates.waiting_instruction.state:
        return
    text = (message.text or "").strip()
    instruction = None if _is_instruction_skip(text) else text
    data = await state.get_data()

    source_raw = data.get(FACE_SWAP_SOURCE_PATH_KEY)
    target_raw = data.get(FACE_SWAP_TARGET_PATH_KEY)
    if not source_raw or not target_raw:
        await message.answer(
            "Не удалось найти одно из изображений. Запустите режим замены лица заново.",
            reply_markup=build_main_keyboard(),
        )
        await state.clear()
        return

    source_path = Path(source_raw)
    target_path = Path(target_raw)
    if not source_path.exists() or not target_path.exists():
        await message.answer(
            "Исходные файлы недоступны. Пожалуйста, начните режим замены лица заново.",
            reply_markup=build_main_keyboard(),
        )
        await state.clear()
        return

    try:
        await _queue_face_swap_job(
            message,
            state,
            source_path=source_path,
            target_path=target_path,
            instruction=instruction,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to enqueue face swap job: {}", exc)
        await message.answer(
            "Не удалось отправить запрос на замену лица. Попробуйте позже.",
            reply_markup=build_main_keyboard(),
        )
        await state.clear()
        return

    await state.clear()


async def handle_face_swap_text_in_source_stage(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != FaceSwapStates.waiting_source.state:
        return
    if message.text and message.text.startswith("/"):
        return
    await message.answer(
        "Сначала загрузите портрет (источник лица), затем продолжайте.",
        reply_markup=build_main_keyboard(),
    )


async def handle_face_swap_text_in_target_stage(message: types.Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state != FaceSwapStates.waiting_target.state:
        return
    if message.text and message.text.startswith("/"):
        return
    await message.answer(
        "Теперь пришлите фото, в котором нужно заменить лицо.",
        reply_markup=build_main_keyboard(),
    )




def register_face_swap_handlers(dp: Dispatcher) -> None:
    # Обработчик начала замены лица (сразу использует WaveSpeed модель)
    dp.message.register(
        handle_face_swap_start,
        lambda msg: msg.text and msg.text.strip().lower() == IMAGE_FACE_SWAP_BUTTON.lower(),
    )
    
    # Обработчики загрузки исходного изображения
    dp.message.register(
        handle_face_swap_source_media,
        StateFilter(FaceSwapStates.waiting_source),
        F.photo,
    )
    dp.message.register(
        handle_face_swap_source_media,
        StateFilter(FaceSwapStates.waiting_source),
        F.document,
    )
    
    # Обработчики загрузки целевого изображения
    dp.message.register(
        handle_face_swap_target_media,
        StateFilter(FaceSwapStates.waiting_target),
        F.photo,
    )
    dp.message.register(
        handle_face_swap_target_media,
        StateFilter(FaceSwapStates.waiting_target),
        F.document,
    )
    
    # Обработчик промпта (если понадобится в будущем)
    dp.message.register(
        handle_face_swap_instruction,
        StateFilter(FaceSwapStates.waiting_instruction),
        F.text,
    )
    
    # Обработчики текста на разных этапах
    dp.message.register(
        handle_face_swap_text_in_source_stage,
        StateFilter(FaceSwapStates.waiting_source),
        F.text,
    )
    dp.message.register(
        handle_face_swap_text_in_target_stage,
        StateFilter(FaceSwapStates.waiting_target),
        F.text,
    )

