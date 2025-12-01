from __future__ import annotations

import time
from functools import lru_cache

from deep_translator import GoogleTranslator  # type: ignore[import]
from loguru import logger


@lru_cache(maxsize=1)
def _translator() -> GoogleTranslator:
    return GoogleTranslator(source="auto", target="en")


def translate_to_english(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return text
    
    # Проверяем, не является ли текст уже на английском (простая эвристика)
    # Если текст содержит только латинские символы и пробелы, возможно он уже на английском
    if cleaned.replace(" ", "").replace(",", "").replace(".", "").replace("!", "").replace("?", "").isascii():
        # Но все равно пытаемся перевести, так как может быть смешанный текст
        pass
    
    # Пробуем создать новый экземпляр переводчика каждый раз, чтобы избежать проблем с кэшированием
    translator = None
    try:
        logger.debug("Translating text: '{}'", cleaned[:100])
        start_time = time.time()
        
        # Пробуем использовать кэшированный переводчик
        translator = _translator()
        translated = translator.translate(cleaned)
        
        elapsed = time.time() - start_time
        if translated and translated.strip():
            logger.debug("Translation successful in {:.2f}s: '{}' -> '{}'", elapsed, cleaned[:50], translated[:50])
            return translated
        else:
            logger.warning("Translation returned empty result for '{}'", cleaned[:50])
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to translate prompt '{}': {} (type: {})", text[:100], exc, type(exc).__name__, exc_info=True)
        
        # Попробуем создать новый экземпляр переводчика
        try:
            logger.debug("Retrying translation with new translator instance")
            new_translator = GoogleTranslator(source="auto", target="en")
            translated = new_translator.translate(cleaned)
            if translated and translated.strip():
                logger.info("Translation succeeded with new translator instance: '{}' -> '{}'", cleaned[:50], translated[:50])
                return translated
        except Exception as retry_exc:  # noqa: BLE001
            logger.error("Retry translation also failed: {}", retry_exc)
    
    return text


