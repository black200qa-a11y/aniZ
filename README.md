# Aniz Async Media Pipeline

A Python 3.11+ service that polls configured RSS feeds, filters releases, downloads new magnets through a local aria2 daemon, uploads completed media to a Telegram channel using a Pyrogram user session, emits one JSON record per completed episode, and removes local media after successful upload.

Use this only for content you are authorized to download and redistribute. Nyaa feed formats can change, so the parser is intentionally conservative and should be tested against the feeds used by your deployment.

## Features

- Async polling with `aiohttp` and `feedparser`.
- Durable SQLite state store with an atomic claim to prevent duplicate processing across restarts.
- aria2 retry settings and asynchronous completion polling.
- Pyrogram MTProto upload with reconnect/retry and flood-wait handling.
- Upload-success cleanup, with optional cleanup after failed uploads.
- JSON output compatible with a later MongoDB callback or ingestion layer.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

Install and start aria2c on the host:

```bash
sudo apt-get install aria2
aria2c --enable-rpc=true --rpc-listen-all=false --rpc-listen-port=6800 --dir="$PWD/temp_downloads"
```

Create a Telegram application at [my.telegram.org](https://my.telegram.org), then generate a Pyrogram user `STRING_SESSION` using a trusted, local session-generation script. Do not commit `.env` or share the session string: it grants access to the Telegram account.

Set `NYAA_FEED_URLS`, optional group/quality filters, the channel ID, and Telegram credentials in `.env`. `TG_CHANNEL_ID` can be a private channel ID such as `-1001234567890`; the authenticated user must be an administrator able to post there.

## Run

Process the current feed once:

```bash
aniz-pipeline --once
```

Run continuously until SIGINT/SIGTERM:

```bash
aniz-pipeline
```

Each successful item is printed as one JSON object, for example:

```json
{"anime_title":"Anime Name","episode_number":1090,"quality":"1080p","format":"mkv","telegram_file_id":"...","telegram_message_id":1234,"file_size_bytes":450000000,"video_duration":1440,"status":"COMPLETED","magnet_hash":"...","error":null}
```

## Production notes

Run the process under a supervisor such as systemd, Docker, or a process manager on a persistent host. The default sandbox is not suitable for an always-on deployment. Keep aria2 bound to localhost or protected by a firewall and RPC secret. Use a dedicated Telegram account and private channel, and rotate credentials if `.env` or the session string is exposed.

The current implementation stores processing status and errors in SQLite. MongoDB can be added later by consuming `PipelineResult.as_dict()` or by inserting that dictionary immediately after the successful upload and before local cleanup. A failed item is retained as `FAILED` in the state database and is not retried automatically; this avoids repeated upload attempts and makes retry policy explicit. To reprocess a failed hash, update or delete that row after investigating the failure.

## Tests

```bash
pytest -q
python -m compileall -q src
```
