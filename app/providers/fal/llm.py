from __future__ import annotations

from loguru import logger

from app.providers.fal.client import run_model

# Модели для текстовой генерации и анализа изображений
# Используем fal-ai/any-llm с указанием конкретной модели в payload
# Формат такой же, как в app.core.style_llm (wish_to_params_async)
# Доступные модели: deepseek, anthropic/claude, google/gemini
# OpenAI модели не доступны через any-llm на fal.ai
LLM_ENDPOINT = "fal-ai/any-llm"
# Используем Claude 3.5 Sonnet - хороший баланс качества и скорости
TEXT_GENERATION_MODEL = "anthropic/claude-3.5-sonnet"  # Качественная модель с хорошей скоростью
# Для vision используем Gemini Pro 1.5 - проверенная рабочая модель
# gemini-1.5-pro и gemini-2.0-flash-exp не поддерживаются через any-llm
VISION_MODEL = "google/gemini-pro-1.5"  # Рабочая модель Gemini Pro с vision поддержкой


def generate_prompt(user_request: str) -> str:
    """
    Генерирует промпт для создания изображения на основе текстового запроса пользователя.
    
    Args:
        user_request: Текстовый запрос пользователя
        
    Returns:
        Сгенерированный промпт для создания изображения
    """
    system_prompt = """Ты помощник для генерации промптов для создания изображений. 
Твоя задача - преобразовать запрос пользователя в детальный, качественный промпт на русском языке для генерации изображений.

КРИТИЧЕСКИ ВАЖНО - ИЗБЕГАЙ ПРОТИВОРЕЧИЙ И ДВОЙНЫХ ТРАКТОВОК:

1. ЛОГИЧЕСКАЯ СОГЛАСОВАННОСТЬ:
   - Проверь промпт на противоречия перед отправкой
   - Если упоминается "без верха купальника" - не добавляй описание верха купальника
   - Если описывается "лысый" - не упоминай волосы
   - Если "в полный рост" - не добавляй "крупный план лица"
   - Все элементы описания должны логически сочетаться друг с другом

2. СТРУКТУРА ПРОМПТА (в порядке приоритета):
   - ГЛАВНЫЙ ОБЪЕКТ/ПЕРСОНАЖ: кто или что на изображении (1-2 предложения)
   - ВНЕШНОСТЬ/ДЕТАЛИ: описание внешности, одежды, позы (2-3 предложения)
   - ОКРУЖЕНИЕ/ФОН: где происходит действие, что на заднем плане (1-2 предложения)
   - ОСВЕЩЕНИЕ И АТМОСФЕРА: время суток, освещение, настроение (1 предложение)
   - СТИЛЬ И ОБРАБОТКА: стиль фотографии, обработка, цветовая гамма (1 предложение)

3. ТРЕБОВАНИЯ К ПРОМПТУ:
   - Детальный и описательный (1000+ символов)
   - Включать стиль, композицию, освещение, настроение, цвета
   - Подходить для моделей: Nano Banana, Nano Banana Pro и Seedream
   - На русском языке
   - БЕЗ указания размеров изображения (не указывай разрешение, соотношение сторон, параметры типа --ar, 4k, 8k, ultra HD и т.д.)
   - БЕЗ технических параметров (только описание изображения)
   - Без лишних объяснений, только сам промпт
   - ОДИН непрерывный текст без нумерации и списков

4. ДЛЯ EDIT МОДЕЛЕЙ:
   Промпт может использоваться для Edit моделей, где пользователь загружает референсное изображение, а нейросеть генерирует новое на его основе. 
   В этом случае промпт должен описывать изменения, дополнения или модификации, которые нужно применить к референсному изображению, 
   а также общий стиль и атмосферу желаемого результата.

ПЕРЕД ОТПРАВКОЙ: перечитай промпт и убедись, что нет противоречий и все элементы логически согласованы."""
    
    user_message = f"Создай промпт для генерации изображения на основе следующего запроса: {user_request}"
    
    # Формат для any-llm: БЕЗ обертки "input", с отдельными полями prompt и system_prompt
    # Такой же формат, как в app.core.style_llm._call_fal_llm
    payload = {
        "model": TEXT_GENERATION_MODEL,
        "prompt": user_message,
        "system_prompt": system_prompt,
        "temperature": 0.7,
        "max_tokens": 1000,  # Увеличено в 2 раза для более детальных промптов
    }
    
    try:
        logger.info("Generating prompt for user request: {} (model: {})", user_request, TEXT_GENERATION_MODEL)
        response = run_model(LLM_ENDPOINT, payload)
        
        # Извлекаем текст ответа из ответа API
        # any-llm возвращает ответ в формате {"output": "текст", ...}
        if isinstance(response, dict):
            if "output" in response:
                output = response["output"]
                if isinstance(output, str) and output:
                    logger.info("Generated prompt: {}", output)
                    return output.strip()
                if isinstance(output, dict) and "text" in output:
                    text = output["text"]
                    if text:
                        logger.info("Generated prompt: {}", text)
                        return text.strip()
            # Альтернативные форматы
            if "text" in response:
                text = response["text"]
                if text:
                    return text.strip()
            if "content" in response:
                content = response["content"]
                if content:
                    return content.strip()
            # OpenAI формат (на случай если изменится)
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
                if content:
                    logger.info("Generated prompt: {}", content)
                    return content.strip()
        
        logger.warning("Unexpected response format: {}", response)
        return str(response).strip()
    except Exception as e:
        logger.error("Failed to generate prompt: {}", e, exc_info=True)
        raise


