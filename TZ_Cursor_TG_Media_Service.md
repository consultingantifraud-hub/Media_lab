# ТЗ для Cursor — Telegram‑сервис генерации изображений и видео (локально → VPS)

## 1) Цель
Собрать работающий сервис в Телеграме для генерации **изображений** (text‑to‑image, image‑to‑image) и **видео** (text‑to‑video, image‑to‑video) через **Fal Model APIs** (OpenAI‑совместимый API). Оплата отключена (внутреннее использование).

## 2) Результат
- Telegram‑бот (лонг‑поллинг для локалки, опция вебхука для VPS).
- Мини‑API (FastAPI): `/health`, `/version`, `/jobs/{id}` (заготовка).
- Очереди задач (Redis + RQ).
- Провайдерный слой `providers/fal/*` (submit → poll → download) — **сейчас заглушки**.
- Сохранение результатов локально (`media/`).
- Docker Compose для локалки и переноса на VPS.
- Документация по запуску.

## 3) Стек
Python 3.12, aiogram 3.x, fastapi, httpx, pydantic, redis+rq, loguru, docker compose.

## 4) Структура
```
/app
  /bot/handlers (start, image, video, status)
  /core (config, logging, queues, storage, ids)
  /providers/fal (client, models_map, images, videos)
  /web (api)
  /workers (image_worker, video_worker)
/docker (Dockerfiles + docker-compose.yml)
/media/images  /media/videos
.env.example  README.md  requirements.txt
```

## 5) Функциональные требования
- Команды бота: `/start`, `/ping`, «Изображение», «Видео», `/status <id>`, `/my` (позже).
- Изображения: промпт + параметры (размер, стиль, отриц. промпт) — **пока заглушка**.
- Видео: длительность 4/8 сек, формат 16:9/9:16/1:1, звук да/нет — **пока заглушка**.
- Очереди: `img_queue`, `vid_queue`; задачи возвращают `job_id` и сохраняют файл в `media/`.

## 6) Провайдер (интерфейсы к реализации)
`providers/fal/images.py`:
- `submit_image(prompt: str, **opts) -> task_id`
- `submit_image_edit(image_path: str, prompt: str, mask_path: str|None, **opts) -> task_id`

`providers/fal/videos.py`:
- `submit_video_from_text(prompt: str, duration: int, aspect: str, audio: bool, **opts) -> task_id`
- `submit_video_from_image(image_path: str, prompt: str, duration: int, aspect: str, audio: bool, **opts) -> task_id`

Общее:
- `check_status(task_id) -> {status, result_url|None, error|None}`
- `download_result(result_url, target_path)`
- httpx + таймаут/ретраи; видео — polling с `video_poll_interval`, `video_max_wait_sec`.

## 7) Конфигурация (.env)
```
tg_bot_token=YOUR_TG_BOT_TOKEN
app_env=local
api_host=0.0.0.0
api_port=8000
redis_url=redis://localhost:6379/0
fal_queue_base_url=https://queue.fal.run
fal_api_key=YOUR_FAL_KEY
fal_standard_model=fal-ai/flux/schnell
fal_premium_model=fal-ai/nano-banana
video_poll_interval=5
video_max_wait_sec=900
media_dir=./media
```

## 8) Запуск локально
1. Python 3.12, Redis.
2. `python -m venv .venv && activate && pip install -r requirements.txt`
3. В двух окнах: `python -m rq worker -u redis://localhost:6379/0 img_queue` и `... vid_queue`
4. API: `uvicorn app.web.api:app --host 0.0.0.0 --port 8000 --reload`
5. Бот: `python app/bot/main.py`

## 9) Критерии приёмки
- По «Изображение» приходит файл‑заглушка в `media/images` и сообщение с `job_id`.
- По «Видео» приходит файл‑заглушка в `media/videos` и `job_id`.
- `/status <id>` работает.
- Воркеры перезапускаются без потери очереди.

## 10) Дальнейшие задачи
- Подключить реальные вызовы к Fal в `providers/fal/*`.
- Включить S3/MinIO и вебхук для VPS.
- Добавить «/my» и пагинацию истории.
