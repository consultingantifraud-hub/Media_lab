from __future__ import annotations

from app.core.redis import get_redis_connection

# Rate limit настройки
RATE_LIMIT_WINDOW = 60  # секунды (окно времени)
RATE_LIMIT_MAX_REQUESTS = 10  # максимальное количество запросов в окне


def check_rate_limit(user_id: int) -> bool:
    """
    Проверяет rate limit для пользователя.
    
    Args:
        user_id: ID пользователя Telegram
        
    Returns:
        True если запрос разрешен, False если превышен лимит
    """
    redis_client = get_redis_connection()
    key = f"rate_limit:{user_id}"
    
    # Получаем текущее количество запросов
    current = redis_client.get(key)
    
    if current is None:
        # Первый запрос - устанавливаем счетчик с TTL
        redis_client.setex(key, RATE_LIMIT_WINDOW, 1)
        return True
    
    count = int(current)
    if count >= RATE_LIMIT_MAX_REQUESTS:
        # Лимит превышен
        return False
    
    # Увеличиваем счетчик
    redis_client.incr(key)
    return True


def get_rate_limit_remaining(user_id: int) -> int:
    """
    Возвращает количество оставшихся запросов для пользователя.
    
    Args:
        user_id: ID пользователя Telegram
        
    Returns:
        Количество оставшихся запросов (0 если лимит превышен)
    """
    redis_client = get_redis_connection()
    key = f"rate_limit:{user_id}"
    
    current = redis_client.get(key)
    if current is None:
        return RATE_LIMIT_MAX_REQUESTS
    
    count = int(current)
    remaining = max(0, RATE_LIMIT_MAX_REQUESTS - count)
    return remaining


def reset_rate_limit(user_id: int) -> None:
    """
    Сбрасывает rate limit для пользователя (для тестирования или админ-функций).
    
    Args:
        user_id: ID пользователя Telegram
    """
    redis_client = get_redis_connection()
    key = f"rate_limit:{user_id}"
    redis_client.delete(key)




