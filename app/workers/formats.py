"""
Единая система форматов изображений для всех моделей.

Определяет логические форматы (1:1, 3:4, 4:3, 4:5, 9:16, 16:9) и функции
для преобразования изображений к нужному формату.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from loguru import logger
from PIL import Image


class ImageFormat(str, Enum):
    """Логические форматы изображений."""
    SQUARE_1_1 = "1:1"  # Квадрат 1:1 (универсальный)
    VERTICAL_3_4 = "3:4"  # Вертикальный 3:4 (WB/Ozon)
    HORIZONTAL_4_3 = "4:3"  # Горизонтальный 4:3 (Авито)
    VERTICAL_4_5 = "4:5"  # Вертикальный 4:5 (Instagram)
    VERTICAL_9_16 = "9:16"  # Вертикальный 9:16 (сторис/рилс)
    HORIZONTAL_16_9 = "16:9"  # Горизонтальный 16:9 (баннеры)


@dataclass
class FormatSpec:
    """Спецификация формата изображения."""
    format_id: ImageFormat
    aspect_ratio: str  # "1:1", "3:4", etc.
    label: str  # "Квадрат 1:1"
    button_text: str  # "⬜ 1:1"
    description: str  # "WB/Ozon" для подсказок
    is_vertical: bool
    is_horizontal: bool


# Определения всех форматов
FORMAT_SPECS: dict[ImageFormat, FormatSpec] = {
    ImageFormat.SQUARE_1_1: FormatSpec(
        format_id=ImageFormat.SQUARE_1_1,
        aspect_ratio="1:1",
        label="Квадрат 1:1",
        button_text="⬜ 1:1",
        description="универсальный",
        is_vertical=False,
        is_horizontal=False,
    ),
    ImageFormat.VERTICAL_3_4: FormatSpec(
        format_id=ImageFormat.VERTICAL_3_4,
        aspect_ratio="3:4",
        label="Вертикальное 3:4",
        button_text="▯ 3:4",
        description="WB/Ozon",
        is_vertical=True,
        is_horizontal=False,
    ),
    ImageFormat.HORIZONTAL_4_3: FormatSpec(
        format_id=ImageFormat.HORIZONTAL_4_3,
        aspect_ratio="4:3",
        label="Горизонтальное 4:3",
        button_text="▭ 4:3",
        description="Авито",
        is_vertical=False,
        is_horizontal=True,
    ),
    ImageFormat.VERTICAL_4_5: FormatSpec(
        format_id=ImageFormat.VERTICAL_4_5,
        aspect_ratio="4:5",
        label="Вертикальное 4:5",
        button_text="▯ 4:5",
        description="Instagram",
        is_vertical=True,
        is_horizontal=False,
    ),
    ImageFormat.VERTICAL_9_16: FormatSpec(
        format_id=ImageFormat.VERTICAL_9_16,
        aspect_ratio="9:16",
        label="Вертикальное 9:16",
        button_text="▯ 9:16",
        description="сторис/рилс",
        is_vertical=True,
        is_horizontal=False,
    ),
    ImageFormat.HORIZONTAL_16_9: FormatSpec(
        format_id=ImageFormat.HORIZONTAL_16_9,
        aspect_ratio="16:9",
        label="Горизонтальное 16:9",
        button_text="▭ 16:9",
        description="баннеры",
        is_vertical=False,
        is_horizontal=True,
    ),
}

# Порядок форматов по популярности (для кнопок)
FORMAT_ORDER = [
    ImageFormat.SQUARE_1_1,
    ImageFormat.VERTICAL_3_4,
    ImageFormat.HORIZONTAL_4_3,
    ImageFormat.VERTICAL_4_5,
    ImageFormat.VERTICAL_9_16,
    ImageFormat.HORIZONTAL_16_9,
]


def get_format_spec(format_id: ImageFormat | str) -> FormatSpec:
    """Получить спецификацию формата."""
    if isinstance(format_id, str):
        try:
            format_id = ImageFormat(format_id)
        except ValueError:
            raise ValueError(f"Unknown format: {format_id}")
    return FORMAT_SPECS[format_id]


def parse_aspect_ratio(aspect_ratio: str) -> tuple[float, float]:
    """Парсит соотношение сторон в виде (width_ratio, height_ratio)."""
    parts = aspect_ratio.split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid aspect ratio format: {aspect_ratio}")
    return float(parts[0]), float(parts[1])


def calculate_target_size(
    source_width: int,
    source_height: int,
    target_aspect_ratio: str,
    max_dimension: int = 2048,
) -> tuple[int, int]:
    """
    Вычисляет целевой размер изображения для заданного соотношения сторон.
    
    Использует кроп по центру, чтобы сохранить максимальное качество.
    
    Args:
        source_width: Ширина исходного изображения
        source_height: Высота исходного изображения
        target_aspect_ratio: Целевое соотношение сторон (например, "3:4")
        max_dimension: Максимальный размер по большей стороне
        
    Returns:
        Кортеж (width, height) целевого размера
    """
    target_w_ratio, target_h_ratio = parse_aspect_ratio(target_aspect_ratio)
    target_aspect = target_w_ratio / target_h_ratio
    
    source_aspect = source_width / source_height
    
    # Определяем, какую сторону использовать как базу
    if source_aspect > target_aspect:
        # Исходное изображение шире - используем высоту как базу
        target_height = min(source_height, max_dimension)
        target_width = int(target_height * target_aspect)
    else:
        # Исходное изображение выше - используем ширину как базу
        target_width = min(source_width, max_dimension)
        target_height = int(target_width / target_aspect)
    
    # Округляем до четных чисел (для некоторых моделей это важно)
    target_width = (target_width // 2) * 2
    target_height = (target_height // 2) * 2
    
    return target_width, target_height


def crop_to_aspect_ratio(
    image: Image.Image,
    target_aspect_ratio: str,
) -> Image.Image:
    """
    Обрезает изображение до заданного соотношения сторон (по центру).
    
    Args:
        image: Исходное изображение PIL
        target_aspect_ratio: Целевое соотношение сторон (например, "3:4")
        
    Returns:
        Обрезанное изображение
    """
    target_w_ratio, target_h_ratio = parse_aspect_ratio(target_aspect_ratio)
    target_aspect = target_w_ratio / target_h_ratio
    
    width, height = image.size
    source_aspect = width / height
    
    if abs(source_aspect - target_aspect) < 0.01:
        # Соотношение сторон уже правильное
        return image
    
    # Вычисляем размер обрезки
    if source_aspect > target_aspect:
        # Исходное изображение шире - обрезаем по ширине
        new_width = int(height * target_aspect)
        left = (width - new_width) // 2
        return image.crop((left, 0, left + new_width, height))
    else:
        # Исходное изображение выше - обрезаем по высоте
        new_height = int(width / target_aspect)
        top = (height - new_height) // 2
        return image.crop((0, top, width, top + new_height))


def resize_to_aspect_ratio(
    image: Image.Image,
    target_aspect_ratio: str,
    max_dimension: int = 2048,
) -> Image.Image:
    """
    Изменяет размер изображения до заданного соотношения сторон с сохранением пропорций.
    
    Использует ресайз (не кроп), поэтому может исказить изображение если исходное
    соотношение сильно отличается от целевого.
    
    Args:
        image: Исходное изображение PIL
        target_aspect_ratio: Целевое соотношение сторон
        max_dimension: Максимальный размер по большей стороне
        
    Returns:
        Измененное изображение
    """
    target_width, target_height = calculate_target_size(
        image.width, image.height, target_aspect_ratio, max_dimension
    )
    return image.resize((target_width, target_height), Image.Resampling.LANCZOS)


def convert_image_to_format(
    image_path: str | Path,
    target_format: ImageFormat | str,
    output_path: str | Path | None = None,
    method: Literal["crop", "resize"] = "crop",
    max_dimension: int = 2048,
) -> Path:
    """
    Преобразует изображение к заданному формату.
    
    Args:
        image_path: Путь к исходному изображению
        target_format: Целевой формат (ImageFormat или строка)
        output_path: Путь для сохранения (если None, перезаписывает исходный)
        method: Метод преобразования ("crop" - обрезка по центру, "resize" - изменение размера)
        max_dimension: Максимальный размер по большей стороне
        
    Returns:
        Путь к преобразованному изображению
    """
    if isinstance(target_format, str):
        target_format = ImageFormat(target_format)
    
    spec = get_format_spec(target_format)
    image_path = Path(image_path)
    
    with Image.open(image_path) as img:
        # Конвертируем в RGB если нужно
        if img.mode in ("RGBA", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "RGBA":
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        # Применяем преобразование
        if method == "crop":
            converted = crop_to_aspect_ratio(img, spec.aspect_ratio)
            # Ресайзим до оптимального размера
            target_width, target_height = calculate_target_size(
                converted.width, converted.height, spec.aspect_ratio, max_dimension
            )
            converted = converted.resize((target_width, target_height), Image.Resampling.LANCZOS)
        else:
            converted = resize_to_aspect_ratio(img, spec.aspect_ratio, max_dimension)
        
        # Сохраняем
        if output_path is None:
            output_path = image_path
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        converted.save(output_path, "PNG", optimize=True)
        logger.info(
            "Converted image {} to format {} ({}): {}x{} -> {}x{}",
            image_path.name,
            target_format.value,
            spec.aspect_ratio,
            img.width,
            img.height,
            converted.width,
            converted.height,
        )
        
        return output_path


def get_model_format_mapping(
    model: str,
    format_id: ImageFormat,
) -> dict[str, Any]:
    """
    Получает параметры формата для конкретной модели.
    
    Возвращает словарь с параметрами (size, aspect_ratio, width, height, image_size),
    которые нужно передать в API модели.
    
    Args:
        model: Имя модели (например, "fal-ai/nano-banana-pro")
        format_id: Логический формат
        
    Returns:
        Словарь с параметрами формата для модели
    """
    spec = get_format_spec(format_id)
    
    # Базовые параметры для всех моделей
    result: dict[str, Any] = {
        "aspect_ratio": spec.aspect_ratio,
    }
    
    # Специфичные настройки для разных моделей
    if "nano-banana-pro" in model.lower():
        # Nano Banana Pro поддерживает width/height напрямую
        # Используем оптимальные размеры для каждого формата
        format_sizes = {
            ImageFormat.SQUARE_1_1: (1024, 1024),
            ImageFormat.VERTICAL_3_4: (768, 1024),
            ImageFormat.HORIZONTAL_4_3: (1024, 768),
            ImageFormat.VERTICAL_4_5: (1024, 1280),
            ImageFormat.VERTICAL_9_16: (1024, 1792),
            ImageFormat.HORIZONTAL_16_9: (1792, 1024),
        }
        width, height = format_sizes.get(format_id, (1024, 1024))
        result.update({
            "width": width,
            "height": height,
            "size": f"{width}x{height}",
        })
    elif "nano-banana" in model.lower() and "pro" not in model.lower():
        # Nano-banana (обычный) - используем aspect_ratio для генерации в нужном формате
        # Модель поддерживает aspect_ratio напрямую, что позволяет генерировать в любом формате
        # aspect_ratio уже установлен в result выше, просто передаем его в API
        # Не используем image_size, чтобы модель сама выбрала оптимальный размер для aspect_ratio
        pass  # aspect_ratio уже установлен в result
    elif "seedream" in model.lower():
        # Seedream - используем size напрямую
        format_sizes = {
            ImageFormat.SQUARE_1_1: "2048x2048",
            ImageFormat.VERTICAL_3_4: "1536x2048",
            ImageFormat.HORIZONTAL_4_3: "2048x1536",
            ImageFormat.VERTICAL_4_5: "1536x1920",  # Приблизительно 4:5
            ImageFormat.VERTICAL_9_16: "1536x2048",  # Ближайший доступный
            ImageFormat.HORIZONTAL_16_9: "2048x1152",  # Приблизительно 16:9
        }
        result["size"] = format_sizes.get(format_id, "2048x2048")
    
    return result

