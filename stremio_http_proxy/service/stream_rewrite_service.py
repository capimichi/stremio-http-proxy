import logging
from urllib.parse import urlparse

from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.helper.hash_helper import extract_infohash


class StreamRewriteService:
    @inject
    def __init__(self, torrserver_client: TorrServerClient):
        self.logger = logging.getLogger(__name__)
        self.torrserver_client = torrserver_client

    async def rewrite(self, payload: dict, category: str | None = None) -> dict:
        streams = payload.get("streams")
        if not isinstance(streams, list):
            return payload

        rewritten_streams = []
        for stream in streams:
            if not isinstance(stream, dict):
                rewritten_streams.append(stream)
                continue
            torrent_link = self._extract_torrent_link(stream)
            if torrent_link is None:
                rewritten_streams.append(stream)
                continue
            updated = dict(stream)
            title = self._extract_title(updated)
            poster = self._extract_poster(updated)
            try:
                await self.torrserver_client.add_torrent(torrent_link, title, poster, category)
                await self.torrserver_client.preload(torrent_link, title, poster, category)
                updated["url"] = self.torrserver_client.build_play_url(
                    torrent_link,
                    title,
                    poster,
                    category,
                )
            except Exception:
                self.logger.exception("Unable to register stream in TorrServer")
            rewritten_streams.append(updated)

        updated_payload = dict(payload)
        updated_payload["streams"] = rewritten_streams
        return updated_payload

    def _extract_torrent_link(self, stream: dict) -> str | None:
        candidates = [
            stream.get("magnetUrl"),
            stream.get("magnet"),
            stream.get("infoHash"),
            stream.get("externalUrl"),
            stream.get("url"),
        ]
        behavior_hints = stream.get("behaviorHints")
        if isinstance(behavior_hints, dict):
            candidates.append(behavior_hints.get("magnet"))
            proxy_headers = behavior_hints.get("proxyHeaders")
            if isinstance(proxy_headers, dict):
                request_headers = proxy_headers.get("request")
                if isinstance(request_headers, dict):
                    candidates.append(request_headers.get("x-infohash"))

        for candidate in candidates:
            if isinstance(candidate, str):
                candidate = candidate.strip()
                if candidate.startswith("magnet:"):
                    return candidate
                if self._is_torrent_url(candidate):
                    return candidate
            infohash = extract_infohash(candidate)
            if infohash:
                return infohash
        return None

    def _is_torrent_url(self, value: str) -> bool:
        if not value.startswith(("http://", "https://")):
            return False
        return urlparse(value).path.endswith(".torrent")

    def _extract_title(self, stream: dict) -> str | None:
        for key in ("title", "name", "description"):
            value = stream.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_poster(self, stream: dict) -> str | None:
        for key in ("poster", "thumbnail"):
            value = stream.get(key)
            if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
                return value.strip()
        behavior_hints = stream.get("behaviorHints")
        if isinstance(behavior_hints, dict):
            value = behavior_hints.get("poster")
            if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
                return value.strip()
        return None
