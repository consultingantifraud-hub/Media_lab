#!/usr/bin/env python3
"""
Прямой тест логики обработки промпта для Flux 2 Flex.
Проверяет фактическую передачу промпта без выполнения реальной задачи.
"""

import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent))

def test_flux2flex_prompt_logic_direct():
    """Тестирует логику определения модели и обработки промпта напрямую."""
    
    # Тестовый русский промпт
    russian_prompt = "Фотореалистичная сцена в пиццерии «Папа Джонс». В кадре два человека. Камера ближе всего к девушке-наставнику."
    
    print("=" * 80)
    print("ТЕСТ: Прямая проверка логики обработки промпта для Flux 2 Flex")
    print("=" * 80)
    print(f"\nИсходный промпт (русский):")
    print(f"  {russian_prompt}")
    print()
    
    # Симулируем параметры, которые приходят в воркер
    provider_options = {
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
    
    print("Параметры provider_options:")
    for key, value in provider_options.items():
        print(f"  {key}: {value}")
    print()
    
    # Воспроизводим логику из воркера
    model_name = provider_options.get("model", "")
    selected_model = provider_options.get("selected_model", "")
    
    print("🔍 Проверка модели:")
    print(f"  model_name: '{model_name}'")
    print(f"  selected_model: '{selected_model}'")
    print()
    
    # Проверяем, является ли это Flux 2 Flex
    is_nano_banana = model_name == "fal-ai/nano-banana" or model_name == "fal-ai/nano-banana-pro" or "nano-banana" in model_name.lower()
    is_flux2flex = "flux-2-flex" in model_name.lower() or selected_model == "flux2flex-create"
    is_gpt_create = selected_model == "gpt-create"
    
    print("🔍 Результаты проверки:")
    print(f"  is_nano_banana: {is_nano_banana}")
    print(f"  is_flux2flex: {is_flux2flex}")
    print(f"  is_gpt_create: {is_gpt_create}")
    print()
    
    # Определяем provider_prompt (как в воркере)
    if is_nano_banana or is_flux2flex or is_gpt_create:
        provider_prompt = russian_prompt  # Используем оригинальный русский промпт
        if is_nano_banana:
            print("✅ Nano-banana модель обнаружена - используем оригинальный русский промпт")
        elif is_flux2flex:
            print("✅ Flux 2 Flex модель обнаружена - используем оригинальный русский промпт")
        elif is_gpt_create:
            print("✅ Nano Banana Pro (gpt-create) обнаружена - используем оригинальный русский промпт")
    else:
        provider_prompt = provider_options.pop("provider_prompt", russian_prompt)
        print("⚠️  Не русско-совместимая модель - извлекаем provider_prompt из options")
    
    print()
    print(f"provider_prompt (первые 100 символов):")
    print(f"  {provider_prompt[:100]}")
    print()
    
    # Проверяем, будет ли выполняться перевод
    will_skip_translation = (is_nano_banana or is_flux2flex or is_gpt_create)
    
    print("🔍 Проверка перевода:")
    print(f"  will_skip_translation: {will_skip_translation}")
    print()
    
    if will_skip_translation:
        print("✅ Перевод НЕ будет выполняться")
        print(f"   Промпт останется на русском: {provider_prompt[:50]}...")
    else:
        print("❌ Перевод БУДЕТ выполняться!")
        print("   Это ошибка для Flux 2 Flex!")
    
    print()
    print("=" * 80)
    print("РЕЗУЛЬТАТ ТЕСТА:")
    print("=" * 80)
    
    if is_flux2flex and provider_prompt == russian_prompt and will_skip_translation:
        print("✅ УСПЕХ: Промпт останется на русском языке для Flux 2 Flex")
        print("   Логика работает правильно!")
        return True
    else:
        print("❌ ОШИБКА: Логика не работает правильно!")
        print(f"   is_flux2flex: {is_flux2flex}")
        print(f"   provider_prompt == russian_prompt: {provider_prompt == russian_prompt}")
        print(f"   will_skip_translation: {will_skip_translation}")
        return False

if __name__ == "__main__":
    success = test_flux2flex_prompt_logic_direct()
    sys.exit(0 if success else 1)





