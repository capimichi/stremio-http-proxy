from injector import inject

from stremio_http_proxy.helper.hash_helper import extract_infohash


class StreamRewriteService:
    @inject
    def __init__(self, public_base_url: str):
        self.public_base_url = public_base_url.rstrip("/")

    def rewrite(self, payload: dict) -> dict:
        streams = payload.get("streams")
        if not isinstance(streams, list):
            return payload

        rewritten_streams = []
        for stream in streams:
            if not isinstance(stream, dict):
                rewritten_streams.append(stream)
                continue
            infohash = self._extract_infohash(stream)
            if infohash is None:
                rewritten_streams.append(stream)
                continue
            updated = dict(stream)
            updated["url"] = f"{self.public_base_url}/streams/{infohash}/playlist.m3u8"
            rewritten_streams.append(updated)

        updated_payload = dict(payload)
        updated_payload["streams"] = rewritten_streams
        return updated_payload

    def _extract_infohash(self, stream: dict) -> str | None:
        candidates = [
            stream.get("infoHash"),
            stream.get("url"),
            stream.get("externalUrl"),
            stream.get("magnetUrl"),
            stream.get("magnet"),
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
            infohash = extract_infohash(candidate)
            if infohash:
                return infohash
        return None
