from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, NamedTuple
from urllib.parse import urlparse

from loguru import logger

import httpx
from PIL import Image

from app.core.config import settings, reload_settings
from app.providers.fal.client import queue_get, queue_result, queue_status, queue_submit, run_model
from app.providers.fal.models_map import (
    apply_model_defaults,
    get_image_model,
    model_requires_mask,
    model_supports_inpaint_payload,
)


SEEDREAM_MODEL = "fal-ai/bytedance/seedream/v4/edit"
CHRONO_EDIT_MODEL = "fal-ai/chrono-edit"
UPSCALE_MODEL = settings.fal_upscale_model
QUEUE_UPSCALE_MODELS = {
    "fal-ai/recraft/upscale/crisp",
    "fal-ai/recraft/upscale/creative",
    "fal-ai/esrgan",
}
SMART_MERGE_DEFAULT_MODEL = "fal-ai/nano-banana/edit"
SMART_MERGE_DEFAULT_SIZE = "1024x1024"
SMART_MERGE_DEFAULT_ASPECT_RATIO = "1:1"
SMART_MERGE_MAX_IMAGES = 8
FACE_SWAP_MODEL = settings.fal_face_swap_model


def _get_image_size(path: str | Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to read image size from {}: {}", path, exc)
        return None


# Максимальный размер запроса после base64 кодирования (10 МБ лимит)
# Base64 увеличивает размер примерно на 33%, поэтому проверяем размер после кодирования
MAX_REQUEST_SIZE_BYTES = 10 * 1024 * 1024  # 10 МБ
# Максимальный размер файла до base64: 10 МБ / 1.33 ≈ 7.5 МБ
# Используем 4 МБ как безопасный порог для учета других данных в запросе (промпт, параметры, JSON структура и т.д.)
# Это гарантирует, что даже с учетом других данных (промпт ~1-2 КБ, параметры ~1 КБ, JSON структура ~1-2 КБ) 
# запрос не превысит 10 МБ. 4 МБ * 1.33 ≈ 5.3 МБ для изображения + ~4-5 МБ для других данных = ~9-10 МБ
MAX_FILE_SIZE_BEFORE_BASE64 = int(4 * 1024 * 1024)  # 4 МБ


def _compress_image_if_needed(image_path: str | Path) -> Path:
    """
    Сжимает изображение только если его размер после base64 кодирования превысит 10 МБ.
    Base64 увеличивает размер примерно на 33%, поэтому проверяем размер файла * 1.33.
    Возвращает путь к оригинальному файлу, если сжатие не требуется,
    или путь к временному сжатому файлу.
    """
    path = Path(image_path)
    file_size = path.stat().st_size
    
    # Проверяем размер после base64 кодирования (увеличивается на ~33%)
    # Также учитываем, что в запросе есть другие данные (промпт, параметры), поэтому используем более консервативный порог
    estimated_base64_size = file_size * 1.33
    
    # Если размер файла меньше порога или размер после base64 меньше лимита, не сжимаем
    # Используем двойную проверку: размер файла до base64 и размер после base64
    if file_size <= MAX_FILE_SIZE_BEFORE_BASE64 or estimated_base64_size <= MAX_REQUEST_SIZE_BYTES:
        logger.debug("Image {} size {} bytes (file: {:.2f} MB, estimated base64: {:.2f} MB), no compression needed", 
                     path, file_size, file_size / (1024 * 1024), estimated_base64_size / (1024 * 1024))
        return path
    
    file_size_mb = file_size / (1024 * 1024)
    logger.info("Image {} size {:.2f} MB (estimated base64: {:.2f} MB) exceeds {} MB limit, compressing...", 
                path, file_size_mb, estimated_base64_size / (1024 * 1024), MAX_REQUEST_SIZE_BYTES / (1024 * 1024))
    
    try:
        # Открываем изображение
        with Image.open(path) as img:
            # Конвертируем в RGB если нужно (для JPEG)
            if img.mode == "RGBA":
                # Для RGBA создаем белый фон и конвертируем в RGB
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            
            # Создаем временный файл для сжатого изображения
            fd, tmp_name = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            tmp_path = Path(tmp_name)
            
            # Сохраняем с качеством JPEG, постепенно уменьшая качество пока размер не станет меньше 10 МБ
            # Начинаем с более высокого качества для лучшего результата
            quality = 95
            compressed_size = None
            while quality >= 50:
                img.save(tmp_path, "JPEG", quality=quality, optimize=True)
                compressed_size = tmp_path.stat().st_size
                
                # Проверяем размер после base64 кодирования (увеличивается на ~33%)
                estimated_base64_size = compressed_size * 1.33
                
                if estimated_base64_size <= MAX_REQUEST_SIZE_BYTES:
                    logger.info("Image compressed successfully: original {:.2f} MB -> compressed {:.2f} MB (quality={}, estimated base64 size: {:.2f} MB)", 
                               file_size_mb, compressed_size / (1024 * 1024), quality, estimated_base64_size / (1024 * 1024))
                    return tmp_path
                
                quality -= 5
            
            # Если даже с качеством 50 не уложились, пробуем уменьшить размер изображения
            if compressed_size and compressed_size * 1.33 > MAX_REQUEST_SIZE_BYTES:
                logger.warning("Image still too large after compression, resizing...")
                # Уменьшаем размер изображения пропорционально
                original_size = img.size
                # Целевой размер: чтобы base64 был меньше 10 МБ
                # Примерно: если файл 15 МБ, нужно уменьшить на 33%
                scale_factor = (MAX_REQUEST_SIZE_BYTES / (compressed_size * 1.33)) ** 0.5
                new_size = (int(original_size[0] * scale_factor), int(original_size[1] * scale_factor))
                
                img_resized = img.resize(new_size, Image.Resampling.LANCZOS)
                img_resized.save(tmp_path, "JPEG", quality=75, optimize=True)
                compressed_size = tmp_path.stat().st_size
                estimated_base64_size = compressed_size * 1.33
                
                # Проверяем, что после изменения размера размер все еще в пределах лимита
                if estimated_base64_size > MAX_REQUEST_SIZE_BYTES:
                    logger.warning("Image still too large after resize, trying lower quality...")
                    # Пробуем еще более низкое качество
                    for lower_quality in [65, 55, 50]:
                        img_resized.save(tmp_path, "JPEG", quality=lower_quality, optimize=True)
                        compressed_size = tmp_path.stat().st_size
                        estimated_base64_size = compressed_size * 1.33
                        if estimated_base64_size <= MAX_REQUEST_SIZE_BYTES:
                            logger.info("Image compressed with lower quality {}: {}x{} ({:.2f} MB, estimated base64: {:.2f} MB)", 
                                       lower_quality, new_size[0], new_size[1], compressed_size / (1024 * 1024), estimated_base64_size / (1024 * 1024))
                            break
                
                logger.info("Image compressed and resized: original {}x{} ({:.2f} MB) -> {}x{} ({:.2f} MB, estimated base64: {:.2f} MB)", 
                           original_size[0], original_size[1], file_size_mb,
                           new_size[0], new_size[1], compressed_size / (1024 * 1024), estimated_base64_size / (1024 * 1024))
                
                # Финальная проверка: если все еще слишком большое, уменьшаем еще больше
                if estimated_base64_size > MAX_REQUEST_SIZE_BYTES:
                    logger.warning("Image still exceeds limit after all compression attempts, applying aggressive resize...")
                    # Агрессивное уменьшение: уменьшаем до размера, который гарантированно поместится
                    target_base64_size = MAX_REQUEST_SIZE_BYTES * 0.9  # 90% от лимита для запаса
                    target_file_size = target_base64_size / 1.33
                    current_file_size = compressed_size
                    if current_file_size > target_file_size:
                        additional_scale = (target_file_size / current_file_size) ** 0.5
                        final_size = (int(new_size[0] * additional_scale), int(new_size[1] * additional_scale))
                        # Используем уже измененное изображение img_resized
                        img_final = img_resized.resize(final_size, Image.Resampling.LANCZOS)
                        img_final.save(tmp_path, "JPEG", quality=50, optimize=True)
                        final_compressed_size = tmp_path.stat().st_size
                        final_estimated_base64 = final_compressed_size * 1.33
                        logger.info("Aggressive resize applied: {}x{} -> {}x{} ({:.2f} MB, estimated base64: {:.2f} MB)", 
                                   new_size[0], new_size[1], final_size[0], final_size[1], 
                                   final_compressed_size / (1024 * 1024), final_estimated_base64 / (1024 * 1024))
            
            return tmp_path
            
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to compress image {}: {}", path, exc, exc_info=True)
        # В случае ошибки возвращаем оригинальный файл
        return path


def _compress_image_aggressively(image_path: str | Path, target_size_mb: float | None = None) -> Path:
    """
    Применяет очень агрессивное сжатие изображения для уменьшения размера до минимума.
    Используется когда обычное сжатие не помогло.
    
    Args:
        image_path: Путь к изображению
        target_size_mb: Целевой размер файла в МБ (до base64). Если None, используется 2 МБ.
    """
    path = Path(image_path)
    file_size = path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    
    if target_size_mb is None:
        # Целевой размер: 2 МБ до base64 (после base64 ≈ 2.66 МБ)
        # Это оставляет достаточно места для других данных в запросе
        target_size_mb = 2.0
    
    target_size_bytes = int(target_size_mb * 1024 * 1024)
    
    logger.warning("Applying aggressive compression to image {} ({:.2f} MB) -> target: {:.2f} MB", 
                   path, file_size_mb, target_size_mb)
    
    try:
        with Image.open(path) as img:
            # Конвертируем в RGB
            if img.mode == "RGBA":
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[-1])
                img = background
            elif img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGB")
            
            # Создаем временный файл
            fd, tmp_name = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            tmp_path = Path(tmp_name)
            
            original_size = img.size
            
            # Пробуем разные комбинации размера и качества
            # Начинаем с уменьшения до 60% и качества 50
            scale_factors = [0.6, 0.5, 0.4, 0.3]
            qualities = [50, 40, 30]
            
            compressed_size = None
            best_size = None
            best_quality = None
            
            for scale_factor in scale_factors:
                target_size = (int(original_size[0] * scale_factor), int(original_size[1] * scale_factor))
                img_resized = img.resize(target_size, Image.Resampling.LANCZOS)
                
                for quality in qualities:
                    img_resized.save(tmp_path, "JPEG", quality=quality, optimize=True)
                    compressed_size = tmp_path.stat().st_size
                    
                    if compressed_size <= target_size_bytes:
                        logger.info("Aggressive compression applied: {}x{} ({:.2f} MB) -> {}x{} ({:.2f} MB, quality={})", 
                                   original_size[0], original_size[1], file_size_mb,
                                   target_size[0], target_size[1], compressed_size / (1024 * 1024), quality)
                        return tmp_path
                    
                    # Сохраняем лучший вариант
                    if best_size is None or compressed_size < best_size:
                        best_size = compressed_size
                        best_quality = quality
            
            # Если не удалось достичь целевого размера, возвращаем лучший вариант
            if compressed_size is not None:
                logger.warning("Could not reach target size {:.2f} MB, using best compression: {:.2f} MB (quality={})", 
                              target_size_mb, compressed_size / (1024 * 1024), best_quality)
            return tmp_path
            
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to aggressively compress image {}: {}", path, exc, exc_info=True)
        # В случае ошибки возвращаем оригинальный файл
        return path


