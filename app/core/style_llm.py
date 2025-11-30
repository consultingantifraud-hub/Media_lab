from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from jsonschema import validate
from loguru import logger

from app.core.config import settings

# Схема валидации параметров стиля
STYLE_SCHEMA = {
    "type": "object",
    "properties": {
        "position": {
            "type": "string",
            "enum": [
                "auto",
                "top-left",
                "top-center",
                "top-right",
                "center-left",
                "center",
                "center-right",
                "bottom-left",
                "bottom-center",
                "bottom-right",
            ],
        },
        "size": {
            "oneOf": [
                {"type": "string", "enum": ["auto", "S", "M", "L", "XL"]},
                {"type": "integer", "minimum": 12, "maximum": 200}
            ]
        },
        "align": {"type": "string", "enum": ["left", "center", "right"]},
        "box": {"type": "boolean"},
        "box_alpha": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "box_radius": {"type": "integer", "minimum": 0, "maximum": 64},
        "box_blur": {"type": "number", "minimum": 0.0, "maximum": 20.0},  # Радиус размытия плашки (0.0 = без размытия, 20.0 = сильное размытие)
        "color": {
            "type": "string",
            "enum": ["auto", "white", "black", "red", "green", "blue", "orange", "brand", "from-palette"],
        },
        "box_color": {
            "type": "string",
            "enum": ["auto", "white", "black", "red", "green", "blue", "orange", "brand", "from-palette"],
        },
        "padding": {"type": "integer"},
        "line_spacing": {"type": "number", "minimum": 0.8, "maximum": 2.0},
        "style": {"type": "string", "enum": ["banner", "badge", "subtitle", "custom"]},
        "offset_bottom": {"type": "number", "minimum": 0.0, "maximum": 1.0},  # Смещение от низа в процентах (0.0 = внизу, 1.0 = вверху)
    },
    "additionalProperties": False,
}

