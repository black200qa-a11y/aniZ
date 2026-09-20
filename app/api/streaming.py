from __future__ import annotations

import re

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/v1", tags=["streaming"])
_RANGE = re.compile(r"bytes=(\d*)-(\d*)$")


@router.get("/stream/{episode_id}")
async def stream_episode(episode_id: str, request: Request, range_header: str | None = Header(default=None, alias="Range")):
    db = request.app.state.mongo.db
    doc = await db.episodes.find_one({"stream_slug": episode_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(404, "Episode not found")
    size = int(doc.get("file_size", 0))
    if size <= 0:
        raise HTTPException(500, "Episode has no valid file size")
    start, end = 0, size - 1
    status = 200
    if range_header:
        match = _RANGE.fullmatch(range_header.strip())
        if not match:
            raise HTTPException(416, "Invalid Range header", headers={"Content-Range": f"bytes */{size}"})
        raw_start, raw_end = match.groups()
        if raw_start:
            start = int(raw_start)
            end = int(raw_end) if raw_end else size - 1
        elif raw_end:
            suffix = int(raw_end)
            if suffix <= 0:
                raise HTTPException(416, "Invalid byte suffix", headers={"Content-Range": f"bytes */{size}"})
            start = max(size - suffix, 0)
        if start >= size or end < start:
            raise HTTPException(416, "Range not satisfiable", headers={"Content-Range": f"bytes */{size}"})
        end = min(end, size - 1)
        status = 206
    length = end - start + 1
    media_type = "video/mp4" if doc.get("format", "").lower() == "mp4" else "video/x-matroska"
    iterator = request.app.state.streamer.stream(channel_id=int(doc["telegram_channel_id"]), message_id=int(doc["telegram_message_id"]), start=start, end=end)
    headers = {"Accept-Ranges": "bytes", "Content-Length": str(length), "Content-Type": media_type, "Content-Disposition": f'inline; filename="{episode_id}.{doc.get("format", "mkv")}"'}
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(iterator, status_code=status, headers=headers, media_type=media_type)