def _encode_bytes_to_png_data_url(data: bytes) -> str:
    with Image.open(io.BytesIO(data)) as img:
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _encode_file_to_png_data_url(path: str | Path) -> str:
    with open(path, "rb") as file:
        data = file.read()
    return _encode_bytes_to_png_data_url(data)


def _ensure_png_data_url(image_path: str | None = None, image_url: str | None = None) -> str:
    if image_path:
        return _encode_file_to_png_data_url(image_path)
    if not image_url:
        raise ValueError("Image path or image url is required")
    if image_url.startswith("data:"):
        header, _, payload = image_url.partition(",")
        if not payload:
            raise ValueError("Invalid data URL for image")
        try:
            data = base64.b64decode(payload)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Invalid base64 data in image_url") from exc
        return _encode_bytes_to_png_data_url(data)
    try:
        from app.providers.fal.client import _get_http_client
        client = _get_http_client()
        response = client.get(image_url, timeout=30.0)
        response.raise_for_status()
        return _encode_bytes_to_png_data_url(response.content)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to download image from {image_url}") from exc

_MEMORY_PROTOCOL = "memory://"
_CACHE_TTL_SECONDS = 600
_TASK_CACHE: Dict[str, Dict[str, Any]] = {}


class ImageAsset(NamedTuple):
    url: str | None
    content: bytes | None
    filename: str | None


def _purge_cache() -> None:
    if not _TASK_CACHE:
        return
    threshold = time.time() - _CACHE_TTL_SECONDS
    stale = [key for key, value in _TASK_CACHE.items() if value.get("created_at", 0) < threshold]
    for key in stale:
        _TASK_CACHE.pop(key, None)


def _parse_size(size: str | None) -> dict[str, Any]:
    if not size:
        return {}
    size = size.strip()
    if "x" in size:
        try:
            width, height = size.lower().split("x", 1)
            return {"width": int(width), "height": int(height)}
        except ValueError:
            logger.warning("Unable to parse size '{}', sending as image_size", size)
    return {"image_size": size}


def _build_input_payload(prompt: str, options: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"prompt": prompt}
    
    # Получаем модель из options, но не удаляем её сразу, так как она может понадобиться
    model = options.get("model", "")

    # Для Seedream используем image_size как объект с width и height
    if model and "seedream" in model.lower():
        # Seedream принимает image_size как объект: {"width": 1536, "height": 2048}
        # Согласно документации: https://fal.ai/models/bytedance/seedream/v4/text-to-image
        if "width" in options and "height" in options:
            width = options.pop("width")
            height = options.pop("height")
            payload["image_size"] = {
                "width": width,
                "height": height
            }
            logger.info("_build_input_payload: Seedream detected, setting image_size={{width: {}, height: {}}}", 
                       width, height)
        else:
            logger.warning("_build_input_payload: Seedream detected but width/height not found in options! Available keys: {}", list(options.keys()))
        # Удаляем size и aspect_ratio, если они есть, так как Seedream использует image_size
        options.pop("size", None)
        options.pop("aspect_ratio", None)
    # ВРЕМЕННО ОТКЛЮЧЕНО: Flux 2 Pro Edit - проблемы с размерами изображений
    # # Для Flux 2 Pro Edit используем width и height напрямую
    # elif model and "flux-2-pro" in model.lower() and "/edit" in model.lower():
    #     # Flux 2 Pro Edit принимает width и height напрямую
    #     logger.info("_build_input_payload: Flux 2 Pro Edit detected! model='{}', options keys: {}, width={}, height={}", 
    #                model, list(options.keys()), options.get("width"), options.get("height"))
    #     if "width" in options and "height" in options:
    #         width = options.pop("width")
    #         height = options.pop("height")
    #         payload["width"] = width
    #         payload["height"] = height
    #         logger.info("_build_input_payload: Flux 2 Pro Edit - SUCCESSFULLY set width={}, height={} in payload", width, height)
    #     else:
    #         logger.error("_build_input_payload: Flux 2 Pro Edit detected but width/height not found! Available keys: {}, options={}", 
    #                     list(options.keys()), options)
    #     # Удаляем size и aspect_ratio, если они есть
    #     options.pop("size", None)
    #     options.pop("aspect_ratio", None)
    #     logger.info("_build_input_payload: Flux 2 Pro Edit - FINAL payload keys: {}, width={}, height={}", 
    #                list(payload.keys()), payload.get("width"), payload.get("height"))
    # Для Flux 2 Flex используем image_size как enum (portrait_4_3, square, landscape_4_3 и т.д.)
    # или custom размеры через width/height для формата 4:5
    elif model and "flux-2-flex" in model.lower():
        # Flux 2 Flex принимает image_size как enum согласно документации: https://fal.ai/models/fal-ai/flux-2-flex/api
        # Для формата 4:5 используем custom размеры через width/height
        if "width" in options and "height" in options:
            # Custom размеры для формата 4:5
            width = options.pop("width")
            height = options.pop("height")
            payload["image_size"] = {
                "width": width,
                "height": height
            }
            logger.info("_build_input_payload: Flux 2 Flex detected, setting custom image_size={{width: {}, height: {}}}", width, height)
        elif "image_size" in options:
            # Enum значение (square, portrait_4_3, landscape_4_3, portrait_16_9, landscape_16_9)
            payload["image_size"] = options.pop("image_size")
            logger.info("_build_input_payload: Flux 2 Flex detected, setting image_size={}", payload["image_size"])
        # Удаляем size и aspect_ratio, если они есть, так как Flux 2 Flex использует image_size
        options.pop("size", None)
        options.pop("aspect_ratio", None)
    elif "width" in options and "height" in options:
        # Если есть width и height, используем их напрямую (приоритет над size)
        payload["width"] = options.pop("width")
        payload["height"] = options.pop("height")
        # size игнорируем, если уже есть width/height
        options.pop("size", None)
    elif size := options.pop("size", None):
        payload.update(_parse_size(size))

    # ВАЖНО: Если есть aspect_ratio, удаляем image_size для nano-banana
    # чтобы aspect_ratio не переопределялся image_size
    model = options.get("model", "")
    if aspect := options.pop("aspect_ratio", None):
        payload["aspect_ratio"] = aspect
        # Для nano-banana (не pro) удаляем image_size, если он есть
        # так как aspect_ratio должен быть приоритетным
        if "nano-banana" in model.lower() and "pro" not in model.lower():
            options.pop("image_size", None)

    for key in ("negative_prompt", "seed", "cfg_scale", "guidance_scale", "num_inference_steps", "num_images", "output_format", "format", "enhance_prompt_mode", "enable_safety_checker"):
        if key in options and options[key] is not None:
            payload[key] = options.pop(key)

    # Для nano-banana (не pro) удаляем image_size из всех оставшихся options
    # чтобы он не попал в payload через цикл ниже
    if "nano-banana" in model.lower() and "pro" not in model.lower():
        options.pop("image_size", None)

    for key, value in list(options.items()):
        if key.startswith("notify_"):
            continue
        if value is not None:
            payload[key] = options.pop(key)

    return payload


def _encode_file_to_data_url(file_path: str | Path, compress_if_needed: bool = True) -> str:
    """
    Кодирует файл в data URL.
    
    Args:
        file_path: Путь к файлу изображения
        compress_if_needed: Если True, сжимает изображение если оно больше 10 МБ
    """
    path = Path(file_path)
    
    # Сжимаем изображение если нужно (только для файлов больше 10 МБ)
    if compress_if_needed:
        compressed_path = _compress_image_if_needed(path)
        # Если был создан временный файл, используем его и удалим после кодирования
        is_temporary = compressed_path != path
    else:
        compressed_path = path
        is_temporary = False
    
    try:
        content = compressed_path.read_bytes()
        mime_type, _ = mimetypes.guess_type(compressed_path.name)
        if not mime_type:
            mime_type = "image/jpeg" if compressed_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        encoded = base64.b64encode(content).decode("utf-8")
        return f"data:{mime_type};base64,{encoded}"
    finally:
        # Удаляем временный файл если он был создан
        if is_temporary and compressed_path.exists():
            try:
                compressed_path.unlink()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to delete temporary compressed file {}: {}", compressed_path, exc)


