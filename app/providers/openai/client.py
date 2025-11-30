"""
OpenAI API клиент для редактирования изображений (DALL-E Edit).
"""
import os
import base64
from pathlib import Path
from typing import Optional
from loguru import logger
from PIL import Image, ImageDraw
import httpx


def openai_designer_text(image_path: str, prompt: str, position: str, api_key: Optional[str] = None) -> str:
    """
    Добавляет дизайнерский текст на изображение через OpenAI DALL-E Edit API.
    
    Args:
        image_path: Путь к исходному изображению
        prompt: Промпт для модели (англоязычный, описывающий где и какой текст добавить)
        position: Позиция текста (top, bottom, center, top_left, etc.)
        api_key: API ключ OpenAI. Если не указан, берется из переменных окружения или настроек.
    
    Returns:
        URL результата (временный URL от OpenAI)
    
    Raises:
        RuntimeError: Если произошла ошибка при обработке
    """
    # Получаем API ключ
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            try:
                from app.core.config import reload_settings
                current_settings = reload_settings()
                api_key = current_settings.openai_api_key
            except Exception:
                pass
    
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY не установлен в переменных окружения или настройках")
    
    # Создаем маску для области, где будет текст
    mask_path = _create_text_mask(image_path, position)
    
    try:
        # Открываем изображение и маску
        with open(image_path, "rb") as image_file, open(mask_path, "rb") as mask_file:
            # Вызываем OpenAI API
            url = "https://api.openai.com/v1/images/edits"
            headers = {
                "Authorization": f"Bearer {api_key}",
            }
            
            files = {
                "image": (os.path.basename(image_path), image_file, "image/png"),
                "mask": (os.path.basename(mask_path), mask_file, "image/png"),
            }
            
            data = {
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",  # OpenAI требует квадратное изображение
            }
            
            logger.info("Calling OpenAI DALL-E Edit API: prompt_length={}, position={}", len(prompt), position)
            
            timeout = httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0)
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()
                result = response.json()
                
                logger.info("OpenAI DALL-E Edit API response: keys={}", list(result.keys()) if isinstance(result, dict) else "not a dict")
                
                # OpenAI возвращает результат в формате:
                # {"created": 1234567890, "data": [{"url": "https://..."}]}
                if isinstance(result, dict) and "data" in result and len(result["data"]) > 0:
                    image_url = result["data"][0].get("url")
                    if image_url:
                        logger.info("OpenAI DALL-E Edit completed: {}", image_url[:50])
                        return image_url
                    else:
                        raise RuntimeError(f"OpenAI API не вернул URL изображения: {result}")
                else:
                    raise RuntimeError(f"Неожиданный формат ответа от OpenAI API: {result}")
    
    finally:
        # Удаляем временную маску
        if mask_path.exists():
            mask_path.unlink()


def _create_text_mask(image_path: str, position: str) -> Path:
    """
    Создает маску для области текста на основе позиции.
    
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
        
        # Создаем маску (черное = редактировать, белое = не трогать)
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
        
        # Рисуем черную область (где будет редактирование)
        draw.rectangle([x1, y1, x2, y2], fill=(0, 0, 0, 255))
        
        # Сохраняем маску
        mask_path = Path(image_path).parent / f"{Path(image_path).stem}_mask.png"
        mask.save(mask_path, "PNG")
        logger.info("Created mask for position {}: area=({}, {}, {}, {})", position, x1, y1, x2, y2)
        
        return mask_path

