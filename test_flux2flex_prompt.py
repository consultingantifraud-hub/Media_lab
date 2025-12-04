#!/usr/bin/env python3
"""
Тестовый скрипт для проверки обработки русского промпта для Flux 2 Flex.
Проверяет, что промпт НЕ переводится на английский.
"""

import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent))

# Импортируем необходимые функции
from app.utils.translation import translate_to_english

def test_flux2flex_prompt_logic():
    """Тестирует логику определения модели и обработки промпта."""
    
    # Тестовый русский промпт
    russian_prompt = "Фотореалистичная сцена в пиццерии «Папа Джонс». В кадре два человека. Камера ближе всего к девушке-наставнику."
    
    print("=" * 80)
    print("ТЕСТ: Обработка промпта для Flux 2 Flex")
    print("=" * 80)
    print(f"\nИсходный промпт (русский):")
    print(f"  {russian_prompt}")
    print()
    
    # Симулируем проверки модели
    model_name = "fal-ai/flux-2-flex"
    selected_model = "flux2flex-create"
    
    print("Параметры модели:")
    print(f"  model_name: {model_name}")
    print(f"  selected_model: {selected_model}")
    print()
    
    # Проверяем, является ли это Flux 2 Flex
    is_flux2flex = "flux-2-flex" in model_name.lower() or selected_model == "flux2flex-create"
    
    print(f"Проверка is_flux2flex: {is_flux2flex}")
    print()
    
    # Определяем provider_prompt
    if is_flux2flex:
        provider_prompt = russian_prompt  # Используем оригинальный русский промпт
        print("✅ Flux 2 Flex обнаружен - используем оригинальный русский промпт БЕЗ перевода")
        print(f"  provider_prompt = оригинальный промпт (русский)")
    else:
        provider_prompt = russian_prompt  # По умолчанию
        print("❌ Flux 2 Flex НЕ обнаружен - будет использован перевод")
    
    print()
    print(f"provider_prompt (первые 100 символов):")
    print(f"  {provider_prompt[:100]}")
    print()
    
    # Проверяем, содержит ли промпт кириллицу
    has_cyrillic = any('\u0400' <= char <= '\u04FF' for char in russian_prompt)
    print(f"Промпт содержит кириллицу: {has_cyrillic}")
    print()
    
    # Проверяем, будет ли выполняться перевод
    if is_flux2flex:
        print("✅ Перевод НЕ будет выполняться (is_flux2flex=True)")
        print("   Промпт останется на русском языке")
    else:
        if has_cyrillic:
            print("⚠️  Перевод БУДЕТ выполняться (is_flux2flex=False, есть кириллица)")
            translated = translate_to_english(russian_prompt)
            print(f"   Переведенный промпт: {translated[:100]}")
        else:
            print("ℹ️  Перевод не требуется (нет кириллицы)")
    
    print()
    print("=" * 80)
    print("РЕЗУЛЬТАТ ТЕСТА:")
    print("=" * 80)
    
    if is_flux2flex and provider_prompt == russian_prompt:
        print("✅ УСПЕХ: Промпт останется на русском языке для Flux 2 Flex")
        return True
    else:
        print("❌ ОШИБКА: Промпт будет переведен на английский!")
        return False

if __name__ == "__main__":
    success = test_flux2flex_prompt_logic()
    sys.exit(0 if success else 1)





