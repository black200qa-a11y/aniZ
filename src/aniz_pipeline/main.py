from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from pathlib import Path

import aiohttp
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database import Mongo
from app.services.sync_service import CatalogSyncService

from .downloader import Aria2Downloader
from .models import PipelineResult, Release, completed_result
from .scraper import NyaaScraper
from .state import StateStore
from .uploader import TelegramUploader

log = logging.getLogger("aniz_pipeline")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    nyaa_feed_urls: str
    nyaa_groups: str = ""
    nyaa_qualities: str = "1080p,720p"
    nyaa_check_interval: int = 300
    temp_download_dir: Path = Path("./temp_downloads")
    state_db_path: Path = Path("./aniz_state.sqlite3")
    aria2_rpc_url: str = "http://127.0.0.1:6800/rpc"
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

    @property
    def feed_urls(self) -> list[str]: return self.nyaa_feed_urls.split(",")
    @property
    def groups(self) -> list[str]: return self.nyaa_groups.split(",")
    @property
    def qualities(self) -> list[str]: return self.nyaa_qualities.split(",")


class Pipeline:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = StateStore(settings.state_db_path)
        self.scraper = NyaaScraper(settings.feed_urls, settings.groups, settings.qualities)
        self.downloader = Aria2Downloader(settings.aria2_rpc_url, settings.aria2_secret, settings.temp_download_dir, settings.aria2_download_timeout)
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
                    await asyncio.gather(*(self.process(r) for r in releases))
                    try:
                        await asyncio.wait_for(self.stop_event.wait(), timeout=self.settings.nyaa_check_interval)
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
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
