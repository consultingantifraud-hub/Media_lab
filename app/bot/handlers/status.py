from __future__ import annotations

from aiogram import Dispatcher, types
from aiogram.filters import Command
from loguru import logger

from app.core.queues import get_job


async def handle_status(message: types.Message) -> None:
    if not message.text:
        await message.answer("Укажите ID задачи: `/status <id>`", parse_mode="Markdown")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажите ID задачи: `/status <id>`", parse_mode="Markdown")
        return

    job_id = parts[1].strip()
    job = get_job(job_id)
    logger.debug("Status request for job {} -> {}", job_id, job.get_status() if job else "missing")

    if not job:
        await message.answer("❌ Задача не найдена.")
        return

    status = job.get_status()
    meta = job.meta or {}
    response = f"ℹ️ Статус: *{status}*"
    if "result_path" in meta:
        response += f"\nФайл: `{meta['result_path']}`"
    if "error" in meta:
        response += f"\nОшибка: {meta['error']}"

    await message.answer(response, parse_mode="Markdown")


def register_status_handlers(dp: Dispatcher) -> None:
    dp.message.register(handle_status, Command("status"))

