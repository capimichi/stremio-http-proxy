import time

from stremio_http_proxy.helper.signing_helper import build_hmac_sha256, constant_time_equals


class CacheTokenService:
    def __init__(self, app_secret: str, ttl_seconds: int):
        self.app_secret = app_secret
        self.ttl_seconds = ttl_seconds

    def build_expires_at(self, now: float | None = None) -> int:
        current_time = time.time() if now is None else now
        return int(current_time) + self.ttl_seconds

    def build_token(self, infohash: str, index: int, expires: int) -> str:
        payload = f"cache:{infohash}:{index}:{expires}"
        return build_hmac_sha256(self.app_secret, payload)

    def is_valid(self, infohash: str, index: int, expires: int, token: str, now: float | None = None) -> bool:
        current_time = int(time.time() if now is None else now)
        if expires < current_time:
            return False
        expected_token = self.build_token(infohash, index, expires)
        return constant_time_equals(token, expected_token)
