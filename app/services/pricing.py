"""Pricing service for different operation types."""
from typing import Dict, Optional, Tuple
import os
from loguru import logger

# Base prices from environment or defaults
PRICE_NANO_BANANA_PRO = float(os.getenv("PRICE_NANO_BANANA_PRO", "26"))
PRICE_OTHER_MODELS = float(os.getenv("PRICE_OTHER_MODELS", "9"))
PRICE_SEEDREAM = float(os.getenv("PRICE_SEEDREAM", "7.5"))  # Цена для Seedream в операциях generate и edit
PRICE_PROMPT_GENERATION = float(os.getenv("PRICE_PROMPT_GENERATION", "3"))
PRICE_FACE_SWAP = float(os.getenv("PRICE_FACE_SWAP", "4"))
PRICE_ADD_TEXT = float(os.getenv("PRICE_ADD_TEXT", "1"))

# Operation type to price mapping
OPERATION_PRICES: Dict[str, float] = {
    "generate_nano_banana_pro": PRICE_NANO_BANANA_PRO,
    "generate_other": PRICE_OTHER_MODELS,
    "prompt_generation": PRICE_PROMPT_GENERATION,
    "face_swap": PRICE_FACE_SWAP,
    "add_text": PRICE_ADD_TEXT,
    # Legacy operation types (for backward compatibility)
    "generate": PRICE_OTHER_MODELS,  # Default to other models price
    "edit": PRICE_OTHER_MODELS,
    "merge": PRICE_OTHER_MODELS,
    "retouch": PRICE_OTHER_MODELS,  # Retouch always uses default price, not Seedream price
    "upscale": PRICE_OTHER_MODELS,
}

# Human-readable operation names
OPERATION_NAMES: Dict[str, str] = {
    "generate": "Генерация изображения",
    "generate_nano_banana_pro": "Генерация (Nano Banana Pro)",
    "generate_other": "Генерация изображения",
    "edit": "Редактирование изображения",
    "merge": "Изменить",
    "retouch": "Ретушь",
    "upscale": "Улучшение качества",
    "prompt_generation": "Генерация промпта",
    "face_swap": "Замена лица",
    "add_text": "Добавление текста",
}

# Operation type descriptions for pricing display
OPERATION_DESCRIPTIONS: Dict[str, str] = {
    "generate": "Генерация изображения (Nano Banana Pro: 26₽, Seedream: 7.5₽, другие модели: 9₽)",
    "edit": "Редактирование изображения (Seedream: 7.5₽, другие модели: 9₽)",
    "merge": "Объединение изображений (Nano Banana Pro: 26₽, другие модели: 9₽)",
    "retouch": "Ретушь (9₽)",
    "upscale": "Улучшение качества",
    "prompt_generation": "Генерация промпта (кнопка «Написать»)",
    "face_swap": "Замена лица",
    "add_text": "Добавление текста (кнопка «Добавить текст»)",
}


def get_operation_price(
    operation_type: str,
    model: Optional[str] = None,
    is_nano_banana_pro: bool = False
) -> float:
    """
    Get price for operation type.
    
    Args:
        operation_type: Type of operation (generate, edit, merge, etc.)
        model: Model name (optional, for determining Nano Banana Pro or Seedream)
        is_nano_banana_pro: Explicit flag if it's Nano Banana Pro
        
    Returns:
        float: Price in rubles
    """
    # Check if it's Seedream model (only for generate and edit, not retouch)
    is_seedream = _is_seedream_model(model)
    
    # Check if it's Nano Banana Pro generation or merge
    if operation_type == "generate":
        if is_nano_banana_pro or (model and _is_nano_banana_pro_model(model)):
            return OPERATION_PRICES["generate_nano_banana_pro"]
        if is_seedream:
            return PRICE_SEEDREAM  # 7.5 рублей для Seedream
        return OPERATION_PRICES["generate_other"]
    
    # Check if it's edit operation
    if operation_type == "edit":
        if is_seedream:
            return PRICE_SEEDREAM  # 7.5 рублей для Seedream edit
        return OPERATION_PRICES["edit"]
    
    # Check if it's Nano Banana Pro merge
    if operation_type == "merge":
        if is_nano_banana_pro or (model and _is_nano_banana_pro_model(model)):
            return OPERATION_PRICES["generate_nano_banana_pro"]  # 26 рублей для Nano Banana Pro merge
        # Проверяем, является ли модель Seedream для merge
        if is_seedream:
            return PRICE_SEEDREAM  # 7.5 рублей для Seedream merge
        return OPERATION_PRICES["generate_other"]  # 9 рублей для других моделей merge
    
    # Check for specific operation types (retouch uses default price, not Seedream price)
    if operation_type in OPERATION_PRICES:
        return OPERATION_PRICES[operation_type]
    
    # Default to other models price
    logger.warning(f"Unknown operation type: {operation_type}, using default price")
    return OPERATION_PRICES["generate_other"]


