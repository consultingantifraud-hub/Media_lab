"""Тестовый скрипт для проверки GPT моделей на WaveSpeedAI"""
import os
import httpx
import json

# Загружаем API ключ
api_key = os.getenv("WAVESPEED_API_KEY")
if not api_key:
    # Пробуем загрузить из env файла
    try:
        with open("/opt/media-lab/env", "r") as f:
            for line in f:
                if line.startswith("WAVESPEED_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    except:
        pass

if not api_key:
    print("❌ WAVESPEED_API_KEY не найден")
    exit(1)

print(f"✅ API ключ найден: {api_key[:10]}...")

base_url = "https://api.wavespeed.ai/api/v3"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

# Тестируем разные варианты имен моделей
test_models = [
    "openai/gpt-image-1-mini",
    "openai/gpt-image-1",
    "openai/dall-e-3",
    "openai/dall-e-2",
    "openai/gpt-4-vision",
]

print("\n🔍 Тестируем доступные модели OpenAI на WaveSpeedAI:\n")

for model in test_models:
    print(f"Тестирую модель: {model}")
    try:
        # Пробуем простой запрос с минимальными параметрами
        request_params = {
            "prompt": "test",
            "size": "1024x1024",
        }
        
        with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=30.0)) as client:
            response = client.post(
                f"{base_url}/{model}",
                headers=headers,
                json=request_params,
            )
            
            print(f"  Status: {response.status_code}")
            
            if response.status_code == 200:
                print(f"  ✅ Модель {model} доступна!")
                data = response.json()
                print(f"  Response keys: {list(data.keys())}")
                break
            elif response.status_code == 400:
                error_data = response.json()
                error_msg = error_data.get("message", str(error_data))
                print(f"  ❌ Ошибка 400: {error_msg[:100]}")
            else:
                print(f"  ❌ Status {response.status_code}: {response.text[:100]}")
    except Exception as e:
        print(f"  ❌ Exception: {e}")
    
    print()

print("\n📚 Проверяем документацию WaveSpeedAI...")
print("Попробуйте проверить: https://wavespeed.ai/collections/openai")

