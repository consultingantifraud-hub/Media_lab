from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

# Основные кнопки главного меню
CREATE_BUTTON = "🎨 Создать"
IMAGE_EDIT_BUTTON = "✏️ Редактировать"
IMAGE_SMART_MERGE_BUTTON = "🔗 Объединить ➕ Добавить"
IMAGE_RETOUCHER_BUTTON = "✨ Ретушь"
IMAGE_STYLISH_TEXT_BUTTON = "📝 Добавить текст"
IMAGE_FACE_SWAP_BUTTON = "🔄 Заменить лицо"
IMAGE_UPSCALE_BUTTON = "⬆️ Улучшить"
INFO_BUTTON = "ℹ️ Info"

# Кнопки выбора модели для замены лица
IMAGE_FACE_SWAP_BASIC_BUTTON = "🔄 Face Swap"
IMAGE_FACE_SWAP_ADVANCED_BUTTON = "🔄 WaveSpeed Face Swap"  # Высокое качество замены лица через WaveSpeedAI

# Кнопки выбора моделей для создания
IMAGE_STANDARD_BUTTON = "Nano-banana"  # Используется для выбора модели после "Создать"
IMAGE_SEEDREAM_CREATE_BUTTON = "Seedream (Create)"  # Используется для выбора модели после "Создать"
IMAGE_GPT_CREATE_BUTTON = "Nano Banana Pro"  # Nano Banana Pro через Fal.ai - лучшее качество кириллицы

# Кнопки редактирования
IMAGE_EDIT_CHRONO_BUTTON = "Chrono Edit"
IMAGE_EDIT_SEDEDIT_BUTTON = "Seedream"

# Кнопки Smart merge (используем уникальные названия, чтобы избежать конфликта с кнопками создания)
IMAGE_SMART_MERGE_NANO_BUTTON = "Nano-Banana (Merge)"
IMAGE_SMART_MERGE_SEEDREAM_BUTTON = "Seedream (Merge)"

# Кнопки ретуши
RETOUCHER_SOFT_BUTTON = "Мягкая ретушь"
RETOUCHER_ENHANCE_BUTTON = "Усилить черты"
RETOUCHER_SKIP_BUTTON = "Пропустить"

IMAGE_SIZE_VERTICAL_BUTTON = "Вертикальное"
IMAGE_SIZE_SQUARE_BUTTON = "Квадрат"
IMAGE_SIZE_HORIZONTAL_BUTTON = "Горизонтальное"


def build_main_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=CREATE_BUTTON)],
        [KeyboardButton(text=IMAGE_EDIT_BUTTON), KeyboardButton(text=IMAGE_SMART_MERGE_BUTTON)],
        [KeyboardButton(text=IMAGE_RETOUCHER_BUTTON), KeyboardButton(text=IMAGE_STYLISH_TEXT_BUTTON)],
        [KeyboardButton(text=IMAGE_FACE_SWAP_BUTTON), KeyboardButton(text=IMAGE_UPSCALE_BUTTON)],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Сначала напишите промпт, затем выберите модель",
    )


def build_size_keyboard() -> ReplyKeyboardMarkup:
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


def build_edit_model_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=IMAGE_EDIT_CHRONO_BUTTON), KeyboardButton(text=IMAGE_EDIT_SEDEDIT_BUTTON)],
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


def build_smart_merge_model_keyboard() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text=IMAGE_SMART_MERGE_NANO_BUTTON), KeyboardButton(text=IMAGE_SMART_MERGE_SEEDREAM_BUTTON)],
        [KeyboardButton(text=INFO_BUTTON)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите модель для Smart merge",
    )


def build_create_model_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура выбора модели после нажатия 'Создать'."""
    buttons = [
        [KeyboardButton(text=IMAGE_GPT_CREATE_BUTTON)],  # Nano Banana Pro - первая (приоритет)
        [KeyboardButton(text=IMAGE_STANDARD_BUTTON)],  # Nano-banana - вторая
        [KeyboardButton(text=IMAGE_SEEDREAM_CREATE_BUTTON)],  # Seedream (Create) - третья
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