def get_operation_name(operation_type: str) -> str:
    """Get human-readable operation name."""
    return OPERATION_NAMES.get(operation_type, operation_type)


def get_operation_description(operation_type: str) -> str:
    """Get operation description for pricing display."""
    return OPERATION_DESCRIPTIONS.get(operation_type, operation_type)


def get_all_prices() -> Dict[str, float]:
    """Get all operation prices for display."""
    return {
        "Nano Banana Pro (генерация/объединение)": PRICE_NANO_BANANA_PRO,
        "Seedream (генерация/редактирование)": PRICE_SEEDREAM,
        "Nano Banana (генерация/редактирование)": PRICE_OTHER_MODELS,
        "Остальные модели (генерация/редактирование/объединение/ретушь/upscale)": PRICE_OTHER_MODELS,
        "Генерация промпта": PRICE_PROMPT_GENERATION,
        "Замена лица": PRICE_FACE_SWAP,
        "Добавление текста": PRICE_ADD_TEXT,
    }


def _is_nano_banana_pro_model(model: str) -> bool:
    """Check if model is Nano Banana Pro."""
    if not model:
        return False
    
    model_lower = model.lower()
    return (
        "nano-banana-pro" in model_lower or
        "nano_banana_pro" in model_lower or
        "gpt-image-1-mini" in model_lower or
        model == "fal-ai/nano-banana-pro" or
        model == "fal-ai/nano-banana-pro/edit"
    )


def _is_seedream_model(model: Optional[str]) -> bool:
    """Check if model is Seedream."""
    if not model:
        return False
    
    model_lower = model.lower()
    return (
        "seedream" in model_lower or
        "bytedance/seedream" in model_lower or
        model == "fal-ai/bytedance/seedream/v4/text-to-image" or
        model == "fal-ai/bytedance/seedream/v4/edit" or
        model == "seedream-create"
    )


def apply_discount(price: float, discount_percent: int) -> float:
    """
    Apply discount percentage to price.
    
    Args:
        price: Original price in rubles
        discount_percent: Discount percentage (10, 20, 30, etc.)
        
    Returns:
        float: Discounted price in rubles (rounded to 2 decimal places)
    """
    if discount_percent <= 0:
        return price
    
    # Calculate discount amount with proper rounding
    discount_amount = round(price * discount_percent / 100, 2)
    discounted_price = price - discount_amount
    
    # Ensure price is at least 0.01 ruble
    return max(0.01, round(discounted_price, 2))


def get_price_with_discount(
    operation_type: str,
    discount_percent: Optional[int] = None,
    model: Optional[str] = None,
    is_nano_banana_pro: bool = False
) -> Tuple[float, float]:
    """
    Get price with discount applied.
    
    Returns:
        Tuple[float, float]: (final_price, discount_amount) - prices in rubles with kopecks
    """
    base_price = get_operation_price(operation_type, model, is_nano_banana_pro)
    
    if discount_percent and discount_percent > 0:
        # Calculate discount amount without rounding - keep exact value
        discount_amount = base_price * discount_percent / 100
        final_price = base_price - discount_amount
        # Ensure price is at least 0.01 ruble
        final_price = max(0.01, final_price)
        return final_price, discount_amount
    
    return float(base_price), 0.0
