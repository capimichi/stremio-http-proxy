import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from injector import Injector

from stremio_http_proxy.client.torrent_client import TorrentClient
from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.command.add_torrent_command import AddTorrentCommand
from stremio_http_proxy.command.cleanup_cache_command import CleanupCacheCommand
from stremio_http_proxy.command.monitor_torrents_command import MonitorTorrentsCommand
from stremio_http_proxy.command.serve_command import ServeCommand
from stremio_http_proxy.controller.addon_controller import AddonController
from stremio_http_proxy.controller.chunk_controller import ChunkController
from stremio_http_proxy.controller.health_controller import HealthController
from stremio_http_proxy.controller.playlist_controller import PlaylistController
from stremio_http_proxy.repository.torrent_registry_repository import TorrentRegistryRepository
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.service.playlist_service import PlaylistService
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService
from stremio_http_proxy.service.torrent_service import TorrentService


class DefaultContainer:
    instance = None

    @staticmethod
    def getInstance() -> "DefaultContainer":
        if DefaultContainer.instance is None:
            DefaultContainer.instance = DefaultContainer()
        return DefaultContainer.instance

    def __init__(self):
        self.injector = Injector()
        load_dotenv()
        self._init_variables()
        self._init_logging()
        self._init_bindings()

    def get(self, key):
        return self.injector.get(key)

    def get_var(self, key: str):
        return getattr(self, key)

    def _init_variables(self) -> None:
        root_dir = Path(__file__).resolve().parents[2]
        self.app_name = os.environ.get("APP_NAME", "Stremio HTTP Proxy")
        self.debug = os.environ.get("DEBUG", "false").lower() == "true"
        self.api_host = os.environ.get("API_HOST", "0.0.0.0")
        self.api_port = int(os.environ.get("API_PORT", "8459"))
        self.upstream_base_url = os.environ.get("UPSTREAM_BASE_URL", "https://example.com")
        self.public_base_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8459")
        self.cache_dir = os.environ.get("CACHE_DIR", str(root_dir / "var" / "cache"))
        self.torrent_state_dir = os.environ.get(
            "TORRENT_STATE_DIR", str(root_dir / "var" / "torrents")
        )
        self.torrent_registry_path = os.environ.get(
            "TORRENT_REGISTRY_PATH", str(root_dir / "var" / "torrents" / "registry.json")
        )
        self.max_cache_size_gb = int(os.environ.get("MAX_CACHE_SIZE_GB", "50"))
        self.default_cache_max_age_days = int(os.environ.get("DEFAULT_CACHE_MAX_AGE_DAYS", "7"))
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.request_timeout_seconds = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))

        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        Path(self.torrent_state_dir).mkdir(parents=True, exist_ok=True)

    def _init_logging(self) -> None:
        logging.basicConfig(level=getattr(logging, self.log_level.upper(), logging.INFO))

    def _init_bindings(self) -> None:
        registry_repository = TorrentRegistryRepository(self.torrent_registry_path)
        cache_service = CacheService(self.cache_dir)
        torrent_client = TorrentClient(self.torrent_state_dir)
        upstream_client = UpstreamClient(self.upstream_base_url, self.request_timeout_seconds)
        stream_rewrite_service = StreamRewriteService(self.public_base_url)
        playlist_service = PlaylistService(self.public_base_url, registry_repository)
        torrent_service = TorrentService(
            torrent_client,
            registry_repository,
            cache_service,
            self.max_cache_size_gb,
        )
        serve_command = ServeCommand(self.api_host, self.api_port)
        cleanup_cache_command = CleanupCacheCommand(
            torrent_service,
            self.default_cache_max_age_days,
        )

        self.injector.binder.bind(TorrentRegistryRepository, to=registry_repository)
        self.injector.binder.bind(CacheService, to=cache_service)
        self.injector.binder.bind(TorrentClient, to=torrent_client)
        self.injector.binder.bind(UpstreamClient, to=upstream_client)
        self.injector.binder.bind(StreamRewriteService, to=stream_rewrite_service)
        self.injector.binder.bind(PlaylistService, to=playlist_service)
        self.injector.binder.bind(TorrentService, to=torrent_service)
        self.injector.binder.bind(ServeCommand, to=serve_command)
        self.injector.binder.bind(CleanupCacheCommand, to=cleanup_cache_command)
