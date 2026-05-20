import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from stremio_http_proxy.service.basic_auth_service import BasicAuthService


def test_basic_auth_service_allows_requests_when_disabled():
    service = BasicAuthService()

    service.require_auth(None)


def test_basic_auth_service_rejects_missing_credentials_when_enabled():
    service = BasicAuthService("admin", "secret")

    with pytest.raises(HTTPException) as error:
        service.require_auth(None)

    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Basic"}


def test_basic_auth_service_rejects_invalid_credentials():
    service = BasicAuthService("admin", "secret")

    with pytest.raises(HTTPException):
        service.require_auth(HTTPBasicCredentials(username="admin", password="wrong"))


def test_basic_auth_service_accepts_valid_credentials():
    service = BasicAuthService("admin", "secret")

    service.require_auth(HTTPBasicCredentials(username="admin", password="secret"))
