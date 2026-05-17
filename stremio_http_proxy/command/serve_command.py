import uvicorn
from injector import inject

from stremio_http_proxy.command.abstract_command import AbstractCommand


class ServeCommand(AbstractCommand):
    command_name = "serve"

    @inject
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port

    def run(self):
        uvicorn.run(
            "stremio_http_proxy.api:app",
            host=self.host,
            port=self.port,
            reload=False,
        )