def submit_image(prompt: str, **opts: Any) -> str:
    _purge_cache()
    preset = opts.pop("preset", None)
    requested_model = opts.pop("model", None)
    model = get_image_model(requested_model, preset=preset)
    if requested_model and model != requested_model:
        logger.warning("Model '{}' resolved to '{}' via get_image_model", requested_model, model)
    else:
        logger.info("submit_image: using model '{}' (requested: '{}')", model, requested_model)
    # ВАЖНО: Добавляем model обратно в opts для _build_input_payload, чтобы он мог правильно определить модель
    opts["model"] = model
    input_payload = _build_input_payload(prompt, opts)
    input_payload = apply_model_defaults(model, input_payload)
    logger.info("submit_image: final model '{}' with payload keys: {}", model, list(input_payload.keys()))
    if "seedream" in model.lower():
        logger.info("submit_image: Seedream payload - image_size={}, width={}, height={}", 
                   input_payload.get("image_size"), input_payload.get("width"), input_payload.get("height"))
        logger.debug("submit_image: Seedream full payload: {}", input_payload)
    elif "width" in input_payload and "height" in input_payload:
        logger.info("submit_image: image dimensions: {}x{}, num_inference_steps: {}, guidance_scale: {}", 
                   input_payload.get("width"), input_payload.get("height"), 
                   input_payload.get("num_inference_steps"), input_payload.get("guidance_scale"))
    # Логируем полный английский промпт для проверки перевода
    if "prompt" in input_payload:
        logger.info("submit_image: FULL ENGLISH PROMPT: '{}'", input_payload["prompt"])
    logger.debug("submit_image: full payload: {}", input_payload)

    response = queue_submit(model, input_payload)
    logger.debug("fal submit_image_edit response: {}", response)
    task_id = response.get("request_id")
    if not task_id:
        raise RuntimeError("fal queue response did not include request_id")

    _TASK_CACHE[task_id] = {
        "model": model,
        "status": "queued",
        "created_at": time.time(),
        "status_url": response.get("status_url"),
        "response_url": response.get("response_url"),
        "queue_response": response,
    }
    return task_id


def submit_image_edit(image_path: str, prompt: str, mask_path: str | None = None, **opts: Any) -> str:
    _purge_cache()
    preset = opts.pop("preset", None)
    requested_model = opts.pop("model", None)
    model = get_image_model(requested_model, preset=preset)
    
    # ВАЖНО: Добавляем model обратно в opts для _build_input_payload, чтобы он мог правильно определить модель
    opts["model"] = model
    
    # Получаем размеры исходного изображения
    size = _get_image_size(image_path)
    
    # Для Seedream добавляем размеры изображения в opts ПЕРЕД вызовом _build_input_payload
    # чтобы они попали в image_size
    if model == SEEDREAM_MODEL:
        if size:
            width, height = size
            opts["width"] = width
            opts["height"] = height
            logger.info("submit_image_edit: Seedream detected, adding width={}, height={} to opts", width, height)
    # Для Nano Banana edit добавляем aspect_ratio на основе исходного изображения
    elif "nano-banana" in model.lower() and "pro" not in model.lower() and "/edit" in model.lower():
        if size:
            width, height = size
            # Вычисляем aspect_ratio из размеров изображения
            # Находим наибольший общий делитель для упрощения соотношения
            from math import gcd
            gcd_val = gcd(width, height)
            aspect_w = width // gcd_val
            aspect_h = height // gcd_val
            # Ограничиваем значения для упрощения (максимум 21:9, минимум 1:1)
            # Если соотношение слишком большое, используем ближайшее стандартное
            if aspect_w > 21 or aspect_h > 21:
                # Используем стандартные соотношения, поддерживаемые nano-banana
                # Поддерживаемые: 21:9, 16:9, 3:2, 4:3, 5:4, 1:1, 4:5, 3:4, 2:3, 9:16
                source_aspect = width / height
                standard_ratios = [
                    (21, 9), (16, 9), (3, 2), (4, 3), (5, 4),
                    (1, 1), (4, 5), (3, 4), (2, 3), (9, 16)
                ]
                # Находим ближайшее стандартное соотношение
                best_ratio = (1, 1)
                min_diff = float('inf')
                for w, h in standard_ratios:
                    ratio_aspect = w / h
                    diff = abs(source_aspect - ratio_aspect)
                    if diff < min_diff:
                        min_diff = diff
                        best_ratio = (w, h)
                aspect_w, aspect_h = best_ratio
            aspect_ratio = f"{aspect_w}:{aspect_h}"
            opts["aspect_ratio"] = aspect_ratio
            logger.info("submit_image_edit: Nano Banana edit detected, adding aspect_ratio={} (from {}x{}) to opts", 
                       aspect_ratio, width, height)
    
    requires_mask = model_requires_mask(model)
    use_inpaint_fields = model_supports_inpaint_payload(model)
    input_payload = _build_input_payload(prompt, opts)
    input_payload = apply_model_defaults(model, input_payload)
    encoded_image = _encode_file_to_data_url(image_path)
    input_payload["image_url"] = encoded_image
    if use_inpaint_fields:
        input_payload["inpaint_image_url"] = encoded_image
    
    # Для Seedream добавляем image_urls
    if model == SEEDREAM_MODEL:
        input_payload.setdefault("image_urls", [encoded_image])
    
    # Для Flux 2 Pro Edit добавляем image_urls (поддерживает multi-reference editing до 9 изображений)
    if "flux-2-pro" in model.lower() and "/edit" in model.lower():
        input_payload.setdefault("image_urls", [encoded_image])
        logger.info("submit_image_edit: Flux 2 Pro Edit detected, using image_urls for multi-reference editing")
    
    # Для Chrono Edit добавляем только размеры изображения (без image_urls)
    if model == CHRONO_EDIT_MODEL:
        size = _get_image_size(image_path)
        if size:
            width, height = size
            input_payload.setdefault("width", width)
            input_payload.setdefault("height", height)
    
    if model == SEEDREAM_MODEL and mask_path:
        logger.info("Seedream model does not support masks; ignoring provided mask.")
        mask_path = None

    if mask_path and use_inpaint_fields:
        encoded_mask = _encode_file_to_data_url(mask_path)
        input_payload["mask_url"] = encoded_mask
        input_payload["inpaint_mask_url"] = encoded_mask
    elif mask_path and not use_inpaint_fields:
        logger.info("Mask provided for model {} but it does not accept mask payload; ignoring.", model)
    elif requires_mask:
        raise ValueError("mask_path is required for the selected model")

    # Проверяем размер всего payload перед отправкой
    # Для Seedream изображение может быть дублировано в image_url и image_urls
    try:
        payload_json = json.dumps(input_payload)
        payload_size = len(payload_json.encode('utf-8'))
        payload_size_mb = payload_size / (1024 * 1024)
        logger.info("Payload size before submit: {:.2f} MB (limit: {:.2f} MB)", 
                   payload_size_mb, MAX_REQUEST_SIZE_BYTES / (1024 * 1024))
        
        # Если payload превышает лимит, нужно дополнительно сжать изображение
        # Пробуем несколько итераций сжатия, пока размер не станет приемлемым
        max_iterations = 3
        for iteration in range(max_iterations):
            if payload_size <= MAX_REQUEST_SIZE_BYTES:
                break
                
            logger.warning("Payload size {:.2f} MB exceeds limit {:.2f} MB (iteration {}/{}), compressing image...", 
                          payload_size_mb, MAX_REQUEST_SIZE_BYTES / (1024 * 1024), iteration + 1, max_iterations)
            
            # Применяем агрессивное сжатие
            if iteration == 0:
                # Первая итерация: обычное сжатие
                compressed_path = _compress_image_if_needed(image_path)
            else:
                # Последующие итерации: агрессивное сжатие
                compressed_path = _compress_image_aggressively(image_path if iteration == 1 else compressed_path)
            
            # Перекодируем изображение
            encoded_image = _encode_file_to_data_url(compressed_path, compress_if_needed=False)
            input_payload["image_url"] = encoded_image
            if use_inpaint_fields:
                input_payload["inpaint_image_url"] = encoded_image
            if model == SEEDREAM_MODEL:
                input_payload["image_urls"] = [encoded_image]
            
            # Проверяем размер снова
            payload_json = json.dumps(input_payload)
            payload_size = len(payload_json.encode('utf-8'))
            payload_size_mb = payload_size / (1024 * 1024)
            logger.info("Payload size after compression iteration {}: {:.2f} MB", iteration + 1, payload_size_mb)
        
        if payload_size > MAX_REQUEST_SIZE_BYTES:
            logger.error("Payload still too large after {} compression iterations: {:.2f} MB", 
                        max_iterations, payload_size_mb)
            # Все равно пытаемся отправить, но с предупреждением
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to check payload size: {}", exc)

    response = queue_submit(model, input_payload)
    task_id = response.get("request_id")
    if not task_id:
        raise RuntimeError("fal queue response did not include request_id")

    _TASK_CACHE[task_id] = {
        "model": model,
        "status": "queued",
        "created_at": time.time(),
        "status_url": response.get("status_url"),
        "response_url": response.get("response_url"),
        "queue_response": response,
    }
    return task_id


