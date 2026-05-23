import logging
import os

from dotenv import load_dotenv
from injector import Injector

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.command.serve_command import ServeCommand
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.service.download_queue_service import DownloadQueueService
from stremio_http_proxy.service.download_worker_service import DownloadWorkerService
from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.service.cache_token_service import CacheTokenService
from stremio_http_proxy.service.dashboard_service import DashboardService
from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService
from stremio_http_proxy.service.stream_rewrite_service import StreamRewriteService


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
        self.app_name = os.environ.get("APP_NAME", "Stremio HTTP Proxy")
        self.debug = os.environ.get("DEBUG", "false").lower() == "true"
        self.api_host = os.environ.get("API_HOST", "0.0.0.0")
        self.api_port = int(os.environ.get("API_PORT", "8691"))
        self.upstream_base_url = os.environ.get("UPSTREAM_BASE_URL", "https://example.com")
        self.torrserver_base_url = os.environ.get("TORRSERVER_BASE_URL", "http://localhost:8090")
        self.torrserver_basic_auth_user = os.environ.get("TORRSERVER_BASIC_AUTH_USER")
        self.torrserver_basic_auth_password = os.environ.get("TORRSERVER_BASIC_AUTH_PASSWORD")
        self.public_base_url = os.environ.get("PUBLIC_BASE_URL", f"http://localhost:{self.api_port}")
        self.app_secret = os.environ.get("APP_SECRET")
        self.dashboard_basic_auth_user = os.environ.get("DASHBOARD_BASIC_AUTH_USER")
        self.dashboard_basic_auth_password = os.environ.get("DASHBOARD_BASIC_AUTH_PASSWORD")
        self.cache_token_ttl_seconds = int(os.environ.get("CACHE_TOKEN_TTL_SECONDS", str(72 * 60 * 60)))
        self.log_dir = os.environ.get("LOG_DIR", "var/log")
        self.local_cache_dir = os.environ.get("LOCAL_CACHE_DIR", "var/cache")
        self.sqlite_path = os.environ.get("SQLITE_PATH", "var/db/cache.sqlite")
        self.local_cache_max_age_days = int(os.environ.get("LOCAL_CACHE_MAX_AGE_DAYS", "7"))
        self.local_cache_max_size_gb = int(os.environ.get("LOCAL_CACHE_MAX_SIZE_GB", "20"))
        self.download_queue_poll_seconds = int(os.environ.get("DOWNLOAD_QUEUE_POLL_SECONDS", "1"))
        self.download_max_attempts = int(os.environ.get("DOWNLOAD_MAX_ATTEMPTS", "3"))
        self.download_connect_timeout_seconds = int(os.environ.get("DOWNLOAD_CONNECT_TIMEOUT_SECONDS", "10"))
        self.download_no_progress_timeout_seconds = int(os.environ.get("DOWNLOAD_NO_PROGRESS_TIMEOUT_SECONDS", "30"))
        self.download_min_progress_bytes = int(os.environ.get("DOWNLOAD_MIN_PROGRESS_BYTES", str(32 * 1024 * 1024)))
        self.download_min_progress_window_seconds = int(os.environ.get("DOWNLOAD_MIN_PROGRESS_WINDOW_SECONDS", "120"))
        self.download_max_total_seconds = int(os.environ.get("DOWNLOAD_MAX_TOTAL_SECONDS", str(45 * 60)))
        self.download_progress_log_interval_seconds = int(os.environ.get("DOWNLOAD_PROGRESS_LOG_INTERVAL_SECONDS", "10"))
        self.cache_enabled = os.environ.get("CACHE_ENABLED", "true").lower() == "true"
        self.next_episode_prefetch_enabled = os.environ.get("NEXT_EPISODE_PREFETCH_ENABLED", "true").lower() == "true"
        self.next_episode_prefetch_stream_limit = int(os.environ.get("NEXT_EPISODE_PREFETCH_STREAM_LIMIT", "3"))
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.request_timeout_seconds = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))
        if not self.app_secret or not self.app_secret.strip():
            raise ValueError("APP_SECRET environment variable is required")

    def _init_logging(self) -> None:
        logging.basicConfig(level=getattr(logging, self.log_level.upper(), logging.INFO))

    def _init_bindings(self) -> None:
        logger_factory = LoggerFactory(self.log_dir, self.log_level)
        upstream_client = UpstreamClient(self.upstream_base_url, self.request_timeout_seconds)
        torrserver_client = TorrServerClient(
            self.torrserver_base_url,
            self.request_timeout_seconds,
            self.torrserver_basic_auth_user,
            self.torrserver_basic_auth_password,
        )
        db_manager = DbManager(self.sqlite_path)
        cache_manager = CacheManager(
            self.local_cache_dir,
            db_manager,
            self.local_cache_max_age_days,
            self.local_cache_max_size_gb,
            logger_factory,
        )
        basic_auth_service = BasicAuthService(
            self.dashboard_basic_auth_user,
            self.dashboard_basic_auth_password,
        )
        cache_token_service = CacheTokenService(self.app_secret, self.cache_token_ttl_seconds)
        cache_service = CacheService(cache_manager, self.public_base_url, cache_token_service, self.cache_enabled)
        stream_rewrite_service = StreamRewriteService(self.public_base_url, cache_manager, self.cache_enabled)
        download_queue_service = DownloadQueueService(cache_manager, self.download_max_attempts, self.cache_enabled)
        next_episode_prefetch_service = NextEpisodePrefetchService(
            upstream_client,
            stream_rewrite_service,
            download_queue_service,
            self.next_episode_prefetch_enabled,
            self.next_episode_prefetch_stream_limit,
        )
        dashboard_service = DashboardService(cache_manager, self.public_base_url)
        download_worker_service = DownloadWorkerService(
            torrserver_client,
            cache_manager,
            logger_factory,
            self.download_queue_poll_seconds,
            self.download_connect_timeout_seconds,
            self.download_no_progress_timeout_seconds,
            self.download_min_progress_bytes,
            self.download_min_progress_window_seconds,
            self.download_max_total_seconds,
            self.download_progress_log_interval_seconds,
        )
        serve_command = ServeCommand(self.api_host, self.api_port)

        self.injector.binder.bind(LoggerFactory, to=logger_factory)
        self.injector.binder.bind(TorrServerClient, to=torrserver_client)
        self.injector.binder.bind(UpstreamClient, to=upstream_client)
        self.injector.binder.bind(StreamRewriteService, to=stream_rewrite_service)
        self.injector.binder.bind(DbManager, to=db_manager)
        self.injector.binder.bind(CacheManager, to=cache_manager)
        self.injector.binder.bind(BasicAuthService, to=basic_auth_service)
        self.injector.binder.bind(CacheTokenService, to=cache_token_service)
        self.injector.binder.bind(CacheService, to=cache_service)
        self.injector.binder.bind(DownloadQueueService, to=download_queue_service)
        self.injector.binder.bind(DashboardService, to=dashboard_service)
        self.injector.binder.bind(NextEpisodePrefetchService, to=next_episode_prefetch_service)
        self.injector.binder.bind(DownloadWorkerService, to=download_worker_service)
        self.injector.binder.bind(ServeCommand, to=serve_command)
