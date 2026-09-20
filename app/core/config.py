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
    max_concurrent_streams: int = 8
    stream_chunk_size: int = 1024 * 1024
    log_level: str = "INFO"
    log_dir: Path = Path("./logs")
    admin_password: str = ""
    admin_session_secret: str = "change-me"
    admin_user_ids: str = ""
    bot_token: str = ""
    convert_mkv_to_mp4: bool = False
    aria2_host: str = "127.0.0.1"
    aria2_port: int = 6800
    aria2_secret: str = ""

    @property
    def temp_download_dir(self) -> Path: return Path("./temp_downloads")

    @property
    def effective_max_concurrent_streams(self) -> int:
        return self.max_concurrent_streams if self.max_concurrent_streams != 8 else self.stream_max_concurrent


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