def submit_image_upscale(
    *,
    image_url: str | None = None,
    image_path: str | None = None,
    scale: int = 2,
    **opts: Any,
) -> str:
    _purge_cache()
    if not image_url and not image_path:
        raise ValueError("Either image_url or image_path must be provided for upscaling")

    model_alias = opts.pop("model", UPSCALE_MODEL)
    model = get_image_model(model_alias)

    input_payload: Dict[str, Any] = apply_model_defaults(model, {})

    if model in QUEUE_UPSCALE_MODELS:
        input_payload["image_url"] = _ensure_png_data_url(image_path=image_path, image_url=image_url)
        # For queue models, scale is passed as a separate parameter
        # Always set scale explicitly to ensure it's used
        input_payload["scale"] = scale
        logger.debug("submit_image_upscale: setting scale={} for model {}", scale, model)
    else:
        payload_image_url = (
            _encode_file_to_data_url(image_path) if image_path else image_url  # type: ignore[assignment]
        )
        input_payload["image_url"] = payload_image_url
        input_payload.setdefault("scale", scale)

    # Apply opts AFTER setting defaults, so opts can override defaults
    for key, value in list(opts.items()):
        if key.startswith("notify_") or key.startswith("source_"):
            continue
        if value is not None:
            input_payload[key] = opts.pop(key)

    # Log payload to verify parameters are being sent
    logger.info("submit_image_upscale: sending payload with keys: {}, scale={}, output_format={}", 
                list(input_payload.keys()), 
                input_payload.get("scale"),
                input_payload.get("output_format"))

    response = queue_submit(model, input_payload)
    task_id = response.get("request_id")
    if not task_id:
        raise RuntimeError("fal queue response did not include request_id")

    _TASK_CACHE[task_id] = {
        "model": model,
        "status": "queued",
        "created_at": time.time(),
        "status_url": response.get("status_url"),
        "response_url": response.get("response_url"),
        "queue_response": response,
    }
    return task_id


def run_image_upscale(
    *,
    image_url: str | None = None,
    image_path: str | None = None,
    scale: int = 2,
    **opts: Any,
) -> ImageAsset:
    if not image_url and not image_path:
        raise ValueError("Either image_url or image_path must be provided for upscaling")

    model_alias = opts.pop("model", UPSCALE_MODEL)
    model = get_image_model(model_alias)

    safe_opts: Dict[str, Any] = {}
    for key, value in list(opts.items()):
        if key.startswith("notify_") or key.startswith("source_"):
            continue
        if value is not None:
            safe_opts[key] = opts.pop(key)

    payload = apply_model_defaults(model, {})

    if model in QUEUE_UPSCALE_MODELS:
        payload.update(safe_opts)
        payload["image_url"] = _ensure_png_data_url(image_path=image_path, image_url=image_url)
        payload.setdefault("sync_mode", True)

        result = run_model(model, payload)
        image_result_url = _extract_image_url(result or {})
        filename = None
        if isinstance(result, dict):
            image_info = result.get("image")
            if isinstance(image_info, dict):
                filename = image_info.get("file_name")
        if not image_result_url:
            raise RuntimeError("fal upscale response did not include an image url")
        if image_result_url.startswith("data:"):
            _, _, data_part = image_result_url.partition(",")
            if not data_part:
                raise RuntimeError("Invalid data url received from fal upscale")
            mime = "image/png"
            header = image_result_url.split(",", 1)[0]
            if ":" in header:
                _, mime_part = header.split(":", 1)
                if ";" in mime_part:
                    mime = mime_part.split(";", 1)[0]
                else:
                    mime = mime_part
            ext = "png"
            if "jpeg" in mime or "jpg" in mime:
                ext = "jpg"
            elif "webp" in mime:
                ext = "webp"
            content = base64.b64decode(data_part)
            return ImageAsset(
                url=None,
                content=content,
                filename=filename or f"image.{ext}",
            )
        if image_result_url.startswith(_MEMORY_PROTOCOL):
            b64_data = image_result_url[len(_MEMORY_PROTOCOL) :]
            content = base64.b64decode(b64_data)
            return ImageAsset(url=None, content=content, filename=filename or "image.png")
        return ImageAsset(url=image_result_url, content=None, filename=filename)

    # Fallback synchronous model (e.g., Sima Upscaler)
    payload.setdefault("scale", scale)
    payload.update(safe_opts)
    if image_path:
        payload["image_url"] = _encode_file_to_data_url(image_path)
    elif image_url:
        payload["image_url"] = image_url

    result = run_model(model, payload)
    image_result_url = _extract_image_url(result or {})
    filename = None
    if isinstance(result, dict):
        images = result.get("images") or result.get("result") or result.get("output") or result.get("image")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                filename = first.get("file_name")
        elif isinstance(images, dict):
            filename = images.get("file_name")
    if not image_result_url:
        raise RuntimeError("fal upscale response did not include an image url")
    if image_result_url.startswith(_MEMORY_PROTOCOL):
        b64_data = image_result_url[len(_MEMORY_PROTOCOL) :]
        content = base64.b64decode(b64_data)
        return ImageAsset(url=None, content=content, filename=filename or "image.png")
    return ImageAsset(url=image_result_url, content=None, filename=filename)


def run_image_edit(image_path: str, prompt: str, mask_path: str | None = None, **opts: Any) -> ImageAsset:
    payload_opts = dict(opts)
    preset = payload_opts.pop("preset", None)
    model = get_image_model(payload_opts.pop("model", None), preset=preset)
    requires_mask = model_requires_mask(model)
    use_inpaint_fields = model_supports_inpaint_payload(model)
    # Добавляем модель в payload_opts перед вызовом _build_input_payload, чтобы она была доступна для проверки
    payload_opts["model"] = model
    input_payload = _build_input_payload(prompt, payload_opts)
    input_payload = apply_model_defaults(model, input_payload)
    encoded_image = _encode_file_to_data_url(image_path)
    input_payload["image_url"] = encoded_image
    if use_inpaint_fields:
        input_payload["inpaint_image_url"] = encoded_image
    
    # Для Seedream добавляем image_urls и размеры изображения
    if model == SEEDREAM_MODEL:
        input_payload.setdefault("image_urls", [encoded_image])
        size = _get_image_size(image_path)
        if size:
            width, height = size
            input_payload.setdefault("width", width)
            input_payload.setdefault("height", height)
    
    # Для Chrono Edit добавляем только размеры изображения (без image_urls)
    if model == CHRONO_EDIT_MODEL:
        size = _get_image_size(image_path)
        if size:
            width, height = size
            input_payload.setdefault("width", width)
            input_payload.setdefault("height", height)
    
    # Для Nano Banana edit добавляем aspect_ratio на основе исходного изображения
    # и используем image_urls вместо image_url (как в Smart Merge)
    if "nano-banana" in model.lower() and "pro" not in model.lower() and "/edit" in model.lower():
        size = _get_image_size(image_path)
        if size:
            width, height = size
            # Вычисляем aspect_ratio из размеров изображения
            # ВАЖНО: nano-banana/edit принимает только стандартные значения aspect_ratio:
            # 'auto', '21:9', '16:9', '3:2', '4:3', '5:4', '1:1', '4:5', '3:4', '2:3', '9:16'
            source_aspect = width / height
            standard_ratios = [
                (21, 9, "21:9"), (16, 9, "16:9"), (3, 2, "3:2"), (4, 3, "4:3"), (5, 4, "5:4"),
                (1, 1, "1:1"), (4, 5, "4:5"), (3, 4, "3:4"), (2, 3, "2:3"), (9, 16, "9:16")
            ]
            best_ratio_str = "1:1"
            min_diff = float('inf')
            for w, h, ratio_str in standard_ratios:
                ratio_aspect = w / h
                diff = abs(source_aspect - ratio_aspect)
                if diff < min_diff:
                    min_diff = diff
                    best_ratio_str = ratio_str
            aspect_ratio = best_ratio_str
            input_payload["aspect_ratio"] = aspect_ratio
            # Для nano-banana/edit используем image_urls вместо image_url (как в Smart Merge)
            input_payload["image_urls"] = [encoded_image]
            input_payload.setdefault("image_url", encoded_image)
            logger.info("run_image_edit: Nano Banana edit detected, adding aspect_ratio={} (from {}x{}), using image_urls", 
                       aspect_ratio, width, height)
    
    if mask_path and use_inpaint_fields:
        encoded_mask = _encode_file_to_data_url(mask_path)
        input_payload["mask_url"] = encoded_mask
        input_payload["inpaint_mask_url"] = encoded_mask
    elif mask_path and not use_inpaint_fields:
        logger.info("Mask provided for model {} but it does not accept mask payload; ignoring.", model)
    elif requires_mask:
        raise ValueError("mask_path is required for the selected model")

    result = run_model(model, input_payload)
    image_url = _extract_image_url(result or {})
    filename = None
    if isinstance(result, dict):
        images = result.get("images") or result.get("result") or result.get("output")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                filename = first.get("file_name")
    if not image_url:
        raise RuntimeError("fal synchronous edit response did not include an image url")
    if image_url.startswith(_MEMORY_PROTOCOL):
        b64_data = image_url[len(_MEMORY_PROTOCOL) :]
        content = base64.b64decode(b64_data)
        return ImageAsset(url=None, content=content, filename=filename or "image.png")
    return ImageAsset(url=image_url, content=None, filename=filename)


