from __future__ import annotations

import secrets
import uuid


def generate_job_id() -> str:
    return uuid.uuid4().hex


def generate_filename(prefix: str, suffix: str) -> str:
    token = secrets.token_hex(4)
    return f"{prefix}_{token}.{suffix}"

