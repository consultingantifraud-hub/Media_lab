from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from app.core.formats import FORMAT_ORDER, ImageFormat

# Основные кнопки главного меню
CREATE_BUTTON = "🎨 Создать"
PROMPT_WRITER_BUTTON = "✍️ Написать"
IMAGE_EDIT_BUTTON = "✏️ Редактировать"
IMAGE_SMART_MERGE_BUTTON = "✏️ Изменить"
IMAGE_RETOUCHER_BUTTON = "✨ Ретушь"
IMAGE_STYLISH_TEXT_BUTTON = "📝 Добавить текст"
IMAGE_FACE_SWAP_BUTTON = "🔄 Заменить лицо"
IMAGE_UPSCALE_BUTTON = "⬆️ Улучшить"
INFO_BUTTON = "ℹ️ Info"
HELP_BUTTON = "🆘 Помощь"
BALANCE_BUTTON = "💰 Баланс"

# Кнопки выбора модели для замены лица
IMAGE_FACE_SWAP_BASIC_BUTTON = "🔄 Face Swap"
IMAGE_FACE_SWAP_ADVANCED_BUTTON = "🔄 WaveSpeed Face Swap"  # Высокое качество замены лица через WaveSpeedAI

# Кнопки выбора моделей для создания
IMAGE_STANDARD_BUTTON = "Nano Banana"  # Используется для выбора модели после "Создать"
IMAGE_SEEDREAM_CREATE_BUTTON = "Seedream"  # Используется для выбора модели после "Создать"
IMAGE_GPT_CREATE_BUTTON = "Nano Banana Pro"  # Nano Banana Pro через Fal.ai - лучшее качество кириллицы
IMAGE_FLUX2FLEX_CREATE_BUTTON = "Flux 2 Flex"  # Flux 2 Flex через Fal.ai

# Кнопки редактирования
IMAGE_EDIT_CHRONO_BUTTON = "Chrono Edit"
IMAGE_EDIT_SEDEDIT_BUTTON = "Seedream"
IMAGE_EDIT_FLUX2PRO_BUTTON = "Flux 2 Pro"

# Кнопки Smart merge (используем уникальные названия, чтобы избежать конфликта с кнопками создания)
IMAGE_SMART_MERGE_PRO_BUTTON = "Nano Banana Pro edit"
IMAGE_SMART_MERGE_FLUX2PRO_BUTTON = "Flux 2 Pro edit"
IMAGE_SMART_MERGE_NANO_BUTTON = "Nano Banana edit"
IMAGE_SMART_MERGE_SEEDREAM_BUTTON = "Seedream edit"

# Кнопки выбора качества для Nano Banana Pro edit
QUALITY_FASTER_BUTTON = "⚡ Быстрее"
QUALITY_BETTER_BUTTON = "🎨 Качественнее"

# Кнопки ретуши
RETOUCHER_SOFT_BUTTON = "Мягкая ретушь"
RETOUCHER_ENHANCE_BUTTON = "Усилить черты"
RETOUCHER_SKIP_BUTTON = "Пропустить"

# Кнопки выбора формата (старые, для обратной совместимости)
IMAGE_SIZE_VERTICAL_BUTTON = "Вертикальное"
IMAGE_SIZE_SQUARE_BUTTON = "Квадрат"
IMAGE_SIZE_HORIZONTAL_BUTTON = "Горизонтальное"

# Новые кнопки форматов (единая система)
IMAGE_FORMAT_SQUARE_1_1 = "🔲 1:1"
IMAGE_FORMAT_VERTICAL_3_4 = "📱 3:4"
IMAGE_FORMAT_HORIZONTAL_4_3 = "🖼️ 4:3"
IMAGE_FORMAT_VERTICAL_4_5 = "📱 4:5"
IMAGE_FORMAT_VERTICAL_9_16 = "📹 9:16"
IMAGE_FORMAT_HORIZONTAL_16_9 = "📺 16:9"