def submit_smart_merge(
    image_sources: list[dict[str, str | None]],
    prompt: str,
    **opts: Any,
) -> str:
    """Submit smart merge job to queue and return task_id."""
    if not image_sources:
        raise ValueError("At least one image source must be provided for smart merge")

    _purge_cache()
    payload_opts = dict(opts)
    preset = payload_opts.pop("preset", None)
    model_alias = payload_opts.pop("model", None) or SMART_MERGE_DEFAULT_MODEL
    model = get_image_model(model_alias, preset=preset)

    # Если есть width и height, не устанавливаем size по умолчанию
    # (width и height имеют приоритет в _build_input_payload)
    if "width" not in payload_opts or "height" not in payload_opts:
        payload_opts.setdefault("size", SMART_MERGE_DEFAULT_SIZE)
        payload_opts.setdefault("aspect_ratio", SMART_MERGE_DEFAULT_ASPECT_RATIO)

    # Добавляем модель в payload_opts перед вызовом _build_input_payload, чтобы она была доступна для проверки
    payload_opts["model"] = model
    input_payload = _build_input_payload(prompt, payload_opts)
    input_payload = apply_model_defaults(model, input_payload)

    final_urls: list[str] = []
    for source in (image_sources or [])[:SMART_MERGE_MAX_IMAGES]:
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        path = source.get("path")
        if url:
            final_urls.append(url)
        elif path:
            final_urls.append(_encode_file_to_data_url(path))
    if not final_urls:
        raise ValueError("Smart merge requires at least one valid image url or path")

    input_payload["image_urls"] = final_urls
    input_payload.setdefault("image_url", final_urls[0])

    response = queue_submit(model, input_payload)
    logger.debug("fal submit_smart_merge response: {}", response)
    task_id = response.get("request_id")
    if not task_id:
        raise RuntimeError("fal queue response did not include request_id")

    _TASK_CACHE[task_id] = {
        "model": model,
        "status": "queued",
        "created_at": time.time(),
        "status_url": response.get("status_url"),
        "response_url": response.get("response_url"),
        "queue_response": response,
    }
    return task_id


def run_smart_merge(
    image_sources: list[dict[str, str | None]],
    prompt: str,
    **opts: Any,
) -> ImageAsset:
    """Legacy function for backward compatibility. Use submit_smart_merge + check_image_status + resolve_image_asset instead."""
    if not image_sources:
        raise ValueError("At least one image source must be provided for smart merge")

    payload_opts = dict(opts)
    preset = payload_opts.pop("preset", None)
    model_alias = payload_opts.pop("model", None) or SMART_MERGE_DEFAULT_MODEL
    model = get_image_model(model_alias, preset=preset)
    
    # ВРЕМЕННО ОТКЛЮЧЕНО: Flux 2 Pro Edit - проблемы с размерами изображений
    # # КРИТИЧЕСКИ ВАЖНО: Для Flux 2 Pro Edit не устанавливаем дефолтные size и aspect_ratio
    # # если есть width и height (width и height имеют приоритет в _build_input_payload)
    # is_flux2pro = "flux-2-pro" in model.lower() and "/edit" in model.lower()
    # logger.info("run_smart_merge: model='{}', is_flux2pro={}, payload_opts keys: {}, width={}, height={}", 
    #            model, is_flux2pro, list(payload_opts.keys()), payload_opts.get("width"), payload_opts.get("height"))
    # 
    # if is_flux2pro:
    #     # Для Flux 2 Pro Edit не устанавливаем дефолтные значения, если есть width и height
    #     if "width" not in payload_opts or "height" not in payload_opts:
    #         logger.warning("run_smart_merge: Flux 2 Pro Edit detected but width/height not in payload_opts! Available keys: {}", list(payload_opts.keys()))
    # else:
    # Для всех моделей устанавливаем дефолтные значения, если нет width и height
    if "width" not in payload_opts or "height" not in payload_opts:
        payload_opts.setdefault("size", SMART_MERGE_DEFAULT_SIZE)
        payload_opts.setdefault("aspect_ratio", SMART_MERGE_DEFAULT_ASPECT_RATIO)

    # Добавляем модель в payload_opts перед вызовом _build_input_payload, чтобы она была доступна для проверки
    payload_opts["model"] = model
    logger.info("run_smart_merge: BEFORE _build_input_payload - payload_opts keys: {}, width={}, height={}, model={}", 
               list(payload_opts.keys()), payload_opts.get("width"), payload_opts.get("height"), model)
    input_payload = _build_input_payload(prompt, payload_opts)
    logger.info("run_smart_merge: AFTER _build_input_payload - input_payload keys: {}, width={}, height={}", 
               list(input_payload.keys()), input_payload.get("width"), input_payload.get("height"))
    input_payload = apply_model_defaults(model, input_payload)
    logger.info("run_smart_merge: AFTER apply_model_defaults - input_payload keys: {}, width={}, height={}", 
               list(input_payload.keys()), input_payload.get("width"), input_payload.get("height"))

    final_urls: list[str] = []
    for source in (image_sources or [])[:SMART_MERGE_MAX_IMAGES]:
        if not isinstance(source, dict):
            continue
        url = source.get("url")
        path = source.get("path")
        if url:
            final_urls.append(url)
        elif path:
            final_urls.append(_encode_file_to_data_url(path))
    if not final_urls:
        raise ValueError("Smart merge requires at least one valid image url or path")

    # ВРЕМЕННО ОТКЛЮЧЕНО: Flux 2 Pro Edit - проблемы с размерами изображений
    # # Для Flux 2 Pro Edit используем image_urls для multi-reference editing (до 6 референсов)
    # # Для других моделей также используем image_urls, но с image_url как основной
    # if "flux-2-pro" in model.lower() and "/edit" in model.lower():
    #     # Flux 2 Pro Edit поддерживает multi-reference через image_urls (до 6 изображений)
    #     input_payload["image_urls"] = final_urls[:6]  # Ограничиваем до 6 референсов для Flux 2 Pro
    #     # Не устанавливаем image_url отдельно - используем только image_urls для multi-reference
    #     # Добавляем параметр strength для улучшения сходства с референсом (если не задан)
    #     # Максимальное значение strength=1.0 для максимального сходства с референсом
    #     if "strength" not in input_payload:
    #         input_payload["strength"] = 1.0  # Максимальное значение для лучшего сходства с референсом
    #     logger.info("run_smart_merge: Flux 2 Pro Edit detected! model='{}', image_urls count={} (limited to 6), prompt length={}, width={}, height={}, strength={}", 
    #                model, len(final_urls[:6]), len(prompt), input_payload.get("width"), input_payload.get("height"), input_payload.get("strength"))
    #     logger.debug("run_smart_merge: Flux 2 Pro Edit full payload keys: {}", list(input_payload.keys()))
    #     logger.debug("run_smart_merge: Flux 2 Pro Edit image_urls={}", final_urls[:2] if len(final_urls) > 2 else final_urls)
    # else:
    # Для всех моделей используем стандартный подход
    input_payload["image_urls"] = final_urls
    input_payload.setdefault("image_url", final_urls[0])

    result = run_model(model, input_payload)
    image_url = _extract_image_url(result or {})
    filename = None
    if isinstance(result, dict):
        images = result.get("images") or result.get("result") or result.get("output") or result.get("image")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                filename = first.get("file_name")
        elif isinstance(images, dict):
            filename = images.get("file_name")

    if not image_url:
        raise RuntimeError("fal smart merge response did not include an image url")

    if image_url.startswith(_MEMORY_PROTOCOL):
        b64_data = image_url[len(_MEMORY_PROTOCOL) :]
        content = base64.b64decode(b64_data)
        return ImageAsset(url=None, content=content, filename=filename or "image.png")

    return ImageAsset(url=image_url, content=None, filename=filename)


def run_face_swap(
    *,
    source_path: str,
    target_path: str,
    prompt: str | None = None,
    model: str | None = None,
    **opts: Any,
) -> ImageAsset:
    logger.info("run_face_swap called with opts keys: {}", list(opts.keys()))
    if "gender_0" in opts:
        logger.warning("run_face_swap received gender_0={} in opts", opts["gender_0"])
    if "workflow_type" in opts:
        logger.warning("run_face_swap received workflow_type={} in opts", opts["workflow_type"])
    
    payload_opts = dict(opts)
    model_alias = payload_opts.pop("model", None) or model or FACE_SWAP_MODEL
    resolved_model = get_image_model(model_alias)

    # Save valid values before removing invalid ones
    valid_gender = None
    if "gender_0" in payload_opts:
        if payload_opts["gender_0"] in ("male", "female", "non-binary"):
            valid_gender = payload_opts["gender_0"]
        else:
            logger.warning("Invalid gender_0 in opts: {}, will use default", payload_opts["gender_0"])
        payload_opts.pop("gender_0")  # Always remove, we'll set it correctly later
    
    valid_workflow = None
    if "workflow_type" in payload_opts:
        if payload_opts["workflow_type"] in ("user_hair", "target_hair"):
            valid_workflow = payload_opts["workflow_type"]
        else:
            logger.warning("Invalid workflow_type in opts: {}, will use default", payload_opts["workflow_type"])
        payload_opts.pop("workflow_type")  # Always remove, we'll set it correctly later

    payload: Dict[str, Any] = {}
    for key, value in list(payload_opts.items()):
        if key.startswith("notify_"):
            continue
        if value is not None:
            payload[key] = payload_opts.pop(key)

    # Different face swap models may require different field names
    # fal-ai/face-swap uses: base_image_url, swap_image_url
    if "face-swap" in resolved_model.lower():
        payload["base_image_url"] = _encode_file_to_data_url(target_path)  # target is the base image
        payload["swap_image_url"] = _encode_file_to_data_url(source_path)  # source is the face to swap
        # ВАЖНО: fal-ai/face-swap имеет фиксированные ограничения:
        # - Разрешение: 1024x1024 (нельзя изменить через параметры)
        # - Формат: JPEG (нельзя изменить)
        # - Размер файла: ~200-300 КБ
        # Параметры width, height, resolution, size, output_format НЕ ПОДДЕРЖИВАЮТСЯ
        # API игнорирует эти параметры и всегда возвращает 1024x1024 JPEG
        # Для лучшего качества используйте WaveSpeed Face Swap
    else:
        # Other models - try standard field names
        payload["source_image"] = _encode_file_to_data_url(source_path)
        payload["target_image"] = _encode_file_to_data_url(target_path)
    if prompt:
        payload["prompt"] = prompt
    
    payload = apply_model_defaults(resolved_model, payload)
    
    logger.info("Face swap (fal-ai) payload before API: model={}, fields={}, width={}, height={}", 
                 resolved_model, list(payload.keys()), payload.get("width"), payload.get("height"))
    
    result = run_model(resolved_model, payload)
    image_url = _extract_image_url(result or {})
    filename = None
    if isinstance(result, dict):
        images = result.get("images") or result.get("result") or result.get("output") or result.get("image")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                filename = first.get("file_name")
        elif isinstance(images, dict):
            filename = images.get("file_name")

    if not image_url:
        raise RuntimeError("fal face swap response did not include an image url")

    if image_url.startswith(_MEMORY_PROTOCOL):
        b64_data = image_url[len(_MEMORY_PROTOCOL) :]
        content = base64.b64decode(b64_data)
        return ImageAsset(url=None, content=content, filename=filename or "image.png")

    if image_url.startswith("data:"):
        header, _, data_part = image_url.partition(",")
        if not data_part:
            raise RuntimeError("Invalid data url received from face swap model")
        mime = "image/png"
        if ":" in header:
            _, mime_part = header.split(":", 1)
            if ";" in mime_part:
                mime = mime_part.split(";", 1)[0]
            else:
                mime = mime_part
        ext = "png"
        if "jpeg" in mime or "jpg" in mime:
            ext = "jpg"
        content = base64.b64decode(data_part)
        return ImageAsset(url=None, content=content, filename=filename or f"image.{ext}")

    return ImageAsset(url=image_url, content=None, filename=filename)


