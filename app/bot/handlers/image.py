from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
    IMAGE_SMART_MERGE_PRO_BUTTON,
    IMAGE_SMART_MERGE_NANO_BUTTON,
    IMAGE_SMART_MERGE_SEEDREAM_BUTTON,
    IMAGE_UPSCALE_BUTTON,
    IMAGE_SIZE_HORIZONTAL_BUTTON,
    IMAGE_SIZE_SQUARE_BUTTON,
    IMAGE_SIZE_VERTICAL_BUTTON,
    IMAGE_STANDARD_BUTTON,
    IMAGE_FLUX2FLEX_CREATE_BUTTON,
    INFO_BUTTON,
    PROMPT_WRITER_BUTTON,
    RETOUCHER_ENHANCE_BUTTON,
    RETOUCHER_SKIP_BUTTON,
    RETOUCHER_SOFT_BUTTON,
    BALANCE_BUTTON,
    IMAGE_FORMAT_SQUARE_1_1,
    IMAGE_FORMAT_VERTICAL_3_4,
    IMAGE_FORMAT_HORIZONTAL_4_3,
    IMAGE_FORMAT_VERTICAL_4_5,
    IMAGE_FORMAT_VERTICAL_9_16,
    IMAGE_FORMAT_HORIZONTAL_16_9,
    QUALITY_FASTER_BUTTON,
    QUALITY_BETTER_BUTTON,
    build_create_model_keyboard,
    build_main_keyboard,
    build_size_keyboard,
    build_format_keyboard,
    build_edit_model_keyboard,
    build_retoucher_instruction_keyboard,
    build_retoucher_mode_keyboard,
    build_smart_merge_model_keyboard,
    build_quality_keyboard,
)
from app.core.formats import ImageFormat, get_format_spec, get_model_format_mapping, get_format_hints_text
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
from app.services.pricing import _is_seedream_model
from app.utils.translation import translate_to_english


async def get_operation_discount_percent(state: FSMContext, user_id: int | None = None) -> int | None:
    """Get active discount percent for operations from state or database."""
    # First check state (for immediate use)
    data = await state.get_data()
    if "operation_discount_percent" in data:
        discount_percent = data.get("operation_discount_percent")
        discount_code = data.get("operation_discount_code", "UNKNOWN")
        logger.info(f"Found active discount code {discount_code} ({discount_percent}%) in state for operation")
        return discount_percent
    
    # If not in state, check database (for persistence across restarts)
    if user_id:
        from app.services.billing import BillingService
        from app.db.base import SessionLocal
        db = SessionLocal()
        try:
            user, _ = BillingService.get_or_create_user(db, user_id, None)
            if user.operation_discount_percent:
                # Also update state for future use
                from app.db.models import DiscountCode
                discount = db.query(DiscountCode).filter(DiscountCode.id == user.operation_discount_code_id).first()
                discount_code = discount.code if discount else "UNKNOWN"
                await state.update_data(
                    operation_discount_code=discount_code,
                    operation_discount_id=user.operation_discount_code_id,
                    operation_discount_percent=user.operation_discount_percent
                )
                logger.info(f"Found active discount code {discount_code} ({user.operation_discount_percent}%) in database for operation")
                return user.operation_discount_percent
        finally:
            db.close()
    
    return None


class ImageStates(StatesGroup):
    """Состояния для работы с изображениями."""
    prompt_saved = State()  # Состояние для сохранения промпта


async def _get_telegram_file_url(message: types.Message, file_id: str) -> str | None:
    try:
        file = await message.bot.get_file(file_id)
        if not file.file_path:
            return None
        return f"https://api.telegram.org/file/bot{settings.tg_bot_token}/{file.file_path}"
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to obtain Telegram file url for {}: {}", file_id, exc)
        return None


async def _send_error_notification(message: types.Message, error_context: str = "") -> None:
    """Отправляет пользователю уведомление об ошибке."""
    error_text = (
        "❌ Произошла ошибка при обработке запроса.\n\n"
        "Попробуйте повторить операцию позже или обратитесь в техническую поддержку."
    )
    if error_context:
        logger.error("Error in {}: context={}", error_context, error_context)
    try:
        await message.answer(error_text, reply_markup=build_main_keyboard())
    except Exception as send_exc:
        logger.error("Failed to send error notification: {}", send_exc, exc_info=True)


IMAGE_LIGHT_MODEL = settings.fal_standard_model
IMAGE_STANDARD_MODEL = settings.fal_premium_model
IMAGE_EDIT_MODEL = settings.fal_edit_model
IMAGE_EDIT_ALT_MODEL = settings.fal_seedream_edit_model  # Seedream 4.5 edit
LAST_JOB_BY_CHAT: dict[int, str] = {}
PROMPT_ACCEPTED_TEXT = (
    "Промпт принят ✅.\nТеперь выберите действие из меню."
)
NO_PROMPT_TEXT = (
    "Сначала напишите промпт, затем выберите действие из меню.\n\n"
    "Пример: «Портрет молодой женщины в возрасте 30 лет славянской наружности в деловом костюме, современный офис, естественное освещение, профессиональная фотография».\n\n"
    "💡 Нужна помощь в написании промпта? Используйте кнопку «✍️ Написать» — она поможет составить детальный и качественный промпт."
)
MIN_PROMPT_LENGTH = 3

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
SMART_MERGE_SIZE_KEY = "smart_merge_size"  # Ключ для хранения выбранного размера
SMART_MERGE_PRO_MODEL = settings.fal_nano_banana_pro_edit_model
SMART_MERGE_DEFAULT_MODEL = settings.fal_nano_banana_edit_model
SMART_MERGE_SEEDREAM_MODEL = settings.fal_seedream_edit_model  # Seedream 4.5 edit
SMART_MERGE_DEFAULT_SIZE = "1024x1024"
SMART_MERGE_DEFAULT_ASPECT_RATIO = "1:1"
SMART_MERGE_MAX_IMAGES = 8
RETOUCHER_STAGE_KEY = "retoucher_stage"
RETOUCHER_SOURCE_PATH_KEY = "retoucher_source_path"
RETOUCHER_MODE_KEY = "retoucher_mode"
RETOUCHER_PROMPT_KEY = "retoucher_instruction"
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
        "model": settings.fal_seedream_edit_model,  # Seedream 4.5 Edit для качественной ретуши
        "base_prompt": (
            "Subtle, high-quality face and skin retouch while keeping the person in the same position and scale in the frame. "
            "Do not zoom in, do not crop, do not change the framing or composition. "
            "Keep the original background, full body and surroundings visible if they were in the input image. "
            "Gently enhance facial features, skin texture, clarity and lighting, but do not change the pose, proportions or camera distance. "
            "No dramatic reshaping, no transformation into a close-up portrait, no change of style."
        ),
        "base_options": {
            "output_format": "png",
        },
        "notify_text": "✨ Улучшаю черты лица...",
    },
}

MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "light": {
        "label": "изображение",
        "model": IMAGE_LIGHT_MODEL,
        "base": {
            "num_inference_steps": 28,
            "guidance_scale": 5.5,
            "output_format": "png",
        },
        "sizes": {
            "vertical": {"size": "832x1216", "aspect_ratio": "3:4", "image_size": "portrait_4_3"},
            "square": {"size": "1024x1024", "aspect_ratio": "1:1", "image_size": "square_hd"},
            "horizontal": {"size": "1216x832", "aspect_ratio": "4:3", "image_size": "landscape_4_3"},
        },
    },
    "standard": {
        "label": "изображение",
        "model": IMAGE_STANDARD_MODEL,
        "base": {
            "num_inference_steps": 60,  # Максимальное качество (больше шагов = лучше детализация)
            "guidance_scale": 9.0,  # Максимальное соответствие промпту и качество
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
        "model": settings.fal_seedream_create_model,  # Модель для создания без входного изображения
        "base": {
            "output_format": "png",
            "guidance_scale": 12.0,  # Увеличено для максимального качества и детализации
            "num_inference_steps": 120,  # Увеличено для максимальной детализации и качества изображения
            "enhance_prompt_mode": "standard",  # Стандартный режим для максимального качества (вместо "fast")
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
        "model": settings.fal_nano_banana_pro_model,  # Nano Banana Pro через Fal.ai
        "base": {
            "num_inference_steps": 90,  # Максимальная прорисовка (больше шагов = лучше детализация)
            "guidance_scale": 10.0,  # Максимальное соответствие промпту и качество
            "output_format": "png",
        },
        "sizes": {
            # Старые размеры для обратной совместимости (не используются с новой системой форматов)
            "vertical": {"size": "1024x1792", "aspect_ratio": "9:16", "width": 1024, "height": 1792},
            "square": {"size": "1024x1024", "aspect_ratio": "1:1", "width": 1024, "height": 1024},
            "horizontal": {"size": "1792x1024", "aspect_ratio": "16:9", "width": 1792, "height": 1024},
        },
    },
    "flux2flex-create": {
        "label": "изображение",
        "model": settings.fal_flux2flex_model,  # Flux 2 Flex через Fal.ai
        "base": {
            "output_format": "png",
        },
        "sizes": {
            # Flux 2 Flex использует image_size как enum, размеры будут обработаны через get_model_format_mapping
            "vertical": {"size": "1024x1792", "aspect_ratio": "9:16", "width": 1024, "height": 1792},
            "square": {"size": "1024x1024", "aspect_ratio": "1:1", "width": 1024, "height": 1024},
            "horizontal": {"size": "1792x1024", "aspect_ratio": "16:9", "width": 1792, "height": 1024},
        },
    },
}

SIZE_BUTTONS = {
    IMAGE_SIZE_VERTICAL_BUTTON.lower(): "vertical",
    IMAGE_SIZE_SQUARE_BUTTON.lower(): "square",
    IMAGE_SIZE_HORIZONTAL_BUTTON.lower(): "horizontal",
}

# Маппинг новых кнопок форматов
FORMAT_BUTTONS = {
    IMAGE_FORMAT_SQUARE_1_1: ImageFormat.SQUARE_1_1,
    IMAGE_FORMAT_VERTICAL_3_4: ImageFormat.VERTICAL_3_4,
    IMAGE_FORMAT_HORIZONTAL_4_3: ImageFormat.HORIZONTAL_4_3,
    IMAGE_FORMAT_VERTICAL_4_5: ImageFormat.VERTICAL_4_5,
    IMAGE_FORMAT_VERTICAL_9_16: ImageFormat.VERTICAL_9_16,
    IMAGE_FORMAT_HORIZONTAL_16_9: ImageFormat.HORIZONTAL_16_9,
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
    operation_id: int | None = None,
    state: FSMContext | None = None,
) -> str:
    import asyncio
    from app.services.billing import BillingService
    from app.db.base import SessionLocal
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    # Определяем модель для расчета цены (до проверки баланса)
    model = base_options.get("model") if base_options else None
    selected_model = base_options.get("selected_model") if base_options else None
    is_nano_banana_pro = (
        model == "fal-ai/nano-banana-pro" or 
        "nano-banana-pro" in (model or "").lower() or 
        selected_model == "gpt-create" or
        "gpt-image-1-mini" in (model or "").lower()
    )
    
    # Проверка баланса (если operation_id не передан, проверяем баланс)
    if operation_id is None:
        from app.services.pricing import get_operation_price
        
        db = SessionLocal()
        try:
            user_id = message.from_user.id if message.from_user else None
            if not user_id:
                await message.answer("Ошибка: не удалось определить пользователя.")
                raise ValueError("User ID not found")
            
            user, _ = BillingService.get_or_create_user(db, user_id, message.from_user)
            
            # Получаем цену для отображения
            price = get_operation_price("generate", model, is_nano_banana_pro)
            
            # Check for active discount code in state or database
            discount_percent = None
            if state:
                discount_percent = await get_operation_discount_percent(state, user_id)
            
            success, error_msg, op_id = BillingService.charge_operation(
                db, user.id, "generate",
                model=model,
                is_nano_banana_pro=is_nano_banana_pro,
                discount_percent=discount_percent
            )
            
            if not success:
                balance = BillingService.get_user_balance(db, user.id)
                text = (
                    f"❌ **Недостаточно средств**\n\n"
                    f"Операция стоит: {price} ₽\n"
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
                raise ValueError(f"Insufficient balance: {error_msg}")
            
            operation_id = op_id
            logger.info("_enqueue_image_task: operation reserved, operation_id={}, price={}₽", operation_id, price)
        finally:
            db.close()
    
    # Очищаем промпт от возможных префиксов "Промпт: " или "Prompt: "
    prompt = prompt.strip()
    if prompt.lower().startswith("промпт:"):
        prompt = prompt[7:].strip()
    elif prompt.lower().startswith("prompt:"):
        prompt = prompt[7:].strip()
    
    logger.info("_enqueue_image_task: starting, prompt='{}', label='{}', base_options={}, operation_id={}", 
                prompt[:50], label, base_options, operation_id)
    if base_options:
        logger.info("_enqueue_image_task: base_options keys: {}, width: {}, height: {}, num_inference_steps: {}", 
                   list(base_options.keys()), base_options.get("width"), base_options.get("height"), base_options.get("num_inference_steps"))
    options = _build_notify_options(message, prompt, base_options)
    
    # Проверяем, является ли модель Nano Banana или Nano Banana Pro (могут принимать русский текст)
    is_nano_banana = model == IMAGE_STANDARD_MODEL or model == "fal-ai/nano-banana"
    logger.info("_enqueue_image_task: is_nano_banana={}, is_nano_banana_pro={}", is_nano_banana, is_nano_banana_pro)
    
    translated_prompt = prompt  # Default to original prompt
    if is_nano_banana or is_nano_banana_pro:
        model_name = "Nano Banana Pro" if is_nano_banana_pro else "Nano Banana"
        logger.info("_enqueue_image_task: skipping translation for {} model, using original Russian prompt", model_name)
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
    # Передаем operation_id в options для worker
    if operation_id:
        options["operation_id"] = operation_id
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
    operation_id: int | None = None,
    state: FSMContext | None = None,
) -> str:
    import asyncio
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
                raise ValueError("User ID not found")
            
            user, _ = BillingService.get_or_create_user(db, user_id, message.from_user)
            
            # Извлекаем модель из base_options для правильного расчета цены
            model = None
            if base_options and "model" in base_options:
                model = base_options["model"]
            
            logger.info("_enqueue_image_edit_task: extracted model='{}' from base_options for price calculation", model)
            price = get_operation_price("edit", model=model)
            logger.info("_enqueue_image_edit_task: calculated price={}₽ for edit operation with model='{}'", price, model)
            
            # Check for active discount code in state or database
            discount_percent = None
            if state:
                discount_percent = await get_operation_discount_percent(state, user_id)
            
            success, error_msg, op_id = BillingService.charge_operation(
                db, user.id, "edit",
                model=model,
                discount_percent=discount_percent
            )
            
            if not success:
                balance = BillingService.get_user_balance(db, user.id)
                text = (
                    f"❌ **Недостаточно средств**\n\n"
                    f"Редактирование стоит: {price} ₽\n"
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
                raise ValueError(f"Insufficient balance: {error_msg}")
            
            operation_id = op_id
            logger.info("_enqueue_image_edit_task: balance charged, operation_id={}, price={}₽", operation_id, price)
        finally:
            db.close()
    
    logger.info("_enqueue_image_edit_task: starting, prompt='{}', image_path='{}', base_options={}, operation_id={}", 
                prompt[:50], image_path, base_options, operation_id)
    base_payload = dict(base_options or {})
    base_payload.setdefault("model", IMAGE_EDIT_MODEL)
    
    # Определяем модель для выбора стратегии обработки промпта
    model_name = base_payload.get("model", IMAGE_EDIT_MODEL)
    is_seedream = _is_seedream_model(model_name)
    
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

    # Для Seedream используем упрощенный промпт без лишних дополнений - модель сама хорошо понимает запросы
    if is_seedream:
        logger.info("_enqueue_image_edit_task: Seedream detected, using simplified prompt without reinforcement instructions")
        # Используем только переведенный промпт без дополнительных инструкций
        if translated_prompt != prompt:
            options["provider_prompt"] = translated_prompt
    else:
        # Для других моделей (Chrono Edit и т.д.) используем полный набор инструкций
        logger.info("_enqueue_image_edit_task: building reinforcement prompt for non-Seedream model")
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
            if any(keyword in lowered for keyword in ("person", "человек", "люди", "человека", "мужчин", "женщин", "хозяин", "owner", "girl", "девушка", "девушки", "woman", "женщина", "man", "мужчина")):
                reinforcement_parts.append(
                    "The person must be realistically integrated into the scene with proper lighting, shadows, and perspective. "
                    "Ensure the person appears natural and seamlessly blended with the existing environment. "
                    "Maintain realistic human proportions and scale relative to other objects in the scene."
                )
                if any(keyword in lowered for keyword in ("full", "полный", "рост", "standing", "стоя", "стоит", "стоящий", "upright")):
                    reinforcement_parts.append(
                        "The person must be shown in full height, standing upright, with their entire body visible from head to feet."
                    )
                if any(keyword in lowered for keyword in ("second", "вторая", "второй", "another", "еще", "ещё")):
                    reinforcement_parts.append(
                        "Add an additional person to the scene. The new person should be distinct from any existing people and properly positioned in the composition."
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
    
    # Передаем operation_id в options для worker
    if operation_id:
        options["operation_id"] = operation_id
        logger.info("_enqueue_image_edit_task: added operation_id={} to options, options keys: {}", 
                    operation_id, list(options.keys()))
    else:
        logger.warning("_enqueue_image_edit_task: operation_id is None, not adding to options")
    
    logger.info("_enqueue_image_edit_task: calling enqueue_image_edit with prompt='{}', image_path='{}', model='{}', operation_id={}, options_keys={}", 
                prompt[:50], image_path, base_payload.get("model"), operation_id, list(options.keys()))
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
        "output_format": "png",  # Всегда используем PNG для максимального качества
    }
    # Добавляем width и height, если они переданы (для Nano Banana Pro)
    if "width" in overrides:
        options["width"] = overrides["width"]
    if "height" in overrides:
        options["height"] = overrides["height"]
    # Если output_format переопределен в overrides, используем его
    if "output_format" in overrides:
        options["output_format"] = overrides["output_format"]
    # Добавляем параметры качества, если они переданы (для Nano Banana Pro edit)
    if "num_inference_steps" in overrides:
        options["num_inference_steps"] = overrides["num_inference_steps"]
    if "guidance_scale" in overrides:
        options["guidance_scale"] = overrides["guidance_scale"]
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


async def _trigger_upscale_for_job(message: types.Message, job_id: str, operation_id: int | None = None, state: FSMContext | None = None) -> bool:
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
                return False
            
            user, _ = BillingService.get_or_create_user(db, user_id)
            price = get_operation_price("upscale")
            
            # Check for active discount code in state or database
            discount_percent = await get_operation_discount_percent(state, user_id) if state else None
            if discount_percent is None and user.operation_discount_percent:
                # Use discount from database if state is not available
                discount_percent = user.operation_discount_percent
            
            success, error_msg, op_id = BillingService.charge_operation(
                db, user.id, "upscale",
                discount_percent=discount_percent
            )
            
            if not success:
                balance = BillingService.get_user_balance(db, user.id)
                text = (
                    f"❌ **Недостаточно средств**\n\n"
                    f"Улучшение качества стоит: {price} ₽\n"
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
                return False
            
            operation_id = op_id
            logger.info("_trigger_upscale_for_job: balance charged, operation_id={}, price={}₽", operation_id, price)
        finally:
            db.close()
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
    
    # Передаем operation_id в options для worker
    if operation_id:
        options["operation_id"] = operation_id

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
        triggered = await _trigger_upscale_for_job(message, job_id, state=state)
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
    operation_id: int | None = None,
) -> bool:
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
                await _clear_retoucher_state(state)
                return False
            
            user, _ = BillingService.get_or_create_user(db, user_id)
            price = get_operation_price("retouch")
            
            # Check for active discount code in state or database
            discount_percent = None
            if state:
                discount_percent = await get_operation_discount_percent(state, user_id)
            
            success, error_msg, op_id = BillingService.charge_operation(
                db, user.id, "retouch",
                discount_percent=discount_percent
            )
            
            if not success:
                balance = BillingService.get_user_balance(db, user.id)
                text = (
                    f"❌ **Недостаточно средств**\n\n"
                    f"Ретушь стоит: {price} ₽\n"
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
                await _clear_retoucher_state(state)
                return False
            
            operation_id = op_id
            logger.info("_enqueue_retoucher_task: balance charged, operation_id={}, price={}₽", operation_id, price)
        finally:
            db.close()
    
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
    
    # Добавляем модель из preset в options (если указана)
    if "model" in preset:
        options["model"] = preset["model"]
    
    # Передаем operation_id в options для worker
    if operation_id:
        options["operation_id"] = operation_id

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
            await _send_error_notification(message, "_handle_retoucher_text")
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
            "• Seedream — более продвинутая модель, лучше добавляет персонажей и латинский текст\n"
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
    try:
        # Проверяем, не находимся ли мы в режиме "Написать"
        from app.bot.handlers.prompt_writer import PromptWriterStates
        current_state = await state.get_state()
        if current_state == PromptWriterStates.waiting_input:
            logger.info("handle_create: user is in prompt writer mode, showing message")
            await message.answer(
                "⚠️ Вы находитесь в режиме **«✍️ Написать»**.\n\n"
                "Для перехода в другой режим:\n"
                "• Нажмите кнопку **«ℹ️ Info»** для сброса текущей сессии\n"
                "• Затем выберите нужный режим\n\n"
                "Или введите текст промпта для генерации.",
                parse_mode="Markdown",
            )
            return
        
        # Получаем все данные состояния для диагностики
        data = await state.get_data()
        prompt = data.get("prompt")
        
        logger.info("handle_create called: user={}, has_prompt={}, prompt_length={}, all_keys={}", 
                    message.from_user.id if message.from_user else "unknown",
                    bool(prompt),
                    len(prompt) if prompt else 0,
                    list(data.keys()) if data else [])
        
        # Очищаем состояние Smart Merge при переходе в режим создания
        # чтобы избежать конфликтов с предыдущими сессиями
        await state.update_data(
            selected_model=None,
            SMART_MERGE_STAGE_KEY=None,
            SMART_MERGE_SOURCES_KEY=None,
            SMART_MERGE_MODEL_KEY=None,
            SMART_MERGE_SIZE_KEY=None,
        )
        
        # Если промпт уже есть в состоянии, показываем выбор моделей
        if prompt:
            await message.answer(
                "Выберите модель для создания изображения:\n"
                "• **Nano Banana Pro** — лучшая нейросеть, в т.ч. работает с длинными текстами на кириллице\n"
                "• **Nano Banana** — топовая нейросеть, пишет только заголовки на кириллице\n"
                "• **Seedream 4.5** — качественная нейросеть, пишет текст только на английском языке\n"
                "• **Flux 2 Flex** — оптимизирована для естественного вида изображений без излишней детализации",
                reply_markup=build_create_model_keyboard(),
                parse_mode="Markdown",
            )
        else:
            # Если промпта нет, просим его ввести
            logger.warning("handle_create: prompt not found in state for user={}, state_data={}", 
                          message.from_user.id if message.from_user else "unknown",
                          data)
            await message.answer(
                NO_PROMPT_TEXT,
                reply_markup=build_main_keyboard(),
            )
    except Exception as exc:
        logger.error("Error in handle_create: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_create")


async def handle_light(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора модели Flux Ultra после нажатия 'Создать'."""
    # Проверяем, не находимся ли мы в режиме Smart merge
    data = await state.get_data()
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    if smart_merge_stage:
        # Если мы в режиме Smart merge, не обрабатываем выбор модели для создания
        logger.debug("handle_light: ignoring because smart_merge_stage is active")
        return
    
    prompt = await _require_prompt(message, state)
    if not prompt:
        logger.warning("handle_light: prompt not found in state for user {}", 
                      message.from_user.id if message.from_user else "unknown")
        return
    logger.info("handle_light: prompt found: '{}', saving selected_model='light'", prompt[:50])
    await state.update_data(selected_model="light", prompt=prompt)
    await message.answer(
        "Вы выбрали Flux Ultra. Уточните формат изображения:",
        reply_markup=build_size_keyboard(),
    )


async def handle_standard(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора модели Nano Banana после нажатия 'Создать'."""
    try:
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
        
        format_hints = get_format_hints_text()
        format_message = (
            "Вы выбрали Nano Banana. Выберите формат изображения:\n\n"
            f"{format_hints}"
        )
        await message.answer(
            format_message,
            reply_markup=build_format_keyboard(),
        )
    except Exception as exc:
        logger.error("Error in handle_standard: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_standard")


async def handle_seedream_create(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора модели Seedream после нажатия 'Создать'."""
    try:
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
        
        format_hints = get_format_hints_text()
        format_message = (
            "Вы выбрали Seedream. Выберите формат изображения:\n\n"
            f"{format_hints}"
        )
        await message.answer(
            format_message,
            reply_markup=build_format_keyboard(),
        )
    except Exception as exc:
        logger.error("Error in handle_seedream_create: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_seedream_create")


async def handle_flux_flex_create(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора модели Flux 2 Flex после нажатия 'Создать'."""
    try:
        # Проверяем, не находимся ли мы в режиме Smart merge
        data = await state.get_data()
        smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
        if smart_merge_stage:
            logger.debug("handle_flux_flex_create: ignoring because smart_merge_stage is active")
            return
        
        prompt = await _require_prompt(message, state)
        if not prompt:
            logger.warning("handle_flux_flex_create: prompt not found in state for user {}", 
                          message.from_user.id if message.from_user else "unknown")
            return
        logger.info("handle_flux_flex_create: prompt found: '{}', saving selected_model='flux2flex-create'", prompt[:50])
        await state.update_data(selected_model="flux2flex-create", prompt=prompt)
        
        format_hints = get_format_hints_text()
        format_message = (
            "Вы выбрали Flux 2 Flex. Выберите формат изображения:\n\n"
            f"{format_hints}"
        )
        await message.answer(
            format_message,
            reply_markup=build_format_keyboard(),
        )
    except Exception as exc:
        logger.error("Error in handle_flux_flex_create: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_flux_flex_create")


async def handle_gpt_create(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора модели Nano Banana Pro после нажатия 'Создать'."""
    try:
        # Проверяем, не находимся ли мы в режиме Smart merge
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
        # Используем оригинальный промпт без автоматических добавок
        # Если пользователь хочет текст на изображении, он сам укажет это в промпте
        
        logger.info("handle_gpt_create: prompt found: '{}'", prompt[:100])
        await state.update_data(selected_model="gpt-create", prompt=prompt)
        
        format_hints = get_format_hints_text()
        format_message = (
            "Вы выбрали Nano Banana Pro. Выберите формат изображения:\n\n"
            f"{format_hints}"
        )
        # Показываем кнопки выбора формата (новая единая система)
        await message.answer(
            format_message,
            reply_markup=build_format_keyboard(),
        )
    except Exception as exc:
        logger.error("Error in handle_gpt_create: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_gpt_create")


async def handle_format_choice(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора формата (новая единая система из 6 форматов)."""
    try:
        text = message.text or ""
        logger.info("handle_format_choice called: text='{}'", text)
        
        # Получаем данные состояния в начале функции
        data = await state.get_data()
        
        # Проверяем, является ли это новой кнопкой формата
        format_id = FORMAT_BUTTONS.get(text)
        if not format_id:
            # Проверяем, находимся ли мы в режиме Smart Merge или Create
            smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
            selected_model = data.get("selected_model")
            if smart_merge_stage == "await_size" or (selected_model and data.get("prompt")):
                logger.info("handle_format_choice: user sent text '{}' instead of format button", text)
                format_hints = get_format_hints_text()
                await message.answer(
                    "⚠️ Пожалуйста, выберите формат изображения из предложенных кнопок:\n\n"
                    f"{format_hints}",
                    reply_markup=build_format_keyboard(),
                )
            else:
                logger.debug("handle_format_choice: not a format button and not in format selection stage, ignoring")
            return
        
        # Проверяем, находимся ли мы в режиме Smart Merge
        smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
        if smart_merge_stage == "await_size":
            # Обработка выбора формата для Smart Merge (Nano Banana Pro или Nano Banana)
            logger.info("handle_format_choice: processing format selection for Smart Merge")
            model_path = data.get(SMART_MERGE_MODEL_KEY)
            if not model_path:
                logger.warning("handle_format_choice: model_path not found for Smart Merge")
                await message.answer("Ошибка: модель не найдена. Начните заново.", reply_markup=build_main_keyboard())
                await state.clear()
                return
            
            # Определяем модель для получения параметров формата
            logger.info("handle_format_choice: model_path='{}', SMART_MERGE_PRO_MODEL='{}'", model_path, SMART_MERGE_PRO_MODEL)
            if model_path == SMART_MERGE_PRO_MODEL:
                model_for_format = settings.fal_nano_banana_pro_model
                logger.info("handle_format_choice: detected Nano Banana Pro edit model")
            elif model_path == SMART_MERGE_DEFAULT_MODEL:
                model_for_format = settings.fal_premium_model
                logger.info("handle_format_choice: detected Nano Banana edit model")
            elif model_path == SMART_MERGE_SEEDREAM_MODEL:
                model_for_format = settings.fal_seedream_edit_model  # Seedream 4.5 edit
                logger.info("handle_format_choice: detected Seedream edit model")
            else:
                logger.warning("handle_format_choice: model_path='{}' is not supported for Smart Merge format selection", model_path)
                await message.answer("Ошибка: модель не поддерживает выбор формата. Начните заново.", reply_markup=build_main_keyboard())
                await state.clear()
                return
            
            # Получаем параметры формата для модели
            format_spec = get_format_spec(format_id)
            format_params = get_model_format_mapping(model_for_format, format_id)
            
            # Определяем название модели для сообщения
            if model_path == SMART_MERGE_PRO_MODEL:
                model_display_name = "Nano Banana Pro"
            elif model_path == SMART_MERGE_DEFAULT_MODEL:
                model_display_name = "Nano Banana"
            elif model_path == SMART_MERGE_SEEDREAM_MODEL:
                model_display_name = "Seedream"
            else:
                model_display_name = "Unknown"
            
            # Для всех моделей переходим к сбору изображений
            # Качество для Nano Banana Pro будет запрошено в конце, после ввода промпта и изображений
            logger.info("handle_format_choice: going to collect stage for model {}", model_path)
            await state.update_data(
                {
                    SMART_MERGE_STAGE_KEY: "collect",
                    SMART_MERGE_SOURCES_KEY: [],
                    SMART_MERGE_SIZE_KEY: format_params,  # Сохраняем параметры формата
                    "selected_format": format_id.value,  # Сохраняем логический формат
                }
            )
            await message.answer(
                f"Изменение активировано ({model_display_name} edit, {format_spec.label}).\n"
                    "Отправьте до 8 изображений (фото или документы). "
                    "Когда закончите, опишите изменения текстом.\n\n"
                    "💡 Советы:\n"
                    "• Для объединения людей: «объедини 3х человек, все должны быть видны, стоят рядом»\n"
                    "• Для добавления объектов: «добавь девушку справа, добавь текст на стене»\n"
                    "• Для редактирования: «удали фон, измени цвет неба на красный»\n"
                    "• Укажите количество: «все 3 человека», «оба объекта», «все изображения»",
                    reply_markup=build_main_keyboard(),
                )
            return
        
        # Обычная обработка для Create (не Smart Merge)
        prompt: str | None = data.get("prompt")
        model_key: str | None = data.get("selected_model")
        logger.info("handle_format_choice: prompt='{}', model_key='{}'", prompt[:50] if prompt else None, model_key)

        if not prompt or not model_key:
            logger.warning("handle_format_choice: missing prompt or model_key")
            await message.answer(
                "Сначала напишите промпт и выберите модель.\n\n"
                "💡 Нужна помощь в написании промпта? Используйте кнопку «✍️ Написать».",
                reply_markup=build_main_keyboard()
            )
            await state.clear()
            return

        preset = MODEL_PRESETS.get(model_key)
        if not preset:
            logger.error("handle_format_choice: preset not found for model_key='{}'", model_key)
            await message.answer("Не удалось определить модель. Повторите запрос.", reply_markup=build_main_keyboard())
            await state.clear()
            return

        # Получаем параметры формата для модели
        format_spec = get_format_spec(format_id)
        format_params = get_model_format_mapping(preset["model"], format_id)
        logger.info("handle_format_choice: format_params for model='{}', format='{}': {}", 
                   preset["model"], format_id.value, format_params)
        
        base_options = {
            "model": preset["model"],
            "selected_model": model_key,
            "selected_format": format_id.value,  # Сохраняем логический формат для последующего преобразования
            **preset["base"],
            **format_params,
        }
        logger.info("handle_format_choice: base_options after merge: width={}, height={}, aspect_ratio={}, image_size={}", 
                   base_options.get("width"), base_options.get("height"), 
                   base_options.get("aspect_ratio"), base_options.get("image_size"))
        label = f"{preset['label']} · {format_spec.label}"
        logger.info("handle_format_choice: calling _enqueue_image_task with prompt='{}', label='{}', model='{}', format='{}'", 
                    prompt[:50], label, preset["model"], format_id.value)
        await _enqueue_image_task(
            message,
            prompt=prompt,
            label=label,
            base_options=base_options,
            state=state,
        )
        logger.info("handle_format_choice: _enqueue_image_task completed successfully")
        await state.clear()
    except Exception as exc:
        logger.error("Error in handle_format_choice: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_format_choice")


async def handle_quality_choice(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора качества для Nano Banana Pro edit."""
    try:
        text = message.text or ""
        logger.info("handle_quality_choice called: text='{}'", text)
        
        data = await state.get_data()
        smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
        
        # Проверяем, что мы в режиме ожидания выбора качества
        if smart_merge_stage != "await_quality":
            logger.debug("handle_quality_choice: not in await_quality stage (stage='{}'), ignoring", smart_merge_stage)
            return
        
        # Проверяем, что выбрана правильная кнопка
        if text not in {QUALITY_FASTER_BUTTON, QUALITY_BETTER_BUTTON}:
            logger.info("handle_quality_choice: user sent text '{}' instead of quality button", text)
            await message.answer(
                "⚠️ Пожалуйста, выберите режим качества с помощью кнопок:\n\n"
                "⚡ **Быстрее** — время генерации в районе минуты\n"
                "🎨 **Качественнее** — время генерации до 2х минут\n\n"
                "💡 Отличие режимов — в качестве и детализации изображения. "
                "Качественнее = выше качество и детализация, но дольше время генерации.",
                reply_markup=build_quality_keyboard(),
                parse_mode="Markdown",
            )
            return
        
        # Определяем параметры качества
        if text == QUALITY_FASTER_BUTTON:
            num_inference_steps = 60
            guidance_scale = 8.5
            quality_label = "Быстрее"
            time_hint = "в районе минуты"
        else:  # QUALITY_BETTER_BUTTON
            num_inference_steps = 120
            guidance_scale = 12.0
            quality_label = "Качественнее"
            time_hint = "до 2х минут"
        
        # Получаем промпт и изображения из состояния
        sources = data.get(SMART_MERGE_SOURCES_KEY) or []
        prompt_text = data.get("smart_merge_prompt")
        
        if not prompt_text or not sources or len(sources) == 0:
            logger.warning("handle_quality_choice: missing prompt or sources, cannot proceed")
            await message.answer(
                "⚠️ Ошибка: не найдены промпт или изображения. Начните заново.",
                reply_markup=build_main_keyboard(),
            )
            await state.clear()
            return
        
        # Сохраняем параметры качества
        await state.update_data(
            {
                "quality_num_inference_steps": num_inference_steps,
                "quality_guidance_scale": guidance_scale,
            }
        )
        
        logger.info("handle_quality_choice: quality settings saved: num_inference_steps={}, guidance_scale={}, launching task", 
                    num_inference_steps, guidance_scale)
        
        # Запускаем задачу
        await _enqueue_smart_merge_task(
            message,
            state,
            prompt=prompt_text,
            sources=sources,
            options_override=None,
        )
        await state.clear()
    except Exception as exc:
        logger.error("Error in handle_quality_choice: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_quality_choice")


async def handle_size_choice(message: types.Message, state: FSMContext) -> None:
    """Обработчик выбора размера (старая система для обратной совместимости)."""
    try:
        logger.info("handle_size_choice called: text='{}'", message.text)
        selection = (message.text or "").strip().lower()
        logger.info("handle_size_choice: selection='{}', SIZE_BUTTONS={}", selection, SIZE_BUTTONS)
        size_key = SIZE_BUTTONS.get(selection)
        logger.info("handle_size_choice: size_key='{}'", size_key)
        if not size_key:
            logger.warning("handle_size_choice: size_key not found for selection '{}'", selection)
            return

        data = await state.get_data()
    
        # Проверяем, находимся ли мы в режиме Smart Merge
        smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
        if smart_merge_stage == "await_size":
            # Обработка выбора размера для Smart Merge (Nano Banana Pro)
            logger.info("handle_size_choice: processing size selection for Smart Merge")
            model_path = data.get(SMART_MERGE_MODEL_KEY)
            if not model_path or model_path != SMART_MERGE_PRO_MODEL:
                logger.warning("handle_size_choice: model_path='{}' is not Nano Banana Pro for Smart Merge", model_path)
                await message.answer("Ошибка: модель не найдена. Начните заново.", reply_markup=build_main_keyboard())
                await state.clear()
                return
            
            # Получаем размеры из preset для gpt-create (Nano Banana Pro)
            preset = MODEL_PRESETS.get("gpt-create")
            if not preset:
                logger.error("handle_size_choice: preset 'gpt-create' not found")
                await message.answer("Не удалось определить размеры. Повторите запрос.", reply_markup=build_main_keyboard())
                await state.clear()
                return
            
            size_options = preset["sizes"].get(size_key)
            if not size_options:
                logger.error("handle_size_choice: size_options not found for size_key='{}'", size_key)
                await message.answer("Не удалось определить формат. Попробуйте снова.", reply_markup=build_size_keyboard())
                return
            
            # Сохраняем размер и активируем режим сбора изображений
            await state.update_data(
                {
                    SMART_MERGE_STAGE_KEY: "collect",
                    SMART_MERGE_SOURCES_KEY: [],
                    SMART_MERGE_SIZE_KEY: size_options,  # Сохраняем размеры (size, aspect_ratio, width, height)
                }
            )
            
            await message.answer(
                f"Изменение активировано (Nano Banana Pro edit, {message.text.strip()}).\n"
                "Отправьте до 8 изображений (фото или документы). "
                "Когда закончите, опишите изменения текстом.\n\n"
                "💡 Советы:\n"
                "• Для объединения людей: «объедини 3х человек, все должны быть видны, стоят рядом»\n"
                "• Для добавления объектов: «добавь девушку справа, добавь текст на стене»\n"
                "• Для редактирования: «удали фон, измени цвет неба на красный»\n"
                "• Укажите количество: «все 3 человека», «оба объекта», «все изображения»",
                reply_markup=build_main_keyboard(),
            )
            return
    
        # Обычная обработка для Create (не Smart Merge)
        prompt: str | None = data.get("prompt")
        model_key: str | None = data.get("selected_model")
        logger.info("handle_size_choice: prompt='{}', model_key='{}'", prompt[:50] if prompt else None, model_key)

        if not prompt or not model_key:
            logger.warning("handle_size_choice: missing prompt or model_key")
            await message.answer(
                "Сначала напишите промпт и выберите модель.\n\n"
                "💡 Нужна помощь в написании промпта? Используйте кнопку «✍️ Написать».",
                reply_markup=build_main_keyboard()
            )
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
            "selected_model": model_key,  # Сохраняем selected_model для worker'а
            **preset["base"],
            **size_options,
        }
        label = f"{preset['label']} · {message.text.strip()}"
        logger.info("handle_size_choice: calling _enqueue_image_task with prompt='{}', label='{}', model='{}'", 
                    prompt[:50], label, preset["model"])
        await _enqueue_image_task(
            message,
            prompt=prompt,
            label=label,
            base_options=base_options,
            state=state,
        )
        logger.info("handle_size_choice: _enqueue_image_task completed successfully")
        await state.clear()
    except Exception as exc:
        logger.error("Error in handle_size_choice: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_size_choice")


async def _enqueue_smart_merge_task(
    message: types.Message,
    state: FSMContext,
    *,
    prompt: str,
    sources: list[dict[str, str | None]],
    options_override: dict[str, str] | None = None,
    operation_id: int | None = None,
) -> str:
    from app.services.billing import BillingService
    from app.services.pricing import get_operation_price
    from app.db.base import SessionLocal
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    # Получаем выбранную модель, размер и параметры качества из состояния, если они есть
    data = await state.get_data()
    selected_model = data.get(SMART_MERGE_MODEL_KEY)
    selected_size = data.get(SMART_MERGE_SIZE_KEY)  # Размеры для Nano Banana Pro
    
    # Определяем, является ли это Nano Banana Pro для расчета цены
    is_nano_banana_pro_merge = (
        selected_model == SMART_MERGE_PRO_MODEL or 
        selected_model == "fal-ai/nano-banana-pro" or 
        selected_model == "fal-ai/nano-banana-pro/edit" or
        (options_override and options_override.get("model") == SMART_MERGE_PRO_MODEL)
    )
    
    # Проверка баланса (если operation_id не передан, проверяем баланс)
    if operation_id is None:
        db = SessionLocal()
        try:
            user_id = message.from_user.id if message.from_user else None
            if not user_id:
                await message.answer("Ошибка: не удалось определить пользователя.")
                raise ValueError("User ID not found")
            
            # Get telegram user object if available
            telegram_user = message.from_user if hasattr(message, 'from_user') and message.from_user else None
            user, _ = BillingService.get_or_create_user(db, user_id, telegram_user)
            price = get_operation_price("merge", selected_model, is_nano_banana_pro_merge)
            
            # Get image count and prompt for statistics
            image_count = len(sources) if sources else None
            prompt_text = prompt if prompt else None
            
            # Check for active discount code in state or database
            discount_percent = await get_operation_discount_percent(state, user_id)
            
            success, error_msg, op_id = BillingService.charge_operation(
                db, user.id, "merge",
                model=selected_model,
                is_nano_banana_pro=is_nano_banana_pro_merge,
                discount_percent=discount_percent,
                prompt=prompt_text,
                image_count=image_count
            )
            
            if not success:
                balance = BillingService.get_user_balance(db, user.id)
                text = (
                    f"❌ **Недостаточно средств**\n\n"
                    f"Изменение стоит: {price} ₽\n"
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
                raise ValueError(f"Insufficient balance: {error_msg}")
            
            operation_id = op_id
            logger.info("_enqueue_smart_merge_task: balance charged, operation_id={}, price={}₽", operation_id, price)
        finally:
            db.close()
    
    # Если модель выбрана через кнопку, используем её (если не переопределена в options_override)
    if selected_model and (not options_override or "model" not in options_override):
        options_override = options_override or {}
        options_override["model"] = selected_model
    
    # Если размер выбран для Nano Banana Pro, используем его
    if selected_size and isinstance(selected_size, dict):
        if not options_override:
            options_override = {}
        # Обновляем size, aspect_ratio, width, height из selected_size
        if "size" in selected_size:
            options_override["size"] = selected_size["size"]
        if "aspect_ratio" in selected_size:
            options_override["aspect_ratio"] = selected_size["aspect_ratio"]
        if "width" in selected_size:
            options_override["width"] = selected_size["width"]
        if "height" in selected_size:
            options_override["height"] = selected_size["height"]
        logger.info("_enqueue_smart_merge_task: using selected size from state: {}", selected_size)
    
    # Для Nano Banana Pro edit используем оптимизированные параметры по умолчанию
    # (убрали выбор качества, используем параметры из режима "Качественнее", но немного сниженные)
    if selected_model == SMART_MERGE_PRO_MODEL:
        if not options_override:
            options_override = {}
        # Устанавливаем параметры: 100 шагов и 11.0 для guidance_scale
        options_override.setdefault("num_inference_steps", 100)
        options_override.setdefault("guidance_scale", 11.0)
        logger.info("_enqueue_smart_merge_task: using optimized default parameters for Nano Banana Pro edit: num_inference_steps=100, guidance_scale=11.0")
    
    base_options = _build_smart_merge_base_options(options_override)
    options = _build_notify_options(message, prompt, base_options)
    
    # Передаем operation_id в options для worker
    if operation_id:
        options["operation_id"] = operation_id
    
    # Проверяем, является ли модель Nano Banana или Nano Banana Pro (могут принимать русский текст)
    model = base_options.get("model") if base_options else None
    is_nano_banana = model == SMART_MERGE_DEFAULT_MODEL or model == settings.fal_premium_model or model == "fal-ai/nano-banana/edit"
    is_nano_banana_pro = (
        model == SMART_MERGE_PRO_MODEL or
        model == settings.fal_nano_banana_pro_model or
        model == "fal-ai/nano-banana-pro" or
        model == "fal-ai/nano-banana-pro/edit"
    )
    
    # Переводим промпт только если это не Nano Banana и не Nano Banana Pro
    if is_nano_banana or is_nano_banana_pro:
        model_name = "Nano Banana Pro" if is_nano_banana_pro else "Nano Banana"
        logger.info("Smart merge: skipping translation for {} model, using original Russian prompt", model_name)
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
        "✏️ Запускаю изменение изображений.\nОбрабатываю ваши изображения.",
        reply_markup=build_main_keyboard(),
    )
    return job_id


async def handle_edit_start(message: types.Message, state: FSMContext) -> None:
    try:
        await state.clear()
        await state.update_data({EDIT_STAGE_KEY: "await_source"})
        await message.answer(
            "✏️ Редактирование изображений\n\n"
            "Загрузите изображение, которое нужно отредактировать (как фото или документ).\n\n"
            "💡 Что можно делать:\n"
            "• Удалять объекты из изображения\n"
            "• Добавлять новые объекты или персонажей\n"
            "• Изменять детали (цвет, размер, форму)\n"
            "• Добавлять текст на изображение\n"
            "• Заменять элементы сцены\n\n"
            "Если хотите изменить недавно сгенерированное изображение — нажмите кнопку «Редактировать» под ним.",
            reply_markup=build_main_keyboard(),
        )
    except Exception as exc:
        logger.error("Error in handle_edit_start: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_edit_start")


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
        triggered = await _trigger_upscale_for_job(callback.message, job_id, state=state)
        if triggered:
            await callback.answer("Апскейл запущен!", show_alert=False)
        else:
            await callback.answer("Не удалось запустить апскейл.", show_alert=True)


async def handle_upscale_button(message: types.Message, state: FSMContext) -> None:
    if not message.chat:
        return
    
    # Проверяем, не находимся ли мы в режиме "Написать"
    from app.bot.handlers.prompt_writer import PromptWriterStates
    current_state = await state.get_state()
    if current_state == PromptWriterStates.waiting_input:
        logger.info("handle_upscale_button: user is in prompt writer mode, showing message")
        await message.answer(
            "⚠️ Вы находитесь в режиме **«✍️ Написать»**.\n\n"
            "Для перехода в другой режим:\n"
            "• Нажмите кнопку **«ℹ️ Info»** для сброса текущей сессии\n"
            "• Затем выберите нужный режим\n\n"
            "Или введите текст промпта для генерации.",
            parse_mode="Markdown",
        )
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
    # ВАЖНО: Проверяем состояние ПЕРВЫМ ДЕЛОМ, до любой обработки текста
    # Это нужно для того, чтобы не перехватывать сообщения для других обработчиков
    current_state = await state.get_state()
    from app.bot.handlers.billing import PaymentStates, OperationDiscountStates
    from app.bot.handlers.help import HelpStates
    if current_state == HelpStates.waiting_ai_assistant_input.state:
        logger.info("handle_prompt_input: skipping, user is in waiting_ai_assistant_input state")
        return
    if current_state == HelpStates.waiting_support_message.state:
        logger.info("handle_prompt_input: skipping, user is in waiting_support_message state")
        return
    if current_state == PaymentStates.WAIT_DISCOUNT_CODE.state:
        logger.info("handle_prompt_input: skipping, user is in WAIT_DISCOUNT_CODE state")
        return
    if current_state == PaymentStates.WAIT_CUSTOM_AMOUNT.state:
        logger.info("handle_prompt_input: skipping, user is in WAIT_CUSTOM_AMOUNT state")
        return
    if current_state == OperationDiscountStates.WAIT_OPERATION_DISCOUNT_CODE.state:
        logger.info("handle_prompt_input: skipping, user is in WAIT_OPERATION_DISCOUNT_CODE state")
        return
    
    # НЕ проверяем состояние здесь - обработчик с фильтром состояния (handle_prompt_writer_text)
    # должен иметь приоритет и обрабатываться первым для сообщений в состоянии waiting_input
    # Если handle_prompt_writer_text не сработал, значит состояние не waiting_input, и мы обрабатываем как обычный промпт
    
    text = (message.text or "").strip()
    # Нормализация кодировки: убеждаемся, что текст в UTF-8
    if isinstance(text, str):
        try:
            # Если строка уже в UTF-8, это не вызовет ошибку
            text = text.encode('utf-8').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Если ошибка, пробуем исправить
            text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    
    data = await state.get_data()
    
    logger.info("handle_prompt_input called: text='{}', user_id={}", text, message.from_user.id if message.from_user else "unknown")
    logger.debug("handle_prompt_input: IMAGE_EDIT_CHRONO_BUTTON='{}', IMAGE_EDIT_SEDEDIT_BUTTON='{}'", 
                 IMAGE_EDIT_CHRONO_BUTTON, IMAGE_EDIT_SEDEDIT_BUTTON)
    
    # Проверяем, не является ли это кнопкой меню - если да, не обрабатываем
    text_lower = text.lower()
    menu_buttons = [
        CREATE_BUTTON.lower(),
        PROMPT_WRITER_BUTTON.lower(),
        IMAGE_EDIT_BUTTON.lower(),
        IMAGE_SMART_MERGE_BUTTON.lower(),
        IMAGE_RETOUCHER_BUTTON.lower(),
        IMAGE_STYLISH_TEXT_BUTTON.lower(),
        IMAGE_FACE_SWAP_BUTTON.lower(),
        IMAGE_UPSCALE_BUTTON.lower(),
        INFO_BUTTON.lower(),
        BALANCE_BUTTON.lower(),
    ]
    if text_lower in menu_buttons:
        logger.info("handle_prompt_input: ignoring menu button '{}' (lowercase: '{}')", text, text_lower)
        return
    
    # Дополнительная проверка на кнопку баланса ПЕРЕД проверкой других кнопок меню
    if text_lower == BALANCE_BUTTON.lower() or text == BALANCE_BUTTON:
        logger.info("handle_prompt_input: detected balance button '{}', ignoring (should be handled by balance handler)", text)
        return
    
    # Проверяем кнопки выбора модели редактирования САМЫМ ПЕРВЫМ, до всех остальных проверок
    # Проверяем без учета регистра
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
    # ВАЖНО: включаем кнопки моделей, чтобы они обрабатывались своими handlers
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
    
    # Игнорируем кнопки выбора модели - они обрабатываются своими handlers
    if text == IMAGE_STANDARD_BUTTON or text == IMAGE_SEEDREAM_CREATE_BUTTON or text == IMAGE_GPT_CREATE_BUTTON or text == IMAGE_FLUX2FLEX_CREATE_BUTTON:
        return
    
    # Игнорируем кнопки выбора размера - они обрабатываются handle_size_choice
    if text in (IMAGE_SIZE_VERTICAL_BUTTON, IMAGE_SIZE_SQUARE_BUTTON, IMAGE_SIZE_HORIZONTAL_BUTTON):
        return
    
    # Игнорируем новые кнопки форматов - они обрабатываются handle_format_choice
    if text in FORMAT_BUTTONS:
        return
    
    # Проверяем, не находимся ли мы в режиме Stylish text
    stylish_stage = data.get("stylish_stage")
    if stylish_stage:
        logger.debug("handle_prompt_input: skipping because stylish_stage='{}' is active", stylish_stage)
        # Пропускаем обработку - пусть обрабатывает stylish_text handler
        return

    if not text or text.startswith("/"):
        await message.answer(
            "Сначала напишите промпт, затем выберите модель.\n\n"
            "💡 Нужна помощь в написании промпта? Используйте кнопку «✍️ Написать»."
        )
        return

    upscale_stage = data.get(UPSCALE_STAGE_KEY)
    if upscale_stage == "await_source":
        await _handle_upscale_text(message, state, text)
        return

    # КРИТИЧЕСКИ ВАЖНО: Очистка состояния Smart Merge ДО всех проверок
    # Smart Merge активируется ТОЛЬКО через кнопку "✏️ Изменить" и требует загрузки изображений
    # Если пользователь создает изображение (кнопка "🎨 Создать"), то Smart Merge должен быть полностью проигнорирован
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    smart_merge_model = data.get(SMART_MERGE_MODEL_KEY)
    selected_model = data.get("selected_model")
    sources = data.get(SMART_MERGE_SOURCES_KEY) or []
    
    logger.info("handle_prompt_input: BEFORE cleanup - selected_model='{}', smart_merge_stage='{}', smart_merge_model='{}', sources_count={}, text='{}'", 
                selected_model, smart_merge_stage, smart_merge_model, len(sources), text[:50] if text else None)
    
    # КРИТИЧЕСКИ ВАЖНО: Если есть smart_merge_stage == "collect", но нет источников И нет модели - это старое состояние
    # Smart Merge в стадии "collect" с моделью - это активный процесс, нужно показать подсказку
    # Если нет модели - это старое состояние, очищаем
    # Проверяем ДО всех остальных проверок Smart Merge
    if smart_merge_stage == "collect" and len(sources) == 0 and not smart_merge_model:
        logger.warning("handle_prompt_input: clearing stale Smart Merge state (collect without sources and model) - this is CREATE mode. selected_model='{}', smart_merge_stage='{}', smart_merge_model='{}'", 
                      selected_model, smart_merge_stage, smart_merge_model)
        await state.update_data(
            SMART_MERGE_STAGE_KEY=None,
            SMART_MERGE_SOURCES_KEY=None,
            SMART_MERGE_SIZE_KEY=None,
            SMART_MERGE_MODEL_KEY=None,
        )
        # Перечитываем данные после очистки и обновляем переменные
        data = await state.get_data()
        smart_merge_stage = None
        smart_merge_model = None
        sources = []
        logger.info("handle_prompt_input: AFTER cleanup - smart_merge_stage='{}', smart_merge_model='{}', sources_count={}", 
                    smart_merge_stage, smart_merge_model, len(sources))
    
    # Если есть selected_model - это точно режим создания, игнорируем Smart Merge
    if selected_model:
        smart_merge_stage = None
        smart_merge_model = None
        sources = []
    
    # Проверяем стадии Smart Merge ТОЛЬКО если это действительно режим Smart Merge
    # (есть стадия Smart Merge И нет selected_model для создания)
    if smart_merge_stage == "await_model" and not selected_model:
        # Пользователь должен выбрать модель для объединения
        logger.info("handle_prompt_input: detected await_model stage, user sent text instead of model button")
        await message.answer(
            "⚠️ Пожалуйста, выберите модель из предложенных кнопок:\n\n"
            "• **Nano Banana Pro edit** — лучшая нейросеть, в т.ч. работает с длинными текстами на кириллице\n"
            "• **Nano Banana edit** — топовая нейросеть, пишет только заголовки на кириллице\n"
            "• **Seedream edit** — качественная нейросеть, пишет текст только на английском языке",
            reply_markup=build_smart_merge_model_keyboard(),
            parse_mode="Markdown",
        )
        return
    # Убрана стадия await_quality - выбор качества больше не требуется для Nano Banana Pro edit
    
    if smart_merge_stage == "await_size" and smart_merge_model and not selected_model:
        # Пользователь должен выбрать формат изображения
        logger.info("handle_prompt_input: detected await_size stage, user sent text instead of format button")
        format_hints = get_format_hints_text()
        await message.answer(
            "⚠️ Пожалуйста, выберите формат изображения из предложенных кнопок:\n\n"
            f"{format_hints}",
            reply_markup=build_format_keyboard(),
        )
        return
    
    # Если мы на этапе "collect" но источников нет - показываем подсказку
    if smart_merge_stage == "collect" and smart_merge_model is not None and not selected_model:
        if not sources or len(sources) == 0:
            logger.info("handle_prompt_input: collect stage but no sources, showing hint to send images")
            await message.answer(
                "⚠️ Сначала отправьте изображение (фото или документ).\n\n"
                "Отправьте до 8 изображений. Когда закончите, опишите изменения текстом.\n\n"
                "💡 Советы:\n"
                "• Для объединения людей: «объедини 3х человек, все должны быть видны, стоят рядом»\n"
                "• Для добавления объектов: «добавь девушку справа, добавь текст на стене»\n"
                "• Для редактирования: «удали фон, измени цвет неба на красный»\n"
                "• Укажите количество: «все 3 человека», «оба объекта», «все изображения»",
                reply_markup=build_main_keyboard(),
            )
            return
    
    # Обрабатываем Smart Merge только если это действительно режим Smart Merge
    # (есть модель Smart Merge, есть источники, И нет selected_model для создания)
    # ВАЖНО: Если sources пустые - это НЕ Smart Merge, это режим создания
    # КРИТИЧЕСКИ ВАЖНО: Проверяем, что sources не пустой список (явная проверка)
    # Если smart_merge_stage был очищен выше (стал None), то эта проверка не сработает
    if smart_merge_stage == "collect" and smart_merge_model is not None and sources and len(sources) > 0 and not selected_model:
        logger.info(
            "Smart merge text input: user={}, stage={}, model={}, sources_count={}, sources={}",
            message.from_user.id if message.from_user else "unknown",
            smart_merge_stage,
            smart_merge_model,
            len(sources),
            [s.get("path", "no_path") for s in sources],
        )
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
                "⚠️ Не удалось распознать описание. Напишите сцену текстом, например: «Девушка стоит рядом с автомобилем, утренний свет».",
                reply_markup=build_main_keyboard(),
            )
            return
        if len(prompt_text) < MIN_PROMPT_LENGTH:
            await message.answer("⚠️ Промпт слишком короткий. Пожалуйста, уточните запрос.")
            return
        
        # Для Nano Banana Pro edit сразу запускаем задачу с оптимизированными параметрами
        # (убрали выбор качества, так как разница во времени генерации незначительна)
        else:
            # Для других моделей сразу запускаем задачу
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
            "Изменение уже активно. Опишите изменения текстом или нажмите «ℹ️ Info» для сброса.",
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

    # ВАЖНО: Проверяем этап создания ДО проверки длины промпта
    # Если selected_model уже установлен, значит пользователь на этапе выбора формата
    prompt = data.get("prompt")
    selected_model = data.get("selected_model")
    
    if selected_model and prompt:
        # Пользователь на этапе выбора формата - показываем подсказку
        logger.info("handle_prompt_input: selected_model='{}' already set, user is at format selection stage, showing format hint", selected_model)
        await message.answer(
            "Пожалуйста, выберите формат изображения из предложенных кнопок.",
            reply_markup=build_format_keyboard(),
        )
        return
    
    if prompt and not selected_model:
        # Промпт уже есть, но модель не выбрана - пользователь на этапе выбора модели
        logger.info("handle_prompt_input: prompt exists but selected_model not set, user is at model selection stage, showing model hint")
        await message.answer(
            "Пожалуйста, выберите модель для создания изображения из предложенных кнопок:\n"
            "• **Nano Banana Pro** — лучшая нейросеть, в т.ч. работает с длинными текстами на кириллице\n"
            "• **Nano Banana** — топовая нейросеть, пишет только заголовки на кириллице\n"
            "• **Seedream 4.5** — качественная нейросеть, пишет текст только на английском языке\n"
            "• **Flux 2 Flex** — оптимизирована для естественного вида изображений без излишней детализации",
            reply_markup=build_create_model_keyboard(),
            parse_mode="Markdown",
        )
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

    # Устанавливаем состояние для гарантированного сохранения данных между сообщениями
    await state.set_state(ImageStates.prompt_saved)
    
    # Сохраняем промпт, но НЕ очищаем состояние полностью - только сбрасываем selected_model и edit_stage
    await state.update_data(prompt=cleaned_text, selected_model=None, edit_stage=None)
    
    # Проверяем, что промпт сохранился
    saved_data = await state.get_data()
    saved_prompt = saved_data.get("prompt")
    logger.info("handle_prompt_input: saved prompt, length={}, matches={}, all_keys={}", 
                len(saved_prompt) if saved_prompt else 0,
                saved_prompt == cleaned_text if saved_prompt else False,
                list(saved_data.keys()) if saved_data else [])
    
    # Сразу показываем выбор моделей после принятия промпта
    # Порядок моделей (сверху вниз): 1. Nano Banana Pro, 2. Nano Banana, 3. Seedream
    await message.answer(
        "Промпт принят ✅.\nВыберите модель для создания изображения:\n"
        "• **Nano Banana Pro** — лучшая нейросеть, в т.ч. работает с длинными текстами на кириллице\n"
        "• **Nano Banana** — топовая нейросеть, пишет только заголовки на кириллице\n"
        "• **Seedream 4.5** — качественная нейросеть, пишет текст только на английском языке\n"
        "• **Flux 2 Flex** — оптимизирована для естественного вида изображений без излишней детализации",
        reply_markup=build_create_model_keyboard(),
        parse_mode="Markdown",
    )


async def handle_edit_media(message: types.Message, state: FSMContext) -> None:
    logger.info(
        "handle_edit_media called: user={}, has_photo={}, has_document={}",
        message.from_user.id if message.from_user else "unknown",
        bool(message.photo),
        bool(message.document),
    )
    data = await state.get_data()
    current_state = await state.get_state()
    
    # Проверяем, не находимся ли мы в режиме Stylish text
    stylish_stage = data.get("stylish_stage")
    if stylish_stage:
        logger.debug("Skipping handle_edit_media - stylish_stage={}", stylish_stage)
        # Пропускаем обработку - пусть обрабатывает stylish_text handler
        return
    
    stage = data.get(EDIT_STAGE_KEY)
    upscale_stage = data.get(UPSCALE_STAGE_KEY)
    smart_merge_stage = data.get(SMART_MERGE_STAGE_KEY)
    retoucher_stage = data.get(RETOUCHER_STAGE_KEY)

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


    if smart_merge_stage == "await_model":
        # Пользователь должен выбрать модель для изменения
        logger.info("handle_edit_media: detected await_model stage, user sent media instead of model button")
        await message.answer(
            "⚠️ Пожалуйста, сначала выберите модель из предложенных кнопок:\n\n"
            "• **Nano Banana Pro edit** — лучшая нейросеть, в т.ч. работает с длинными текстами на кириллице\n"
            "• **Nano Banana edit** — топовая нейросеть, пишет только заголовки на кириллице\n"
            "• **Seedream edit** — качественная нейросеть, пишет текст только на английском языке",
            reply_markup=build_smart_merge_model_keyboard(),
            parse_mode="Markdown",
        )
        return
    if smart_merge_stage == "await_size":
        # Пользователь должен выбрать формат изображения
        logger.info("handle_prompt_input: detected await_size stage, user sent text instead of format button")
        format_hints = get_format_hints_text()
        await message.answer(
            "⚠️ Пожалуйста, выберите формат изображения из предложенных кнопок:\n\n"
            f"{format_hints}",
            reply_markup=build_format_keyboard(),
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

        # Проверка баланса и резервирование операции
        from app.services.billing import BillingService
        from app.services.pricing import get_operation_price
        from app.db.base import SessionLocal
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        db = SessionLocal()
        operation_id = None
        try:
            user_id = message.from_user.id if message.from_user else None
            if not user_id:
                await message.answer("Ошибка: не удалось определить пользователя.")
                await _clear_upscale_state(state)
                return
            
            user, _ = BillingService.get_or_create_user(db, user_id)
            price = get_operation_price("upscale")
            
            # Check for active discount code in state or database
            discount_percent = None
            if state:
                discount_percent = await get_operation_discount_percent(state, user_id)
            
            success, error_msg, op_id = BillingService.charge_operation(
                db, user.id, "upscale",
                discount_percent=discount_percent
            )
            
            if not success:
                balance = BillingService.get_user_balance(db, user.id)
                text = (
                    f"❌ **Недостаточно средств**\n\n"
                    f"Улучшение качества стоит: {price} ₽\n"
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
                await _clear_upscale_state(state)
                return
            
            operation_id = op_id
            logger.info("handle_upscale_media: balance charged, operation_id={}, price={}₽", operation_id, price)
        finally:
            db.close()

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
        
        # Передаем operation_id в options для worker
        if operation_id:
            options["operation_id"] = operation_id
            logger.info("handle_upscale_media: adding operation_id={} to options for job", operation_id)

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
        
        # Определяем модель из state или используем модель по умолчанию
        # Проверяем, была ли выбрана модель ранее (для Seedream или Chrono)
        selected_edit_model = data.get("selected_edit_model")  # Может быть установлено при выборе модели
        if selected_edit_model:
            model_path = IMAGE_EDIT_ALT_MODEL if selected_edit_model == "seedream" else IMAGE_EDIT_MODEL
        else:
            # Используем модель по умолчанию (Chrono Edit)
            model_path = IMAGE_EDIT_MODEL
        
        await _enqueue_image_edit_task(
            message,
            prompt=prompt_text,
            image_path=source_path,
            mask_path=saved_path,
            base_options={"model": model_path},
            state=state,
        )
        await state.clear()


async def handle_edit_model_choice(
    message: types.Message,
    state: FSMContext,
    ignore_stage_check: bool = False,
) -> None:
    try:
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
        
        # Сохраняем выбранную модель в state для последующего использования
        await state.update_data(selected_edit_model="seedream" if is_seedream else "chrono")
        
        await _enqueue_image_edit_task(
            message,
            prompt=prompt_text,
            image_path=source_path,
            mask_path=None,
            base_options={"model": model_path},
            state=state,
        )
        logger.info("handle_edit_model_choice: edit task enqueued successfully")
        await state.clear()
    except Exception as outer_exc:
        logger.error("Error in handle_edit_model_choice: {}", outer_exc, exc_info=True)
        await _send_error_notification(message, "handle_edit_model_choice")
        try:
            await state.clear()
        except Exception:
            pass


async def handle_smart_merge_start(message: types.Message, state: FSMContext) -> None:
    try:
        # Проверяем, не находимся ли мы в режиме "Написать"
        from app.bot.handlers.prompt_writer import PromptWriterStates
        current_state = await state.get_state()
        if current_state == PromptWriterStates.waiting_input:
            logger.info("handle_smart_merge_start: user is in prompt writer mode, showing message")
            await message.answer(
                "⚠️ Вы находитесь в режиме **«✍️ Написать»**.\n\n"
                "Для перехода в другой режим:\n"
                "• Нажмите кнопку **«ℹ️ Info»** для сброса текущей сессии\n"
                "• Затем выберите нужный режим\n\n"
                "Или введите текст промпта для генерации.",
                parse_mode="Markdown",
            )
            return
        
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
            "✏️ **Изменение изображений**\n"
            "**Что можно делать:**\n"
            "• Удалить объекты — «удали всех людей на фоне», «убери машину справа»\n"
            "• Добавить объекты — «добавь девушку справа», «добавь дерево на заднем плане»\n"
            "• Изменить цвет — «измени цвет неба на красный», «сделай платье синим»\n"
            "• Создать на основе референса — загрузите фото и опишите изменения\n"
            "• Объединить изображения — отправьте до 8 изображений и опишите сцену\n"
            "• Добавить текст — «добавь текст 'Привет' в центре»\n\n"
            "**Выберите модель:**\n"
            "• **Nano Banana Pro edit** — лучшая нейросеть, в т.ч. работает с длинными текстами на кириллице\n"
            "• **Nano Banana edit** — топовая нейросеть, пишет только заголовки на кириллице\n"
            "• **Seedream edit** — качественная нейросеть, пишет текст только на английском языке",
            reply_markup=build_smart_merge_model_keyboard(),
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("Error in handle_smart_merge_start: {}", exc, exc_info=True)
        await _send_error_notification(message, "handle_smart_merge_start")


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
    if selection not in {IMAGE_SMART_MERGE_PRO_BUTTON, IMAGE_SMART_MERGE_NANO_BUTTON, IMAGE_SMART_MERGE_SEEDREAM_BUTTON}:
        logger.info("handle_smart_merge_model_choice: user sent text '{}' instead of model button", selection)
        await message.answer(
            "⚠️ Пожалуйста, выберите модель для изменения из предложенных кнопок:\n\n"
            "• **Nano Banana Pro edit** — лучшая нейросеть, в т.ч. работает с длинными текстами на кириллице\n"
            "• **Nano Banana edit** — топовая нейросеть, пишет только заголовки на кириллице\n"
            "• **Seedream edit** — качественная нейросеть, пишет текст только на английском языке",
            reply_markup=build_smart_merge_model_keyboard(),
            parse_mode="Markdown",
        )
        return
    
    logger.info("handle_smart_merge_model_choice: processing selection '{}' for smart merge", selection)
    
    # Определяем модель на основе выбора
    if selection == IMAGE_SMART_MERGE_PRO_BUTTON:
        model_path = SMART_MERGE_PRO_MODEL
        model_name = "Nano Banana Pro"
    elif selection == IMAGE_SMART_MERGE_NANO_BUTTON:
        model_path = SMART_MERGE_DEFAULT_MODEL
        model_name = "Nano Banana"
    else:
        model_path = SMART_MERGE_SEEDREAM_MODEL
        model_name = "Seedream"
    
    try:
        # Для всех моделей (включая Nano Banana Pro edit) сначала показываем выбор формата
        # Качество будет запрошено в конце, после ввода промпта и изображений
        await state.update_data(
            {
                SMART_MERGE_STAGE_KEY: "await_size",
                SMART_MERGE_SOURCES_KEY: [],
                SMART_MERGE_MODEL_KEY: model_path,
            }
        )
        verify_data_after = await state.get_data()
        verify_stage_after = verify_data_after.get(SMART_MERGE_STAGE_KEY)
        logger.info(
            "Smart merge activated for user {} with model {}. Stage set to 'await_size', verified stage='{}'",
            message.from_user.id if message.from_user else "unknown",
            model_name,
            verify_stage_after,
        )
        format_hints = get_format_hints_text()
        format_message = (
            f"Вы выбрали {model_name} edit для изменения. Выберите формат изображения:\n\n"
            f"{format_hints}"
        )
        await message.answer(
            format_message,
            reply_markup=build_format_keyboard(),
        )
        return
        logger.info("handle_smart_merge_model_choice: message sent successfully for model '{}'", model_name)
    except Exception as exc:
        logger.error("handle_smart_merge_model_choice: error processing selection '{}': {}", selection, exc, exc_info=True)
        await _send_error_notification(message, "handle_smart_merge_model_choice")




async def handle_retoucher_start(message: types.Message, state: FSMContext) -> None:
    # Проверяем, не находимся ли мы в режиме "Написать"
    from app.bot.handlers.prompt_writer import PromptWriterStates
    current_state = await state.get_state()
    if current_state == PromptWriterStates.waiting_input:
        logger.info("handle_retoucher_start: user is in prompt writer mode, showing message")
        await message.answer(
            "⚠️ Вы находитесь в режиме **«✍️ Написать»**.\n\n"
            "Для перехода в другой режим:\n"
            "• Нажмите кнопку **«ℹ️ Info»** для сброса текущей сессии\n"
            "• Затем выберите нужный режим\n\n"
            "Или введите текст промпта для генерации.",
            parse_mode="Markdown",
        )
        return
    
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
                "Получено 4 из 4 изображений ✅\nТеперь опишите изменения, чтобы обработать их.",
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
    # Регистрируем обработчик кнопки "Написать" ПЕРВЫМ, чтобы он проверялся ПОСЛЕДНИМ (имел приоритет)
    from app.bot.handlers.prompt_writer import handle_prompt_writer_start
    from app.bot.keyboards.main import PROMPT_WRITER_BUTTON
    dp.message.register(handle_prompt_writer_start, _match_button(PROMPT_WRITER_BUTTON))
    
    # Регистрируем обработчики создания изображения ПОСЛЕДНИМИ, чтобы они проверялись ПЕРВЫМИ
    # Это гарантирует, что они имеют приоритет при обработке кнопок моделей после "Создать"
    # Порядок моделей (приоритет): 1. Nano Banana Pro, 2. Nano Banana, 3. Seedream, 4. Flux 2 Flex
    dp.message.register(handle_create, _match_button(CREATE_BUTTON))
    dp.message.register(handle_gpt_create, _match_button(IMAGE_GPT_CREATE_BUTTON))  # 1. Nano Banana Pro
    dp.message.register(handle_standard, _match_button(IMAGE_STANDARD_BUTTON))  # 2. Nano Banana
    dp.message.register(handle_seedream_create, _match_button(IMAGE_SEEDREAM_CREATE_BUTTON))  # 3. Seedream
    dp.message.register(handle_flux_flex_create, _match_button(IMAGE_FLUX2FLEX_CREATE_BUTTON))  # 4. Flux 2 Flex
    
    # Обработчики редактирования регистрируем ПЕРЕД созданием,
    # чтобы они проверялись ПОСЛЕ создания (в обратном порядке)
    dp.message.register(handle_edit_model_choice, _match_button(IMAGE_EDIT_CHRONO_BUTTON))
    dp.message.register(handle_edit_model_choice, _match_button(IMAGE_EDIT_SEDEDIT_BUTTON))
    
    # Обработчики Smart merge регистрируем ПЕРЕД созданием и редактированием,
    # чтобы они проверялись ПОСЛЕ них (в обратном порядке)
    # handle_smart_merge_model_choice теперь сначала проверяет состояние, поэтому не блокирует другие обработчики
    dp.message.register(handle_smart_merge_start, _match_button(IMAGE_SMART_MERGE_BUTTON))
    dp.message.register(handle_smart_merge_model_choice, _match_button(IMAGE_SMART_MERGE_PRO_BUTTON))  # 1. Nano Banana Pro
    dp.message.register(handle_smart_merge_model_choice, _match_button(IMAGE_SMART_MERGE_NANO_BUTTON))  # 2. Nano Banana
    dp.message.register(handle_smart_merge_model_choice, _match_button(IMAGE_SMART_MERGE_SEEDREAM_BUTTON))  # 3. Seedream
    # handle_edit_start removed from menu - button "Редактировать" is still available under generated images via callback
    dp.message.register(handle_retoucher_start, _match_button(IMAGE_RETOUCHER_BUTTON))
    dp.message.register(handle_upscale_button, _match_button(IMAGE_UPSCALE_BUTTON))
    # Обработчики выбора формата (новая единая система)
    dp.message.register(handle_format_choice, _match_button(IMAGE_FORMAT_SQUARE_1_1))
    dp.message.register(handle_format_choice, _match_button(IMAGE_FORMAT_VERTICAL_3_4))
    dp.message.register(handle_format_choice, _match_button(IMAGE_FORMAT_HORIZONTAL_4_3))
    dp.message.register(handle_format_choice, _match_button(IMAGE_FORMAT_VERTICAL_4_5))
    dp.message.register(handle_format_choice, _match_button(IMAGE_FORMAT_VERTICAL_9_16))
    dp.message.register(handle_format_choice, _match_button(IMAGE_FORMAT_HORIZONTAL_16_9))
    # Регистрируем обработчики выбора качества для Nano Banana Pro edit
    dp.message.register(handle_quality_choice, _match_button(QUALITY_FASTER_BUTTON))
    dp.message.register(handle_quality_choice, _match_button(QUALITY_BETTER_BUTTON))
    # Регистрируем обработчики выбора качества
    dp.message.register(handle_quality_choice, _match_button(QUALITY_FASTER_BUTTON))
    dp.message.register(handle_quality_choice, _match_button(QUALITY_BETTER_BUTTON))
    
    # Обработчики выбора размера (старая система для обратной совместимости)
    dp.message.register(handle_size_choice, _match_button(IMAGE_SIZE_VERTICAL_BUTTON))
    dp.message.register(handle_size_choice, _match_button(IMAGE_SIZE_SQUARE_BUTTON))
    dp.message.register(handle_size_choice, _match_button(IMAGE_SIZE_HORIZONTAL_BUTTON))
    dp.message.register(handle_edit_media, F.photo)
    dp.message.register(handle_edit_media, F.document)
    dp.callback_query.register(handle_edit_callback, lambda c: c.data and c.data.startswith("edit:"))
    dp.callback_query.register(handle_upscale_callback, lambda c: c.data and c.data.startswith("upscale:"))
    # Общий обработчик текста регистрируется последним, чтобы он проверялся первым
    # (в обратном порядке), но он пропускает кнопки редактирования через проверку выше
    # ИСКЛЮЧАЕМ кнопку баланса из фильтра, чтобы она обрабатывалась специальным обработчиком
    # ИСКЛЮЧАЕМ состояние PromptWriterStates.waiting_input - текст обрабатывается handle_prompt_writer_text
    from app.bot.handlers.prompt_writer import PromptWriterStates
    async def prompt_input_filter(msg: types.Message, state: FSMContext) -> bool:
        if not msg.text or msg.text.startswith("/") or msg.text == BALANCE_BUTTON:
            return False
        # Пропускаем, если пользователь в режиме "Написать" или в режиме помощи
        current_state = await state.get_state()
        from app.bot.handlers.help import HelpStates
        from app.bot.handlers.billing import PaymentStates
        if current_state == HelpStates.waiting_help_choice.state:
            return False
        if current_state == HelpStates.waiting_ai_assistant_input.state:
            return False
        if current_state == HelpStates.waiting_support_message.state:
            return False
        if current_state == "PromptWriterStates:waiting_input":
            return False
        if current_state == PaymentStates.BALANCE_MENU_SHOWN.state:
            return False
        return True
    
    dp.message.register(handle_prompt_input, prompt_input_filter)

