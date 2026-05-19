import asyncio

from injector import inject

from stremio_http_proxy.command.abstract_command import AbstractCommand
from stremio_http_proxy.service.download_worker_service import DownloadWorkerService


class WorkerCommand(AbstractCommand):
    command_name = "worker"

    @inject
    def __init__(self, download_worker_service: DownloadWorkerService):
        self.download_worker_service = download_worker_service

    def run(self):
        asyncio.run(self.download_worker_service.run_forever())
