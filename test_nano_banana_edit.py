"""
Тестовый скрипт для проверки получения результата Nano Banana edit
"""
import sys
sys.path.insert(0, '/app')

from app.providers.fal.images import resolve_result_asset, _TASK_CACHE
from app.providers.fal.client import queue_status, queue_get, _build_queue_url

# Тестовый request_id из логов
test_request_id = "b0b36687-7677-458e-a141-02ed0d7a9150"
test_result_url = f"https://queue.fal.run/fal-ai/nano-banana/requests/{test_request_id}"

print(f"Тестирование получения результата для Nano Banana edit")
print(f"Request ID: {test_request_id}")
print(f"Result URL: {test_result_url}")
print()

# Проверяем кэш
cache_entry = _TASK_CACHE.get(test_request_id, {})
cached_model = cache_entry.get("model")
print(f"Модель в кэше: {cached_model}")
print()

if cached_model and "nano-banana" in cached_model.lower() and "/edit" in cached_model.lower():
    print(f"Используем модель из кэша: {cached_model}")
    
    # Тест 1: queue_status
    print("\n=== Тест 1: queue_status ===")
    try:
        status_data = queue_status(cached_model, test_request_id)
        print(f"Статус получен: {list(status_data.keys()) if isinstance(status_data, dict) else 'not a dict'}")
        if isinstance(status_data, dict):
            print(f"Статус: {status_data.get('status')}")
            print(f"Response URL: {status_data.get('response_url')}")
    except Exception as e:
        print(f"Ошибка queue_status: {e}")
    
    # Тест 2: прямой queue_get с полным путем
    print("\n=== Тест 2: прямой queue_get с полным путем ===")
    try:
        direct_url = _build_queue_url(cached_model, f"requests/{test_request_id}")
        print(f"URL: {direct_url}")
        response_result = queue_get(direct_url)
        print(f"Результат получен: {list(response_result.keys()) if isinstance(response_result, dict) else 'not a dict'}")
        if isinstance(response_result, dict):
            for key in ["image_url", "url", "output", "result", "images", "response"]:
                if key in response_result:
                    print(f"Найден ключ '{key}': {type(response_result[key])}")
    except Exception as e:
        print(f"Ошибка queue_get: {e}")
else:
    print("Модель не найдена в кэше или не является nano-banana/edit")

