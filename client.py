"""
WaveSpeedAI API клиент для face swap.
"""
import os
import time
from typing import Any, Dict
from loguru import logger
import httpx
from PIL import Image


def wavespeed_face_swap(source_path: str, face_path: str, model: str | None = None) -> str:
    """
    Делает face swap через WaveSpeedAI и возвращает URL или локальный путь результата.
    
    Args:
        source_path: Путь к базовому изображению (куда вставляем лицо)
        face_path: Путь к изображению с лицом (откуда берем лицо)
        model: Имя модели (например, "akool/image-face-swap"). Если не указано, берется из настроек.
    
    Returns:
        URL результата или путь к файлу
    
    Raises:
        RuntimeError: Если произошла ошибка при обработке
    """
    # Пробуем получить API ключ из переменных окружения или из настроек
    api_key = os.getenv("WAVESPEED_API_KEY")
    if not api_key:
        try:
            from app.core.config import settings
            api_key = settings.wavespeed_api_key
        except Exception:
            pass
    if not api_key:
        raise RuntimeError("WAVESPEED_API_KEY не установлен в переменных окружения или настройках")
    
    # Получаем имя модели из настроек, если не указано
    if not model:
        try:
            from app.core.config import reload_settings
            current_settings = reload_settings()  # Используем reload_settings для получения актуальных настроек
            model = current_settings.wavespeed_face_swap_model
            logger.info("Using model from settings: {}", model)
        except Exception as e:
            logger.warning("Failed to load model from settings: {}, using default", e)
            model = "wavespeed-ai/image-head-swap"  # Значение по умолчанию
    
    base_url = "https://api.wavespeed.ai/api/v3"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    
    try:
        # Шаг 1: Загружаем изображения
        logger.info("Uploading images to WaveSpeedAI...")
        
        with httpx.Client(timeout=60.0) as client:
            # Проверяем размер изображений для диагностики
            try:
                with Image.open(source_path) as img:
                    source_size = img.size
                    logger.info("Source image size: {}x{} pixels", source_size[0], source_size[1])
            except Exception as e:
                logger.warning("Could not read source image size: {}", e)
            
            try:
                with Image.open(face_path) as img:
                    face_size = img.size
                    logger.info("Face image size: {}x{} pixels", face_size[0], face_size[1])
            except Exception as e:
                logger.warning("Could not read face image size: {}", e)
            
            # Загружаем source image
            with open(source_path, "rb") as f:
                source_data = f.read()
            
            upload_response = client.post(
                f"{base_url}/media/upload/binary",
                headers=headers,
                files={"file": (os.path.basename(source_path), source_data, "image/jpeg")},
            )
            upload_response.raise_for_status()
            upload_data = upload_response.json()
            # WaveSpeedAI возвращает {"code": 200, "message": "success", "data": {"download_url": "..."}}
            if upload_data.get("code") == 200 and upload_data.get("data"):
                source_url = upload_data["data"].get("download_url")
            else:
                # Fallback на старый формат
                source_url = upload_data.get("url")
            if not source_url:
                raise RuntimeError(f"Не удалось получить URL для загруженного изображения: {upload_response.text}")
            logger.info("Source image uploaded: {}", source_url[:50])
            
            # Загружаем face image
            with open(face_path, "rb") as f:
                face_data = f.read()
            
            upload_response = client.post(
                f"{base_url}/media/upload/binary",
                headers=headers,
                files={"file": (os.path.basename(face_path), face_data, "image/jpeg")},
            )
            upload_response.raise_for_status()
            upload_data = upload_response.json()
            # WaveSpeedAI возвращает {"code": 200, "message": "success", "data": {"download_url": "..."}}
            if upload_data.get("code") == 200 and upload_data.get("data"):
                face_url = upload_data["data"].get("download_url")
            else:
                # Fallback на старый формат
                face_url = upload_data.get("url")
            if not face_url:
                raise RuntimeError(f"Не удалось получить URL для загруженного изображения лица: {upload_response.text}")
            logger.info("Face image uploaded: {}", face_url[:50])
            
            # Шаг 2: Вызываем модель face swap
            logger.info("Calling WaveSpeedAI face swap model...")
            logger.info("WaveSpeedAI params: target={} (target), source={} (source)", source_url[:50], face_url[:50])
            
            # Определяем параметры в зависимости от модели
            # Согласно документации WaveSpeedAI:
            # - wavespeed-ai/image-head-swap: image, face_image, output_format, enable_sync_mode (заменяет ВСЮ голову для лучшего сходства)
            # - wavespeed-ai/image-face-swap-pro: image, face_image, target_index (опционально), output_format, enable_sync_mode
            # - wavespeed-ai/image-face-swap: image, face_image, target_index (опционально), output_format, enable_sync_mode
            # - akool/image-face-swap: image, source_image (массив), target_image (массив), face_enhance, output_format, enable_sync_mode
            if "akool" in model.lower():
                request_params = {
                    "image": source_url,  # Целевое изображение (куда вставляем лицо)
                    "source_image": [face_url],  # Исходное изображение (откуда берем лицо) - массив
                    "target_image": [source_url],  # Целевое изображение (куда вставляем лицо) - массив
                    "enable_sync_mode": True,  # Синхронный режим - ждем результат сразу
                    "output_format": "png",  # Используем PNG для максимального качества
                    "face_enhance": True,  # Улучшение лица для лучшего сходства (boolean)
                }
            elif "head-swap" in model.lower():
                # Для wavespeed-ai/image-head-swap - заменяет ВСЮ голову (лицо + волосы + контур)
                # Это может дать лучшее сходство, так как заменяется вся голова целиком
                # Параметры согласно документации: image, face_image, output_format, enable_sync_mode
                request_params = {
                    "image": source_url,  # Целевое изображение (куда вставляем голову)
                    "face_image": face_url,  # Исходное изображение (откуда берем голову) - ЭТО ГОЛОВА ДЛЯ ВСТАВКИ
                    "enable_sync_mode": True,  # Синхронный режим - ждем результат сразу
                    "output_format": "png",  # Используем PNG для максимального качества
                }
            elif "face-swap-pro" in model.lower() or "wavespeed-ai" in model.lower():
                # Для wavespeed-ai/image-face-swap-pro и wavespeed-ai/image-face-swap
                # Pro версия использует передовые алгоритмы для лучшего сходства
                # Важно: image = куда вставляем лицо, face_image = откуда берем лицо
                request_params = {
                    "image": source_url,  # Целевое изображение (куда вставляем лицо)
                    "face_image": face_url,  # Исходное изображение (откуда берем лицо) - ЭТО ЛИЦО ДЛЯ ВСТАВКИ
                    "enable_sync_mode": True,  # Синхронный режим - ждем результат сразу
                    "output_format": "png",  # Используем PNG для максимального качества (Pro версия поддерживает)
                    "target_index": 0,  # Индекс лица для замены (0 = самое крупное лицо)
                }
            else:
                # Fallback для других моделей
                request_params = {
                    "image": source_url,
                    "face_image": face_url,
                    "enable_sync_mode": True,
                    "output_format": "png",
                }
            logger.debug("WaveSpeedAI request params: {}", {k: (v[:50] + "..." if isinstance(v, str) and len(v) > 50 else v) for k, v in request_params.items()})
            
            predict_response = client.post(
                f"{base_url}/{model}",
                headers={**headers, "Content-Type": "application/json"},
                json=request_params,
            )
            predict_response.raise_for_status()
            predict_data = predict_response.json()
            
            # WaveSpeedAI возвращает {"code": 200, "data": {...}}
            if predict_data.get("code") == 200 and predict_data.get("data"):
                data = predict_data["data"]
                status = data.get("status")
                
                # Если синхронный режим, результат должен быть сразу
                if status == "completed":
                    outputs = data.get("outputs", [])
                    if outputs and len(outputs) > 0:
                        result_url = outputs[0]  # Берем первый URL из массива
                        logger.info("WaveSpeedAI face swap completed (sync): {}", result_url[:50])
                        return result_url
                    else:
                        raise RuntimeError(f"Статус completed, но outputs пуст: {data}")
                
                # Если асинхронный режим, делаем polling
                request_id = data.get("id")  # В WaveSpeedAI используется "id" вместо "requestId"
                if not request_id:
                    raise RuntimeError(f"Не удалось получить id из ответа: {predict_data}")
            else:
                # Fallback на старый формат
                if predict_data.get("status") == "completed" and predict_data.get("output"):
                    result_url = predict_data["output"]
                    logger.info("WaveSpeedAI face swap completed: {}", result_url[:50])
                    return result_url
                
                request_id = predict_data.get("requestId") or predict_data.get("id")
                if not request_id:
                    raise RuntimeError(f"Не удалось получить requestId/id из ответа: {predict_data}")
            
            logger.info("WaveSpeedAI face swap started (async), requestId: {}", request_id)
            
            # Polling результата
            max_attempts = 30  # Максимум 30 попыток
            poll_interval = 2  # 2 секунды между попытками
            
            for attempt in range(max_attempts):
                time.sleep(poll_interval)
                
                result_response = client.get(
                    f"{base_url}/predictions/{request_id}/result",
                    headers=headers,
                )
                result_response.raise_for_status()
                result_data = result_response.json()
                
                # WaveSpeedAI может возвращать данные в разных форматах
                # Проверяем структуру ответа
                if result_data.get("code") == 200 and result_data.get("data"):
                    # Новый формат: {"code": 200, "data": {...}}
                    data = result_data["data"]
                    status = data.get("status")
                    logger.debug("WaveSpeedAI prediction status (from data): {} (attempt {}/{})", status, attempt + 1, max_attempts)
                    if status == "completed":
                        outputs = data.get("outputs", [])
                        if outputs and len(outputs) > 0:
                            result_url = outputs[0]
                            logger.info("WaveSpeedAI face swap completed: {}", result_url[:50])
                            return result_url
                        else:
                            logger.debug("WaveSpeedAI response data: {}", data)
                else:
                    # Старый формат или другой формат
                    status = result_data.get("status")
                    logger.debug("WaveSpeedAI prediction status: {} (attempt {}/{})", status, attempt + 1, max_attempts)
                    if status is None:
                        logger.debug("WaveSpeedAI full response: {}", result_data)
                
                if status == "completed":
                    output = result_data.get("output")
                    if output:
                        logger.info("WaveSpeedAI face swap completed: {}", output[:50] if isinstance(output, str) else "output received")
                        return output if isinstance(output, str) else str(output)
                    else:
                        raise RuntimeError(f"Статус completed, но output отсутствует: {result_data}")
                
                if status == "failed":
                    error = result_data.get("error", "Unknown error")
                    raise RuntimeError(f"WaveSpeedAI face swap failed: {error}")
            
            raise RuntimeError(f"WaveSpeedAI face swap timeout после {max_attempts} попыток")
            
    except httpx.HTTPStatusError as e:
        error_text = e.response.text if e.response else str(e)
        logger.error("WaveSpeedAI HTTP error: {} - {}", e.response.status_code if e.response else "unknown", error_text)
        raise RuntimeError(f"WaveSpeedAI API error: {e.response.status_code if e.response else 'unknown'} - {error_text[:200]}") from e
    except Exception as e:
        logger.error("WaveSpeedAI face swap error: {}", e)
        raise RuntimeError(f"WaveSpeedAI face swap failed: {e}") from e

