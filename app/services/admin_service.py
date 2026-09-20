from __future__ import annotations

from pathlib import Path

import psutil


class AdminService:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir

    async def stats(self, mongo) -> dict:
        db = mongo.db
        return {
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "active_downloads": 0,
            "total_animes": await db.animes.count_documents({}),
            "total_episodes": await db.episodes.count_documents({}),
        }

    def tail(self, filename: str, lines: int = 200) -> list[str]:
        if filename not in {"pipeline.log", "errors.log"}:
            raise ValueError("unsupported log file")
        path = self.log_dir / filename
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-min(lines, 200):]
