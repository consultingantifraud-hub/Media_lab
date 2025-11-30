from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app.core import settings, setup_logging
from app.core.queues import get_job

app = FastAPI(title="TG Media Service", version="0.1.0")


@app.on_event("startup")
async def on_startup() -> None:
    setup_logging()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
async def version() -> dict[str, str]:
    return {"version": app.version, "env": settings.app_env}


@app.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.get_status(),
        "meta": job.meta,
    }

