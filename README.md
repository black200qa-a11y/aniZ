# Aniz Async Media Pipeline, Catalog, and Streaming API

Aniz now includes four cooperating phases: an RSS release worker, aria2 downloads, Telegram uploads, and a MongoDB/FastAPI catalog with Telegram-backed HTTP video streaming.

Use this only for content you are authorized to download, store, and redistribute.

## Components

- `src/aniz_pipeline/`: Phase 1 and 2 worker. Polls RSS feeds, deduplicates magnets in SQLite, downloads through aria2, uploads with Pyrogram, cleans local media, and—when `MONGODB_SYNC_ENABLED=true`—upserts anime and episode records into MongoDB.
- `app/core/`: FastAPI settings, MongoDB lifecycle, and one cached Pyrogram client.
- `app/services/sync_service.py`: idempotent anime/episode upserts and unique-key handling.
- `app/services/stream_service.py`: bounded concurrent Telegram streaming.
- `app/api/`: catalog routes and full single-range HTTP streaming route.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Install and start aria2:

```bash
sudo apt-get install aria2 mongodb
aria2c --enable-rpc=true --rpc-listen-all=false --rpc-listen-port=6800 --dir="$PWD/temp_downloads"
# Start MongoDB using your OS/service-manager configuration.
```

Create a Telegram application at [my.telegram.org](https://my.telegram.org), generate a Pyrogram user session, and set `API_ID`, `API_HASH`, `STRING_SESSION`, and `TG_CHANNEL_ID`. Never commit `.env` or share the session string.

Set `MONGODB_URI`, `DATABASE_NAME`, and `MONGODB_SYNC_ENABLED=true`. The worker creates indexes on startup. MongoDB uniqueness is enforced by `(anime_id, episode_number, quality)` for episodes and `anime_id` for anime records.

## Run both processes

Terminal 1, the downloader/uploader worker:

```bash
aniz-pipeline
# or one polling cycle:
aniz-pipeline --once
```

Terminal 2, the API server:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

For production, run them under separate systemd/Docker/process-manager services on a persistent host. The default sandbox is not suitable for 24/7 hosting.

## API

- `GET /api/v1/health` — MongoDB, Telegram, and storage health.
- `GET /api/v1/animes?page=1&page_size=20` — recent anime catalog.
- `GET /api/v1/animes/{anime_id}/episodes` — episode list with stream URLs.
- `GET /api/v1/stream/{episode_id}` — Telegram-backed video stream. Supports `Range: bytes=start-end`, suffix ranges, `206 Partial Content`, `Content-Range`, `Accept-Ranges`, and seeking-compatible `Content-Length`.

The stream endpoint intentionally uses the stored `telegram_channel_id`, `telegram_message_id`, and `file_size`; it does not expose Telegram credentials or direct Telegram URLs. Concurrent streams are bounded by `STREAM_MAX_CONCURRENT`, and `STREAM_CHUNK_SIZE` controls the Pyrogram request chunk size.

## JSON/MongoDB flow

After a successful upload, the worker upserts the anime and episode before deleting the local file. An episode stores the Telegram identifiers, file size, duration, format, quality, and stable `stream_slug`. A MongoDB insert/update failure marks the processing attempt as failed and preserves the downloaded file unless the configured cleanup policy removes it.

## Tests

```bash
ruff check src app tests
python -m compileall -q src app
pytest -q
```