def submit_face_swap(
    *,
    source_path: str,
    target_path: str,
    prompt: str | None = None,
    model: str | None = None,
    **opts: Any,
) -> str:
    """Submit face swap job to queue API for more reliable processing."""
    _purge_cache()
    payload_opts = dict(opts)
    # Priority: explicit model parameter > model in opts > default
    model_alias = model or payload_opts.pop("model", None) or FACE_SWAP_MODEL
    logger.info("submit_face_swap: using model='{}' (from param={}, from opts={}, default={})", 
               model_alias, model, opts.get("model"), FACE_SWAP_MODEL)
    resolved_model = get_image_model(model_alias)

    # Save valid values before removing invalid ones
    valid_gender = None
    if "gender_0" in payload_opts:
        if payload_opts["gender_0"] in ("male", "female", "non-binary"):
            valid_gender = payload_opts["gender_0"]
        else:
            logger.warning("Invalid gender_0 in opts: {}, will use default", payload_opts["gender_0"])
        payload_opts.pop("gender_0")
    
    valid_workflow = None
    if "workflow_type" in payload_opts:
        if payload_opts["workflow_type"] in ("user_hair", "target_hair"):
            valid_workflow = payload_opts["workflow_type"]
        else:
            logger.warning("Invalid workflow_type in opts: {}, will use default", payload_opts["workflow_type"])
        payload_opts.pop("workflow_type")

    payload: Dict[str, Any] = {}
    for key, value in list(payload_opts.items()):
        if key.startswith("notify_"):
            continue
        if value is not None:
            payload[key] = payload_opts.pop(key)

    # Different face swap models may require different field names
    # fal-ai/face-swap uses: base_image_url, swap_image_url
    if "face-swap" in resolved_model.lower():
        # fal-ai/face-swap uses: base_image_url, swap_image_url
        payload["base_image_url"] = _encode_file_to_data_url(target_path)  # target is the base image
        payload["swap_image_url"] = _encode_file_to_data_url(source_path)  # source is the face to swap
        # Note: fal-ai/face-swap may not support text prompts/instructions
        # According to documentation, it only requires base_image_url and swap_image_url
        # If prompt is provided, we'll try to include it, but it may be ignored by the model
        if prompt:
            # Try common field names for face swap instructions (model may ignore these)
            payload["prompt"] = prompt
            payload["instruction"] = prompt
            payload["description"] = prompt
            logger.debug("Face swap: including prompt in payload (model may ignore it): {}", prompt[:100])
        else:
            logger.debug("Face swap: no prompt provided, using only images")
    else:
        # Other models - try standard field names
        payload["source_image"] = _encode_file_to_data_url(source_path)
        payload["target_image"] = _encode_file_to_data_url(target_path)
        if prompt:
            payload["prompt"] = prompt
    
    payload = apply_model_defaults(resolved_model, payload)
    
    logger.info("Submitting face swap (fal-ai) to queue API: model={}, resolved_model={}, prompt={}, fields={}", 
                 model_alias, resolved_model, prompt[:100] if prompt else "none", list(payload.keys()))
    logger.info("submit_face_swap: FINAL model being sent to Fal.ai API: '{}' (original: '{}')", 
                 resolved_model, model_alias)

    response = queue_submit(resolved_model, payload)
    task_id = response.get("request_id")
    if not task_id:
        raise RuntimeError("fal queue response did not include request_id")

    _TASK_CACHE[task_id] = {
        "model": resolved_model,
        "status": "queued",
        "created_at": time.time(),
        "status_url": response.get("status_url"),
        "response_url": response.get("response_url"),
        "queue_response": response,
    }
    return task_id


def check_status(task_id: str) -> dict[str, Any]:
    _purge_cache()
    entry = _TASK_CACHE.get(task_id)
    if not entry:
        return {"status": "not_found", "result_url": None, "error": "Task not found"}

    status_data: dict[str, Any] | None = None
    api_request_type = None
    if entry.get("status_url"):
        try:
            logger.debug("📡 API REQUEST: GET status_url for task {}: {}", task_id[:8], entry["status_url"][:80])
            status_data = queue_get(entry["status_url"])
            api_request_type = "status_url"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to use cached status_url for {}: {}", task_id, exc)
            status_data = None

    if status_data is None:
        model = entry["model"]
        logger.debug("📡 API REQUEST: queue_status for task {} (model: {})", task_id[:8], model)
        status_data = queue_status(model, task_id)
        api_request_type = "queue_status"
    
    status_raw = str(status_data.get("status", "UNKNOWN")).upper()

    if status_raw in {"COMPLETED", "COMPLETED_WITH_WARNINGS", "SUCCEEDED"}:
        # Логируем только факт успеха, без полного payload для экономии места
        logger.debug("fal status for {} succeeded", task_id)
        entry["status"] = "succeeded"
        entry["result_url"] = status_data.get("response_url") or entry.get("response_url")
        entry["error"] = None
        entry["raw_result"] = status_data
    elif status_raw in {"FAILED", "ERROR"}:
        entry["status"] = "failed"
        entry["error"] = status_data.get("error") or status_data.get("detail")
    else:
        entry["status"] = "processing" if status_raw != "IN_QUEUE" else "queued"
        entry["queue_position"] = status_data.get("queue_position")

    if status_data.get("response_url"):
        entry["response_url"] = status_data["response_url"]
    if status_data.get("status_url"):
        entry["status_url"] = status_data["status_url"]

    result_url = entry.get("result_url") if entry.get("status") == "succeeded" else None

    return {
        "status": entry.get("status", "unknown"),
        "result_url": result_url,
        "error": entry.get("error"),
    }


def _extract_image_url(result: dict[str, Any]) -> str | None:
    for key in ("response", "output", "data", "result"):
        if key in result and isinstance(result[key], dict):
            result = result[key]
            break

    def _extract_from_obj(obj: Any) -> str | None:
        if not isinstance(obj, dict):
            return None
        if b64 := obj.get("images_base64") or obj.get("image_base64") or obj.get("b64"):
            if isinstance(b64, list) and b64:
                return f"{_MEMORY_PROTOCOL}{b64[0]}"
            if isinstance(b64, str):
                return f"{_MEMORY_PROTOCOL}{b64}"
        file_data = obj.get("file_data")
        if isinstance(file_data, str):
            if file_data.startswith("data:"):
                return file_data
            return f"{_MEMORY_PROTOCOL}{file_data}"
        for key in ("image_url", "image", "url", "result_url"):
            value = obj.get(key)
            if isinstance(value, str):
                # Skip queue API endpoints - they are not direct image URLs
                if value.startswith("https://queue.fal.run") or value.startswith("http://queue.fal.run"):
                    logger.debug("_extract_image_url: skipping queue API endpoint: {}", value[:100])
                    continue
                logger.debug("_extract_image_url: found image URL in key '{}': {}", key, value[:100])
                return value
        data_field = obj.get("data")
        if isinstance(data_field, dict):
            candidate = _extract_from_obj(data_field)
            if candidate:
                return candidate
        if isinstance(data_field, list) and data_field:
            for item in data_field:
                candidate = _extract_from_obj(item)
                if candidate:
                    return candidate
        result_field = (
            obj.get("result")
            or obj.get("output")
            or obj.get("images")
            or obj.get("image")
        )
        if isinstance(result_field, dict):
            candidate = _extract_from_obj(result_field)
            if candidate:
                return candidate
        if isinstance(result_field, list):
            for item in result_field:
                if isinstance(item, dict):
                    # Check for 'url' field first (common in fal.ai responses)
                    if "url" in item and isinstance(item["url"], str):
                        return item["url"]
                    candidate = _extract_from_obj(item)
                    if candidate:
                        return candidate
                elif isinstance(item, str):
                    return item
        return None

    if isinstance(result, dict):
        return _extract_from_obj(result)
    return None


def _parse_result_url(result_url: str) -> tuple[str, str] | None:
    try:
        parsed = urlparse(result_url)
    except Exception:  # noqa: BLE001
        return None
    segments = parsed.path.strip("/").split("/")
    if "requests" not in segments:
        return None
    idx = segments.index("requests")
    if idx + 1 >= len(segments):
        return None
    request_id = segments[idx + 1]
    model_path = "/".join(segments[:idx])
    return model_path, request_id


