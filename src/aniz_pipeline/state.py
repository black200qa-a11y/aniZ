from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = asyncio.Lock()
        self._conn: sqlite3.Connection | None = None

    async def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("CREATE TABLE IF NOT EXISTS releases (magnet_hash TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL, error TEXT)")
        self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    async def seen(self, magnet_hash: str) -> bool:
        async with self._lock:
            assert self._conn
            return self._conn.execute("SELECT 1 FROM releases WHERE magnet_hash = ?", (magnet_hash,)).fetchone() is not None

    async def claim(self, magnet_hash: str, title: str) -> bool:
        async with self._lock:
            assert self._conn
            now = datetime.now(UTC).isoformat()
            cur = self._conn.execute("INSERT OR IGNORE INTO releases VALUES (?, ?, 'PROCESSING', ?, NULL)", (magnet_hash, title, now))
            self._conn.commit()
            return cur.rowcount == 1

    async def mark(self, magnet_hash: str, status: str, error: str | None = None) -> None:
        async with self._lock:
            assert self._conn
            self._conn.execute("UPDATE releases SET status = ?, updated_at = ?, error = ? WHERE magnet_hash = ?", (status, datetime.now(UTC).isoformat(), error, magnet_hash))
            self._conn.commit()
