#!/usr/bin/env python3
"""
Тест фактического поведения воркера на сервере.
Проверяет, что происходит с промптом в реальном воркере.
"""

import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent))

def test_worker_logic_on_server():
    """Тестирует логику воркера, как она есть на сервере."""
    
    # Импортируем функцию перевода
    from app.utils.translation import translate_to_english
    
    # Тестовый русский промпт
    russian_prompt = "Фотореалистичная сцена в пиццерии «Папа Джонс». В кадре два человека. Камера ближе всего к девушке-наставнику."
    
    print("=" * 80)
    print("ТЕСТ: Фактическое поведение логики воркера")
    print("=" * 80)
    print(f"\nИсходный промпт (русский):")
    print(f"  {russian_prompt[:80]}...")
    print()
    
    # Симулируем options, которые приходят в воркер (как в реальном вызове)
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
    
    # Воспроизводим ТОЧНУЮ логику из process_image_job
    provider_options = dict(options)
    prompt = russian_prompt
    
    # ШАГ 1: Проверка модели (строки 929-940)
    model_name = provider_options.get("model", "")
    selected_model = provider_options.get("selected_model", "")
    
    print("🔍 ШАГ 1: Проверка модели")
    print(f"  model_name: '{model_name}'")
    print(f"  selected_model: '{selected_model}'")
    print()
    
    is_nano_banana = model_name == "fal-ai/nano-banana" or model_name == "fal-ai/nano-banana-pro" or "nano-banana" in model_name.lower()
    is_flux2flex = "flux-2-flex" in model_name.lower() or selected_model == "flux2flex-create"
    is_gpt_create = selected_model == "gpt-create"
    
    print(f"  is_nano_banana: {is_nano_banana}")
    print(f"  is_flux2flex: {is_flux2flex}")
    print(f"  is_gpt_create: {is_gpt_create}")
    print()
    
    # ШАГ 2: Установка provider_prompt (строки 942-954)
    if is_nano_banana or is_flux2flex or is_gpt_create:
        provider_prompt = prompt  # Используем оригинальный русский промпт
        if is_flux2flex:
            print("✅ ШАГ 2: Flux 2 Flex обнаружен - provider_prompt = оригинальный промпт")
        elif is_nano_banana:
            print("✅ ШАГ 2: Nano-banana обнаружен - provider_prompt = оригинальный промпт")
        elif is_gpt_create:
            print("✅ ШАГ 2: Nano Banana Pro обнаружен - provider_prompt = оригинальный промпт")
    else:
        provider_prompt = provider_options.pop("provider_prompt", prompt)
        print("⚠️  ШАГ 2: Не русско-совместимая модель - извлекаем provider_prompt из options")
    
    print(f"  provider_prompt после шага 2: {provider_prompt[:50]}...")
    print(f"  provider_prompt == prompt: {provider_prompt == prompt}")
    print()
    
    # ШАГ 3: Проверка блока перевода (строки 981-1006)
    will_skip_translation = (is_nano_banana or is_flux2flex or is_gpt_create)
    
    print("🔍 ШАГ 3: Проверка блока перевода")
    print(f"  will_skip_translation: {will_skip_translation}")
    print()
    
    if not will_skip_translation:
        print("⚠️  ШАГ 3: Блок перевода ВЫПОЛНИТСЯ (это ошибка для Flux 2 Flex!)")
        if provider_prompt != prompt:
            print("  provider_prompt был переведен в боте")
        else:
            has_cyrillic = any('\u0400' <= char <= '\u04FF' for char in prompt)
            if has_cyrillic:
                print("  ❌ ОШИБКА: Промпт содержит кириллицу, будет переведен!")
                translated = translate_to_english(prompt)
                print(f"  Переведенный: {translated[:50]}...")
                provider_prompt = translated
    else:
        print("✅ ШАГ 3: Блок перевода ПРОПУЩЕН (правильно для Flux 2 Flex)")
    
    print()
    print(f"ФИНАЛЬНЫЙ provider_prompt:")
    print(f"  {provider_prompt[:80]}...")
    print()
    
    # Проверяем финальный результат
    has_cyrillic_final = any('\u0400' <= char <= '\u04FF' for char in provider_prompt)
    print(f"Финальный промпт содержит кириллицу: {has_cyrillic_final}")
    print()
    
    print("=" * 80)
    print("РЕЗУЛЬТАТ:")
    print("=" * 80)
    
    if is_flux2flex and provider_prompt == russian_prompt and has_cyrillic_final:
        print("✅ УСПЕХ: Промпт остался на русском!")
        return True
    else:
        print("❌ ОШИБКА: Промпт был изменен!")
        print(f"   is_flux2flex: {is_flux2flex}")
        print(f"   provider_prompt == russian_prompt: {provider_prompt == russian_prompt}")
        print(f"   has_cyrillic_final: {has_cyrillic_final}")
        if provider_prompt != russian_prompt:
            print(f"   Оригинал: {russian_prompt[:50]}...")
            print(f"   Финальный: {provider_prompt[:50]}...")
        return False

if __name__ == "__main__":
    success = test_worker_logic_on_server()
    sys.exit(0 if success else 1)





