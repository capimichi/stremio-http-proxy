import pytest

from stremio_http_proxy.container.default_container import DefaultContainer


def test_default_container_requires_app_secret(monkeypatch):
    monkeypatch.delenv("APP_SECRET", raising=False)
    DefaultContainer.instance = None

    with pytest.raises(ValueError, match="APP_SECRET environment variable is required"):
        DefaultContainer()


def test_default_container_loads_prefetch_and_download_env_vars(monkeypatch, tmp_path):
    DefaultContainer.instance = None
    monkeypatch.setattr("stremio_http_proxy.container.default_container.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("DOWNLOAD_NO_PROGRESS_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("DOWNLOAD_PREFETCH_MIN_PROGRESS_BYTES", "2097152")
    monkeypatch.setenv("PREFETCH_TARGET_COMPLETED_PER_EPISODE", "2")
    monkeypatch.setenv("PREFETCH_SKIP_ZERO_SEEDERS", "false")

    container = DefaultContainer()
    assert container.download_no_progress_timeout_seconds == 120
    assert container.download_prefetch_min_progress_bytes == 2097152
    assert container.prefetch_target_completed_per_episode == 2
    assert container.prefetch_skip_zero_seeders is False

    # Also test default values
    DefaultContainer.instance = None
    monkeypatch.delenv("DOWNLOAD_NO_PROGRESS_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("DOWNLOAD_PREFETCH_MIN_PROGRESS_BYTES", raising=False)
    monkeypatch.delenv("PREFETCH_TARGET_COMPLETED_PER_EPISODE", raising=False)
    monkeypatch.delenv("PREFETCH_SKIP_ZERO_SEEDERS", raising=False)

    default_container = DefaultContainer()
    assert default_container.download_no_progress_timeout_seconds == 90
    assert default_container.download_prefetch_min_progress_bytes == 1048576
    assert default_container.prefetch_target_completed_per_episode == 1
    assert default_container.prefetch_skip_zero_seeders is True


def test_default_container_loads_cache_base_url(monkeypatch):
    DefaultContainer.instance = None
    monkeypatch.setattr("stremio_http_proxy.container.default_container.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://proxy.example.com")
    monkeypatch.setenv("CACHE_BASE_URL", "http://192.168.1.100:8691")

    container = DefaultContainer()
    assert container.public_base_url == "https://proxy.example.com"
    assert container.cache_base_url == "http://192.168.1.100:8691"

    # Default fallback when CACHE_BASE_URL is not set
    DefaultContainer.instance = None
    monkeypatch.delenv("CACHE_BASE_URL", raising=False)
    default_container = DefaultContainer()
    assert default_container.cache_base_url == "https://proxy.example.com"

    # Default fallback when CACHE_BASE_URL is empty
    DefaultContainer.instance = None
    monkeypatch.setenv("CACHE_BASE_URL", "  ")
    empty_container = DefaultContainer()
    assert empty_container.cache_base_url == "https://proxy.example.com"


def test_default_container_loads_torrserver_internal_url(monkeypatch):
    DefaultContainer.instance = None
    monkeypatch.setattr("stremio_http_proxy.container.default_container.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("APP_SECRET", "test-secret")
    monkeypatch.setenv("TORRSERVER_BASE_URL", "https://torrserver.example.com")
    monkeypatch.setenv("TORRSERVER_INTERNAL_URL", "http://torrserver:8090")

    container = DefaultContainer()
    assert container.torrserver_base_url == "https://torrserver.example.com"
    assert container.torrserver_internal_url == "http://torrserver:8090"

    # Default fallback when TORRSERVER_INTERNAL_URL is not set
    DefaultContainer.instance = None
    monkeypatch.delenv("TORRSERVER_INTERNAL_URL", raising=False)
    default_container = DefaultContainer()
    assert default_container.torrserver_internal_url == "https://torrserver.example.com"

    # Default fallback when TORRSERVER_INTERNAL_URL is empty
    DefaultContainer.instance = None
    monkeypatch.setenv("TORRSERVER_INTERNAL_URL", "   ")
    empty_container = DefaultContainer()
    assert empty_container.torrserver_internal_url == "https://torrserver.example.com"


