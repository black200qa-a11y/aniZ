from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument

from ..core.database import Mongo


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "unknown-anime"


class CatalogSyncService:
    def __init__(self, mongo: Mongo, public_base_url: str, channel_id: int):
        self.mongo = mongo
        self.public_base_url = public_base_url.rstrip("/")
        self.channel_id = channel_id

    async def upsert_uploaded_episode(self, *, anime_title: str, episode_number: int | None, quality: str, file_format: str, telegram_file_id: str, telegram_message_id: int, file_size: int, duration: int | None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.mongo.db is None:
            raise RuntimeError("MongoDB is not connected")
        now = datetime.now(UTC)
        anime_id = slugify(anime_title)
        episode_key = {"anime_id": anime_id, "episode_number": episode_number, "quality": quality}
        await self.mongo.db.animes.update_one({"anime_id": anime_id}, {"$set": {"title": anime_title, "updated_at": now}, "$setOnInsert": {"anime_id": anime_id, "cover_image": None, "genres": [], "synopsis": None, "status": "ongoing", "created_at": now}}, upsert=True)
        episode = await self.mongo.db.episodes.find_one_and_update(episode_key, {"$set": {"telegram_file_id": telegram_file_id, "telegram_message_id": telegram_message_id, "telegram_channel_id": self.channel_id, "file_size": file_size, "duration": duration, "updated_at": now, **(metadata or {})}, "$setOnInsert": {"stream_slug": f"{anime_id}-{episode_number or 'unknown'}-{quality}", "created_at": now}}, upsert=True, return_document=ReturnDocument.AFTER)
        return episode
