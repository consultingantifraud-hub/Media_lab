from __future__ import annotations

"""
Конфигурация для оптимизированного polling с exponential backoff.
Используется в воркерах для проверки статуса задач.
"""

# Базовые интервалы polling (в секундах)
POLL_INTERVAL_INITIAL = 2.0  # Начальный интервал
POLL_INTERVAL_MIN = 1.0      # Минимальный интервал
POLL_INTERVAL_MAX = 10.0     # Максимальный интервал
POLL_BACKOFF_MULTIPLIER = 1.2  # Множитель для увеличения интервала

# Максимальное количество попыток (зависит от типа задачи)
IMAGE_POLL_MAX_ATTEMPTS = 120  # ~4 минуты при среднем интервале 2 сек
EDIT_POLL_MAX_ATTEMPTS = 180   # ~6 минут
RETOUCHER_POLL_MAX_ATTEMPTS = 180  # ~6 минут
FACE_SWAP_POLL_MAX_ATTEMPTS = 150  # ~5 минут
UPSCALE_POLL_MAX_ATTEMPTS = 90     # ~3 минуты


def get_next_poll_interval(current_interval: float) -> float:
    """
    Вычисляет следующий интервал polling с exponential backoff.
    
    Args:
        current_interval: Текущий интервал в секундах
        
    Returns:
        Новый интервал (ограничен максимальным значением)
    """
    new_interval = current_interval * POLL_BACKOFF_MULTIPLIER
    return min(max(new_interval, POLL_INTERVAL_MIN), POLL_INTERVAL_MAX)


class PollingConfig:
    """Конфигурация для polling конкретного типа задачи."""
    
    def __init__(
        self,
        initial_interval: float = POLL_INTERVAL_INITIAL,
        max_interval: float = POLL_INTERVAL_MAX,
        max_attempts: int = 120,
    ):
        self.initial_interval = initial_interval
        self.max_interval = max_interval
        self.max_attempts = max_attempts
        self.current_interval = initial_interval
    
    def get_interval(self) -> float:
        """Возвращает текущий интервал и увеличивает его для следующего раза."""
        interval = self.current_interval
        self.current_interval = min(
            self.current_interval * POLL_BACKOFF_MULTIPLIER,
            self.max_interval
        )
        return interval
    
    def reset(self) -> None:
        """Сбрасывает интервал к начальному значению."""
        self.current_interval = self.initial_interval





