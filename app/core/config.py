from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    api_id: int
    api_hash: str
    string_session: str
    tg_channel_id: int
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    database_name: str = "aniz"
    mongodb_server_selection_timeout_ms: int = 3000
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_public_base_url: str = "http://127.0.0.1:8000"
    stream_max_concurrent: int = 8
    stream_chunk_size: int = 1024 * 1024
    log_level: str = "INFO"

    @property
    def temp_download_dir(self) -> Path: return Path("./temp_downloads")


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
