from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from loguru import logger
from PIL import Image

from app.bot.keyboards.main import (
    CREATE_BUTTON,
    IMAGE_FACE_SWAP_BUTTON,
    IMAGE_SEEDREAM_CREATE_BUTTON,
    IMAGE_GPT_CREATE_BUTTON,
    IMAGE_EDIT_BUTTON,
    IMAGE_SMART_MERGE_BUTTON,
    IMAGE_RETOUCHER_BUTTON,
    IMAGE_STYLISH_TEXT_BUTTON,
    IMAGE_EDIT_CHRONO_BUTTON,
    IMAGE_EDIT_SEDEDIT_BUTTON,
    IMAGE_SMART_MERGE_NANO_BUTTON,
    IMAGE_SMART_MERGE_SEEDREAM_BUTTON,
    IMAGE_UPSCALE_BUTTON,
    IMAGE_SIZE_HORIZONTAL_BUTTON,
    IMAGE_SIZE_SQUARE_BUTTON,
    IMAGE_SIZE_VERTICAL_BUTTON,
    IMAGE_STANDARD_BUTTON,
    INFO_BUTTON,
    RETOUCHER_ENHANCE_BUTTON,
    RETOUCHER_SKIP_BUTTON,
    RETOUCHER_SOFT_BUTTON,
    build_create_model_keyboard,
    build_main_keyboard,
    build_size_keyboard,
    build_edit_model_keyboard,
    build_retoucher_instruction_keyboard,
    build_retoucher_mode_keyboard,
    build_smart_merge_model_keyboard,
)
from app.bot.services.jobs import (
    enqueue_image,
    enqueue_image_edit,
    enqueue_image_upscale,
    enqueue_retoucher,
    enqueue_smart_merge,
)
from app.core.config import settings
from app.core.queues import get_job
from app.core.storage import storage
from app.providers.fal.client import download_file
from app.providers.fal.models_map import resolve_alias, model_requires_mask
from app.utils.translation import translate_to_english


async def _get_telegram_file_url(message: types.Message, file_id: str) -> str | None:
    try:
        file = await message.bot.get_file(file_id)
        if not file.file_path:
            return None
        return f"https://api.telegram.org/file/bot{settings.tg_bot_token}/{file.file_path}"
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to obtain Telegram file url for {}: {}", file_id, exc)
        return None


IMAGE_STANDARD_MODEL = settings.fal_premium_model
IMAGE_EDIT_MODEL = settings.fal_edit_model
IMAGE_EDIT_ALT_MODEL = "fal-ai/bytedance/seedream/v4/edit"
LAST_JOB_BY_CHAT: dict[int, str] = {}
PROMPT_ACCEPTED_TEXT = (
    "Промпт принят ✅.\nТеперь выберите действие из меню."
)
NO_PROMPT_TEXT = (
    "Сначала напишите промпт, затем выберите действие из меню. Пример: «маленькая собака в шляпе, студийный свет»."
)
MIN_PROMPT_LENGTH = 3

# Текст описания моделей для создания изображений
MODELS_DESCRIPTION_TEXT = (
    "Выберите модель для создания изображения:\n"
    "• Nano Banana Pro — лучшая нейросеть, отличное качество кириллицы, продвинутая генерация изображений с текстом\n"
    "• Nano-banana — топовая модель, рисует текст на русском (заголовки)\n"
    "• Seedream (Create) — топовая модель, рисует текст только на английском"
)

EDIT_STAGE_KEY = "edit_stage"
EDIT_SOURCE_PATH_KEY = "edit_source_path"
EDIT_SOURCE_URL_KEY = "edit_source_url"
EDIT_PROMPT_KEY = "edit_prompt"
EDIT_MASK_PATH_KEY = "edit_mask_path"
EDIT_SOURCE_JOB_ID = "edit_source_job_id"
EDIT_SELECTED_MODEL_KEY = "edit_selected_model"
UPSCALE_STAGE_KEY = "upscale_stage"
UPSCALE_LAST_JOB_KEY = "upscale_last_job"
SMART_MERGE_STAGE_KEY = "smart_merge_stage"
SMART_MERGE_SOURCES_KEY = "smart_merge_sources"
SMART_MERGE_MODEL_KEY = "smart_merge_model"
SMART_MERGE_DEFAULT_MODEL = "fal-ai/nano-banana/edit"
SMART_MERGE_SEEDREAM_MODEL = "fal-ai/bytedance/seedream/v4/edit"
SMART_MERGE_DEFAULT_SIZE = "1024x1024"
SMART_MERGE_DEFAULT_ASPECT_RATIO = "1:1"
SMART_MERGE_MAX_IMAGES = 4
RETOUCHER_STAGE_KEY = "retoucher_stage"
RETOUCHER_SOURCE_PATH_KEY = "retoucher_source_path"
RETOUCHER_MODE_KEY = "retoucher_mode"
RETOUCHER_PROMPT_KEY = "retoucher_instruction"
CREATE_STAGE_KEY = "create_stage"
RETOUCHER_MODE_PRESETS: dict[str, dict[str, Any]] = {
    "soft": {
        "label": "Мягкая ретушь",
        "model": settings.fal_retoucher_model,
        "base_prompt": (
            "Delicate face retouch. Remove small blemishes and even the skin tone while preserving natural pores, texture, and details. "
            "Keep the original face structure, facial features, and identity exactly the same. "
            "Only remove imperfections, do not change face shape, eyes, nose, or mouth structure. "
            "Avoid over-smoothing the eyes and lips. Maintain realistic skin texture."
        ),
        "base_options": {
            "output_format": "png",
        },
        "notify_text": "✨ Запускаю мягкую ретушь лица...",
    },
    "enhance": {
        "label": "Усилить черты",
        "model": settings.fal_face_enhance_model,
        "base_prompt": (
            "Enhance facial features with natural clarity while preserving the original face identity. "
            "Keep the exact same face structure, proportions, and appearance. "
            "Accentuate the eyes, lips, and contours subtly while keeping skin texture realistic. "
            "Do not change face shape, bone structure, or facial features. Only enhance clarity and definition."
        ),
        "base_options": {
            "output_format": "png",
        },
        "notify_text": "✨ Улучшаю черты лица...",
    },
}

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "standard": {
        "label": "изображение",
        "model": IMAGE_STANDARD_MODEL,
        "base": {
            "num_inference_steps": 36,
            "guidance_scale": 7.0,
            "output_format": "png",
        },
        "sizes": {
            "vertical": {"size": "1472x2048", "aspect_ratio": "3:4", "image_size": "portrait_4_3"},
            "square": {"size": "1792x1792", "aspect_ratio": "1:1", "image_size": "square_2k"},
            "horizontal": {"size": "2048x1472", "aspect_ratio": "4:3", "image_size": "landscape_4_3"},
        },
    },
    "seededit": {
        "label": "SeedEdit",
        "model": IMAGE_EDIT_ALT_MODEL,
        "base": {
            "guidance_scale": 7.5,
            "output_format": "png",
        },
        "sizes": {
            "vertical": {"size": "832x1216"},
            "square": {"size": "1024x1024"},
            "horizontal": {"size": "1216x832"},
        },
    },
    "seedream-create": {
        "label": "изображение",
        "model": "fal-ai/bytedance/seedream/v4/text-to-image",  # Модель для создания без входного изображения
        "base": {
            "output_format": "png",
            "guidance_scale": 10.0,  # Максимальный guidance_scale для максимального качества
            "num_inference_steps": 100,  # Максимальное количество шагов для максимальной детализации
            # Seedream может иметь ограничения на разрешение, увеличиваем качество через шаги
        },
        "sizes": {
            # Используем максимальные размеры, которые модель может поддерживать
            "vertical": {"size": "1536x2048", "aspect_ratio": "3:4", "width": 1536, "height": 2048},
            "square": {"size": "2048x2048", "aspect_ratio": "1:1", "width": 2048, "height": 2048},
            "horizontal": {"size": "2048x1536", "aspect_ratio": "4:3", "width": 2048, "height": 1536},
        },
    },
    "gpt-create": {
        "label": "изображение",
        "model": "wavespeed-gpt",  # Используем специальный маркер для WaveSpeedAI GPT
        "base": {
            "output_format": "png",
        },
        "sizes": {
            # nano-banana-pro поддерживает только квадратные форматы
            "square": {"size": "2048x2048", "aspect_ratio": "1:1", "width": 2048, "height": 2048},
        },
    },
}

SIZE_BUTTONS = {
    IMAGE_SIZE_VERTICAL_BUTTON.lower(): "vertical",
    IMAGE_SIZE_SQUARE_BUTTON.lower(): "square",
    IMAGE_SIZE_HORIZONTAL_BUTTON.lower(): "horizontal",
}
RETOUCHER_MODE_BUTTONS = {
    RETOUCHER_SOFT_BUTTON.lower(): "soft",
    RETOUCHER_ENHANCE_BUTTON.lower(): "enhance",
}
RETOUCHER_SKIP_VALUES = {"", RETOUCHER_SKIP_BUTTON.lower(), "готово", "done", "skip"}


def _build_notify_options(message: types.Message, prompt: str, base: Dict[str, Any] | None = None) -> Dict[str, Any]:
    options: Dict[str, Any] = dict(base or {})
    if message.chat:
        options["notify_chat_id"] = message.chat.id
        if getattr(message.chat, "linked_chat_id", None):
            options["notify_linked_chat_id"] = message.chat.linked_chat_id
    if message.message_thread_id:
        options["notify_message_thread_id"] = message.message_thread_id
    if message.message_id:
        options["notify_reply_to_message_id"] = message.message_id
    options["notify_prompt"] = prompt
    return options


