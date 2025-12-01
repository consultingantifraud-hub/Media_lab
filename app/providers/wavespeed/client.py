"""
WaveSpeedAI API клиент для face swap и дизайнерского текста.
"""
import os
import time
from pathlib import Path
from typing import Any, Dict
from loguru import logger
import httpx
from PIL import Image, ImageDraw


def wavespeed_face_swap(source_path: str, face_path: str, model: str | None = None) -> str:
    """
    Делает face swap через WaveSpeedAI и возвращает URL или локальный путь результата.
    
    Args:
        source_path: Путь к исходному изображению (куда вставляется лицо)
        face_path: Путь к изображению с лицом для замены
        model: Имя модели (например, "wavespeed-ai/image-face-swap"). Если не указано, берется из настроек.
    
    Returns:
        URL результата
    
    Raises:
        RuntimeError: Если произошла ошибка при обработке
    """
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

    if not model:
        try:
            from app.core.config import reload_settings
            current_settings = reload_settings()
            model = current_settings.wavespeed_face_swap_model
            logger.info("Using face swap model from settings: {}", model)
        except Exception as e:
            logger.warning("Failed to load face swap model from settings: {}, using default", e)
            model = "wavespeed-ai/image-face-swap"  # Значение по умолчанию

    base_url = "https://api.wavespeed.ai/api/v3"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    try:
        # Увеличиваем таймаут для больших файлов и медленных соединений
        timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
        with httpx.Client(timeout=timeout) as client:
            # Загружаем изображения с повторными попытками
            max_upload_attempts = 3
            source_url = None
            face_url = None

            # Загружаем исходное изображение (target)
            logger.info("Uploading source image to WaveSpeedAI...")
            for upload_attempt in range(max_upload_attempts):
                try:
                    with open(source_path, "rb") as f:
                        source_data = f.read()

                    logger.info("Upload attempt {}/{}: uploading {} bytes", upload_attempt + 1, max_upload_attempts, len(source_data))
                    # Определяем MIME type на основе расширения файла для сохранения качества
                    file_ext = Path(source_path).suffix.lower()
                    mime_type = "image/png" if file_ext == ".png" else "image/jpeg"
                    upload_response = client.post(
                        f"{base_url}/media/upload/binary",
                        headers=headers,
                        files={"file": (os.path.basename(source_path), source_data, mime_type)},
                    )
                    upload_response.raise_for_status()
                    upload_data = upload_response.json()

                    # Извлекаем URL из ответа
                    if upload_data.get("code") == 200 and upload_data.get("data"):
                        source_url = upload_data["data"].get("download_url")
                    else:
                        source_url = upload_data.get("url")

                    if not source_url:
                        raise RuntimeError(f"Не удалось получить URL для загруженного изображения: {upload_response.text}")
                    logger.info("Source image uploaded successfully: {}", source_url[:50])
                    break
                except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                    if upload_attempt < max_upload_attempts - 1:
                        logger.warning("Upload timeout (attempt {}/{}), retrying...", upload_attempt + 1, max_upload_attempts)
                        time.sleep(2)
                    else:
                        raise RuntimeError(f"Не удалось загрузить исходное изображение после {max_upload_attempts} попыток: {e}") from e
                except Exception as e:
                    logger.error("Upload error (attempt {}/{}): {}", upload_attempt + 1, max_upload_attempts, e)
                    if upload_attempt < max_upload_attempts - 1:
                        time.sleep(2)
                    else:
                        raise

            # Загружаем изображение с лицом (source)
            logger.info("Uploading face image to WaveSpeedAI...")
            for upload_attempt in range(max_upload_attempts):
                try:
                    with open(face_path, "rb") as f:
                        face_data = f.read()

                    logger.info("Upload attempt {}/{}: uploading {} bytes", upload_attempt + 1, max_upload_attempts, len(face_data))
                    # Определяем MIME type на основе расширения файла для сохранения качества
                    file_ext = Path(face_path).suffix.lower()
                    mime_type = "image/png" if file_ext == ".png" else "image/jpeg"
                    upload_response = client.post(
                        f"{base_url}/media/upload/binary",
                        headers=headers,
                        files={"file": (os.path.basename(face_path), face_data, mime_type)},
                    )
                    upload_response.raise_for_status()
                    upload_data = upload_response.json()

                    # Извлекаем URL из ответа
                    if upload_data.get("code") == 200 and upload_data.get("data"):
                        face_url = upload_data["data"].get("download_url")
                    else:
                        face_url = upload_data.get("url")

                    if not face_url:
                        raise RuntimeError(f"Не удалось получить URL для загруженного изображения: {upload_response.text}")
                    logger.info("Face image uploaded successfully: {}", face_url[:50])
                    break
                except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                    if upload_attempt < max_upload_attempts - 1:
                        logger.warning("Upload timeout (attempt {}/{}), retrying...", upload_attempt + 1, max_upload_attempts)
                        time.sleep(2)
                    else:
                        raise RuntimeError(f"Не удалось загрузить изображение с лицом после {max_upload_attempts} попыток: {e}") from e
                except Exception as e:
                    logger.error("Upload error (attempt {}/{}): {}", upload_attempt + 1, max_upload_attempts, e)
                    if upload_attempt < max_upload_attempts - 1:
                        time.sleep(2)
                    else:
                        raise

            if not source_url or not face_url:
                raise RuntimeError("Не удалось загрузить одно из изображений после всех попыток")

            # Вызываем модель для face swap
            logger.info("Calling WaveSpeedAI model for face swap: {}", model)

            # Определяем параметры в зависимости от модели
            is_akool = "akool" in model.lower()
            is_head_swap = "head-swap" in model.lower()

            if is_akool:
                # akool/image-face-swap использует source_image и target_image (массивы)
                request_params = {
                    "source_image": [face_url],  # Лицо для замены (массив)
                    "target_image": [source_url],  # Исходное изображение (массив)
                    "face_enhance": True,  # Улучшение лица
                    "output_format": "png",  # PNG для максимального качества
                }
            elif is_head_swap:
                # wavespeed-ai/image-head-swap использует image и face_image
                request_params = {
                    "image": source_url,  # Исходное изображение
                    "face_image": face_url,  # Лицо для замены
                    "output_format": "png",  # PNG для максимального качества
                }
            else:
                # wavespeed-ai/image-face-swap использует image и face_image
                # Добавляем параметры для улучшения качества и схожести
                request_params = {
                    "image": source_url,  # Исходное изображение (куда вставляется лицо)
                    "face_image": face_url,  # Лицо для замены
                    "face_enhance": True,  # Улучшение качества лица для большей схожести
                    "target_index": 0,  # Явно указываем первое обнаруженное лицо для замены
                    "output_format": "png",  # PNG для максимального качества (без потерь)
                }

            try:
                api_endpoint = f"{base_url}/{model}"
                logger.info("Sending request to WaveSpeedAI API: endpoint={}, model={}, params_keys={}", 
                           api_endpoint, model, list(request_params.keys()))
                logger.info("WaveSpeedAI request params: image={}, face_image={}, face_enhance={}, output_format={}", 
                           source_url[:50] if source_url else "None", face_url[:50] if face_url else "None",
                           request_params.get("face_enhance"), request_params.get("output_format"))
                predict_response = client.post(
                    api_endpoint,
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
                        logger.info("WaveSpeedAI face swap completed (sync): {}", result_url[:50])
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
                    logger.info("WaveSpeedAI face swap completed: {}", result_url[:50])
                    return result_url

                request_id = predict_data.get("requestId") or predict_data.get("id")
                if not request_id:
                    raise RuntimeError(f"Не удалось получить requestId/id из ответа: {predict_data}")

            logger.info("WaveSpeedAI face swap started (async), requestId: {}", request_id)

            # Polling результата
            max_attempts = 30
            poll_interval = 2

            for attempt in range(max_attempts):
                time.sleep(poll_interval)

                try:
                    result_response = client.get(
                        f"{base_url}/predictions/{request_id}/result",
                        headers=headers,
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
                        raise RuntimeError(f"Ошибка при polling после {max_attempts} попыток: {poll_error}") from poll_error

                if result_data.get("code") == 200 and result_data.get("data"):
                    data = result_data["data"]
                    status = data.get("status")
                    logger.debug("WaveSpeedAI prediction status: {} (attempt {}/{})", status, attempt + 1, max_attempts)
                    if status == "completed":
                        outputs = data.get("outputs", [])
                        if outputs and len(outputs) > 0:
                            result_url = outputs[0]
                            logger.info("WaveSpeedAI face swap completed: {}", result_url[:50])
                            return result_url
                        else:
                            raise RuntimeError(f"Статус completed, но outputs пуст: {data}")
                else:
                    status = result_data.get("status")
                    logger.debug("WaveSpeedAI prediction status: {} (attempt {}/{})", status, attempt + 1, max_attempts)
                    if status == "completed":
                        output = result_data.get("output")
                        if output:
                            logger.info("WaveSpeedAI face swap completed: {}", output[:50] if isinstance(output, str) else "output received")
                            return output if isinstance(output, str) else str(output)
                        else:
                            raise RuntimeError(f"Статус completed, но output отсутствует: {result_data}")

                if status == "failed":
                    error = result_data.get("error", "Unknown error")
                    logger.error("WaveSpeedAI prediction failed: error={}, full_data={}", error, result_data)
                    raise RuntimeError(f"WaveSpeedAI face swap failed: {error}")

            raise RuntimeError(f"WaveSpeedAI face swap timeout после {max_attempts} попыток")

    except httpx.HTTPStatusError as e:
        error_text = e.response.text if e.response else str(e)
        logger.error("WaveSpeedAI HTTP error: {} - {}", e.response.status_code if e.response else "unknown", error_text)
        raise RuntimeError(f"WaveSpeedAI API error: {e.response.status_code if e.response else 'unknown'} - {error_text[:200]}") from e
    except Exception as e:
        logger.error("WaveSpeedAI face swap error: {}", e)
        raise RuntimeError(f"WaveSpeedAI face swap failed: {e}") from e


def wavespeed_designer_text(image_path: str, prompt: str, model: str | None = None, use_text_to_image: bool = False, position: str | None = None) -> tuple[str, tuple[int, int] | None]:
    """
    Добавляет дизайнерский текст на изображение через WaveSpeedAI (OpenAI GPT Image 1 Mini Edit или другие модели).
    
    Args:
        image_path: Путь к исходному изображению
        prompt: Промпт для модели (англоязычный, описывающий где и какой текст добавить)
        model: Имя модели (например, "openai/gpt-image-1-mini/edit"). Если не указано, берется из настроек.
        use_text_to_image: Использовать text-to-image режим (для Ideogram)
        position: Позиция текста (top, bottom, center, etc.) - используется для создания маски
    
    Returns:
        URL результата
    
    Raises:
        RuntimeError: Если произошла ошибка при обработке
    """
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

    if not model:
        try:
            from app.core.config import reload_settings
            current_settings = reload_settings()
            model = current_settings.wavespeed_text_model
            logger.info("Using text model from settings: {}", model)
        except Exception as e:
            logger.warning("Failed to load text model from settings: {}, using default", e)
            model = "openai/gpt-image-1-mini/edit"  # Значение по умолчанию (OpenAI GPT Image 1 Mini Edit через WaveSpeedAI)

    base_url = "https://api.wavespeed.ai/api/v3"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    # Определяем режим работы модели
    use_text_to_image = "ideogram" in model.lower()
    is_openai_model = "openai" in model.lower() or "gpt-image" in model.lower()
    
    if use_text_to_image:
        logger.info("Using text-to-image mode for Ideogram (inpainting requires mask, which we don't have)")
        image_url = None  # Не загружаем изображение для text-to-image
    elif is_openai_model:
        logger.info("Using OpenAI model via WaveSpeedAI (image editing mode with mask)")
        # OpenAI модели через WaveSpeedAI требуют загрузку изображения и маски
    else:
        logger.info("Using image-to-image mode, uploading image to WaveSpeedAI...")

    try:
        # Увеличиваем таймаут для больших файлов и медленных соединений
        timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
        with httpx.Client(timeout=timeout) as client:
            # Загружаем изображение только если не используем text-to-image
            if not use_text_to_image:
                logger.info("Uploading image to WaveSpeedAI for designer text...")
                # Для OpenAI моделей нужно квадратное изображение - предобрабатываем
                # Также уменьшаем размер для ускорения (максимум 1024x1024)
                processed_image_path = image_path
                original_size = None
                if is_openai_model:
                    logger.info("Preprocessing image for OpenAI model (square format required, max 1024x1024 for speed)")
                    processed_image_path, original_size = _prepare_image_for_openai(image_path)
                
                # Проверяем размер изображения
                try:
                    with Image.open(processed_image_path) as img:
                        img_size = img.size
                        file_size = os.path.getsize(processed_image_path)
                        logger.info("Image size: {}x{} pixels, file size: {} bytes", img_size[0], img_size[1], file_size)
                except Exception as e:
                    logger.warning("Could not read image size: {}", e)
                
                # Загружаем изображение с повторными попытками
                max_upload_attempts = 3
                image_url = None
                for upload_attempt in range(max_upload_attempts):
                    try:
                        with open(processed_image_path, "rb") as f:
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
                
                # Не удаляем обработанное изображение сразу - оно понадобится для определения размера
                
                # Для OpenAI моделей создаем и загружаем маску, если указана позиция
                mask_url = None
                if is_openai_model and position:
                    logger.info("Creating mask for OpenAI model (position: {})", position)
                    # Используем обработанное изображение для создания маски
                    mask_path = _create_text_mask(processed_image_path, position)
                    try:
                        # Загружаем маску
                        with open(mask_path, "rb") as f:
                            mask_data = f.read()
                        
                        logger.info("Uploading mask: {} bytes", len(mask_data))
                        mask_upload_response = client.post(
                            f"{base_url}/media/upload/binary",
                            headers=headers,
                            files={"file": (mask_path.name, mask_data, "image/png")},
                        )
                        mask_upload_response.raise_for_status()
                        mask_upload_data = mask_upload_response.json()
                        
                        if mask_upload_data.get("code") == 200 and mask_upload_data.get("data"):
                            mask_url = mask_upload_data["data"].get("download_url")
                        else:
                            mask_url = mask_upload_data.get("url")
                        
                        if not mask_url:
                            logger.warning("Failed to get mask URL, continuing without mask")
                        else:
                            logger.info("Mask uploaded successfully: {}", mask_url[:50])
                    except Exception as e:
                        logger.warning("Failed to upload mask: {}, continuing without mask", e)
                    finally:
                        # Удаляем временную маску
                        if mask_path.exists():
                            mask_path.unlink()
            
            # Вызываем модель для редактирования
            logger.info("Calling WaveSpeedAI model for designer text: {}", model)
            logger.debug("Prompt length: {} characters", len(prompt))
            
            # Параметры для разных моделей
            is_openai_model = "openai" in model.lower() or "gpt-image" in model.lower()
            
            if "ideogram" in model.lower():
                # Ideogram модели - используем text-to-image (не передаем image, так как нужна маска для inpainting)
                request_params = {
                    "prompt": prompt,  # Промпт с инструкциями по добавлению текста
                    "style": "Auto",  # Стиль генерации (Auto, Design, Realistic)
                    "aspect_ratio": "1:1",  # Сохраняем пропорции
                }
                logger.info("Using Ideogram model with text-to-image (inpainting requires mask, which we don't have)")
            elif is_openai_model:
                # OpenAI модели через WaveSpeedAI (например, openai/gpt-image-1-mini/edit)
                # Согласно документации OpenAI DALL-E Edit: маска должна быть прозрачной в области редактирования
                # Параметры: prompt, images (массив URL), mask (URL маски, опционально), enable_sync_mode, enable_base64_output
                request_params = {
                    "prompt": prompt,  # Промпт с инструкциями по добавлению текста
                    "images": [image_url],  # Исходное изображение (массив URL согласно документации)
                    "enable_sync_mode": True,  # Синхронный режим (быстрее для небольших изображений)
                    "enable_base64_output": False,  # Возвращать URL, а не base64
                }
                # Добавляем маску, если она была создана (для локального редактирования)
                # ВАЖНО: WaveSpeedAI может не поддерживать маски для OpenAI моделей через их прокси
                # Пробуем передать маску, но если не работает, возможно нужно использовать другой подход
                if mask_url:
                    request_params["mask"] = mask_url  # Маска для локального редактирования
                    # НЕ передаем size - пусть модель использует размер входного изображения
                    logger.info("Using OpenAI model via WaveSpeedAI with mask for local editing (mask URL: {})", mask_url[:50])
                else:
                    logger.info("Using OpenAI model via WaveSpeedAI without mask (full image edit)")
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
                        return result_url, original_size if is_openai_model else None
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
                    return result_url, original_size if is_openai_model else None

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
                    result_response = client.get(
                        f"{base_url}/predictions/{request_id}/result",
                        headers=headers,
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
                        raise RuntimeError(f"Ошибка при polling после {max_attempts} попыток: {poll_error}") from poll_error

                if result_data.get("code") == 200 and result_data.get("data"):
                    data = result_data["data"]
                    status = data.get("status")
                    logger.debug("WaveSpeedAI prediction status: {} (attempt {}/{})", status, attempt + 1, max_attempts)
                    if status == "completed":
                        outputs = data.get("outputs", [])
                        if outputs and len(outputs) > 0:
                            result_url = outputs[0]
                            logger.info("WaveSpeedAI designer text completed: {}", result_url[:50])
                            return result_url, original_size if is_openai_model else None
                        else:
                            raise RuntimeError(f"Статус completed, но outputs пуст: {data}")
                else:
                    status = result_data.get("status")
                    logger.debug("WaveSpeedAI prediction status: {} (attempt {}/{})", status, attempt + 1, max_attempts)
                    if status == "completed":
                        output = result_data.get("output")
                        if output:
                            logger.info("WaveSpeedAI designer text completed: {}", output[:50] if isinstance(output, str) else "output received")
                            return (output if isinstance(output, str) else str(output)), original_size if is_openai_model else None
                        else:
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


def _create_text_mask(image_path: str, position: str) -> Path:
    """
    Создает маску для области текста на основе позиции.
    Черная область = где будет редактирование (добавление текста).
    Белая область = не трогать (оставить без изменений).
    
    Args:
        image_path: Путь к исходному изображению
        position: Позиция текста (top, bottom, center, top_left, etc.)
    
    Returns:
        Путь к созданной маске
    """
    # Открываем исходное изображение
    with Image.open(image_path) as img:
        # Конвертируем в RGBA, если нужно
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        
        width, height = img.size
        
        # Создаем маску (белое = не редактировать, черное = редактировать)
        # Для OpenAI моделей: черная область = где будет редактирование
        mask = Image.new("RGBA", (width, height), (255, 255, 255, 255))  # Белая маска (не редактировать)
        draw = ImageDraw.Draw(mask)
        
        # Определяем область для текста на основе позиции
        # Черная область = где будет редактирование (добавление текста)
        text_area_height = int(height * 0.2)  # 20% высоты для текста
        text_area_width = int(width * 0.8)  # 80% ширины для текста
        
        if position == "top":
            # Верхняя часть
            x1 = int((width - text_area_width) / 2)
            y1 = 0
            x2 = x1 + text_area_width
            y2 = text_area_height
        elif position == "bottom":
            # Нижняя часть
            x1 = int((width - text_area_width) / 2)
            y1 = height - text_area_height
            x2 = x1 + text_area_width
            y2 = height
        elif position == "center":
            # Центр
            x1 = int((width - text_area_width) / 2)
            y1 = int((height - text_area_height) / 2)
            x2 = x1 + text_area_width
            y2 = y1 + text_area_height
        elif position == "top_left":
            # Верхний левый угол
            x1 = 0
            y1 = 0
            x2 = int(width * 0.3)
            y2 = text_area_height
        elif position == "top_right":
            # Верхний правый угол
            x1 = int(width * 0.7)
            y1 = 0
            x2 = width
            y2 = text_area_height
        elif position == "bottom_left":
            # Нижний левый угол
            x1 = 0
            y1 = height - text_area_height
            x2 = int(width * 0.3)
            y2 = height
        elif position == "bottom_right":
            # Нижний правый угол
            x1 = int(width * 0.7)
            y1 = height - text_area_height
            x2 = width
            y2 = height
        else:
            # По умолчанию - нижняя часть
            x1 = int((width - text_area_width) / 2)
            y1 = height - text_area_height
            x2 = x1 + text_area_width
            y2 = height
        
        # Рисуем прозрачную область (alpha=0) для области редактирования
        # Для OpenAI DALL-E Edit: прозрачная область (alpha=0) = редактировать, непрозрачная (alpha=255) = не трогать
        draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0, 0))  # Прозрачная область (alpha=0)
        
        # Сохраняем маску
        mask_path = Path(image_path).parent / f"{Path(image_path).stem}_mask.png"
        mask.save(mask_path, "PNG")
        logger.info("Created mask for position {}: area=({}, {}, {}, {})", position, x1, y1, x2, y2)
        
        return mask_path


def _prepare_image_for_openai(image_path: str) -> tuple[str, tuple[int, int]]:
    """
    Предобрабатывает изображение для OpenAI моделей:
    1. Уменьшает до максимум 1024x1024 для ускорения
    2. Делает квадратным с padding (белый фон)
    
    OpenAI DALL-E Edit требует квадратные изображения.
    
    Args:
        image_path: Путь к исходному изображению
    
    Returns:
        Кортеж: (путь к обработанному изображению, исходный размер (width, height))
    """
    with Image.open(image_path) as img:
        original_size = img.size
        width, height = original_size
        
        # Уменьшаем до максимум 1024x1024 для ускорения
        max_size = 1024
        if width > max_size or height > max_size:
            # Масштабируем, сохраняя пропорции
            if width > height:
                new_width = max_size
                new_height = int(height * (max_size / width))
            else:
                new_height = max_size
                new_width = int(width * (max_size / height))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            width, height = new_width, new_height
            logger.info("Resized image for speed: {}x{} -> {}x{}", original_size[0], original_size[1], width, height)
        
        # Если уже квадратное, возвращаем
        if width == height:
            processed_path = Path(image_path).parent / f"{Path(image_path).stem}_prep.jpg"
            img.convert("RGB").save(processed_path, "JPEG", quality=95)
            logger.debug("Image is already square: {}x{}", width, height)
            return str(processed_path), original_size
        
        # Определяем размер квадрата (максимальная сторона)
        size = max(width, height)
        
        # Создаем новое квадратное изображение с белым фоном
        square_img = Image.new("RGB", (size, size), (255, 255, 255))
        
        # Вычисляем позицию для центрирования исходного изображения
        x_offset = (size - width) // 2
        y_offset = (size - height) // 2
        
        # Вставляем исходное изображение в центр квадрата
        if img.mode == "RGBA":
            # Если есть прозрачность, используем alpha composite
            square_img.paste(img, (x_offset, y_offset), img)
        else:
            square_img.paste(img.convert("RGB"), (x_offset, y_offset))
        
        # Сохраняем обработанное изображение
        processed_path = Path(image_path).parent / f"{Path(image_path).stem}_prep.jpg"
        square_img.save(processed_path, "JPEG", quality=95)
        logger.info("Prepared image for OpenAI: {}x{} -> {}x{} (padding: x={}, y={})", 
                   original_size[0], original_size[1], size, size, x_offset, y_offset)
        
        return str(processed_path), original_size


def wavespeed_text_to_image(prompt: str, size: str = "1024x1024", model: str | None = None) -> str:
    """
    Генерирует изображение из текста через WaveSpeedAI (GPT модель).
    
    Args:
        prompt: Текстовый промпт для генерации
        size: Размер изображения (например, "1024x1024", "1024x1792")
        model: Имя модели (например, "openai/gpt-image-1-mini"). Если не указано, берется из настроек.
    
    Returns:
        URL результата
    
    Raises:
        RuntimeError: Если произошла ошибка при обработке
    """
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

    if not model:
        try:
            from app.core.config import reload_settings
            current_settings = reload_settings()
            model = current_settings.wavespeed_gpt_create_model
            logger.info("Using GPT create model from settings: {}", model)
        except Exception as e:
            logger.warning("Failed to load GPT create model from settings: {}, using default", e)
            model = "openai/gpt-image-1-mini"  # Значение по умолчанию (GPT Image 1 Mini для text-to-image - лучшее качество кириллицы)

    base_url = "https://api.wavespeed.ai/api/v3"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    # Параметры для GPT text-to-image (DALL-E 3)
    # DALL-E 3 использует другие параметры, чем GPT Image 1 Mini
    is_dalle3 = "dall-e-3" in model.lower() or "dall-e" in model.lower()
    
    if is_dalle3:
        # DALL-E 3 параметры: prompt, size, quality, n, response_format
        # ВАЖНО: WaveSpeedAI API требует формат размера со звездочкой: "1024*1024", а не "1024x1024"
        # Конвертируем формат размера из "1024x1024" в "1024*1024"
        size_formatted = size.replace("x", "*") if "x" in size else size
        
        request_params = {
            "prompt": prompt,
            "size": size_formatted,  # Формат "1024*1024", "1024*1792", "1792*1024" (со звездочкой!)
            "quality": "standard",  # "standard" или "hd"
            "n": 1,  # Количество изображений
            "response_format": "url",  # "url" или "b64_json"
        }
    else:
        # Параметры для других GPT моделей
        request_params = {
            "prompt": prompt,
            "size": size,  # Формат "1024x1024"
            "enable_sync_mode": True,  # Синхронный режим для быстрого ответа
            "enable_base64_output": False,  # Возвращать URL, а не base64
        }

    try:
        with httpx.Client(timeout=httpx.Timeout(connect=30.0, read=180.0, write=30.0, pool=30.0)) as client:
            logger.info("Sending text-to-image request to WaveSpeedAI: model={}, size={}, is_dalle3={}", model, size, is_dalle3)
            predict_response = client.post(
                f"{base_url}/{model}",
                headers={**headers, "Content-Type": "application/json"},
                json=request_params,
            )
            logger.info("WaveSpeedAI API response status: {}", predict_response.status_code)
            predict_response.raise_for_status()
            predict_data = predict_response.json()
            logger.debug("WaveSpeedAI API response data keys: {}", list(predict_data.keys()) if isinstance(predict_data, dict) else "not a dict")

            # Обрабатываем ответ
            # DALL-E 3 может возвращать результат напрямую в другом формате
            if is_dalle3:
                # DALL-E 3 может возвращать данные в формате {"data": [{"url": "..."}]}
                if predict_data.get("data") and isinstance(predict_data["data"], list):
                    if len(predict_data["data"]) > 0 and "url" in predict_data["data"][0]:
                        result_url = predict_data["data"][0]["url"]
                        logger.info("WaveSpeedAI DALL-E 3 completed: {}", result_url[:50])
                        return result_url
                # Или в формате {"data": {"url": "..."}}
                if predict_data.get("data") and isinstance(predict_data["data"], dict):
                    if "url" in predict_data["data"]:
                        result_url = predict_data["data"]["url"]
                        logger.info("WaveSpeedAI DALL-E 3 completed: {}", result_url[:50])
                        return result_url
            
            if predict_data.get("code") == 200 and predict_data.get("data"):
                data = predict_data["data"]
                status = data.get("status")
                
                if status == "completed":
                    outputs = data.get("outputs", [])
                    if outputs and len(outputs) > 0:
                        result_url = outputs[0]
                        logger.info("WaveSpeedAI text-to-image completed (sync): {}", result_url[:50])
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
                    logger.info("WaveSpeedAI text-to-image completed: {}", result_url[:50])
                    return result_url

                request_id = predict_data.get("requestId") or predict_data.get("id")
                if not request_id:
                    raise RuntimeError(f"Не удалось получить requestId/id из ответа: {predict_data}")

            logger.info("WaveSpeedAI text-to-image started (async), requestId: {}", request_id)

            # Polling для асинхронного режима
            max_attempts = 60
            poll_interval = 2
            for attempt in range(max_attempts):
                time.sleep(poll_interval)

                try:
                    result_response = client.get(
                        f"{base_url}/predictions/{request_id}/result",
                        headers=headers,
                    )
                    result_response.raise_for_status()
                    result_data = result_response.json()

                    if result_data.get("code") == 200 and result_data.get("data"):
                        data = result_data["data"]
                        status = data.get("status")
                        
                        if status == "completed":
                            outputs = data.get("outputs", [])
                            if outputs and len(outputs) > 0:
                                result_url = outputs[0]
                                logger.info("WaveSpeedAI text-to-image completed: {}", result_url[:50])
                                return result_url
                        elif status == "failed":
                            error = data.get("error", "Unknown error")
                            logger.error("WaveSpeedAI text-to-image failed: error={}", error)
                            raise RuntimeError(f"WaveSpeedAI text-to-image failed: {error}")
                    else:
                        # Альтернативный формат
                        status = result_data.get("status")
                        if status == "completed":
                            output = result_data.get("output")
                            if output:
                                logger.info("WaveSpeedAI text-to-image completed: {}", output[:50] if isinstance(output, str) else "output received")
                                return output if isinstance(output, str) else str(output)
                        elif status == "failed":
                            error = result_data.get("error", "Unknown error")
                            logger.error("WaveSpeedAI text-to-image failed (alt format): error={}", error)
                            raise RuntimeError(f"WaveSpeedAI text-to-image failed: {error}")

                except Exception as poll_error:
                    logger.error("Error during polling (attempt {}/{}): {}", attempt + 1, max_attempts, poll_error)
                    if attempt < max_attempts - 1:
                        continue
                    else:
                        raise RuntimeError(f"Ошибка при polling после {max_attempts} попыток: {poll_error}") from poll_error

            raise RuntimeError(f"WaveSpeedAI text-to-image timeout после {max_attempts} попыток")

    except httpx.HTTPStatusError as e:
        error_text = e.response.text if e.response else str(e)
        logger.error("WaveSpeedAI HTTP error: {} - {}", e.response.status_code if e.response else "unknown", error_text)
        raise RuntimeError(f"WaveSpeedAI API error: {e.response.status_code if e.response else 'unknown'} - {error_text[:200]}") from e
    except httpx.TimeoutException as e:
        logger.error("WaveSpeedAI API timeout: {}", e)
        raise RuntimeError(f"WaveSpeedAI API timeout: запрос превысил время ожидания. Попробуйте позже.") from e
    except Exception as e:
        logger.error("WaveSpeedAI text-to-image error: {}", e)
        raise RuntimeError(f"WaveSpeedAI text-to-image failed: {e}") from e
