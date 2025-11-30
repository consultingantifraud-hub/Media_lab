from __future__ import annotations

# asyncio removed - using sync notifications now
import io
import os
import tempfile
import time
import threading
from pathlib import Path
from typing import Any, Dict

from aiogram.types import InlineKeyboardMarkup
from loguru import logger
from rq import get_current_job
from PIL import Image

from app.core.config import settings
from app.core.queues import get_job
import httpx

from app.providers.fal import (
    check_image_status,
    resolve_image_asset,
    run_smart_merge,
    submit_face_swap,
    submit_image,
    submit_image_edit,
    submit_image_upscale,
)

try:
    from app.providers.wavespeed.client import wavespeed_face_swap, wavespeed_text_to_image
    WAVESPEED_AVAILABLE = True
except ImportError:
    WAVESPEED_AVAILABLE = False
from app.providers.fal.client import download_file, run_model
from app.providers.fal.models_map import model_requires_mask
from app.providers.fal.images import _extract_image_url, ImageAsset
from app.utils.translation import translate_to_english
from app.core.formats import ImageFormat, convert_image_to_format

# Import models and initialize database to ensure tables exist
from app.db import models  # noqa: F401
from app.db.base import init_db

# Initialize database on module import
try:
    init_db()
    logger.debug("Database initialized in image_worker")
except Exception as e:
    logger.warning("Failed to initialize database in image_worker: {}", e)

UPSCALE_MAX_EDGE = 4096
UPSCALE_INPUT_MAX_EDGE = 4096

SMART_MERGE_DEFAULT_MODEL = "fal-ai/nano-banana/edit"
SMART_MERGE_DEFAULT_SIZE = "1024x1024"
SMART_MERGE_DEFAULT_ASPECT_RATIO = "1:1"
RETOUCHER_SUBMIT_MAX_ATTEMPTS = 3
RETOUCHER_SUBMIT_BACKOFF = 2.0
RETOUCHER_POLL_MAX_ATTEMPTS = 240
# Максимальный размер файла перед base64 кодированием (10 МБ лимит запроса, base64 увеличивает на ~33%)
RETOUCHER_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 МБ
RETOUCHER_MODELS = {
    "soft": settings.fal_retoucher_model,
    "enhance": "fal-ai/nano-banana/edit",  # Nano Banana Edit для качественной ретуши без добавления новых объектов
}

FACE_SWAP_DEFAULT_MODEL = settings.fal_face_swap_model
FACE_SWAP_MAX_ATTEMPTS = 3
FACE_SWAP_RETRY_BASE_DELAY = 2.0

UPSCALE_MAX_ATTEMPTS = 3
UPSCALE_RETRY_BASE_DELAY = 2.0
UPSCALE_POLL_MAX_ATTEMPTS = 36  # 3 minutes max (36 * 5 seconds) - matches RQ job timeout

def _extract_notify_options(options: Dict[str, Any]) -> dict[str, Any]:
    return {
        "chat_id": options.pop("notify_chat_id", None),
        "linked_chat_id": options.pop("notify_linked_chat_id", None),
        "message_thread_id": options.pop("notify_message_thread_id", None),
        "reply_to_message_id": options.pop("notify_reply_to_message_id", None),
        "prompt": options.pop("notify_prompt", None),
    }


