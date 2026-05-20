# stremio-http-proxy

HTTP proxy for Stremio addons that rewrites upstream torrent streams to TorrServer URLs.

## Features

- FastAPI addon proxy for `manifest`, `catalog`, `meta`, `stream`, and `subtitles`
- TorrServer-backed stream registration and preload
- Stream URL rewrite to TorrServer HTTP playback
- Deferred local cache downloads backed by SQLite state and a worker process
- Local `/cache` endpoint for already downloaded media files

## Development

Install dependencies:

```bash
pip install -e .[dev]
```

Run the API:

```bash
python -m stremio_http_proxy.cli serve
```

Run with Docker:

```bash
docker compose up --build
```

Environment:

```bash
UPSTREAM_BASE_URL=https://example.com
PUBLIC_BASE_URL=http://localhost:8691
TORRSERVER_BASE_URL=http://localhost:8090
TORRSERVER_BASIC_AUTH_USER=
TORRSERVER_BASIC_AUTH_PASSWORD=
LOG_DIR=var/log
LOCAL_CACHE_DIR=var/cache
SQLITE_PATH=var/db/cache.sqlite
LOCAL_CACHE_MAX_AGE_DAYS=7
LOCAL_CACHE_MAX_SIZE_GB=20
DOWNLOAD_QUEUE_POLL_SECONDS=1
DOWNLOAD_MAX_ATTEMPTS=3
DOWNLOAD_CONNECT_TIMEOUT_SECONDS=10
DOWNLOAD_NO_PROGRESS_TIMEOUT_SECONDS=30
DOWNLOAD_MIN_PROGRESS_BYTES=33554432
DOWNLOAD_MIN_PROGRESS_WINDOW_SECONDS=120
DOWNLOAD_MAX_TOTAL_SECONDS=2700
DOWNLOAD_PROGRESS_LOG_INTERVAL_SECONDS=10
NEXT_EPISODE_PREFETCH_STREAM_LIMIT=3
```

To scale download workers manually:

```bash
docker compose up --build -d --scale stremio-http-proxy-worker=2
```

If TorrServer runs outside Docker, set `TORRSERVER_BASE_URL` to a hostname or IP reachable from the container.
