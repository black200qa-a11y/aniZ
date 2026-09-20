from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AnimeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    anime_id: str
    title: str
    cover_image: str | None = None
    genres: list[str] = Field(default_factory=list)
    synopsis: str | None = None
    status: str = "ongoing"
    created_at: datetime
    updated_at: datetime


class EpisodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    anime_id: str
    episode_number: int | None
    quality: str
    format: str
    file_size: int
    duration: int | None
    stream_slug: str
    stream_url: str
    created_at: datetime


class PaginatedAnimes(BaseModel):
    items: list[AnimeOut]
    page: int
    page_size: int
    has_next: bool
