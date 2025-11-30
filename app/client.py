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


def wavespeed_designer_text(image_path: str, prompt: str, model: str | None = None) -> str:
    """
    Добавляет дизайнерский текст на изображение через WaveSpeedAI (Ideogram 3 или FLUX Kontext).
    
    Args:
        image_path: Путь к исходному изображению
        prompt: Промпт для модели (англоязычный, описывающий где и какой текст добавить)
        model: Имя модели (например, "ideogram-ai/ideogram-v3-turbo" или "wavespeed-ai/flux-kontext-pro"). Если не указано, берется из настроек.
    
    Returns:
        URL результата
    
    Raises:
        RuntimeError: Если произошла ошибка при обработке
    """
    # Пробуем получить API ключ из переменных окружения или из настроек
    api_key = os.getenv("WAVESPEED_API_KEY")
    if not api_key:
        try:
            from app.core.config import reload_settings
            current_settings = reload_settings()
            api_key = current_settings.wavespeed_api_key
        except Exception:
            pass
    if not api_key:
        raise RuntimeError("WAVESPEED_API_KEY не установлен в переменных окружения или настройках")
    
    # Получаем имя модели из настроек, если не указано
    if not model:
        try:
            from app.core.config import reload_settings
            current_settings = reload_settings()
            model = current_settings.wavespeed_text_model
            logger.info("Using text model from settings: {}", model)
        except Exception as e:
            logger.warning("Failed to load text model from settings: {}, using default", e)
            model = "ideogram-ai/ideogram-v2a-turbo"  # Значение по умолчанию (Ideogram V2a Turbo поддерживает inpainting)
    
    base_url = "https://api.wavespeed.ai/api/v3"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }
    
    try:
        logger.info("Uploading image to WaveSpeedAI for designer text...")
        
        # Увеличиваем таймаут для больших файлов и медленных соединений
        timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
        with httpx.Client(timeout=timeout) as client:
            # Проверяем размер изображения
            try:
                with Image.open(image_path) as img:
                    img_size = img.size
                    file_size = os.path.getsize(image_path)
                    logger.info("Image size: {}x{} pixels, file size: {} bytes", img_size[0], img_size[1], file_size)
            except Exception as e:
                logger.warning("Could not read image size: {}", e)
            
            # Загружаем изображение с повторными попытками
            max_upload_attempts = 3
            image_url = None
            for upload_attempt in range(max_upload_attempts):
                try:
                    with open(image_path, "rb") as f:
                        image_data = f.read()
                    
                    logger.info("Upload attempt {}/{}: uploading {} bytes", upload_attempt + 1, max_upload_attempts, len(image_data))
                    upload_response = client.post(
                        f"{base_url}/media/upload/binary",
                        headers=headers,
                        files={"file": (os.path.basename(image_path), image_data, "image/jpeg")},
                    )
                    upload_response.raise_for_status()
                    upload_data = upload_response.json()
                    
                    # Извлекаем URL из ответа
                    if upload_data.get("code") == 200 and upload_data.get("data"):
                        image_url = upload_data["data"].get("download_url")
                    else:
                        image_url = upload_data.get("url")
                    
                    if not image_url:
                        raise RuntimeError(f"Не удалось получить URL для загруженного изображения: {upload_response.text}")
                    logger.info("Image uploaded successfully: {}", image_url[:50])
                    break
                except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                    if upload_attempt < max_upload_attempts - 1:
                        logger.warning("Upload timeout (attempt {}/{}), retrying...", upload_attempt + 1, max_upload_attempts)
                        time.sleep(2)
                    else:
                        raise RuntimeError(f"Не удалось загрузить изображение после {max_upload_attempts} попыток: {e}") from e
                except Exception as e:
                    logger.error("Upload error (attempt {}/{}): {}", upload_attempt + 1, max_upload_attempts, e)
                    if upload_attempt < max_upload_attempts - 1:
                        time.sleep(2)
                    else:
                        raise
            
            if not image_url:
                raise RuntimeError("Не удалось загрузить изображение после всех попыток")
            
            # Вызываем модель для image-to-image редактирования (Ideogram 3 или FLUX Kontext)
            logger.info("Calling WaveSpeedAI model for designer text: {}", model)
            logger.debug("Prompt length: {} characters", len(prompt))
            
            # Параметры для Ideogram моделей
            # Ideogram V2a Turbo поддерживает inpainting (редактирование изображений)
            if "ideogram-v2a" in model.lower():
                # Ideogram V2a Turbo - поддерживает inpainting для редактирования изображений
                request_params = {
                    "image": image_url,  # Исходное изображение
                    "prompt": prompt,  # Промпт с инструкциями по добавлению текста
                    "style": "Auto",  # Стиль генерации
                    "aspect_ratio": "1:1",  # Сохраняем пропорции
                }
                logger.info("Using Ideogram V2a Turbo with image-to-image (inpainting) parameters")
            elif "ideogram-v3" in model.lower():
                # Ideogram V3 Turbo - может не поддерживать image-to-image
                request_params = {
                    "prompt": prompt,  # Промпт с инструкциями
                    "style": "Auto",  # Стиль генерации
                    "aspect_ratio": "1:1",  # Сохраняем пропорции
                }
                logger.warning("Ideogram V3 Turbo - используем text-to-image (image-to-image может не поддерживаться)")
            elif "ideogram" in model.lower():
                # Для других версий Ideogram пробуем image-to-image
                request_params = {
                    "image": image_url,  # Исходное изображение
                    "prompt": prompt,  # Промпт с инструкциями
                    "style": "Auto",  # Стиль генерации
                    "aspect_ratio": "1:1",  # Сохраняем пропорции
                }
                logger.info("Using Ideogram model with image-to-image parameters")
            else:
                # Для других моделей (FLUX Kontext) используем image-to-image
                request_params = {
                    "image": image_url,  # Исходное изображение (для image-to-image)
                    "prompt": prompt,  # Промпт с инструкциями по добавлению текста
                    "style": "Auto",  # Стиль генерации (если поддерживается)
                    "aspect_ratio": "1:1",  # Сохраняем пропорции исходного изображения
                    "enable_sync_mode": True,  # Синхронный режим (если поддерживается)
                    "output_format": "png",  # PNG для максимального качества
                }
            
            try:
                logger.info("Sending request to WaveSpeedAI API: model={}, params_keys={}", model, list(request_params.keys()))
                predict_response = client.post(
                    f"{base_url}/{model}",
                    headers={**headers, "Content-Type": "application/json"},
                    json=request_params,
                    timeout=httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0),  # Увеличиваем таймаут для генерации
                )
                logger.info("WaveSpeedAI API response status: {}", predict_response.status_code)
                predict_response.raise_for_status()
                predict_data = predict_response.json()
                logger.debug("WaveSpeedAI API response data keys: {}", list(predict_data.keys()) if isinstance(predict_data, dict) else "not a dict")
            except httpx.HTTPStatusError as e:
                error_text = e.response.text if e.response else str(e)
                logger.error("WaveSpeedAI HTTP error: {} - {}", e.response.status_code if e.response else "unknown", error_text[:500])
                raise RuntimeError(f"WaveSpeedAI API error: {e.response.status_code if e.response else 'unknown'} - {error_text[:200]}") from e
            except httpx.TimeoutException as e:
                logger.error("WaveSpeedAI API timeout: {}", e)
                raise RuntimeError(f"WaveSpeedAI API timeout: запрос превысил время ожидания. Попробуйте позже.") from e
            except Exception as e:
                logger.error("WaveSpeedAI API unexpected error: {}", e, exc_info=True)
                raise RuntimeError(f"WaveSpeedAI API unexpected error: {e}") from e
            
            # Обрабатываем ответ
            if predict_data.get("code") == 200 and predict_data.get("data"):
                data = predict_data["data"]
                status = data.get("status")
                
                if status == "completed":
                    outputs = data.get("outputs", [])
                    if outputs and len(outputs) > 0:
                        result_url = outputs[0]
                        logger.info("WaveSpeedAI designer text completed (sync): {}", result_url[:50])
                        return result_url
                    else:
                        raise RuntimeError(f"Статус completed, но outputs пуст: {data}")
                
                # Если не completed, получаем request_id для polling
                request_id = data.get("id")
                if not request_id:
                    raise RuntimeError(f"Не удалось получить id из ответа: {predict_data}")
            else:
                # Альтернативный формат ответа (без code/data)
                if predict_data.get("status") == "completed" and predict_data.get("output"):
                    result_url = predict_data["output"]
                    logger.info("WaveSpeedAI designer text completed: {}", result_url[:50])
                    return result_url
                
                request_id = predict_data.get("requestId") or predict_data.get("id")
                if not request_id:
                    raise RuntimeError(f"Не удалось получить requestId/id из ответа: {predict_data}")
            
            logger.info("WaveSpeedAI designer text started (async), requestId: {}", request_id)
            
            # Polling результата
            max_attempts = 30
            poll_interval = 2
            
            for attempt in range(max_attempts):
                time.sleep(poll_interval)
                
                try:
                    logger.debug("Polling WaveSpeedAI prediction (attempt {}/{}): requestId={}", attempt + 1, max_attempts, request_id)
                    result_response = client.get(
                        f"{base_url}/predictions/{request_id}/result",
                        headers=headers,
                        timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
                    )
                    result_response.raise_for_status()
                    result_data = result_response.json()
                    logger.debug("WaveSpeedAI polling response: keys={}, status_code={}", 
                                list(result_data.keys()) if isinstance(result_data, dict) else "not a dict",
                                result_response.status_code)
                except Exception as poll_error:
                    logger.error("Error during polling (attempt {}/{}): {}", attempt + 1, max_attempts, poll_error)
                    if attempt < max_attempts - 1:
                        continue  # Продолжаем попытки
                    else:
                        raise RuntimeError(f"Ошибка при polling результата: {poll_error}") from poll_error
                
                status = None
                if result_data.get("code") == 200 and result_data.get("data"):
                    data = result_data["data"]
                    status = data.get("status")
                    logger.info("WaveSpeedAI prediction status: {} (attempt {}/{})", status, attempt + 1, max_attempts)
                    if status == "completed":
                        outputs = data.get("outputs", [])
                        if outputs and len(outputs) > 0:
                            result_url = outputs[0]
                            logger.info("WaveSpeedAI designer text completed: {}", result_url[:50])
                            return result_url
                        else:
                            logger.warning("Status completed but outputs is empty: {}", data)
                    elif status == "failed":
                        error = data.get("error", result_data.get("error", "Unknown error"))
                        logger.error("WaveSpeedAI prediction failed: error={}, full_data={}", error, result_data)
                        raise RuntimeError(f"WaveSpeedAI designer text failed: {error}")
                else:
                    status = result_data.get("status")
                    logger.info("WaveSpeedAI prediction status (alt format): {} (attempt {}/{})", status, attempt + 1, max_attempts)
                    if status == "completed":
                        output = result_data.get("output")
                        if output:
                            logger.info("WaveSpeedAI designer text completed: {}", output[:50] if isinstance(output, str) else "output received")
                            return output if isinstance(output, str) else str(output)
                        else:
                            logger.warning("Status completed but output is missing: {}", result_data)
                            raise RuntimeError(f"Статус completed, но output отсутствует: {result_data}")
                    elif status == "failed":
                        error = result_data.get("error", "Unknown error")
                        logger.error("WaveSpeedAI prediction failed (alt format): error={}, full_data={}", error, result_data)
                        raise RuntimeError(f"WaveSpeedAI designer text failed: {error}")
                
                # Если статус не completed и не failed, продолжаем polling
                if status not in ("completed", "failed"):
                    logger.debug("Status is '{}', continuing polling...", status)
            
            raise RuntimeError(f"WaveSpeedAI designer text timeout после {max_attempts} попыток")
            
    except httpx.HTTPStatusError as e:
        error_text = e.response.text if e.response else str(e)
        logger.error("WaveSpeedAI HTTP error: {} - {}", e.response.status_code if e.response else "unknown", error_text)
        raise RuntimeError(f"WaveSpeedAI API error: {e.response.status_code if e.response else 'unknown'} - {error_text[:200]}") from e
    except Exception as e:
        logger.error("WaveSpeedAI designer text error: {}", e)
        raise RuntimeError(f"WaveSpeedAI designer text failed: {e}") from e

