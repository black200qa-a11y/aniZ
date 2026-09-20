from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..models.schemas import AnimeOut, EpisodeOut, PaginatedAnimes

router = APIRouter(prefix="/api/v1", tags=["catalog"])


def episode_out(doc: dict, request: Request) -> EpisodeOut:
    slug = doc["stream_slug"]
    base = str(request.base_url).rstrip("/")
    return EpisodeOut(id=slug, anime_id=doc["anime_id"], episode_number=doc.get("episode_number"), quality=doc["quality"], format=doc.get("format", "mkv"), file_size=doc.get("file_size", 0), duration=doc.get("duration"), stream_slug=slug, stream_url=f"{base}/api/v1/stream/{slug}", created_at=doc["created_at"])


@router.get("/animes", response_model=PaginatedAnimes)
async def list_animes(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    db = request.app.state.mongo.db
    cursor = db.animes.find({}, {"_id": 0}).sort("updated_at", -1).skip((page - 1) * page_size).limit(page_size + 1)
    docs = await cursor.to_list(length=page_size + 1)
    return PaginatedAnimes(items=[AnimeOut(**doc) for doc in docs[:page_size]], page=page, page_size=page_size, has_next=len(docs) > page_size)


@router.get("/animes/{anime_id}/episodes", response_model=list[EpisodeOut])
async def list_episodes(anime_id: str, request: Request):
    db = request.app.state.mongo.db
    anime = await db.animes.find_one({"anime_id": anime_id})
    if anime is None:
        raise HTTPException(404, "Anime not found")
    docs = await db.episodes.find({"anime_id": anime_id}, {"_id": 0}).sort([("episode_number", 1), ("quality", 1)]).to_list(length=None)
    return [episode_out(doc, request) for doc in docs]
