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
