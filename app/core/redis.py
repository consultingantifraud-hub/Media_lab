from __future__ import annotations

import redis

from app.core.config import settings


def get_redis_connection() -> redis.Redis:
    """Get Redis connection."""
    return redis.Redis.from_url(settings.redis_url, decode_responses=False)

