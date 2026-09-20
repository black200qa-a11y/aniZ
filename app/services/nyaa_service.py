from __future__ import annotations

import re
from urllib.parse import quote, urljoin

import aiohttp
from bs4 import BeautifulSoup

NYAA_BASE = "https://nyaa.si"


def smart_tags(title: str) -> list[str]:
    lower = title.lower()
    tags: list[str] = []
    if re.search(r"batch|pack|\b\d{1,3}\s*[-~]\s*\d{1,3}\b", lower):
        tags.append("pack")
    if re.search(r"arabic|عربي|عربية|\bara\b", lower):
        tags.append("ara")
    if re.search(r"subsplease|\beng\b|english", lower):
        tags.append("eng")
    if ".mp4" in lower or re.search(r"\bmp4\b", lower):
        tags.append("mp4")
    if ".mkv" in lower or re.search(r"\bmkv\b", lower):
        tags.append("mkv")
    return tags


class NyaaSearchService:
    def __init__(self, timeout: int = 30):
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    async def search(self, query: str, limit: int = 500) -> list[dict]:
        if not query.strip():
            return []
        results: list[dict] = []
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            for page in range(1, 8):
                url = f"{NYAA_BASE}/?f=0&c=0_0&q={quote(query)}&p={page}"
                async with session.get(url) as response:
                    response.raise_for_status()
                    html = await response.text(errors="replace")
                page_results = self._parse_results(html)
                results.extend(page_results)
                if len(results) >= limit or len(page_results) == 0:
                    break
        deduped = {item["nyaa_id"]: item for item in results}
        return sorted(deduped.values(), key=lambda item: ("ara" not in item["tags"], item["title"].lower()))[:limit]

    def _parse_results(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []
        for row in soup.select("tr.default, tr.success, tr.danger"):
            link = row.select_one('a[href^="/view/"]')
            magnet = row.select_one('a[href^="magnet:"]')
            if not link or not magnet:
                continue
            nyaa_id = link["href"].rsplit("/", 1)[-1]
            title = link.get("title") or link.get_text(" ", strip=True)
            cells = row.find_all("td")
            results.append({
                "nyaa_id": nyaa_id,
                "title": title,
                "page_url": urljoin(NYAA_BASE, link["href"]),
                "magnet": magnet["href"],
                "size": cells[3].get_text(" ", strip=True) if len(cells) > 3 else "",
                "seeders": cells[-2].get_text(" ", strip=True) if len(cells) > 1 else "",
                "tags": smart_tags(title),
            })
        return results

    async def inspect(self, view: str) -> list[dict[str, str]]:
        if not re.fullmatch(r"\d+", view):
            raise ValueError("view must be a numeric Nyaa torrent id")
        async with aiohttp.ClientSession(timeout=self.timeout) as session, session.get(f"{NYAA_BASE}/view/{view}") as response:
            response.raise_for_status()
            html = await response.text(errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("#torrent-filelist tr, table.torrent-file-list tr, .torrent-file-list tr")
        files: list[dict[str, str]] = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 2:
                name = cells[0].get_text(" ", strip=True)
                size = cells[-1].get_text(" ", strip=True)
                if name and name.lower() not in {"name", "filename"}:
                    files.append({"name": name, "size": size})
        return files
