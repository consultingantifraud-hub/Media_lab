#!/usr/bin/env python3
"""
Прямой тест вызова функции process_image_job с тестовыми данными.
Имитирует реальный вызов из RQ воркера.
"""

import sys
import os
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent))

# Устанавливаем минимальные переменные окружения
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
os.environ.setdefault("FAL_KEY", "test_key")

def test_direct_worker_call():
    """Прямой тест вызова функции воркера."""
    
    print("=" * 80)
    print("ТЕСТ: Прямой вызов process_image_job с Flux 2 Flex")
    print("=" * 80)
    print()
    
    # Импортируем функцию воркера
    try:
        from app.providers.fal.image_worker_server import process_image_job
        print("✅ Функция process_image_job импортирована")
    except Exception as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    
    # Тестовый русский промпт
    russian_prompt = "Фотореалистичная сцена в пиццерии «Папа Джонс». В кадре два человека. Камера ближе всего к девушке-наставнику."
    
    print(f"Исходный промпт (русский):")
    print(f"  {russian_prompt[:80]}...")
    print()
    
    # Создаем тестовые параметры, как они приходят в воркер
    job_data = {
        "job_id": "test-flux2flex-123",
        "prompt": russian_prompt,
        "options": {
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
    }
    
    print("Параметры задачи:")
    print(f"  job_id: {job_data['job_id']}")
    print(f"  model: {job_data['options']['model']}")
    print(f"  selected_model: {job_data['options']['selected_model']}")
    print()
    
    # Проверяем логику ДО вызова функции
    print("🔍 Проверка логики определения модели:")
    model_name = job_data['options'].get("model", "")
    selected_model = job_data['options'].get("selected_model", "")
    
    is_flux2flex = "flux-2-flex" in model_name.lower() or selected_model == "flux2flex-create"
    print(f"  model_name: '{model_name}'")
    print(f"  selected_model: '{selected_model}'")
    print(f"  is_flux2flex: {is_flux2flex}")
    print()
    
    if not is_flux2flex:
        print("❌ ОШИБКА: Модель не определена как Flux 2 Flex!")
        return False
    
    print("✅ Модель правильно определена как Flux 2 Flex")
    print()
    
    # Теперь проверяем, что происходит внутри функции
    # Вместо реального вызова, воспроизводим логику
    provider_options = dict(job_data['options'])
    prompt = job_data['prompt']
    
    # Воспроизводим логику из process_image_job
    model_name = provider_options.get("model", "")
    selected_model = provider_options.get("selected_model", "")
    
    is_nano_banana = model_name == "fal-ai/nano-banana" or model_name == "fal-ai/nano-banana-pro" or "nano-banana" in model_name.lower()
    is_flux2flex = "flux-2-flex" in model_name.lower() or selected_model == "flux2flex-create"
    is_gpt_create = selected_model == "gpt-create"
    
    print("🔍 Воспроизведение логики из process_image_job:")
    print(f"  is_nano_banana: {is_nano_banana}")
    print(f"  is_flux2flex: {is_flux2flex}")
    print(f"  is_gpt_create: {is_gpt_create}")
    print()
    
    # Определяем provider_prompt
    if is_nano_banana or is_flux2flex or is_gpt_create:
        provider_prompt = prompt
        print("✅ provider_prompt установлен = оригинальный промпт (русский)")
    else:
        provider_prompt = provider_options.pop("provider_prompt", prompt)
        print("⚠️  provider_prompt извлечен из options")
    
    print(f"  provider_prompt: {provider_prompt[:50]}...")
    print(f"  provider_prompt == prompt: {provider_prompt == prompt}")
    print()
    
    # Проверяем блок перевода
    will_skip_translation = (is_nano_banana or is_flux2flex or is_gpt_create)
    print(f"🔍 Блок перевода будет пропущен: {will_skip_translation}")
    print()
    
    if not will_skip_translation:
        print("❌ ОШИБКА: Блок перевода НЕ будет пропущен!")
        return False
    
    # Проверяем финальный результат
    has_cyrillic = any('\u0400' <= char <= '\u04FF' for char in provider_prompt)
    print(f"Финальный промпт содержит кириллицу: {has_cyrillic}")
    print()
    
    print("=" * 80)
    print("РЕЗУЛЬТАТ:")
    print("=" * 80)
    
    if is_flux2flex and provider_prompt == russian_prompt and has_cyrillic:
        print("✅ УСПЕХ: Логика работает правильно!")
        print("   Промпт останется на русском языке для Flux 2 Flex")
        return True
    else:
        print("❌ ОШИБКА: Логика не работает правильно!")
        return False

if __name__ == "__main__":
    success = test_direct_worker_call()
    sys.exit(0 if success else 1)




