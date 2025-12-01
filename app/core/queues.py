from __future__ import annotations

from rq import Queue
from rq.job import Job
from rq.registry import FinishedJobRegistry

from app.core.redis import get_redis_connection

IMG_QUEUE_NAME = "img_queue"


def get_image_queue() -> Queue:
    return Queue(name=IMG_QUEUE_NAME, connection=get_redis_connection())


def get_job(job_id: str) -> Job | None:
    """Get job by ID from image queue."""
    connection = get_redis_connection()
    queue = Queue(name=IMG_QUEUE_NAME, connection=connection)
    try:
        job = queue.fetch_job(job_id)
        if job:
            return job
    except Exception:  # pragma: no cover - safe guard
        pass
    return None


def get_finished_registry(queue_name: str) -> FinishedJobRegistry:
    queue = Queue(name=queue_name, connection=get_redis_connection())
    return FinishedJobRegistry(name=queue_name, connection=queue.connection)

