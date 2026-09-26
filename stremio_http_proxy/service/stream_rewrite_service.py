from urllib.parse import urlencode, urlparse
import os
import re

from injector import inject

from stremio_http_proxy.client.mediaflow_client import MediaflowClient
from stremio_http_proxy.helper.format_helper import format_bytes
from stremio_http_proxy.helper.hash_helper import extract_infohash, normalize_infohash
from stremio_http_proxy.manager.cache_manager import CacheManager
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
        mediaflow_client: MediaflowClient | None = None,
        http_streams_proxy_enabled: bool = True,
    ):
        self.public_base_url = public_base_url.rstrip("/")
        self.cache_manager = cache_manager
        self.cache_enabled = cache_enabled
        self.torrent_health_service = torrent_health_service
        self.torrserver_health_check_enabled = torrserver_health_check_enabled
        self.torrserver_health_check_timeout = torrserver_health_check_timeout
        self.mediaflow_client = mediaflow_client
        self.http_streams_proxy_enabled = http_streams_proxy_enabled

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
        seen_cached_keys: set[tuple[str, int | None]] = set()

        for stream in streams:
            if not isinstance(stream, dict):
                rewritten_streams.append(stream)
                continue
            torrent_link = self._extract_torrent_link(stream)
            if torrent_link is None:
                if not self.http_streams_proxy_enabled:
                    updated = dict(stream)
                    raw_url = updated.get("url")
                    if isinstance(raw_url, str) and raw_url.startswith(("http://", "https://")):
                        title = self._extract_title(updated)
                        poster = self._extract_poster(updated)
                        index = self._extract_index(updated)
                        updated["url"] = self._build_playback_url(
                            raw_url,
                            title,
                            poster,
                            category,
                            index,
                            content_type,
                            content_id,
                            is_cached=False,
                            force_play_route=True,
                        )
                    rewritten_streams.append(updated)
                    continue

                updated = dict(stream)
                raw_url = updated.get("url")
                if isinstance(raw_url, str) and raw_url.startswith(("http://", "https://")):
                    is_mediaflow = False
                    if self.mediaflow_client and self.mediaflow_client.is_available():
                        if self.mediaflow_client.is_mediaflow_url(raw_url):
                            hint = None
                            bh = updated.get("behaviorHints")
                            if isinstance(bh, dict) and bh.get("filename"):
                                hint = bh.get("filename")
                            elif updated.get("description") and ".m3u8" in updated.get("description"):
                                hint = ".m3u8"
                            updated["url"] = self.mediaflow_client.fix_mediaflow_url(raw_url, destination_hint=hint)
                            is_mediaflow = True
                        elif self._needs_mediaflow_proxy(updated):
                            proxy_headers = self._extract_proxy_headers(updated)
                            filename = self._extract_filename(updated)
                            updated["url"] = await self.mediaflow_client.generate_proxy_url(
                                destination_url=raw_url,
                                request_headers=proxy_headers,
                                filename=filename,
                            )
                            if "behaviorHints" in updated and isinstance(updated["behaviorHints"], dict):
                                updated_bh = dict(updated["behaviorHints"])
                                updated_bh.pop("proxyHeaders", None)
                                updated["behaviorHints"] = updated_bh
                            is_mediaflow = True

                    if is_mediaflow:
                        if "behaviorHints" in updated and isinstance(updated["behaviorHints"], dict):
                            updated_bh = dict(updated["behaviorHints"])
                            updated_bh.pop("notWebReady", None)
                            updated["behaviorHints"] = updated_bh

                        http_link = updated["url"]
                        title = self._extract_title(updated)
                        poster = self._extract_poster(updated)
                        index = self._extract_index(updated)
                        self._mark_cached_if_ready(updated, http_link, index, content_id)
                        is_cached = bool(isinstance(updated.get("_meta"), dict) and updated["_meta"].get("cached"))
                        effective_http_index = (
                            updated["_meta"].get("cache_index")
                            if isinstance(updated.get("_meta"), dict) and updated["_meta"].get("cache_index") is not None
                            else index
                        )
                        updated["url"] = self._build_playback_url(
                            http_link,
                            title,
                            poster,
                            category,
                            effective_http_index,
                            content_type,
                            content_id,
                            is_cached=is_cached,
                        )

                if isinstance(updated.get("_meta"), dict):
                    m_hash = updated["_meta"].get("infohash")
                    m_idx = updated["_meta"].get("cache_index")
                    if m_hash:
                        seen_cached_keys.add((normalize_infohash(m_hash), m_idx))

                rewritten_streams.append(updated)
                continue
            updated = dict(stream)
            title = self._extract_title(updated)
            poster = self._extract_poster(updated)
            index = self._extract_index(updated)
            self._mark_cached_if_ready(updated, torrent_link, index, content_id)
            is_cached = bool(isinstance(updated.get("_meta"), dict) and updated["_meta"].get("cached"))
            effective_index = (
                updated["_meta"].get("cache_index")
                if isinstance(updated.get("_meta"), dict) and updated["_meta"].get("cache_index") is not None
                else index
            )
            raw_infohash = extract_infohash(torrent_link)
            if raw_infohash:
                norm_hash = normalize_infohash(raw_infohash)
                seen_cached_keys.add((norm_hash, index))
                seen_cached_keys.add((norm_hash, effective_index))
                raw_idx = updated.get("fileIdx") if updated.get("fileIdx") is not None else updated.get("fileIndex")
                if isinstance(raw_idx, int):
                    seen_cached_keys.add((norm_hash, raw_idx))
            if isinstance(updated.get("_meta"), dict):
                m_hash = updated["_meta"].get("infohash")
                m_idx = updated["_meta"].get("cache_index")
                if m_hash:
                    seen_cached_keys.add((normalize_infohash(m_hash), m_idx))

            updated["url"] = self._build_playback_url(
                torrent_link,
                title,
                poster,
                category,
                effective_index,
                content_type,
                content_id,
                is_cached=is_cached,
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

        # Inject missing ready cached streams for this content_id
        if self.cache_enabled and content_id and hasattr(self.cache_manager, "get_ready_entries_by_content"):
            ready_entries = self.cache_manager.get_ready_entries_by_content(content_id)
            for entry in ready_entries:
                entry_hash = normalize_infohash(entry.infohash) if entry.infohash else ""
                if (entry_hash, entry.cache_index) in seen_cached_keys or (entry_hash, None) in seen_cached_keys:
                    continue
                formatted_sz = format_bytes(entry.size_bytes)
                syn_title = f"{entry.title or 'Video'}\n💾 {formatted_sz}" if formatted_sz != "N/A" else (entry.title or "Video")
                syn_link = entry.source_link or f"magnet:?xt=urn:btih:{entry.infohash}"
                syn_stream = {
                    "name": f"{self.CACHED_NAME_PREFIX}[Cache Locale]",
                    "title": syn_title,
                    "url": self._build_playback_url(
                        link=syn_link,
                        title=entry.title,
                        poster=entry.poster,
                        category=category,
                        index=entry.cache_index,
                        content_type=content_type,
                        content_id=content_id,
                        is_cached=True,
                    ),
                    "behaviorHints": {
                        "notWebReady": False,
                    },
                    "_meta": {
                        "cached": True,
                        "infohash": entry.infohash,
                        "cache_index": entry.cache_index,
                    },
                }
                rewritten_streams.append(syn_stream)
                seen_cached_keys.add((entry_hash, entry.cache_index))

        # Prioritize cached streams at the very top, preserving relative order of other streams
        rewritten_streams.sort(
            key=lambda s: 1 if (isinstance(s.get("_meta"), dict) and s["_meta"].get("cached")) else 0,
            reverse=True,
        )

        updated_payload = dict(payload)
        updated_payload["streams"] = rewritten_streams
        return updated_payload

    def _needs_mediaflow_proxy(self, stream: dict) -> bool:
        bh = stream.get("behaviorHints")
        if isinstance(bh, dict) and bh.get("proxyHeaders"):
            return True
        return False

    def _extract_proxy_headers(self, stream: dict) -> dict[str, str] | None:
        bh = stream.get("behaviorHints")
        if isinstance(bh, dict):
            ph = bh.get("proxyHeaders")
            if isinstance(ph, dict):
                req = ph.get("request")
                if isinstance(req, dict):
                    return req
        return None

    def _extract_filename(self, stream: dict) -> str | None:
        bh = stream.get("behaviorHints")
        if isinstance(bh, dict) and bh.get("filename"):
            return bh.get("filename")
        return None

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

    def _mark_cached_if_ready(
        self,
        stream: dict,
        torrent_link: str,
        index: int | None,
        content_id: str | None = None,
    ) -> None:
        if not self.cache_enabled:
            return

        infohash = extract_infohash(torrent_link)
        normalized = normalize_infohash(infohash) if infohash else None

        cache_key = self.cache_manager.build_cache_key(torrent_link, index)
        is_ready = False
        cache_index = None
        if cache_key is not None and self.cache_manager.is_ready(cache_key):
            is_ready = True
            if hasattr(self.cache_manager, "parse_cache_key"):
                _, cache_index = self.cache_manager.parse_cache_key(cache_key)
        elif normalized and content_id and hasattr(self.cache_manager, "get_ready_entry_by_content"):
            entry = self.cache_manager.get_ready_entry_by_content(normalized, content_id)
            if entry is not None:
                is_ready = True
                cache_index = entry.cache_index
        elif normalized and content_id and self.cache_manager.is_content_ready(normalized, content_id):
            is_ready = True

        if not is_ready:
            return

        meta = stream.get("_meta")
        if not isinstance(meta, dict):
            meta = {}
        updated_meta = dict(meta)
        updated_meta["cached"] = True
        if cache_index is not None:
            updated_meta["cache_index"] = cache_index
        stream["_meta"] = updated_meta

        name = stream.get("name")
        if isinstance(name, str) and name.strip() and not name.startswith(self.CACHED_NAME_PREFIX):
            stream["name"] = f"{self.CACHED_NAME_PREFIX}{name}"

    def extract_download_candidates(self, payload: dict) -> list[dict[str, str | int | None]]:
        streams = payload.get("streams")
        if not isinstance(streams, list):
            return []

        candidates = []
        excluded_extensions = {".srt", ".txt", ".nfo", ".jpg", ".png", ".jpeg", ".pdf", ".zip", ".rar", ".html"}
        for stream in streams:
            if not isinstance(stream, dict):
                continue

            # Exclude known non-video file extensions from candidate list
            filename = None
            behavior_hints = stream.get("behaviorHints")
            if isinstance(behavior_hints, dict):
                filename = behavior_hints.get("filename")
            
            if not filename:
                filename = stream.get("title") or stream.get("description")
                
            if isinstance(filename, str):
                name_to_check = filename.split("\n")[0].strip()
                _, ext = os.path.splitext(name_to_check.lower())
                if ext in excluded_extensions or any(name_to_check.lower().endswith(ex) for ex in excluded_extensions):
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
                    "seeders": self._extract_seeders(stream),
                }
            )
        return candidates

    def _extract_seeders(self, stream: dict) -> int | None:
        meta = stream.get("_meta")
        if isinstance(meta, dict) and meta.get("seeders") is not None:
            try:
                return int(meta["seeders"])
            except (ValueError, TypeError):
                pass

        for field in ("description", "title", "name"):
            val = stream.get(field)
            if isinstance(val, str):
                match = re.search(r"👤\s*(\d+)", val)
                if match:
                    return int(match.group(1))
        return None

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
        is_cached: bool = False,
        force_play_route: bool = False,
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
        is_hls = (".m3u8" in link or "/proxy/hls" in link) and not is_cached and not force_play_route
        path = "/play/manifest.m3u8" if is_hls else "/play"
        return f"{self.public_base_url}{path}?{urlencode(params)}"
