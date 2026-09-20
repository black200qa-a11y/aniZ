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

## Control architecture

### Persistent logs and FFmpeg inspection

The worker configures Loguru at startup. It writes detailed download/sync/upload events to `logs/pipeline.log`, rotates at midnight, retains 14 days, and writes warning/error/critical records with source line numbers and stack traces to `logs/errors.log` with 30-day retention. `logs/` is ignored by Git.

After aria2 finishes, the worker recursively selects the largest `.mkv` or `.mp4` file. Set `CONVERT_MKV_TO_MP4=true` to convert MKV to MP4 with FFmpeg stream copy (`-c copy`); no video re-encoding is performed. FFmpeg must be installed on the host or included in the container image.

### Web admin dashboard

Start the API and visit `http://localhost:8000/admin`. Login uses `ADMIN_PASSWORD` with a signed session cookie backed by `ADMIN_SESSION_SECRET`.

The dashboard provides CPU/RAM/disk and MongoDB counts, recent episode search, manual source queueing, catalog deletion, episode resync timestamps, and a live log viewer that refreshes the last 200 lines of both log files. Manual jobs are stored in MongoDB and consumed by the worker, so the API and worker can run as separate processes.

### Telegram admin bot

Create a bot token with BotFather and configure:

```env
BOT_TOKEN=...
ADMIN_USER_IDS=123456789,987654321
```

Only those numeric Telegram user IDs can use the private bot panel. Start the API process with the bot token configured; the bot registers inline-keyboard actions for system status, recent uploads with stream URLs, manual source queueing, error logs, and safe restart guidance. The restart action does not kill the process from inside Telegram; use Docker Compose/systemd restart policy to avoid corrupting downloads or sessions.

## Start everything together

```bash
cp .env.example .env
# Fill API_ID, API_HASH, STRING_SESSION, TG_CHANNEL_ID, BOT_TOKEN,
# ADMIN_PASSWORD, ADMIN_SESSION_SECRET, ADMIN_USER_IDS, and ARIA2_SECRET.
docker compose up -d --build mongodb aria2 api worker
curl http://localhost:8000/api/v1/health
# Open http://localhost:8000/admin and message /start to the admin bot.
```

Run checks before deployment:

```bash
python scripts/check_env.py
ruff check src app scripts tests
python -m compileall -q src app scripts
pytest -q
```
