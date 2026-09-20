from __future__ import annotations

import asyncio
import html
import logging
import re
from collections.abc import Iterable

import aiohttp
import feedparser

from .models import Release, infer_release

log = logging.getLogger(__name__)


class NyaaScraper:
    def __init__(self, feed_urls: Iterable[str], groups: Iterable[str], qualities: Iterable[str], timeout: int = 30):
        self.feed_urls = tuple(x.strip() for x in feed_urls if x.strip())
        self.groups = tuple(x.lower().strip() for x in groups if x.strip())
        self.qualities = tuple(x.lower().strip() for x in qualities if x.strip())
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    def _matches(self, title: str) -> bool:
        lower = title.lower()
        return (not self.groups or any(group in lower for group in self.groups)) and (not self.qualities or any(q in lower for q in self.qualities))

    async def poll(self, session: aiohttp.ClientSession) -> list[Release]:
        releases: list[Release] = []
        for url in self.feed_urls:
            try:
                async with session.get(url, timeout=self.timeout) as response:
                    response.raise_for_status()
                    parsed = await asyncio.to_thread(feedparser.parse, await response.read())
                for entry in parsed.entries:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "")
                    magnet = entry.get("magnet") or entry.get("magnet_uri")
                    if not magnet:
                        description = entry.get("description", "")
                        start = description.find("magnet:")
                        if start >= 0:
                            magnet = description[start:].split('"', 1)[0].split("<", 1)[0].strip()
                    if title and magnet and self._matches(title):
                        releases.append(infer_release(title, magnet, link))
            except (TimeoutError, aiohttp.ClientError) as exc:
                log.warning("Could not poll RSS feed %s: %s", url, exc)
        return releases

    async def resolve_source(self, session: aiohttp.ClientSession, source: str) -> Release:
        if source.startswith("magnet:"):
            return infer_release("Manual upload", source, source)
        async with session.get(source, timeout=self.timeout) as response:
            response.raise_for_status()
            body = html.unescape(await response.text(errors="replace"))
        match = re.search(r"magnet:\?[^\"'<>\s]+", body)
        if not match:
            raise ValueError("No magnet link found at source URL")
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else "Manual upload"
        return infer_release(title, match.group(0), source)