def build_main_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=CREATE_BUTTON), KeyboardButton(text=PROMPT_WRITER_BUTTON)],
        [KeyboardButton(text=IMAGE_SMART_MERGE_BUTTON), KeyboardButton(text=IMAGE_RETOUCHER_BUTTON)],
        [KeyboardButton(text=IMAGE_STYLISH_TEXT_BUTTON), KeyboardButton(text=IMAGE_FACE_SWAP_BUTTON)],
        [KeyboardButton(text=IMAGE_UPSCALE_BUTTON), KeyboardButton(text=BALANCE_BUTTON)],
        [KeyboardButton(text=INFO_BUTTON), KeyboardButton(text=HELP_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Напишите промпт или используйте кнопку «✍️ Написать»",
    )


def build_size_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора формата (старая версия для обратной совместимости)."""
    buttons = [
        [
            KeyboardButton(text=IMAGE_SIZE_VERTICAL_BUTTON),
            KeyboardButton(text=IMAGE_SIZE_SQUARE_BUTTON),
            KeyboardButton(text=IMAGE_SIZE_HORIZONTAL_BUTTON),
        ],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите формат изображения",
    )


def build_format_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора формата (новая единая система из 6 форматов).
    
    Порядок форматов по популярности:
    1. Квадрат 1:1 (универсальный)
    2. Вертикальное 3:4 (WB/Ozon)
    3. Горизонтальное 4:3 (Авито)
    4. Вертикальное 4:5 (Instagram)
    5. Вертикальное 9:16 (сторис/рилс)
    6. Горизонтальное 16:9 (баннеры)
    """
    buttons = [
        [
            KeyboardButton(text=IMAGE_FORMAT_SQUARE_1_1),
            KeyboardButton(text=IMAGE_FORMAT_VERTICAL_3_4),
        ],
        [
            KeyboardButton(text=IMAGE_FORMAT_HORIZONTAL_4_3),
            KeyboardButton(text=IMAGE_FORMAT_VERTICAL_4_5),
        ],
        [
            KeyboardButton(text=IMAGE_FORMAT_VERTICAL_9_16),
            KeyboardButton(text=IMAGE_FORMAT_HORIZONTAL_16_9),
        ],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите формат изображения",
    )


def build_edit_model_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=IMAGE_EDIT_CHRONO_BUTTON), KeyboardButton(text=IMAGE_EDIT_SEDEDIT_BUTTON)],
        [KeyboardButton(text=IMAGE_EDIT_FLUX2PRO_BUTTON)],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите модель редактирования",
    )


def build_retoucher_mode_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=RETOUCHER_SOFT_BUTTON), KeyboardButton(text=RETOUCHER_ENHANCE_BUTTON)],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите режим ретуши",
    )


def build_retoucher_instruction_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=RETOUCHER_SKIP_BUTTON)],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Добавьте инструкцию или пропустите",
    )


def build_quality_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора качества для Nano Banana Pro edit."""
    buttons = [
        [
            KeyboardButton(text=QUALITY_FASTER_BUTTON),
            KeyboardButton(text=QUALITY_BETTER_BUTTON),
        ],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите режим качества",
    )


def build_smart_merge_model_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора модели для изменения изображений.
    
    Порядок моделей (формат 2x2):
    Ряд 1: Nano Banana Pro edit, [Flux 2 Pro edit - временно отключен]
    Ряд 2: Nano Banana edit, Seedream edit
    """
    buttons = [
        [KeyboardButton(text=IMAGE_SMART_MERGE_PRO_BUTTON)],  # Ряд 1: Nano Banana Pro (Flux 2 Pro временно отключен)
        [KeyboardButton(text=IMAGE_SMART_MERGE_NANO_BUTTON), KeyboardButton(text=IMAGE_SMART_MERGE_SEEDREAM_BUTTON)],  # Ряд 2: Nano Banana, Seedream
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите модель для изменения",
    )


def build_create_model_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора модели после нажатия 'Создать'.
    
    Раскладка кнопок (2x2):
    Верхний ряд: Nano Banana Pro, Flux 2 Flex
    Нижний ряд: Nano Banana, Seedream
    """
    buttons = [
        [KeyboardButton(text=IMAGE_GPT_CREATE_BUTTON), KeyboardButton(text=IMAGE_FLUX2FLEX_CREATE_BUTTON)],  # Верхний ряд: Nano Banana Pro, Flux 2 Flex
        [KeyboardButton(text=IMAGE_STANDARD_BUTTON), KeyboardButton(text=IMAGE_SEEDREAM_CREATE_BUTTON)],   # Нижний ряд: Nano Banana, Seedream
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите модель для создания изображения",
    )


def build_face_swap_model_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора модели для замены лица."""
    buttons = [
        [KeyboardButton(text=IMAGE_FACE_SWAP_BASIC_BUTTON), KeyboardButton(text=IMAGE_FACE_SWAP_ADVANCED_BUTTON)],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите модель для замены лица",
    )


# Кнопки помощи
HELP_AI_ASSISTANT_BUTTON = "🤖 ИИ-помощник"
HELP_SUPPORT_BUTTON = "💬 Вопрос разработчикам"


def build_help_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура меню помощи."""
    buttons = [
        [KeyboardButton(text=HELP_AI_ASSISTANT_BUTTON)],
        [KeyboardButton(text=HELP_SUPPORT_BUTTON)],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите тип помощи",
    )
