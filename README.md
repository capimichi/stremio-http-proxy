# stremio-http-proxy

HTTP proxy for Stremio addons that rewrites upstream torrent streams to TorrServer URLs.

## Features

- FastAPI addon proxy for `manifest`, `catalog`, `meta`, `stream`, and `subtitles`
- TorrServer-backed stream registration and preload
- Stream URL rewrite to TorrServer HTTP playback

## Development

Install dependencies:

```bash
pip install -e .[dev]
```

Run the API:

```bash
python -m stremio_http_proxy.cli serve
```

Environment:

```bash
UPSTREAM_BASE_URL=https://example.com
TORRSERVER_BASE_URL=http://localhost:8090
```