def resolve_result_asset(result_url: str) -> ImageAsset:
    parsed = _parse_result_url(result_url)
    result: dict[str, Any] | None = None
    if parsed:
        parsed_model_path, request_id = parsed
        cache_entry = _TASK_CACHE.get(request_id, {})
        raw_result = cache_entry.get("raw_result")
        result_candidates: list[dict[str, Any]] = []
        
        # ВАЖНО: Для nano-banana/edit используем модель из кэша (полный путь fal-ai/nano-banana/edit)
        # так как URL от Fal.ai содержит только базовый путь fal-ai/nano-banana (без /edit)
        # Fal.ai использует базовый путь модели в URL, а не полный путь с /edit
        cached_model = cache_entry.get("model")
        logger.info("resolve_result_asset: request_id={}, parsed_model_path={}, cached_model={}, cache_keys={}", 
                   request_id, parsed_model_path, cached_model, list(cache_entry.keys()) if cache_entry else "no cache")
        
        # Определяем правильный путь модели для использования
        if cached_model and "nano-banana" in cached_model.lower() and "/edit" in cached_model.lower():
            # Для nano-banana/edit ВСЕГДА используем cached_model, так как parsed_model_path не содержит /edit
            model_path = cached_model
            logger.info("resolve_result_asset: Using cached model {} instead of parsed {} for nano-banana/edit", 
                       cached_model, parsed_model_path)
        else:
            # Для других моделей используем стандартную функцию
            from app.providers.fal.client import _base_model_path
            model_path = parsed_model_path
            base_model_path = _base_model_path(model_path)
            if base_model_path != model_path:
                logger.debug("Using base model path {} instead of {} for result retrieval (subpath removed per Fal.ai docs)", base_model_path, model_path)
                model_path = base_model_path

        # Для nano-banana/edit и nano-banana-pro/edit используем queue_result с базовым путем (без /edit),
        # как для обычного nano-banana и nano-banana-pro в кнопке "Создать"
        if cached_model and "nano-banana" in cached_model.lower() and "/edit" in cached_model.lower():
            # Определяем базовый путь в зависимости от модели
            # ВАЖНО: проверяем "nano-banana-pro" ПЕРЕД "nano-banana", чтобы правильно определить модель
            if "nano-banana-pro" in cached_model.lower():
                base_model_for_result = "fal-ai/nano-banana-pro"
                model_type = "nano-banana-pro/edit"
            else:
                base_model_for_result = "fal-ai/nano-banana"
                model_type = "nano-banana/edit"
            
            logger.info("resolve_result_asset: Using check_status for {} (base_model={}, cached_model={}, request_id={})", 
                       model_type, base_model_for_result, cached_model, request_id)
            try:
                # Для nano-banana/edit используем check_status (который использует правильный endpoint)
                # вместо queue_status или queue_result
                # check_status использует правильный путь для получения статуса с результатом
                # Для nano-banana/edit используем raw_result из кэша напрямую
                # check_status возвращает только {'status': 'COMPLETED', 'result_url': '...', 'error': None}
                # но raw_result содержит полный ответ от queue_status с base64 данными изображения
                cache_entry = _TASK_CACHE.get(request_id, {})
                raw_result = cache_entry.get("raw_result")
                result_image_url = None
                
                if raw_result:
                    logger.info("resolve_result_asset: Checking raw_result from cache for {}: keys={}", model_type, list(raw_result.keys()) if isinstance(raw_result, dict) else "not a dict")
                    # Проверяем все возможные поля в raw_result
                    result_image_url = _extract_image_url(raw_result)
                    if result_image_url:
                        result_candidates.append(raw_result)
                        logger.info("resolve_result_asset: Extracted image URL from raw_result: {}", result_image_url[:100] if len(result_image_url) > 100 else result_image_url)
                    else:
                        # Если _extract_image_url не нашел, проверяем напрямую поле "data"
                        if isinstance(raw_result, dict):
                            data_field = raw_result.get("data")
                            if isinstance(data_field, str) and data_field.startswith("data:image"):
                                result_image_url = data_field
                                result_candidates.append(raw_result)
                                logger.info("resolve_result_asset: Found data URL in raw_result['data'] field")
                            # Также проверяем другие возможные поля
                            for key in ["image", "result", "output", "images"]:
                                value = raw_result.get(key)
                                if isinstance(value, str) and value.startswith("data:image"):
                                    result_image_url = value
                                    result_candidates.append(raw_result)
                                    logger.info("resolve_result_asset: Found data URL in raw_result['{}'] field", key)
                                    break
                
                # Если не нашли в raw_result, пробуем check_status
                if not result_image_url:
                    status_data = check_status(request_id)
                    logger.info("resolve_result_asset: Got status data for {}: keys={}", model_type, list(status_data.keys()) if isinstance(status_data, dict) else "not a dict")
                    result_image_url = _extract_image_url(status_data)
                    if result_image_url:
                        result_candidates.append(status_data)
                        logger.info("resolve_result_asset: Extracted image URL from status data: {}", result_image_url[:100] if len(result_image_url) > 100 else result_image_url)
                
                # Если все еще нет URL, пробуем использовать queue_get для response_url
                if not result_image_url:
                    logger.warning("resolve_result_asset: No image URL found in raw_result or status data for {}. Trying queue_get for response_url", model_type)
                    # Берем response_url из raw_result или кэша
                    response_url = None
                    if raw_result and isinstance(raw_result, dict):
                        response_url = raw_result.get("response_url")
                    if not response_url:
                        response_url = cache_entry.get("response_url")
                    
                    if response_url and response_url.startswith("http"):
                        logger.info("resolve_result_asset: Trying queue_get for response_url: {}", response_url[:100])
                        from app.providers.fal.client import queue_get
                        try:
                            result_data = queue_get(response_url)
                            logger.info("resolve_result_asset: Got result from queue_get: keys={}", list(result_data.keys()) if isinstance(result_data, dict) else "not a dict")
                            result_image_url = _extract_image_url(result_data)
                            if result_image_url:
                                result_candidates.append(result_data)
                                logger.info("resolve_result_asset: Extracted image URL from queue_get result: {}", result_image_url[:100] if len(result_image_url) > 100 else result_image_url)
                        except Exception as queue_get_exc:  # noqa: BLE001
                            logger.warning("resolve_result_asset: queue_get failed for {}: {}", response_url[:100], queue_get_exc)
            except Exception as result_exc:  # noqa: BLE001
                logger.error("resolve_result_asset: Failed to get status for {}: {}", model_type, result_exc, exc_info=True)
        # Для Flux 2 Flex пробуем несколько способов получения результата
        elif cached_model and "flux-2-flex" in cached_model.lower():
            logger.info("resolve_result_asset: Using multiple methods for flux-2-flex (request_id={}, model_path={})", request_id, model_path)
            try:
                # Сначала пробуем queue_result (как для других моделей)
                try:
                    logger.info("resolve_result_asset: Trying queue_result for flux-2-flex")
                    result_data = queue_result(model_path, request_id)
                    logger.info("resolve_result_asset: Got result from queue_result for flux-2-flex: keys={}, full_result={}", 
                               list(result_data.keys()) if isinstance(result_data, dict) else "not a dict",
                               str(result_data)[:500] if isinstance(result_data, dict) else str(result_data)[:500])
                    result_candidates.append(result_data)
                except Exception as queue_result_exc:  # noqa: BLE001
                    logger.warning("resolve_result_asset: queue_result failed for flux-2-flex: {}", queue_result_exc)
                
                # Также пробуем queue_status и queue_get
                try:
                    status_data = queue_status(model_path, request_id)
                    logger.info("resolve_result_asset: Got status data for flux-2-flex: keys={}, status={}", 
                               list(status_data.keys()) if isinstance(status_data, dict) else "not a dict",
                               status_data.get("status") if isinstance(status_data, dict) else "N/A")
                    
                    # Проверяем, есть ли ошибка в статусе (например, content policy violation)
                    if isinstance(status_data, dict):
                        error_info = status_data.get("error")
                        if error_info:
                            logger.warning("resolve_result_asset: Flux 2 Flex request has error in status: {}", error_info)
                            # Если есть ошибка, пробуем извлечь информацию об ошибке
                            if isinstance(error_info, dict) and error_info.get("type") == "content_policy_violation":
                                raise RuntimeError(f"Content policy violation: {error_info.get('msg', 'Request rejected by content checker')}")
                    
                    # Добавляем status_data в candidates для извлечения URL
                    result_candidates.append(status_data)
                    
                    # Извлекаем response_url из статуса и пробуем получить результат
                    response_url = status_data.get("response_url")
                    if response_url and response_url.startswith("http"):
                        logger.info("resolve_result_asset: Trying queue_get for flux-2-flex response_url: {}", response_url[:100])
                        try:
                            # Импортируем queue_get здесь, чтобы избежать ошибки импорта
                            from app.providers.fal.client import queue_get as get_queue_result
                            result_data = get_queue_result(response_url)
                            logger.info("resolve_result_asset: Got result from queue_get for flux-2-flex: keys={}, full_result={}", 
                                       list(result_data.keys()) if isinstance(result_data, dict) else "not a dict",
                                       str(result_data)[:500] if isinstance(result_data, dict) else str(result_data)[:500])
                            # Добавляем result_data в candidates для извлечения URL
                            result_candidates.append(result_data)
                            
                            # Дополнительно проверяем, есть ли image URL напрямую в result_data
                            if isinstance(result_data, dict):
                                # Проверяем все возможные поля для image URL
                                for key in ["image", "images", "output", "result", "data", "image_url", "url"]:
                                    value = result_data.get(key)
                                    if value:
                                        logger.info("resolve_result_asset: Found field '{}' in result_data: type={}, value_preview={}", 
                                                   key, type(value).__name__, str(value)[:200] if isinstance(value, (str, dict, list)) else value)
                        except Exception as queue_get_exc:  # noqa: BLE001
                            # Проверяем, не является ли это ошибкой 422 (content policy violation)
                            error_str = str(queue_get_exc)
                            if "422" in error_str or "content_policy_violation" in error_str.lower() or "content checker" in error_str.lower():
                                logger.error("resolve_result_asset: Flux 2 Flex request rejected by content policy. This means the image was not generated.")
                                raise RuntimeError("Content policy violation: Request was rejected by Fal.ai content checker")
                            logger.warning("resolve_result_asset: queue_get failed for flux-2-flex response_url: {}", queue_get_exc, exc_info=True)
                except Exception as status_exc:  # noqa: BLE001
                    logger.warning("resolve_result_asset: queue_status failed for flux-2-flex: {}", status_exc)
                    # Если это RuntimeError о content policy violation, пробрасываем его дальше
                    if isinstance(status_exc, RuntimeError) and "content policy" in str(status_exc).lower():
                        raise
                
                # Также проверяем raw_result из кэша
                raw_result = cache_entry.get("raw_result")
                if raw_result:
                    logger.info("resolve_result_asset: Adding raw_result to candidates for flux-2-flex: keys={}, full_raw_result={}", 
                               list(raw_result.keys()) if isinstance(raw_result, dict) else "not a dict",
                               str(raw_result)[:500] if isinstance(raw_result, dict) else str(raw_result)[:500])
                    result_candidates.append(raw_result)
            except Exception as result_exc:  # noqa: BLE001
                logger.error("resolve_result_asset: Failed to get result for flux-2-flex: {}", result_exc, exc_info=True)
                # Если это RuntimeError о content policy violation, пробрасываем его дальше
                if isinstance(result_exc, RuntimeError) and "content policy" in str(result_exc).lower():
                    raise
        else:
            # Для других моделей используем queue_result
            attempts = 0
            max_attempts = 3  # Уменьшено с 5 до 3 - обычно результат получается с первой попытки
            delay = 0.3
            last_error: Exception | None = None
            # Используем путь модели для получения результата
            current_model_path = model_path
            
            logger.debug("📡 API REQUEST: resolve_result_asset starting for {} (max_attempts: {})", request_id[:8], max_attempts)
            while attempts < max_attempts:
                try:
                    logger.debug("📡 API REQUEST: queue_result attempt {}/{} for {} (model: {})", 
                               attempts + 1, max_attempts, request_id[:8], current_model_path)
                    response_payload = queue_result(current_model_path, request_id)
                    # Логируем только ключи, не весь payload для экономии места в логах
                    logger.info("📡 API RESPONSE: queue_result for {} succeeded on attempt {}: payload keys: {}", 
                               request_id[:8], attempts + 1, list(response_payload.keys()) if isinstance(response_payload, dict) else "not a dict")
                    result_candidates.append(response_payload)
                    break
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status_code = exc.response.status_code
                    # Retry on server errors (500, 502, 503)
                    if status_code in (500, 502, 503) and attempts < max_attempts - 1:
                        logger.warning(
                            "resolve_result_asset {} attempt {} failed with {}: {}. Retrying in {:.1f}s",
                            request_id,
                            attempts + 1,
                            status_code,
                            exc.response.text[:100] if hasattr(exc.response, 'text') else str(exc),
                            delay,
                        )
                        attempts += 1
                        time.sleep(delay)
                        delay *= 2
                        continue
                    if exc.response.status_code in {404, 405}:
                        # Для других моделей пробуем использовать модель из кэша
                        cached_model = cache_entry.get("model")
                        if cached_model and cached_model != current_model_path:
                            logger.debug(
                                "Retrying queue_result for {} using cached model {} due to {}",
                                request_id,
                                cached_model,
                                exc.response.status_code,
                            )
                            current_model_path = cached_model
                        else:
                            logger.debug(
                                "queue_result for {} still returning {}. Will retry after {:.1f}s",
                                request_id,
                                exc.response.status_code,
                                delay,
                            )
                        time.sleep(delay)
                        attempts += 1
                        delay *= 1.5
                        continue
                    # Для 422 не ретраим - это означает, что endpoint не поддерживается для этой модели
                    if exc.response.status_code == 422:
                        logger.debug("queue_result returned 422 for {}, endpoint not supported", request_id)
                        break
                    raise
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    time.sleep(delay)
                    attempts += 1
                    delay *= 1.5
            else:
                if last_error:
                    logger.debug("queue_result attempts exhausted for {}: {}", request_id, last_error)

        # Добавляем raw_result и queue_response в candidates
        # Для nano-banana/edit результат может быть в queue_response из первоначального ответа
        queue_response = cache_entry.get("queue_response")
        if queue_response:
            logger.info("resolve_result_asset: Adding queue_response to candidates. queue_response keys: {}", 
                       list(queue_response.keys()) if isinstance(queue_response, dict) else "not a dict")
            # Для nano-banana/edit логируем первые 2000 символов queue_response для отладки
            if cached_model and "nano-banana" in cached_model.lower() and "/edit" in cached_model.lower():
                logger.debug("resolve_result_asset: queue_response content (first 2000 chars): {}", str(queue_response)[:2000])
            result_candidates.append(queue_response)
        
        if raw_result:
            logger.info("resolve_result_asset: Adding raw_result to candidates. raw_result keys: {}, type: {}", 
                       list(raw_result.keys()) if isinstance(raw_result, dict) else "not a dict",
                       type(raw_result).__name__)
            # Логируем первые 1000 символов raw_result для nano-banana/edit
            if cached_model and "nano-banana" in cached_model.lower() and "/edit" in cached_model.lower():
                logger.debug("resolve_result_asset: raw_result content (first 1000 chars): {}", str(raw_result)[:1000])
            result_candidates.append(raw_result)

        result = None
        image_url = None
        logger.info("resolve_result_asset: Checking {} candidates for image URL", len(result_candidates))
        for idx, candidate in enumerate(result_candidates):
            candidate_type = type(candidate).__name__
            candidate_keys = list(candidate.keys()) if isinstance(candidate, dict) else "not a dict"
            logger.info("resolve_result_asset: Checking candidate {}: type={}, keys={}", idx + 1, candidate_type, candidate_keys)
            # Для Flux 2 Flex добавляем детальное логирование
            if cached_model and "flux-2-flex" in cached_model.lower():
                logger.info("resolve_result_asset: Flux 2 Flex candidate {} full content: {}", idx + 1, str(candidate)[:1000] if isinstance(candidate, dict) else str(candidate)[:1000])
            image_url = _extract_image_url(candidate or {})
            if image_url:
                result = candidate
                logger.info("resolve_result_asset: Found image URL in candidate {}: {} (length: {})", 
                           idx + 1, image_url[:100] if len(image_url) > 100 else image_url, len(image_url))
                break
            else:
                logger.warning("resolve_result_asset: No image URL found in candidate {} (type={}, keys={})", 
                             idx + 1, candidate_type, candidate_keys)

        # Если не удалось извлечь URL из результата, попробуем использовать response_url напрямую
        # НО: для nano-banana/edit мы уже обработали его в блоке выше (строки 1316-1374)
        # Если там не нашли результат, значит его нет в статусе, и нужно использовать другой подход
        if result is None and result_url and result_url.startswith("http"):
            # Для nano-banana/edit мы уже обработали response_url в блоке выше
            # Если результат не найден, значит его нет в статусе, и нужно использовать другой подход
            if cached_model and "nano-banana" in cached_model.lower() and "/edit" in cached_model.lower():
                # Для nano-banana/edit результат должен быть в статусе или response_url
                # Если мы здесь, значит результат не найден - это ошибка
                logger.debug("nano-banana/edit result not found in status or response_url - this should not happen")
            else:
                logger.debug("Trying to fetch result from response_url using queue_get: {}", result_url)
                try:
                    # Используем queue_get, который уже использует правильные заголовки авторизации
                    from app.providers.fal.client import queue_get
                    response_data = queue_get(result_url)
                    logger.debug("Got response data from response_url: {}", response_data)
                    candidate_url = _extract_image_url(response_data)
                    if candidate_url:
                        image_url = candidate_url
                        result = response_data
                        logger.debug("Extracted image URL from response_url: {}", image_url)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Failed to fetch from response_url: {}", exc)

        if result is None:
            logger.error("fal response missing image url after checking candidates: {}", result_candidates)
        else:
            if request_id in _TASK_CACHE:
                _TASK_CACHE[request_id]["image_url"] = image_url or result_url
    else:
        logger.warning("Unable to parse fal result URL {}, returning as remote asset", result_url)
        return ImageAsset(url=result_url, content=None, filename=None)

    image_url = _extract_image_url(result or {})
    if not image_url:
        # Последняя попытка: использовать result_url напрямую только если это похоже на CDN URL
        if result_url and result_url.startswith("http"):
            # Не используем result_url как fallback, если это не CDN URL (queue API endpoints не работают напрямую)
            if "cdn.fal.ai" not in result_url and "storage.googleapis.com" not in result_url:
                logger.warning("result_url does not look like a CDN URL, cannot use as fallback: {}", result_url)
                raise RuntimeError("fal response did not include an image url")
            else:
                logger.debug("Using result_url as fallback image URL: {}", result_url)
                image_url = result_url
        else:
            raise RuntimeError("fal response did not include an image url")
    file_name = None
    if isinstance(result, dict):
        images = result.get("images") or result.get("result") or result.get("output")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, dict):
                file_name = first.get("file_name")

    if not image_url:
        raise RuntimeError("fal response did not include an image url")

    if image_url.startswith(_MEMORY_PROTOCOL):
        b64_data = image_url[len(_MEMORY_PROTOCOL) :]
        content = base64.b64decode(b64_data)
        return ImageAsset(url=None, content=content, filename=file_name or "image.png")

    return ImageAsset(url=image_url, content=None, filename=file_name)

