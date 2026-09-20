from __future__ import annotations

import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..services.admin_service import AdminService
from ..services.nyaa_service import NyaaSearchService

router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).parents[1] / "templates"))


def logged_in(request: Request) -> bool:
    return request.session.get("admin_authenticated") is True


def require_admin(request: Request) -> None:
    if not logged_in(request):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Admin login required")


def service(request: Request) -> AdminService:
    return request.app.state.admin_service


def nyaa_service(request: Request) -> NyaaSearchService:
    if not hasattr(request.app.state, "nyaa_service"):
        request.app.state.nyaa_service = NyaaSearchService()
    return request.app.state.nyaa_service


@router.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/admin/login", response_class=HTMLResponse)
async def login(request: Request, password: str = Form(...)):
    expected = request.app.state.settings.admin_password
    if not expected or not secrets.compare_digest(password, expected):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid password"}, status_code=401)
    request.session["admin_authenticated"] = True
    return RedirectResponse("/admin", status_code=303)


@router.post("/admin/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=303)


@router.get("/admin", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": await service(request).stats(request.app.state.mongo)})


@router.get("/admin/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    if not logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    return templates.TemplateResponse("logs.html", {"request": request})


@router.get("/admin/search", response_class=HTMLResponse)
async def nyaa_search_page(request: Request):
    if not logged_in(request):
        return RedirectResponse("/admin/login", status_code=303)
    return templates.TemplateResponse("search.html", {"request": request})


@router.get("/admin/api/stats")
async def stats(request: Request):
    require_admin(request)
    return await service(request).stats(request.app.state.mongo)


@router.get("/admin/api/logs")
async def logs(request: Request, filename: str = "pipeline.log"):
    require_admin(request)
    return {"filename": filename, "lines": service(request).tail(filename)}


@router.get("/admin/api/activity")
async def activity(request: Request):
    require_admin(request)
    return service(request).activity()


@router.get("/api/v1/admin/nyaa/search")
async def nyaa_search(request: Request, q: str = ""):
    require_admin(request)
    return {"query": q, "results": await nyaa_service(request).search(q, 500)}


@router.get("/api/v1/admin/nyaa/inspect")
async def nyaa_inspect(request: Request, view: str):
    require_admin(request)
    return {"view": view, "files": await nyaa_service(request).inspect(view)}


@router.get("/admin/api/episodes")
async def episodes(request: Request, search: str = "", limit: int = 100):
    require_admin(request)
    query = {"$or": [{"anime_id": {"$regex": search, "$options": "i"}}, {"quality": {"$regex": search, "$options": "i"}}]} if search else {}
    docs = await request.app.state.mongo.db.episodes.find(query, {"_id": 0}).sort("created_at", -1).limit(min(limit, 200)).to_list(length=min(limit, 200))
    return docs


@router.post("/admin/api/manual-add")
async def manual_add(request: Request, source: str = Form(...)):
    require_admin(request)
    if not source.startswith(("magnet:", "http://", "https://")):
        raise HTTPException(400, "Enter a magnet link or Nyaa URL")
    now = datetime.now(UTC)
    result = await request.app.state.mongo.db.manual_jobs.insert_one({"source": source, "status": "PENDING", "created_at": now})
    return {"job_id": str(result.inserted_id), "status": "PENDING"}


@router.post("/api/v1/admin/nyaa/queue")
async def nyaa_queue(request: Request, payload: dict[str, Any]):
    require_admin(request)
    items = payload.get("items", [])
    if not isinstance(items, list) or len(items) > 500:
        raise HTTPException(400, "items must be a list of at most 500 results")
    now = datetime.now(UTC)
    jobs = [{"source": item.get("magnet", ""), "title": item.get("title", ""), "tags": item.get("tags", []), "nyaa_id": item.get("nyaa_id", ""), "status": "PENDING", "created_at": now} for item in items if isinstance(item, dict) and str(item.get("magnet", "")).startswith("magnet:")]
    if not jobs:
        raise HTTPException(400, "No valid magnet results selected")
    result = await request.app.state.mongo.db.manual_jobs.insert_many(jobs)
    return {"queued": len(result.inserted_ids), "status": "PENDING"}


@router.delete("/admin/api/episodes/{stream_slug}")
async def delete_episode(stream_slug: str, request: Request):
    require_admin(request)
    result = await request.app.state.mongo.db.episodes.delete_one({"stream_slug": stream_slug})
    if result.deleted_count == 0:
        raise HTTPException(404, "Episode not found")
    return {"deleted": True, "stream_slug": stream_slug}


@router.post("/admin/api/episodes/{stream_slug}/resync")
async def resync_episode(stream_slug: str, request: Request):
    require_admin(request)
    result = await request.app.state.mongo.db.episodes.update_one({"stream_slug": stream_slug}, {"$set": {"updated_at": datetime.now(UTC)}})
    if result.matched_count == 0:
        raise HTTPException(404, "Episode not found")
    return {"resynced": True, "stream_slug": stream_slug}
