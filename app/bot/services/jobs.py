from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.core.ids import generate_filename, generate_job_id
from app.core.queues import get_image_queue
from app.core.storage import storage

# Таймауты для всех операций (4 минуты = 240 секунд)
# Если задача не выполнилась за это время, пользователь получит уведомление
JOB_TIMEOUTS = {
    "image": 240,        # 4 минуты - генерация изображений
    "edit": 240,         # 4 минуты - редактирование изображений
    "smart_merge": 240,  # 4 минуты - объединение изображений
    "retouch": 240,      # 4 минуты - ретушь
    "face_swap": 240,    # 4 минуты - замена лица
    "upscale": 240,      # 4 минуты - улучшение качества
}

# TTL для результатов задач (24 часа)
RESULT_TTL = 86400
TTL = 86400


def enqueue_image(prompt: str, **opts) -> tuple[str, Path]:
    job_id = generate_job_id()
    filename = generate_filename("image", "png")
    output_path = storage.base_dir / "images" / filename

    queue = get_image_queue()
    logger.info("Enqueue image job {} ({})", job_id, prompt)
    queue.enqueue(
        "app.workers.image_worker_server.process_image_job",
        kwargs={
            "job_id": job_id,
            "prompt": prompt,
            "options": opts,
            "output_path": output_path.as_posix(),
        },
        job_id=job_id,
        timeout=JOB_TIMEOUTS["image"],
        result_ttl=RESULT_TTL,
        ttl=TTL,
    )
    return job_id, output_path


def enqueue_smart_merge(prompt: str, image_sources: list[dict[str, str | None]], **opts) -> tuple[str, Path]:
    job_id = generate_job_id()
    filename = generate_filename("image-smart-merge", "png")
    output_path = storage.base_dir / "edits" / filename

    queue = get_image_queue()
    logger.info("Enqueue smart merge job {} ({}), opts keys: {}, width={}, height={}, model={}", 
               job_id, prompt, list(opts.keys()), opts.get("width"), opts.get("height"), opts.get("model"))
    queue.enqueue(
        "app.workers.image_worker_server.process_smart_merge_job",
        kwargs={
            "job_id": job_id,
            "prompt": prompt,
            "image_sources": image_sources,
            "options": opts,
            "output_path": output_path.as_posix(),
        },
        job_id=job_id,
        timeout=JOB_TIMEOUTS["smart_merge"],
        result_ttl=RESULT_TTL,
        ttl=TTL,
    )
    return job_id, output_path


def enqueue_face_swap(
    *,
    source_path: str,
    target_path: str,
    instruction: str | None = None,
    **opts,
) -> tuple[str, Path]:
    job_id = generate_job_id()
    filename = generate_filename("face-swap", "png")
    output_path = storage.base_dir / "face_swap" / filename

    queue = get_image_queue()
    operation_id = opts.get("operation_id")
    logger.info("Enqueue face swap job {} (instruction={}), operation_id={}, opts_keys={}", 
                job_id, instruction or "none", operation_id, list(opts.keys()))
    queue.enqueue(
        "app.workers.image_worker_server.process_face_swap_job",
        kwargs={
            "job_id": job_id,
            "source_path": source_path,
            "target_path": target_path,
            "instruction": instruction,
            "options": opts,
            "output_path": output_path.as_posix(),
        },
        job_id=job_id,
        timeout=JOB_TIMEOUTS["face_swap"],
        result_ttl=RESULT_TTL,
        ttl=TTL,
    )
    return job_id, output_path


def enqueue_image_edit(prompt: str, image_path: str, mask_path: str | None = None, **opts) -> tuple[str, Path]:
    job_id = generate_job_id()
    filename = generate_filename("image-edit", "png")
    output_path = storage.base_dir / "edits" / filename

    queue = get_image_queue()
    operation_id = opts.get("operation_id")
    logger.info("Enqueue image edit job {} ({}), operation_id={}, opts_keys={}", 
                job_id, prompt, operation_id, list(opts.keys()))
    queue.enqueue(
        "app.workers.image_worker_server.process_image_edit_job",
        kwargs={
            "job_id": job_id,
            "prompt": prompt,
            "image_path": image_path,
            "mask_path": mask_path,
            "options": opts,
            "output_path": output_path.as_posix(),
        },
        job_id=job_id,
        timeout=JOB_TIMEOUTS["edit"],
        result_ttl=RESULT_TTL,
        ttl=TTL,
    )
    return job_id, output_path


def enqueue_image_upscale(
    image_url: str | None = None,
    *,
    image_path: str | None = None,
    scale: int = 2,
    **opts,
) -> tuple[str, Path]:
    job_id = generate_job_id()
    filename = generate_filename("image-upscale", "png")
    output_path = storage.base_dir / "edits" / filename

    queue = get_image_queue()
    queue.enqueue(
        "app.workers.image_worker_server.process_image_upscale_job",
        kwargs={
            "job_id": job_id,
            "image_url": image_url,
            "image_path": image_path,
            "scale": scale,
            "options": opts,
            "output_path": output_path.as_posix(),
        },
        job_id=job_id,
        timeout=JOB_TIMEOUTS["upscale"],
        result_ttl=RESULT_TTL,
        ttl=TTL,
    )
    return job_id, output_path


def enqueue_retoucher(
    *,
    prompt: str,
    image_path: str,
    mode: str,
    instruction: str | None = None,
    **opts,
) -> tuple[str, Path]:
    job_id = generate_job_id()
    filename = generate_filename("image-retouch", "png")
    output_path = storage.base_dir / "edits" / filename

    queue = get_image_queue()
    logger.info(
        "Enqueue retoucher job {} ({}, mode={}, instruction={})",
        job_id,
        prompt,
        mode,
        instruction,
    )
    queue.enqueue(
        "app.workers.image_worker_server.process_retoucher_job",
        kwargs={
            "job_id": job_id,
            "prompt": prompt,
            "image_path": image_path,
            "mode": mode,
            "instruction": instruction,
            "options": opts,
            "output_path": output_path.as_posix(),
        },
        job_id=job_id,
        timeout=JOB_TIMEOUTS["retouch"],
        result_ttl=RESULT_TTL,
        ttl=TTL,
    )
    return job_id, output_path

