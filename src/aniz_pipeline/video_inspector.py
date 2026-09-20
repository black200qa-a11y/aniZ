from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger(__name__)
VIDEO_EXTENSIONS = {".mkv", ".mp4"}


class VideoInspectionError(RuntimeError):
    pass


class VideoInspector:
    def __init__(self, convert_mkv_to_mp4: bool = False):
        self.convert_mkv_to_mp4 = convert_mkv_to_mp4

    def pick_main_video(self, directory: Path) -> Path:
        candidates = [path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]
        if not candidates:
            raise VideoInspectionError(f"No MKV/MP4 video found under {directory}")
        selected = max(candidates, key=lambda path: path.stat().st_size)
        log.info("Selected main video: %s (%d bytes)", selected, selected.stat().st_size)
        return selected

    async def inspect_and_prepare(self, source: Path) -> Path:
        if source.suffix.lower() != ".mkv" or not self.convert_mkv_to_mp4:
            return source
        target = source.with_suffix(".mp4")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-map", "0", "-c", "copy", str(target)]
        log.info("Converting MKV to MP4 with stream copy: %s -> %s", source, target)
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await process.communicate()
        if process.returncode != 0 or not target.exists() or target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            raise VideoInspectionError(f"FFmpeg conversion failed: {stderr.decode(errors='replace')[-1000:]}")
        source.unlink(missing_ok=True)
        return target
