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
    IMAGE_FACE_SWAP_BASIC_BUTTON,
    IMAGE_FACE_SWAP_ADVANCED_BUTTON,
    build_main_keyboard,
    build_face_swap_model_keyboard,
)
from app.bot.services.jobs import enqueue_face_swap
from app.core.config import reload_settings
from app.core.storage import storage
from app.utils.translation import translate_to_english


class FaceSwapStates(StatesGroup):
    waiting_model = State()  # Выбор модели (face-swap или advanced-face-swap)
    waiting_source = State()
    waiting_target = State()
    waiting_instruction = State()


FACE_SWAP_SOURCE_PATH_KEY = "face_swap_source_path"
FACE_SWAP_TARGET_PATH_KEY = "face_swap_target_path"
FACE_SWAP_MODEL_KEY = "face_swap_model"  # Модель: "fal-ai/face-swap" или "easel-ai/advanced-face-swap"


async def handle_face_swap_start(message: types.Message, state: FSMContext) -> None:
    """Начало процесса замены лица - выбор модели."""
    await state.clear()
    await state.set_state(FaceSwapStates.waiting_model)
    await state.update_data(
        {
            FACE_SWAP_SOURCE_PATH_KEY: None,
            FACE_SWAP_TARGET_PATH_KEY: None,
            FACE_SWAP_MODEL_KEY: None,
        }
    )
    await message.answer(
        "Выберите модель для замены лица:\n\n"
        "🔄 Face Swap — базовая замена лица (fal-ai/face-swap)\n"
        "🔄 WaveSpeed Face Swap — замена лица через WaveSpeedAI (wavespeed-ai/image-face-swap) — выше качество",
        reply_markup=build_face_swap_model_keyboard(),
    )


async def handle_face_swap_basic_model(message: types.Message, state: FSMContext) -> None:
    """Обработка выбора базовой модели Face Swap."""
    current_state = await state.get_state()
    if current_state != FaceSwapStates.waiting_model.state:
        return
    
    model = "fal-ai/face-swap"
    model_name = "Face Swap"
    
    # Сохраняем выбранную модель
    await state.update_data({FACE_SWAP_MODEL_KEY: model})
    await state.set_state(FaceSwapStates.waiting_source)
    
    await message.answer(
        f"Модель {model_name} выбрана ✅\n\n"
        "1) Загрузите портрет с лицом (источник).\n"
        "2) Затем отправьте фото, в котором нужно заменить лицо.",
        reply_markup=build_main_keyboard(),
    )


