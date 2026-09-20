from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from urllib.parse import urlsplit

import aria2p

log = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    pass


class Aria2Downloader:
    def __init__(self, rpc_url: str, secret: str, output_dir: Path, timeout: int = 7200):
        parsed = urlsplit(rpc_url if "://" in rpc_url else f"http://{rpc_url}")
        host = f"{parsed.scheme}://{parsed.hostname or '127.0.0.1'}"
        port = parsed.port or 6800
        self.api = aria2p.API(aria2p.Client(host=host, port=port, secret=secret))
        self.output_dir = output_dir
        self.timeout = timeout

    async def download(self, magnet_uri: str, magnet_hash: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            download = await asyncio.to_thread(self.api.add_magnet, magnet_uri, options={"dir": str(self.output_dir), "seed-time": "0", "max-tries": "5", "retry-wait": "10"})
            elapsed = 0
            while elapsed < self.timeout:
                download = await asyncio.to_thread(self.api.get_download, download.gid)
                if download.is_complete:
                    files = [Path(f.path) for f in download.files if Path(f.path).is_file() and Path(f.path).suffix.lower() in {".mkv", ".mp4", ".webm"}]
                    if not files:
                        raise DownloadError(f"aria2 completed but no media file was found for {magnet_hash}")
                    return max(files, key=lambda p: p.stat().st_size)
                if download.error_message:
                    raise DownloadError(download.error_message)
                if elapsed and elapsed % 60 == 0:
                    log.info("Download %s: %s", magnet_hash, download.progress_string())
                await asyncio.sleep(5)
                elapsed += 5
            raise DownloadError(f"download timed out after {self.timeout}s")
        except Exception as exc:
            if isinstance(exc, DownloadError):
                raise
            raise DownloadError(str(exc)) from exc