# Системный промпт для LLM
SYSTEM_PROMPT = """Ты — парсер оформления текста для графического рендера. Преобразуй русскоязычные пожелания пользователя в JSON для функции render_text_box.

Верни ТОЛЬКО JSON, без пояснений. Разрешённые ключи:
  position: ["auto","top-left","top-center","top-right","center-left","center","center-right","bottom-left","bottom-center","bottom-right"]
  size:     ["auto","S","M","L","XL"] или число (12-200) - размер шрифта в пикселях
           Соответствие слов размерам:
           - "маленький" = S (36px)
           - "обычный" = M (64px)
           - "средний" = M (64px)
           - "крупный" = L (96px)
           - "огромный" = XL (128px)
           Также можно указать размер цифрами: "72px", "48 пикселей", "размер 60"
  align:    ["left","center","right"]
  box:      boolean (если не упомянуто - false, без плашки)
  box_alpha: float 0.0-1.0 (непрозрачность плашки: 0.0 = полностью прозрачная/невидимая, 1.0 = полностью непрозрачная/видимая)
           ВАЖНО: "прозрачность X%" означает, что плашка видна на (100-X)%
           Например: "прозрачность 90%" = плашка видна на 10% = box_alpha = 0.1
           "прозрачность 50%" = плашка видна на 50% = box_alpha = 0.5
           "прозрачная плашка" без процента = box_alpha = 0.5 (50% видимости)
  box_radius: int 0-64
  box_blur: float 0.0-20.0 (радиус размытия плашки: 0.0 = без размытия, 5.0 = легкое размытие, 10.0 = среднее, 20.0 = сильное)
  color:    ["auto","white","black","red","green","blue","orange","brand","from-palette"]
  box_color:["auto","white","black","red","green","blue","orange","brand","from-palette"]
  padding:  int
  line_spacing: float 0.8-2.0
  style:    ["banner","badge","subtitle","custom"]
  offset_bottom: float 0.0-1.0 (смещение от низа в процентах: 0.0 = внизу, 0.3 = 30% от низа, 1.0 = вверху)

ВАЖНО: Если пользователь НЕ упоминает плашку, обводку или тень - не добавляй их (box=false по умолчанию).
Если пользователь просит "расстояние от низа X%" или "X% от низа" - используй offset_bottom (X/100).
Если пользователь упоминает прозрачность плашки ("прозрачность X%", "прозрачная плашка") - ОБЯЗАТЕЛЬНО добавляй box_alpha.
Если пожелания конфликтуют — приоритет у последней инструкции. Если чего-то нет — не добавляй поле.

Примеры:

Ввод: "Крупный белый текст на чёрной плашке, снизу по центру, скругление побольше, прозрачность 40%"
Ожидаемый JSON:
{"size":"L","color":"white","box":true,"box_color":"black","position":"bottom-center","box_radius":32,"box_alpha":0.6}
# Примечание: прозрачность 40% = видимость 60% = box_alpha = 0.6

Ввод: "Маленький без плашки, справа сверху, выравнивание по правому"
{"size":"S","box":false,"position":"top-right","align":"right"}

Ввод: "Обычный текст, в центре, белая плашка с прозрачностью 50%"
{"size":"M","position":"center","box":true,"box_color":"white","box_alpha":0.5}
# Примечание: прозрачность 50% = видимость 50% = box_alpha = 0.5

Ввод: "Средний текст, в центре, белая плашка с прозрачностью 50%"
{"size":"M","position":"center","box":true,"box_color":"white","box_alpha":0.5}

Ввод: "Огромный текст по центру, красный цвет"
{"size":"XL","position":"center","color":"red","box":false}

Ввод: "Крупный текст без плашки, белый цвет"
{"size":"L","color":"white","box":false}

Ввод: "Текст с плашкой, черная плашка"
{"box":true,"box_color":"black"}

Ввод: "Крупный белый текст на чёрной плашке, снизу"
{"size":"L","color":"white","box":true,"box_color":"black","position":"bottom-center"}

Ввод: "Красный текст, без обводки, без плашки"
{"color":"red","box":false}

Ввод: "Огромный текст по центру, зеленый, без плашки, без тени"
{"size":"XL","position":"center","color":"green","box":false}

Ввод: "Белая плашка с размытием, радиус размытия 5"
{"box":true,"box_color":"white","box_blur":5.0}

Ввод: "Черная плашка с блюрингом, размытие 10"
{"box":true,"box_color":"black","box_blur":10.0}

Ввод: "Плашка с размытием фона, блюринг 8"
{"box":true,"box_blur":8.0}

Ввод: "Белый текст на прозрачной плашке, снизу по центру"
{"color":"white","box":true,"box_alpha":0.5,"position":"bottom-center"}

Ввод: "Маленький текст сверху слева, синий цвет"
{"size":"S","position":"top-left","color":"blue","box":false}

Ввод: "Средний текст, черная плашка, белый текст, прозрачность 60%"
{"size":"M","box":true,"box_color":"black","color":"white","box_alpha":0.4}
# Примечание: прозрачность 60% = видимость 40% = box_alpha = 0.4

Ввод: "Крупный текст справа внизу, красный цвет, без обводки"
{"size":"L","position":"bottom-right","color":"red","box":false}

Ввод: "Крупный текст снизу, расстояние от низа 30%"
{"size":"L","position":"bottom-center","offset_bottom":0.3}

Ввод: "Текст на 20% от низа, по центру"
{"position":"bottom-center","offset_bottom":0.2}

Ввод: "Крупный текст снизу, но не в самом низу, на 30% от низа"
{"size":"L","position":"bottom-center","offset_bottom":0.3}

Ввод: "Текст размером 72px снизу, расстояние от низа 10%"
{"size":72,"position":"bottom-center","offset_bottom":0.1}

Ввод: "Текст размером 48 пикселей по центру, белая плашка"
{"size":48,"position":"center","box":true,"box_color":"white"}

Ввод: "Крупный белый текст, находится внутри плашки, цвет плашки черный, прозрачность 70%, размещение плашки с тектом слева изображения по центру"
{"size":"L","color":"white","box":true,"box_color":"black","box_alpha":0.3,"position":"center-left"}
# Примечание: прозрачность 70% = видимость 30% = box_alpha = 0.3

Ввод: "Текст слева по центру"
{"position":"center-left"}

Ввод: "Плашка слева изображения, по центру вертикали"
{"position":"center-left"}

Ввод: "Слева по центру"
{"position":"center-left"}

ПОЗИЦИИ:
- "слева" или "слева изображения" = left (по горизонтали)
- "по центру" или "по центру вертикали" = center (по вертикали)
- "слева по центру" или "слева изображения по центру" = center-left (слева по горизонтали, по центру по вертикали)
- "сверху слева" = top-left
- "сверху по центру" = top-center
- "сверху справа" = top-right
- "по центру" (без уточнения) = center (по центру и горизонтали, и вертикали)
- "снизу слева" = bottom-left
- "снизу по центру" = bottom-center
- "снизу справа" = bottom-right
"""

