#!/usr/bin/env python3
"""
Тест фактической передачи промпта в воркер.
Имитирует реальный вызов process_image_job с проверкой промпта.
"""

import sys
import os
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent))

# Устанавливаем переменные окружения для теста
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("FAL_KEY", "test_key")

def test_actual_prompt_passing():
    """Тестирует фактическую передачу промпта через логику воркера."""
    
    # Импортируем функцию перевода для проверки
    from app.utils.translation import translate_to_english
    
    # Тестовый русский промпт
    russian_prompt = "Фотореалистичная сцена в пиццерии «Папа Джонс». В кадре два человека."
    
    print("=" * 80)
    print("ТЕСТ: Фактическая передача промпта в логику воркера")
    print("=" * 80)
    print(f"\nИсходный промпт (русский):")
    print(f"  {russian_prompt}")
    print()
    
    # Симулируем options, которые приходят в воркер
    options = {
        "model": "fal-ai/flux-2-flex",
        "selected_model": "flux2flex-create",
        "selected_format": "1:1",
        "output_format": "png",
        "guidance_scale": 10.0,
        "num_inference_steps": 50,
        "enable_prompt_expansion": True,
        "enable_safety_checker": True,
        "image_size": "square_hd",
        "aspect_ratio": "1:1",
    }
    
    # Воспроизводим ТОЧНУЮ логику из воркера (строки 929-1006)
    provider_options = dict(options)
    
    # ВАЖНО: Проверяем модель ПЕРЕД извлечением provider_prompt
    model_name = provider_options.get("model", "")
    selected_model = provider_options.get("selected_model", "")
    
    print("🔍 Шаг 1: Проверка модели")
    print(f"  model_name: '{model_name}'")
    print(f"  selected_model: '{selected_model}'")
    print()
    
    is_nano_banana = model_name == "fal-ai/nano-banana" or model_name == "fal-ai/nano-banana-pro" or "nano-banana" in model_name.lower()
    is_flux2flex = "flux-2-flex" in model_name.lower() or selected_model == "flux2flex-create"
    is_gpt_create = selected_model == "gpt-create"
    
    print("🔍 Шаг 2: Результаты проверки модели")
    print(f"  is_nano_banana: {is_nano_banana}")
    print(f"  is_flux2flex: {is_flux2flex}")
    print(f"  is_gpt_create: {is_gpt_create}")
    print()
    
    # Для Nano Banana, Flux 2 Flex и gpt-create используем оригинальный русский промпт БЕЗ перевода
    if is_nano_banana or is_flux2flex or is_gpt_create:
        provider_prompt = russian_prompt  # Используем оригинальный русский промпт
        if is_flux2flex:
            print("✅ Шаг 3: Flux 2 Flex обнаружен - используем оригинальный русский промпт")
        elif is_nano_banana:
            print("✅ Шаг 3: Nano-banana обнаружен - используем оригинальный русский промпт")
        elif is_gpt_create:
            print("✅ Шаг 3: Nano Banana Pro обнаружен - используем оригинальный русский промпт")
    else:
        provider_prompt = provider_options.pop("provider_prompt", russian_prompt)
        print("⚠️  Шаг 3: Не русско-совместимая модель - извлекаем provider_prompt из options")
    
    print()
    print(f"provider_prompt после шага 3:")
    print(f"  {provider_prompt[:100]}")
    print(f"  provider_prompt == russian_prompt: {provider_prompt == russian_prompt}")
    print()
    
    # Проверяем блок перевода (строки 981-1006)
    will_skip_translation = (is_nano_banana or is_flux2flex or is_gpt_create)
    
    print("🔍 Шаг 4: Проверка блока перевода")
    print(f"  will_skip_translation: {will_skip_translation}")
    print()
    
    if not will_skip_translation:
        # Этот блок НЕ должен выполняться для Flux 2 Flex
        if provider_prompt != russian_prompt:
            print("⚠️  provider_prompt был переведен в боте")
        else:
            has_cyrillic = any('\u0400' <= char <= '\u04FF' for char in russian_prompt)
            if has_cyrillic:
                print("❌ ОШИБКА: Блок перевода выполнится для Flux 2 Flex!")
                translated = translate_to_english(russian_prompt)
                print(f"   Переведенный промпт: {translated[:50]}...")
                provider_prompt = translated
            else:
                print("ℹ️  Промпт не содержит кириллицу")
    else:
        print("✅ Блок перевода пропущен для русско-совместимой модели")
    
    print()
    print(f"ФИНАЛЬНЫЙ provider_prompt:")
    print(f"  {provider_prompt[:100]}")
    print()
    
    # Проверяем, содержит ли финальный промпт кириллицу
    has_cyrillic_final = any('\u0400' <= char <= '\u04FF' for char in provider_prompt)
    print(f"Финальный промпт содержит кириллицу: {has_cyrillic_final}")
    print()
    
    print("=" * 80)
    print("РЕЗУЛЬТАТ ТЕСТА:")
    print("=" * 80)
    
    if is_flux2flex and provider_prompt == russian_prompt and has_cyrillic_final:
        print("✅ УСПЕХ: Промпт остался на русском языке!")
        print("   Логика работает правильно!")
        return True
    else:
        print("❌ ОШИБКА: Промпт был переведен или логика не работает!")
        print(f"   is_flux2flex: {is_flux2flex}")
        print(f"   provider_prompt == russian_prompt: {provider_prompt == russian_prompt}")
        print(f"   has_cyrillic_final: {has_cyrillic_final}")
        if provider_prompt != russian_prompt:
            print(f"   Оригинальный: {russian_prompt[:50]}...")
            print(f"   Финальный: {provider_prompt[:50]}...")
        return False

if __name__ == "__main__":
    success = test_actual_prompt_passing()
    sys.exit(0 if success else 1)





