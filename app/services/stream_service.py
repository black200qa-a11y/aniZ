from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import HTTPException

from ..core.telegram_client import TelegramClientManager


class TelegramStreamService:
    def __init__(self, telegram: TelegramClientManager, max_concurrent: int, chunk_size: int):
        self.telegram = telegram
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.chunk_size = chunk_size

    async def stream(self, *, channel_id: int, message_id: int, start: int, end: int) -> AsyncIterator[bytes]:
        if start < 0 or end < start:
            raise HTTPException(416, "Invalid byte range")
        if self.telegram is None:
            raise HTTPException(503, "Telegram streaming is available on the PC deployment only")
        async with self.semaphore, self.telegram.connection() as client:
                try:
                    message = await client.get_messages(channel_id, message_id)
                    if not message or not (message.video or message.document):
                        raise HTTPException(404, "Telegram media not found")
                    offset = start
                    remaining = end - start + 1
                    limit = max(1, (remaining + self.chunk_size - 1) // self.chunk_size)
                    async for chunk in client.stream_media(message, offset=offset, limit=limit):
                        if not chunk:
                            break
                        if len(chunk) > remaining:
                            chunk = chunk[:remaining]
                        yield chunk
                        remaining -= len(chunk)
                        offset += len(chunk)
                        if remaining <= 0:
                            break
                except HTTPException:
                    raise
                except Exception as exc:
                    raise HTTPException(502, f"Telegram streaming failed: {exc}") from exc
