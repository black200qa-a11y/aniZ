from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True, frozen=True)
class Release:
    title: str
    magnet_uri: str
    source_url: str
    anime_title: str
    episode_number: int | None
    quality: str
    file_format: str

    @property
    def magnet_hash(self) -> str:
        match = re.search(r"btih:([A-Za-z0-9]+)", self.magnet_uri, re.IGNORECASE)
        return (match.group(1).lower() if match else hashlib.sha256(self.magnet_uri.encode()).hexdigest())


@dataclass(slots=True)
class PipelineResult:
    anime_title: str
    episode_number: int | None
    quality: str
    format: str
    telegram_file_id: str | None
    telegram_message_id: int | None
    file_size_bytes: int | None
    video_duration: int | None
    status: str
    magnet_hash: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_release(title: str, magnet_uri: str, source_url: str = "") -> Release:
    """Best-effort metadata extraction; feed-specific custom parsers can replace this."""
    cleaned = re.sub(r"\[[^]]+\]", " ", title)
    episode_match = re.search(r"(?:\s|[-_])(?:ep(?:isode)?[ ._-]*)?(\d{1,4})(?:\D|$)", cleaned, re.IGNORECASE)
    quality_match = re.search(r"(2160p|1080p|720p|480p|360p)", title, re.IGNORECASE)
    format_match = re.search(r"\.(mkv|mp4)(?:\b|$)", title, re.IGNORECASE)
    quality = quality_match.group(1).lower() if quality_match else "unknown"
    file_format = format_match.group(1).lower() if format_match else "mkv"
    anime = re.split(r"\s+(?:S\d+|\d{1,4}|1080p|720p|480p)\b", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    anime = re.sub(r"[_\.]+", " ", anime).strip(" -") or title
    return Release(title, magnet_uri, source_url, anime, int(episode_match.group(1)) if episode_match else None, quality, file_format)


def completed_result(release: Release, path: Path, file_id: str, message_id: int, duration: int | None) -> PipelineResult:
    return PipelineResult(release.anime_title, release.episode_number, release.quality, path.suffix.lstrip(".").lower(), file_id, message_id, path.stat().st_size, duration, "COMPLETED", release.magnet_hash)
