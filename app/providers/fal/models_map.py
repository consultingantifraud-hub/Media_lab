from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.config import settings

IMAGE_MODEL_ALIASES = {
    "light": settings.fal_standard_model,
    "standard": settings.fal_premium_model,
    "premium": settings.fal_premium_model,
    "inpaint": settings.fal_inpaint_model,
    "flux-inpaint": settings.fal_inpaint_model,
    "edit": settings.fal_edit_model,
    "chrono": settings.fal_edit_model,
    "chrono-edit": settings.fal_edit_model,
    "flux": settings.fal_standard_model,
    "flux-standard": settings.fal_standard_model,
    "flux-fast": "fal-ai/flux/schnell",
    "flux-dev": "fal-ai/flux-pro/v1.1-ultra",
    "flux-schnell": "fal-ai/flux/schnell",
    "flux-pro": settings.fal_premium_model,
    "flash": settings.fal_premium_model,
    "nano-banana": "fal-ai/nano-banana",
    "nano-banana-pro": "fal-ai/nano-banana-pro",
    "wavespeed-gpt": "fal-ai/nano-banana-pro",
    "gpt-create": "fal-ai/nano-banana-pro",
    "dalle3": "fal-ai/dall-e-3",
    "retouch": settings.fal_retoucher_model,
    "retoucher": settings.fal_retoucher_model,
    "face-enhancement": settings.fal_face_enhance_model,
    "face-enhance": settings.fal_face_enhance_model,
    "seededit": "fal-ai/bytedance/seededit/v3/edit-image",
    "seededit-v3": "fal-ai/bytedance/seededit/v3/edit-image",
    "seededit3": "fal-ai/bytedance/seededit/v3/edit-image",
    "seedream": "fal-ai/bytedance/seedream/v4/edit",
    "seedream-edit": "fal-ai/bytedance/seedream/v4/edit",
    "seedream-create": "fal-ai/bytedance/seedream/v4/text-to-image",  # Модель для создания без входного изображения
    "flux2flex-create": "fal-ai/flux-2-flex",  # Flux 2 Flex модель для создания изображений
    # ВРЕМЕННО ОТКЛЮЧЕНО: Flux 2 Pro Edit - проблемы с размерами изображений
    # "flux2pro-edit": "fal-ai/flux-2-pro/edit",  # Flux 2 Pro модель для редактирования изображений
    "gpt-image-1-mini": "fal-ai/gpt-image-1-mini/edit",
    "reve": "fal-ai/reve/fast/edit",
    "stylish": "fal-ai/ideogram/v2/edit",
    "stylish-text": "fal-ai/ideogram/v2/edit",
    "ideogram-edit": "fal-ai/ideogram/v2/edit",
    "upscale": settings.fal_upscale_model,
    "face-swap": settings.fal_face_swap_model,
    "recraft-upscale-crisp": "fal-ai/recraft/upscale/crisp",
    "recraft-upscale-creative": "fal-ai/recraft/upscale/creative",
    "esrgan": "fal-ai/esrgan",
}


MODEL_CAPABILITIES = {
    settings.fal_inpaint_model: {"requires_mask": True, "inpaint_payload": True},
    "fal-ai/flux/inpaint": {"requires_mask": True, "inpaint_payload": True},
    "fal-ai/fooocus/inpaint": {"requires_mask": True, "inpaint_payload": True},
    "fal-ai/nana-inpaint": {"requires_mask": True, "inpaint_payload": True},
    "fal-ai/recraft-advanced/inpaint": {"requires_mask": True, "inpaint_payload": True},
    settings.fal_edit_model: {"requires_mask": False},
    "fal-ai/reve/fast/edit": {"requires_mask": False},
    "fal-ai/reve/edit": {"requires_mask": False},
    "fal-ai/bytedance/seededit/v3/edit-image": {"requires_mask": False},
    "fal-ai/bytedance/seedream/v4/edit": {"requires_mask": False},
    "fal-ai/gpt-image-1-mini/edit": {"requires_mask": False},
    "fal-ai/ideogram/v2/edit": {"requires_mask": False},
    # ВРЕМЕННО ОТКЛЮЧЕНО: Flux 2 Pro Edit - проблемы с размерами изображений
    # "fal-ai/flux-2-pro/edit": {"requires_mask": False},  # Flux 2 Pro Edit - редактирование без маски
    "fal-ai/flux-pro/kontext": {"requires_mask": True, "inpaint_payload": True},
}

MODEL_DEFAULT_OPTIONS: dict[str, dict[str, Any]] = {
    settings.fal_edit_model: {
        "resolution": "720p",
        "output_format": "png",
    },
    "fal-ai/bytedance/seedream/v4/text-to-image": {
        "output_format": "png",  # PNG формат для лучшего качества
    },
    "fal-ai/recraft/upscale/crisp": {
        "enable_safety_checker": False,
        "output_format": "png",  # Use PNG for better quality (like Smart merge)
    },
    "fal-ai/recraft/upscale/creative": {
        "enable_safety_checker": False,
        "output_format": "jpeg",
        "quality": 50,  # Lower quality to reduce file size
    },
    "fal-ai/esrgan": {
        "scale": 2,  # Use 2x scale for better quality
        "output_format": "png",  # Request PNG format for better quality (like Smart merge)
    },
    "fal-ai/nano-banana": {
        "output_format": "png",  # PNG формат (fal.ai может сжимать PNG, но это лучший вариант)
        # Примечание: fal.ai может возвращать сжатые PNG изображения (~250-300 KB)
        # Это ограничение модели, а не нашей обработки
    },
    "fal-ai/face-swap": {
        # fal-ai/face-swap may not need these parameters
        # Will be handled dynamically in submit_face_swap
    },
}


@lru_cache
def _normalized_aliases() -> dict[str, str]:
    return {key.lower(): value for key, value in IMAGE_MODEL_ALIASES.items()}


def resolve_alias(name: str | None) -> str | None:
    if not name:
        return None
    return _normalized_aliases().get(name.lower(), name)


def get_image_model(name: str | None = None, *, preset: str | None = None) -> str:
    resolved = resolve_alias(name)
    if resolved:
        return resolved
    if preset:
        preset_resolved = resolve_alias(preset)
        if preset_resolved:
            return preset_resolved
    return settings.fal_standard_model


def model_requires_mask(model: str) -> bool:
    """Return True if the resolved model expects a mask."""
    return MODEL_CAPABILITIES.get(model, {}).get("requires_mask", False)


def model_supports_inpaint_payload(model: str) -> bool:
    """Return True if the model expects inpaint_* payload fields."""
    return MODEL_CAPABILITIES.get(model, {}).get("inpaint_payload", False)


def apply_model_defaults(model: str, payload: dict[str, Any]) -> dict[str, Any]:
    defaults = MODEL_DEFAULT_OPTIONS.get(model)
    if not defaults:
        return payload
    for key, value in defaults.items():
        payload.setdefault(key, value)
    return payload
