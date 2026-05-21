import pytest

from stremio_http_proxy.container.default_container import DefaultContainer


def test_default_container_requires_app_secret(monkeypatch):
    monkeypatch.delenv("APP_SECRET", raising=False)
    DefaultContainer.instance = None

    with pytest.raises(ValueError, match="APP_SECRET environment variable is required"):
        DefaultContainer()
