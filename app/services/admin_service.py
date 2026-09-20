from __future__ import annotations

from datetime import UTC, datetime, timedelta
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

    def activity(self) -> list[dict[str, int | str]]:
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        buckets = [{"hour": (now - timedelta(hours=index)).strftime("%H:%M"), "uploads": 0, "downloads": 0} for index in range(11, -1, -1)]
        path = self.log_dir / "pipeline.log"
        if not path.exists():
            return buckets
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-5000:]:
            try:
                timestamp = datetime.fromisoformat(line[:23]).replace(tzinfo=UTC).replace(minute=0, second=0, microsecond=0)
            except ValueError:
                continue
            for bucket in buckets:
                if bucket["hour"] == timestamp.strftime("%H:%M"):
                    lower = line.lower()
                    if "upload" in lower: bucket["uploads"] += 1
                    if "download" in lower: bucket["downloads"] += 1
                    break
        return buckets
