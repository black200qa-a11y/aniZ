from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError

log = logging.getLogger(__name__)


class TelegramUploader:
    def __init__(self, api_id: int, api_hash: str, session_string: str, channel_id: int, max_retries: int = 4):
        self.client = Client("aniz-userbot", api_id=api_id, api_hash=api_hash, session_string=session_string, in_memory=True)
        self.channel_id = channel_id
        self.max_retries = max_retries

    async def upload(self, path: Path) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self.client:
                    last = {"sent": 0, "total": path.stat().st_size}

                    async def progress(current: int, total: int, last: dict[str, int] = last, path: Path = path) -> None:
                        if current == total or current - last["sent"] >= 50 * 1024 * 1024:
                            log.info("Telegram upload %s: %.1f%%", path.name, current * 100 / max(total, 1))
                            last["sent"] = current

                    kwargs = {"chat_id": self.channel_id, "caption": path.name, "progress": progress}
                    if path.suffix.lower() == ".mp4":
                        message = await self.client.send_video(video=str(path), supports_streaming=True, **kwargs)
                    else:
                        message = await self.client.send_document(document=str(path), **kwargs)
                    media = message.video or message.document
                    if media is None or not media.file_id:
                        raise RuntimeError("Telegram returned a message without a file id")
                    return {"file_id": media.file_id, "message_id": message.id, "duration": getattr(media, "duration", None)}
            except FloodWait as exc:
                last_error = exc
                log.warning("Telegram flood wait: sleeping %ss", exc.value)
                await asyncio.sleep(exc.value)
            except (RPCError, OSError, RuntimeError) as exc:
                last_error = exc
                delay = min(60, 2 ** attempt)
                log.warning("Telegram upload attempt %d/%d failed: %s; retrying in %ss", attempt, self.max_retries, exc, delay)
                await asyncio.sleep(delay)
        raise RuntimeError(f"Telegram upload failed after {self.max_retries} attempts: {last_error}") from last_error