async def _enqueue_image_task(
    message: types.Message,
    prompt: str,
    label: str,
    base_options: Dict[str, Any] | None = None,
) -> str:
    import asyncio
    # Очищаем промпт от возможных префиксов "Промпт: " или "Prompt: "
    prompt = prompt.strip()
    if prompt.lower().startswith("промпт:"):
        prompt = prompt[7:].strip()
    elif prompt.lower().startswith("prompt:"):
        prompt = prompt[7:].strip()
    
    logger.info("_enqueue_image_task: starting, prompt='{}', label='{}', base_options={}", 
                prompt[:50], label, base_options)
    if base_options:
        logger.info("_enqueue_image_task: base_options keys: {}, width: {}, height: {}, num_inference_steps: {}", 
                   list(base_options.keys()), base_options.get("width"), base_options.get("height"), base_options.get("num_inference_steps"))
    options = _build_notify_options(message, prompt, base_options)
    
    # Проверяем, является ли модель Nano-banana (может принимать русский текст)
    model = base_options.get("model") if base_options else None
    is_nano_banana = model == IMAGE_STANDARD_MODEL or model == "fal-ai/nano-banana"
    
    translated_prompt = prompt  # Default to original prompt
    if is_nano_banana:
        logger.info("_enqueue_image_task: skipping translation for Nano-banana model, using original Russian prompt")
    else:
        logger.info("_enqueue_image_task: calling translate_to_english in executor")
        try:
            # Выполняем синхронный перевод в отдельном потоке с таймаутом, чтобы не блокировать event loop
            # Увеличено до 10 секунд для более надежного перевода
            translated_prompt = await asyncio.wait_for(
                asyncio.to_thread(translate_to_english, prompt),
                timeout=10.0  # Таймаут 10 секунд для перевода
            )
            logger.info("_enqueue_image_task: translate_to_english completed, translated='{}'", 
                        translated_prompt[:50] if translated_prompt else None)
        except asyncio.TimeoutError:
            logger.warning("_enqueue_image_task: translate_to_english timed out after 10s, retrying once...")
            # Попробуем еще раз с меньшим таймаутом
            try:
                translated_prompt = await asyncio.wait_for(
                    asyncio.to_thread(translate_to_english, prompt),
                    timeout=5.0
                )
                logger.info("_enqueue_image_task: translate_to_english succeeded on retry, translated='{}'", 
                            translated_prompt[:50] if translated_prompt else None)
            except (asyncio.TimeoutError, Exception) as retry_exc:
                logger.error("_enqueue_image_task: translate_to_english failed on retry: {}, using original prompt", retry_exc)
                translated_prompt = prompt  # Fallback to original prompt
        except Exception as exc:
            logger.error("_enqueue_image_task: translate_to_english failed: {}, using original prompt", exc, exc_info=True)
            translated_prompt = prompt  # Fallback to original prompt
    
    # Всегда устанавливаем provider_prompt, даже если перевод не сработал
    # Это позволяет worker'у видеть, что перевод был попытка
    options["provider_prompt"] = translated_prompt
    logger.info("_enqueue_image_task: calling enqueue_image with prompt='{}'", prompt[:50])
    job_id, _ = enqueue_image(prompt=prompt, **options)
    logger.info("_enqueue_image_task: enqueue_image returned job_id='{}'", job_id)
    if message.chat:
        LAST_JOB_BY_CHAT[message.chat.id] = job_id
    logger.info("_enqueue_image_task: sending 'Генерирую' message to chat_id={}", 
                message.chat.id if message.chat else None)
    await message.answer(f"🚀 Генерирую: {label}\nПромпт: {prompt}", reply_markup=build_main_keyboard())
    logger.info("_enqueue_image_task: 'Генерирую' message sent successfully")
    return job_id


async def _enqueue_image_edit_task(
    message: types.Message,
    prompt: str,
    image_path: Path,
    mask_path: Path | None = None,
    base_options: Dict[str, Any] | None = None,
) -> str:
    import asyncio
    logger.info("_enqueue_image_edit_task: starting, prompt='{}', image_path='{}', base_options={}", 
                prompt[:50], image_path, base_options)
    base_payload = dict(base_options or {})
    base_payload.setdefault("model", IMAGE_EDIT_MODEL)
    options = _build_notify_options(message, prompt, base_payload)
    logger.info("_enqueue_image_edit_task: calling translate_to_english in executor")
    try:
        # Выполняем синхронный перевод в отдельном потоке с таймаутом, чтобы не блокировать event loop
        translated_prompt = await asyncio.wait_for(
            asyncio.to_thread(translate_to_english, prompt),
            timeout=5.0  # Таймаут 5 секунд для перевода
        )
        logger.info("_enqueue_image_edit_task: translate_to_english completed, translated='{}'", 
                    translated_prompt[:50] if translated_prompt else None)
    except asyncio.TimeoutError:
        logger.warning("_enqueue_image_edit_task: translate_to_english timed out after 5s, using original prompt")
        translated_prompt = prompt  # Fallback to original prompt
    except Exception as exc:
        logger.error("_enqueue_image_edit_task: translate_to_english failed: {}", exc, exc_info=True)
        translated_prompt = prompt  # Fallback to original prompt

    logger.info("_enqueue_image_edit_task: building reinforcement prompt")
    reinforcement_parts: list[str] = []
    lowered = translated_prompt.lower()
    if any(keyword in lowered for keyword in ("remove", "delete", "erase", "удали", "убери", "стереть")):
        reinforcement_parts.append(
            "Remove the specified content completely. The area must be clean, empty, and seamlessly blended."
        )
    if any(keyword in lowered for keyword in ("add", "place", "insert", "добав", "помест", "встав")):
        reinforcement_parts.append(
            "Add the requested content clearly and in high detail. It must be fully visible and match the scene."
        )
        # Специальная обработка для добавления людей
        if any(keyword in lowered for keyword in ("person", "человек", "люди", "человека", "мужчин", "женщин", "хозяин", "owner")):
            if any(keyword in lowered for keyword in ("full", "полный", "рост", "стоя", "стоит", "стоящий")):
                reinforcement_parts.append(
                    "The person must be shown in full height, standing upright, with their entire body visible from head to feet. "
                    "Maintain realistic proportions and natural human scale relative to other objects in the scene."
                )
    if "replace" in lowered or "замен" in lowered:
        reinforcement_parts.append(
            "Replace the target element entirely and ensure the new content fits naturally with proper lighting and perspective."
        )

    reinforcement_instruction = " ".join(reinforcement_parts).strip()
    logger.info("_enqueue_image_edit_task: reinforcement_instruction='{}'", reinforcement_instruction[:100] if reinforcement_instruction else None)

    enforcement_suffix = (
        "You must strictly follow every part of the user's request. "
        "Ensure the output fully reflects all changes."
    )

    enhanced_prompt_lines = [translated_prompt]
    if reinforcement_instruction:
        enhanced_prompt_lines.append(reinforcement_instruction)
    enhanced_prompt_lines.append(enforcement_suffix)
    enforced_prompt = "\n".join(enhanced_prompt_lines)
    logger.info("_enqueue_image_edit_task: enforced_prompt built, length={}", len(enforced_prompt))

    if enforced_prompt != prompt:
        options["provider_prompt"] = enforced_prompt
    logger.info("_enqueue_image_edit_task: calling enqueue_image_edit with prompt='{}', image_path='{}', model='{}'", 
                prompt[:50], image_path, base_payload.get("model"))
    try:
        job_id, _ = enqueue_image_edit(
            prompt=prompt,
            image_path=image_path.as_posix(),
            mask_path=mask_path.as_posix() if mask_path else None,
            **options,
        )
        logger.info("_enqueue_image_edit_task: enqueue_image_edit returned job_id='{}'", job_id)
    except Exception as exc:
        logger.error("_enqueue_image_edit_task: enqueue_image_edit failed: {}", exc, exc_info=True)
        raise
    if message.chat:
        LAST_JOB_BY_CHAT[message.chat.id] = job_id
    logger.info(
        "_enqueue_image_edit_task: Queued edit job {} for user {} (source: {}, mask: {})",
        job_id,
        message.from_user.id if message.from_user else "unknown",
        image_path,
        mask_path,
    )
    await message.answer(
        f"🛠️ Редактирую изображение\nПромпт: {prompt}",
        reply_markup=build_main_keyboard(),
    )
    return job_id


def _generate_edit_path(suffix: str = ".png") -> Path:
    filename = f"{uuid4().hex}{suffix}"
    destination = storage.base_dir / "edits" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


async def _download_message_image(message: types.Message) -> Path | None:
    try:
        if message.photo:
            file = message.photo[-1]
            suffix = ".png"
            target = _generate_edit_path(suffix)
            logger.debug("Downloading photo: file_id={}, target={}", file.file_id, target)
            await message.bot.download(file, destination=target)
            logger.debug("Photo downloaded successfully: {}", target)
            return target
        if message.document:
            document = message.document
            if document.mime_type and not document.mime_type.startswith("image"):
                await message.answer("Пожалуйста, отправьте изображение (PNG/JPEG).")
                return None
            suffix = Path(document.file_name or "").suffix or ".png"
            target = _generate_edit_path(suffix)
            logger.debug("Downloading document: file_id={}, mime_type={}, target={}", document.file_id, document.mime_type, target)
            await message.bot.download(document, destination=target)
            logger.debug("Document downloaded successfully: {}", target)
            return target
        logger.warning("No photo or document found in message")
        return None
    except Exception as exc:
        logger.error("Error downloading image: {}", exc, exc_info=True)
        return None


def _enhance_smart_merge_prompt(prompt: str, image_count: int = 0) -> str:
    """
    Улучшает промпт для Smart merge, добавляя инструкции о пропорциях и использовании всех изображений.
    """
    prompt_lower = prompt.lower()
    
    # Проверяем, есть ли уже конкретные инструкции о пропорциях или размерах
    has_explicit_proportions = any(phrase in prompt_lower for phrase in [
        "realistic proportions", "natural size", "correct scale", 
        "life-size", "proper scale", "real-world", "accurate size"
    ])
    
    enhancements = []
    
    # Если несколько изображений, ВСЕГДА добавляем явную инструкцию использовать ВСЕ изображения
    # Это критично для правильного объединения нескольких объектов
    if image_count > 1:
        # Проверяем, есть ли уже очень явная инструкция об использовании всех изображений
        has_explicit_all_images = any(phrase in prompt_lower for phrase in [
            "include all", "use all", "all images", "all photos", "all pictures",
            "все изображения", "все фото", "все картинки", "используй все",
            "from each image", "from all images", "each person from", "каждого человека из"
        ])
        
        # Проверяем, упоминает ли промпт людей
        mentions_people = any(word in prompt_lower for word in [
            "people", "person", "человек", "люди", "людей"
        ])
        
        if not has_explicit_all_images:
            if mentions_people:
                # Для людей добавляем более конкретную инструкцию
                enhancements.append(f"CRITICAL: extract and include each person from each of the {image_count} provided images - do not generate new people, use only the people shown in the input images")
            else:
                # Для других объектов добавляем общую инструкцию
                enhancements.append(f"IMPORTANT: use all {image_count} provided images in the final composition")
    
    # Добавляем инструкцию о пропорциях, если её нет
    if not has_explicit_proportions:
        enhancements.append("maintain realistic proportions and natural sizes")
    
    if enhancements:
        enhanced = f"{prompt}. {', '.join(enhancements)}."
        return enhanced
    
    return prompt


