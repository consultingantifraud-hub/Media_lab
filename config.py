from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    tg_bot_token: str
    app_env: Literal["local", "vps"] = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    redis_url: str = "redis://redis:6379/0"  # В Docker используем имя сервиса 'redis' вместо 'localhost'
    fal_api_key: str
    fal_queue_base_url: str = "https://queue.fal.run"
    fal_standard_model: str = "fal-ai/flux-pro/v1.1-ultra"
    fal_premium_model: str = "fal-ai/nano-banana"
    fal_inpaint_model: str = "fal-ai/flux-general/inpainting"
    fal_edit_model: str = "fal-ai/chrono-edit"
    fal_upscale_model: str = "fal-ai/recraft/upscale/crisp"
    fal_upscale_fallback_model: str | None = None
    fal_retoucher_model: str = "fal-ai/retoucher"
    fal_face_enhance_model: str = "fal-ai/image-editing/face-enhancement"
    fal_face_swap_model: str = "fal-ai/face-swap"
    # Настройки для WaveSpeedAI
    wavespeed_api_key: str | None = None  # API ключ WaveSpeedAI (обязательно для WaveSpeed Face Swap - высокое качество)
    wavespeed_face_swap_model: str = "wavespeed-ai/image-head-swap"  # Модель для face swap на WaveSpeedAI (head-swap заменяет всю голову для лучшего сходства)
    media_dir: Path = Path("./media")
    log_level: str = "INFO"  # INFO для production, DEBUG только для разработки

    model_config = SettingsConfigDict(
        env_file=(".env", "env", "/opt/media-lab/env", "/opt/media-lab/.env"), 
        env_file_encoding="utf-8", 
        case_sensitive=False,
        extra="ignore",  # Игнорировать дополнительные поля из env файла
    )

    @property
    def images_dir(self) -> Path:
        return self.media_dir / "images"


@lru_cache
def get_settings() -> Settings:
    # Clear cache to reload settings from env file
    # This allows hot-reloading of settings without restart
    return Settings()

def reload_settings() -> Settings:
    """Перезагрузить настройки из env файла (очистить кэш)."""
    get_settings.cache_clear()
    return get_settings()


settings = get_settings()

