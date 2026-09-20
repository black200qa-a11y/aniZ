# Aniz Async Media Pipeline, Catalog, and Streaming API

Aniz contains an RSS release worker, aria2 downloads, Telegram uploads, MongoDB catalog synchronization, and a FastAPI Telegram-backed range-streaming proxy. Use it only for content you are authorized to download, store, and redistribute.

## Configuration

```bash
cp .env.example .env
# Edit .env and replace every replace-me value.
```

The repository includes a local `.env` template for convenience, but it is ignored by Git and contains no real credentials. Never commit a real `.env`, Telegram API hash, or Pyrogram string session.

The requested variables are supported directly: `ARIA2_HOST`, `ARIA2_PORT`, `ARIA2_SECRET`, `API_PORT`, `STREAM_CHUNK_SIZE`, `MAX_CONCURRENT_STREAMS`, `NYAA_CHECK_INTERVAL_MINUTES`, `QUALITY_FILTERS`, and `RELEASE_GROUPS`. JSON array values must use valid JSON, for example `["1080p", "720p"]`.

## Pre-flight diagnostics

Run this before starting the worker or API:

```bash
python scripts/check_env.py
```

The script validates required values without printing secrets, then checks MongoDB, aria2 JSON-RPC, and Telegram MTProto authentication. It prints `[SUCCESS]` or `[FAILED]` per subsystem and exits non-zero if any check fails. A placeholder `.env` is expected to fail until you add real credentials and start the services.

## Docker Compose deployment

The Compose file runs MongoDB, aria2, the FastAPI API, and the Aniz worker:

```bash
cp .env.example .env
# Set real credentials and a strong ARIA2_SECRET.
docker compose up -d --build mongodb aria2
python scripts/check_env.py   # use host values if running the checker on the host

docker compose up -d --build api worker
docker compose ps
curl http://localhost:8000/api/v1/health
```

Inside Compose, `.env` should use `MONGODB_URI=mongodb://mongodb:27017` and `ARIA2_HOST=aria2`. The aria2 RPC port is bound to localhost only; the API port is configurable through `API_PORT`. Persistent Docker volumes retain MongoDB and aria2 state, while `./temp_downloads` stores only in-progress worker downloads.

For a host-native deployment, use `MONGODB_URI=mongodb://127.0.0.1:27017` and `ARIA2_HOST=127.0.0.1`, then run:

```bash
aniz-pipeline
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Run the worker and API as separate supervised services in production. The default sandbox is not a 24/7 host.

## API endpoints

- `GET /api/v1/health` — MongoDB, Telegram, and storage health.
- `GET /api/v1/animes?page=1&page_size=20` — recent anime catalog.
- `GET /api/v1/animes/{anime_id}/episodes` — episodes with stream URLs.
- `GET /api/v1/stream/{episode_id}` — Telegram-backed video stream with single-range HTTP support, `206 Partial Content`, `Content-Range`, `Accept-Ranges`, and seeking.

## Resilience and logging

Worker and API logs are emitted as one JSON object per line with timestamp, level, logger, message, and exception details. aria2 retries broken downloads and the worker records failures in SQLite. Pyrogram upload FloodWait errors are delayed and retried. The API restarts a dropped Pyrogram connection, bounds concurrent streams, and MongoDB startup uses bounded retry attempts; the Mongo client itself also reconnects through Motor's connection pool.

## Tests and development

```bash
pip install -e '.[dev]'
ruff check src app scripts tests
python -m compileall -q src app scripts
pytest -q
```
