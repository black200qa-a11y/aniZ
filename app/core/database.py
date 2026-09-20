from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from .config import AppSettings


class Mongo:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.client: AsyncIOMotorClient | None = None
        self.db: AsyncIOMotorDatabase | None = None

    async def connect(self) -> None:
        self.client = AsyncIOMotorClient(self.settings.mongodb_uri, serverSelectionTimeoutMS=self.settings.mongodb_server_selection_timeout_ms)
        self.db = self.client[self.settings.database_name]
        await self.client.admin.command("ping")
        await self.db.animes.create_index("anime_id", unique=True)
        await self.db.episodes.create_index([("anime_id", 1), ("episode_number", 1), ("quality", 1)], unique=True)
        await self.db.episodes.create_index("stream_slug", unique=True)
        await self.db.episodes.create_index([("created_at", -1)])

    async def close(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
            self.db = None

    async def ping(self) -> bool:
        if not self.client:
            return False
        try:
            await self.client.admin.command("ping")
            return True
        except (PyMongoError, OSError):
            return False
