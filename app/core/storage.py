from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.core.config import settings


class MediaStorage:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = Path(base_dir or settings.media_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "images").mkdir(exist_ok=True)
        (self.base_dir / "edits").mkdir(exist_ok=True)
        (self.base_dir / "face_swap").mkdir(exist_ok=True)

    def save_placeholder(self, rel_path: Path, content: bytes) -> Path:
        target_path = self.base_dir / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        logger.debug("Saved placeholder media to {}", target_path)
        return target_path


storage = MediaStorage()