def _persist_asset(asset, output_path: str, skip_download: bool = False) -> Path | None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if asset.content is not None:
        logger.debug("_persist_asset: writing {} bytes to {}", len(asset.content), path)
        path.write_bytes(asset.content)
        return path
    if asset.url and not skip_download:
        try:
            logger.debug("_persist_asset: downloading from {} to {}", asset.url, path)
            download_file(asset.url, path.as_posix())
            if path.exists():
                logger.debug("_persist_asset: successfully saved to {} ({} bytes)", path, path.stat().st_size)
                return path
            else:
                logger.warning("_persist_asset: download completed but file does not exist: {}", path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist remote asset {}: {}", asset.url, exc, exc_info=True)
    elif asset.url and skip_download:
        logger.debug("_persist_asset: skipping download (skip_download=True), will use URL directly")
    return None


def _schedule_result_download(job_id: str, url: str, target_path: Path) -> None:
    def _worker() -> None:
        try:
            # Download the JPEG file (API should return JPEG)
            jpeg_path = target_path.with_suffix(".jpg")
            download_file(url, jpeg_path.as_posix())

            if jpeg_path.exists():
                file_size = jpeg_path.stat().st_size
                logger.info("Background download completed for job {}: {} bytes (JPEG)", 
                           job_id, file_size)

                # Update job metadata
                redis_job = get_job(job_id)
                if redis_job:
                    meta = redis_job.meta or {}
                    meta["result_path"] = jpeg_path.as_posix()
                    redis_job.meta = meta
                    redis_job.save_meta()
            else:
                logger.warning("Downloaded file does not exist: {}", jpeg_path)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to cache result for job {}: {}", job_id, exc)

    threading.Thread(
        target=_worker,
        name=f"fal-download-{job_id}",
        daemon=True,
    ).start()


def _send_success_notification_sync(
    notify: dict[str, Any],
    job_id: str,
    image_url: str | None = None,
    image_bytes: bytes | None = None,
    filename: str | None = None,
    caption_title: str = "🖼️ Готово!",
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Send success notification synchronously (for use in workers)."""
    from app.core.telegram_sync import send_document_sync

    # Используем только короткий заголовок без промпта
    caption = caption_title

    # Convert reply_markup to dict if needed
    reply_markup_dict = None
    if reply_markup:
        reply_markup_dict = reply_markup.model_dump() if hasattr(reply_markup, 'model_dump') else None

    # Сохраняем message_id отправленного изображения для отправки полного промпта отдельным сообщением
    sent_message_id = None

    if image_bytes is not None:
        file_size_kb = len(image_bytes) / 1024
        logger.info("Sending image as bytes: size = {:.2f} KB ({} bytes), filename = {}", 
                   file_size_kb, len(image_bytes), filename or "image.png")
        sent_message_id = send_document_sync(
            chat_id=notify["chat_id"],
            document=image_bytes,
            filename=filename or "image.png",
            caption=caption,
            reply_to_message_id=notify.get("reply_to_message_id"),
            message_thread_id=notify.get("message_thread_id"),
            reply_markup=reply_markup_dict,
        )
    elif image_url:
        # ВАЖНО: Telegram сжимает изображения при отправке по URL
        # Для nano-banana-pro отправляем по URL напрямую, чтобы избежать долгого ожидания
        # Для других моделей скачиваем локально для лучшего качества
        from app.providers.fal.client import download_file
        import tempfile
        
        # Проверяем, не является ли это nano-banana-pro (может быть долгое скачивание)
        is_nano_banana_pro_url = "nano-banana-pro" in image_url.lower()
        
        if is_nano_banana_pro_url:
            # Для nano-banana-pro отправляем по URL напрямую - быстрее
            logger.info("Nano Banana Pro detected in URL, sending directly by URL to avoid long download: {}", image_url[:100])
            sent_message_id = send_document_sync(
                chat_id=notify["chat_id"],
                document=image_url,
                caption=caption,
                reply_to_message_id=notify.get("reply_to_message_id"),
                message_thread_id=notify.get("message_thread_id"),
                reply_markup=reply_markup_dict,
            )
        else:
            # Для других моделей скачиваем локально для лучшего качества
            logger.info("Image URL provided, downloading to preserve quality (Telegram compresses URLs): {}", image_url[:100])
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                    tmp_path = tmp_file.name

                # Скачиваем с таймаутом (максимум 30 секунд для обычных файлов)
                logger.info("Starting download to temp file: {}", tmp_path)
                download_file(image_url, tmp_path)

                if Path(tmp_path).exists() and Path(tmp_path).stat().st_size > 0:
                    file_size_kb = Path(tmp_path).stat().st_size / 1024
                    logger.info("Downloaded image from URL: size = {:.2f} KB ({} bytes)", file_size_kb, Path(tmp_path).stat().st_size)
                    with open(tmp_path, "rb") as f:
                        image_bytes = f.read()
                    # Удаляем временный файл
                    Path(tmp_path).unlink()
                    logger.info("Sending downloaded image as bytes: size = {:.2f} KB ({} bytes), chat_id={}", 
                               len(image_bytes) / 1024, len(image_bytes), notify["chat_id"])
                    try:
                        sent_message_id = send_document_sync(
                            chat_id=notify["chat_id"],
                            document=image_bytes,
                            filename=filename or "image.png",
                            caption=caption,
                            reply_to_message_id=notify.get("reply_to_message_id"),
                            message_thread_id=notify.get("message_thread_id"),
                            reply_markup=reply_markup_dict,
                        )
                        if sent_message_id:
                            logger.info("Successfully sent image to Telegram: message_id={}, chat_id={}", 
                                       sent_message_id, notify["chat_id"])
                        else:
                            logger.warning("Failed to send image to Telegram (send_document_sync returned None), chat_id={}", 
                                          notify["chat_id"])
                    except Exception as send_exc:
                        logger.error("Exception while sending image to Telegram: {}, chat_id={}", 
                               send_exc, notify["chat_id"], exc_info=True)
                        sent_message_id = None
                else:
                    logger.warning("Downloaded file does not exist or is empty: {}, falling back to URL send", tmp_path)
                    if Path(tmp_path).exists():
                        Path(tmp_path).unlink()
                    sent_message_id = send_document_sync(
                        chat_id=notify["chat_id"],
                        document=image_url,
                        caption=caption,
                        reply_to_message_id=notify.get("reply_to_message_id"),
                        message_thread_id=notify.get("message_thread_id"),
                        reply_markup=reply_markup_dict,
                    )
            except Exception as exc:
                logger.error("Failed to download image from URL, falling back to URL send: {}", exc, exc_info=True)
                # Очищаем временный файл если он существует
                if 'tmp_path' in locals() and Path(tmp_path).exists():
                    try:
                        Path(tmp_path).unlink()
                    except Exception:
                        pass
                # Fallback: отправляем по URL (Telegram может сжать)
                sent_message_id = send_document_sync(
                    chat_id=notify["chat_id"],
                    document=image_url,
                    caption=caption,
                    reply_to_message_id=notify.get("reply_to_message_id"),
                    message_thread_id=notify.get("message_thread_id"),
                    reply_markup=reply_markup_dict,
                )

    # Промпт больше не отправляется отдельным сообщением - только короткий заголовок в caption


def _send_failure_notification_sync(notify: dict[str, Any], job_id: str, error: str) -> None:
    """Send failure notification synchronously (for use in workers)."""
    from app.core.telegram_sync import send_message_sync

    text = f"❌ Не удалось обработать задачу {job_id}.\nОшибка: {error}"
    send_message_sync(
        chat_id=notify["chat_id"],
        text=text,
        reply_to_message_id=notify.get("reply_to_message_id"),
        message_thread_id=notify.get("message_thread_id"),
    )


def _is_network_error(exc: Exception) -> bool:
    return isinstance(exc, httpx.RequestError)


def _parse_operation_id(operation_id_raw: Any, job_id: str, context: str = "") -> int | None:
    """
    Конвертирует operation_id в int, так как через RQ он может передаваться как строка.
    
    Args:
        operation_id_raw: Сырое значение operation_id
        job_id: ID задачи для логирования
        context: Контекст для логирования (например, "image", "face_swap")
        
    Returns:
        int | None: Конвертированный operation_id или None
    """
    if operation_id_raw is None:
        return None
    
    try:
        operation_id = int(operation_id_raw)
        if operation_id:
            logger.debug("{} job {}: extracted operation_id={} (type: {})", 
                        context or "Job", job_id, operation_id, type(operation_id_raw).__name__)
        return operation_id
    except (ValueError, TypeError) as e:
        logger.warning("{} job {}: failed to convert operation_id '{}' to int: {}", 
                      context or "Job", job_id, operation_id_raw, e)
        return None


def _is_retryable_error(exc: Exception) -> bool:
    """Check if error is retryable (network errors or server errors 500-503)"""
    if isinstance(exc, httpx.RequestError):
        logger.debug("Error is retryable (RequestError): {}", type(exc).__name__)
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        is_retryable = status_code in (500, 502, 503)
        logger.info("HTTPStatusError with status {}: retryable={}", status_code, is_retryable)
        if is_retryable:
            return True
    logger.debug("Error is NOT retryable: {} ({})", type(exc).__name__, exc)
    return False


def process_face_swap_job(
    job_id: str,
    source_path: str,
    target_path: str,
    instruction: str | None,
    options: dict | None,
    output_path: str,
) -> str:
    # Import models to ensure they are registered with Base.metadata
    from app.db import models  # noqa: F401
    from app.services.billing import BillingService
    from app.db.base import SessionLocal

    provider_options: Dict[str, Any] = dict(options or {})
    operation_id_raw = provider_options.pop("operation_id", None)
    operation_id = _parse_operation_id(operation_id_raw, job_id, "Face swap")
    logger.info("Face swap job {}: operation_id_raw={} (type: {}), parsed operation_id={}", 
               job_id, operation_id_raw, type(operation_id_raw).__name__ if operation_id_raw is not None else "None", operation_id)
    provider_instruction = provider_options.pop("provider_instruction", None)
    model_name = provider_options.pop("model", FACE_SWAP_DEFAULT_MODEL) or FACE_SWAP_DEFAULT_MODEL
    logger.info("Face swap job {}: model_name from options: '{}' (default: '{}')", 
               job_id, model_name, FACE_SWAP_DEFAULT_MODEL)

    # Always translate instruction to English if it's not already translated
    # Use provider_instruction if available (already translated), otherwise translate instruction
    from app.utils.translation import translate_to_english
    if provider_instruction:
        # Already translated
        final_prompt = provider_instruction
    elif instruction:
        # Translate to English
        final_prompt = translate_to_english(instruction)
        logger.info("Face swap job {}: translated instruction '{}' -> '{}'", job_id, instruction[:100], final_prompt[:100] if final_prompt else "none")
    else:
        final_prompt = None

    notify_options = _extract_notify_options(provider_options)
    output_file = Path(output_path)
    source_file = Path(source_path)
    target_file = Path(target_path)

    job = get_current_job()

    try:
        if job:
            job.meta.update(
                {
                    "face_swap": True,
                    "prompt": instruction or "Замена лица",
                    "source_path": source_file.as_posix(),
                    "target_path": target_file.as_posix(),
                }
            )
            if provider_instruction and provider_instruction != (instruction or ""):
                job.meta["provider_instruction"] = provider_instruction
            job.save_meta()

        if not source_file.exists():
            error = f"Source face image not found at {source_path}"
            logger.error("Face swap job {} missing source image: {}", job_id, source_path)
            if job:
                job.meta["error"] = error
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, error)
            raise RuntimeError(error)

        if not target_file.exists():
            error = f"Target image not found at {target_path}"
            logger.error("Face swap job {} missing target image: {}", job_id, target_path)
            if job:
                job.meta["error"] = error
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, error)
            raise RuntimeError(error)

        logger.info(
            "Processing face swap job {} (source={}, target={}, instruction={})",
            job_id,
            source_path,
            target_path,
            instruction or "none",
        )

        # Check if this is advanced face swap model - use WaveSpeedAI
        # Advanced models use WaveSpeedAI API (not Fal.ai)
        # Загружаем актуальные настройки для проверки
        from app.core.config import reload_settings
        current_settings = reload_settings()
        # Логируем для диагностики
        logger.debug("Face swap job {}: wavespeed_api_key from env: {}, from settings: {}", 
                    job_id, os.getenv("WAVESPEED_API_KEY"), current_settings.wavespeed_api_key)
        # Проверяем, является ли модель WaveSpeedAI моделью (akool, wavespeed-ai, head-swap и т.д.)
        is_advanced_model = (
            "codeplugtech" in model_name.lower() or
            "cdingram" in model_name.lower() or
            "advanced-face-swap" in model_name.lower() or
            "advanced" in model_name.lower() or
            "akool" in model_name.lower() or  # akool/image-face-swap
            "wavespeed-ai" in model_name.lower() or  # wavespeed-ai/image-face-swap, image-head-swap
            "head-swap" in model_name.lower() or  # wavespeed-ai/image-head-swap
            model_name == current_settings.wavespeed_face_swap_model  # Проверяем по настройкам
        )
        logger.info("Face swap job {}: model_name='{}', is_advanced_model={}, wavespeed_model={}", 
                    job_id, model_name, is_advanced_model, current_settings.wavespeed_face_swap_model)

        if is_advanced_model:
            # Use WaveSpeedAI for advanced face swap
            if not WAVESPEED_AVAILABLE:
                error_msg = "WaveSpeedAI не доступен. Установите библиотеку httpx."
                logger.error("Face swap job {}: WaveSpeedAI not available", job_id)
                if job:
                    job.meta["error"] = error_msg
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, error_msg)
                raise RuntimeError(error_msg)

            # Проверяем API ключ из переменной окружения напрямую, если в настройках его нет
            wavespeed_api_key = current_settings.wavespeed_api_key or os.getenv("WAVESPEED_API_KEY")
            if not wavespeed_api_key:
                error_msg = (
                    "❌ Сервис WaveSpeed Face Swap временно недоступен.\n\n"
                    "Попробуйте использовать базовую модель «🔄 Face Swap» или обратитесь в техническую поддержку."
                )
                logger.error("Face swap job {}: WaveSpeedAI API key not configured (env: {}, settings: {})", 
                            job_id, os.getenv("WAVESPEED_API_KEY"), current_settings.wavespeed_api_key)
                if job:
                    job.meta["error"] = error_msg
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, error_msg)
                raise RuntimeError("WaveSpeedAI API key not configured")

            logger.info("Face swap job {} using WaveSpeedAI for advanced model", job_id)
            try:
                # Передаем модель явно из настроек для гарантии использования актуальной модели
                # wavespeed_face_swap сама загружает API ключ из переменных окружения
                result_url = wavespeed_face_swap(
                    source_path=target_file.as_posix(),  # target - куда вставляем лицо
                    face_path=source_file.as_posix(),   # source - откуда берем лицо
                    model=current_settings.wavespeed_face_swap_model,  # Явно передаем модель из настроек
                )
                logger.info("Face swap job {} successfully completed via WaveSpeedAI: {}", job_id, result_url[:50])
                # Скачиваем результат
                download_file(result_url, output_file.as_posix())

                # Определяем расширение файла на основе URL (WaveSpeedAI возвращает .jpeg или .png)
                # Если URL содержит .jpeg или .jpg, меняем расширение output_file
                if ".jpeg" in result_url.lower() or ".jpg" in result_url.lower():
                    # Меняем расширение на .jpg для JPEG файлов
                    output_file_jpeg = output_file.with_suffix(".jpg")
                    if output_file != output_file_jpeg:
                        # Переименовываем файл, если расширение отличается
                        if output_file.exists():
                            output_file.rename(output_file_jpeg)
                            output_file = output_file_jpeg
                            logger.debug("Face swap job {}: renamed output file to {}", job_id, output_file)

                # Отправляем результат в Telegram
                if notify_options.get("chat_id"):
                    try:
                        # Читаем файл для отправки
                        with open(output_file, "rb") as f:
                            image_bytes = f.read()
                        logger.info("Face swap job {}: sending notification with image bytes ({} bytes)", job_id, len(image_bytes))
                        # Определяем имя файла для отправки
                        filename = output_file.name
                        _send_success_notification_sync(
                            notify_options,
                            job_id,
                            image_bytes=image_bytes,
                            filename=filename,
                            caption_title="🤖 Замена лица готова!",
                        )
                    except Exception as notify_error:
                        logger.error("Failed to send Telegram notification for face swap job {}: {}", job_id, notify_error)

                # Confirm operation after successful completion (WaveSpeedAI path)
                if operation_id:
                    db = SessionLocal()
                    try:
                        success = BillingService.confirm_operation(db, operation_id)
                        if success:
                            logger.info("Confirmed operation {} for face swap job {} (WaveSpeedAI)", operation_id, job_id)
                        else:
                            logger.error("Failed to confirm operation {} for face swap job {} (WaveSpeedAI)", operation_id, job_id)
                    except Exception as e:
                        logger.error("Error confirming operation {} for face swap job {} (WaveSpeedAI): {}", operation_id, job_id, e, exc_info=True)
                    finally:
                        db.close()

                return output_file.as_posix()
            except Exception as wavespeed_exc:
                logger.error("Face swap job {} WaveSpeedAI failed: {}", job_id, wavespeed_exc)
                error_msg = f"Ошибка при обработке через WaveSpeedAI: {str(wavespeed_exc)}"
                if job:
                    job.meta["error"] = str(wavespeed_exc)
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, error_msg)
                raise RuntimeError(error_msg) from wavespeed_exc

        # For basic models, use Fal.ai as before
        # Remove any incorrect values that might be in provider_options
        clean_options = dict(provider_options)
        # Remove model from clean_options to avoid conflicts - we pass it explicitly
        if "model" in clean_options:
            clean_options.pop("model")
        # Remove invalid gender_0 and workflow_type values - they will be set correctly in submit_face_swap
        if "gender_0" in clean_options and clean_options["gender_0"] not in ("male", "female", "non-binary"):
            clean_options.pop("gender_0")
        if "workflow_type" in clean_options and clean_options["workflow_type"] not in ("user_hair", "target_hair"):
            clean_options.pop("workflow_type")

        # Use queue API for more reliable processing
        attempts = 0
        delay = FACE_SWAP_RETRY_BASE_DELAY
        last_error: Exception | None = None
        task_id: str | None = None

        logger.info("Face swap job {}: submitting to Fal.ai with model='{}' (is_advanced_model={})", 
                   job_id, model_name, False)
        while attempts < FACE_SWAP_MAX_ATTEMPTS:
            try:
                task_id = submit_face_swap(
                    source_path=source_file.as_posix(),
                    target_path=target_file.as_posix(),
                    prompt=final_prompt,
                    model=model_name,
                    **clean_options,
                )
                logger.info("Face swap job {} submitted to queue with task_id: {}", job_id, task_id)
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempts += 1
                logger.info("Face swap job {} submit attempt {} caught exception: {} ({})", 
                           job_id, attempts, type(exc).__name__, exc)
            is_retryable = _is_retryable_error(exc)
            logger.info("Face swap job {} submit attempt {}: is_retryable={}, attempts_left={}", 
                       job_id, attempts, is_retryable, FACE_SWAP_MAX_ATTEMPTS - attempts)
            if is_retryable and attempts < FACE_SWAP_MAX_ATTEMPTS:
                error_type = "network/server" if isinstance(exc, (httpx.RequestError, httpx.HTTPStatusError)) else "error"
                logger.warning(
                    "Face swap job {} submit attempt {} failed due to {} issue: {}. Retrying in {:.1f}s",
                    job_id,
                    attempts,
                    error_type,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay *= 2
                continue
            logger.error("Face swap job {} submit failed after {} attempts: {}", job_id, attempts, exc)

            # Determine error message based on error type
            if isinstance(exc, httpx.HTTPStatusError):
                status_code = exc.response.status_code
                if status_code == 500:
                    error_msg = (
                        "Сервер временно недоступен (ошибка 500). "
                        "Это проблема на стороне сервиса fal.ai. "
                        "Попробуйте повторить запрос через несколько минут."
                    )
                elif status_code == 422:
                    error_msg = (
                        "Некорректные параметры запроса (ошибка 422). "
                        "Проверьте, что загружены корректные изображения с лицами."
                    )
                elif status_code == 429:
                    error_msg = (
                        "Превышен лимит запросов (ошибка 429). "
                        "Подождите немного и попробуйте снова."
                    )
                else:
                    error_msg = f"Ошибка API (код {status_code}). Попробуйте позже."
            elif isinstance(exc, httpx.RequestError):
                error_msg = (
                    "Проблема с сетью при обращении к API. "
                    "Проверьте подключение к интернету и попробуйте снова."
                )
            else:
                error_msg = f"Не удалось отправить запрос на замену лица: {str(exc)}. Попробуйте позже."

            if job:
                job.meta["error"] = str(exc)
                job.meta["error_message"] = error_msg
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(
                    notify_options,
                    job_id,
                    error_msg,
                )
                raise

        if task_id is None:
            error = last_error or RuntimeError("Face swap task submission failed")
            if job:
                job.meta["error"] = str(error)
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, str(error))
            raise RuntimeError(str(error))

        # Poll for completion using queue API
        logger.info("Face swap job {} polling for task {} completion", job_id, task_id)
        status = check_image_status(task_id)
        max_poll_attempts = 60  # 5 minutes max (60 * 5 seconds)
        poll_attempts = 0

        while status["status"] not in ("succeeded", "failed"):
            if poll_attempts >= max_poll_attempts:
                error = "Face swap task timed out after polling"
                logger.error("Face swap job {} task {} timed out", job_id, task_id)
                if job:
                    job.meta["error"] = error
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, "Задача превысила время ожидания. Попробуйте позже.")
                raise RuntimeError(error)

            poll_attempts += 1
            time.sleep(5)  # Poll every 5 seconds
            status = check_image_status(task_id)
            logger.debug("Face swap job {} task {} status: {}", job_id, task_id, status["status"])

        if status["status"] == "failed":
            error = status.get("error", "Unknown error")
            logger.error("Face swap job {} task {} failed: {}", job_id, task_id, error)
            if job:
                job.meta["error"] = error
                job.save_meta()
            if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, f"Замена лица не удалась: {error}")
            raise RuntimeError(error)

        # According to fal.ai docs, when status is COMPLETED, the result may be in the status response itself
        # or available via response_url. Let's check if result is already in status first.
        # Import the helper function to extract image URL from response
        from app.providers.fal.images import _extract_image_url as extract_image_url
        status_image_url = extract_image_url(status)
        logger.debug("Face swap job {} extracted URL from status: {}", job_id, status_image_url[:100] if status_image_url else "None")
        asset = None

        if status_image_url:
            # Check if this is a queue API endpoint (response_url) or a real image URL
            if status_image_url.startswith("https://queue.fal.run") or status_image_url.startswith("http://queue.fal.run"):
                # This is a queue API endpoint, not a direct image URL - skip it
                logger.info("Face swap job {} found response_url in status (not a direct image URL), will use resolve_image_asset", job_id)
                status_image_url = None
                asset = None  # Ensure asset is None so we use resolve_image_asset
            elif status_image_url.startswith("data:"):
                logger.info("Face swap job {} result found in status response (data URL)", job_id)
                # Result is already in status as data URL, extract it directly
                from app.providers.fal.images import ImageAsset
                import base64
                header, _, data_part = status_image_url.partition(",")
                content = base64.b64decode(data_part)
                asset = ImageAsset(url=None, content=content, filename="face-swap.png")
            elif status_image_url.startswith("http"):
                # This looks like a direct image URL (CDN, etc.)
                logger.info("Face swap job {} result found in status response (direct URL): {}", job_id, status_image_url[:100])
                from app.providers.fal.images import ImageAsset
                asset = ImageAsset(url=status_image_url, content=None, filename=None)
            else:
                logger.warning("Face swap job {} unexpected image URL format in status: {}", job_id, status_image_url[:100])

        # If result not in status, try to get it via response_url with retries
        if asset is None:
            result_url = status.get("result_url")
            if not result_url:
                error = "Face swap task completed but no result URL provided and no result in status"
                logger.error("Face swap job {} task {} completed without result URL or result in status", job_id, task_id)
                if job:
                    job.meta["error"] = error
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, "Задача завершена, но результат недоступен.")
                raise RuntimeError(error)

        # Small delay after completion to allow API to prepare the result
        # Sometimes the API returns 500 immediately after COMPLETED status
        logger.debug("Face swap job {} task {} completed, waiting 1s before fetching result", job_id, task_id)
        time.sleep(1.0)

        # Try to get result with retries and increasing delays
        # Use resolve_image_asset which properly handles authorization and retries
        max_result_attempts = 5
        result_delay = 1.0
        last_result_error: Exception | None = None

        for result_attempt in range(max_result_attempts):
            try:
                logger.debug("Face swap job {} attempt {} to get result from {}", job_id, result_attempt + 1, result_url)
                # Use resolve_image_asset which properly handles queue API authorization
                asset = resolve_image_asset(result_url)
                logger.info("Face swap job {} successfully got result on attempt {}: asset.url={}, asset.content={}", 
                           job_id, result_attempt + 1, asset.url[:100] if asset.url else "None", asset.content is not None)
                # Check if asset.url is a queue API endpoint - if so, we need to get the actual image URL
                if asset.url and (asset.url.startswith("https://queue.fal.run") or asset.url.startswith("http://queue.fal.run")):
                    logger.warning("Face swap job {} asset.url is a queue API endpoint, this should not happen. asset.url={}", 
                                  job_id, asset.url)
                    # Try to get the actual result from queue_result
                    from app.providers.fal.client import queue_result
                    from app.providers.fal.images import _extract_image_url, ImageAsset, _parse_result_url
                    parsed = _parse_result_url(result_url)
                    if parsed:
                        model_path, request_id = parsed
                        logger.info("Face swap job {} trying queue_result directly for model={}, request_id={}", 
                                   job_id, model_path, request_id)
                        response_data = queue_result(model_path, request_id)
                        logger.info("Face swap job {} queue_result response keys: {}", job_id, list(response_data.keys()) if isinstance(response_data, dict) else "not a dict")
                        actual_image_url = _extract_image_url(response_data)
                        if actual_image_url and not (actual_image_url.startswith("https://queue.fal.run") or actual_image_url.startswith("http://queue.fal.run")):
                            logger.info("Face swap job {} extracted actual image URL: {}", job_id, actual_image_url[:100])
                            asset = ImageAsset(url=actual_image_url, content=None, filename=None)
                        else:
                            logger.error("Face swap job {} failed to extract valid image URL from queue_result response", job_id)
                break
            except httpx.HTTPStatusError as exc:
                last_result_error = exc
                status_code = exc.response.status_code
                if status_code in (500, 502, 503, 401) and result_attempt < max_result_attempts - 1:
                    logger.warning(
                        "Face swap job {} result attempt {} failed with {}: {}. Retrying in {:.1f}s",
                        job_id,
                        result_attempt + 1,
                        status_code,
                        exc.response.text[:100] if hasattr(exc.response, 'text') else str(exc),
                        result_delay,
                    )
                    time.sleep(result_delay)
                    result_delay *= 1.5
                    continue
                else:
                    logger.error("Face swap job {} result attempt {} failed with {}: {}", job_id, result_attempt + 1, status_code, exc)
                    raise
            except Exception as exc:  # noqa: BLE001
                last_result_error = exc
                logger.error("Face swap job {} result attempt {} failed: {}", job_id, result_attempt + 1, exc)
                if result_attempt >= max_result_attempts - 1:
                    raise

        if asset is None:
            error = last_result_error or RuntimeError("Failed to get face swap result")
            logger.error("Face swap job {} failed to get result after {} attempts: {}", job_id, max_result_attempts, error)

            # Create user-friendly error message
            error_str = str(error)
            if "timeout" in error_str.lower() or "timed out" in error_str.lower():
                user_error_msg = (
                    "• Проблема на стороне сервиса\n\n"
                    "Попробуйте:\n"
                    "• Повторить запрос через несколько минут\n"
                    "• Использовать базовую модель Face Swap (fal-ai/face-swap)"
                )
            elif "500" in error_str:
                user_error_msg = (
                    "Ошибка обработки на стороне API Fal.ai (500 Internal Server Error).\n\n"
                    "Попробуйте повторить запрос через несколько минут."
                )
            else:
                user_error_msg = f"Не удалось получить результат: {error_str}"

            if job:
                job.meta["error"] = error_str
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, user_error_msg)
            raise RuntimeError(error_str)

        # Try to persist asset locally, but don't block on it
        # If asset has content, save it immediately
        saved_path = None
        image_bytes = asset.content
        filename = asset.filename

        if image_bytes:
            # We have content, save it immediately
            try:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_bytes(image_bytes)
                saved_path = output_file
                filename = filename or output_file.name
            except Exception as exc:  # noqa: BLE001
                logger.warning("Face swap job {}: failed to save inline bytes: {}", job_id, exc)
        elif asset.url:
            # We only have URL - schedule background download for caching
            # but don't try to download synchronously as it may timeout
            # Telegram can download the image directly from the URL
            _schedule_result_download(job_id, asset.url, output_file)
            logger.info("Face swap job {}: will send image by URL (background download scheduled): {}", job_id, asset.url[:100])
            # Continue without local file - we'll send by URL

        if job:
            job.meta["image_url"] = asset.url
            if image_bytes:
                job.meta["image_inline"] = True
                if filename:
                    job.meta["image_filename"] = filename
            if saved_path:
                job.meta["result_path"] = saved_path.as_posix()
            else:
                job.meta["result_path"] = None
            job.save_meta()

        caption_path = saved_path.as_posix() if saved_path else asset.url or ""
        logger.success("Face swap job {} completed: {}", job_id, caption_path)

        if notify_options.get("chat_id"):
            logger.info("Face swap job {}: preparing notification (image_bytes={}, saved_path={}, asset.url={})", 
                        job_id, image_bytes is not None, saved_path, asset.url[:100] if asset.url else None)
            try:
                if image_bytes is None and saved_path and saved_path.exists():
                    image_bytes = saved_path.read_bytes()
                    filename = filename or saved_path.name
                    logger.info("Face swap job {}: loaded image bytes from saved file ({} bytes)", job_id, len(image_bytes))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Face swap job {}: failed to prepare bytes for notification: {}", job_id, exc)

            if image_bytes is not None:
                logger.info("Face swap job {}: sending notification with image bytes ({} bytes)", job_id, len(image_bytes))
                try:
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_bytes=image_bytes,
                        filename=filename or "face-swap.png",
                        caption_title="🤖 Замена лица готова!",
                        reply_markup=None,
                    )
                    logger.info("Face swap job {}: successfully sent notification with image bytes", job_id)
                except Exception as notify_error:  # noqa: BLE001
                    logger.error("Failed to send Telegram notification for face swap job {}: {}", job_id, notify_error)
            elif asset.url:
                # Fallback to sending the URL if bytes are unavailable
                logger.info("Face swap job {}: sending notification with image URL: {}", job_id, asset.url[:100])
                try:
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_url=asset.url,
                        caption_title="🤖 Замена лица готова!",
                        reply_markup=None,
                    )
                    logger.info("Face swap job {}: successfully sent notification with image URL", job_id)
                except Exception as notify_error:  # noqa: BLE001
                    logger.error("Failed to send fallback notification for face swap job {}: {}", job_id, notify_error)
            else:
                logger.error("Face swap job {}: cannot send notification - no image_bytes and no asset.url", job_id)

        # Confirm operation after successful completion
        if operation_id:
            db = SessionLocal()
            try:
                success = BillingService.confirm_operation(db, operation_id)
                if success:
                    logger.info("Confirmed operation {} for face swap job {}", operation_id, job_id)
                else:
                    logger.error("Failed to confirm operation {} for face swap job {}", operation_id, job_id)
            except Exception as e:
                logger.error("Error confirming operation {} for face swap job {}: {}", operation_id, job_id, e, exc_info=True)
            finally:
                db.close()

        return caption_path
    except Exception as e:
        # Mark operation as failed on any error
        if operation_id:
            db = SessionLocal()
            try:
                BillingService.fail_operation(db, operation_id)
                logger.info("Marked operation {} as failed for face swap job {} due to error", operation_id, job_id)
            except Exception as fail_error:
                logger.error("Error failing operation {} for face swap job {}: {}", operation_id, job_id, fail_error, exc_info=True)
            finally:
                db.close()
        raise


def process_image_job(job_id: str, prompt: str, options: dict | None, output_path: str) -> str:
    # Import models to ensure they are registered with Base.metadata
    from app.db import models  # noqa: F401
    from app.services.billing import BillingService
    from app.db.base import SessionLocal

    provider_options: Dict[str, Any] = dict(options or {})
    logger.info("Image job {}: received options keys: {}", job_id, list(provider_options.keys()))
    operation_id_raw = provider_options.pop("operation_id", None)
    logger.info("Image job {}: operation_id_raw from options: {} (type: {})", 
               job_id, operation_id_raw, type(operation_id_raw).__name__ if operation_id_raw is not None else "None")
    operation_id = _parse_operation_id(operation_id_raw, job_id, "Image")
    provider_prompt = provider_options.pop("provider_prompt", prompt)
    output_file = Path(output_path)
    job = get_current_job()
    if job:
        job.meta.update({"prompt": prompt})
        if prompt != provider_prompt:
            job.meta["provider_prompt"] = provider_prompt
        job.save_meta()

    notify_options = _extract_notify_options(provider_options)

    try:
        logger.info("Processing image job {} with prompt '{}'", job_id, prompt[:100])
        logger.info("Image job {}: provider_prompt='{}' (same as prompt: {})", 
                    job_id, provider_prompt[:100] if provider_prompt else "None", provider_prompt == prompt)

        # Проверяем, является ли модель Nano Banana Pro (gpt-create - внутренний ключ для UI)
        selected_model = provider_options.get("selected_model", "")
        is_gpt_create = selected_model == "gpt-create"

        if is_gpt_create:
            # Используем Nano Banana Pro через Fal.ai для лучшего качества кириллицы
            logger.info("Image job {} using Nano Banana Pro (Fal.ai) for text-to-image generation", job_id)

            # Nano Banana Pro поддерживает кириллицу напрямую, не нужно переводить
            # Используем оригинальный промпт
            provider_prompt = prompt

            # Устанавливаем модель Nano Banana Pro (уже должна быть установлена, но на всякий случай)
            provider_options["model"] = "fal-ai/nano-banana-pro"
            provider_options["selected_model"] = None  # Убираем gpt-create, чтобы использовать обычную логику

            logger.info("Image job {}: Using Nano Banana Pro with original Russian prompt: '{}'", job_id, prompt[:50])

        # Проверяем, является ли модель Nano-banana (может принимать русский текст)
        model_name = provider_options.get("model", "")
        is_nano_banana = model_name == "fal-ai/nano-banana" or model_name == "fal-ai/nano-banana-pro" or "nano-banana" in model_name.lower()

        if provider_prompt != prompt:
            logger.info("Using translated prompt for job {}: '{}'", job_id, provider_prompt[:100])
        elif is_nano_banana:
            # Для Nano-banana не переводим промпт, используем оригинальный русский
            logger.info("Image job {}: Nano-banana model detected, using original Russian prompt without translation", job_id)
            provider_prompt = prompt  # Используем оригинальный промпт без перевода
        else:
            # Если перевод не сработал, попробуем перевести здесь еще раз
            # Проверяем, содержит ли промпт кириллицу (признак русского текста)
            has_cyrillic = any('\u0400' <= char <= '\u04FF' for char in prompt)
            logger.info("Image job {}: checking for Cyrillic in prompt: {}", job_id, has_cyrillic)
            if has_cyrillic:
                logger.warning("Image job {}: provider_prompt is same as original (likely Russian), attempting translation in worker", job_id)
                try:
                    translated = translate_to_english(prompt)
                    if translated != prompt and translated:
                        logger.info("Image job {}: successfully translated in worker: '{}' -> '{}'", 
                                   job_id, prompt[:50], translated[:50])
                        provider_prompt = translated
                    else:
                        logger.warning("Image job {}: translation in worker failed or returned same text, using original", job_id)
                except Exception as exc:
                    logger.error("Image job {}: translation in worker failed: {}", job_id, exc)

        # Используем обычную логику через очередь для всех моделей
        model_name = provider_options.get("model", "")
        
        # Применяем настройки качества для nano-banana (обычный и pro)
        is_nano_banana_regular = model_name == "fal-ai/nano-banana" or ("nano-banana" in model_name.lower() and "pro" not in model_name.lower())
        is_nano_banana_pro = "nano-banana-pro" in model_name.lower()
        
        if is_nano_banana_regular:
            # Увеличиваем параметры качества для максимального результата (обычный nano-banana)
            current_steps = provider_options.get("num_inference_steps", 60)
            current_guidance = provider_options.get("guidance_scale", 9.0)
            # Увеличиваем, если текущие значения меньше максимальных
            if current_steps < 60:
                provider_options["num_inference_steps"] = 60
            if current_guidance < 9.0:
                provider_options["guidance_scale"] = 9.0
            logger.info("Image job {}: Applied quality settings for nano-banana: num_inference_steps={}, guidance_scale={}", 
                       job_id, provider_options.get("num_inference_steps"), provider_options.get("guidance_scale"))
        elif is_nano_banana_pro:
            # Применяем максимальные настройки качества для nano-banana-pro (максимальная прорисовка)
            provider_options["num_inference_steps"] = 90
            provider_options["guidance_scale"] = 10.0
            logger.info("Image job {}: Applied enhanced quality settings for nano-banana-pro: num_inference_steps={}, guidance_scale={}", 
                       job_id, provider_options.get("num_inference_steps"), provider_options.get("guidance_scale"))
        elif "seedream" in model_name.lower():
            # Применяем максимальные настройки качества для Seedream (увеличенная прорисовка и детализация)
            # Принудительно устанавливаем максимальные значения для максимального качества
            provider_options["num_inference_steps"] = 120
            provider_options["guidance_scale"] = 12.0
            # Добавляем enhance_prompt_mode для максимального качества (standard вместо fast)
            provider_options["enhance_prompt_mode"] = "standard"
            logger.info("Image job {}: Applied enhanced quality settings for Seedream: num_inference_steps={}, guidance_scale={}, enhance_prompt_mode={}", 
                       job_id, provider_options.get("num_inference_steps"), provider_options.get("guidance_scale"), provider_options.get("enhance_prompt_mode"))
        
        logger.info("Image job {}: Submitting image job with model: {}", job_id, model_name)
        logger.info("Image job {}: provider_options keys: {}, width: {}, height: {}, num_inference_steps: {}, guidance_scale: {}", 
                   job_id, list(provider_options.keys()), provider_options.get("width"), provider_options.get("height"), 
                   provider_options.get("num_inference_steps"), provider_options.get("guidance_scale"))
        task_id = submit_image(prompt=provider_prompt, **provider_options)
        asset = None

        # Polling для получения результата (асинхронная процедура с интервалом 4 сек)
        if asset is None:
            poll_attempts = 0
            max_attempts = 45  # 3 минуты при интервале 4 сек (45 * 4 = 180 секунд)
            poll_interval = 4.0  # Интервал 4 секунды для проверки статуса
            status: dict[str, Any]
            while True:
                status = check_image_status(task_id)
                current_status = status.get("status")
                if current_status == "succeeded":
                    break
                if current_status == "failed":
                    error = status.get("error", "Unknown error")
                    logger.error("Image job {} failed: {}", job_id, error)
                    if job:
                        job.meta["error"] = error
                        job.save_meta()
                    if notify_options.get("chat_id"):
                        _send_failure_notification_sync(notify_options, job_id, str(error))
                    raise RuntimeError(error)
                poll_attempts += 1
                if poll_attempts >= max_attempts:
                    error = f"fal request did not complete within {int(max_attempts * poll_interval)} seconds"
                    logger.error("Image job {} timed out waiting for fal result", job_id)
                    if job:
                        job.meta["error"] = error
                        job.save_meta()
                    if notify_options.get("chat_id"):
                        _send_failure_notification_sync(notify_options, job_id, error)
                    raise RuntimeError(error)
                time.sleep(poll_interval)

        # Получаем результат после завершения
        if asset is None:
            # Сначала проверяем, есть ли результат прямо в статусе (как для Seedream в редактировании)
            from app.providers.fal.images import _extract_image_url as extract_image_url
            status_image_url = extract_image_url(status)

            if status_image_url:
                # Проверяем формат URL
                if status_image_url.startswith("data:"):
                    logger.info("Image job {} result found in status response (data URL)", job_id)
                    from app.providers.fal.images import ImageAsset
                    import base64
                    header, _, data_part = status_image_url.partition(",")
                    content = base64.b64decode(data_part)
                    asset = ImageAsset(url=None, content=content, filename="image.png")
                elif status_image_url.startswith("http") and not (status_image_url.startswith("https://queue.fal.run") or status_image_url.startswith("http://queue.fal.run")):
                    logger.info("Image job {} result found in status response (direct URL): {}", job_id, status_image_url[:100])
                    from app.providers.fal.images import ImageAsset
                    asset = ImageAsset(url=status_image_url, content=None, filename=None)
                elif status_image_url.startswith("https://queue.fal.run") or status_image_url.startswith("http://queue.fal.run"):
                    # Это endpoint для получения результата, не прямой URL изображения
                    # Продолжаем с обычной логикой получения результата
                    logger.debug("Image job {} status contains queue endpoint, will resolve through resolve_image_asset", job_id)
                    status_image_url = None

            # Если результат не в статусе, получаем через response_url
            if asset is None:
                result_url = status.get("result_url")
                if not result_url:
                    error = "Задача завершена, но результат недоступен"
                    logger.error("Image job {} task {} completed without result URL or result in status", job_id, task_id)
                    if job:
                        job.meta["error"] = error
                        job.save_meta()
                    if notify_options.get("chat_id"):
                        _send_failure_notification_sync(notify_options, job_id, error)
                    raise RuntimeError(error)

                # Для nano-banana-pro используем URL напрямую, без resolve_image_asset
                # чтобы избежать долгого скачивания файла
                is_nano_banana_pro = model_name == "fal-ai/nano-banana-pro" or "nano-banana-pro" in model_name.lower()
                
                if is_nano_banana_pro:
                    # Проверяем, что result_url - это прямой URL изображения, а не API endpoint
                    # API endpoints обычно содержат "/requests/" или "/response" или "/result"
                    is_api_endpoint = (
                        "/requests/" in result_url or 
                        "/response" in result_url or 
                        "/result" in result_url or
                        "queue.fal.run" in result_url
                    )
                    
                    if is_api_endpoint:
                        # Если это API endpoint, нужно получить прямой URL через resolve_image_asset
                        logger.warning("Image job {}: Nano Banana Pro result_url is API endpoint, will use resolve_image_asset to get direct URL: {}", 
                                     job_id, result_url[:100])
                        # Небольшая задержка после завершения
                        time.sleep(0.5)
                        # Получаем прямой URL через resolve_image_asset (но не скачиваем файл)
                        try:
                            asset = resolve_image_asset(result_url)
                            logger.info("Image job {}: Got direct image URL from resolve_image_asset: {}", 
                                       job_id, asset.url[:100] if asset.url else "None")
                        except Exception as exc:
                            logger.error("Image job {}: Failed to get direct URL from resolve_image_asset: {}", job_id, exc)
                            raise
                    else:
                        # Это прямой URL изображения, можно использовать напрямую
                        logger.info("Image job {}: Nano Banana Pro detected, using result_url directly (direct image URL): {}", 
                                   job_id, result_url[:100])
                        from app.providers.fal.images import ImageAsset
                        # Используем result_url как прямой URL изображения (Telegram сам скачает)
                        asset = ImageAsset(url=result_url, content=None, filename=None)
                else:
                    # Небольшая задержка после завершения, чтобы API успел подготовить результат
                    time.sleep(0.5)

                    # Получаем результат с повторными попытками (как для Nano-banana)
                    max_result_attempts = 3
                    result_delay = 0.5
                    last_result_error: Exception | None = None

                    for result_attempt in range(max_result_attempts):
                        try:
                            asset = resolve_image_asset(result_url)
                            logger.info("Image job {} successfully got result on attempt {}: asset.url={}, asset.content={}", 
                                       job_id, result_attempt + 1, asset.url[:100] if asset.url else "None", asset.content is not None)
                            break
                        except httpx.HTTPStatusError as exc:
                            last_result_error = exc
                            status_code = exc.response.status_code
                            if status_code in (500, 502, 503, 401) and result_attempt < max_result_attempts - 1:
                                logger.warning(
                                    "Image job {} result attempt {} failed with {}: {}. Retrying in {:.1f}s",
                                    job_id,
                                    result_attempt + 1,
                                    status_code,
                                    exc.response.text[:100] if hasattr(exc.response, 'text') else str(exc),
                                    result_delay,
                                )
                                time.sleep(result_delay)
                                result_delay *= 1.5
                                continue
                            else:
                                logger.error("Image job {} result attempt {} failed with {}: {}", job_id, result_attempt + 1, status_code, exc)
                                raise
                        except Exception as exc:  # noqa: BLE001
                            last_result_error = exc
                            logger.error("Image job {} result attempt {} failed: {}", job_id, result_attempt + 1, exc)
                            if result_attempt >= max_result_attempts - 1:
                                raise

                    if asset is None:
                        error = last_result_error or RuntimeError("Failed to get image result")
                        logger.error("Image job {} failed to get result after {} attempts: {}", job_id, max_result_attempts, error)
                        if job:
                            job.meta["error"] = str(error)
                            job.save_meta()
                        if notify_options.get("chat_id"):
                            _send_failure_notification_sync(notify_options, job_id, f"Не удалось получить результат: {error}")
                        raise RuntimeError(str(error))

        image_url = asset.url
        image_bytes = asset.content
        filename = asset.filename
        saved_path = None

        # Для nano-banana-pro всегда отправляем по URL, без скачивания, чтобы ускорить отправку
        # ИСКЛЮЧЕНИЕ: если указан selected_format, нужно скачать и преобразовать изображение
        is_nano_banana_pro = model_name == "fal-ai/nano-banana-pro" or "nano-banana-pro" in model_name.lower()
        is_nano_banana = model_name == "fal-ai/nano-banana" or ("nano-banana" in model_name.lower() and "pro" not in model_name.lower())
        selected_format = provider_options.get("selected_format")
        needs_format_conversion = selected_format is not None
        
        # Для nano-banana (обычный) всегда нужно преобразование формата, так как модель
        # может вернуть изображение с неточным соотношением сторон (например, 864x1184 вместо 3:4)
        if is_nano_banana and selected_format:
            needs_format_conversion = True
        
        if is_nano_banana_pro and not needs_format_conversion:
            # Для nano-banana-pro без преобразования формата пропускаем скачивание и сохраняем только URL
            logger.info("Image job {}: Nano Banana Pro detected, skipping download, will send by URL directly", job_id)
            saved_path = None
            # Планируем фоновое скачивание для кеширования, но не блокируем отправку
            if image_url:
                _schedule_result_download(job_id, image_url, output_file)
        elif is_nano_banana_pro and needs_format_conversion:
            # Для nano-banana-pro с преобразованием формата нужно скачать изображение
            logger.info("Image job {}: Nano Banana Pro with format conversion, downloading image first", job_id)
            if image_bytes is not None:
                # Изображение уже в памяти
                saved_path = _persist_asset(asset, output_file.as_posix())
            elif image_url:
                # Скачиваем изображение
                saved_path = _persist_asset(asset, output_file.as_posix())
            else:
                saved_path = None
        elif is_nano_banana:
            # Для nano-banana используем изображение как есть, без обрезки/ресайза
            # Модель получает aspect_ratio и возвращает изображение нужного размера
            logger.info("Image job {}: Nano Banana detected, using image as-is from model (no post-processing)", job_id)
            if image_bytes is not None:
                saved_path = _persist_asset(asset, output_file.as_posix())
            elif image_url:
                saved_path = _persist_asset(asset, output_file.as_posix())
            else:
                saved_path = None
        else:
            # Логируем размер файла для диагностики
            if image_bytes is not None:
                file_size_kb = len(image_bytes) / 1024
                logger.info("Image job {}: image_bytes size = {:.2f} KB ({} bytes)", job_id, file_size_kb, len(image_bytes))
                saved_path = _persist_asset(asset, output_file.as_posix())
                if saved_path and saved_path.exists():
                    saved_size_kb = saved_path.stat().st_size / 1024
                    logger.info("Image job {}: saved file size = {:.2f} KB ({} bytes)", job_id, saved_size_kb, saved_path.stat().st_size)
                elif image_url:
                    logger.info("Image job {}: image_url = {} (no inline content)", job_id, image_url[:100] if image_url else "None")

        if job:
            if image_url:
                job.meta["image_url"] = image_url
            if image_bytes:
                job.meta["image_inline"] = True
                if filename:
                    job.meta["image_filename"] = filename
            if saved_path:
                job.meta["result_path"] = saved_path.as_posix()
            elif image_url:
                job.meta["result_path"] = None
            job.save_meta()

        # Планируем фоновое скачивание только если файл еще не сохранен и это не nano-banana-pro
        # (для nano-banana-pro скачивание уже запланировано выше)
        if saved_path is None and image_url and not is_nano_banana_pro:
            _schedule_result_download(job_id, image_url, output_file)

        logger.success("Image job {} completed: {}", job_id, image_url or filename or "binary")
        if notify_options.get("chat_id"):
            try:
                reply_markup = None
                # Проверяем saved_path из job.meta на случай, если фоновое скачивание уже завершилось
                if saved_path is None and job and job.meta.get("result_path"):
                    saved_path = Path(job.meta["result_path"])
                    if not saved_path.exists():
                        saved_path = None
                
                if image_bytes is not None:
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_bytes=image_bytes,
                        filename=filename,
                        reply_markup=reply_markup,
                    )
                elif saved_path and saved_path.exists():
                    # Используем уже скачанный файл вместо повторного скачивания
                    logger.info("Using already downloaded file for notification: {} (size: {:.2f} KB)", 
                               saved_path, saved_path.stat().st_size / 1024)
                    with open(saved_path, "rb") as f:
                        image_bytes = f.read()
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_bytes=image_bytes,
                        filename=filename or saved_path.name,
                        reply_markup=reply_markup,
                    )
                else:
                    # Для nano-banana-pro без преобразования формата отправляем по URL напрямую для максимальной скорости
                    # Фоновое скачивание уже запланировано и завершится позже
                    # Для nano-banana-pro с преобразованием формата уже должно быть saved_path
                    if is_nano_banana_pro and not needs_format_conversion:
                        logger.info("Nano Banana Pro: sending by URL directly (background download in progress): {}", image_url[:100] if image_url else "None")
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_url=image_url,
                        reply_markup=reply_markup,
                    )
            except Exception as notify_error:  # noqa: BLE001
                logger.error("Failed to send Telegram notification for job {}: {}", job_id, notify_error, exc_info=True)

        # Confirm operation after successful completion
        if operation_id:
            db = SessionLocal()
            try:
                success = BillingService.confirm_operation(db, operation_id)
                if success:
                    logger.info("Confirmed operation {} for job {}", operation_id, job_id)
                else:
                    logger.error("Failed to confirm operation {} for job {}", operation_id, job_id)
            except Exception as e:
                logger.error("Error confirming operation {} for job {}: {}", operation_id, job_id, e, exc_info=True)
            finally:
                db.close()

        return image_url or ""
    except Exception as e:
        # Mark operation as failed on any error
        if operation_id:
            db = SessionLocal()
            try:
                BillingService.fail_operation(db, operation_id)
                logger.info("Marked operation {} as failed for job {} due to error", operation_id, job_id)
            except Exception as fail_error:
                logger.error("Error failing operation {} for job {}: {}", operation_id, job_id, fail_error, exc_info=True)
            finally:
                db.close()
        raise


def process_image_edit_job(
    job_id: str,
    prompt: str,
    image_path: str,
    mask_path: str | None,
    options: dict | None,
    output_path: str,
) -> str:
    # Import models to ensure they are registered with Base.metadata
    from app.db import models  # noqa: F401
    from app.services.billing import BillingService
    from app.db.base import SessionLocal

    provider_options: Dict[str, Any] = dict(options or {})
    operation_id_raw = provider_options.pop("operation_id", None)
    operation_id = _parse_operation_id(operation_id_raw, job_id, "Image edit")
    logger.info("Image edit job {}: operation_id_raw={} (type: {}), parsed operation_id={}", 
               job_id, operation_id_raw, type(operation_id_raw).__name__ if operation_id_raw is not None else "None", operation_id)
    provider_prompt = provider_options.pop("provider_prompt", prompt)
    model_name = provider_options.setdefault("model", settings.fal_edit_model)
    requires_mask = model_requires_mask(model_name)

    notify_options = _extract_notify_options(provider_options)
    output_file = Path(output_path)
    source_file = Path(image_path)
    mask_file = Path(mask_path) if mask_path else None

    job = get_current_job()

    try:
        if job:
            job.meta.update(
                {
                    "prompt": prompt,
                    "edit": True,
                    "source_path": source_file.as_posix(),
                }
            )
            if mask_file:
                job.meta["mask_path"] = mask_file.as_posix()
            if prompt != provider_prompt:
                job.meta["provider_prompt"] = provider_prompt
            job.save_meta()

        logger.info(
            "Processing image edit job {} with prompt {} (source={}, mask={})",
            job_id,
            prompt,
            image_path,
            mask_path,
        )

        if not source_file.exists():
            error = f"Source image for job {job_id} not found at {image_path}"
            logger.error(error)
            if job:
                job.meta["error"] = error
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, error)
            raise RuntimeError(error)

        if requires_mask:
            if mask_file is None or not mask_file.exists():
                error = "Для этой модели нужна маска, выделяющая область изменения."
                logger.error("Edit job {} missing mask file", job_id)
                if job:
                    job.meta["error"] = error
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, error)
                raise RuntimeError(error)
        else:
            if mask_file is None or not mask_file.exists():
                mask_file = None

        # Всегда используем асинхронный режим с polling для всех моделей редактирования
        # Это позволяет отправлять уведомления сразу после получения результата
        # аналогично Face swap и Retoucher
        logger.info("Using asynchronous queue mode for edit model {} in edit job {}", model_name, job_id)
        try:
            task_id = submit_image_edit(
                image_path=source_file.as_posix(),
                prompt=provider_prompt,
                mask_path=mask_file.as_posix() if mask_file else None,
                **provider_options,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to submit edit job {} to fal: {}", job_id, exc)
            if job:
                job.meta["error"] = str(exc)
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, str(exc))
            raise

        # Polling для получения результата с экспоненциальным backoff
        poll_attempts = 0
        max_attempts = 120  # allow up to ~4 minutes for edit jobs (with backoff)
        poll_interval = 2.0  # Start with 2 seconds
        min_interval = 2.0
        max_interval = 10.0

        logger.info("Edit job {} polling for task {} completion", job_id, task_id)
        while True:
            status = check_image_status(task_id)
            current_status = status.get("status")
            # Логируем статус только каждые 5 попыток или при изменении статуса
            if poll_attempts % 5 == 0 or current_status not in ("processing", "queued"):
                logger.debug("Edit job {} task {} status: {} (attempt {})", job_id, task_id, current_status, poll_attempts + 1)

            if current_status == "succeeded":
                break
            if current_status == "failed":
                error = status.get("error", "Unknown error")
                logger.error("Edit job {} task {} failed: {}", job_id, task_id, error)
                if job:
                    job.meta["error"] = error
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, f"Редактирование не удалось: {error}")
                raise RuntimeError(error)

            poll_attempts += 1
            if poll_attempts >= max_attempts:
                error = f"Редактирование превысило время ожидания"
                logger.error("Edit job {} task {} timed out after {} attempts", job_id, task_id, poll_attempts)
                if job:
                    job.meta["error"] = error
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, "Задача превысила время ожидания. Попробуйте позже.")
                raise RuntimeError(error)

            # Экспоненциальный backoff: увеличиваем интервал до максимума
            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.1, max_interval)  # Увеличиваем на 10% до максимума

        # Получаем результат после завершения
        # Сначала проверяем, есть ли результат прямо в статусе
        from app.providers.fal.images import _extract_image_url as extract_image_url
        status_image_url = extract_image_url(status)
        asset = None

        if status_image_url:
            # Проверяем формат URL
            if status_image_url.startswith("data:"):
                logger.info("Edit job {} result found in status response (data URL)", job_id)
                from app.providers.fal.images import ImageAsset
                import base64
                header, _, data_part = status_image_url.partition(",")
                content = base64.b64decode(data_part)
                asset = ImageAsset(url=None, content=content, filename="edit.png")
            elif status_image_url.startswith("http") and not (status_image_url.startswith("https://queue.fal.run") or status_image_url.startswith("http://queue.fal.run")):
                logger.info("Edit job {} result found in status response (direct URL): {}", job_id, status_image_url[:100])
                from app.providers.fal.images import ImageAsset
                asset = ImageAsset(url=status_image_url, content=None, filename=None)

        # Если результат не в статусе, получаем через result_url или response_url
        if asset is None:
            # Для nano-banana/edit используем response_url, если result_url отсутствует
            result_url = status.get("result_url") or status.get("response_url")
            if not result_url:
                error = "Задача завершена, но результат недоступен"
                logger.error("Edit job {} task {} completed without result URL or result in status", job_id, task_id)
                if job:
                    job.meta["error"] = error
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, error)
                raise RuntimeError(error)

            # Небольшая задержка после завершения, чтобы API успел подготовить результат
            # Уменьшено с 1s до 0.5s для ускорения
            time.sleep(0.5)

            # Получаем результат с повторными попытками
            max_result_attempts = 3  # Уменьшено с 5 до 3 попыток
            result_delay = 0.5  # Уменьшено с 1.0 до 0.5 секунды
            last_result_error: Exception | None = None

            for result_attempt in range(max_result_attempts):
                try:
                    asset = resolve_image_asset(result_url)
                    logger.info("Edit job {} successfully got result on attempt {}: asset.url={}, asset.content={}", 
                               job_id, result_attempt + 1, asset.url[:100] if asset.url else "None", asset.content is not None)
                    break
                except httpx.HTTPStatusError as exc:
                    last_result_error = exc
                    status_code = exc.response.status_code
                    if status_code in (500, 502, 503, 401) and result_attempt < max_result_attempts - 1:
                        logger.warning(
                            "Edit job {} result attempt {} failed with {}: {}. Retrying in {:.1f}s",
                            job_id,
                            result_attempt + 1,
                            status_code,
                            exc.response.text[:100] if hasattr(exc.response, 'text') else str(exc),
                            result_delay,
                        )
                        time.sleep(result_delay)
                        result_delay *= 1.5
                        continue
                    else:
                        logger.error("Edit job {} result attempt {} failed with {}: {}", job_id, result_attempt + 1, status_code, exc)
                        raise
                except Exception as exc:  # noqa: BLE001
                    last_result_error = exc
                    logger.error("Edit job {} result attempt {} failed: {}", job_id, result_attempt + 1, exc)
                    if result_attempt >= max_result_attempts - 1:
                        raise

            if asset is None:
                error = last_result_error or RuntimeError("Failed to get edit result")
                logger.error("Edit job {} failed to get result after {} attempts: {}", job_id, max_result_attempts, error)
                if job:
                    job.meta["error"] = str(error)
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, f"Не удалось получить результат: {error}")
                raise RuntimeError(str(error))

        image_url = asset.url
        image_bytes = asset.content
        filename = asset.filename
        saved_path = None
        if image_bytes is not None:
            saved_path = _persist_asset(asset, output_file.as_posix())

        if job:
            if image_url:
                job.meta["image_url"] = image_url
            if image_bytes:
                job.meta["image_inline"] = True
                if filename:
                    job.meta["image_filename"] = filename
            if saved_path:
                job.meta["result_path"] = saved_path.as_posix()
            elif image_url:
                job.meta["result_path"] = None
            job.save_meta()

        if saved_path is None and image_url:
            _schedule_result_download(job_id, image_url, output_file)

        logger.success("Edit job {} completed: {}", job_id, image_url or filename or "binary")
        if notify_options.get("chat_id"):
            try:
                reply_markup = None
                # Определяем заголовок: Stylish text только для моделей, используемых ИСКЛЮЧИТЕЛЬНО в Stylish text режиме
                # Seedream используется и для обычного редактирования, поэтому не включаем её в этот список
                stylish_models = {"fal-ai/ideogram/v2/edit", "fal-ai/reve/fast/edit", "fal-ai/gpt-image-1-mini/edit"}
                is_stylish = model_name in stylish_models
                logger.info("Edit job {}: model_name='{}', is_stylish={}, stylish_models={}", 
                            job_id, model_name, is_stylish, stylish_models)
                caption_title = "✨ Stylish text готов!" if is_stylish else "🛠️ Редактирование готово!"
                logger.info("Edit job {}: caption_title='{}'", job_id, caption_title)
                if image_bytes is not None:
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_bytes=image_bytes,
                        filename=filename,
                        caption_title=caption_title,
                        reply_markup=reply_markup,
                    )
                else:
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_url=image_url,
                        caption_title=caption_title,
                        reply_markup=reply_markup,
                    )
            except Exception as notify_error:  # noqa: BLE001
                logger.error("Failed to send Telegram notification for edit job {}: {}", job_id, notify_error)

        # Confirm operation after successful completion
        if operation_id:
            logger.info("Image edit job {}: attempting to confirm operation_id={} (type: {})", 
                       job_id, operation_id, type(operation_id).__name__)
            db = SessionLocal()
            try:
                success = BillingService.confirm_operation(db, operation_id)
                if success:
                    logger.info("Confirmed operation {} for edit job {}", operation_id, job_id)
                else:
                    logger.error("Failed to confirm operation {} for edit job {} - operation may not exist or already processed", 
                               operation_id, job_id)
            except Exception as e:
                logger.error("Error confirming operation {} for edit job {}: {}", operation_id, job_id, e, exc_info=True)
            finally:
                db.close()
        else:
            logger.warning("Image edit job {}: no operation_id provided, skipping billing confirmation", job_id)

        return image_url or ""
    except Exception as e:
        # Mark operation as failed on any error
        if operation_id:
            db = SessionLocal()
            try:
                BillingService.fail_operation(db, operation_id)
                logger.info("Marked operation {} as failed for edit job {} due to error", operation_id, job_id)
            except Exception as fail_error:
                logger.error("Error failing operation {} for edit job {}: {}", operation_id, job_id, fail_error, exc_info=True)
            finally:
                db.close()
        raise


def process_retoucher_job(
    job_id: str,
    prompt: str,
    image_path: str,
    mode: str,
    instruction: str | None,
    options: dict | None,
    output_path: str,
) -> str:
    logger.info("process_retoucher_job called: job_id={}, mode={}, model={}", 
                job_id, mode, RETOUCHER_MODELS.get(mode, "default"))
    # Import models to ensure they are registered with Base.metadata
    from app.db import models  # noqa: F401
    from app.services.billing import BillingService
    from app.db.base import SessionLocal

    provider_options: Dict[str, Any] = dict(options or {})
    operation_id_raw = provider_options.pop("operation_id", None)
    operation_id = _parse_operation_id(operation_id_raw, job_id, "Retoucher")
    provider_prompt = provider_options.pop("provider_prompt", prompt)
    model_name = provider_options.setdefault("model", RETOUCHER_MODELS.get(mode, settings.fal_retoucher_model))
    logger.info("process_retoucher_job: model_name={}, prompt={}", model_name, prompt[:100] if prompt else "None")

    notify_options = _extract_notify_options(provider_options)
    output_file = Path(output_path)
    source_file = Path(image_path)

    job = get_current_job()

    try:
        if job:
            job.meta.update(
                {
                    "prompt": prompt,
                    "retoucher": True,
                    "mode": mode,
                    "instruction": instruction,
                    "source_path": source_file.as_posix(),
                }
            )
            if prompt != provider_prompt:
                job.meta["provider_prompt"] = provider_prompt
            job.save_meta()

        logger.info(
            "Processing retoucher job {} mode={} instruction={}",
            job_id,
            mode,
            instruction,
        )

        if not source_file.exists():
            error = "Исходное изображение не найдено."
            logger.error("Retoucher job {} missing source {}", job_id, image_path)
            if job:
                job.meta["error"] = error
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, error)
            raise RuntimeError(error)

        # Проверяем размер файла перед отправкой
        try:
            file_size = source_file.stat().st_size
        except Exception as stat_exc:
            error = f"Не удалось получить информацию о файле: {stat_exc}"
            logger.error("Retoucher job {} failed to stat source file: {}", job_id, stat_exc)
            if job:
                job.meta["error"] = error
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, error)
            raise RuntimeError(error)
        if file_size > RETOUCHER_MAX_FILE_BYTES:
            file_size_mb = file_size / (1024 * 1024)
            error = (
                f"❌ Размер изображения слишком большой ({file_size_mb:.1f} МБ).\n\n"
                f"Пожалуйста, загрузите изображение размером менее 10 МБ."
            )
            logger.error(
                "Retoucher job {}: source image size {:.2f}MB exceeds limit {:.2f}MB",
                job_id,
                file_size_mb,
                RETOUCHER_MAX_FILE_BYTES / (1024 * 1024),
            )
            if job:
                job.meta["error"] = error
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, error)
            raise RuntimeError(error)

        # Для Nano Banana edit используем асинхронный режим (как в кнопке "Изменить"),
        # так как синхронный режим блокирует worker'ы при высокой нагрузке
        # Асинхронный режим работает через queue_result с базовым путем fal-ai/nano-banana
        if False and mode == "enhance" and ("nano-banana" in model_name.lower() and "pro" not in model_name.lower() and "/edit" in model_name.lower()):
            # Применяем настройки качества для Nano Banana edit (обычный)
            provider_options["num_inference_steps"] = 60
            provider_options["guidance_scale"] = 9.0
            logger.info("Retoucher job {}: Using synchronous mode for Nano Banana edit with quality settings: num_inference_steps={}, guidance_scale={}", 
                       job_id, provider_options.get("num_inference_steps"), provider_options.get("guidance_scale"))
            
            # Используем синхронный режим для nano-banana/edit (как в Smart Merge)
            from app.providers.fal.images import run_image_edit
            try:
                asset = run_image_edit(
                    image_path=source_file.as_posix(),
                    prompt=provider_prompt,
                    mask_path=None,
                    **provider_options,
                )
                logger.info("Retoucher job {}: Got result from synchronous run_image_edit: asset.url={}, asset.content={}", 
                           job_id, asset.url[:100] if asset.url else "None", asset.content is not None)
            except Exception as exc:  # noqa: BLE001
                logger.error("Retoucher job {} synchronous run_image_edit failed: {}", job_id, exc)
                if job:
                    job.meta["error"] = str(exc)
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, f"Ошибка ретуши: {exc}")
                raise
        else:
            # Для других моделей используем асинхронный queue API
            task_id: str | None = None
            last_error: Exception | None = None
            for attempt in range(1, RETOUCHER_SUBMIT_MAX_ATTEMPTS + 1):
                try:
                    from app.providers.fal.images import submit_image_edit
                    task_id = submit_image_edit(
                        image_path=source_file.as_posix(),
                        prompt=provider_prompt,
                        mask_path=None,
                        **provider_options,
                    )
                    break
                except httpx.RequestError as exc:
                    last_error = exc
                    logger.warning(
                        "Retoucher job {} submit attempt {} failed: {}",
                        job_id,
                        attempt,
                        exc,
                    )
                    if attempt < RETOUCHER_SUBMIT_MAX_ATTEMPTS:
                        time.sleep(RETOUCHER_SUBMIT_BACKOFF * attempt)
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    logger.error("Retoucher job {} submit failed: {}", job_id, exc)
                    break

            if task_id is None:
                error_text = "Не удалось отправить запрос на ретушь. Попробуйте позже."
                if job:
                    job.meta["error"] = str(last_error) if last_error else error_text
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, error_text)
                if last_error:
                    raise last_error
                raise RuntimeError(error_text)

            # Polling для получения результата с экспоненциальным backoff
            poll_attempts = 0
            max_attempts = 120  # allow up to ~4 minutes for retoucher jobs (with backoff)
            poll_interval = 2.0  # Start with 2 seconds
            max_interval = 10.0

            logger.info("Retoucher job {} polling for task {} completion", job_id, task_id)
            status: dict[str, Any]
            while True:
                from app.providers.fal.images import check_image_status
                status = check_image_status(task_id)
                current_status = status.get("status")
                # Логируем статус только каждые 5 попыток или при изменении статуса
                if poll_attempts % 5 == 0 or current_status not in ("processing", "queued", "IN_QUEUE", "IN_PROGRESS"):
                    logger.debug("Retoucher job {} task {} status: {} (attempt {})", job_id, task_id, current_status, poll_attempts + 1)

                if current_status == "succeeded":
                    break
                if current_status == "failed":
                    error = status.get("error", "Unknown error")
                    logger.error("Retoucher job {} failed: {}", job_id, error)
                    if job:
                        job.meta["error"] = error
                        job.save_meta()
                    if notify_options.get("chat_id"):
                        _send_failure_notification_sync(notify_options, job_id, str(error))
                    raise RuntimeError(error)
                poll_attempts += 1
                if poll_attempts >= max_attempts:
                    error = "Время ожидания ретуши истекло. Попробуйте позже."
                    logger.error("Retoucher job {} timed out after {} attempts", job_id, poll_attempts)
                    if job:
                        job.meta["error"] = error
                        job.save_meta()
                    if notify_options.get("chat_id"):
                        _send_failure_notification_sync(notify_options, job_id, error)
                    raise RuntimeError(error)

                # Экспоненциальный backoff: увеличиваем интервал до максимума
                time.sleep(poll_interval)
                poll_interval = min(poll_interval * 1.1, max_interval)  # Увеличиваем на 10% до максимума

            # Получаем результат после завершения
            from app.providers.fal.images import _extract_image_url as extract_image_url, resolve_image_asset
            status_image_url = extract_image_url(status)
            logger.info("Retoucher job {} checking status for result: keys={}, extracted_url={}", 
                       job_id, list(status.keys()) if isinstance(status, dict) else "not a dict",
                       status_image_url[:100] if status_image_url else "None")
            asset = None

            if status_image_url:
                # Проверяем формат URL
                if status_image_url.startswith("data:"):
                    logger.info("Retoucher job {} result found in status response (data URL)", job_id)
                    from app.providers.fal.images import ImageAsset
                    import base64
                    header, _, data_part = status_image_url.partition(",")
                    content = base64.b64decode(data_part)
                    asset = ImageAsset(url=None, content=content, filename="retouch.png")
                elif status_image_url.startswith("http") and not (status_image_url.startswith("https://queue.fal.run") or status_image_url.startswith("http://queue.fal.run")):
                    logger.info("Retoucher job {} result found in status response (direct URL): {}", job_id, status_image_url[:100])
                    from app.providers.fal.images import ImageAsset
                    asset = ImageAsset(url=status_image_url, content=None, filename=None)

            # Если результат не в статусе, получаем через result_url или response_url
            if asset is None:
                result_url = status.get("result_url") or status.get("response_url")
                if not result_url:
                    error = "Задача завершена, но результат недоступен"
                    logger.error("Retoucher job {} task {} completed without result URL or result in status", job_id, task_id)
                    if job:
                        job.meta["error"] = error
                        job.save_meta()
                    if notify_options.get("chat_id"):
                        _send_failure_notification_sync(notify_options, job_id, error)
                    raise RuntimeError(error)

                # Небольшая задержка после завершения, чтобы API успел подготовить результат
                time.sleep(0.5)

                # Получаем результат с повторными попытками
                max_result_attempts = 3
                result_delay = 0.5
                last_result_error: Exception | None = None

                for result_attempt in range(max_result_attempts):
                    try:
                        asset = resolve_image_asset(result_url)
                        logger.info("Retoucher job {} successfully got result on attempt {}: asset.url={}, asset.content={}", 
                                   job_id, result_attempt + 1, asset.url[:100] if asset.url else "None", asset.content is not None)
                        break
                    except httpx.HTTPStatusError as exc:
                        last_result_error = exc
                        status_code = exc.response.status_code
                        if status_code in (500, 502, 503, 401) and result_attempt < max_result_attempts - 1:
                            logger.warning(
                                "Retoucher job {} result attempt {} failed with {}: {}. Retrying in {:.1f}s",
                                job_id,
                                result_attempt + 1,
                                status_code,
                                exc.response.text[:100] if hasattr(exc.response, 'text') else str(exc),
                                result_delay,
                            )
                            time.sleep(result_delay)
                            result_delay *= 1.5
                            continue
                        else:
                            logger.error("Retoucher job {} result attempt {} failed with {}: {}", job_id, result_attempt + 1, status_code, exc)
                            raise
                    except Exception as exc:  # noqa: BLE001
                        last_result_error = exc
                        logger.error("Retoucher job {} result attempt {} failed: {}", job_id, result_attempt + 1, exc)
                        if result_attempt >= max_result_attempts - 1:
                            raise

                if asset is None:
                    error = last_result_error or RuntimeError("Failed to get retoucher result")
                    logger.error("Retoucher job {} failed to get result after {} attempts: {}", job_id, max_result_attempts, error)
                    if job:
                        job.meta["error"] = str(error)
                        job.save_meta()
                    if notify_options.get("chat_id"):
                        _send_failure_notification_sync(notify_options, job_id, f"Не удалось получить результат: {error}")
                    raise RuntimeError(str(error))

        # Используем ту же логику сохранения, что и в process_image_edit_job
        image_url = asset.url
        image_bytes = asset.content
        filename = asset.filename
        saved_path = None
        if image_bytes is not None:
            saved_path = _persist_asset(asset, output_file.as_posix())

        if job:
            if image_url:
                job.meta["image_url"] = image_url
            if image_bytes:
                job.meta["image_inline"] = True
                if filename:
                    job.meta["image_filename"] = filename
            if saved_path:
                job.meta["result_path"] = saved_path.as_posix()
            elif image_url:
                job.meta["result_path"] = None
            else:
                job.meta["result_path"] = None
            job.save_meta()

        # Отправляем уведомление об успехе (используем ту же логику, что и в process_image_edit_job)
        if notify_options.get("chat_id"):
            try:
                reply_markup = None
                caption_title = "✨ Ретушь готова!"
                if image_bytes is not None:
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_bytes=image_bytes,
                        filename=filename,
                        caption_title=caption_title,
                        reply_markup=reply_markup,
                    )
                else:
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_url=image_url,
                        caption_title=caption_title,
                        reply_markup=reply_markup,
                    )
            except Exception as notify_error:  # noqa: BLE001
                logger.error("Failed to send Telegram notification for retoucher job {}: {}", job_id, notify_error)

        logger.info("Retoucher job {} completed successfully", job_id)
        
        # Confirm operation after successful completion
        if operation_id:
            from app.db.base import SessionLocal
            from app.services.billing import BillingService
            db = SessionLocal()
            try:
                success = BillingService.confirm_operation(db, operation_id)
                if success:
                    logger.info("Confirmed operation {} for retoucher job {}", operation_id, job_id)
                else:
                    logger.error("Failed to confirm operation {} for retoucher job {}", operation_id, job_id)
            except Exception as e:
                logger.error("Error confirming operation {} for retoucher job {}: {}", operation_id, job_id, e, exc_info=True)
            finally:
                db.close()
        
        return {
            "image_url": image_url,
            "image_bytes": image_bytes,
            "filename": filename,
            "saved_path": saved_path.as_posix() if saved_path else None,
        }

        return caption_path
    except Exception as e:
                    # Mark operation as failed on any error
        if operation_id:
            db = SessionLocal()
            try:
                BillingService.fail_operation(db, operation_id)
                logger.info("Marked operation {} as failed for retoucher job {} due to error", operation_id, job_id)
            except Exception as fail_error:
                logger.error("Error failing operation {} for retoucher job {}: {}", operation_id, job_id, fail_error, exc_info=True)
            finally:
                db.close()
        raise


def process_smart_merge_job(
    job_id: str,
    prompt: str,
    image_sources: list[dict[str, str | None]],
    options: dict | None,
    output_path: str,
) -> str:
    # Import models to ensure they are registered with Base.metadata
    from app.db import models  # noqa: F401
    from app.services.billing import BillingService
    from app.db.base import SessionLocal

    if not image_sources:
        raise ValueError("Smart merge requires at least one image source")

    provider_options: Dict[str, Any] = dict(options or {})
    operation_id_raw = provider_options.pop("operation_id", None)
    operation_id = _parse_operation_id(operation_id_raw, job_id, "Smart merge")
    provider_prompt = provider_options.pop("provider_prompt", prompt)
    provider_options.setdefault("model", SMART_MERGE_DEFAULT_MODEL)
    # Если есть width и height, не устанавливаем size по умолчанию
    # (width и height имеют приоритет в _build_input_payload)
    if "width" not in provider_options or "height" not in provider_options:
        provider_options.setdefault("size", SMART_MERGE_DEFAULT_SIZE)
        provider_options.setdefault("aspect_ratio", SMART_MERGE_DEFAULT_ASPECT_RATIO)

    # Проверяем, является ли модель Nano-banana (может принимать русский текст)
    model_name = provider_options.get("model", "")
    is_nano_banana_regular = model_name == SMART_MERGE_DEFAULT_MODEL or model_name == "fal-ai/nano-banana" or ("nano-banana" in model_name.lower() and "pro" not in model_name.lower())
    is_nano_banana_pro = "nano-banana-pro" in model_name.lower()
    is_nano_banana = is_nano_banana_regular or is_nano_banana_pro

    if is_nano_banana:
        # Для Nano-banana не переводим промпт, используем оригинальный русский
        logger.info("Smart merge job {}: Nano-banana model detected, using original Russian prompt without translation", job_id)
        provider_prompt = prompt  # Используем оригинальный промпт без перевода
    
    # Применяем настройки качества для nano-banana (обычный и pro) и seedream в Smart Merge
    is_seedream = "seedream" in model_name.lower()
    
    if is_nano_banana_regular:
        # Увеличиваем параметры качества для максимального результата (обычный nano-banana)
        provider_options["num_inference_steps"] = 60
        provider_options["guidance_scale"] = 9.0
        logger.info("Smart merge job {}: Applied quality settings for nano-banana: num_inference_steps={}, guidance_scale={}", 
                   job_id, provider_options.get("num_inference_steps"), provider_options.get("guidance_scale"))
    elif is_nano_banana_pro:
        # Применяем максимальные настройки качества для nano-banana-pro (максимальная прорисовка)
        provider_options["num_inference_steps"] = 90
        provider_options["guidance_scale"] = 10.0
        logger.info("Smart merge job {}: Applied enhanced quality settings for nano-banana-pro: num_inference_steps={}, guidance_scale={}", 
                   job_id, provider_options.get("num_inference_steps"), provider_options.get("guidance_scale"))
    elif is_seedream:
        # Применяем максимальные настройки качества для Seedream (увеличенная прорисовка и детализация)
        provider_options["num_inference_steps"] = 120
        provider_options["guidance_scale"] = 12.0
        provider_options["enhance_prompt_mode"] = "standard"  # Добавлен для повышения качества промпта
        logger.info("Smart merge job {}: Applied enhanced quality settings for Seedream: num_inference_steps={}, guidance_scale={}, enhance_prompt_mode={}", 
                   job_id, provider_options.get("num_inference_steps"), provider_options.get("guidance_scale"), provider_options.get("enhance_prompt_mode"))

    notify_options = _extract_notify_options(provider_options)
    output_file = Path(output_path)

    job = get_current_job()

    try:
        if job:
            job.meta.update(
                {
                    "prompt": prompt,
                    "smart_merge": True,
                    "sources": image_sources,
                }
            )
        if provider_prompt != prompt:
            job.meta["provider_prompt"] = provider_prompt
        job.save_meta()

        logger.info(
            "Processing smart merge job {} with {} images, prompt='{}', provider_prompt='{}'",
            job_id,
            len(image_sources),
            prompt,
            provider_prompt,
        )

        # Для nano-banana/edit и nano-banana-pro/edit используем асинхронный режим через queue API
        # чтобы не блокировать worker'ы при высокой нагрузке
        model_name = provider_options.get("model", "")
        is_nano_banana_edit = "nano-banana" in model_name.lower() and "/edit" in model_name.lower()
        is_nano_banana_pro_edit = "nano-banana-pro" in model_name.lower() and "/edit" in model_name.lower()
        
        if is_nano_banana_edit:
            # Используем асинхронный режим для nano-banana/edit и nano-banana-pro/edit
            from app.providers.fal.images import submit_smart_merge
            from app.providers.fal.images import check_status as check_image_status
            from app.providers.fal.images import resolve_result_asset as resolve_image_asset
            if is_nano_banana_pro_edit:
                logger.info("Smart merge job {}: Using asynchronous queue mode for nano-banana-pro/edit", job_id)
            else:
                logger.info("Smart merge job {}: Using asynchronous queue mode for nano-banana/edit", job_id)
            try:
                task_id = submit_smart_merge(
                    image_sources=image_sources,
                    prompt=provider_prompt,
                    **provider_options,
                )
                
                # Polling для получения результата
                # Используем более частые проверки для быстрого обнаружения завершения
                poll_attempts = 0
                max_attempts = 180  # Увеличено для nano-banana-pro/edit (может обрабатываться до 2-3 минут)
                poll_interval = 1.5  # Уменьшено с 2.0 до 1.5 секунд для более быстрого обнаружения завершения
                max_interval = 5.0  # Уменьшено с 10.0 до 5.0 секунд, чтобы не пропустить завершение
                
                logger.info("Smart merge job {} polling for task {} completion", job_id, task_id)
                while True:
                    status = check_image_status(task_id)
                    current_status = status.get("status")
                    if poll_attempts % 10 == 0 or current_status not in ("processing", "queued", "IN_QUEUE", "IN_PROGRESS"):
                        logger.debug("Smart merge job {} task {} status: {} (attempt {})", job_id, task_id, current_status, poll_attempts + 1)
                    
                    if current_status == "succeeded":
                        break
                    if current_status == "failed":
                        error = status.get("error", "Unknown error")
                        logger.error("Smart merge job {} task {} failed: {}", job_id, task_id, error)
                        if job:
                            job.meta["error"] = error
                            job.save_meta()
                        if notify_options.get("chat_id"):
                            _send_failure_notification_sync(notify_options, job_id, f"Редактирование не удалось: {error}")
                        raise RuntimeError(error)
                    
                    poll_attempts += 1
                    if poll_attempts >= max_attempts:
                        error = "Редактирование превысило время ожидания"
                        logger.error("Smart merge job {} task {} timed out after {} attempts", job_id, task_id, poll_attempts)
                        if job:
                            job.meta["error"] = error
                            job.save_meta()
                        if notify_options.get("chat_id"):
                            _send_failure_notification_sync(notify_options, job_id, "Задача превысила время ожидания. Попробуйте позже.")
                        raise RuntimeError(error)
                    
                    time.sleep(poll_interval)
                    # Увеличиваем интервал медленнее, чтобы не пропустить завершение
                    poll_interval = min(poll_interval * 1.05, max_interval)  # Уменьшено с 1.1 до 1.05 для более плавного увеличения
                
                # Получаем результат
                result_url = status.get("result_url") or status.get("response_url")
                if not result_url:
                    error = "Задача завершена, но результат недоступен"
                    logger.error("Smart merge job {} task {} completed without result URL", job_id, task_id)
                    if job:
                        job.meta["error"] = error
                        job.save_meta()
                    if notify_options.get("chat_id"):
                        _send_failure_notification_sync(notify_options, job_id, error)
                    raise RuntimeError(error)
                
                time.sleep(0.5)
                asset = resolve_image_asset(result_url)
                logger.info("Smart merge job {} successfully got result: asset.url={}, asset.content={}", 
                           job_id, asset.url[:100] if asset.url else "None", asset.content is not None)
            except Exception as exc:  # noqa: BLE001
                logger.error("Smart merge job {} asynchronous mode failed: {}", job_id, exc)
                if job:
                    job.meta["error"] = str(exc)
                    job.save_meta()
                if notify_options.get("chat_id"):
                    _send_failure_notification_sync(notify_options, job_id, f"Ошибка редактирования: {exc}")
                raise
        else:
            # Для других моделей используем синхронный режим (как было)
            try:
                asset = run_smart_merge(
                    image_sources=image_sources,
                    prompt=provider_prompt,
                    **provider_options,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Smart merge job {} failed: {}", job_id, exc)
                if job:
                    job.meta["error"] = str(exc)
                    job.save_meta()
                if notify_options.get("chat_id"):
                    failure_text = "Сервис временно недоступен, попробуйте позже."
                    if isinstance(exc, ValueError):
                        failure_text = "Не удалось обработать изображения. Проверьте файлы и попробуйте снова."
                    _send_failure_notification_sync(
                        notify_options,
                        job_id,
                        failure_text,
                    )
                raise

        # Используем ту же логику, что и в process_image_job
        image_url = asset.url
        image_bytes = asset.content
        filename = asset.filename
        saved_path = None
        if asset.content is not None:
            saved_path = _persist_asset(asset, output_file.as_posix())

        # Если изображение не было скачано, но есть URL, пробуем скачать с коротким таймаутом
        # Если не успевает быстро скачаться, отправляем по URL (Telegram может принять URL напрямую)
        if image_bytes is None and image_url:
            # Не пытаемся скачивать синхронно - это может занять много времени
            # Отправляем по URL, Telegram обычно принимает URL от fal.media
            logger.info("Smart merge: image not downloaded, will send by URL: {}", image_url[:100])

        if job:
            if image_url:
                job.meta["image_url"] = image_url
            if image_bytes:
                job.meta["image_inline"] = True
                if filename:
                    job.meta["image_filename"] = filename
            if saved_path:
                job.meta["result_path"] = saved_path.as_posix()
            elif image_url:
                job.meta["result_path"] = None
            job.save_meta()

        # Не запускаем фоновое скачивание для Smart Merge - отправляем по URL сразу
        # Фоновое скачивание может занимать много времени и не нужно для немедленной отправки
        # if saved_path is None and image_url:
        #     _schedule_result_download(job_id, image_url, output_file)

        logger.success("Smart merge job {} completed: {}", job_id, image_url or filename or "binary")
        if notify_options.get("chat_id"):
            try:
                reply_markup = None
                if image_bytes is not None:
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_bytes=image_bytes,
                        filename=filename,
                        caption_title="Готово",
                        reply_markup=reply_markup,
                    )
                else:
                    _send_success_notification_sync(
                        notify_options,
                        job_id,
                        image_url=image_url,
                        caption_title="Готово",
                        reply_markup=reply_markup,
                    )
            except Exception as notify_error:  # noqa: BLE001
                logger.error("Failed to send Telegram notification for smart merge job {}: {}", job_id, notify_error)

        # Confirm operation after successful completion
        if operation_id:
            db = SessionLocal()
            try:
                success = BillingService.confirm_operation(db, operation_id)
                if success:
                    logger.info("Confirmed operation {} for smart merge job {}", operation_id, job_id)
                else:
                    logger.error("Failed to confirm operation {} for smart merge job {}", operation_id, job_id)
            except Exception as e:
                logger.error("Error confirming operation {} for smart merge job {}: {}", operation_id, job_id, e, exc_info=True)
            finally:
                db.close()

        return image_url or ""
    except Exception as e:
        # Mark operation as failed on any error
        if operation_id:
            db = SessionLocal()
            try:
                BillingService.fail_operation(db, operation_id)
                logger.info("Marked operation {} as failed for smart merge job {} due to error", operation_id, job_id)
            except Exception as fail_error:
                logger.error("Error failing operation {} for smart merge job {}: {}", operation_id, job_id, fail_error, exc_info=True)
            finally:
                db.close()
        raise


def process_image_upscale_job(
    job_id: str,
    image_url: str | None,
    image_path: str | None,
    scale: int,
    options: dict | None,
    output_path: str,
) -> str:
    # Import models to ensure they are registered with Base.metadata
    from app.db import models  # noqa: F401
    from app.services.billing import BillingService
    from app.db.base import SessionLocal

    provider_options: Dict[str, Any] = dict(options or {})
    operation_id_raw = provider_options.pop("operation_id", None)
    operation_id = _parse_operation_id(operation_id_raw, job_id, "Upscale")
    scale_value = int(provider_options.pop("scale", scale or 2))
    if scale_value > 2:
        logger.debug("Clamping upscale scale {} to 2 to limit output size", scale_value)
        scale_value = 2
    model_name = provider_options.setdefault("model", settings.fal_upscale_model)
    provider_options.pop("model", None)
    provider_options.pop("fallback_model", None)  # Remove fallback if present

    notify_options = _extract_notify_options(provider_options)
    output_file = Path(output_path)

    job = get_current_job()
    
    if job:
        job.meta.update(
            {
                "upscale": True,
                "source_url": image_url,
                "scale": scale_value,
                "model": model_name,
            }
        )
        job.save_meta()

    cleanup_paths: list[Path] = []
    local_input_path: Path | None = None
    input_dimensions = None
    if image_path:
        candidate = Path(image_path)
        if candidate.exists():
            local_input_path = candidate
        else:
            logger.warning("Provided image_path {} does not exist for upscale job {}", image_path, job_id)

    if local_input_path is None and image_url:
        fd, tmp_name = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            download_file(image_url, tmp_path.as_posix())
            cleanup_paths.append(tmp_path)
            local_input_path = tmp_path
        except Exception as download_exc:  # noqa: BLE001
            logger.error("Failed to download source image for upscale job {}: {}", job_id, download_exc)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

    if local_input_path:
        try:
            with Image.open(local_input_path) as input_image:
                prepared = input_image.convert("RGB")
                max_edge = max(prepared.size)
                original_input_size = f"{prepared.width}x{prepared.height}"
                # Don't reduce input size - let the model handle it
                # The model should accept images up to reasonable size
                # Only log if we would have reduced it
                if max_edge > UPSCALE_INPUT_MAX_EDGE:
                    logger.info(
                        "Upscale job {}: input image {}x{} exceeds {}px limit, but sending as-is (model should handle it)",
                        job_id,
                        prepared.width,
                        prepared.height,
                        UPSCALE_INPUT_MAX_EDGE,
                    )
                else:
                    # Calculate input file size
                    input_file_size = local_input_path.stat().st_size / (1024 * 1024)
                    logger.info(
                        "Upscale job {}: input image size {}x{} (file size: {:.2f}MB, format: PNG)",
                        job_id,
                        prepared.width,
                        prepared.height,
                        input_file_size,
                    )
                fd, png_name = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                png_path = Path(png_name)
                prepared.save(png_path.as_posix(), "PNG", optimize=True)
                cleanup_paths.append(png_path)
                local_input_path = png_path
                input_dimensions = original_input_size
        except Exception as prepare_exc:  # noqa: BLE001
            logger.warning("Failed to preprocess upscale input for job {}: {}", job_id, prepare_exc)

    # Log input image dimensions
    if input_dimensions is None and local_input_path and local_input_path.exists():
        try:
            with Image.open(local_input_path) as img:
                input_dimensions = f"{img.width}x{img.height}"
        except Exception:
            pass

    logger.info(
        "Processing image upscale job {} for url={}, path={} (scale={}, input_size={})",
        job_id,
        image_url,
        image_path,
        scale_value,
        input_dimensions or "unknown",
    )

    if local_input_path is None:
        error = "Не удалось подготовить изображение для апскейла."
        logger.error("Upscale job {} missing source image (url={}, path={})", job_id, image_url, image_path)
        if job:
            job.meta["error"] = error
            job.save_meta()
        if notify_options.get("chat_id"):
            _send_failure_notification_sync(notify_options, job_id, error)
        raise RuntimeError(error)

    # Use queue API for more reliable processing (async approach like face swap)
    attempts = 0
    delay = UPSCALE_RETRY_BASE_DELAY
    last_error: Exception | None = None
    task_id: str | None = None
    used_model = model_name

    # Add parameters to control output format - request JPEG format with quality for file size control
    upscale_options = dict(provider_options)
    # Try to request JPEG format for all upscale models to reduce file size
    # Note: Some models may not support output_format parameter, but we try anyway
    if model_name in ("fal-ai/recraft/upscale/crisp", "fal-ai/recraft/upscale/creative", "fal-ai/esrgan"):
        # Request JPEG format with quality parameter to control file size (3-5 MB target)
        upscale_options.setdefault("output_format", "jpeg")
        upscale_options.setdefault("quality", 50)  # Lower quality (40-50%) to reduce file size
        logger.info("Upscale job {}: requesting JPEG output format with quality={} for model {}", 
                   job_id, upscale_options.get("quality"), model_name)

    # Try primary model first
    while attempts < UPSCALE_MAX_ATTEMPTS:
        try:
            logger.info("Upscale job {}: calling submit_image_upscale with upscale_options: {}", 
                       job_id, {k: v for k, v in upscale_options.items() if not k.startswith("notify_") and not k.startswith("source_")})
            task_id = submit_image_upscale(
                image_url=None,
                image_path=local_input_path.as_posix() if local_input_path else None,
                scale=scale_value,
                model=model_name,
                **upscale_options,
            )
            logger.info("Upscale job {} submitted to queue with task_id: {} (model: {})", job_id, task_id, model_name)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            attempts += 1
            logger.info("Upscale job {} submit attempt {} caught exception: {} ({})", 
                       job_id, attempts, type(exc).__name__, exc)
            is_retryable = _is_retryable_error(exc)
            logger.info("Upscale job {} submit attempt {}: is_retryable={}, attempts_left={}", 
                       job_id, attempts, is_retryable, UPSCALE_MAX_ATTEMPTS - attempts)
            if is_retryable and attempts < UPSCALE_MAX_ATTEMPTS:
                error_type = "network/server" if isinstance(exc, (httpx.RequestError, httpx.HTTPStatusError)) else "error"
                logger.warning(
                    "Upscale job {} submit attempt {} failed due to {} issue: {}. Retrying in {:.1f}s",
                    job_id,
                    attempts,
                    error_type,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay *= 2
                continue
            logger.error("Upscale job {} submit failed after {} attempts: {}", job_id, attempts, exc)

            # Determine error message based on error type
            if isinstance(exc, httpx.HTTPStatusError):
                status_code = exc.response.status_code
                if status_code == 500:
                    error_msg = (
                        "Сервер временно недоступен (ошибка 500). "
                        "Это проблема на стороне сервиса fal.ai. "
                        "Попробуйте повторить запрос через несколько минут."
                    )
                elif status_code == 422:
                    error_msg = (
                        "Некорректные параметры запроса (ошибка 422). "
                        "Проверьте, что загружено корректное изображение."
                    )
                elif status_code == 429:
                    error_msg = (
                        "Превышен лимит запросов (ошибка 429). "
                        "Подождите немного и попробуйте снова."
                    )
                else:
                    error_msg = f"Ошибка API (код {status_code}). Попробуйте позже."
            elif isinstance(exc, httpx.RequestError):
                error_msg = (
                    "Проблема с сетью при обращении к API. "
                    "Проверьте подключение к интернету и попробуйте снова."
                )
            else:
                    error_msg = f"Не удалось отправить запрос на улучшение изображения: {str(exc)}. Попробуйте позже."

            if job:
                job.meta["error"] = str(exc)
                job.meta["error_message"] = error_msg
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(
                    notify_options,
                    job_id,
                    error_msg,
                )
                raise

    if task_id is None:
        error = last_error or RuntimeError("Upscale task submission failed")
        if job:
            job.meta["error"] = str(error)
            job.save_meta()
        if notify_options.get("chat_id"):
            _send_failure_notification_sync(notify_options, job_id, str(error))
        raise RuntimeError(str(error))

    # Cleanup temporary input files before polling (they're no longer needed)
    for tmp in cleanup_paths:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            logger.debug("Failed to remove temporary file {} after upscale job {}", tmp, job_id)

    # Poll for completion using queue API
    logger.info("Upscale job {} polling for task {} completion", job_id, task_id)
    status = check_image_status(task_id)
    poll_attempts = 0

    while status["status"] not in ("succeeded", "failed"):
        if poll_attempts >= UPSCALE_POLL_MAX_ATTEMPTS:
            error = "Upscale task timed out after polling"
            logger.error("Upscale job {} task {} timed out", job_id, task_id)
            if job:
                job.meta["error"] = error
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, "Задача превысила время ожидания. Попробуйте позже.")
            raise RuntimeError(error)

        poll_attempts += 1
        time.sleep(5)  # Poll every 5 seconds
        status = check_image_status(task_id)
        logger.debug("Upscale job {} task {} status: {}", job_id, task_id, status["status"])

    if status["status"] == "failed":
        error = status.get("error", "Unknown error")
        logger.error("Upscale job {} task {} failed: {}", job_id, task_id, error)
        if job:
            job.meta["error"] = error
            job.save_meta()
        if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, f"Улучшение изображения не удалось: {error}")
        # Mark operation as failed on error
        if operation_id:
            db = SessionLocal()
            try:
                BillingService.fail_operation(db, operation_id)
                logger.info("Marked operation {} as failed for upscale job {} due to error", operation_id, job_id)
            except Exception as fail_error:
                logger.error("Error failing operation {} for upscale job {}: {}", operation_id, job_id, fail_error, exc_info=True)
            finally:
                db.close()
        raise RuntimeError(error)

    # According to fal.ai docs, when status is COMPLETED, the result may be in the status response itself
    # or available via response_url. Let's check if result is already in status first.
    from app.providers.fal.images import _extract_image_url as extract_image_url
    status_image_url = extract_image_url(status)
    logger.debug("Upscale job {} extracted URL from status: {}", job_id, status_image_url[:100] if status_image_url else "None")
    asset = None

    if status_image_url:
        # Check if this is a queue API endpoint (response_url) or a real image URL
        if status_image_url.startswith("https://queue.fal.run") or status_image_url.startswith("http://queue.fal.run"):
            # This is a queue API endpoint, not a direct image URL - skip it
            logger.info("Upscale job {} found response_url in status (not a direct image URL), will use resolve_image_asset", job_id)
            status_image_url = None
            asset = None  # Ensure asset is None so we use resolve_image_asset
        elif status_image_url.startswith("data:"):
            logger.info("Upscale job {} result found in status response (data URL)", job_id)
            # Result is already in status as data URL, extract it directly
            from app.providers.fal.images import ImageAsset
            import base64
            header, _, data_part = status_image_url.partition(",")
            content = base64.b64decode(data_part)
            asset = ImageAsset(url=None, content=content, filename="upscale.png")
        elif status_image_url.startswith("http"):
            # This looks like a direct image URL (CDN, etc.)
            logger.info("Upscale job {} result found in status response (direct URL): {}", job_id, status_image_url[:100])
            from app.providers.fal.images import ImageAsset
            asset = ImageAsset(url=status_image_url, content=None, filename=None)
        else:
            logger.warning("Upscale job {} unexpected image URL format in status: {}", job_id, status_image_url[:100])

    # If result not in status, try to get it via response_url with retries
    if asset is None:
        result_url = status.get("result_url")
        if not result_url:
            error = "Upscale task completed but no result URL provided and no result in status"
            logger.error("Upscale job {} task {} completed without result URL or result in status", job_id, task_id)
            if job:
                job.meta["error"] = error
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, "Задача завершена, но результат недоступен.")
            raise RuntimeError(error)

        # Small delay after completion to allow API to prepare the result
        # Sometimes the API returns 500 immediately after COMPLETED status
        logger.debug("Upscale job {} task {} completed, waiting 1s before fetching result", job_id, task_id)
        time.sleep(1.0)

        # Try to get result with retries and increasing delays
        # Use resolve_image_asset which properly handles authorization and retries
        max_result_attempts = 5
        result_delay = 1.0
        last_result_error: Exception | None = None
        api_file_size: int | None = None  # Store file_size from API response

        for result_attempt in range(max_result_attempts):
            try:
                logger.debug("Upscale job {} attempt {} to get result from {}", job_id, result_attempt + 1, result_url)

                # Try to extract file_size from API response before calling resolve_image_asset
                from app.providers.fal.images import _parse_result_url
                from app.providers.fal.client import queue_result
                parsed = _parse_result_url(result_url)
                if parsed:
                    model_path, request_id = parsed
                    try:
                        response_data = queue_result(model_path, request_id)
                        if isinstance(response_data, dict):
                            # Check common structures: {'image': {'file_size': ...}} or {'file_size': ...}
                            if 'image' in response_data and isinstance(response_data['image'], dict):
                                extracted_size = response_data['image'].get('file_size')
                                if extracted_size:
                                    api_file_size = extracted_size
                                    logger.info("Upscale job {}: extracted file_size {} bytes ({:.2f}MB) from API response", 
                                               job_id, api_file_size, api_file_size / (1024 * 1024))
                            elif 'file_size' in response_data:
                                extracted_size = response_data.get('file_size')
                                if extracted_size:
                                    api_file_size = extracted_size
                                    logger.info("Upscale job {}: extracted file_size {} bytes ({:.2f}MB) from API response", 
                                               job_id, api_file_size, api_file_size / (1024 * 1024))
                    except Exception as size_extract_exc:  # noqa: BLE001
                        logger.debug("Upscale job {}: could not extract file_size from API response: {}", job_id, size_extract_exc)

                # Use resolve_image_asset which properly handles queue API authorization
                asset = resolve_image_asset(result_url)
                logger.info("Upscale job {} successfully got result on attempt {}: asset.url={}, asset.content={}", 
                           job_id, result_attempt + 1, asset.url[:100] if asset.url else "None", asset.content is not None)
                # Check if asset.url is a queue API endpoint - if so, we need to get the actual image URL
                if asset.url and (asset.url.startswith("https://queue.fal.run") or asset.url.startswith("http://queue.fal.run")):
                    logger.warning("Upscale job {} asset.url is a queue API endpoint, this should not happen. asset.url={}", 
                                  job_id, asset.url)
                    # Try to get the actual result from queue_result
                    from app.providers.fal.client import queue_result
                    from app.providers.fal.images import _extract_image_url, ImageAsset, _parse_result_url
                    parsed = _parse_result_url(result_url)
                    if parsed:
                        model_path, request_id = parsed
                        logger.info("Upscale job {} trying queue_result directly for model={}, request_id={}", 
                                   job_id, model_path, request_id)
                        response_data = queue_result(model_path, request_id)
                        logger.info("Upscale job {} queue_result response keys: {}", job_id, list(response_data.keys()) if isinstance(response_data, dict) else "not a dict")
                        actual_image_url = _extract_image_url(response_data)
                        # Try to extract file_size from response_data
                        if isinstance(response_data, dict):
                            # Check common structures: {'image': {'file_size': ...}} or {'file_size': ...}
                            if 'image' in response_data and isinstance(response_data['image'], dict):
                                api_file_size = response_data['image'].get('file_size')
                            elif 'file_size' in response_data:
                                api_file_size = response_data['file_size']
                            if api_file_size:
                                logger.info("Upscale job {}: extracted file_size {} bytes ({:.2f}MB) from API response", 
                                           job_id, api_file_size, api_file_size / (1024 * 1024))
                        if actual_image_url and not (actual_image_url.startswith("https://queue.fal.run") or actual_image_url.startswith("http://queue.fal.run")):
                            logger.info("Upscale job {} extracted actual image URL: {}", job_id, actual_image_url[:100])
                            asset = ImageAsset(url=actual_image_url, content=None, filename=None)
                        else:
                            logger.error("Upscale job {} failed to extract valid image URL from queue_result response", job_id)
                break
            except Exception as exc:  # noqa: BLE001
                last_result_error = exc
                # Check if it's an HTTP error that we can retry
                if isinstance(exc, httpx.HTTPStatusError):
                    status_code = exc.response.status_code
                    if status_code in (500, 502, 503, 401) and result_attempt < max_result_attempts - 1:
                        logger.warning(
                            "Upscale job {} result attempt {} failed with {}: {}. Retrying in {:.1f}s",
                            job_id,
                            result_attempt + 1,
                            status_code,
                            exc.response.text[:100] if hasattr(exc.response, 'text') else str(exc),
                            result_delay,
                        )
                        time.sleep(result_delay)
                        result_delay *= 1.5
                        continue
                    else:
                        logger.error("Upscale job {} result attempt {} failed with {}: {}", job_id, result_attempt + 1, status_code, exc)
                        raise
                else:
                    logger.error("Upscale job {} result attempt {} failed: {}", job_id, result_attempt + 1, exc)
                    if result_attempt >= max_result_attempts - 1:
                        raise

        if asset is None:
            error = last_result_error or RuntimeError("Failed to get upscale result")
            logger.error("Upscale job {} failed to get result after {} attempts: {}", job_id, max_result_attempts, error)
            if job:
                job.meta["error"] = str(error)
                job.save_meta()
            if notify_options.get("chat_id"):
                _send_failure_notification_sync(notify_options, job_id, f"Не удалось получить результат: {error}")
            raise RuntimeError(str(error))

    if asset is None:
        raise RuntimeError("fal upscale did not return an asset")

    # Use same approach as Smart merge - send by URL directly
    # This avoids download timeouts and Telegram handles the download server-side
    # send_document with URL doesn't compress files, so quality is preserved
    saved_path = _persist_asset(asset, output_file.as_posix(), skip_download=True)
    logger.info("Upscale: _persist_asset returned saved_path={}, asset.url={}, asset.content={}", 
                saved_path, asset.url, asset.content is not None)

    # Schedule background download for caching, but don't block sending
    if asset.url:
        _schedule_result_download(job_id, asset.url, output_file)
        logger.debug("Scheduled background download for upscale result: {} -> {}", asset.url, output_file)

    caption_url = asset.url
    image_bytes = asset.content
    filename = asset.filename

    # If no image_bytes but saved_path exists, read file (for fallback)
    if image_bytes is None and saved_path and saved_path.exists():
        try:
            image_bytes = saved_path.read_bytes()
            filename = filename or saved_path.name
            logger.debug("Read upscale result from file: {} ({} bytes)", saved_path, len(image_bytes))
        except Exception as read_exc:  # noqa: BLE001
            logger.warning("Failed to read saved upscale result {}: {}", saved_path, read_exc)

    if job:
        if asset.url:
            job.meta["image_url"] = asset.url
        if asset.content:
            job.meta["image_inline"] = True
            if asset.filename:
                job.meta["image_filename"] = asset.filename
        if saved_path:
            job.meta["result_path"] = saved_path.as_posix()
        else:
            job.meta["result_path"] = None
        job.save_meta()

    if notify_options.get("chat_id"):
        try:
            logger.info(
                "Sending upscale notification: job_id={}, has_bytes={}, has_url={}, filename={}",
                job_id,
                image_bytes is not None,
                bool(caption_url),
                filename,
            )
            if image_bytes is not None:
                _send_success_notification_sync(
                    notify_options,
                    job_id,
                    image_bytes=image_bytes,
                    filename=filename,
                    caption_title="🔍 Улучшение изображения готово!",
                    reply_markup=None,
                )
                logger.info("Upscale notification sent successfully with image bytes")
            elif caption_url:
                _send_success_notification_sync(
                    notify_options,
                    job_id,
                    image_url=caption_url,
                    caption_title="🔍 Улучшение изображения готово!",
                    reply_markup=None,
                )
                logger.info("Upscale notification sent successfully with image URL")
            else:
                logger.error("Upscale job {}: no image_bytes and no image_url to send", job_id)
        except Exception as notify_error:  # noqa: BLE001
            logger.error("Failed to send Telegram notification for upscale job {}: {}", job_id, notify_error, exc_info=True)

    # Confirm operation after successful completion
    if operation_id:
        db = SessionLocal()
        try:
            success = BillingService.confirm_operation(db, operation_id)
            if success:
                logger.info("Confirmed operation {} for upscale job {}", operation_id, job_id)
            else:
                logger.error("Failed to confirm operation {} for upscale job {}", operation_id, job_id)
        except Exception as e:
            logger.error("Error confirming operation {} for upscale job {}: {}", operation_id, job_id, e, exc_info=True)
        finally:
            db.close()

    return caption_url or ""