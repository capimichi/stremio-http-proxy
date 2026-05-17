# stremio-http-proxy

HTTP proxy for Stremio addons that rewrites upstream stream URLs into local HLS playlists.

## Features

- FastAPI addon proxy for `manifest`, `catalog`, `meta`, `stream`, and `subtitles`
- Local `playlist.m3u8` endpoint for rewritten streams
- Local `.ts` segment endpoint backed by disk cache
- CLI commands for serving, registering magnets, monitoring torrents, and cleaning cache

## Development

Install dependencies:

```bash
pip install -e .[dev]
```

Run the API:

```bash
python -m stremio_http_proxy.cli serve
```

Register a torrent:

```bash
python -m stremio_http_proxy.cli add-torrent --magnet "magnet:?xt=urn:btih:..." --segment 0001 --segment 0002
```

Monitor torrents:

```bash
python -m stremio_http_proxy.cli monitor-torrents
```

Cleanup cache:

```bash
python -m stremio_http_proxy.cli cleanup-cache --older-than-days 7 --max-size-gb 50
```
