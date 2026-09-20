from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from pyrogram import Client

from .config import AppSettings


class TelegramClientManager:
    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.client = Client("aniz-api", api_id=settings.api_id, api_hash=settings.api_hash, session_string=settings.string_session, in_memory=True)
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        async with self._lock:
            if self._started and not self.client.is_connected:
                self._started = False
            if not self._started:
                await self.client.start()
                self._started = True

    async def stop(self) -> None:
        async with self._lock:
            if self._started:
                await self.client.stop()
                self._started = False

    async def health(self) -> bool:
        return self._started and self.client.is_connected

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[Client]:
        await self.start()
        yield self.client
