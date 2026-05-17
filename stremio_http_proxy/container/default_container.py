import logging
import os

from dotenv import load_dotenv
from injector import Injector

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.client.upstream_client import UpstreamClient
from stremio_http_proxy.command.serve_command import ServeCommand
from stremio_http_proxy.controller.addon_controller import AddonController
from stremio_http_proxy.controller.health_controller import HealthController
from stremio_http_proxy.controller.playback_controller import PlaybackController
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
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.request_timeout_seconds = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "20"))

    def _init_logging(self) -> None:
        logging.basicConfig(level=getattr(logging, self.log_level.upper(), logging.INFO))

    def _init_bindings(self) -> None:
        upstream_client = UpstreamClient(self.upstream_base_url, self.request_timeout_seconds)
        torrserver_client = TorrServerClient(
            self.torrserver_base_url,
            self.request_timeout_seconds,
            self.torrserver_basic_auth_user,
            self.torrserver_basic_auth_password,
        )
        stream_rewrite_service = StreamRewriteService(self.public_base_url)
        playback_controller = PlaybackController(torrserver_client)
        serve_command = ServeCommand(self.api_host, self.api_port)

        self.injector.binder.bind(TorrServerClient, to=torrserver_client)
        self.injector.binder.bind(UpstreamClient, to=upstream_client)
        self.injector.binder.bind(StreamRewriteService, to=stream_rewrite_service)
        self.injector.binder.bind(PlaybackController, to=playback_controller)
        self.injector.binder.bind(ServeCommand, to=serve_command)