def analyze_image_to_prompt(image_url: str, user_request: str = "") -> str:
    """
    Анализирует изображение и создает промпт для его воссоздания.
    
    Args:
        image_url: URL изображения для анализа
        user_request: Дополнительный запрос пользователя (например, "опиши лицо", "для nano banana pro")
        
    Returns:
        Промпт, описывающий изображение
    """
    system_prompt = """Ты помощник для анализа изображений. Тебе передано изображение по URL. Создай детальный промпт на русском языке для воссоздания изображения.

КРИТИЧЕСКИ ВАЖНО - ВНИМАТЕЛЬНО СМОТРИ НА ИЗОБРАЖЕНИЕ И ОПИСЫВАЙ ТОЛЬКО ТО, ЧТО РЕАЛЬНО ВИДИШЬ:

1. ВНИМАТЕЛЬНО ПРОАНАЛИЗИРУЙ ВСЁ ИЗОБРАЖЕНИЕ:
   - Посмотри на ВСЁ изображение целиком, а не только на людей
   - Что это за место? (магазин, офис, улица, дом, ресторан, мясная лавка и т.д.)
   - Какие объекты видны? (товары, продукты, мебель, вывески, витрины и т.д.)
   - Что происходит на изображении?
   - НЕ ПРИДУМЫВАЙ! Опиши ТОЛЬКО то, что реально видишь!

2. ЕСЛИ ЕСТЬ ЛЮДИ:
   - ВОЛОСЫ: Если ЛЫСЫЙ - напиши "лысый", НЕ "коротко стриженные волосы"!
   - ПОЛ: Определи точно по реальным признакам
   - Одежда: опиши детально
   - Что делает человек?

3. ОКРУЖЕНИЕ И ОБЪЕКТЫ:
   - Опиши ВСЁ, что видишь: товары, продукты, вывески, витрины, полки
   - Прочитай надписи на вывесках, если они видны
   - Опиши фон и окружение

Промпт должен быть на русском языке, без технических параметров (разрешение, --ar и т.д.), только описание изображения."""
    
    # Для Gemini vision моделей нужно передать image_url как отдельный параметр
    # Формат для any-llm с vision: передаем image_url в payload
    # Учитываем запрос пользователя, если он есть
    base_instruction = """ПРОАНАЛИЗИРУЙ ИЗОБРАЖЕНИЕ ПО URL: {image_url}

ВНИМАНИЕ! ОПИСЫВАЙ ВСЁ ИЗОБРАЖЕНИЕ, А НЕ ТОЛЬКО ЛЮДЕЙ!

ШАГ 1 - ОПРЕДЕЛИ ЧТО НА ИЗОБРАЖЕНИИ:
СНАЧАЛА посмотри на ВСЁ изображение целиком:
- Что это за место? (магазин, офис, улица, дом и т.д.)
- Что происходит? (покупка, работа, встреча и т.д.)
- Какие объекты видны? (товары, мебель, вывески, продукты и т.д.)
- Кто на изображении? (если есть люди - опиши их)
- Опиши ВСЁ, что видишь, а не только людей!

ШАГ 2 - ЕСЛИ ЕСТЬ ЛЮДИ:
Если на изображении есть люди, опиши их:
- Пол: мужчина/женщина (определи по реальным признакам)
- Возраст: примерно
- ВОЛОСЫ: 
  * Если ЛЫСЫЙ - напиши "лысый" или "без волос"
  * Если есть волосы - опиши цвет, длину, прическу
  * НЕ ПРИДУМЫВАЙ ВОЛОСЫ, ЕСЛИ ИХ НЕТ!
- Лицо: форма, скулы, нос, глаза, губы
- Очки: есть/нет, если есть - опиши
- Борода/усы: есть/нет, если есть - опиши
- Одежда: детально
- Что делает человек?

ШАГ 3 - ОПИСАНИЕ ОКРУЖЕНИЯ:
- Фон: что на заднем плане?
- Объекты: что еще видно на изображении?
- Вывески/надписи: что написано? (если видно)
- Освещение: какое освещение?
- Общая атмосфера: какое настроение у изображения?

ШАГ 4 - СОЗДАНИЕ ПРОМПТА:
Создай промпт на русском языке для воссоздания этого изображения.
Опиши ВСЁ изображение целиком, а не только людей!"""
    
    # Если есть запрос пользователя, добавляем его
    if user_request and user_request.strip():
        user_request_lower = user_request.strip().lower()
        
        # Если запрос про рекламный промпт или оффер
        if "реклам" in user_request_lower or "оффер" in user_request_lower or "предложи" in user_request_lower:
            user_message = f"""ВНИМАТЕЛЬНО ПРОАНАЛИЗИРУЙ ИЗОБРАЖЕНИЕ ПО URL: {image_url}

КРИТИЧЕСКИ ВАЖНО:
1. СНАЧАЛА внимательно посмотри на ВСЁ изображение целиком
2. Определи ЧТО это за место/бизнес (магазин, мясная лавка, ресторан, офис и т.д.)
3. Опиши ВСЁ что видишь: товары, продукты, вывески, витрины, людей, действия
4. Прочитай надписи на вывесках, если они видны
5. НЕ ПРИДУМЫВАЙ детали, которых нет на изображении!

ДОПОЛНИТЕЛЬНЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_request.strip()}

После анализа изображения:
1. Опиши ЧТО реально видишь на изображении
2. Создай рекламный промпт с оффером для этого бизнеса/продукта
3. Рекламный промпт должен быть на русском языке и включать оффер (предложение для клиента)
4. Промпт должен соответствовать тому, что реально видно на изображении"""
        else:
            user_message = f"""{base_instruction.format(image_url=image_url)}

ДОПОЛНИТЕЛЬНЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ: {user_request.strip()}

Учти этот запрос при создании промпта."""
    else:
        user_message = base_instruction.format(image_url=image_url)
    
    payload = {
        "model": VISION_MODEL,
        "prompt": user_message,
        "system_prompt": system_prompt,
        "image_url": image_url,  # Передаем изображение как отдельный параметр для vision
        "temperature": 0.0,  # Минимальная температура для максимально точного и детерминированного анализа
        "max_tokens": 1000,  # Увеличиваем для более детального описания
    }
    
    try:
        logger.info("Analyzing image: {} (model: {})", image_url, VISION_MODEL)
        response = run_model(LLM_ENDPOINT, payload)
        
        # Извлекаем текст ответа из ответа API
        # any-llm возвращает ответ в формате {"output": "текст", ...}
        if isinstance(response, dict):
            if "output" in response:
                output = response["output"]
                if isinstance(output, str) and output:
                    logger.info("Generated prompt from image: {}", output)
                    return output.strip()
                if isinstance(output, dict) and "text" in output:
                    text = output["text"]
                    if text:
                        logger.info("Generated prompt from image: {}", text)
                        return text.strip()
            # Альтернативные форматы
            if "text" in response:
                text = response["text"]
                if text:
                    return text.strip()
            if "content" in response:
                content = response["content"]
                if content:
                    return content.strip()
            # OpenAI формат (на случай если изменится)
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
                if content:
                    logger.info("Generated prompt from image: {}", content)
                    return content.strip()
        
        logger.warning("Unexpected response format: {}", response)
        return str(response).strip()
    except Exception as e:
        logger.error("Failed to analyze image: {}", e, exc_info=True)
        raise