async def handle_face_swap_advanced_model(message: types.Message, state: FSMContext) -> None:
    """Обработка выбора модели WaveSpeed Face Swap (высокое качество через WaveSpeedAI)."""
    logger.info("handle_face_swap_advanced_model called: text='{}', state={}", message.text, await state.get_state())
    current_state = await state.get_state()
    if current_state != FaceSwapStates.waiting_model.state:
        logger.warning("handle_face_swap_advanced_model: wrong state. Expected {}, got {}", FaceSwapStates.waiting_model.state, current_state)
        return
    
    # WaveSpeed Face Swap использует WaveSpeedAI для высокого качества замены лица
    try:
        current_settings = reload_settings()
        model = current_settings.wavespeed_face_swap_model
        model_name = f"WaveSpeed Face Swap ({model})"  # Высокое качество через WaveSpeedAI
        logger.info("handle_face_swap_advanced_model: using model {}", model)
    except Exception as e:
        logger.error("handle_face_swap_advanced_model: failed to load settings: {}", e)
        await message.answer("Ошибка при загрузке настроек. Попробуйте позже.")
        return
    
    # Сохраняем выбранную модель
    await state.update_data({FACE_SWAP_MODEL_KEY: model})
    await state.set_state(FaceSwapStates.waiting_source)
    
    try:
        response_text = (
            f"Модель {model_name} выбрана ✅\n\n"
            "1) Загрузите портрет с лицом (источник).\n"
            "2) Затем отправьте фото, в котором нужно заменить лицо."
        )
        logger.info("handle_face_swap_advanced_model: sending response to user")
        sent_message = await message.answer(
            response_text,
            reply_markup=build_main_keyboard(),
        )
        logger.info("handle_face_swap_advanced_model: message sent successfully, message_id={}", sent_message.message_id if sent_message else "None")
    except Exception as e:
        logger.error("handle_face_swap_advanced_model: failed to send message: {}", e, exc_info=True)
        # Попробуем отправить без клавиатуры
        try:
            await message.answer(response_text)
            logger.info("handle_face_swap_advanced_model: message sent without keyboard")
        except Exception as e2:
            logger.error("handle_face_swap_advanced_model: failed to send message even without keyboard: {}", e2, exc_info=True)


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
        file = message.photo[-1]
        destination = _generate_face_swap_path(".png")
        # Попытка загрузки с повторными попытками
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                await message.bot.download(file, destination=destination)
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
) -> None:
    """Постановка задачи замены лица в очередь."""
    # Получаем выбранную модель из state
    data = await state.get_data()
    model = data.get(FACE_SWAP_MODEL_KEY, "fal-ai/face-swap")  # По умолчанию старая модель
    
    translated_instruction = translate_to_english(instruction) if instruction else None
    options = _build_notify_options(message, instruction or "Замена лица")
    if translated_instruction and translated_instruction != instruction:
        options["provider_instruction"] = translated_instruction
    
    # Передаем модель в options для worker
    options["model"] = model
    
    job_id, _ = enqueue_face_swap(
        source_path=source_path.as_posix(),
        target_path=target_path.as_posix(),
        instruction=instruction,
        **options,
    )
    logger.debug(
        "Queued face swap job {} for user {} (model={}, source={}, target={})",
        job_id,
        message.from_user.id if message.from_user else "unknown",
        model,
        source_path,
        target_path,
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
    
    # Get both images and check which model is selected
    data = await state.get_data()
    source_raw = data.get(FACE_SWAP_SOURCE_PATH_KEY)
    target_raw = saved.as_posix()
    model = data.get(FACE_SWAP_MODEL_KEY, "fal-ai/face-swap")
    
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
    
    # Check if advanced model requires prompt
    if "easel-ai" in model.lower() or "advanced" in model.lower():
        # Advanced model supports prompts - ask for instruction
        await state.set_state(FaceSwapStates.waiting_instruction)
        await message.answer(
            "Оба изображения получены ✅\n\n"
            "Модель WaveSpeed Face Swap поддерживает текстовые инструкции.\n"  # Высокое качество через WaveSpeedAI
            "Напишите инструкцию для замены лица (например: 'сохранить прическу цели', 'улучшить освещение') "
            "или отправьте 'готово' / 'пропустить' для использования настроек по умолчанию.",
            reply_markup=build_main_keyboard(),
        )
        return
    
    # Basic model (fal-ai/face-swap) - no prompt needed, start immediately
    try:
        await _queue_face_swap_job(
            message,
            state,
            source_path=source_path,
            target_path=target_path,
            instruction=None,  # No prompt needed for basic face-swap
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


async def handle_face_swap_text_in_model_stage(message: types.Message, state: FSMContext) -> None:
    """Обработка текста на этапе выбора модели."""
    current_state = await state.get_state()
    if current_state != FaceSwapStates.waiting_model.state:
        return
    if message.text and message.text.startswith("/"):
        return
    # Если пользователь отправил текст, который не является кнопкой выбора модели,
    # обработаем его через handle_face_swap_model_selection
    # Если это не кнопка, покажем подсказку
    text = message.text or ""
    if IMAGE_FACE_SWAP_BASIC_BUTTON not in text and IMAGE_FACE_SWAP_ADVANCED_BUTTON not in text:
        await message.answer(
            "Пожалуйста, выберите модель из предложенных кнопок.",
            reply_markup=build_face_swap_model_keyboard(),
        )


def register_face_swap_handlers(dp: Dispatcher) -> None:
    # Обработчик начала замены лица (показывает выбор модели)
    dp.message.register(
        handle_face_swap_start,
        lambda msg: msg.text and msg.text.strip().lower() == IMAGE_FACE_SWAP_BUTTON.lower(),
    )
    
    # Обработчики выбора модели (с фильтрами для точного совпадения)
    dp.message.register(
        handle_face_swap_basic_model,
        StateFilter(FaceSwapStates.waiting_model),
        F.text == IMAGE_FACE_SWAP_BASIC_BUTTON,
    )
    dp.message.register(
        handle_face_swap_advanced_model,
        StateFilter(FaceSwapStates.waiting_model),
        F.text == IMAGE_FACE_SWAP_ADVANCED_BUTTON,
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
    
    # Обработчик промпта для advanced модели
    dp.message.register(
        handle_face_swap_instruction,
        StateFilter(FaceSwapStates.waiting_instruction),
        F.text,
    )
    
    # Обработчики текста на разных этапах
    # Примечание: handle_face_swap_model_selection уже обрабатывает текст в состоянии waiting_model
    # Но добавим дополнительный обработчик для случаев, когда текст не является кнопкой
    dp.message.register(
        handle_face_swap_text_in_model_stage,
        StateFilter(FaceSwapStates.waiting_model),
        F.text,
    )
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

