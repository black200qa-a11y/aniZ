from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from pathlib import Path

import aiohttp
from pydantic_settings import BaseSettings, SettingsConfigDict
from pymongo import ReturnDocument

from app.core.database import Mongo
from app.services.sync_service import CatalogSyncService

from .downloader import Aria2Downloader
from .logging_config import configure_logging
from .models import PipelineResult, Release, completed_result
from .scraper import NyaaScraper
from .state import StateStore
from .uploader import TelegramUploader
from .video_inspector import VideoInspector

log = logging.getLogger("aniz_pipeline")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    nyaa_feed_urls: str
    nyaa_groups: str = ""
    nyaa_qualities: str = "1080p,720p"
    nyaa_check_interval: int = 300
    nyaa_check_interval_minutes: int = 15
    quality_filters: str = '["1080p", "720p"]'
    release_groups: str = '["SubsPlease", "Erai-raws"]'
    temp_download_dir: Path = Path("./temp_downloads")
    state_db_path: Path = Path("./aniz_state.sqlite3")
    aria2_rpc_url: str = ""
    aria2_host: str = "127.0.0.1"
    aria2_port: int = 6800
    aria2_secret: str = ""
    aria2_download_timeout: int = 7200
    api_id: int
    api_hash: str
    string_session: str
    tg_channel_id: int
    mongodb_sync_enabled: bool = False
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    database_name: str = "aniz"
    mongodb_server_selection_timeout_ms: int = 3000
    api_public_base_url: str = "http://127.0.0.1:8000"
    max_concurrent_uploads: int = 1
    cleanup_on_upload_failure: bool = False
    log_level: str = "INFO"
    log_dir: Path = Path("./logs")
    convert_mkv_to_mp4: bool = False

    @property
    def feed_urls(self) -> list[str]: return [x.strip() for x in self.nyaa_feed_urls.split(",") if x.strip()]
    @property
    def groups(self) -> list[str]:
        try: return [str(x) for x in json.loads(self.release_groups)]
        except (json.JSONDecodeError, TypeError): return [x.strip() for x in self.nyaa_groups.split(",") if x.strip()]
    @property
    def qualities(self) -> list[str]:
        try: return [str(x) for x in json.loads(self.quality_filters)]
        except (json.JSONDecodeError, TypeError): return [x.strip() for x in self.nyaa_qualities.split(",") if x.strip()]
    @property
    def aria2_endpoint(self) -> str: return self.aria2_rpc_url or f"http://{self.aria2_host}:{self.aria2_port}"
    @property
    def poll_interval_seconds(self) -> int: return self.nyaa_check_interval_minutes * 60 if self.nyaa_check_interval_minutes != 15 else self.nyaa_check_interval


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = StateStore(settings.state_db_path)
        self.scraper = NyaaScraper(settings.feed_urls, settings.groups, settings.qualities)
        self.downloader = Aria2Downloader(settings.aria2_endpoint, settings.aria2_secret, settings.temp_download_dir, settings.aria2_download_timeout)
        self.video_inspector = VideoInspector(settings.convert_mkv_to_mp4)
        self.uploader = TelegramUploader(settings.api_id, settings.api_hash, settings.string_session, settings.tg_channel_id)
        self.mongo = Mongo(settings)
        self.catalog = CatalogSyncService(self.mongo, settings.api_public_base_url, settings.tg_channel_id)
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_uploads)
        self.stop_event = asyncio.Event()

    async def process(self, release: Release) -> PipelineResult | None:
        if not await self.store.claim(release.magnet_hash, release.title):
            return None
        path: Path | None = None
        try:
            async with self.semaphore:
                path = await self.downloader.download(release.magnet_uri, release.magnet_hash)
                path = self.video_inspector.pick_main_video(path.parent)
                path = await self.video_inspector.inspect_and_prepare(path)
                telegram = await self.uploader.upload(path)
                result = completed_result(release, path, telegram["file_id"], telegram["message_id"], telegram.get("duration"))
                if self.settings.mongodb_sync_enabled:
                    await self.catalog.upsert_uploaded_episode(
                        anime_title=release.anime_title,
                        episode_number=release.episode_number,
                        quality=release.quality,
                        file_format=result.format,
                        telegram_file_id=result.telegram_file_id or "",
                        telegram_message_id=result.telegram_message_id or 0,
                        file_size=result.file_size_bytes or 0,
                        duration=result.video_duration,
                    )
                await self.store.mark(release.magnet_hash, "COMPLETED")
                print(json.dumps(result.as_dict(), ensure_ascii=False), flush=True)
                path.unlink(missing_ok=True)
                return result
        except Exception as exc:
            await self.store.mark(release.magnet_hash, "FAILED", str(exc))
            log.exception("Release failed: %s", release.title)
            if path and self.settings.cleanup_on_upload_failure:
                path.unlink(missing_ok=True)
            return None

    async def run(self) -> None:
        await self.store.open()
        if self.settings.mongodb_sync_enabled:
            await self.mongo.connect()
        self.settings.temp_download_dir.mkdir(parents=True, exist_ok=True)
        timeout = aiohttp.ClientTimeout(total=60)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                while not self.stop_event.is_set():
                    releases = await self.scraper.poll(session)
                    if self.settings.mongodb_sync_enabled and self.mongo.db is not None:
                        job = await self.mongo.db.manual_jobs.find_one_and_update({"status": "PENDING"}, {"$set": {"status": "PROCESSING"}}, sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)
                        if job:
                            try:
                                releases.append(await self.scraper.resolve_source(session, job["source"]))
                                await self.mongo.db.manual_jobs.update_one({"_id": job["_id"]}, {"$set": {"status": "RESOLVED"}})
                            except Exception as exc:  # noqa: BLE001 - persist job failure and continue worker loop
                                await self.mongo.db.manual_jobs.update_one({"_id": job["_id"]}, {"$set": {"status": "FAILED", "error": str(exc)}})
                    await asyncio.gather(*(self.process(r) for r in releases))
                    try:
                        await asyncio.wait_for(self.stop_event.wait(), timeout=self.settings.poll_interval_seconds)
                    except TimeoutError:
                        pass
        finally:
            if self.settings.mongodb_sync_enabled:
                await self.mongo.close()
            await self.store.close()

    def stop(self) -> None:
        self.stop_event.set()


def cli() -> None:
    parser = argparse.ArgumentParser(description="Poll Nyaa RSS, download with aria2, upload to Telegram, and emit JSON")
    parser.add_argument("--once", action="store_true", help="poll and process once, then exit")
    args = parser.parse_args()
    settings = Settings()
    configure_logging(settings.log_level, settings.log_dir)
    pipeline = Pipeline(settings)
    if args.once:
        async def once() -> None:
            await pipeline.store.open()
            if settings.mongodb_sync_enabled:
                await pipeline.mongo.connect()
            try:
                async with aiohttp.ClientSession() as session:
                    for release in await pipeline.scraper.poll(session):
                        await pipeline.process(release)
            finally:
                if settings.mongodb_sync_enabled:
                    await pipeline.mongo.close()
                await pipeline.store.close()
        asyncio.run(once())
        return
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, pipeline.stop)
    try:
        loop.run_until_complete(pipeline.run())
    finally:
        loop.close()


if __name__ == "__main__":
    cli()