# Модель LLM по умолчанию
# Используем две модели Gemini с одинаковым форматом запроса
# Обе модели используют формат БЕЗ "input" с отдельным system_prompt
# Из тестов: gemini-flash-1.5 работает быстро (отвечает за ~2-3 секунды)
# gemini-pro-1.5 может отвечать очень долго (60+ секунд)
PRIMARY_LLM_MODEL = "google/gemini-flash-1.5"  # Быстрая модель Gemini (проверена)
FALLBACK_LLM_MODEL = "google/gemini-pro-1.5"  # Более мощная модель Gemini (fallback, но медленная)
LLM_TIMEOUT_SECONDS = 10.0  # Таймаут для первой LLM (10 секунд)


async def wish_to_params_async(hint: str) -> dict[str, Any]:
    """
    Преобразует текстовые пожелания пользователя в параметры стиля через LLM.
    
    Args:
        hint: Текстовое описание пожеланий по оформлению
    
    Returns:
        Словарь с параметрами стиля, валидными по STYLE_SCHEMA
    """
    if not hint or not hint.strip():
        return {}
    
    try:
        # Формируем промпт для LLM
        user_prompt = f"Пожелания пользователя: {hint.strip()}\n\nВерни только JSON:"
        
        # Вызываем первую LLM с таймаутом 10 секунд
        response = None
        import time
        start_time = time.time()
        
        # Запускаем первую модель в фоне
        primary_task = asyncio.create_task(
            asyncio.to_thread(_call_fal_llm, SYSTEM_PROMPT, user_prompt, PRIMARY_LLM_MODEL)
        )
        
        try:
            logger.info("Trying primary LLM ({}) with timeout {}s", PRIMARY_LLM_MODEL, LLM_TIMEOUT_SECONDS)
            response = await asyncio.wait_for(primary_task, timeout=LLM_TIMEOUT_SECONDS)
            elapsed = time.time() - start_time
            if response:
                logger.info("Primary LLM responded successfully in {:.2f}s", elapsed)
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            logger.warning("Primary LLM ({}) timed out after {:.2f}s (limit: {}s), trying fallback", PRIMARY_LLM_MODEL, elapsed, LLM_TIMEOUT_SECONDS)
            # Отменяем задачу первой модели, но не ждем её завершения
            primary_task.cancel()
            
            # Используем фаллбек LLM
            try:
                logger.info("Trying fallback LLM ({})", FALLBACK_LLM_MODEL)
                response = await asyncio.wait_for(
                    asyncio.to_thread(_call_fal_llm, SYSTEM_PROMPT, user_prompt, FALLBACK_LLM_MODEL),
                    timeout=60.0  # Фаллбек может отвечать дольше
                )
                if response:
                    logger.info("Fallback LLM ({}) responded successfully", FALLBACK_LLM_MODEL)
            except asyncio.TimeoutError:
                logger.error("Both LLM calls timed out (primary: {}s, fallback: 60s)", LLM_TIMEOUT_SECONDS)
                return {}
            except Exception as e:
                logger.error("Fallback LLM call failed: {}", e, exc_info=True)
                return {}
        except Exception as e:
            logger.error("Primary LLM call failed: {}, trying fallback", e, exc_info=True)
            primary_task.cancel()
            # Если первая LLM ошибка но не таймаут, пробуем фаллбек
            try:
                logger.debug("Trying fallback LLM ({}) after primary error", FALLBACK_LLM_MODEL)
                response = await asyncio.wait_for(
                    asyncio.to_thread(_call_fal_llm, SYSTEM_PROMPT, user_prompt, FALLBACK_LLM_MODEL),
                    timeout=60.0
                )
                if response:
                    logger.info("Fallback LLM ({}) responded successfully after primary error", FALLBACK_LLM_MODEL)
            except Exception as fallback_error:
                logger.error("Fallback LLM call also failed: {}", fallback_error, exc_info=True)
                return {}
        
        if not response:
            logger.warning("Empty response from LLM for hint: {}", hint)
            return {}
        
        # Парсим JSON
        try:
            # Убираем markdown code blocks если есть
            response_clean = response.strip()
            if response_clean.startswith("```"):
                # Убираем ```json и ```
                lines = response_clean.split("\n")
                response_clean = "\n".join(lines[1:-1]) if len(lines) > 2 else response_clean
            elif response_clean.startswith("```"):
                response_clean = response_clean[3:]
            if response_clean.endswith("```"):
                response_clean = response_clean[:-3]
            
            params = json.loads(response_clean.strip())
        except json.JSONDecodeError as e:
            logger.error("Failed to parse JSON from LLM response: {} | Response: {}", e, response)
            return {}
        
        # Валидируем по схеме
        try:
            validate(instance=params, schema=STYLE_SCHEMA)
            logger.debug("Successfully parsed and validated style params: {}", params)
            return params
        except Exception as e:
            logger.error("Validation failed for style params: {} | Error: {}", params, e)
            # Возвращаем только валидные поля
            valid_params = {}
            for key, value in params.items():
                if key in STYLE_SCHEMA.get("properties", {}):
                    try:
                        # Проверяем тип и enum если есть
                        prop_schema = STYLE_SCHEMA["properties"][key]
                        if "enum" in prop_schema and value not in prop_schema["enum"]:
                            continue
                        if "type" in prop_schema:
                            if prop_schema["type"] == "boolean" and not isinstance(value, bool):
                                continue
                            if prop_schema["type"] == "integer" and not isinstance(value, int):
                                continue
                            if prop_schema["type"] == "number" and not isinstance(value, (int, float)):
                                continue
                            if prop_schema["type"] == "string" and not isinstance(value, str):
                                continue
                        valid_params[key] = value
                    except Exception:
                        continue
            return valid_params
    
    except Exception as e:
        logger.error("Error in wish_to_params_async for hint '{}': {}", hint, e, exc_info=True)
        return {}


