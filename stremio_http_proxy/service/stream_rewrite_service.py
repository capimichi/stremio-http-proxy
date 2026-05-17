from urllib.parse import urlencode, urlparse

from injector import inject

from stremio_http_proxy.helper.hash_helper import extract_infohash


class StreamRewriteService:
    @inject
    def __init__(self, public_base_url: str):
        self.public_base_url = public_base_url.rstrip("/")

    def rewrite(self, payload: dict, category: str | None = None) -> dict:
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
            index = self._extract_index(updated)
            updated["url"] = self._build_playback_url(torrent_link, title, poster, category, index)
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
        return f"{self.public_base_url}/play?{urlencode(params)}"
