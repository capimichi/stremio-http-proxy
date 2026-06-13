from urllib.parse import urlencode, urlparse

from injector import inject

from stremio_http_proxy.helper.hash_helper import extract_infohash, normalize_infohash
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.repository.whitelist_repository import WhitelistRepository
from stremio_http_proxy.service.torrent_health_service import TorrentHealthService


class StreamRewriteService:
    CACHED_NAME_PREFIX = "🔥 "
    HEALTHY_NAME_PREFIX = "✅ "

    @inject
    def __init__(
        self,
        public_base_url: str,
        cache_manager: CacheManager,
        cache_enabled: bool = True,
        torrent_health_service: TorrentHealthService | None = None,
        torrserver_health_check_enabled: bool = False,
        torrserver_health_check_timeout: int = 15,
        whitelist_repository: WhitelistRepository | None = None,
    ):
        self.public_base_url = public_base_url.rstrip("/")
        self.cache_manager = cache_manager
        self.cache_enabled = cache_enabled
        self.torrent_health_service = torrent_health_service
        self.torrserver_health_check_enabled = torrserver_health_check_enabled
        self.torrserver_health_check_timeout = torrserver_health_check_timeout
        self.whitelist_repository = whitelist_repository

    async def rewrite(
        self,
        payload: dict,
        category: str | None = None,
        content_type: str | None = None,
        content_id: str | None = None,
    ) -> dict:
        streams = payload.get("streams")
        if not isinstance(streams, list):
            return payload

        rewritten_streams = []
        link_to_entries: dict[str, list[dict]] = {}

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
            index = self._extract_index(updated)
            self._mark_cached_if_ready(updated, torrent_link, index)
            updated["url"] = self._build_playback_url(
                torrent_link,
                title,
                poster,
                category,
                index,
                content_type,
                content_id,
            )
            rewritten_streams.append(updated)
            link_to_entries.setdefault(torrent_link, []).append(updated)

        if self.torrserver_health_check_enabled and self.torrent_health_service:
            non_cached_links = [
                link
                for link, entries in link_to_entries.items()
                if not any(
                    isinstance(e.get("_meta"), dict) and e["_meta"].get("cached")
                    for e in entries
                )
            ]
            if non_cached_links:
                health_map = await self.torrent_health_service.check_batch(
                    non_cached_links[:10],
                    timeout=self.torrserver_health_check_timeout,
                )
                for link, (playable, seeders) in health_map.items():
                    for entry in link_to_entries.get(link, []):
                        if playable:
                            self._mark_healthy(entry)
                        if seeders is not None:
                            meta = entry.get("_meta")
                            if not isinstance(meta, dict):
                                meta = {}
                            updated_meta = dict(meta)
                            updated_meta["seeders"] = seeders
                            entry["_meta"] = updated_meta

        if self.whitelist_repository is not None:
            imdb_id, season, episode = self._parse_content_id(content_id)
            if imdb_id:
                allowed = self.whitelist_repository.get_allowed_infohashes(imdb_id, season, episode)
                if allowed:
                    rewritten_streams = [
                        s for s in rewritten_streams
                        if self._extract_infohash_from_stream(s) in allowed
                    ]

        updated_payload = dict(payload)
        updated_payload["streams"] = rewritten_streams
        return updated_payload

    def _extract_infohash_from_stream(self, stream: dict) -> str | None:
        link = self._extract_torrent_link(stream)
        if link is None:
            return None
        infohash = extract_infohash(link)
        if infohash:
            return normalize_infohash(infohash)
        return None

    def _parse_content_id(self, content_id: str | None) -> tuple[str | None, int | None, int | None]:
        if not content_id:
            return None, None, None
        parts = content_id.split(":")
        imdb_id = parts[0]
        if not imdb_id.startswith("tt"):
            return None, None, None
        season = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        episode = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        return imdb_id, season, episode

    def _mark_healthy(self, stream: dict) -> None:
        name = stream.get("name")
        if not isinstance(name, str) or not name.strip():
            stream["name"] = self.HEALTHY_NAME_PREFIX.strip()
            return
        if name.startswith(self.CACHED_NAME_PREFIX):
            rest = name[len(self.CACHED_NAME_PREFIX) :]
            stream["name"] = f"{self.CACHED_NAME_PREFIX}{self.HEALTHY_NAME_PREFIX}{rest}"
        elif not name.startswith(self.HEALTHY_NAME_PREFIX):
            stream["name"] = f"{self.HEALTHY_NAME_PREFIX}{name}"

    def _mark_cached_if_ready(self, stream: dict, torrent_link: str, index: int | None) -> None:
        if not self.cache_enabled:
            return
        cache_key = self.cache_manager.build_cache_key(torrent_link, index)
        if cache_key is None or not self.cache_manager.is_ready(cache_key):
            return

        meta = stream.get("_meta")
        if not isinstance(meta, dict):
            meta = {}
        updated_meta = dict(meta)
        updated_meta["cached"] = True
        stream["_meta"] = updated_meta

        name = stream.get("name")
        if isinstance(name, str) and name.strip() and not name.startswith(self.CACHED_NAME_PREFIX):
            stream["name"] = f"{self.CACHED_NAME_PREFIX}{name}"

    def extract_download_candidates(self, payload: dict) -> list[dict[str, str | int | None]]:
        streams = payload.get("streams")
        if not isinstance(streams, list):
            return []

        candidates = []
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            torrent_link = self._extract_torrent_link(stream)
            if torrent_link is None:
                continue
            candidates.append(
                {
                    "link": torrent_link,
                    "title": self._extract_title(stream),
                    "poster": self._extract_poster(stream),
                    "index": self._extract_index(stream),
                }
            )
        return candidates

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
        parts = []
        for key in ("title", "name", "description"):
            value = stream.get(key)
            if isinstance(value, str) and value.strip():
                clean_value = value.strip().replace("\r\n", " ").replace("\n", " ")
                if clean_value:
                    parts.append(clean_value)
        if not parts:
            return None
        joined = " - ".join(parts)
        if len(joined) > 255:
            return joined[:252] + "..."
        return joined

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

    def _extract_index(self, stream: dict) -> int | None:
        value = stream.get("fileIdx")
        if value is None:
            value = stream.get("fileIndex")
        if not isinstance(value, int):
            return None
        return value + 1

    def _build_playback_url(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
        content_type: str | None,
        content_id: str | None,
    ) -> str:
        params = {"link": link}
        if title:
            params["title"] = title
        if poster:
            params["poster"] = poster
        if category:
            params["category"] = category
        if index is not None:
            params["index"] = str(index)
        if content_type:
            params["content_type"] = content_type
        if content_id:
            params["content_id"] = content_id
        return f"{self.public_base_url}/play?{urlencode(params)}"
