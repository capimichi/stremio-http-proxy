from stremio_http_proxy.service.cache_token_service import CacheTokenService


def test_cache_token_service_builds_and_validates_token():
    service = CacheTokenService("secret", 259200)
    expires = service.build_expires_at(now=100)
    token = service.build_token("abc", 1, expires)

    assert expires == 259300
    assert service.is_valid("abc", 1, expires, token, now=200)


def test_cache_token_service_rejects_tampered_token():
    service = CacheTokenService("secret", 259200)
    expires = service.build_expires_at(now=100)

    assert not service.is_valid("abc", 1, expires, "wrong", now=200)


def test_cache_token_service_rejects_expired_token():
    service = CacheTokenService("secret", 259200)
    token = service.build_token("abc", 1, 100)

    assert not service.is_valid("abc", 1, 100, token, now=101)
