from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Literal

import pyphen
from loguru import logger
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pilmoji import Pilmoji

# Позиции на сетке 3x3
POSITION_GRID = {
    "top-left": (0, 0),
    "top-center": (1, 0),
    "top-right": (2, 0),
    "center-left": (0, 1),
    "center": (1, 1),
    "center-right": (2, 1),
    "bottom-left": (0, 2),
    "bottom-center": (1, 2),
    "bottom-right": (2, 2),
}

# Размеры шрифта (увеличены для лучшей читаемости)
FONT_SIZES = {
    "S": 36,   # Увеличено с 24
    "M": 64,   # Увеличено с 48
    "L": 96,   # Увеличено с 72
    "XL": 128, # Увеличено с 96
}

# Цвета
COLORS = {
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "orange": (255, 165, 0),  # Оранжевый
    "brand": (59, 130, 246),  # Синий брендовый
}

PROJECT_ROOT = Path(__file__).parent.parent.parent
FONT_DIR = PROJECT_ROOT / "assets" / "fonts"
DEFAULT_FONT = FONT_DIR / "Inter-Bold.ttf"
DEFAULT_EMOJI_FONT = FONT_DIR / "NotoColorEmoji.ttf"


def pick_contrast_color(rgb_tuple: tuple[int, int, int]) -> Literal["white", "black"]:
    """Выбирает контрастный цвет (белый или черный) на основе яркости фона."""
    r, g, b = rgb_tuple
    # Вычисляем относительную яркость (luminance)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "white" if luminance < 0.5 else "black"


def wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_height: int | None = None,
    line_spacing: float = 1.15,
) -> list[str]:
    """Переносит текст на несколько строк с учетом максимальной ширины."""
    # Сначала разбиваем текст по явным переносам строк (\n)
    # Это позволяет сохранить форматирование, которое пользователь указал явно
    paragraphs = text.split('\n')
    all_lines: list[str] = []
    
    for paragraph in paragraphs:
        # Для каждого абзаца применяем перенос по словам
        words = paragraph.split()
        lines: list[str] = []
        current_line = ""
        
        for word in words:
            # Проверяем, поместится ли слово на текущей строке
            if current_line:
                test_line = f"{current_line} {word}"
            else:
                test_line = word
            
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0] if bbox else len(test_line) * (max_width // 20)

            if width <= max_width:
                current_line = test_line
            else:
                # Если текущая строка не пуста, сохраняем её
                if current_line:
                    lines.append(current_line)
                # Если слово само по себе длиннее max_width, разбиваем его
                word_bbox = font.getbbox(word)
                word_width = word_bbox[2] - word_bbox[0] if word_bbox else len(word) * (max_width // 20)
                
                if word_width > max_width:
                    # Используем pyphen для переноса длинных слов
                    try:
                        dic = pyphen.Pyphen(lang="ru_RU")
                        hyphenated = dic.inserted(word, hyphen="-")
                        parts = hyphenated.split("-")
                        current_line = ""
                        for part in parts:
                            if current_line:
                                test_part = f"{current_line}{part}"
                            else:
                                test_part = part
                            part_bbox = font.getbbox(test_part)
                            part_width = part_bbox[2] - part_bbox[0] if part_bbox else len(test_part) * (max_width // 20)
                            
                            if part_width <= max_width:
                                current_line = test_part
                            else:
                                if current_line:
                                    lines.append(current_line)
                                current_line = part
                    except Exception:
                        # Если pyphen не работает, просто добавляем слово как есть
                        current_line = word
                else:
                    current_line = word
        
        # Добавляем последнюю строку абзаца
        if current_line:
            lines.append(current_line)
        
        # Добавляем все строки абзаца к общему списку
        all_lines.extend(lines)
        
        # Если абзац был пустым (двойной перенос строки), добавляем пустую строку
        if not paragraph.strip() and len(paragraphs) > 1:
            all_lines.append("")
    
    lines = all_lines
        
    # Проверяем максимальную высоту, если указана
    # НЕ удаляем строки - лучше показать весь текст, даже если он не помещается
    # Удаление строк приводит к потере информации
    if max_height:
        bbox = font.getbbox("Ag")
        line_height = bbox[3] - bbox[1] if bbox else 20
        # Используем средний множитель для расчета (учитываем, что некоторые строки могут иметь эмодзи)
        avg_spacing = line_spacing * 1.1  # Средний множитель между обычным и с эмодзи
        total_height = len(lines) * line_height * avg_spacing
        if total_height > max_height:
            # Логируем предупреждение, но не удаляем строки
            logger.warning("Text height ({}) exceeds max_height ({}), but keeping all lines to avoid data loss", total_height, max_height)

    return lines


def render_text_box(
    img: Image.Image,
    text: str,
    *,
    position: str = "bottom-center",
    size: str | int = "M",
    align: str = "center",
    font_path: str | Path | None = None,
    emoji_font: str | Path | None = None,
    max_width_ratio: float = 0.92,
    max_height_ratio: float = 0.38,
    padding: int = 24,
    line_spacing: float = 1.15,
    box: bool = True,
    box_radius: int = 28,
    box_alpha: float = 0.6,
    box_blur: float = 0.0,  # Радиус размытия плашки (0.0 = без размытия, 20.0 = сильное размытие)
    shadow: bool = True,
    stroke: int = 2,
    color: str = "auto",
    box_color: str = "auto",
    offset_bottom: float | None = None,  # Смещение от низа в процентах (0.0-1.0), например 0.3 = 30% от низа
) -> Image.Image:
    logger.info("render_text_box called with text: '{}', position: {}, size: {}, box: {}", text[:50], position, size, box)

    # Конвертируем в RGB если нужно
    if img.mode != "RGB":
        logger.debug("Converting image from {} to RGB", img.mode)
        img = img.convert("RGB")
    
    # Создаем копию для редактирования
    logger.debug("Creating image copy for editing")
    result = img.copy()
    draw = ImageDraw.Draw(result)
    logger.debug("Image copy created, size: {}", result.size)
    
    # Загружаем шрифты
    font_path = Path(font_path) if font_path else DEFAULT_FONT
    emoji_font_path = Path(emoji_font) if emoji_font else DEFAULT_EMOJI_FONT
    
    # Проверяем наличие локального шрифта эмодзи
    logger.debug("Checking emoji font path: {}", emoji_font_path)
    if emoji_font_path.exists():
        logger.info("Local emoji font found: {} ({} bytes)", emoji_font_path, emoji_font_path.stat().st_size)
    else:
        logger.warning("Local emoji font not found at: {}", emoji_font_path)

    # Определяем размер шрифта
    # Если size - число, используем его напрямую
    # Если size - строка (S, M, L, XL), берем из FONT_SIZES
    if isinstance(size, (int, float)):
        font_size = int(size)
    elif isinstance(size, str) and size in FONT_SIZES:
        font_size = FONT_SIZES[size]
    else:
        font_size = FONT_SIZES.get("M", 64)  # По умолчанию средний размер
    
    # Загружаем основной шрифт
    try:
        final_font = ImageFont.truetype(str(font_path), font_size)
        logger.debug("Loaded font: {} (size: {})", font_path, font_size)
    except Exception as e:
        logger.warning("Failed to load font {}: {}, using default", font_path, e)
        try:
            final_font = ImageFont.truetype(str(DEFAULT_FONT), font_size)
        except Exception:
            # Последний fallback - load_default (может не работать с pilmoji)
            logger.warning("No suitable font found, using load_default (may cause issues with pilmoji)")
            final_font = ImageFont.load_default()

    # Определяем цвет текста
    text_color_name = None
    if color == "auto":
        # Автоматический выбор цвета на основе яркости фона
        # Берем средний цвет из центра изображения
        center_x, center_y = img.size[0] // 2, img.size[1] // 2
        sample_size = 100
        x1 = max(0, center_x - sample_size // 2)
        y1 = max(0, center_y - sample_size // 2)
        x2 = min(img.size[0], center_x + sample_size // 2)
        y2 = min(img.size[1], center_y + sample_size // 2)
        sample_region = img.crop((x1, y1, x2, y2))
        # Получаем средний цвет
        avg_color = sample_region.resize((1, 1)).getpixel((0, 0))
        text_color_name = pick_contrast_color(avg_color)
        text_color = COLORS[text_color_name]
    elif color in COLORS:
        text_color_name = color
        text_color = COLORS[color]
    else:
        text_color = COLORS["white"]
        text_color_name = "white"

    # Определяем цвет плашки
    if box_color == "auto":
        # Автоматический выбор цвета плашки (противоположный тексту)
        box_color_rgb = COLORS["black"] if text_color_name == "white" else COLORS["white"]
    elif box_color in COLORS:
        box_color_rgb = COLORS[box_color]
    else:
        box_color_rgb = COLORS["black"]

    # Вычисляем максимальную ширину и высоту текста
    img_width, img_height = img.size
    max_line_width = int(img_width * max_width_ratio)
    max_text_height = int(img_height * max_height_ratio) if max_height_ratio else None

    # Переносим текст на несколько строк
    wrapped_lines = wrap_text(text, final_font, max_line_width, max_text_height, line_spacing)
    logger.debug("Text wrapped into {} lines", len(wrapped_lines))

    # Измеряем реальную ширину каждой строки (текст + эмодзи) для правильного расчета размера плашки
    # Создаем временное изображение для измерения
    temp_img = Image.new("RGB", (max_line_width * 2, 200), (255, 255, 255))
    temp_draw = ImageDraw.Draw(temp_img)
    
    # Разделяем каждую строку на части (текст и эмодзи) и измеряем их ширину
    line_widths = []  # Ширина каждой строки
    twemoji_local_path = PROJECT_ROOT / "assets" / "twemoji" / "72x72"
    
    for line in wrapped_lines:
        line_width = 0
        
        # Разделяем строку на части: обычный текст и эмодзи
        # Включаем дополнительные диапазоны для символов типа ❤️ (U+2764)
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # Emoticons
            "\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
            "\U0001F680-\U0001F6FF"  # Transport and Map
            "\U0001F1E0-\U0001F1FF"  # Flags
            "\U00002702-\U000027B0"   # Dingbats
            "\U000024C2-\U0001F251"   # Enclosed characters
            "\U00002764-\U0000279F"   # Additional symbols (❤️, etc.)
            "\U0001F440-\U0001F4FF"   # Gestures and body parts (👍, 👎, etc.)
            "\U0001F900-\U0001F9FF"   # Supplemental Symbols and Pictographs
            "]+",
            flags=re.UNICODE
        )
        
        parts = []
        last_end = 0
        for match in emoji_pattern.finditer(line):
            if match.start() > last_end:
                parts.append(("text", line[last_end:match.start()]))
            parts.append(("emoji", match.group()))
            last_end = match.end()
        if last_end < len(line):
            parts.append(("text", line[last_end:]))
        if not parts:
            parts = [("text", line)]
        
        # Измеряем ширину каждой части
        for part_type, part_text in parts:
            if not part_text:
                continue
                
            if part_type == "text":
                # Измеряем ширину текста
                bbox = temp_draw.textbbox((0, 0), part_text, font=final_font)
                if bbox:
                    line_width += bbox[2] - bbox[0]
                else:
                    line_width += len(part_text) * (font_size // 2)
            else:  # emoji
                # Измеряем ширину эмодзи (с учетом возможного масштабирования)
                # Расширенный диапазон для эмодзи
                emoji_chars = [char for char in part_text 
                              if (ord(char) >= 0x1F300 or 
                                  (ord(char) >= 0x2764 and ord(char) <= 0x279F) or
                                  (ord(char) >= 0x1F440 and ord(char) <= 0x1F4FF) or  # Gestures and body parts (👍, 👎, etc.)
                                  (ord(char) >= 0x1F900 and ord(char) <= 0x1F9FF))]
                if emoji_chars:
                    emoji_size = font_size
                    # Проверяем, нужно ли масштабирование (если есть плашка)
                    if box:
                        max_emoji_width = max_line_width - int(padding * 2)
                        total_emoji_width = len(emoji_chars) * emoji_size
                        if total_emoji_width > max_emoji_width:
                            emoji_size = int(max_emoji_width / len(emoji_chars))
                    line_width += len(emoji_chars) * emoji_size
        else:
                    line_width += font_size
        
        line_widths.append(line_width)
    
    # Находим максимальную ширину строки
    max_actual_width = max(line_widths) if line_widths else max_line_width
    logger.debug("Box calculation: line_widths={}, max_actual_width={}, max_line_width={}", 
                 line_widths, max_actual_width, max_line_width)

    # Вычисляем позицию текста
    grid_x, grid_y = POSITION_GRID.get(position, (1, 2))
    x_ratio = grid_x / 2.0
    
    # Если указано offset_bottom, используем его для расчета y_ratio
    # offset_bottom: 0.0 = в самом низу, 1.0 = в самом верху
    # y_ratio: 0.0 = вверху, 1.0 = внизу
    # Поэтому: y_ratio = 1.0 - offset_bottom
    if offset_bottom is not None:
        y_ratio = 1.0 - offset_bottom  # 0.0 = внизу, 1.0 = вверху
        logger.info("Using offset_bottom={}, calculated y_ratio={}", offset_bottom, y_ratio)
    else:
        y_ratio = grid_y / 2.0

    # Вычисляем координаты для текста
    box_x = None  # Сохраняем координату начала плашки для позиционирования эмодзи
    if box:
        # Если есть плашка, текст центрируется внутри плашки
        box_width = int(max_actual_width + padding * 2)
        bbox_temp = final_font.getbbox("Ag")
        line_height_temp = bbox_temp[3] - bbox_temp[1] if bbox_temp else 20
        # Учитываем увеличенное расстояние для строк с эмодзи (расширенный диапазон)
        has_emoji_lines = any(
            any((ord(char) >= 0x1F300 or 
                 (ord(char) >= 0x2764 and ord(char) <= 0x279F) or
                 (ord(char) >= 0x1F440 and ord(char) <= 0x1F4FF) or  # Gestures and body parts (👍, 👎, etc.)
                 (ord(char) >= 0x1F900 and ord(char) <= 0x1F9FF))
                for char in line)
            for line in wrapped_lines
        )
        spacing_for_box = line_spacing * 1.2 if has_emoji_lines else line_spacing
        
        # Вычисляем реальную высоту текста (с учетом междустрочного расстояния)
        total_text_height = 0
        for i, line in enumerate(wrapped_lines):
            line_has_emoji = any(
                (ord(char) >= 0x1F300 or 
                 (ord(char) >= 0x2764 and ord(char) <= 0x279F) or
                 (ord(char) >= 0x1F440 and ord(char) <= 0x1F4FF) or  # Gestures and body parts (👍, 👎, etc.)
                 (ord(char) >= 0x1F900 and ord(char) <= 0x1F9FF))
                for char in line
            )
            line_spacing_mult = line_spacing * 1.2 if line_has_emoji else line_spacing
            if i == 0:
                total_text_height += line_height_temp  # Первая строка без отступа сверху
            else:
                total_text_height += line_height_temp * line_spacing_mult  # Последующие строки с отступом
        
        # Padding для плашки (вертикальный) - уменьшен для более компактной плашки
        box_padding_vertical = int(padding * 1.0)
        box_height = int(total_text_height + box_padding_vertical * 2)
        
        # Вычисляем позицию плашки с учетом границ изображения
        box_x = int(img_width * x_ratio - box_width / 2)  # Сохраняем координату начала плашки
        box_y = int(img_height * y_ratio - box_height / 2)
        
        # Проверяем и корректируем границы плашки, чтобы она не выходила за пределы изображения
        if box_x < 0:
            box_x = 0
        if box_x + box_width > img_width:
            box_x = img_width - box_width
        if box_y < 0:
            box_y = 0
        if box_y + box_height > img_height:
            box_y = img_height - box_height
        
        # Центрируем текст по горизонтали и вертикали внутри плашки
        text_x = box_x + padding  # Горизонтальное центрирование будет через current_x расчет
        # Вертикальное центрирование: центр плашки минус половина высоты текста
        text_y = int(box_y + box_height / 2 - total_text_height / 2)
    else:
        # Если плашки нет, текст позиционируется напрямую
        text_x = int(img_width * x_ratio)
        text_y = int(img_height * y_ratio)
        box_x = None
        box_y = None

    # Рисуем плашку (если нужно)
    if box:
        # Создаем временное изображение для плашки с правильной прозрачностью
        # box_alpha: 0.0 = полностью прозрачная (невидимая), 1.0 = полностью непрозрачная (видимая)
        # box_alpha уже содержит правильное значение непрозрачности от LLM
        alpha_value = int(255 * box_alpha)
        box_img = Image.new("RGBA", (int(box_width), int(box_height)), (*box_color_rgb, alpha_value))
        logger.debug("Box image created: size=({}, {}), color={}, alpha={} ({}%)", 
                     box_width, box_height, box_color_rgb, box_alpha, int(box_alpha * 100))
        
        # Применяем размытие если нужно
        if box_blur > 0:
            # Размытие может изменить альфа-канал, поэтому сохраняем его
            alpha_before_blur = box_img.split()[3]
            box_img = box_img.filter(ImageFilter.GaussianBlur(radius=float(box_blur)))
            # Восстанавливаем альфа-канал после размытия
            box_img.putalpha(alpha_before_blur)
        
        # Применяем скругление если нужно
        if box_radius > 0:
            # Создаем маску для скругления
            mask = Image.new("L", (int(box_width), int(box_height)), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle(
                [(0, 0), (int(box_width), int(box_height))],
                radius=int(box_radius),
                fill=255,
            )
            # Применяем маску к alpha каналу, сохраняя исходную прозрачность
            # Умножаем исходный alpha канал на маску для сохранения прозрачности
            alpha_channel = box_img.split()[3]
            # Используем ImageChops.multiply для умножения alpha канала на маску
            from PIL import ImageChops
            alpha_masked = ImageChops.multiply(alpha_channel, mask)
            box_img.putalpha(alpha_masked)
            logger.debug("Rounded corners applied, alpha preserved: {}%", int(box_alpha * 100))
        
        # Накладываем плашку на изображение с использованием альфа-канала
        # Используем box_img как маску для правильного наложения прозрачности
        result.paste(box_img, (int(box_x), int(box_y)), box_img)
        logger.info("Box drawn: x={}, y={}, width={}, height={}, color={}, alpha={} ({}%), blur={}, radius={}", 
                     box_x, box_y, box_width, box_height, box_color_rgb, box_alpha, int(box_alpha * 100), box_blur, box_radius)

    # Обновляем x и y для текста
    x = text_x
    y = text_y

    # Тень рисуется через pilmoji ниже

    # Используем Pilmoji для рендеринга эмодзи с локальными файлами Twemoji
    # Локальные файлы Twemoji находятся в /app/assets/twemoji/72x72/
    # Это позволяет избежать загрузки из интернета
    pilmoji_context = None
    
    # Путь к локальным файлам Twemoji
    twemoji_local_path = PROJECT_ROOT / "assets" / "twemoji" / "72x72"
    
    try:
        # Проверяем наличие локальных файлов Twemoji
        if twemoji_local_path.exists() and any(twemoji_local_path.glob("*.png")):
            png_files = list(twemoji_local_path.glob("*.png"))
            png_count = len(png_files)
            logger.info("Local Twemoji files found at: {} ({} PNG files)", twemoji_local_path, png_count)
            
            # Копируем локальные файлы Twemoji в кэш Pilmoji для использования без интернета
            import os
            import shutil
            cache_dir = Path.home() / ".cache" / "pilmoji"
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Копируем файлы только если их еще нет в кэше
            files_copied = 0
            for png_file in png_files[:500]:  # Копируем первые 500 файлов (основные эмодзи)
                cache_file = cache_dir / png_file.name
                if not cache_file.exists():
                    try:
                        shutil.copy2(png_file, cache_file)
                        files_copied += 1
                    except Exception as copy_error:
                        logger.debug("Failed to copy {} to cache: {}", png_file.name, copy_error)
            
            # Копируем остальные файлы в фоне (если нужно)
            if len(png_files) > 500:
                for png_file in png_files[500:]:
                    cache_file = cache_dir / png_file.name
                    if not cache_file.exists():
                        try:
                            shutil.copy2(png_file, cache_file)
                            files_copied += 1
                        except Exception:
                            pass  # Игнорируем ошибки для остальных файлов
            
            if files_copied > 0:
                logger.info("Copied {} Twemoji files to Pilmoji cache at: {}", files_copied, cache_dir)
            else:
                logger.info("Twemoji files already in cache, using cached files (no internet download)")
            
            pilmoji_context = Pilmoji(result, cache=True)
            logger.info("Pilmoji initialized with local Twemoji files (no internet download)")
        else:
            logger.warning("Local Twemoji files not found at: {}, Pilmoji will download from internet on first use", twemoji_local_path)
            pilmoji_context = Pilmoji(result, cache=True)
            logger.info("Pilmoji initialized (will cache Twemoji after first download)")
    except Exception as e:
        logger.warning("Failed to initialize Pilmoji: {}, will use regular text rendering", e, exc_info=True)
        pilmoji_context = None
    
    if pilmoji_context:
        try:
            # Используем Pilmoji для рендеринга эмодзи
            logger.info("Starting text rendering with Pilmoji, {} lines to render", len(wrapped_lines))
            logger.info("Entering Pilmoji context manager...")
            try:
                with pilmoji_context as pilmoji:
                    logger.info("Pilmoji context entered successfully, starting to render lines")
                    # Инициализируем current_y начальным значением для первой строки
                    # Для первой строки используем text_y, для последующих - обновляем после каждой строки
                    current_y = text_y
                    for line_idx, line in enumerate(wrapped_lines):
                        logger.info("Rendering line {}/{}: '{}'", line_idx + 1, len(wrapped_lines), line[:50])
                        
                        # Рисуем обводку (если нужно) - сначала обводка, потом основной текст
                        if stroke > 0:
                            # Определяем цвет обводки (контрастный к тексту)
                            stroke_color = (0, 0, 0) if (text_color_name == "white" or text_color == COLORS.get("white", (255, 255, 255))) else (255, 255, 255)
                            # КРИТИЧНО: Если есть плашка, используем align="left"
                            text_align = "left" if box else align
                            # Обводка рисуется смещением в 8 направлениях
                            for dx in [-stroke, 0, stroke]:
                                for dy in [-stroke, 0, stroke]:
                                    if dx != 0 or dy != 0:
                                        try:
                                            pilmoji.text(
                                                (int(x + dx), int(current_y + dy)),
                                                line,
                                                font=final_font,
                                                fill=stroke_color,
                                                align=text_align,
                                            )
                                        except Exception as line_error:
                                            logger.warning("Error rendering stroke for line: {}, continuing", line_error)
                                            # Если ошибка на одной строке, продолжаем
                        
                        # Тень (если нужно)
                        if shadow:
                            try:
                                # КРИТИЧНО: Если есть плашка, используем align="left"
                                text_align = "left" if box else align
                                pilmoji.text(
                                    (int(x + 2), int(current_y + 2)),
                                    line,
                                    font=final_font,
                                    fill=(0, 0, 0, 128),
                                    align=text_align,
                                )
                            except Exception as line_error:
                                logger.warning("Error rendering shadow for line: {}", line_error)
                        
                        # Основной текст - разделяем на части: обычный текст и эмодзи
                        try:
                            logger.info("Rendering main text with color: {} (RGB: {}), x={}, y={}, line='{}', align={}", 
                                       text_color_name or "unknown", text_color, x, current_y, line[:30], align if not box else "left")
                            # КРИТИЧНО: Если есть плашка, текст должен быть внутри плашки
                            # Используем align="left" для ручного позиционирования, но позиция рассчитывается относительно плашки
                            # Если плашки нет, используем оригинальный align
                            text_align = "left" if box else align
                            
                            # Если есть плашка, убеждаемся, что текст рендерится внутри плашки
                            if box and box_x is not None:
                                # Текст должен начинаться внутри плашки (с учетом padding)
                                # current_y уже правильный (text_y), но нужно убедиться, что current_x тоже правильный
                                logger.info("Box present: box_x={}, box_width={}, text_x={}, current_y={}", 
                                           box_x, box_width, text_x, current_y)
                            
                            # Разделяем строку на части: обычный текст и эмодзи
                            # Паттерн для поиска эмодзи (Unicode ranges для эмодзи)
                            # Включаем дополнительные диапазоны для символов типа ❤️ (U+2764)
                            emoji_pattern = re.compile(
                                "["
                                "\U0001F600-\U0001F64F"  # Emoticons
                                "\U0001F300-\U0001F5FF"  # Misc Symbols and Pictographs
                                "\U0001F680-\U0001F6FF"  # Transport and Map
                                "\U0001F1E0-\U0001F1FF"  # Flags
                                "\U00002702-\U000027B0"   # Dingbats
                                "\U000024C2-\U0001F251"   # Enclosed characters
                                "\U00002764-\U0000279F"   # Additional symbols (❤️, etc.)
                                "\U0001F440-\U0001F4FF"   # Gestures and body parts (👍, 👎, etc.)
                                "\U0001F900-\U0001F9FF"   # Supplemental Symbols and Pictographs
                                "]+",
                                flags=re.UNICODE
                            )
                            
                            # Разделяем строку на части
                            parts = []
                            last_end = 0
                            for match in emoji_pattern.finditer(line):
                                # Добавляем текст до эмодзи
                                if match.start() > last_end:
                                    parts.append(("text", line[last_end:match.start()]))
                                # Добавляем эмодзи
                                parts.append(("emoji", match.group()))
                                last_end = match.end()
                            # Добавляем оставшийся текст
                            if last_end < len(line):
                                parts.append(("text", line[last_end:]))
                            
                            # Если нет эмодзи, просто рендерим весь текст
                            if not parts:
                                parts = [("text", line)]
                            
                            logger.info("Split line into {} parts (text/emoji)", len(parts))
                            
                            # Рендерим каждую часть соответствующим способом
                            # Для правильного позиционирования используем align только для первой части,
                            # остальные позиционируем относительно предыдущих
                            import time
                            render_start = time.time()
                            
                            # Вычисляем начальную позицию X в зависимости от align
                            # ВАЖНО: Если есть плашка, текст ДОЛЖЕН быть внутри плашки (с учетом padding)
                            if box and box_x is not None:
                                # Текст рендерится внутри плашки
                                # Вычисляем общую ширину всех частей (текст + эмодзи) для правильного центрирования
                                total_width = 0
                                for part_type, part_text in parts:
                                    if not part_text:
                                        continue
                                    if part_type == "text":
                                        bbox = draw.textbbox((0, 0), part_text, font=final_font)
                                        if bbox:
                                            total_width += bbox[2] - bbox[0]
                                        else:
                                            total_width += len(part_text) * (FONT_SIZES.get(size, 48) // 2)
                                    else:  # emoji
                                        # Для эмодзи используем текущий размер (может быть масштабирован)
                                        # Расширенный диапазон для подсчета эмодзи
                                        emoji_chars_count = sum(1 for char in part_text 
                                                               if (ord(char) >= 0x1F300 or 
                                                                   (ord(char) >= 0x2764 and ord(char) <= 0x279F) or
                                                                   (ord(char) >= 0x1F440 and ord(char) <= 0x1F4FF) or  # Gestures and body parts (👍, 👎, etc.)
                                                                   (ord(char) >= 0x1F900 and ord(char) <= 0x1F9FF)))
                                        if emoji_chars_count > 0:
                                            emoji_size = font_size
                                            max_emoji_width = int(img_width * max_width_ratio) - int(padding * 2)
                                            total_emoji_width = emoji_chars_count * emoji_size
                                            if total_emoji_width > max_emoji_width:
                                                emoji_size = int(max_emoji_width / emoji_chars_count)
                                            total_width += emoji_chars_count * emoji_size
                                        else:
                                            total_width += FONT_SIZES.get(size, 48)
                                
                                # Позиционируем текст внутри плашки в зависимости от align
                                if align == "center":
                                    # Центрируем относительно центра плашки
                                    current_x = int(box_x + box_width / 2) - total_width // 2
                                elif align == "right":
                                    # Выравниваем по правому краю плашки (с учетом padding)
                                    current_x = int(box_x + box_width - padding) - total_width
                                else:  # left
                                    # Выравниваем по левому краю плашки (с учетом padding)
                                    current_x = int(box_x + padding)
                                
                                # Проверяем границы изображения для текста
                                # Убеждаемся, что текст не выходит за левую границу
                                if current_x < 0:
                                    current_x = 0
                                # Убеждаемся, что текст не выходит за правую границу
                                if current_x + total_width > img_width:
                                    current_x = img_width - total_width
                                    # Если текст все еще не помещается, уменьшаем его размер
                                    if current_x < 0:
                                        logger.warning("Text too wide for image, may be clipped")
                                        current_x = 0
                                
                                logger.info("Text positioning inside box: box_x={}, box_width={}, total_width={}, current_x={}, align={}, img_width={}", 
                                           box_x, box_width, total_width, current_x, align, img_width)
                            else:
                                # Если плашки нет, позиционируем относительно изображения
                                if text_align == "center":
                                    # Для центрирования нужно вычислить общую ширину всех частей
                                    total_width = 0
                                    for part_type, part_text in parts:
                                        if not part_text:
                                            continue
                                        if part_type == "text":
                                            bbox = draw.textbbox((0, 0), part_text, font=final_font)
                                            if bbox:
                                                total_width += bbox[2] - bbox[0]
                                            else:
                                                total_width += len(part_text) * (FONT_SIZES.get(size, 48) // 2)
                                        else:  # emoji
                                            emoji_chars_count = sum(1 for char in part_text 
                                                                   if (ord(char) >= 0x1F300 or 
                                                                       (ord(char) >= 0x1F440 and ord(char) <= 0x1F4FF)))  # Gestures and body parts (👍, 👎, etc.)
                                            if emoji_chars_count > 0:
                                                emoji_size = font_size
                                                total_width += emoji_chars_count * emoji_size
                                            else:
                                                total_width += FONT_SIZES.get(size, 48)
                                    # Центрируем относительно центра изображения
                                    current_x = int(img_width / 2) - total_width // 2
                                    # Проверяем границы
                                    if current_x < 0:
                                        current_x = 0
                                    if current_x + total_width > img_width:
                                        current_x = img_width - total_width
                                        if current_x < 0:
                                            current_x = 0
                                elif text_align == "right":
                                    # Для правого выравнивания вычисляем общую ширину и начинаем справа
                                    total_width = 0
                                    for part_type, part_text in parts:
                                        if not part_text:
                                            continue
                                        if part_type == "text":
                                            bbox = draw.textbbox((0, 0), part_text, font=final_font)
                                            if bbox:
                                                total_width += bbox[2] - bbox[0]
                                            else:
                                                total_width += len(part_text) * (FONT_SIZES.get(size, 48) // 2)
                                        else:  # emoji
                                            emoji_chars_count = sum(1 for char in part_text 
                                                                   if (ord(char) >= 0x1F300 or 
                                                                       (ord(char) >= 0x1F440 and ord(char) <= 0x1F4FF)))  # Gestures and body parts (👍, 👎, etc.)
                                            if emoji_chars_count > 0:
                                                emoji_size = font_size
                                                total_width += emoji_chars_count * emoji_size
                                            else:
                                                total_width += FONT_SIZES.get(size, 48)
                                    current_x = int(img_width * max_width_ratio) - total_width
                                    # Проверяем границы
                                    if current_x < 0:
                                        current_x = 0
                                    if current_x + total_width > img_width:
                                        current_x = img_width - total_width
                                        if current_x < 0:
                                            current_x = 0
                                else:  # left
                                    current_x = int(img_width * (1 - max_width_ratio) / 2)
                                    # Проверяем границы
                                    if current_x < 0:
                                        current_x = 0
                                    if current_x + total_width > img_width:
                                        current_x = img_width - total_width
                                        if current_x < 0:
                                            current_x = 0
                            
                            for part_idx, (part_type, part_text) in enumerate(parts):
                                if not part_text:
                                    logger.debug("Skipping empty part {}", part_idx)
                                    continue
                                
                                logger.info("Processing part {}/{}: type={}, text='{}'", part_idx + 1, len(parts), part_type, part_text[:30])
                                
                                if part_type == "text":
                                    # Обычный текст - рендерим через обычный draw.text()
                                    logger.info("Rendering text part '{}' at x={}", part_text[:30], current_x)
                                    part_start = time.time()
                                    # Используем align только для первой части, остальные без align
                                    part_align = text_align if part_idx == 0 else "left"
                                    try:
                                        draw.text(
                                            (current_x, int(current_y)),
                                            part_text,
                                            font=final_font,
                                            fill=text_color,
                                            align=part_align,
                                        )
                                        text_elapsed = time.time() - part_start
                                        logger.info("Text part rendered in {:.3f}s", text_elapsed)
                                    except Exception as text_error:
                                        logger.error("Error rendering text part: {}", text_error, exc_info=True)
                                        raise
                                    
                                    # Вычисляем ширину текста для позиционирования следующей части
                                    bbox_start = time.time()
                                    bbox = draw.textbbox((0, 0), part_text, font=final_font)
                                    bbox_elapsed = time.time() - bbox_start
                                    if bbox:
                                        current_x += bbox[2] - bbox[0]
                                        logger.info("Text bbox calculated in {:.3f}s, width={}, current_x={}", bbox_elapsed, bbox[2] - bbox[0], current_x)
                                    else:
                                        current_x += len(part_text) * (FONT_SIZES.get(size, 48) // 2)
                                        logger.info("Text bbox failed, using estimate, current_x={}", current_x)
                                else:  # emoji
                                    # Эмодзи - рендерим через локальные Twemoji PNG файлы напрямую
                                    logger.info("Rendering emoji part '{}' with Twemoji PNG at x={}", part_text, current_x)
                                    emoji_start = time.time()
                                    try:
                                        # Используем локальные Twemoji PNG файлы для рендеринга эмодзи
                                        twemoji_local_path = PROJECT_ROOT / "assets" / "twemoji" / "72x72"
                                        
                                        if twemoji_local_path.exists():
                                            # Обрабатываем каждый эмодзи отдельно (строка может содержать несколько эмодзи)
                                            emoji_size = font_size
                                            
                                            # Выравниваем эмодзи по той же базовой линии, что и текст
                                            # Используем current_y напрямую для выравнивания по одной линии
                                            bbox = draw.textbbox((0, 0), "Ag", font=final_font)
                                            text_height = bbox[3] - bbox[1] if bbox else emoji_size
                                            # Центрируем эмодзи по высоте текста: базовая линия текста + половина высоты текста - половина размера эмодзи
                                            emoji_y = int(current_y + text_height / 2 - emoji_size / 2)
                                            
                                            # Сначала подсчитываем количество эмодзи и вычисляем общую ширину
                                            emoji_chars = []
                                            for char in part_text:
                                                # Пропускаем пробелы и другие не-эмодзи символы
                                                # Расширенный фильтр для эмодзи (включая ❤️ и другие символы)
                                                char_code = ord(char)
                                                if (char_code >= 0x1F300 or  # Основной диапазон эмодзи
                                                    (char_code >= 0x2764 and char_code <= 0x279F) or  # Дополнительные символы (❤️ и др.)
                                                    (char_code >= 0x1F440 and char_code <= 0x1F4FF) or  # Gestures and body parts (👍, 👎, etc.)
                                                    (char_code >= 0x1F900 and char_code <= 0x1F9FF)):  # Supplemental Symbols
                                                    code_point = ord(char)
                                                    emoji_code = f"{code_point:x}"
                                                    emoji_file = twemoji_local_path / f"{emoji_code}.png"
                                                    if emoji_file.exists():
                                                        emoji_chars.append(char)
                                            
                                            if emoji_chars:
                                                # Вычисляем максимальную доступную ширину для эмодзи
                                                img_width, img_height = result.size
                                                max_emoji_width = int(img_width * max_width_ratio) - int(padding * 2) if box else int(img_width * max_width_ratio)
                                                
                                                # Вычисляем общую ширину всех эмодзи
                                                total_emoji_width = len(emoji_chars) * emoji_size
                                                
                                                # Автомасштабирование: если эмодзи не помещаются, уменьшаем размер
                                                if total_emoji_width > max_emoji_width:
                                                    emoji_size = int(max_emoji_width / len(emoji_chars))
                                                    logger.info("Auto-scaling emojis: {} emojis, original size={}, scaled size={}, max_width={}", 
                                                               len(emoji_chars), FONT_SIZES.get(size, 48), emoji_size, max_emoji_width)
                                                
                                                # Эмодзи рендерятся последовательно после текста, используя current_x
                                                # НЕ центрируем отдельно - они должны идти сразу после текста
                                                emoji_x = current_x
                                                emoji_count = 0
                                                
                                                for char in emoji_chars:
                                                    code_point = ord(char)
                                                    emoji_code = f"{code_point:x}"
                                                    emoji_file = twemoji_local_path / f"{emoji_code}.png"
                                                    
                                                    try:
                                                        logger.debug("Found Twemoji PNG file: {} for emoji '{}'", emoji_file.name, char)
                                                        
                                                        # Загружаем PNG изображение эмодзи
                                                        emoji_img = Image.open(emoji_file)
                                                        
                                                        # Конвертируем в RGBA если нужно (для правильной прозрачности)
                                                        if emoji_img.mode != 'RGBA':
                                                            emoji_img = emoji_img.convert('RGBA')
                                                        
                                                        # Масштабируем до нужного размера
                                                        emoji_img = emoji_img.resize((emoji_size, emoji_size), Image.Resampling.LANCZOS)
                                                        
                                                        # Вставляем эмодзи на изображение (с маской для прозрачности)
                                                        result.paste(emoji_img, (emoji_x, emoji_y), emoji_img)
                                                        
                                                        # Переходим к следующему эмодзи
                                                        emoji_x += emoji_size
                                                        emoji_count += 1
                                                    except Exception as emoji_render_error:
                                                        logger.warning("Failed to render emoji '{}' (code: {}): {}", char, emoji_code, emoji_render_error)
                                                        # Пропускаем этот эмодзи и продолжаем
                                                        continue
                                                
                                                # Обновляем current_x для следующей части
                                                current_x = emoji_x
                                                
                                                if emoji_count > 0:
                                                    emoji_elapsed = time.time() - emoji_start
                                                    logger.info("Rendered {} emoji(s) successfully with Twemoji PNG in {:.3f}s, final_x={}", emoji_count, emoji_elapsed, current_x)
                                            else:
                                                logger.warning("No valid emojis found in string '{}'", part_text)
                                                # Fallback: рендерим эмодзи как обычный текст
                                                draw.text(
                                                    (current_x, int(current_y)),
                                                    part_text,
                                                    font=final_font,
                                                    fill=text_color,
                                                    align="left",
                                                )
                                                bbox = draw.textbbox((0, 0), part_text, font=final_font)
                                                if bbox:
                                                    current_x += bbox[2] - bbox[0]
                                                else:
                                                    current_x += FONT_SIZES.get(size, 48)
                                                emoji_elapsed = time.time() - emoji_start
                                                logger.info("Emoji fallback rendered in {:.3f}s", emoji_elapsed)
                                        else:
                                            logger.warning("Twemoji directory not found, using text fallback")
                                            # Fallback: рендерим эмодзи как обычный текст
                                            draw.text(
                                                (current_x, int(current_y)),
                                                part_text,
                                                font=final_font,
                                                fill=text_color,
                                                align="left",
                                            )
                                            bbox = draw.textbbox((0, 0), part_text, font=final_font)
                                            if bbox:
                                                current_x += bbox[2] - bbox[0]
                                            else:
                                                current_x += FONT_SIZES.get(size, 48)
                                            emoji_elapsed = time.time() - emoji_start
                                            logger.info("Emoji fallback rendered in {:.3f}s", emoji_elapsed)
                                    except Exception as emoji_error:
                                        emoji_elapsed = time.time() - emoji_start
                                        logger.error("Failed to render emoji '{}' after {:.3f}s: {}, using text fallback", part_text, emoji_elapsed, emoji_error, exc_info=True)
                                        # Fallback: рендерим эмодзи как обычный текст
                                        try:
                                            draw.text(
                                                (current_x, int(current_y)),
                                                part_text,
                            font=final_font,
                            fill=text_color,
                                                align="left",
                                            )
                                            bbox = draw.textbbox((0, 0), part_text, font=final_font)
                                            if bbox:
                                                current_x += bbox[2] - bbox[0]
                                            else:
                                                current_x += FONT_SIZES.get(size, 48)
                                            logger.info("Emoji fallback rendered successfully")
                                        except Exception as fallback_error:
                                            logger.error("Fallback rendering also failed: {}", fallback_error, exc_info=True)
                                            raise
                            
                            render_elapsed = time.time() - render_start
                            logger.info("Line {} rendered successfully in {:.2f}s ({} parts)", line_idx + 1, render_elapsed, len(parts))
                        except Exception as line_error:
                            logger.error("Error rendering main text for line: {}, switching to fallback", line_error, exc_info=True)
                            # Если ошибка критическая, переходим на fallback
                            raise line_error
                    
                        # Получаем высоту строки через textbbox
                        bbox = draw.textbbox((0, 0), "Ag", font=final_font)
                        line_height = bbox[3] - bbox[1] if bbox else 20  # Fallback на 20 если не удалось
                        
                        # Увеличиваем междустрочное расстояние для строк с эмодзи
                        # Проверяем, содержит ли строка эмодзи (расширенный диапазон)
                        has_emoji = any(
                            (ord(char) >= 0x1F300 or 
                             (ord(char) >= 0x2764 and ord(char) <= 0x279F) or
                             (ord(char) >= 0x1F440 and ord(char) <= 0x1F4FF) or  # Gestures and body parts (👍, 👎, etc.)
                             (ord(char) >= 0x1F900 and ord(char) <= 0x1F9FF))
                            for char in line
                        )
                        # Увеличиваем расстояние немного для строк с эмодзи (для лучшего визуального разделения)
                        spacing_multiplier = line_spacing * 1.2 if has_emoji else line_spacing
                        
                        # Обновляем current_y для следующей строки ПЕРЕД переходом к следующей итерации
                        current_y += int(line_height * spacing_multiplier)
                        logger.info("Line {} rendered, current_y updated to {} (has_emoji={}, spacing={:.2f})", 
                                   line_idx + 1, current_y, has_emoji, spacing_multiplier)
                
                logger.info("Text rendering with Pilmoji completed successfully, exiting context manager")
            except Exception as context_error:
                logger.error("Error in Pilmoji context manager: {}", context_error, exc_info=True)
                raise
        except Exception as e:
            logger.error("Error rendering with Pilmoji: {}, falling back to regular text", e, exc_info=True)
            # Fallback: рисуем текст без эмодзи через обычный draw
            pilmoji_context = None
    
    # Fallback: если Pilmoji не работает, используем обычный рендеринг без эмодзи
    if not pilmoji_context:
        logger.warning("Pilmoji not available, rendering text without emoji support (emojis will appear as squares)")
        current_y = y
        for line in wrapped_lines:
            # Draw stroke (if needed)
            if stroke > 0:
                # Determine stroke color (contrasting to text)
                stroke_color = (0, 0, 0) if (text_color_name == "white" or text_color == COLORS.get("white", (255, 255, 255))) else (255, 255, 255)
                # КРИТИЧНО: Если есть плашка, используем align="left"
                text_align = "left" if box else align
                for dx in [-stroke, 0, stroke]:
                    for dy in [-stroke, 0, stroke]:
                        if dx != 0 or dy != 0:
                            draw.text(
                                (x + dx, current_y + dy),
                                line,
                                font=final_font,
                                fill=stroke_color,
                                align=text_align,
                            )
            
            # Shadow (if needed)
            if shadow:
                # КРИТИЧНО: Если есть плашка, используем align="left"
                text_align = "left" if box else align
                draw.text(
                    (x + 2, current_y + 2),
                    line,
                    font=final_font,
                    fill=(0, 0, 0, 128),
                    align=text_align,
                )
            
            # Main text
            logger.debug("Rendering main text with color: {} (RGB: {}), align={}", 
                       text_color_name or "unknown", text_color, align if not box else "left")
            # КРИТИЧНО: Если есть плашка, используем align="left" и x рассчитан так,
            # чтобы текст был по центру плашки
            text_align = "left" if box else align
            
            # Используем обычный рендеринг без эмодзи (Pilmoji недоступен)
            draw.text(
                (x, current_y),
                line,
                font=final_font,
                fill=text_color,
                align=text_align,
            )
            
            # Get line height via textbbox
            bbox = draw.textbbox((0, 0), "Ag", font=final_font)
            line_height = bbox[3] - bbox[1] if bbox else 20  # Fallback to 20 if failed
            
            # Увеличиваем междустрочное расстояние для строк с эмодзи (расширенный диапазон)
            has_emoji = any(
                (ord(char) >= 0x1F300 or 
                 (ord(char) >= 0x2764 and ord(char) <= 0x279F) or
                 (ord(char) >= 0x1F440 and ord(char) <= 0x1F4FF) or  # Gestures and body parts (👍, 👎, etc.)
                 (ord(char) >= 0x1F900 and ord(char) <= 0x1F9FF))
                for char in line
            )
            spacing_multiplier = line_spacing * 1.2 if has_emoji else line_spacing
            current_y += int(line_height * spacing_multiplier)
    
    logger.info("render_text_box completed successfully, returning result image with size: {}", result.size)
    return result