def _parse_smart_merge_input(text: str) -> tuple[str, dict[str, str]]:
    working = text.strip()
    if working.lower().startswith("smart merge"):
        working = working[len("smart merge") :].strip()

    if not working:
        return "", {}

    parts = [part.strip() for part in working.split("|")]
    parts = [part for part in parts if part]
    if not parts:
        return "", {}

    prompt = parts[0]
    options: dict[str, str] = {}
    for part in parts[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue
        if key in {"model", "size", "aspect_ratio"}:
            options[key] = value
    return prompt, options


def _build_smart_merge_base_options(overrides: dict[str, str] | None = None) -> Dict[str, Any]:
    overrides = overrides or {}
    options: Dict[str, Any] = {
        "model": overrides.get("model") or SMART_MERGE_DEFAULT_MODEL,
        "size": overrides.get("size") or SMART_MERGE_DEFAULT_SIZE,
        "aspect_ratio": overrides.get("aspect_ratio") or SMART_MERGE_DEFAULT_ASPECT_RATIO,
    }
    return options


async def _ensure_job_source_path(job_id: str) -> Path | None:
    job = get_job(job_id)
    if not job:
        return None
    meta = job.meta or {}
    stored_path = meta.get("result_path")
    if stored_path:
        path = Path(stored_path)
        if path.exists():
            return path
    image_url = meta.get("image_url")
    if image_url:
        target = _generate_edit_path(".png")
        try:
            download_file(image_url, target.as_posix())
            return target
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to download image {} for edit job {}: {}", image_url, job_id, exc)
    return None


async def _trigger_upscale_for_job(message: types.Message, job_id: str) -> bool:
    job = get_job(job_id)
    if not job:
        await message.answer(
            "Последняя задача не найдена. Сгенерируйте изображение ещё раз.",
            reply_markup=build_main_keyboard(),
        )
        return False
    if job.get_status() != "finished":
        await message.answer(
            "Последняя задача ещё выполняется. Дождитесь завершения и попробуйте снова.",
            reply_markup=build_main_keyboard(),
        )
        return False
    meta = job.meta or {}
    image_url = meta.get("image_url")
    image_path = meta.get("result_path")
    if image_path and not Path(image_path).exists():
        image_path = None
    if not image_path:
        output_path = job.kwargs.get("output_path")
        if output_path and Path(output_path).exists():
            image_path = output_path
    if not image_url and not image_path:
        await message.answer(
            "Не удалось получить ссылку на изображение для апскейла.",
            reply_markup=build_main_keyboard(),
        )
        return False

    prompt = meta.get("prompt") or meta.get("provider_prompt") or "Upscale"
    options = _build_notify_options(message, prompt)
    # Убираем промпт из уведомления для upscale
    options["notify_prompt"] = ""
    options["source_job_id"] = job_id

    new_job_id, _ = enqueue_image_upscale(
        image_url=image_url if not image_path else None,
        image_path=image_path,
        scale=2,
        **options,
    )
    if message.chat:
        LAST_JOB_BY_CHAT[message.chat.id] = new_job_id

    await message.answer("🔍 Запускаю апскейл последнего изображения...", reply_markup=build_main_keyboard())
    return True


async def _clear_upscale_state(state: FSMContext) -> None:
    await state.update_data({UPSCALE_STAGE_KEY: None, UPSCALE_LAST_JOB_KEY: None})


async def _clear_retoucher_state(state: FSMContext) -> None:
    await state.update_data(
        {
            RETOUCHER_STAGE_KEY: None,
            RETOUCHER_SOURCE_PATH_KEY: None,
            RETOUCHER_MODE_KEY: None,
            RETOUCHER_PROMPT_KEY: None,
        }
    )


async def _handle_upscale_text(message: types.Message, state: FSMContext, text: str) -> None:
    lowered = text.strip().lower()
    if lowered in {"последнее", "last", "latest"}:
        data = await state.get_data()
        job_id = data.get(UPSCALE_LAST_JOB_KEY)
        if not job_id and message.chat:
            job_id = LAST_JOB_BY_CHAT.get(message.chat.id)
        if not job_id:
            await message.answer(
                "Нет последнего изображения для апскейла. Отправьте файл вручную.",
                reply_markup=build_main_keyboard(),
            )
            return
        triggered = await _trigger_upscale_for_job(message, job_id)
        if triggered:
            await _clear_upscale_state(state)
        return

    await message.answer(
        "Не понял команду. Отправьте изображение или напишите «последнее».",
        reply_markup=build_main_keyboard(),
    )


async def _enqueue_retoucher_task(
    message: types.Message,
    state: FSMContext,
    *,
    mode: str,
    instruction: str | None,
) -> bool:
    data = await state.get_data()
    source_raw = data.get(RETOUCHER_SOURCE_PATH_KEY)
    if not source_raw:
        await message.answer(
            "Не удалось найти изображение для ретуши. Отправьте файл ещё раз.",
            reply_markup=build_main_keyboard(),
        )
        await _clear_retoucher_state(state)
        return False

    source_path = Path(source_raw)
    if not source_path.exists():
        await message.answer(
            "Исходный файл отсутствует. Отправьте изображение снова.",
            reply_markup=build_main_keyboard(),
        )
        await _clear_retoucher_state(state)
        return False

    preset = RETOUCHER_MODE_PRESETS.get(mode)
    if not preset:
        logger.error("Unsupported retoucher mode requested: {}", mode)
        await message.answer(
            "Не удалось определить режим ретуши. Попробуйте начать заново.",
            reply_markup=build_main_keyboard(),
        )
        await _clear_retoucher_state(state)
        return False

    instruction_clean = (instruction or "").strip()
    display_prompt = preset["label"]
    if instruction_clean:
        display_prompt = f"{display_prompt} · {instruction_clean}"

    provider_prompt = preset["base_prompt"]
    if instruction_clean:
        import asyncio
        logger.info("_enqueue_retoucher_task: calling translate_to_english in executor for instruction='{}'", instruction_clean[:50])
        try:
            # Выполняем синхронный перевод в отдельном потоке с таймаутом, чтобы не блокировать event loop
            translated_instruction = await asyncio.wait_for(
                asyncio.to_thread(translate_to_english, instruction_clean),
                timeout=5.0  # Таймаут 5 секунд для перевода
            )
            logger.info("_enqueue_retoucher_task: translate_to_english completed, translated='{}'", 
                        translated_instruction[:50] if translated_instruction else None)
        except asyncio.TimeoutError:
            logger.warning("_enqueue_retoucher_task: translate_to_english timed out after 5s, using original instruction")
            translated_instruction = instruction_clean  # Fallback to original instruction
        except Exception as exc:
            logger.error("_enqueue_retoucher_task: translate_to_english failed: {}", exc, exc_info=True)
            translated_instruction = instruction_clean  # Fallback to original instruction
        
        if translated_instruction != instruction_clean:
            instruction_clean_provider = translated_instruction
        else:
            instruction_clean_provider = instruction_clean
        provider_prompt = f"{provider_prompt}\nAdditional instruction: {instruction_clean_provider}"

    # Merge base_options from preset with notify options
    base_options = preset.get("base_options", {})
    options = _build_notify_options(message, display_prompt, base_options)
    if provider_prompt != display_prompt:
        options["provider_prompt"] = provider_prompt

    try:
        job_id, _ = enqueue_retoucher(
            prompt=display_prompt,
            image_path=source_path.as_posix(),
            mode=mode,
            instruction=instruction_clean or None,
            **options,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to enqueue retoucher job: {}", exc)
        await message.answer(
            "Не удалось отправить запрос на ретушь. Попробуйте позже.",
            reply_markup=build_main_keyboard(),
        )
        return False

    if message.chat:
        LAST_JOB_BY_CHAT[message.chat.id] = job_id

    notify_lines = [preset.get("notify_text") or "✨ Запускаю ретушь..."]
    notify_lines.append(f"Промпт: {display_prompt}")
    await message.answer(
        "\n".join(notify_lines),
        reply_markup=build_main_keyboard(),
    )
    await _clear_retoucher_state(state)
    return True


async def _handle_retoucher_text(
    message: types.Message,
    state: FSMContext,
    stage: str,
    text: str,
) -> None:
    stripped = (text or "").strip()
    lowered = stripped.lower()

    if stage == "await_image":
        await message.answer(
            "Отправьте фотографию лица, чтобы запустить ретушь.",
            reply_markup=build_main_keyboard(),
        )
        return

    if stage == "await_mode":
        logger.info("_handle_retoucher_text: stage=await_mode, text='{}', lowered='{}', RETOUCHER_MODE_BUTTONS={}", 
                    text, lowered, RETOUCHER_MODE_BUTTONS)
        mode = RETOUCHER_MODE_BUTTONS.get(lowered)
        logger.info("_handle_retoucher_text: mode='{}'", mode)
        if not mode:
            logger.warning("_handle_retoucher_text: mode not found for text '{}' (lowered: '{}')", text, lowered)
            await message.answer(
                "Выберите один из режимов ретуши.",
                reply_markup=build_retoucher_mode_keyboard(),
            )
            return
        logger.info("_handle_retoucher_text: selected mode='{}', updating state", mode)
        await state.update_data(
            {
                RETOUCHER_MODE_KEY: mode,
                RETOUCHER_STAGE_KEY: "await_instruction",
            }
        )
        await message.answer(
            "Опишите пожелания (опционально) или нажмите «Пропустить».",
            reply_markup=build_retoucher_instruction_keyboard(),
        )
        return

    if stage == "await_instruction":
        logger.info("_handle_retoucher_text: stage=await_instruction, text='{}', lowered='{}'", text, lowered)
        data = await state.get_data()
        mode = data.get(RETOUCHER_MODE_KEY)
        logger.info("_handle_retoucher_text: mode='{}'", mode)
        if not mode:
            logger.warning("_handle_retoucher_text: mode not found in state")
            await message.answer(
                "Режим ретуши не выбран. Начните заново с кнопки «✨ Ретушь».",
                reply_markup=build_main_keyboard(),
            )
            await _clear_retoucher_state(state)
            return
        instruction_value = None
        if lowered not in RETOUCHER_SKIP_VALUES:
            instruction_value = stripped
        logger.info("_handle_retoucher_text: calling _enqueue_retoucher_task with mode='{}', instruction='{}'", 
                    mode, instruction_value[:50] if instruction_value else None)
        try:
            queued = await _enqueue_retoucher_task(
                message,
                state,
                mode=mode,
                instruction=instruction_value,
            )
            logger.info("_handle_retoucher_text: _enqueue_retoucher_task returned queued={}", queued)
        except Exception as exc:
            logger.error("_handle_retoucher_text: error calling _enqueue_retoucher_task: {}", exc, exc_info=True)
            await message.answer(
                "Произошла ошибка при постановке задачи в очередь. Попробуйте снова.",
                reply_markup=build_main_keyboard(),
            )
            return
        if not queued:
            await state.update_data({RETOUCHER_STAGE_KEY: "await_instruction"})
        return

    await message.answer(
        "Режим ретуши сброшен. Нажмите «✨ Ретушь», чтобы начать заново.",
        reply_markup=build_main_keyboard(),
    )
    await _clear_retoucher_state(state)


async def _reset_state(state: FSMContext) -> None:
    await state.clear()


async def _set_edit_stage(state: FSMContext, stage: str | None) -> None:
    await state.update_data({EDIT_STAGE_KEY: stage})


async def _handle_edit_text(message: types.Message, state: FSMContext, stage: str, text: str) -> None:
    if stage == "await_prompt":
        if len(text) < MIN_PROMPT_LENGTH:
            await message.answer("Промпт слишком короткий. Пожалуйста, уточните запрос.")
            return
        data = await state.get_data()
        source_raw = data.get(EDIT_SOURCE_PATH_KEY)
        if not source_raw:
            await message.answer("Не удалось найти исходное изображение. Загрузите файл ещё раз.")
            await state.clear()
            return
        source_path = Path(source_raw)
        if not source_path.exists():
            await message.answer("Исходный файл недоступен. Отправьте изображение снова.")
            await state.clear()
            return
        await state.update_data(
            {
                EDIT_PROMPT_KEY: text,
                EDIT_STAGE_KEY: "await_model",
            }
        )
        await message.answer(
            "Отлично! Теперь выберите модель редактирования:\n"
            "• Chrono Edit — максимально реалистичное удаление/смена объектов\n"
            "• Seedream — новое поколение ByteDance, лучше добавляет персонажей и текст\n"
            "Если передумаете, нажмите «ℹ️ Info» для сброса.",
            reply_markup=build_edit_model_keyboard(),
        )
        return
    if stage == "await_model":
        # Проверяем, является ли текст кнопкой выбора модели
        text_lower = text.lower()
        if text_lower == IMAGE_EDIT_CHRONO_BUTTON.lower() or text_lower == IMAGE_EDIT_SEDEDIT_BUTTON.lower():
            logger.info("_handle_edit_text: in await_model stage, detected model button '{}', calling handle_edit_model_choice", text)
            await handle_edit_model_choice(message, state, ignore_stage_check=True)
        else:
            logger.warning("_handle_edit_text: in await_model stage, but text '{}' is not a model button", text)
            await message.answer(
                "Пожалуйста, выберите модель редактирования из предложенных кнопок: Chrono Edit или Seedream.",
                reply_markup=build_edit_model_keyboard(),
            )
        return

    if stage == "await_mask":
        await message.answer("Редактирование уже запущено. Для нового запроса нажмите «ℹ️ Info».")
        return

    if stage == "await_source":
        await message.answer("Сначала отправьте изображение, которое нужно изменить.")
        return


async def _require_prompt(message: types.Message, state: FSMContext) -> str | None:
    data = await state.get_data()
    if data.get(EDIT_STAGE_KEY):
        await message.answer(
            "Сейчас активен режим редактирования. Завершите его или нажмите «ℹ️ Info» для сброса.",
            reply_markup=build_main_keyboard(),
        )
        return None
    prompt = data.get("prompt")
    if not prompt:
        await message.answer(NO_PROMPT_TEXT, reply_markup=build_main_keyboard())
        return None
    return prompt


async def handle_create(message: types.Message, state: FSMContext) -> None:
    """Обработчик кнопки 'Создать' - показывает выбор моделей."""
    data = await state.get_data()
    prompt = data.get("prompt")
    
    # Устанавливаем режим создания для обработки ввода промпта
    await state.update_data(create_stage="await_prompt")
    
    # Если промпт уже есть в состоянии, показываем выбор моделей
    if prompt:
        await state.update_data(selected_model=None)
        await message.answer(
            MODELS_DESCRIPTION_TEXT,
            reply_markup=build_create_model_keyboard(),
        )
    else:
        # Если промпта нет, просим его ввести
        await message.answer(
            NO_PROMPT_TEXT,
            reply_markup=build_main_keyboard(),
        )


async def handle_standard(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора модели Nano-banana после нажатия 'Создать'."""
    # Проверяем, не находимся ли мы в режиме Smart merge
    data = await state.get_data()
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    if smart_merge_stage:
        # Если мы в режиме Smart merge, не обрабатываем выбор модели для создания
        # Просто возвращаемся без ответа, чтобы следующий обработчик мог обработать
        logger.debug("handle_standard: ignoring because smart_merge_stage='{}' is active, letting other handlers process", 
                    smart_merge_stage)
        return
    
    prompt = await _require_prompt(message, state)
    if not prompt:
        logger.warning("handle_standard: prompt not found in state for user {}", 
                      message.from_user.id if message.from_user else "unknown")
        return
    logger.info("handle_standard: prompt found: '{}', saving selected_model='standard'", prompt[:50])
    await state.update_data(selected_model="standard", prompt=prompt)
    await message.answer(
        "Вы выбрали Nano-banana. Какой формат нужен?",
        reply_markup=build_size_keyboard(),
    )


async def handle_seedream_create(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора модели Seedream (Create) после нажатия 'Создать'."""
    data = await state.get_data()
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    if smart_merge_stage:
        logger.debug("handle_seedream_create: ignoring because smart_merge_stage is active")
        return
    
    prompt = await _require_prompt(message, state)
    if not prompt:
        logger.warning("handle_seedream_create: prompt not found in state for user {}", 
                      message.from_user.id if message.from_user else "unknown")
        return
    logger.info("handle_seedream_create: prompt found: '{}', saving selected_model='seedream-create'", prompt[:50])
    await state.update_data(selected_model="seedream-create", prompt=prompt)
    await message.answer(
        "Вы выбрали Seedream (Create). Уточните формат изображения:",
        reply_markup=build_size_keyboard(),
    )


async def handle_gpt_create(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора модели Nano Banana Pro после нажатия 'Создать'."""
    import asyncio
    import re

    data = await state.get_data()
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    if smart_merge_stage:
        logger.debug("handle_gpt_create: ignoring because smart_merge_stage is active")
        return

    prompt = await _require_prompt(message, state)
    if not prompt:
        logger.warning("handle_gpt_create: prompt not found in state for user {}",
                      message.from_user.id if message.from_user else "unknown")
        return

    # Nano Banana Pro поддерживает кириллицу напрямую, не нужно переводить
    # Просто добавляем инструкцию о четкости кириллического текста
    enhanced_prompt = f"{prompt}. Важно: весь текст на изображении должен быть на кириллице (русский алфавит), четко и читаемо."

    logger.info("handle_gpt_create: prompt found: '{}', enhanced: '{}'", prompt[:50], enhanced_prompt[:100])
    await state.update_data(selected_model="gpt-create", prompt=enhanced_prompt)

    # nano-banana-pro поддерживает только квадратный формат, запускаем сразу
    await message.answer("🔄 Генерирую изображение через Nano Banana Pro...")
    
    # Используем enqueue_image для постановки задачи в очередь с квадратным форматом
    job_id, _ = enqueue_image(
        prompt=enhanced_prompt,
        selected_model="gpt-create",
        width=2048,
        height=2048,
        aspect_ratio="1:1",
        output_format="png",
        notify_chat_id=message.chat.id,
        notify_reply_to_message_id=message.message_id,
    )

    logger.info("GPT create job enqueued: job_id={}, prompt_length={}", job_id, len(enhanced_prompt))
    await state.clear()


async def handle_size_choice(message: types.Message, state: FSMContext) -> None:
    logger.info("handle_size_choice called: text='{}'", message.text)
    selection = (message.text or "").strip().lower()
    logger.info("handle_size_choice: selection='{}', SIZE_BUTTONS={}", selection, SIZE_BUTTONS)
    size_key = SIZE_BUTTONS.get(selection)
    logger.info("handle_size_choice: size_key='{}'", size_key)
    if not size_key:
        logger.warning("handle_size_choice: size_key not found for selection '{}'", selection)
        return

    data = await state.get_data()
    prompt: str | None = data.get("prompt")
    model_key: str | None = data.get("selected_model")
    logger.info("handle_size_choice: prompt='{}', model_key='{}'", prompt[:50] if prompt else None, model_key)

    if not prompt or not model_key:
        logger.warning("handle_size_choice: missing prompt or model_key")
        await message.answer("Сначала напишите промпт и выберите модель.", reply_markup=build_main_keyboard())
        await state.clear()
        return

    preset = MODEL_PRESETS.get(model_key)
    if not preset:
        logger.error("handle_size_choice: preset not found for model_key='{}'", model_key)
        await message.answer("Не удалось определить модель. Повторите запрос.", reply_markup=build_main_keyboard())
        await state.clear()
        return

    size_options = preset["sizes"].get(size_key)
    if not size_options:
        logger.error("handle_size_choice: size_options not found for size_key='{}', preset={}", size_key, preset)
        await message.answer("Не удалось определить формат. Попробуйте снова.", reply_markup=build_size_keyboard())
        return

    base_options = {
        "model": preset["model"],
        "selected_model": model_key,  # Добавляем selected_model для правильной обработки gpt-create
        **preset["base"],
        **size_options,
    }
    label = f"{preset['label']} · {message.text.strip()}"
    logger.info("handle_size_choice: calling _enqueue_image_task with prompt='{}', label='{}', model='{}'", 
                prompt[:50], label, preset["model"])
    try:
        await _enqueue_image_task(
            message,
            prompt=prompt,
            label=label,
            base_options=base_options,
        )
        logger.info("handle_size_choice: _enqueue_image_task completed successfully")
    except Exception as exc:
        logger.error("handle_size_choice: error calling _enqueue_image_task: {}", exc, exc_info=True)
        await message.answer("Произошла ошибка при постановке задачи в очередь. Попробуйте снова.", 
                           reply_markup=build_main_keyboard())
        return
    await state.clear()


async def _enqueue_smart_merge_task(
    message: types.Message,
    state: FSMContext,
    *,
    prompt: str,
    sources: list[dict[str, str | None]],
    options_override: dict[str, str] | None = None,
) -> str:
    # Получаем выбранную модель из состояния, если она есть
    data = await state.get_data()
    selected_model = data.get(SMART_MERGE_MODEL_KEY)
    
    # Если модель выбрана через кнопку, используем её (если не переопределена в options_override)
    if selected_model and (not options_override or "model" not in options_override):
        options_override = options_override or {}
        options_override["model"] = selected_model
    
    base_options = _build_smart_merge_base_options(options_override)
    options = _build_notify_options(message, prompt, base_options)
    
    # Проверяем, является ли модель Nano-banana (может принимать русский текст)
    model = base_options.get("model") if base_options else None
    is_nano_banana = model == SMART_MERGE_DEFAULT_MODEL or model == "fal-ai/nano-banana" or model == "fal-ai/nano-banana/edit"
    
    # Переводим промпт только если это не Nano-banana
    if is_nano_banana:
        logger.info("Smart merge: skipping translation for Nano-banana model, using original Russian prompt")
        provider_prompt = prompt  # Используем оригинальный русский промпт
    else:
        # Переводим промпт асинхронно, чтобы не блокировать event loop
        try:
            provider_prompt = await asyncio.wait_for(
                asyncio.to_thread(translate_to_english, prompt),
                timeout=5.0  # Таймаут 5 секунд для перевода
            )
        except asyncio.TimeoutError:
            logger.warning("Smart merge: translate_to_english timed out after 5s for prompt '{}', using original prompt", prompt[:50])
            provider_prompt = prompt  # Fallback to original prompt
        except Exception as exc:
            logger.error("Smart merge: translate_to_english failed: {}, using original prompt", exc, exc_info=True)
            provider_prompt = prompt  # Fallback to original prompt
    
    # Улучшаем промпт только если пользователь не отключил это явно
    # Можно отключить через параметр: "промпт | no_enhance=true"
    if not options_override or options_override.get("no_enhance", "").lower() != "true":
        image_count = len(sources)
        enhanced_prompt = _enhance_smart_merge_prompt(provider_prompt, image_count)
    else:
        enhanced_prompt = provider_prompt
    
    logger.info(
        "Smart merge: original prompt='{}', translated prompt='{}', enhanced prompt='{}', images={}, model={}",
        prompt,
        provider_prompt,
        enhanced_prompt,
        len(sources),
        base_options.get("model", "default"),
    )
    options["provider_prompt"] = enhanced_prompt

    job_id, _ = enqueue_smart_merge(
        prompt=prompt,
        image_sources=sources[:SMART_MERGE_MAX_IMAGES],
        **options,
    )
    if message.chat:
        LAST_JOB_BY_CHAT[message.chat.id] = job_id
    logger.debug(
        "Queued smart merge job {} for user {} (images={})",
        job_id,
        message.from_user.id if message.from_user else "unknown",
        len(sources),
    )
    await message.answer(
        "🔗 Запускаю объединение изображений.\nМы объединяем изображения в единую сцену.",
        reply_markup=build_main_keyboard(),
    )
    return job_id


async def handle_edit_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data({EDIT_STAGE_KEY: "await_source"})
    await message.answer(
        "Загрузите изображение, которое нужно отредактировать (как фото или документ).\n"
        "Если хотите изменить недавно сгенерированное изображение — нажмите кнопку «Редактировать» под ним.",
        reply_markup=build_main_keyboard(),
    )


async def handle_edit_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not callback.data or not callback.data.startswith("edit:"):
        return
    job_id = callback.data.split(":", 1)[1]
    await callback.answer()
    await state.clear()
    source_path = await _ensure_job_source_path(job_id)
    if not source_path:
        await callback.message.answer(
            "Не удалось получить файл для редактирования. Сохраните изображение и отправьте его вручную через «✏️ Редактировать».",
            reply_markup=build_main_keyboard(),
        )
        return
    await state.update_data(
        {
            EDIT_STAGE_KEY: "await_prompt",
            EDIT_SOURCE_PATH_KEY: source_path.as_posix(),
            EDIT_SOURCE_JOB_ID: job_id,
        }
    )
    await callback.message.answer(
        "Изображение добавлено в режим редактирования ✅\nОпишите, какие изменения нужно внести.",
        reply_markup=build_main_keyboard(),
    )


async def handle_upscale_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    if not callback.data or not callback.data.startswith("upscale:"):
        return
    job_id = callback.data.split(":", 1)[1]
    if callback.message:
        triggered = await _trigger_upscale_for_job(callback.message, job_id)
        if triggered:
            await callback.answer("Апскейл запущен!", show_alert=False)
        else:
            await callback.answer("Не удалось запустить апскейл.", show_alert=True)


async def handle_upscale_button(message: types.Message, state: FSMContext) -> None:
    if not message.chat:
        return
    last_job_id = LAST_JOB_BY_CHAT.get(message.chat.id)
    
    await state.update_data(
        {
            UPSCALE_STAGE_KEY: "await_source",
            UPSCALE_LAST_JOB_KEY: last_job_id,
        }
    )
    await message.answer(
        "Отправьте изображение, которое нужно улучшить.",
        reply_markup=build_main_keyboard(),
    )


async def handle_prompt_input(message: types.Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    
    # Сразу пропускаем кнопки главного меню, чтобы они обрабатывались другими обработчиками
    from app.bot.keyboards.main import (
        CREATE_BUTTON,
        IMAGE_EDIT_BUTTON,
        IMAGE_SMART_MERGE_BUTTON,
        IMAGE_RETOUCHER_BUTTON,
        IMAGE_STYLISH_TEXT_BUTTON,
        IMAGE_FACE_SWAP_BUTTON,
        IMAGE_UPSCALE_BUTTON,
        INFO_BUTTON,
    )
    main_menu_buttons = {
        CREATE_BUTTON,
        IMAGE_EDIT_BUTTON,
        IMAGE_SMART_MERGE_BUTTON,
        IMAGE_RETOUCHER_BUTTON,
        IMAGE_STYLISH_TEXT_BUTTON,
        IMAGE_FACE_SWAP_BUTTON,
        IMAGE_UPSCALE_BUTTON,
        INFO_BUTTON,
    }
    if text in main_menu_buttons:
        # Пропускаем обработку, чтобы другие обработчики могли обработать кнопку
        return
    
    data = await state.get_data()

    # Проверяем, выбран ли режим работы
    selected_model = data.get("selected_model")
    create_stage = data.get(CREATE_STAGE_KEY)
    edit_stage = data.get(EDIT_STAGE_KEY)
    upscale_stage = data.get(UPSCALE_STAGE_KEY)
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    retoucher_stage = data.get(RETOUCHER_STAGE_KEY)
    stylish_stage = data.get("stylish_stage")
    face_swap_stage = data.get("face_swap_stage")
    
    # Если ни один режим не выбран, показываем подсказку
    # Но сначала проверяем, не является ли это кнопкой или командами
    text_lower = text.lower()
    chrono_lower = IMAGE_EDIT_CHRONO_BUTTON.lower()
    seedream_lower = IMAGE_EDIT_SEDEDIT_BUTTON.lower()
    is_edit_button = (text_lower == chrono_lower or text_lower == seedream_lower)
    # Если активен режим создания и промпт еще не сохранен, сохраняем его и показываем выбор моделей
    if create_stage == "await_prompt" and text and not selected_model:
        await state.update_data(prompt=text, create_stage="await_model")
        from app.bot.keyboards.main import build_create_model_keyboard
        await message.answer(
            MODELS_DESCRIPTION_TEXT,
            reply_markup=build_create_model_keyboard(),
        )
        return


    
    # Игнорируем кнопки главного меню
    main_menu_buttons = {
        CREATE_BUTTON,
        IMAGE_EDIT_BUTTON,
        IMAGE_SMART_MERGE_BUTTON,
        IMAGE_RETOUCHER_BUTTON,
        IMAGE_STYLISH_TEXT_BUTTON,
        IMAGE_FACE_SWAP_BUTTON,
        IMAGE_UPSCALE_BUTTON,
        INFO_BUTTON,
    }
    
    if not any([selected_model, create_stage, edit_stage, upscale_stage, smart_merge_stage, retoucher_stage, stylish_stage, face_swap_stage]) and text not in main_menu_buttons and not is_edit_button:
        from app.bot.keyboards.main import build_main_keyboard
        await message.answer(
            "⚠️ Сначала выберите режим работы, нажав одну из кнопок ниже.",
            reply_markup=build_main_keyboard()
        )
        return

    
    logger.info("handle_prompt_input called: text='{}', user_id={}", text, message.from_user.id if message.from_user else "unknown")
    logger.debug("handle_prompt_input: IMAGE_EDIT_CHRONO_BUTTON='{}', IMAGE_EDIT_SEDEDIT_BUTTON='{}'", 
                 IMAGE_EDIT_CHRONO_BUTTON, IMAGE_EDIT_SEDEDIT_BUTTON)
    
    # Проверяем кнопки выбора модели редактирования САМЫМ ПЕРВЫМ, до всех остальных проверок
    # Проверяем без учета регистра
    text_lower = text.lower()
    chrono_lower = IMAGE_EDIT_CHRONO_BUTTON.lower()
    seedream_lower = IMAGE_EDIT_SEDEDIT_BUTTON.lower()
    
    is_edit_button = (text_lower == chrono_lower or text_lower == seedream_lower)
    
    logger.debug("handle_prompt_input: text_lower='{}', chrono_lower='{}', seedream_lower='{}', is_edit_button={}", 
                 text_lower, chrono_lower, seedream_lower, is_edit_button)
    
    if is_edit_button:
        logger.info("handle_prompt_input: detected edit model button '{}' (lowercase: '{}'), calling handle_edit_model_choice directly", 
                   text, text_lower)
        await handle_edit_model_choice(message, state, ignore_stage_check=True)
        return
    
    # Проверяем режим ретуши ПЕРЕД проверкой main_menu_buttons,
    # чтобы кнопки режима ретуши обрабатывались правильно
    retoucher_stage = data.get(RETOUCHER_STAGE_KEY)
    if retoucher_stage:
        logger.info("handle_prompt_input: retoucher_stage='{}', calling _handle_retoucher_text with text='{}'", 
                    retoucher_stage, text)
        await _handle_retoucher_text(message, state, retoucher_stage, text)
        return
    
    # Игнорируем все кнопки главного меню - они обрабатываются отдельными handlers
    # НЕ включаем IMAGE_EDIT_CHRONO_BUTTON и IMAGE_EDIT_SEDEDIT_BUTTON, так как они обрабатываются выше
    # ВАЖНО: включаем IMAGE_STANDARD_BUTTON, чтобы он обрабатывался своим handler
    main_menu_buttons = {
        CREATE_BUTTON,
        IMAGE_EDIT_BUTTON,
        IMAGE_SMART_MERGE_BUTTON,
        IMAGE_RETOUCHER_BUTTON,
        IMAGE_STYLISH_TEXT_BUTTON,
        IMAGE_FACE_SWAP_BUTTON,
        IMAGE_UPSCALE_BUTTON,
        INFO_BUTTON,
    }
    if text in main_menu_buttons:
        return
    
    # Игнорируем кнопки выбора модели - они обрабатываются handle_standard, handle_seedream_create и handle_gpt_create
    if text == IMAGE_STANDARD_BUTTON or text == IMAGE_SEEDREAM_CREATE_BUTTON or text == IMAGE_GPT_CREATE_BUTTON:
        return
    
    # Игнорируем кнопки выбора размера - они обрабатываются handle_size_choice
    if text in (IMAGE_SIZE_VERTICAL_BUTTON, IMAGE_SIZE_SQUARE_BUTTON, IMAGE_SIZE_HORIZONTAL_BUTTON):
        return
    
    # Проверяем, не находимся ли мы в режиме Stylish text
    stylish_stage = data.get("stylish_stage")
    if stylish_stage:
        logger.debug("handle_prompt_input: skipping because stylish_stage='{}' is active", stylish_stage)
        # Пропускаем обработку - пусть обрабатывает stylish_text handler
        return

    if not text or text.startswith("/"):
        await message.answer("Сначала напишите промпт, затем выберите модель.")
        return

    upscale_stage = data.get(UPSCALE_STAGE_KEY)
    if upscale_stage == "await_source":
        await _handle_upscale_text(message, state, text)
        return

    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    if smart_merge_stage == "collect":
        sources: list[dict[str, str | None]] = data.get(SMART_MERGE_SOURCES_KEY) or []
        logger.info(
            "Smart merge text input: user={}, stage={}, sources_count={}, sources={}",
            message.from_user.id if message.from_user else "unknown",
            smart_merge_stage,
            len(sources),
            [s.get("path", "no_path") for s in sources],
        )
        if not sources:
            # Получаем полное состояние для диагностики
            full_data = await state.get_data()
            logger.error(
                "Smart merge: no sources found in state for user {}. Full state data: {}",
                message.from_user.id if message.from_user else "unknown",
                full_data,
            )
            await message.answer(
                "❌ Изображения не найдены в состоянии.\n"
                "Возможные причины:\n"
                "• Изображения не были загружены\n"
                "• Состояние было сброшено\n"
                "• Попробуйте нажать «ℹ️ Info» и начать заново\n\n"
                "Пожалуйста, нажмите «🔗 Объединить ➕ Добавить» и отправьте изображения снова.",
                reply_markup=build_main_keyboard(),
            )
            return
        lowered = text.lower()
        if lowered in {"готово", "done"}:
            await message.answer(
                "Отлично! Теперь опишите сцену, например: «Девушка стоит рядом с автомобилем, утренний свет».",
                reply_markup=build_main_keyboard(),
            )
            return
        prompt_text, override_options = _parse_smart_merge_input(text)
        if not prompt_text:
            await message.answer(
                "Не удалось распознать описание. Напишите сцену текстом, например: «Девушка стоит рядом с автомобилем, утренний свет».",
                reply_markup=build_main_keyboard(),
            )
            return
        if len(prompt_text) < MIN_PROMPT_LENGTH:
            await message.answer("Промпт слишком короткий. Пожалуйста, уточните запрос.")
            return
        await _enqueue_smart_merge_task(
            message,
            state,
            prompt=prompt_text,
            sources=sources,
            options_override=override_options,
        )
        await state.clear()
        return
    if smart_merge_stage:
        await message.answer(
            "Объединение уже активно. Опишите сцену текстом или нажмите «ℹ️ Info» для сброса.",
            reply_markup=build_main_keyboard(),
        )
        return

    edit_stage = data.get(EDIT_STAGE_KEY)
    if edit_stage:
        # Если мы в режиме редактирования и это кнопка выбора модели, обрабатываем напрямую
        if text_lower == IMAGE_EDIT_CHRONO_BUTTON.lower() or text_lower == IMAGE_EDIT_SEDEDIT_BUTTON.lower():
            logger.info("handle_prompt_input: in edit stage, detected model button '{}', calling handle_edit_model_choice", text)
            await handle_edit_model_choice(message, state, ignore_stage_check=True)
            return
        # Иначе обрабатываем как обычный текст в режиме редактирования
        await _handle_edit_text(message, state, edit_stage, text)
        return

    # Очищаем промпт от возможных префиксов "Промпт: " или "Prompt: "
    cleaned_text = text.strip()
    if cleaned_text.lower().startswith("промпт:"):
        cleaned_text = cleaned_text[7:].strip()
    elif cleaned_text.lower().startswith("prompt:"):
        cleaned_text = cleaned_text[7:].strip()
    
    if len(cleaned_text) < MIN_PROMPT_LENGTH:
        await message.answer("Промпт слишком короткий. Пожалуйста, уточните запрос.")
        return

    await state.update_data(prompt=cleaned_text, selected_model=None, edit_stage=None)
    try:
        await message.answer(
        "Промпт принят ✅.\nТеперь нажмите «🎨 Создать» для выбора модели.",
            reply_markup=build_main_keyboard(),
    )


    except Exception as e:
        # Игнорируем ошибки отправки сообщения (таймаут Telegram API)
        logger.warning("handle_prompt_input: failed to send confirmation message: {}", e)
        return

async def handle_edit_media(message: types.Message, state: FSMContext) -> None:
    logger.info(
        "handle_edit_media called: user={}, has_photo={}, has_document={}",
        message.from_user.id if message.from_user else "unknown",
        bool(message.photo),
        bool(message.document),
    )
    data = await state.get_data()
    
    # Проверяем, не находимся ли мы в режиме Stylish text
    stylish_stage = data.get("stylish_stage")
    if stylish_stage:
        logger.debug("Skipping handle_edit_media - stylish_stage={}", stylish_stage)
        # Пропускаем обработку - пусть обрабатывает stylish_text handler
        return

    # Проверяем, выбран ли режим работы
    edit_stage = data.get(EDIT_STAGE_KEY)
    upscale_stage = data.get(UPSCALE_STAGE_KEY)
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    retoucher_stage = data.get(RETOUCHER_STAGE_KEY)
    face_swap_stage = data.get("face_swap_stage")
    
    # Если ни один режим не выбран, показываем подсказку
    if not any([edit_stage, upscale_stage, smart_merge_stage, retoucher_stage, stylish_stage, face_swap_stage]):
        from app.bot.keyboards.main import build_main_keyboard
        await message.answer(
            "⚠️ Сначала выберите режим работы, нажав одну из кнопок ниже.",
            reply_markup=build_main_keyboard()
        )
        return

    
    stage = edit_stage

    logger.info(
        "handle_edit_media: user={}, stages: edit={}, upscale={}, smart_merge={}, retoucher={}, stylish={}",
        message.from_user.id if message.from_user else "unknown",
        stage,
        upscale_stage,
        smart_merge_stage,
        retoucher_stage,
        stylish_stage,
    )

    if retoucher_stage in {"await_image", "await_mode", "await_instruction"}:
        saved_path = await _download_message_image(message)
        if not saved_path:
            return
        await state.update_data(
            {
                RETOUCHER_SOURCE_PATH_KEY: saved_path.as_posix(),
                RETOUCHER_STAGE_KEY: "await_mode",
                RETOUCHER_MODE_KEY: None,
                RETOUCHER_PROMPT_KEY: None,
            }
        )
        retoucher_info = (
            "Изображение получено ✅\n\n"
            "**Выберите режим ретуши:**\n\n"
            "**✨ Мягкая ретушь**\n"
            "• Удаляет мелкие дефекты (прыщи, пятна)\n"
            "• Выравнивает тон кожи\n"
            "• Сохраняет естественную текстуру и поры\n"
            "• Не изменяет структуру лица\n\n"
            "💡 Примеры инструкций:\n"
            "• \"убери прыщи на лбу\"\n"
            "• \"сделай кожу более гладкой\"\n"
            "• \"убери темные круги под глазами\"\n"
            "• \"выровняй тон кожи\"\n\n"
            "**✨ Усилить черты**\n"
            "• Улучшает четкость черт лица\n"
            "• Подчеркивает глаза, губы и контуры\n"
            "• Сохраняет структуру лица и пропорции\n"
            "• Только улучшает четкость и определение\n\n"
            "💡 Примеры инструкций:\n"
            "• \"подчеркни глаза и губы\"\n"
            "• \"улучши четкость черт\"\n"
            "• \"сделай контуры более выразительными\"\n\n"
            "После выбора режима можно указать дополнительную инструкцию или нажать \"Пропустить\"."
        )
        await message.answer(
            retoucher_info,
            reply_markup=build_retoucher_mode_keyboard(),
            parse_mode="Markdown",
        )
        return


    if smart_merge_stage == "collect":
        logger.info("Processing image for smart merge (stage=collect) for user {}", 
                    message.from_user.id if message.from_user else "unknown")
        await _handle_smart_merge_media(message, state)
        return
    elif smart_merge_stage:
        logger.warning("handle_edit_media: smart_merge_stage='{}' but not 'collect', skipping smart merge processing", 
                      smart_merge_stage)

    if upscale_stage == "await_source":
        saved_path = await _download_message_image(message)
        if not saved_path:
            return

        remote_url = None
        if message.photo:
            file_id = message.photo[-1].file_id
            remote_url = await _get_telegram_file_url(message, file_id)
        elif message.document:
            file_id = message.document.file_id
            remote_url = await _get_telegram_file_url(message, file_id)

        prompt = "Upscale"
        options = _build_notify_options(message, prompt)
        # Убираем промпт из уведомления для upscale
        options["notify_prompt"] = ""

        new_job_id, _ = enqueue_image_upscale(
            image_url=remote_url,
            image_path=saved_path.as_posix(),
            scale=2,
            **options,
        )
        await _clear_upscale_state(state)
        if message.chat:
            LAST_JOB_BY_CHAT[message.chat.id] = new_job_id
        await message.answer("🔍 Запускаю апскейл изображения...", reply_markup=build_main_keyboard())
        return

    if stage not in {"await_source", "await_mask"}:
        return

    saved_path = await _download_message_image(message)
    if not saved_path:
        return

    if stage == "await_source":
        await state.update_data({EDIT_SOURCE_PATH_KEY: saved_path.as_posix()})
        await _set_edit_stage(state, "await_prompt")
        await message.answer(
            "Изображение получено ✅\nОпишите, какие изменения нужны.",
            reply_markup=build_main_keyboard(),
        )
        return

    if stage == "await_mask":
        await state.update_data({EDIT_MASK_PATH_KEY: saved_path.as_posix()})
        source_raw = data.get(EDIT_SOURCE_PATH_KEY)
        prompt_text = data.get(EDIT_PROMPT_KEY)
        if not source_raw or not prompt_text:
            await message.answer("Не удалось найти исходные данные. Начните заново.")
            await state.clear()
            return
        source_path = Path(source_raw)
        if not source_path.exists():
            await message.answer("Исходный файл недоступен. Отправьте изображение снова.")
            await state.clear()
            return
        await _enqueue_image_edit_task(
            message,
            prompt=prompt_text,
            image_path=source_path,
            mask_path=saved_path,
        )
        await state.clear()


async def handle_edit_model_choice(
    message: types.Message,
    state: FSMContext,
    ignore_stage_check: bool = False,
) -> None:
    selection = (message.text or "").strip()
    selection_lower = selection.lower()
    
    # СНАЧАЛА проверяем режим Smart merge, чтобы не перехватывать сообщения для Smart merge
    data = await state.get_data()
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    
    # Если мы в режиме Smart merge, не обрабатываем выбор модели для редактирования
    if smart_merge_stage:
        logger.debug("handle_edit_model_choice: ignoring because smart_merge_stage is active (stage: {})", smart_merge_stage)
        return
    
    logger.info("handle_edit_model_choice called: selection='{}' (lower: '{}'), ignore_stage_check={}", 
                selection, selection_lower, ignore_stage_check)
    logger.info("handle_edit_model_choice: IMAGE_EDIT_CHRONO_BUTTON='{}' (lower: '{}'), IMAGE_EDIT_SEDEDIT_BUTTON='{}' (lower: '{}')", 
                IMAGE_EDIT_CHRONO_BUTTON, IMAGE_EDIT_CHRONO_BUTTON.lower(), 
                IMAGE_EDIT_SEDEDIT_BUTTON, IMAGE_EDIT_SEDEDIT_BUTTON.lower())
    
    # Проверяем совпадение без учета регистра
    is_chrono = selection_lower == IMAGE_EDIT_CHRONO_BUTTON.lower()
    is_seedream = selection_lower == IMAGE_EDIT_SEDEDIT_BUTTON.lower()
    
    logger.info("handle_edit_model_choice: is_chrono={}, is_seedream={}", is_chrono, is_seedream)
    
    if not (is_chrono or is_seedream):
        logger.warning("handle_edit_model_choice: selection '{}' (lower: '{}') does not match any edit model button. Chrono='{}', Seedream='{}'", 
                      selection, selection_lower, IMAGE_EDIT_CHRONO_BUTTON.lower(), IMAGE_EDIT_SEDEDIT_BUTTON.lower())
        return

    current_stage = data.get(EDIT_STAGE_KEY)
    
    # Если ignore_stage_check=False, проверяем стадию
    if not ignore_stage_check:
        if current_stage != "await_model":
            logger.debug("handle_edit_model_choice: current_stage '{}' != 'await_model', ignore_stage_check={}", current_stage, ignore_stage_check)
            return
    else:
        # Если ignore_stage_check=True, все равно проверяем, что мы в режиме редактирования
        if current_stage not in ("await_model", "await_prompt"):
            logger.warning("handle_edit_model_choice: current_stage '{}' is not in edit mode, but ignore_stage_check=True", current_stage)
            await message.answer(
                "Сначала загрузите изображение и опишите изменения через «✏️ Редактировать».",
                reply_markup=build_main_keyboard(),
            )
            return

    prompt_text = data.get(EDIT_PROMPT_KEY)
    source_raw = data.get(EDIT_SOURCE_PATH_KEY)
    
    logger.info("handle_edit_model_choice: checking data - prompt_text={}, source_raw={}", 
                prompt_text is not None, source_raw is not None)
    
    if not prompt_text or not source_raw:
        logger.error("handle_edit_model_choice: missing prompt_text or source_raw. prompt_text={}, source_raw={}. Full data keys: {}", 
                    prompt_text, source_raw, list(data.keys()))
        await message.answer("Не удалось найти исходные данные. Начните заново.", reply_markup=build_main_keyboard())
        await state.clear()
        return
    
    source_path = Path(source_raw)
    if not source_path.exists():
        logger.error("handle_edit_model_choice: source_path does not exist: {}", source_path)
        await message.answer("Исходный файл недоступен. Отправьте изображение снова.", reply_markup=build_main_keyboard())
        await state.clear()
        return

    model_path = IMAGE_EDIT_MODEL if is_chrono else IMAGE_EDIT_ALT_MODEL
    model_name = "Chrono Edit" if is_chrono else "Seedream"
    logger.info("handle_edit_model_choice: user selected {} model (path: {}). Starting edit task...", model_name, model_path)
    
    try:
        await _enqueue_image_edit_task(
            message,
            prompt=prompt_text,
            image_path=source_path,
            mask_path=None,
            base_options={"model": model_path},
        )
        logger.info("handle_edit_model_choice: edit task enqueued successfully")
        await state.clear()
    except Exception as exc:
        logger.error("handle_edit_model_choice: failed to enqueue edit task: {}", exc, exc_info=True)
        await message.answer(f"Ошибка при запуске редактирования: {str(exc)}", reply_markup=build_main_keyboard())
        await state.clear()


async def handle_smart_merge_start(message: types.Message, state: FSMContext) -> None:
    # Сначала очищаем состояние, затем устанавливаем флаг для Smart merge
    await state.clear()
    # Устанавливаем флаг, что мы ожидаем выбор модели для Smart merge
    await state.update_data({SMART_MERGE_STAGE_KEY: "await_model"})
    
    # Проверяем, что состояние установлено правильно
    verify_data = await state.get_data()
    logger.info(
        "Smart merge model selection for user {}. Stage set to: {}",
        message.from_user.id if message.from_user else "unknown",
        verify_data.get(SMART_MERGE_STAGE_KEY),
    )
    await message.answer(
        "🔗 Объединение изображений\n\n"
        "Выберите модель:\n"
        "• **Nano-Banana (Merge)** — качественное объединение объектов и сцен\n"
        "• **Seedream (Merge)** — лучше работает с людьми, добавляет объекты\n\n"
        "После выбора модели отправьте до 4 изображений.\n\n"
        "💡 Можно добавить текст в изображение — укажите название или текст на английском языке в описании сцены, и модель добавит его в результат.",
        reply_markup=build_smart_merge_model_keyboard(),
        parse_mode="Markdown",
    )


async def handle_smart_merge_model_choice(message: types.Message, state: FSMContext) -> None:
    selection = message.text
    logger.info("handle_smart_merge_model_choice called: selection='{}'", selection)
    
    # ВАЖНО: Сначала проверяем состояние, потом текст кнопки
    # Это предотвращает конфликт с кнопками создания изображения, которые имеют тот же текст
    data = await state.get_data()
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    
    logger.info("handle_smart_merge_model_choice: smart_merge_stage='{}', selection='{}'", smart_merge_stage, selection)
    
    # СНАЧАЛА проверяем, что мы в режиме Smart merge
    # Если не в режиме Smart merge, сразу возвращаемся, чтобы не блокировать другие обработчики
    if not smart_merge_stage or smart_merge_stage != "await_model":
        logger.debug("handle_smart_merge_model_choice: not in smart_merge mode (stage='{}'), ignoring. Full data: {}", 
                    smart_merge_stage, data)
        return
    
    # Только если мы в режиме Smart merge, проверяем текст кнопки
    if selection not in {IMAGE_SMART_MERGE_NANO_BUTTON, IMAGE_SMART_MERGE_SEEDREAM_BUTTON}:
        logger.warning("handle_smart_merge_model_choice: selection '{}' not in smart merge buttons (expected: {} or {}), ignoring", 
                      selection, IMAGE_SMART_MERGE_NANO_BUTTON, IMAGE_SMART_MERGE_SEEDREAM_BUTTON)
        return
    
    logger.info("handle_smart_merge_model_choice: processing selection '{}' for smart merge", selection)
    
    # Определяем модель на основе выбора
    model_path = SMART_MERGE_DEFAULT_MODEL if selection == IMAGE_SMART_MERGE_NANO_BUTTON else SMART_MERGE_SEEDREAM_MODEL
    model_name = "Nano-Banana" if selection == IMAGE_SMART_MERGE_NANO_BUTTON else "Seedream"
    
    try:
        await state.update_data(
            {
                SMART_MERGE_STAGE_KEY: "collect",
                SMART_MERGE_SOURCES_KEY: [],
                SMART_MERGE_MODEL_KEY: model_path,
            }
        )
        logger.info(
            "Smart merge activated for user {} with model {}",
            message.from_user.id if message.from_user else "unknown",
            model_name,
        )
        
        # Проверяем, что состояние сохранилось
        verify_data = await state.get_data()
        verify_stage = verify_data.get(SMART_MERGE_STAGE_KEY)
        logger.info("handle_smart_merge_model_choice: state updated, verify_stage='{}'", verify_stage)
        
        if model_name == "Nano-Banana":
            await message.answer(
                f"Объединение активировано ({model_name}).\n"
                "Отправьте до 4 изображений (фото или документы). "
                "Когда закончите, опишите сцену текстом.\n\n"
                "💡 Особенности Nano-Banana:\n"
                "• Лучше работает с одним объектом и детальным промптом\n"
                "• Для нескольких объектов используйте Seedream\n"
                "• Опишите детали: «объедини объекты, сохрани пропорции»",
                reply_markup=build_main_keyboard(),
            )
        else:
            await message.answer(
                f"Объединение активировано ({model_name}).\n"
                "Отправьте до 4 изображений (фото или документы). "
                "Когда закончите, опишите сцену текстом.\n\n"
                "💡 Советы:\n"
                "• Для объединения людей: «объедини 3х человек, все должны быть видны, стоят рядом»\n"
                "• Укажите количество: «все 3 человека», «оба объекта», «все изображения»\n"
                "• Опишите расположение: «плечом к плечу», «рядом друг с другом»",
                reply_markup=build_main_keyboard(),
            )
        logger.info("handle_smart_merge_model_choice: message sent successfully for model '{}'", model_name)
    except Exception as exc:
        logger.error("handle_smart_merge_model_choice: error processing selection '{}': {}", selection, exc, exc_info=True)
        await message.answer(f"Ошибка при активации объединения: {str(exc)}", reply_markup=build_main_keyboard())




async def handle_retoucher_start(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(
        {
            RETOUCHER_STAGE_KEY: "await_image",
            RETOUCHER_SOURCE_PATH_KEY: None,
            RETOUCHER_MODE_KEY: None,
            RETOUCHER_PROMPT_KEY: None,
        }
    )
    await message.answer(
        "✨ Ретушь активирована. Отправьте фото лица (как фото или документ), которое нужно деликатно улучшить.",
        reply_markup=build_main_keyboard(),
    )


async def _handle_smart_merge_media(message: types.Message, state: FSMContext) -> None:
    user_id = message.from_user.id if message.from_user else "unknown"
    try:
        logger.info("_handle_smart_merge_media: Starting smart merge media processing for user {}", user_id)
        
        saved_path = await _download_message_image(message)
        if not saved_path:
            logger.warning("Failed to download image for smart merge from user {}", user_id)
            await message.answer(
                "❌ Не удалось загрузить изображение. Пожалуйста, попробуйте отправить изображение снова (как фото или документ).",
                reply_markup=build_main_keyboard(),
            )
            return

        logger.debug("Image downloaded successfully: {}", saved_path)

        remote_url = None
        try:
            if message.photo:
                file_id = message.photo[-1].file_id
                logger.debug("Getting Telegram file URL for photo: file_id={}", file_id)
                remote_url = await _get_telegram_file_url(message, file_id)
            elif message.document:
                file_id = message.document.file_id
                logger.debug("Getting Telegram file URL for document: file_id={}", file_id)
                remote_url = await _get_telegram_file_url(message, file_id)
            if remote_url:
                logger.debug("Got Telegram file URL: {}", remote_url)
        except Exception as exc:
            logger.warning("Failed to get Telegram file URL for smart merge: {}", exc, exc_info=True)
            # Продолжаем работу даже если URL не получен, используем локальный путь

        logger.debug("Getting state data for user {}", user_id)
        data = await state.get_data()
        existing_sources: list[dict[str, str | None]] = list(data.get(SMART_MERGE_SOURCES_KEY) or [])
        logger.debug("Current sources count: {}", len(existing_sources))

        if len(existing_sources) >= SMART_MERGE_MAX_IMAGES:
            logger.info("User {} already has {} images, asking for prompt", user_id, len(existing_sources))
            await message.answer(
                "Вы уже загрузили 4 изображения. Теперь опишите сцену текстом.",
                reply_markup=build_main_keyboard(),
            )
            return

        new_source = {
            "url": remote_url,
            "path": saved_path.as_posix(),
        }
        existing_sources.append(new_source)
        logger.debug("Added new source: url={}, path={}", remote_url, saved_path.as_posix())

        logger.debug("Updating state with {} sources", len(existing_sources))
        await state.update_data(
            {
                SMART_MERGE_STAGE_KEY: "collect",
                SMART_MERGE_SOURCES_KEY: existing_sources,
            }
        )
        
        # Проверяем, что состояние сохранилось
        verify_data = await state.get_data()
        verify_sources = verify_data.get(SMART_MERGE_SOURCES_KEY) or []
        logger.info(
            "Smart merge: received image {}/{} from user {}, saved_path={}, state_verified={} sources",
            len(existing_sources),
            SMART_MERGE_MAX_IMAGES,
            user_id,
            saved_path.as_posix(),
            len(verify_sources),
        )
        
        if len(verify_sources) != len(existing_sources):
            logger.error(
                "Smart merge: state verification failed! Expected {} sources, got {}. Sources: {}",
                len(existing_sources),
                len(verify_sources),
                verify_sources,
            )

        if len(existing_sources) >= SMART_MERGE_MAX_IMAGES:
            await message.answer(
                "Получено 4 из 4 изображений ✅\nТеперь опишите сцену, чтобы объединить их в единую композицию.",
                reply_markup=build_main_keyboard(),
            )
        else:
            await message.answer(
                f"Изображение {len(existing_sources)}/{SMART_MERGE_MAX_IMAGES} получено ✅\n"
                "Добавьте ещё или сразу опишите сцену текстом.",
                reply_markup=build_main_keyboard(),
            )
    except Exception as exc:
        logger.error(
            "Error processing smart merge media for user {}: {}",
            user_id,
            exc,
            exc_info=True,
        )
        await message.answer(
            "❌ Произошла ошибка при обработке изображения. Попробуйте отправить изображение снова или нажмите «ℹ️ Info» для сброса.",
            reply_markup=build_main_keyboard(),
        )


def _match_button(target: str):
    target_lower = target.lower()

    def checker(message: types.Message) -> bool:
        if not message.text:
            return False
        text_lower = message.text.strip().lower()
        matches = text_lower == target_lower
        return matches

    return checker


def register_image_handlers(dp: Dispatcher) -> None:
    # ВАЖНО: В aiogram обработчики проверяются в ОБРАТНОМ порядке регистрации
    # Регистрируем обработчики создания изображения ПОСЛЕДНИМИ, чтобы они проверялись ПЕРВЫМИ
    # Это гарантирует, что они имеют приоритет при обработке кнопок "Nano-banana", "Seedream (Create)" и "Nano Banana Pro" после "Создать"
    dp.message.register(handle_create, _match_button(CREATE_BUTTON))
    dp.message.register(handle_standard, _match_button(IMAGE_STANDARD_BUTTON))
    dp.message.register(handle_seedream_create, _match_button(IMAGE_SEEDREAM_CREATE_BUTTON))
    dp.message.register(handle_gpt_create, _match_button(IMAGE_GPT_CREATE_BUTTON))
    
    # Обработчики редактирования регистрируем ПЕРЕД созданием,
    # чтобы они проверялись ПОСЛЕ создания (в обратном порядке)
    dp.message.register(handle_edit_model_choice, _match_button(IMAGE_EDIT_CHRONO_BUTTON))
    dp.message.register(handle_edit_model_choice, _match_button(IMAGE_EDIT_SEDEDIT_BUTTON))
    
    # Обработчики Smart merge регистрируем ПЕРЕД созданием и редактированием,
    # чтобы они проверялись ПОСЛЕ них (в обратном порядке)
    # handle_smart_merge_model_choice теперь сначала проверяет состояние, поэтому не блокирует другие обработчики
    dp.message.register(handle_smart_merge_start, _match_button(IMAGE_SMART_MERGE_BUTTON))
    dp.message.register(handle_smart_merge_model_choice, _match_button(IMAGE_SMART_MERGE_NANO_BUTTON))
    dp.message.register(handle_smart_merge_model_choice, _match_button(IMAGE_SMART_MERGE_SEEDREAM_BUTTON))
    dp.message.register(handle_edit_start, _match_button(IMAGE_EDIT_BUTTON))
    dp.message.register(handle_retoucher_start, _match_button(IMAGE_RETOUCHER_BUTTON))
    dp.message.register(handle_upscale_button, _match_button(IMAGE_UPSCALE_BUTTON))
    dp.message.register(handle_size_choice, _match_button(IMAGE_SIZE_VERTICAL_BUTTON))
    dp.message.register(handle_size_choice, _match_button(IMAGE_SIZE_SQUARE_BUTTON))
    dp.message.register(handle_size_choice, _match_button(IMAGE_SIZE_HORIZONTAL_BUTTON))
    dp.message.register(handle_edit_media, F.photo)
    dp.message.register(handle_edit_media, F.document)
    dp.callback_query.register(handle_edit_callback, lambda c: c.data and c.data.startswith("edit:"))
    dp.callback_query.register(handle_upscale_callback, lambda c: c.data and c.data.startswith("upscale:"))
    # Общий обработчик текста регистрируется последним, чтобы он проверялся первым
    # (в обратном порядке), но он пропускает кнопки редактирования через проверку выше
    dp.message.register(handle_prompt_input, lambda msg: msg.text and not msg.text.startswith("/"))