def _call_fal_llm(system_prompt: str, user_prompt: str, model: str | None = None) -> str | None:
    """
    Вызывает LLM через Fal.ai any-llm endpoint.
    
    Args:
        system_prompt: Системный промпт
        user_prompt: Пользовательский промпт
        model: Модель LLM (используется по умолчанию PRIMARY_LLM_MODEL)
    
    Returns:
        Ответ LLM или None при ошибке
    """
    try:
        from app.providers.fal.client import run_model
        
        # Используем run_model для синхронного вызова
        endpoint = "fal-ai/any-llm"
        
        # Используем переданную модель или по умолчанию
        llm_model = model if model else PRIMARY_LLM_MODEL
        
        # Формируем промпт в зависимости от модели
        # Для Gemini можно использовать system_prompt отдельно
        # Для других моделей объединяем в один промпт
        
        # Вариант 1: С оберткой "input" и system_prompt отдельно (для Gemini)
        payload_with_input_system = {
            "input": {
                "model": llm_model,
                "prompt": user_prompt,  # Только user prompt
                "system_prompt": system_prompt,  # System prompt отдельно
                "temperature": 0.1,
                "max_tokens": 500,
            }
        }
        
        # Вариант 2: С оберткой "input" и объединенным промптом
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        payload_with_input = {
            "input": {
                "model": llm_model,
                "prompt": full_prompt,
                "temperature": 0.1,
                "max_tokens": 500,
            }
        }
        
        # Вариант 3: Без обертки (как в прямых HTTP запросах)
        payload_direct = {
            "model": llm_model,
            "prompt": full_prompt,
            "temperature": 0.1,
            "max_tokens": 500,
        }
        
        # Для синхронного API fal.run формат БЕЗ "input" (как в документации)
        # Обе модели Gemini используют одинаковый формат с отдельным system_prompt
        # Формат: БЕЗ обертки "input", с отдельными полями prompt и system_prompt
        payload = {
            "model": llm_model,
            "prompt": user_prompt,
            "system_prompt": system_prompt,
            "temperature": 0.1,
            "max_tokens": 500,
        }
        logger.debug("Using Gemini format: direct (no input wrapper) with separate system_prompt for model: {}", llm_model)
        
        logger.info("Calling fal-ai/any-llm with model: {}, user_prompt length: {}, system_prompt length: {}", llm_model, len(user_prompt), len(system_prompt))
        logger.info("Payload: {}", payload)
        
        import time
        start_time = time.time()
        try:
            result = run_model(endpoint, payload)
            elapsed = time.time() - start_time
            logger.info("LLM call successful in {:.2f}s. Response type: {}, keys: {}", elapsed, type(result), list(result.keys()) if isinstance(result, dict) else "N/A")
        except Exception as e:
            elapsed = time.time() - start_time
            error_str = str(e)
            logger.warning("LLM call failed after {:.2f}s with error: {} | Error type: {}", elapsed, error_str[:200], type(e).__name__)
            
            # Если ошибка 422, пробуем формат с "input" (для queue API)
            if "422" in error_str:
                logger.debug("Got 422 with direct format, trying input wrapper format")
                try:
                    # Для Gemini используем формат с input и отдельным system_prompt
                    payload_retry = {
                        "input": {
                            "model": llm_model,
                            "prompt": user_prompt,
                            "system_prompt": system_prompt,
                            "temperature": 0.1,
                            "max_tokens": 500,
                        }
                    }
                    logger.debug("Retrying Gemini with input wrapper format")
                    result = run_model(endpoint, payload_retry)
                    logger.debug("Input wrapper format successful. Response type: {}, keys: {}", type(result), list(result.keys()) if isinstance(result, dict) else "N/A")
                except Exception as e2:
                    logger.error("Both payload formats failed. Direct format error: {}, Input wrapper error: {}", str(e)[:200], str(e2)[:200])
                    raise e2
            else:
                raise
        
        logger.debug("LLM response type: {}, keys: {}", type(result), result.keys() if isinstance(result, dict) else "N/A")
        
        # Извлекаем текст ответа из результата
        # Формат ответа для any-llm может быть разным в зависимости от модели
        logger.debug("Extracting response from result. Type: {}, Full result: {}", type(result), str(result)[:500] if result else "None")
        
        if isinstance(result, dict):
            # Для any-llm ответ обычно в поле "output" или "text"
            # Также может быть вложен в "input" -> "output" или просто в корне
            logger.debug("Result is dict. Keys: {}", list(result.keys()))
            
            # Сначала проверяем "output" - это основной формат для any-llm
            if "output" in result:
                output = result["output"]
                if isinstance(output, str):
                    logger.debug("Found response in 'output' field: {}", output[:200])
                    return output
                elif isinstance(output, dict):
                    logger.debug("'output' is dict, keys: {}", list(output.keys()) if isinstance(output, dict) else "N/A")
                    if "content" in output:
                        logger.debug("Found response in 'output.content'")
                        return output["content"]
                    elif "text" in output:
                        logger.debug("Found response in 'output.text'")
                        return output["text"]
            
            # Проверяем другие возможные поля
            for field in ["text", "content", "response", "message"]:
                if field in result:
                    content = result[field]
                    if isinstance(content, str):
                        logger.debug("Found response in field '{}': {}", field, content[:200])
                        return content
                    elif isinstance(content, dict):
                        # Если это словарь, ищем внутри
                        if "content" in content:
                            logger.debug("Found response in field '{}' -> 'content'", field)
                            return content["content"]
                        elif "text" in content:
                            logger.debug("Found response in field '{}' -> 'text'", field)
                            return content["text"]
            
            # Если есть choices (OpenAI-формат)
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    logger.debug("Found response in choices[0].message.content")
                    return choice["message"]["content"]
                elif "text" in choice:
                    logger.debug("Found response in choices[0].text")
                    return choice["text"]
            
            # Если есть "input" -> "output" (для некоторых моделей)
            if "input" in result and isinstance(result["input"], dict):
                if "output" in result["input"]:
                    output = result["input"]["output"]
                    if isinstance(output, str):
                        logger.debug("Found response in input.output")
                        return output
            
            logger.warning("Unexpected LLM response format. Keys: {}, Full result: {}", list(result.keys()), str(result)[:500])
            return None
        elif isinstance(result, str):
            logger.debug("Response is a string: {}", result[:100])
            return result
        else:
            logger.warning("Unexpected LLM response type: {}", type(result))
            return None
    
    except Exception as e:
        logger.error("Error calling Fal LLM: {}", e, exc_info=True)
        return None

