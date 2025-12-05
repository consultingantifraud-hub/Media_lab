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
    fal_nano_banana_pro_model: str = "fal-ai/nano-banana-pro"
    fal_nano_banana_edit_model: str = "fal-ai/nano-banana/edit"
    fal_nano_banana_pro_edit_model: str = "fal-ai/nano-banana-pro/edit"
    fal_inpaint_model: str = "fal-ai/flux-general/inpainting"
    fal_edit_model: str = "fal-ai/chrono-edit"
    fal_upscale_model: str = "fal-ai/recraft/upscale/crisp"
    fal_upscale_fallback_model: str | None = None
    fal_retoucher_model: str = "fal-ai/retoucher"
    fal_face_enhance_model: str = "fal-ai/image-editing/face-enhancement"
    fal_face_swap_model: str = "fal-ai/face-swap"
    # Настройки для Seedream
    fal_seedream_edit_model: str = Field(default="fal-ai/bytedance/seedream/v4.5/edit")
    fal_seedream_create_model: str = Field(default="fal-ai/bytedance/seedream/v4.5/text-to-image")
    # Настройки для Flux 2 Flex
    fal_flux2flex_model: str = "fal-ai/flux-2-flex"
    # Настройки для WaveSpeedAI
    wavespeed_api_key: str | None = None  # API ключ WaveSpeedAI (обязательно для WaveSpeed Face Swap - высокое качество)
    wavespeed_face_swap_model: str = "wavespeed-ai/image-face-swap"  # Модель для face swap на WaveSpeedAI
    wavespeed_text_model: str = "openai/gpt-image-1-mini/edit"  # Модель для дизайнерского текста (OpenAI GPT Image 1 Mini Edit через WaveSpeedAI - лучшее качество кириллицы)
    wavespeed_gpt_create_model: str = "openai/gpt-image-1-mini"  # GPT модель для создания изображений через WaveSpeedAI - лучшее качество кириллицы (GPT Image 1 Mini)
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

